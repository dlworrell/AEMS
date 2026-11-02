#!/usr/bin/env python3
"""Read-only drift audit of the Catylist ADR-0006/ADR-0013 repository protections.

The ruleset workflow (``apply-catylist-rulesets.yml``) applies protections only
when the owner dispatches it and approves the ``ruleset-admin`` environment.
This audit runs with an ordinary read token and reports anything that has
drifted since. It never writes repository settings.

For every ``protected`` entry of the Catylist inventory that GitHub reports as
public it checks:

* the rulesets ``protect-default-branch`` and ``protect-release-tags`` exist
  and are active;
* the default branch's effective rules include deletion, non_fast_forward,
  required_signatures and a pull_request rule allowing merge commits only, and
  never required_linear_history (it conflicts with merge commits);
* merge settings: merge commits on, squash and rebase off.

For every repository in ``config/fitment.json`` it also checks the
``protect-integration-branches`` ruleset and the same effective rules on
``dev-daily`` and ``fitment``. On every branch it compares the required status
checks with ``config/required-checks.json`` by context and by the App
(integration ID) that must report each one.

Public scope. The report is published, so the audit covers public
repositories only. A repository GitHub reports as private, or that answers 404
to this token, is excluded: it is counted, never named, no request beyond the
visibility lookup is made for it, and it cannot change the public report,
outcome or issue. Private repositories need a separate, private audit.

Public-safe output. Every sink (stdout, stderr, ``--output``,
``--result-json``, the job summary and the issue) is safe to publish. Errors
are reported by kind or HTTP status only, never by message, URL or input text.

Verification. Drift is a definite finding. Anything the audit could not
establish (a merge setting the token cannot see, an unreadable branch-rules
response, a repository whose visibility could not be read) is "unverified":
never "drift" and never "clean". An unverified run never closes the issue.

Issue handling. The audit only ever touches an open issue that starts with its
own marker line (``ISSUE_MARKER``) and whose number is not preserved. Issue
#170, the evidence of the first, unsafe version of this audit, is always
preserved (``--preserve-issue`` adds more). The audit never edits, comments on
or closes a preserved issue.

Outcome, also written to ``--result-json``: clean (exit 0), drift (exit 1),
unverified (exit 3), error (exit 2: unusable input, a GitHub error, a failed
report write or a failed issue update). The result file is removed at start and
written only once the outcome is terminal, so it never holds a stale outcome:
any failure leaves ``{"outcome": "error"}``, or no file at all if the file
itself cannot be written. A missing result file means error. Standard library
only.
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
RESULT_SCHEMA = "aems.ruleset-drift-result.v1"
EXIT_CODES = {"clean": 0, "drift": 1, "error": 2, "unverified": 3}
REQUIRED_RULES = frozenset({"deletion", "non_fast_forward", "required_signatures", "pull_request"})
FORBIDDEN_RULES = frozenset({"required_linear_history"})
MERGE_SETTINGS = {"allow_merge_commit": True, "allow_squash_merge": False, "allow_rebase_merge": False}
INTEGRATION = ("dev-daily", "fitment")

PUBLIC, EXCLUDED, UNKNOWN = "public", "excluded", "unknown"


@dataclasses.dataclass
class RepoAudit:
    repository: str
    visibility: str = UNKNOWN  # PUBLIC, EXCLUDED (private or 404) or UNKNOWN
    drift: list[str] = dataclasses.field(default_factory=list)
    unverified: list[str] = dataclasses.field(default_factory=list)

    @property
    def verified(self) -> bool:
        return self.visibility != UNKNOWN and not self.unverified


def _status(exc: BaseException) -> str:
    """A publishable description of an error: its HTTP status or kind, never its message or URL."""
    if isinstance(exc, GitHubError):
        return f"HTTP {exc.status}" if exc.status else "network error"
    return "unexpected response shape"


def _check_pairs(checks: list[dict[str, Any]]) -> set[tuple[str, int | None]]:
    """Required checks as (context, integration ID) pairs. A missing ID stays None, so it never matches an ID."""
    pairs = set()
    for check in checks:
        app = check.get("integration_id")
        pairs.add((str(check.get("context", "")), app if isinstance(app, int) and not isinstance(app, bool)
                   else None))
    return pairs


def _show(pairs: set[tuple[str, int | None]]) -> str:
    return ", ".join(f"{context} (app {app if app is not None else 'any'})" for context, app in sorted(
        pairs, key=lambda p: (p[0], p[1] or 0)))


def check_branch(gh: Client, repo: str, branch: str,
                 expected: set[tuple[str, int | None]]) -> tuple[list[str], list[str]]:
    """(drift, unverified) for one branch's effective rules. ``expected`` holds (context, App ID) pairs."""
    try:
        rules = list(gh.get_all(f"/repos/{repo}/rules/branches/{branch}?per_page=100", limit=200))
    except GitHubError as exc:
        # A 404 alone does not prove the branch or its protection is absent.
        return [], [f"{branch}: effective rules not readable ({_status(exc)})"]
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
    actual = _check_pairs([c for r in rules if r.get("type") == "required_status_checks"
                           for c in (r.get("parameters") or {}).get("required_status_checks", [])])
    if actual != expected:
        missing, extra = expected - actual, actual - expected
        parts = ([f"missing {_show(missing)}"] if missing else []) + ([f"unexpected {_show(extra)}"]
                                                                      if extra else [])
        drift.append(f"{branch}: required checks differ from config/required-checks.json ({'; '.join(parts)})")
    return drift, []


def audit_repository(gh: Client, repo: str, *, adopted: bool,
                     required: dict[str, list[dict[str, Any]]]) -> RepoAudit:
    result = RepoAudit(repo)
    try:
        meta = gh.get(f"/repos/{repo}")
    except GitHubError as exc:
        if exc.status == 404:
            result.visibility = EXCLUDED  # not visible to this token: private, or gone
        else:
            result.unverified.append(f"visibility not readable ({_status(exc)})")
        return result
    if not isinstance(meta, dict) or not isinstance(meta.get("private"), bool):
        result.unverified.append("visibility not reported")
        return result
    if meta["private"]:
        result.visibility = EXCLUDED
        return result  # out of scope: no further requests, no findings
    result.visibility = PUBLIC
    try:
        default = meta["default_branch"]
        for key, want in MERGE_SETTINGS.items():
            if key not in meta:
                result.unverified.append(f"merge settings: {key} is not visible to this token")
            elif meta[key] is not want:
                result.drift.append(f"merge settings: {key} is {str(meta[key]).lower()}, expected {str(want).lower()}")
        rulesets = {r.get("name"): r for r in gh.get_all(f"/repos/{repo}/rulesets?per_page=100", limit=200)}
        wanted = [cr.BRANCH_RULESET_NAME, cr.TAG_RULESET_NAME] + ([cr.INTEGRATION_RULESET_NAME] if adopted else [])
        for name in wanted:
            if name not in rulesets:
                result.drift.append(f"ruleset {name} is missing")
            elif rulesets[name].get("enforcement") != "active":
                result.drift.append(f"ruleset {name} is {rulesets[name].get('enforcement')}, not active")
        expected = {ruleset["name"].removeprefix(cr.REQUIRED_CHECKS_PREFIX):
                    _check_pairs(ruleset["rules"][0]["parameters"]["required_status_checks"])
                    for ruleset in required.get(repo.lower(), [])}
        for branch in [default] + (list(INTEGRATION) if adopted else []):
            key = "main" if branch == default else branch
            drift, unverified = check_branch(gh, repo, branch, expected.get(key, set()))
            result.drift += drift
            result.unverified += unverified
    except (GitHubError, KeyError, TypeError, AttributeError) as exc:
        result.unverified.append(f"could not audit ({_status(exc)})")
    return result


def load_inventory(gh: Client) -> list[str]:
    text = decode_content(gh.get(f"/repos/{cr.CATYLIST_REPOSITORY}/contents/{cr.INVENTORY_PATH}"))
    if text is None:
        raise ValueError("inventory could not be read")
    selected, _ = cr.select_repositories(json.loads(text), [])
    return selected


def outcome(audits: list[RepoAudit]) -> str:
    """From public and unknown-visibility repositories only; excluded ones never count."""
    in_scope = [a for a in audits if a.visibility != EXCLUDED]
    if any(a.drift for a in in_scope):
        return "drift"
    if any(not a.verified for a in in_scope):
        return "unverified"
    return "clean"


def summary(audits: list[RepoAudit]) -> dict[str, Any]:
    """The machine-readable result: counts and outcome, no repository names."""
    public = [a for a in audits if a.visibility == PUBLIC]
    return {"schema": RESULT_SCHEMA, "outcome": outcome(audits),
            "repositories": len(audits),
            "public": len(public),
            "public_drift": sum(1 for a in public if a.drift),
            "public_unverified": sum(1 for a in public if not a.verified),
            "excluded": sum(1 for a in audits if a.visibility == EXCLUDED),
            "visibility_unknown": sum(1 for a in audits if a.visibility == UNKNOWN)}


def render(audits: list[RepoAudit]) -> str:
    """The one rendering every sink gets. It names public repositories only."""
    counts = summary(audits)
    public = [a for a in audits if a.visibility == PUBLIC]
    listed = sorted((a for a in public if a.drift or not a.verified), key=lambda a: a.repository.lower())
    lines = [ISSUE_MARKER, "# Ruleset drift audit", "",
             f"**Outcome: {counts['outcome']}.** {counts['repositories']} protected repositories in the "
             f"inventory: {counts['public']} public audited ({counts['public_drift']} with drift, "
             f"{counts['public_unverified']} not fully verified); {counts['excluded']} excluded as not public; "
             f"{counts['visibility_unknown']} with unknown visibility. "
             "Read-only (AEMS `scripts/ruleset_drift_audit.py`, Catylist ADR-0006/ADR-0013).", ""]
    if counts["outcome"] == "clean":
        lines += ["No drift in the public repositories, and every check was verified.", ""]
    for audit in listed:
        lines.append(f"## {audit.repository}")
        lines += [f"- {item}" for item in audit.drift]
        lines += [f"- not verified: {item}" for item in audit.unverified]
        lines.append("")
    if counts["excluded"]:
        lines += [f"Excluded: {counts['excluded']} repositories are private or not visible to this token. "
                  "They are not named or audited here; audit them privately.", ""]
    if counts["visibility_unknown"]:
        lines += [f"Unknown visibility: {counts['visibility_unknown']} repositories could not be classified, "
                  "so they are not named, and the outcome cannot be clean.", ""]
    lines += ["Outcomes: clean means every check passed and was verified; unverified means some evidence "
              "was unavailable, which is not a pass. To repair drift, dispatch **Apply Catylist Rulesets** "
              "as a dry run, review the plan, then apply."]
    return "\n".join(lines).rstrip() + "\n"


def find_issue(gh: Client, repo: str, preserved: frozenset[int]) -> dict[str, Any] | None:
    """The audit's own open issue: starts with ISSUE_MARKER and is not preserved. A title alone never matches."""
    issues = gh.get_all(f"/repos/{repo}/issues?state=open&labels={ISSUE_LABEL}&per_page=100", limit=200)
    for issue in issues:
        if "pull_request" in issue or issue.get("number") in preserved:
            continue
        if (issue.get("body") or "").startswith(ISSUE_MARKER):
            return issue
    return None


def publish(gh: Client, repo: str, body: str, result: str,
            preserved: frozenset[int] = PRESERVED_ISSUES) -> str:
    """Keep one issue open while drift exists; close it only once the audit is clean.

    ``result`` is ``outcome()``. An unverified result never opens or closes the
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
    parser.add_argument("--result-json", type=Path,
                        help=f"write the machine-readable outcome ({RESULT_SCHEMA}) here, even on error")
    return parser.parse_args(argv)


def _write(path: Path | None, text: str) -> bool:
    if path is None:
        return True
    try:
        path.write_text(text, encoding="utf-8")
        return True
    except OSError as exc:
        print(f"error: could not write an output file ({type(exc).__name__})", file=sys.stderr)
        return False


def _fail(args: argparse.Namespace, message: str) -> int:
    print(f"error: {message}", file=sys.stderr)
    _write(args.result_json, json.dumps({"schema": RESULT_SCHEMA, "outcome": "error"}) + "\n")
    return EXIT_CODES["error"]


def main(argv: list[str] | None = None, *, reader: Client | None = None, writer: Client | None = None) -> int:
    args = parse_args(argv)
    if args.result_json is not None:
        # The result file is written last, once the outcome is terminal; a stale one must never survive.
        try:
            args.result_json.unlink(missing_ok=True)
        except OSError:
            print("error: could not reset the result file", file=sys.stderr)
            return EXIT_CODES["error"]
    # No exception text reaches any sink: messages from input validation can name repositories.
    try:
        adopted = cr.load_adopted(args.fitment_config)
        required = cr.load_required_checks(args.required_checks)
    except (cr.PlanError, OSError, ValueError):
        return _fail(args, "unusable configuration (config/fitment.json or config/required-checks.json)")
    try:
        reader = reader or GitHubClient(os.environ.get("AUDIT_TOKEN") or os.environ.get("GITHUB_TOKEN"),
                                        agent="aems-ruleset-audit")
        repos = load_inventory(reader)
    except GitHubError as exc:
        return _fail(args, f"could not read the Catylist inventory ({_status(exc)})")
    except (cr.PlanError, ValueError):
        return _fail(args, "the Catylist inventory is unusable")
    wanted = {r.strip().lower() for r in args.repos.split(",") if r.strip()}
    if wanted:
        repos = [r for r in repos if r.lower() in wanted]
    audits = [audit_repository(reader, repo, adopted=repo.lower() in adopted, required=required)
              for repo in repos]
    body = render(audits)
    result = summary(audits)
    print(body)
    if not _write(args.output, body):
        return _fail(args, "the report was not written")
    if not args.dry_run:
        writer = writer or GitHubClient(os.environ.get("ISSUE_TOKEN") or os.environ.get("GITHUB_TOKEN"),
                                        agent="aems-ruleset-audit")
        preserved = PRESERVED_ISSUES | frozenset(args.preserve_issue)
        try:
            print(f"issue {publish(writer, args.issue_repository, body, result['outcome'], preserved)}")
        except GitHubError as exc:
            return _fail(args, f"issue update failed ({_status(exc)})")
    if not _write(args.result_json, json.dumps(result, sort_keys=True) + "\n"):
        return EXIT_CODES["error"]  # absent result file: consumers treat that as error
    return EXIT_CODES[result["outcome"]]


if __name__ == "__main__":
    sys.exit(main())
