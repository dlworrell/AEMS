#!/usr/bin/env python3
"""Plan or delete merged branches across Catalyst repositories.

The repository inventory is read from ``dlworrell/Catylist`` at a pinned
commit SHA. Every inventory entry with ``default_branch_policy: protected``
is in scope; ``dlworrell/ruleset-sandbox`` is in scope only when named in the
repository filter.

A branch is deleted only if ALL of the following hold:

1. It is not the repository's default branch and is not a protected branch.
2. It is not the head or the base of any open pull request in the repository.
3. Its name does not match a keep pattern (``backup/*``, ``dev-daily`` and
   ``fitment`` always, plus any
   patterns passed with ``--keep``).
4. EITHER (a) a merged pull request has the branch as its head and the
   branch's current tip SHA equals that pull request's ``head.sha``, OR
   (b) the compare API reports that the branch is not ahead of the default
   branch (``ahead_by == 0``).

Everything else is kept and reported with the reason. The default mode is a
dry run that sends no write requests.

Classification is a set of pure functions over plain JSON values so that it
can be tested without network access. All GitHub I/O is isolated in
``GitHubClient`` and ``collect_state``/``process_repository``.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Callable, Protocol
import urllib.error
import urllib.parse
import urllib.request


REPORT_SCHEMA = "aems.branch-cleanup-report.v1"
INVENTORY_SCHEMA = "catylist.repository-inventory.v1"
POLICY_PROTECTED = "protected"
KNOWN_POLICIES = frozenset({"protected", "excluded", "pending-classification"})

CATYLIST_REPOSITORY = "dlworrell/Catylist"
INVENTORY_PATH = "inventory/repositories.json"

# The ruleset sandbox is not a Catalyst repository and is therefore not in the
# inventory. It is the only name the repository filter may select outside the
# inventory.
SANDBOX_REPOSITORY = "dlworrell/ruleset-sandbox"

# Branches matching these patterns are never deleted.
# dev-daily and fitment are long-lived Catylist ADR-0013 branches.
DEFAULT_KEEP_PATTERNS = ("backup/*", "dev-daily", "fitment")

CLEANUP_TOKEN_ENV = "BRANCH_CLEANUP_TOKEN"
SOURCE_TOKEN_ENV = "SOURCE_TOKEN"
API_ROOT = "https://api.github.com"
API_VERSION = "2022-11-28"

SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
FULL_NAME_PATTERN = re.compile(r"^[A-Za-z0-9-]+/[A-Za-z0-9._-]+$")

# Decision reasons. Delete reasons:
REASON_MERGED_PR = "merged-pr"
REASON_CONTAINED = "contained-in-default"
# Keep reasons:
REASON_DEFAULT = "default"
REASON_PROTECTED = "protected"
REASON_OPEN_PR_HEAD = "open-pr-head"
REASON_OPEN_PR_BASE = "open-pr-base"
REASON_KEEP_PATTERN = "keep-pattern"
REASON_COMMITS_AFTER_MERGE = "commits-after-merge"
REASON_CLOSED_UNMERGED = "closed-unmerged-pr"
REASON_UNMERGED_COMMITS = "unmerged-commits"


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


def parse_keep_patterns(value: str | None) -> list[str]:
    """Return the fixed keep patterns plus comma-separated extra patterns."""

    patterns = list(DEFAULT_KEEP_PATTERNS)
    for raw in (value or "").split(","):
        pattern = raw.strip()
        if not pattern:
            continue
        if any(ord(char) < 0x20 for char in pattern):
            raise PlanError(f"invalid keep pattern: {pattern!r}")
        if pattern not in patterns:
            patterns.append(pattern)
    return patterns


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


# ---------------------------------------------------------------------------
# Classification (pure)
# ---------------------------------------------------------------------------


def index_pulls(repository: str, pulls: list[dict[str, Any]]) -> dict[str, Any]:
    """Index pull requests by the branch names they reference.

    Head refs are indexed only when the head repository is ``repository``
    itself, so a fork branch with the same name is not confused with a
    branch of this repository. Base refs of open pull requests always belong
    to this repository.
    """

    key = repository.lower()
    merged: dict[str, list[dict[str, Any]]] = {}
    closed_unmerged: dict[str, list[dict[str, Any]]] = {}
    open_heads: dict[str, list[int]] = {}
    open_bases: dict[str, list[int]] = {}
    for pull in pulls:
        number = pull.get("number")
        state = pull.get("state")
        head = pull.get("head") or {}
        base = pull.get("base") or {}
        head_repo = (head.get("repo") or {}).get("full_name") or ""
        same_repo = head_repo.lower() == key
        head_ref = head.get("ref")
        if state == "open":
            if isinstance(base.get("ref"), str):
                open_bases.setdefault(base["ref"], []).append(number)
            if same_repo and isinstance(head_ref, str):
                open_heads.setdefault(head_ref, []).append(number)
            continue
        if not same_repo or not isinstance(head_ref, str):
            continue
        summary = {"number": number, "head_sha": head.get("sha")}
        if pull.get("merged_at"):
            merged.setdefault(head_ref, []).append(summary)
        else:
            closed_unmerged.setdefault(head_ref, []).append(summary)
    for table in (merged, closed_unmerged):
        for items in table.values():
            items.sort(key=lambda item: item["number"] or 0, reverse=True)
    for table in (open_heads, open_bases):
        for numbers in table.values():
            numbers.sort()
    return {
        "merged": merged,
        "closed_unmerged": closed_unmerged,
        "open_heads": open_heads,
        "open_bases": open_bases,
    }


def matching_keep_pattern(name: str, patterns: list[str]) -> str | None:
    for pattern in patterns:
        if fnmatch.fnmatchcase(name, pattern):
            return pattern
    return None


def _decision(
    branch: dict[str, Any],
    action: str,
    reason: str,
    detail: str,
    **extra: Any,
) -> dict[str, Any]:
    result = {
        "branch": branch["name"],
        "sha": (branch.get("commit") or {}).get("sha"),
        "action": action,
        "reason": reason,
        "detail": detail,
    }
    result.update(extra)
    return result


def _numbers(numbers: list[int]) -> str:
    return ", ".join(f"#{number}" for number in numbers)


def pre_classify(
    branch: dict[str, Any],
    default_branch: str,
    pulls_index: dict[str, Any],
    keep_patterns: list[str],
) -> dict[str, Any]:
    """Classify a branch without the compare API.

    Returns a final decision (``action`` is ``delete`` or ``keep``) or a
    pending decision (``action`` is ``compare``) that ``finish_classify``
    resolves from the compare API's ``ahead_by``.
    """

    name = branch["name"]
    tip = (branch.get("commit") or {}).get("sha")
    if name == default_branch:
        return _decision(branch, "keep", REASON_DEFAULT, "default branch")
    if branch.get("protected") is not False:
        # Anything other than an explicit ``false`` is treated as protected.
        return _decision(branch, "keep", REASON_PROTECTED, "protected branch")
    if name in pulls_index["open_heads"]:
        numbers = pulls_index["open_heads"][name]
        return _decision(
            branch, "keep", REASON_OPEN_PR_HEAD,
            f"head of open PR {_numbers(numbers)}", pulls=numbers,
        )
    if name in pulls_index["open_bases"]:
        numbers = pulls_index["open_bases"][name]
        return _decision(
            branch, "keep", REASON_OPEN_PR_BASE,
            f"base of open PR {_numbers(numbers)}", pulls=numbers,
        )
    pattern = matching_keep_pattern(name, keep_patterns)
    if pattern is not None:
        return _decision(
            branch, "keep", REASON_KEEP_PATTERN,
            f"matches keep pattern `{pattern}`", pattern=pattern,
        )
    if not isinstance(tip, str) or not SHA_PATTERN.fullmatch(tip):
        raise PlanError(f"branch {name!r} has no valid tip SHA")
    merged = pulls_index["merged"].get(name, [])
    for pull in merged:
        if pull["head_sha"] == tip:
            return _decision(
                branch, "delete", REASON_MERGED_PR,
                f"merged PR #{pull['number']}", pull=pull["number"],
            )
    return _decision(branch, "compare", "", "")


def finish_classify(
    pending: dict[str, Any],
    pulls_index: dict[str, Any],
    ahead_by: int,
) -> dict[str, Any]:
    """Resolve a pending decision from the compare API's ``ahead_by``."""

    name = pending["branch"]
    branch = {"name": name, "commit": {"sha": pending["sha"]}}
    if not isinstance(ahead_by, int) or isinstance(ahead_by, bool) or ahead_by < 0:
        raise PlanError(f"branch {name!r}: invalid ahead_by {ahead_by!r}")
    if ahead_by == 0:
        return _decision(
            branch, "delete", REASON_CONTAINED,
            "contained in default branch", ahead_by=0,
        )
    merged = pulls_index["merged"].get(name, [])
    closed = pulls_index["closed_unmerged"].get(name, [])
    if merged:
        return _decision(
            branch, "keep", REASON_COMMITS_AFTER_MERGE,
            f"{ahead_by} commit(s) not in default; tip differs from merged "
            f"PR #{merged[0]['number']}",
            ahead_by=ahead_by, pull=merged[0]["number"],
        )
    if closed:
        return _decision(
            branch, "keep", REASON_CLOSED_UNMERGED,
            f"closed-unmerged PR #{closed[0]['number']}; {ahead_by} "
            "commit(s) not in default",
            ahead_by=ahead_by, pull=closed[0]["number"],
        )
    return _decision(
        branch, "keep", REASON_UNMERGED_COMMITS,
        f"{ahead_by} commit(s) not in default; no pull request",
        ahead_by=ahead_by,
    )


def plan_repository(
    repository: str,
    default_branch: str,
    branches: list[dict[str, Any]],
    pulls: list[dict[str, Any]],
    keep_patterns: list[str],
    ahead_by: Callable[[str], int],
) -> list[dict[str, Any]]:
    """Return one decision per branch, sorted by branch name.

    ``ahead_by(tip_sha)`` is called only for branches that rule 4a does not
    decide; it returns how many commits the tip is ahead of the default
    branch.
    """

    if not isinstance(default_branch, str) or not default_branch:
        raise PlanError(f"{repository}: default branch is unknown")
    pulls_index = index_pulls(repository, pulls)
    decisions = []
    for branch in sorted(branches, key=lambda item: item["name"]):
        decision = pre_classify(branch, default_branch, pulls_index, keep_patterns)
        if decision["action"] == "compare":
            decision = finish_classify(
                decision, pulls_index, ahead_by(decision["sha"])
            )
        decisions.append(decision)
    return decisions


# ---------------------------------------------------------------------------
# Reporting (pure)
# ---------------------------------------------------------------------------


def build_report(
    *,
    mode: str,
    catylist_ref: str,
    repos_filter: list[str],
    keep_patterns: list[str],
    skipped: list[dict[str, str]],
    results: list[dict[str, Any]],
) -> dict[str, Any]:
    statuses = [result["status"] for result in results]
    totals = {"delete": 0, "keep": 0, "deleted": 0, "already_gone": 0}
    for result in results:
        totals["delete"] += len(result.get("delete", []))
        totals["keep"] += len(result.get("keep", []))
        for outcome in result.get("deletions", []):
            if outcome["result"] == "deleted":
                totals["deleted"] += 1
            elif outcome["result"] == "already-gone":
                totals["already_gone"] += 1
    return {
        "schema": REPORT_SCHEMA,
        "mode": mode,
        "sources": {
            "inventory": {
                "repository": CATYLIST_REPOSITORY,
                "path": INVENTORY_PATH,
                "ref": catylist_ref,
            }
        },
        "repos_filter": repos_filter,
        "keep_patterns": keep_patterns,
        "skipped": skipped,
        "summary": {
            "repositories": {
                status: statuses.count(status)
                for status in sorted(set(statuses))
            },
            "branches": totals,
        },
        "repositories": results,
    }


def _cell(text: Any) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def render_markdown(report: dict[str, Any]) -> str:
    dry_run = report["mode"] == "dry-run"
    inventory = report["sources"]["inventory"]
    totals = report["summary"]["branches"]
    lines = [
        "# Merged-branch cleanup report",
        "",
        f"- Mode: **{report['mode']}**",
        (
            f"- Inventory: `{inventory['repository']}` `{inventory['path']}` "
            f"@ `{inventory['ref']}`"
        ),
        (
            "- Repository filter: "
            + (", ".join(f"`{name}`" for name in report["repos_filter"])
               or "none (all protected entries)")
        ),
        "- Keep patterns: "
        + ", ".join(f"`{pattern}`" for pattern in report["keep_patterns"]),
        "- Repositories: "
        + (
            ", ".join(
                f"{key}: {value}"
                for key, value in report["summary"]["repositories"].items()
            )
            or "none selected"
        ),
        (
            f"- Branches: {totals['delete']} "
            + ("would be deleted" if dry_run else "selected for deletion")
            + f", {totals['keep']} kept"
            + (
                ""
                if dry_run
                else f", {totals['deleted']} deleted, "
                f"{totals['already_gone']} already gone"
            )
        ),
        "",
    ]
    for entry in report["repositories"]:
        lines.append(f"## `{entry['repository']}` — {entry['status']}")
        lines.append("")
        if entry.get("default_branch"):
            lines.append(f"Default branch: `{entry['default_branch']}`")
            lines.append("")
        if entry.get("error"):
            lines.append(f"**Error:** {_cell(entry['error'])}")
            lines.append("")
        outcomes = {item["branch"]: item for item in entry.get("deletions", [])}
        if entry.get("delete"):
            heading = "Would delete" if dry_run else "Delete"
            lines += [
                f"### {heading} ({len(entry['delete'])})",
                "",
                "| Branch | Tip | Reason | Result |",
                "|---|---|---|---|",
            ]
            for item in entry["delete"]:
                outcome = outcomes.get(item["branch"])
                if dry_run:
                    result_text = "not deleted (dry run)"
                elif outcome is None:
                    result_text = "not attempted"
                else:
                    result_text = outcome["result"]
                    if outcome.get("error"):
                        result_text += f": {outcome['error']}"
                lines.append(
                    f"| `{_cell(item['branch'])}` | `{(item['sha'] or '')[:12]}` "
                    f"| {_cell(item['detail'])} | {_cell(result_text)} |"
                )
            lines.append("")
        if entry.get("keep"):
            lines += [
                f"### Kept ({len(entry['keep'])})",
                "",
                "| Branch | Reason |",
                "|---|---|",
            ]
            for item in entry["keep"]:
                lines.append(
                    f"| `{_cell(item['branch'])}` | {_cell(item['detail'])} |"
                )
            lines.append("")
        if entry.get("remaining_branches") is not None:
            lines.append(
                f"Branches after cleanup ({len(entry['remaining_branches'])}): "
                + (
                    ", ".join(
                        f"`{_cell(name)}`" for name in entry["remaining_branches"]
                    )
                    or "none"
                )
            )
            lines.append("")
    if report["skipped"]:
        lines += ["## Skipped by policy", ""]
        for item in report["skipped"]:
            lines.append(f"- `{item['repository']}`: {item['reason']}")
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# GitHub I/O
# ---------------------------------------------------------------------------


class GitHubError(RuntimeError):
    def __init__(self, status: int, message: str, detail: str = "") -> None:
        super().__init__(f"HTTP {status}: {message}")
        self.status = status
        self.detail = detail


class Client(Protocol):
    def request(self, method: str, path: str, body: Any | None = None) -> Any: ...

    def list_all(self, path: str) -> list[dict[str, Any]]: ...


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
            "User-Agent": "aems-branch-cleanup",
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
            detail = str(exc.reason)
            try:
                payload = json.loads(exc.read().decode("utf-8"))
                detail = str(payload.get("message", detail))
            except (ValueError, UnicodeDecodeError, AttributeError):
                pass
            detail = self._redact(detail)
            raise GitHubError(
                exc.code, self._redact(f"{method} {url}: {detail}"), detail
            ) from None
        except urllib.error.URLError as exc:
            raise GitHubError(
                0, self._redact(f"{method} {url}: {exc.reason}")
            ) from None

    def request(self, method: str, path: str, body: Any | None = None) -> Any:
        raw, _ = self._open(method, API_ROOT + path, body)
        return json.loads(raw.decode("utf-8")) if raw else None

    def list_all(self, path: str) -> list[dict[str, Any]]:
        """GET a list endpoint and follow ``Link: rel="next"`` pages.

        ``_open`` refuses any next link outside https://api.github.com.
        """

        url: str | None = API_ROOT + path
        results: list[dict[str, Any]] = []
        while url:
            raw, headers = self._open("GET", url, None)
            page = json.loads(raw.decode("utf-8"))
            if not isinstance(page, list):
                raise GitHubError(0, f"GET {url}: expected a JSON list")
            results.extend(page)
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


def _quote(name: str) -> str:
    return urllib.parse.quote(name, safe="")


def collect_state(
    client: Client, repository: str
) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    """Read the default branch, all branches and all pull requests."""

    repo = client.request("GET", f"/repos/{repository}")
    if repo.get("archived"):
        raise PlanError(f"{repository} is archived")
    default_branch = repo.get("default_branch")
    branches = client.list_all(f"/repos/{repository}/branches?per_page=100")
    pulls = client.list_all(f"/repos/{repository}/pulls?state=all&per_page=100")
    return default_branch, branches, pulls


def make_ahead_by(
    client: Client, repository: str, default_branch: str
) -> Callable[[str], int]:
    def ahead_by(tip: str) -> int:
        # The head is the tip SHA that was classified, so the answer cannot
        # describe a newer commit pushed to the branch during the run.
        result = client.request(
            "GET",
            f"/repos/{repository}/compare/{_quote(default_branch)}...{tip}",
        )
        return result.get("ahead_by") if isinstance(result, dict) else None

    return ahead_by


def _is_already_gone(exc: GitHubError) -> bool:
    if exc.status == 404:
        return True
    return exc.status == 422 and "reference does not exist" in exc.detail.lower()


def delete_branch(client: Client, repository: str, decision: dict[str, Any]) -> dict[str, Any]:
    """Delete one branch after confirming its tip has not moved."""

    name = decision["branch"]
    ref_path = f"/repos/{repository}/git/refs/heads/{_quote(name)}"
    outcome: dict[str, Any] = {"branch": name, "sha": decision["sha"]}
    try:
        current = client.request(
            "GET", f"/repos/{repository}/git/ref/heads/{_quote(name)}"
        )
        current_sha = ((current or {}).get("object") or {}).get("sha")
        if current_sha != decision["sha"]:
            outcome["result"] = "skipped-tip-changed"
            outcome["error"] = f"tip is now {current_sha}"
            return outcome
        client.request("DELETE", ref_path)
        outcome["result"] = "deleted"
    except GitHubError as exc:
        if _is_already_gone(exc):
            outcome["result"] = "already-gone"
        else:
            outcome["result"] = "failed"
            outcome["error"] = str(exc)
    return outcome


def process_repository(
    client: Client,
    repository: str,
    keep_patterns: list[str],
    *,
    apply: bool,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "repository": repository,
        "status": "error",
        "error": None,
        "default_branch": None,
        "delete": [],
        "keep": [],
        "deletions": [],
        "remaining_branches": None,
    }
    try:
        default_branch, branches, pulls = collect_state(client, repository)
        result["default_branch"] = default_branch
        decisions = plan_repository(
            repository,
            default_branch,
            branches,
            pulls,
            keep_patterns,
            make_ahead_by(client, repository, default_branch),
        )
        result["delete"] = [d for d in decisions if d["action"] == "delete"]
        result["keep"] = [d for d in decisions if d["action"] == "keep"]
        if not apply:
            result["status"] = "planned" if result["delete"] else "nothing-to-delete"
            return result
        if not result["delete"]:
            result["status"] = "nothing-to-delete"
            return result
        result["deletions"] = [
            delete_branch(client, repository, decision)
            for decision in result["delete"]
        ]
        remaining = sorted(
            item["name"]
            for item in client.list_all(f"/repos/{repository}/branches?per_page=100")
        )
        result["remaining_branches"] = remaining
        problems = [
            f"{item['branch']}: {item['result']}"
            for item in result["deletions"]
            if item["result"] not in ("deleted", "already-gone")
        ]
        still_present = sorted(
            item["branch"]
            for item in result["deletions"]
            if item["result"] in ("deleted", "already-gone")
            and item["branch"] in remaining
        )
        problems += [f"{name}: still present after deletion" for name in still_present]
        if problems:
            result["error"] = "; ".join(problems)
        else:
            result["status"] = "cleaned"
    except (GitHubError, PlanError) as exc:
        result["error"] = str(exc)
    return result


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Plan (default) or delete merged branches in Catalyst "
            f"repositories. Reads the cleanup token from ${CLEANUP_TOKEN_ENV} "
            f"and an optional source-read token from ${SOURCE_TOKEN_ENV}."
        )
    )
    parser.add_argument("--catylist-ref", required=True,
                        help=f"pinned commit SHA of {CATYLIST_REPOSITORY}")
    parser.add_argument("--repos", default="",
                        help="optional comma-separated full_name filter")
    parser.add_argument("--keep", default="",
                        help="optional comma-separated fnmatch patterns of "
                        "branches to keep, in addition to backup/*, dev-daily and fitment")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", dest="apply", action="store_false",
                      help="report without deleting anything (default)")
    mode.add_argument("--apply", dest="apply", action="store_true",
                      help="delete the branches the rule selects")
    parser.set_defaults(apply=False)
    parser.add_argument("--output-dir", type=Path,
                        default=Path("build/aems/branch-cleanup"))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        catylist_ref = validate_sha(args.catylist_ref, "catylist_ref")
        repos_filter = parse_repos_filter(args.repos)
        keep_patterns = parse_keep_patterns(args.keep)
    except PlanError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    token = os.environ.get(CLEANUP_TOKEN_ENV, "").strip()
    if not token:
        print(
            f"error: {CLEANUP_TOKEN_ENV} is not set; configure the environment "
            "secret described in docs/engineering/merged-branch-cleanup.md",
            file=sys.stderr,
        )
        return 2
    source = GitHubClient(os.environ.get(SOURCE_TOKEN_ENV, "").strip() or None)
    cleanup = GitHubClient(token)

    try:
        inventory = source.get_file(CATYLIST_REPOSITORY, INVENTORY_PATH, catylist_ref)
        selected, skipped = select_repositories(inventory, repos_filter)
    except (GitHubError, PlanError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    results = [
        process_repository(cleanup, repository, keep_patterns, apply=args.apply)
        for repository in selected
    ]
    report = build_report(
        mode="apply" if args.apply else "dry-run",
        catylist_ref=catylist_ref,
        repos_filter=repos_filter,
        keep_patterns=keep_patterns,
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
