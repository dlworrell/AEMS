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

Public-safe output. Every sink (stdout, ``--output``, the job summary and
the issue) gets the same rendering, and that rendering is safe to publish:

* only repositories GitHub reports as public (``private`` is false) are
  named; private repositories and repositories the token cannot read are
  counted, never named, and their findings are withheld;
* GitHub errors are reported by HTTP status only, never by message or URL;
* a repository that could not be checked is "unverified", never "drift".

Issue handling. The audit only ever touches an open issue that carries its
own marker line (``ISSUE_MARKER``) and whose number is not preserved.
Issue #170, the evidence of the first, unsafe version of this audit, is
preserved by default (``--preserve-issue`` adds more); the audit never
edits, comments on or closes a preserved issue.

Exit codes: 0 clean, 1 drift found, 3 no drift but some repositories
unverified, 2 unusable input or GitHub error. Standard library only.
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
ISSUE_TITLE = "Ruleset drift audit"
ISSUE_LABEL = "ruleset-drift"
ISSUE_MARKER = "<!-- aems:ruleset-drift-audit:v2 -->"
PRESERVED_ISSUES = frozenset({170})  # evidence of the unsafe first version; never touched
REQUIRED_RULES = frozenset({"deletion", "non_fast_forward", "required_signatures", "pull_request"})
FORBIDDEN_RULES = frozenset({"required_linear_history"})
MERGE_SETTINGS = {"allow_merge_commit": True, "allow_squash_merge": False, "allow_rebase_merge": False}
INTEGRATION = ("dev-daily", "fitment")


@dataclasses.dataclass
class RepoAudit:
    repository: str
    public: bool = False
    drift: list[str] = dataclasses.field(default_factory=list)
    unverified: list[str] = dataclasses.field(default_factory=list)
    error: str | None = None

    @property
    def verified(self) -> bool:
        return self.error is None


def _status(exc: Exception) -> str:
    """A publishable description of an error: the HTTP status, never the message or URL."""
    if isinstance(exc, GitHubError):
        return f"HTTP {exc.status}" if exc.status else "network error"
    return "unexpected response shape"


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
    except GitHubError as exc:
        result.error = _status(exc)
        return result
    if not isinstance(meta, dict) or meta.get("private") is not False:
        # Private, or visibility unknown: audit it, but publish nothing identifying.
        result.public = False
    else:
        result.public = True
    try:
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
        result.error = _status(exc)
    return result


def load_inventory(gh: Client) -> list[str]:
    text = decode_content(gh.get(f"/repos/{cr.CATYLIST_REPOSITORY}/contents/{cr.INVENTORY_PATH}"))
    if text is None:
        raise ValueError(f"{cr.CATYLIST_REPOSITORY}/{cr.INVENTORY_PATH} could not be read")
    selected, _ = cr.select_repositories(json.loads(text), [])
    return selected


def render(audits: list[RepoAudit]) -> str:
    """The one rendering every sink gets. It names public repositories only."""
    public = [a for a in audits if a.public]
    withheld = [a for a in audits if not a.public]
    drifted = [a for a in public if a.drift]
    failed = [a for a in public if not a.verified]
    lines = [ISSUE_MARKER, "# Ruleset drift audit", "",
             f"{len(audits)} repositories in scope: {len(public)} public, {len(withheld)} withheld. "
             f"{len(drifted)} public with drift; {len(failed)} public not verified. "
             "Read-only (AEMS `scripts/ruleset_drift_audit.py`, Catylist ADR-0006/ADR-0013).", ""]
    if not drifted and not failed:
        lines += ["No drift in the public repositories.", ""]
    for audit in sorted(drifted + failed, key=lambda a: a.repository.lower()):
        lines.append(f"## {audit.repository}")
        lines += [f"- not verified: could not audit ({audit.error})"] if audit.error else []
        lines += [f"- {item}" for item in audit.drift]
        lines.append("")
    if withheld:
        w_drift = sum(1 for a in withheld if a.drift)
        w_failed = sum(1 for a in withheld if not a.verified)
        lines += [f"Withheld: {len(withheld)} repositories are private or not visible to this token, "
                  "so they are not named here. "
                  f"{w_drift} of them with drift; {w_failed} not verified. "
                  "Audit them privately with an authorized token.", ""]
    unverified = sorted({u for a in public for u in a.unverified})
    if unverified:
        lines += ["Not verified with this token: " + "; ".join(unverified) + ".", ""]
    lines += ["To repair drift, dispatch **Apply Catylist Rulesets** as a dry run, review the plan, then apply."]
    return "\n".join(lines).rstrip() + "\n"


def outcome(audits: list[RepoAudit]) -> str:
    if any(a.drift for a in audits):
        return "drift"
    if any(not a.verified for a in audits):
        return "unverified"
    return "clean"


def find_issue(gh: Client, repo: str, preserved: frozenset[int]) -> dict[str, Any] | None:
    """The audit's own open issue: carries ISSUE_MARKER and is not preserved. Title alone never matches."""
    issues = gh.get_all(f"/repos/{repo}/issues?state=open&labels={ISSUE_LABEL}&per_page=100", limit=200)
    for issue in issues:
        if "pull_request" in issue or issue.get("number") in preserved:
            continue
        if (issue.get("body") or "").startswith(ISSUE_MARKER):
            return issue
    return None


def publish(gh: Client, repo: str, body: str, result: str,
            preserved: frozenset[int] = PRESERVED_ISSUES) -> str:
    """Keep one issue open while drift exists; close it once the audit is fully clean.

    ``result`` is ``outcome()``. Unverified repositories never open or close the
    issue: an open one is updated, and nothing else happens.
    """
    issue = find_issue(gh, repo, preserved)
    if result == "drift" and issue is None:
        gh.post(f"/repos/{repo}/issues", {"title": ISSUE_TITLE, "body": body, "labels": [ISSUE_LABEL]})
        return "opened"
    if result in ("drift", "unverified") and issue is not None:
        if (issue.get("body") or "") == body:
            return "unchanged"
        gh.patch(f"/repos/{repo}/issues/{issue['number']}", {"body": body})
        return "updated"
    if result == "clean" and issue is not None:
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
    parser.add_argument("--preserve-issue", type=int, action="append", default=[],
                        help="an issue number the audit must never touch (repeatable; #170 always is)")
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
    except GitHubError as exc:
        print(f"error: GitHub request failed ({_status(exc)})", file=sys.stderr)
        return 2
    except (cr.PlanError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    body = render(audits)
    print(body)
    if args.output:
        args.output.write_text(body, encoding="utf-8")
    result = outcome(audits)
    if not args.dry_run:
        writer = writer or GitHubClient(os.environ.get("ISSUE_TOKEN") or os.environ.get("GITHUB_TOKEN"),
                                        agent="aems-ruleset-audit")
        preserved = PRESERVED_ISSUES | frozenset(args.preserve_issue)
        try:
            print(f"issue {publish(writer, args.issue_repository, body, result, preserved)}")
        except GitHubError as exc:
            print(f"error: issue update failed ({_status(exc)})", file=sys.stderr)
            return 2
    return {"drift": 1, "unverified": 3, "clean": 0}[result]


if __name__ == "__main__":
    sys.exit(main())
