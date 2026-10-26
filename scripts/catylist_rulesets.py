#!/usr/bin/env python3
"""Plan or apply Catylist ADR-0006 default-branch rulesets.

The repository inventory is read from ``dlworrell/Catylist`` and the baseline
rulesets from ``dlworrell/repo_templates``, each at a pinned commit SHA. Every
inventory entry with ``default_branch_policy: protected`` is compared with the
baseline, and the drift is reported. With ``--apply`` the drift is corrected:
rulesets are created or updated by name and repository merge settings are
patched.

Planning and drift detection are pure functions over plain JSON values so that
they can be tested without network access. All GitHub I/O is isolated in
``GitHubClient`` and ``collect_state``/``apply_plan``.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Protocol
import urllib.error
import urllib.parse
import urllib.request


REPORT_SCHEMA = "aems.catylist-rulesets-report.v1"
INVENTORY_SCHEMA = "catylist.repository-inventory.v1"
POLICY_PROTECTED = "protected"
KNOWN_POLICIES = frozenset({"protected", "excluded", "pending-classification"})

CATYLIST_REPOSITORY = "dlworrell/Catylist"
INVENTORY_PATH = "inventory/repositories.json"
TEMPLATES_REPOSITORY = "dlworrell/repo_templates"
BRANCH_RULESET_PATH = "rulesets/protect-default-branch.json"
TAG_RULESET_PATH = "rulesets/protect-release-tags.json"
BRANCH_RULESET_NAME = "protect-default-branch"
TAG_RULESET_NAME = "protect-release-tags"

# Catylist ADR-0013: dev-daily and fitment get the default-branch rules, but
# only in repositories that have adopted the daily and fitment branches. The
# adopted set is AEMS config/fitment.json, and both branches must exist before
# the ruleset is applied.
INTEGRATION_RULESET_PATH = "rulesets/protect-integration-branches.json"
INTEGRATION_RULESET_NAME = "protect-integration-branches"
INTEGRATION_BRANCHES = ("dev-daily", "fitment")
FITMENT_CONFIG_SCHEMA = "aems.fitment-config.v1"
DEFAULT_FITMENT_CONFIG = Path(__file__).resolve().parents[1] / "config" / "fitment.json"

# Legacy explicit opt-in for ruleset sandbox experiments. Pending Catylist
# ADR-0014 proposes removing the named testbed/adoption prerequisite; it has
# not been accepted upstream. See the retained proposal in
# docs/engineering/Catylist-experimental-sandbox-20261026.patch. Once its
# experimental inventory entry lands, normal inventory selection applies.
SANDBOX_REPOSITORY = "dlworrell/ruleset-sandbox"

# ADR-0006 section 2, rule 4 and the paragraph on head-branch deletion.
DESIRED_MERGE_SETTINGS: dict[str, bool] = {
    "allow_merge_commit": True,
    "allow_squash_merge": False,
    "allow_rebase_merge": False,
    "delete_branch_on_merge": True,
}

# Rule types the baseline must never contain. Linear history conflicts with
# merge commits (ADR-0006 section 2, rule 4). Status checks and code scanning
# are per-repository and outside the baseline (ADR-0006 section 4).
FORBIDDEN_RULE_TYPES = frozenset(
    {"required_linear_history", "required_status_checks", "code_scanning"}
)

ADMIN_TOKEN_ENV = "RULESET_ADMIN_TOKEN"
SOURCE_TOKEN_ENV = "SOURCE_TOKEN"
API_ROOT = "https://api.github.com"
API_VERSION = "2022-11-28"

SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
FULL_NAME_PATTERN = re.compile(r"^[A-Za-z0-9-]+/[A-Za-z0-9._-]+$")


class PlanError(ValueError):
    """Raised when inputs cannot be planned safely."""


# ---------------------------------------------------------------------------
# Input validation (pure)
# ---------------------------------------------------------------------------


def validate_sha(value: str, label: str) -> str:
    """Return a lower-case 40-hex commit SHA or raise ``PlanError``."""

    candidate = (value or "").strip().lower()
    if not SHA_PATTERN.fullmatch(candidate):
        raise PlanError(
            f"{label} must be a full 40-character hexadecimal commit SHA"
        )
    return candidate


def parse_repos_filter(value: str | None) -> list[str]:
    """Parse a comma-separated list of ``owner/name`` repository names."""

    if not value:
        return []
    names: list[str] = []
    seen: set[str] = set()
    for raw in value.split(","):
        name = raw.strip()
        if not name:
            continue
        if not FULL_NAME_PATTERN.fullmatch(name):
            raise PlanError(f"invalid repository name in filter: {name!r}")
        key = name.lower()
        if key not in seen:
            seen.add(key)
            names.append(name)
    return names


def validate_inventory(inventory: Any) -> list[dict[str, Any]]:
    """Validate the Catylist inventory and return its repository entries."""

    if not isinstance(inventory, dict):
        raise PlanError("inventory must be a JSON object")
    if inventory.get("schema") != INVENTORY_SCHEMA:
        raise PlanError(
            f"unsupported inventory schema {inventory.get('schema')!r}; "
            f"expected {INVENTORY_SCHEMA}"
        )
    entries = inventory.get("repositories")
    if not isinstance(entries, list):
        raise PlanError("inventory.repositories must be a list")
    seen: set[str] = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise PlanError(f"inventory entry {index} must be an object")
        name = entry.get("full_name")
        if not isinstance(name, str) or not FULL_NAME_PATTERN.fullmatch(name):
            raise PlanError(f"inventory entry {index} has invalid full_name")
        policy = entry.get("default_branch_policy")
        if policy not in KNOWN_POLICIES:
            raise PlanError(
                f"{name}: unknown default_branch_policy {policy!r}"
            )
        if name.lower() in seen:
            raise PlanError(f"duplicate inventory entry for {name}")
        seen.add(name.lower())
    return entries


def select_repositories(
    inventory: Any, repos_filter: list[str]
) -> tuple[list[str], list[dict[str, str]]]:
    """Return (selected repositories, skipped filter entries with reasons).

    Only entries whose ``default_branch_policy`` is ``protected`` are
    selected. A filter narrows that set. A filter name outside the inventory
    is an error, except for the ruleset sandbox.
    """

    entries = validate_inventory(inventory)
    by_key = {entry["full_name"].lower(): entry for entry in entries}
    protected = [
        entry["full_name"]
        for entry in entries
        if entry["default_branch_policy"] == POLICY_PROTECTED
    ]
    if not repos_filter:
        return protected, []

    selected: list[str] = []
    skipped: list[dict[str, str]] = []
    for name in repos_filter:
        key = name.lower()
        entry = by_key.get(key)
        if entry is None:
            if key == SANDBOX_REPOSITORY.lower():
                selected.append(SANDBOX_REPOSITORY)
                continue
            raise PlanError(
                f"{name} is not in the Catylist inventory at the pinned ref"
            )
        if entry["default_branch_policy"] != POLICY_PROTECTED:
            skipped.append(
                {
                    "repository": entry["full_name"],
                    "reason": (
                        "default_branch_policy is "
                        f"{entry['default_branch_policy']}"
                    ),
                }
            )
            continue
        selected.append(entry["full_name"])
    return selected, skipped


def validate_desired_ruleset(
    ruleset: Any, *, expected_name: str, expected_target: str
) -> dict[str, Any]:
    """Validate a baseline ruleset from repo_templates against ADR-0006."""

    if not isinstance(ruleset, dict):
        raise PlanError(f"{expected_name}: ruleset must be a JSON object")
    if ruleset.get("name") != expected_name:
        raise PlanError(
            f"ruleset name {ruleset.get('name')!r} != {expected_name!r}"
        )
    if ruleset.get("target") != expected_target:
        raise PlanError(f"{expected_name}: target must be {expected_target}")
    if ruleset.get("enforcement") != "active":
        raise PlanError(f"{expected_name}: enforcement must be active")
    if ruleset.get("bypass_actors", []) != []:
        raise PlanError(
            f"{expected_name}: bypass_actors must be empty (ADR-0006 rule 6)"
        )
    conditions = ruleset.get("conditions")
    if not isinstance(conditions, dict) or not isinstance(
        conditions.get("ref_name"), dict
    ):
        raise PlanError(f"{expected_name}: conditions.ref_name is required")
    rules = ruleset.get("rules")
    if not isinstance(rules, list) or not rules:
        raise PlanError(f"{expected_name}: rules must be a non-empty list")
    seen: set[str] = set()
    for rule in rules:
        if not isinstance(rule, dict) or not isinstance(rule.get("type"), str):
            raise PlanError(f"{expected_name}: every rule needs a type")
        rule_type = rule["type"]
        if rule_type in FORBIDDEN_RULE_TYPES:
            raise PlanError(
                f"{expected_name}: rule {rule_type} is not permitted by "
                "ADR-0006"
            )
        if rule_type in seen:
            raise PlanError(f"{expected_name}: duplicate rule {rule_type}")
        seen.add(rule_type)
    return {
        "name": ruleset["name"],
        "target": ruleset["target"],
        "enforcement": ruleset["enforcement"],
        "conditions": copy.deepcopy(conditions),
        "bypass_actors": [],
        "rules": copy.deepcopy(rules),
    }


def load_adopted(path: Path) -> frozenset[str]:
    """Return the lower-cased repositories that adopted Catylist ADR-0013."""

    if not path.is_file():
        return frozenset()
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema") != FITMENT_CONFIG_SCHEMA:
        raise PlanError(f"{path}: schema must be {FITMENT_CONFIG_SCHEMA}")
    names = data.get("repositories")
    if not isinstance(names, list) or not all(
        isinstance(n, str) and FULL_NAME_PATTERN.fullmatch(n) for n in names
    ):
        raise PlanError(f"{path}: repositories must be a list of owner/name")
    return frozenset(n.lower() for n in names)


def desired_for(
    repository: str, desired: list[dict[str, Any]], adopted: frozenset[str]
) -> list[dict[str, Any]]:
    """The baseline rulesets that apply to one repository."""

    if repository.lower() in adopted:
        return list(desired)
    return [r for r in desired if r["name"] != INTEGRATION_RULESET_NAME]


# ---------------------------------------------------------------------------
# Drift detection and planning (pure)
# ---------------------------------------------------------------------------


def _canonical(value: Any) -> Any:
    """Sort lists of scalars and object keys so comparison ignores order."""

    if isinstance(value, dict):
        return {key: _canonical(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        items = [_canonical(item) for item in value]
        return sorted(items, key=lambda item: json.dumps(item, sort_keys=True))
    return value


def _drift(field: str, desired: Any, current: Any) -> dict[str, Any]:
    return {"field": field, "desired": desired, "current": current}


def diff_ruleset(
    desired: dict[str, Any], current: dict[str, Any] | None
) -> list[dict[str, Any]]:
    """Return drift items between a desired ruleset and the current one.

    Rule parameters are compared on the keys the baseline declares; keys the
    API adds with defaults are ignored. Rules present in the repository but
    not in the baseline are drift, because updating replaces the rule list.
    """

    if current is None:
        return [_drift("ruleset", "present", "missing")]

    items: list[dict[str, Any]] = []
    for field in ("target", "enforcement"):
        if current.get(field) != desired[field]:
            items.append(_drift(field, desired[field], current.get(field)))

    if _canonical(current.get("conditions") or {}) != _canonical(
        desired["conditions"]
    ):
        items.append(
            _drift("conditions", desired["conditions"], current.get("conditions"))
        )

    current_bypass = current.get("bypass_actors") or []
    if _canonical(current_bypass) != _canonical(desired["bypass_actors"]):
        items.append(
            _drift("bypass_actors", desired["bypass_actors"], current_bypass)
        )

    current_rules: dict[str, dict[str, Any]] = {}
    for rule in current.get("rules") or []:
        if isinstance(rule, dict) and isinstance(rule.get("type"), str):
            current_rules[rule["type"]] = rule
    desired_rules = {rule["type"]: rule for rule in desired["rules"]}

    for rule_type, rule in desired_rules.items():
        existing = current_rules.get(rule_type)
        if existing is None:
            items.append(_drift(f"rules.{rule_type}", "present", "missing"))
            continue
        wanted = rule.get("parameters") or {}
        actual = existing.get("parameters") or {}
        for key in sorted(wanted):
            if _canonical(actual.get(key)) != _canonical(wanted[key]):
                items.append(
                    _drift(
                        f"rules.{rule_type}.parameters.{key}",
                        wanted[key],
                        actual.get(key),
                    )
                )
    for rule_type in sorted(set(current_rules) - set(desired_rules)):
        items.append(_drift(f"rules.{rule_type}", "absent", "present"))
    return items


def diff_merge_settings(
    current: dict[str, Any],
    desired: dict[str, bool] = DESIRED_MERGE_SETTINGS,
) -> list[dict[str, Any]]:
    """Return drift items for repository merge settings."""

    return [
        _drift(key, value, current.get(key))
        for key, value in desired.items()
        if current.get(key) is not value
    ]


def plan_repository(
    repository: str,
    desired_rulesets: list[dict[str, Any]],
    current_rulesets: list[dict[str, Any]],
    current_settings: dict[str, Any],
) -> dict[str, Any]:
    """Plan the changes needed to bring one repository to the baseline.

    ``current_rulesets`` holds the full repository-level rulesets (as returned
    by ``GET /repos/{repo}/rulesets/{id}``) whose names match a desired
    ruleset. Rulesets are matched by name.
    """

    by_name: dict[str, list[dict[str, Any]]] = {}
    for ruleset in current_rulesets:
        by_name.setdefault(ruleset.get("name", ""), []).append(ruleset)

    ruleset_plans: list[dict[str, Any]] = []
    for desired in desired_rulesets:
        matches = by_name.get(desired["name"], [])
        if len(matches) > 1:
            raise PlanError(
                f"{repository}: {len(matches)} rulesets are named "
                f"{desired['name']}; resolve the duplicates manually"
            )
        current = matches[0] if matches else None
        drift = diff_ruleset(desired, current)
        if current is None:
            action = "create"
        elif drift:
            action = "update"
        else:
            action = "none"
        ruleset_plans.append(
            {
                "name": desired["name"],
                "ruleset_id": current.get("id") if current else None,
                "action": action,
                "drift": drift,
                "payload": desired if action != "none" else None,
            }
        )

    settings_drift = diff_merge_settings(current_settings)
    patch = {item["field"]: item["desired"] for item in settings_drift}
    return {
        "repository": repository,
        "rulesets": ruleset_plans,
        "merge_settings": {
            "action": "patch" if patch else "none",
            "drift": settings_drift,
            "payload": patch or None,
        },
    }


def plan_has_changes(plan: dict[str, Any]) -> bool:
    return plan["merge_settings"]["action"] != "none" or any(
        item["action"] != "none" for item in plan["rulesets"]
    )


# ---------------------------------------------------------------------------
# Reporting (pure)
# ---------------------------------------------------------------------------


def _strip_payloads(plan: dict[str, Any] | None) -> dict[str, Any] | None:
    if plan is None:
        return None
    result = copy.deepcopy(plan)
    for item in result["rulesets"]:
        item.pop("payload", None)
    result["merge_settings"].pop("payload", None)
    return result


def build_report(
    *,
    mode: str,
    catylist_ref: str,
    templates_ref: str,
    repos_filter: list[str],
    skipped: list[dict[str, str]],
    results: list[dict[str, Any]],
) -> dict[str, Any]:
    entries = []
    for result in results:
        entries.append(
            {
                "repository": result["repository"],
                "status": result["status"],
                "error": result.get("error"),
                "unmanaged_rulesets": result.get("unmanaged_rulesets", []),
                "before": _strip_payloads(result.get("before")),
                "after": _strip_payloads(result.get("after")),
            }
        )
    statuses = [entry["status"] for entry in entries]
    return {
        "schema": REPORT_SCHEMA,
        "mode": mode,
        "sources": {
            "inventory": {
                "repository": CATYLIST_REPOSITORY,
                "path": INVENTORY_PATH,
                "ref": catylist_ref,
            },
            "rulesets": {
                "repository": TEMPLATES_REPOSITORY,
                "paths": [BRANCH_RULESET_PATH, TAG_RULESET_PATH, INTEGRATION_RULESET_PATH],
                "ref": templates_ref,
            },
        },
        "desired_merge_settings": dict(DESIRED_MERGE_SETTINGS),
        "repos_filter": repos_filter,
        "skipped": skipped,
        "summary": {
            status: statuses.count(status)
            for status in sorted(set(statuses))
        },
        "repositories": entries,
    }


def _describe(drift: list[dict[str, Any]]) -> str:
    if not drift:
        return "compliant"
    if len(drift) == 1 and drift[0]["field"] == "ruleset":
        return "missing"
    return f"{len(drift)} drift: " + ", ".join(
        f"`{item['field']}`" for item in drift
    )


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def render_markdown(report: dict[str, Any]) -> str:
    dry_run = report["mode"] == "dry-run"
    sources = report["sources"]
    lines = [
        "# Catylist ADR-0006 ruleset drift report",
        "",
        f"- Mode: **{report['mode']}**",
        (
            f"- Inventory: `{sources['inventory']['repository']}` "
            f"`{sources['inventory']['path']}` @ "
            f"`{sources['inventory']['ref']}`"
        ),
        (
            f"- Rulesets: `{sources['rulesets']['repository']}` @ "
            f"`{sources['rulesets']['ref']}`"
        ),
        (
            "- Repository filter: "
            + (", ".join(f"`{name}`" for name in report["repos_filter"])
               or "none (all protected entries)")
        ),
        "- Summary: "
        + (
            ", ".join(f"{key}: {value}" for key, value in report["summary"].items())
            or "no repositories selected"
        ),
        "",
        "| Repository | Item | Before | Action | After |",
        "|---|---|---|---|---|",
    ]
    for entry in report["repositories"]:
        repo = entry["repository"]
        before = entry["before"]
        after = entry["after"]
        if before is None:
            lines.append(
                f"| `{repo}` | all | error | none | "
                f"{_cell(entry.get('error') or 'unknown error')} |"
            )
            continue
        after_items: dict[str, list[dict[str, Any]]] = {}
        if after is not None:
            for item in after["rulesets"]:
                after_items[item["name"]] = item["drift"]
            after_items["merge settings"] = after["merge_settings"]["drift"]
        rows = [
            (item["name"], item["drift"], item["action"])
            for item in before["rulesets"]
        ]
        rows.append(
            (
                "merge settings",
                before["merge_settings"]["drift"],
                before["merge_settings"]["action"],
            )
        )
        for name, drift, action in rows:
            if action == "none":
                action_text = "none"
            elif dry_run:
                action_text = f"would {action}"
            else:
                action_text = action
            if dry_run:
                after_text = "unchanged (dry run)" if drift else "compliant"
            elif entry["status"] == "error" and after is None:
                after_text = _cell(entry.get("error") or "error")
            else:
                after_text = _describe(after_items.get(name, drift))
            lines.append(
                f"| `{repo}` | `{name}` | {_cell(_describe(drift))} | "
                f"{action_text} | {_cell(after_text)} |"
            )
    if report["skipped"]:
        lines += ["", "## Skipped by policy", ""]
        for item in report["skipped"]:
            lines.append(f"- `{item['repository']}`: {item['reason']}")

    details: list[str] = []
    for entry in report["repositories"]:
        before = entry["before"]
        if entry["unmanaged_rulesets"]:
            details.append(
                f"- `{entry['repository']}` also has unmanaged rulesets: "
                + ", ".join(f"`{name}`" for name in entry["unmanaged_rulesets"])
            )
        if before is None:
            continue
        drift_items = [
            (item["name"], drift)
            for item in before["rulesets"]
            for drift in item["drift"]
        ] + [("merge settings", d) for d in before["merge_settings"]["drift"]]
        for name, drift in drift_items:
            details.append(
                f"- `{entry['repository']}` `{name}` `{drift['field']}`: "
                f"current `{json.dumps(drift['current'], sort_keys=True)}`, "
                f"desired `{json.dumps(drift['desired'], sort_keys=True)}`"
            )
    if details:
        lines += ["", "## Drift details (before)", ""] + details
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# GitHub I/O
# ---------------------------------------------------------------------------


class GitHubError(RuntimeError):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(f"HTTP {status}: {message}")
        self.status = status


class Client(Protocol):
    def request(
        self, method: str, path: str, body: Any | None = None
    ) -> Any: ...

    def list_rulesets(self, repository: str) -> list[dict[str, Any]]: ...


def _next_link(header: str | None) -> str | None:
    if not header:
        return None
    for part in header.split(","):
        section = part.split(";")
        if len(section) < 2:
            continue
        url = section[0].strip().strip("<>")
        if any(s.strip() == 'rel="next"' for s in section[1:]):
            return url
    return None


class GitHubClient:
    """Minimal GitHub REST client. The token is never logged or returned."""

    def __init__(self, token: str | None, *, timeout: float = 30.0) -> None:
        self._token = token
        self._timeout = timeout

    def _redact(self, text: str) -> str:
        if self._token:
            text = text.replace(self._token, "***")
        return text

    def _open(
        self,
        method: str,
        url: str,
        body: Any | None,
        accept: str = "application/vnd.github+json",
    ) -> tuple[bytes, Any]:
        if not url.startswith(API_ROOT + "/"):
            raise GitHubError(0, "refusing to send a request outside the API")
        data = None
        headers = {
            "Accept": accept,
            "X-GitHub-Api-Version": API_VERSION,
            "User-Agent": "aems-catylist-rulesets",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            url, data=data, headers=headers, method=method
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                return response.read(), response.headers
        except urllib.error.HTTPError as exc:
            detail = exc.reason
            try:
                payload = json.loads(exc.read().decode("utf-8"))
                detail = payload.get("message", detail)
            except (ValueError, UnicodeDecodeError, AttributeError):
                pass
            raise GitHubError(
                exc.code, self._redact(f"{method} {url}: {detail}")
            ) from None
        except urllib.error.URLError as exc:
            raise GitHubError(
                0, self._redact(f"{method} {url}: {exc.reason}")
            ) from None

    def request(self, method: str, path: str, body: Any | None = None) -> Any:
        raw, _ = self._open(method, API_ROOT + path, body)
        return json.loads(raw.decode("utf-8")) if raw else None

    def list_rulesets(self, repository: str) -> list[dict[str, Any]]:
        url: str | None = (
            f"{API_ROOT}/repos/{repository}/rulesets"
            "?includes_parents=false&per_page=100"
        )
        results: list[dict[str, Any]] = []
        while url:
            raw, headers = self._open("GET", url, None)
            results.extend(json.loads(raw.decode("utf-8")))
            url = _next_link(headers.get("Link"))
        return results

    def get_file(self, repository: str, path: str, ref: str) -> Any:
        query = urllib.parse.urlencode({"ref": ref})
        raw, _ = self._open(
            "GET",
            f"{API_ROOT}/repos/{repository}/contents/{path}?{query}",
            None,
            accept="application/vnd.github.raw+json",
        )
        return json.loads(raw.decode("utf-8"))


def collect_state(
    client: Client, repository: str, desired_names: set[str]
) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    """Read managed rulesets, merge settings and unmanaged ruleset names."""

    summaries = [
        item
        for item in client.list_rulesets(repository)
        if item.get("source_type", "Repository") == "Repository"
    ]
    managed = [
        client.request("GET", f"/repos/{repository}/rulesets/{item['id']}")
        for item in summaries
        if item.get("name") in desired_names
    ]
    unmanaged = sorted(
        item.get("name", "") for item in summaries
        if item.get("name") not in desired_names
    )
    repo = client.request("GET", f"/repos/{repository}")
    if repo.get("archived"):
        raise PlanError(f"{repository} is archived")
    settings = {key: repo.get(key) for key in DESIRED_MERGE_SETTINGS}
    return managed, settings, unmanaged


def apply_plan(client: Client, plan: dict[str, Any]) -> None:
    repository = plan["repository"]
    for item in plan["rulesets"]:
        if item["action"] == "create":
            client.request("POST", f"/repos/{repository}/rulesets", item["payload"])
        elif item["action"] == "update":
            client.request(
                "PUT",
                f"/repos/{repository}/rulesets/{item['ruleset_id']}",
                item["payload"],
            )
    if plan["merge_settings"]["action"] == "patch":
        client.request(
            "PATCH", f"/repos/{repository}", plan["merge_settings"]["payload"]
        )


def process_repository(
    client: Client,
    repository: str,
    desired_rulesets: list[dict[str, Any]],
    *,
    apply: bool,
) -> dict[str, Any]:
    names = {ruleset["name"] for ruleset in desired_rulesets}
    result: dict[str, Any] = {
        "repository": repository,
        "before": None,
        "after": None,
    }
    try:
        if INTEGRATION_RULESET_NAME in names:
            for branch in INTEGRATION_BRANCHES:
                try:
                    client.request("GET", f"/repos/{repository}/branches/{branch}")
                except GitHubError as exc:
                    if exc.status == 404:
                        raise PlanError(
                            f"{repository}: create the {branch} branch from the "
                            "default branch before applying "
                            f"{INTEGRATION_RULESET_NAME}"
                        ) from None
                    raise
        managed, settings, unmanaged = collect_state(client, repository, names)
        result["unmanaged_rulesets"] = unmanaged
        before = plan_repository(repository, desired_rulesets, managed, settings)
        result["before"] = before
        if not plan_has_changes(before):
            result["status"] = "compliant"
            return result
        if not apply:
            result["status"] = "drift"
            return result
        apply_plan(client, before)
        managed, settings, _ = collect_state(client, repository, names)
        after = plan_repository(repository, desired_rulesets, managed, settings)
        result["after"] = after
        if plan_has_changes(after):
            result["status"] = "error"
            result["error"] = "drift remains after apply"
        else:
            result["status"] = "applied"
    except (GitHubError, PlanError) as exc:
        result["status"] = "error"
        result["error"] = str(exc)
    return result


def load_desired_rulesets(
    client: GitHubClient, templates_ref: str, *, integration: bool = False
) -> list[dict[str, Any]]:
    rulesets = [
        validate_desired_ruleset(
            client.get_file(TEMPLATES_REPOSITORY, BRANCH_RULESET_PATH, templates_ref),
            expected_name=BRANCH_RULESET_NAME,
            expected_target="branch",
        ),
        validate_desired_ruleset(
            client.get_file(TEMPLATES_REPOSITORY, TAG_RULESET_PATH, templates_ref),
            expected_name=TAG_RULESET_NAME,
            expected_target="tag",
        ),
    ]
    if integration:
        rulesets.append(
            validate_desired_ruleset(
                client.get_file(TEMPLATES_REPOSITORY, INTEGRATION_RULESET_PATH, templates_ref),
                expected_name=INTEGRATION_RULESET_NAME,
                expected_target="branch",
            )
        )
    return rulesets


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Plan (default) or apply Catylist ADR-0006 rulesets and merge "
            f"settings. Reads the admin token from ${ADMIN_TOKEN_ENV} and an "
            f"optional source-read token from ${SOURCE_TOKEN_ENV}."
        )
    )
    parser.add_argument("--catylist-ref", required=True,
                        help=f"pinned commit SHA of {CATYLIST_REPOSITORY}")
    parser.add_argument("--templates-ref", required=True,
                        help=f"pinned commit SHA of {TEMPLATES_REPOSITORY}")
    parser.add_argument("--repos", default="",
                        help="optional comma-separated full_name filter")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", dest="apply", action="store_false",
                      help="report drift without changing anything (default)")
    mode.add_argument("--apply", dest="apply", action="store_true",
                      help="create/update rulesets and patch merge settings")
    parser.set_defaults(apply=False)
    parser.add_argument("--output-dir", type=Path,
                        default=Path("build/aems/catylist-rulesets"))
    parser.add_argument("--fitment-config", type=Path, default=DEFAULT_FITMENT_CONFIG,
                        help="repositories that adopted Catylist ADR-0013 (integration-branch ruleset)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        catylist_ref = validate_sha(args.catylist_ref, "catylist_ref")
        templates_ref = validate_sha(args.templates_ref, "templates_ref")
        repos_filter = parse_repos_filter(args.repos)
    except PlanError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    admin_token = os.environ.get(ADMIN_TOKEN_ENV, "").strip()
    if not admin_token:
        print(
            f"error: {ADMIN_TOKEN_ENV} is not set; configure the Actions "
            "secret described in docs/engineering/catylist-default-branch-rulesets.md",
            file=sys.stderr,
        )
        return 2
    source = GitHubClient(os.environ.get(SOURCE_TOKEN_ENV, "").strip() or None)
    admin = GitHubClient(admin_token)

    try:
        inventory = source.get_file(CATYLIST_REPOSITORY, INVENTORY_PATH, catylist_ref)
        selected, skipped = select_repositories(inventory, repos_filter)
        adopted = load_adopted(args.fitment_config)
        desired = load_desired_rulesets(
            source, templates_ref,
            integration=any(r.lower() in adopted for r in selected),
        )
    except (GitHubError, PlanError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    results = [
        process_repository(
            admin, repository, desired_for(repository, desired, adopted), apply=args.apply
        )
        for repository in selected
    ]
    report = build_report(
        mode="apply" if args.apply else "dry-run",
        catylist_ref=catylist_ref,
        templates_ref=templates_ref,
        repos_filter=repos_filter,
        skipped=skipped,
        results=results,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    markdown = render_markdown(report)
    (args.output_dir / "report.md").write_text(markdown, encoding="utf-8")
    print(markdown)
    return 1 if any(r["status"] == "error" for r in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
