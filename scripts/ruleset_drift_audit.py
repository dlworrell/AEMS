#!/usr/bin/env python3
"""Read-only drift audit of the Catylist ADR-0006/ADR-0013 repository protections.

The ruleset workflow (``apply-catylist-rulesets.yml``) applies protections only
when the owner dispatches it and approves the ``ruleset-admin`` environment.
This audit runs on a schedule with an ordinary read token and reports anything
that has drifted since. It never writes repository settings.

For every ``protected`` entry of the Catylist inventory it checks:

* the rulesets ``protect-default-branch`` and ``protect-release-tags`` exist
  and are active;
* the default branch's effective rules include deletion, non_fast_forward,
  required_signatures and a pull_request rule allowing merge commits only, and
  never required_linear_history (it conflicts with merge commits);
* merge settings: merge commits on, squash and rebase off. Fields the token
  cannot see are reported as unverified, not as drift.

For every repository in ``config/fitment.json`` it also checks the
``protect-integration-branches`` ruleset and the same effective rules on
``dev-daily`` and ``fitment``, and for every branch it compares the required
status check contexts with ``config/required-checks.json``.

Exit codes: 0 no drift, 1 drift found, 2 unusable input or GitHub error.
Standard library only.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import os
from pathlib import Path
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ring0_sweep import Client, GitHubClient, GitHubError, decode_content  # noqa: E402
import catylist_rulesets as cr  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FITMENT = ROOT / "config" / "fitment.json"
DEFAULT_REQUIRED = ROOT / "config" / "required-checks.json"
ISSUE_TITLE = "Ruleset drift"
ISSUE_LABEL = "ruleset-drift"
REQUIRED_RULES = frozenset({"deletion", "non_fast_forward", "required_signatures", "pull_request"})
FORBIDDEN_RULES = frozenset({"required_linear_history"})
MERGE_SETTINGS = {"allow_merge_commit": True, "allow_squash_merge": False, "allow_rebase_merge": False}
INTEGRATION = ("dev-daily", "fitment")


@dataclasses.dataclass
class RepoAudit:
    repository: str
    drift: list[str] = dataclasses.field(default_factory=list)
    unverified: list[str] = dataclasses.field(default_factory=list)
    error: str | None = None


def _branch_rules(gh: Client, repo: str, branch: str) -> list[dict[str, Any]]:
    return list(gh.get_all(f"/repos/{repo}/rules/branches/{branch}?per_page=100", limit=200))


def check_branch(gh: Client, repo: str, branch: str, expected_checks: list[str] | None) -> list[str]:
    """Drift on one branch's effective rules. ``expected_checks`` None means no required-checks entry."""
    try:
        rules = _branch_rules(gh, repo, branch)
    except GitHubError as exc:
        if exc.status == 404:
            return [f"{branch}: branch missing"]
        raise
    drift = []
    types = {r.get("type") for r in rules}
    for missing in sorted(REQUIRED_RULES - types):
        drift.append(f"{branch}: no {missing} rule")
    for bad in sorted(FORBIDDEN_RULES & types):
        drift.append(f"{branch}: {bad} is set (conflicts with merge commits)")
    for rule in rules:
        if rule.get("type") == "pull_request":
            methods = (rule.get("parameters") or {}).get("allowed_merge_methods")
            if methods is not None and sorted(methods) != ["merge"]:
                drift.append(f"{branch}: pull_request allows {', '.join(sorted(methods))}, not merge only")
    actual = sorted({c.get("context", "") for r in rules if r.get("type") == "required_status_checks"
                     for c in (r.get("parameters") or {}).get("required_status_checks", [])})
    wanted = sorted(set(expected_checks or []))
    if actual != wanted:
        extra, missing = sorted(set(actual) - set(wanted)), sorted(set(wanted) - set(actual))
        parts = ([f"missing {', '.join(missing)}"] if missing else []) + ([f"unexpected {', '.join(extra)}"]
                                                                            if extra else [])
        drift.append(f"{branch}: required checks differ from config/required-checks.json ({'; '.join(parts)})")
    return drift


def audit_repository(gh: Client, repo: str, *, adopted: bool,
                     required: dict[str, list[dict[str, Any]]]) -> RepoAudit:
    result = RepoAudit(repo)
    try:
        meta = gh.get(f"/repos/{repo}")
        default = meta["default_branch"]
        for key, want in MERGE_SETTINGS.items():
            if key not in meta:
                result.unverified.append(f"{key} is not visible to this token")
            elif meta[key] is not want:
                result.drift.append(f"merge settings: {key} is {str(meta[key]).lower()}, expected {str(want).lower()}")
        rulesets = {r.get("name"): r for r in gh.get_all(f"/repos/{repo}/rulesets?per_page=100", limit=200)}
        wanted = [cr.BRANCH_RULESET_NAME, cr.TAG_RULESET_NAME] + ([cr.INTEGRATION_RULESET_NAME] if adopted else [])
        for name in wanted:
            if name not in rulesets:
                result.drift.append(f"ruleset {name} is missing")
            elif rulesets[name].get("enforcement") != "active":
                result.drift.append(f"ruleset {name} is {rulesets[name].get('enforcement')}, not active")
        checks = {ruleset["name"].removeprefix(cr.REQUIRED_CHECKS_PREFIX):
                  [c["context"] for c in ruleset["rules"][0]["parameters"]["required_status_checks"]]
                  for ruleset in required.get(repo.lower(), [])}
        result.drift += check_branch(gh, repo, default, checks.get("main"))
        if adopted:
            for branch in INTEGRATION:
                result.drift += check_branch(gh, repo, branch, checks.get(branch))
    except (GitHubError, KeyError, TypeError) as exc:
        result.error = str(exc)[:200]
    return result


def load_inventory(gh: Client) -> list[str]:
    text = decode_content(gh.get(f"/repos/{cr.CATYLIST_REPOSITORY}/contents/{cr.INVENTORY_PATH}"))
    if text is None:
        raise ValueError(f"{cr.CATYLIST_REPOSITORY}/{cr.INVENTORY_PATH} could not be read")
    selected, _ = cr.select_repositories(json.loads(text), [])
    return selected


def render(audits: list[RepoAudit]) -> str:
    drifted = [a for a in audits if a.drift or a.error]
    lines = ["# Ruleset drift audit", "",
             f"{len(audits)} repositories checked; {len(drifted)} with drift or errors. "
             "Read-only (AEMS `scripts/ruleset_drift_audit.py`, Catylist ADR-0006/ADR-0013).", ""]
    if not drifted:
        lines += ["No drift: every repository matches the protections.", ""]
    for audit in sorted(drifted, key=lambda a: a.repository.lower()):
        lines.append(f"## {audit.repository}")
        lines += [f"- ⚠️ could not audit: {audit.error}"] if audit.error else []
        lines += [f"- {item}" for item in audit.drift]
        lines.append("")
    unverified = sorted({u for a in audits for u in a.unverified})
    if unverified:
        lines += ["Not verified with this token: " + "; ".join(unverified) + ".", ""]
    lines += ["To repair drift, dispatch **Apply Catylist Rulesets** as a dry run, review the plan, then apply."]
    return "\n".join(lines).rstrip() + "\n"


def publish(gh: Client, repo: str, body: str, drift: bool) -> str:
    """Keep one issue open while drift exists; close it, with a note, once the audit is clean."""
    issues = gh.get_all(f"/repos/{repo}/issues?state=open&labels={ISSUE_LABEL}&per_page=10", limit=10)
    issue = next((i for i in issues if i.get("title") == ISSUE_TITLE and "pull_request" not in i), None)
    if drift and issue is None:
        gh.post(f"/repos/{repo}/issues", {"title": ISSUE_TITLE, "body": body, "labels": [ISSUE_LABEL]})
        return "opened"
    if drift:
        if (issue.get("body") or "") == body:
            return "unchanged"
        gh.patch(f"/repos/{repo}/issues/{issue['number']}", {"body": body})
        return "updated"
    if issue is not None:
        gh.post(f"/repos/{repo}/issues/{issue['number']}/comments", {"body": "The audit is clean again; closing."})
        gh.patch(f"/repos/{repo}/issues/{issue['number']}", {"state": "closed", "state_reason": "completed"})
        return "closed"
    return "clean"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fitment-config", type=Path, default=DEFAULT_FITMENT)
    parser.add_argument("--required-checks", type=Path, default=DEFAULT_REQUIRED)
    parser.add_argument("--repos", default="", help="optional comma-separated filter")
    parser.add_argument("--issue-repository", default="dlworrell/AEMS")
    parser.add_argument("--dry-run", action="store_true", help="print the report; open, update or close no issue")
    parser.add_argument("--output", type=Path, help="also write the report here")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None, *, reader: Client | None = None, writer: Client | None = None) -> int:
    args = parse_args(argv)
    try:
        reader = reader or GitHubClient(os.environ.get("AUDIT_TOKEN") or os.environ.get("GITHUB_TOKEN"),
                                        agent="aems-ruleset-audit")
        adopted = cr.load_adopted(args.fitment_config)
        required = cr.load_required_checks(args.required_checks)
        repos = load_inventory(reader)
        wanted = {r.strip().lower() for r in args.repos.split(",") if r.strip()}
        if wanted:
            repos = [r for r in repos if r.lower() in wanted]
        audits = [audit_repository(reader, repo, adopted=repo.lower() in adopted, required=required)
                  for repo in repos]
    except (cr.PlanError, GitHubError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    body = render(audits)
    print(body)
    if args.output:
        args.output.write_text(body, encoding="utf-8")
    drift = any(a.drift or a.error for a in audits)
    if not args.dry_run:
        writer = writer or GitHubClient(os.environ.get("ISSUE_TOKEN") or os.environ.get("GITHUB_TOKEN"),
                                        agent="aems-ruleset-audit")
        try:
            print(f"issue {publish(writer, args.issue_repository, body, drift)}")
        except GitHubError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
    return 1 if drift else 0


if __name__ == "__main__":
    sys.exit(main())
