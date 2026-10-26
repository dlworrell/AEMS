#!/usr/bin/env python3
"""Read-only retention preflight for Catylist ADR-0013 integration branches.

Existence alone is insufficient: GitHub can delete an unprotected promotion
head after merge. Inspect the active rules for each exact branch name before
opening promotions. This checks retention, not every ADR-0006 obligation.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Protocol

from ring0_sweep import FULL_NAME_PATTERN, GitHubClient, GitHubError

BRANCHES = ("dev-daily", "fitment")
SHA = re.compile(r"[0-9a-f]{40}")
RULES_LIMIT = 1000


class RetentionError(RuntimeError):
    """Missing, unreadable or unsafe integration-branch evidence."""


class Reader(Protocol):
    def get(self, path: str) -> Any: ...
    def get_all(self, path: str, limit: int = 1000) -> list[Any]: ...


def inspect_branches(github: Reader, repository: str) -> dict[str, str]:
    """Return observed heads only when both branches exist and resist deletion.

    The effective-rules endpoint excludes disabled/evaluate rulesets and
    includes inherited active rules. A broad `protected` flag or a ruleset's
    name alone cannot establish retention. No branch or setting is written.
    """
    if not FULL_NAME_PATTERN.fullmatch(repository):
        raise RetentionError("repository must be owner/name")
    heads: dict[str, str] = {}
    errors: list[str] = []
    for branch in BRANCHES:
        try:
            value = github.get(f"/repos/{repository}/branches/{branch}")
            sha = ((value or {}).get("commit") or {}).get("sha") if isinstance(value, dict) else None
            if not isinstance(sha, str) or not SHA.fullmatch(sha):
                errors.append(f"{branch}: branch head is malformed")
            else:
                heads[branch] = sha
        except GitHubError as exc:
            if exc.status == 404:
                errors.append(f"{branch}: branch is missing; restore its last verified head from promotion history "
                              "(use the default branch only for first adoption)")
            else:
                errors.append(f"{branch}: cannot read branch (HTTP {exc.status})")
        try:
            # Ask for one beyond our bound, rather than silently accepting a
            # truncated rules list from the shared client's bounded pagination.
            rules = github.get_all(f"/repos/{repository}/rules/branches/{branch}?per_page=100",
                                   limit=RULES_LIMIT + 1)
            if (not isinstance(rules, list) or len(rules) > RULES_LIMIT
                    or any(not isinstance(rule, dict) or not isinstance(rule.get("type"), str)
                           for rule in rules)):
                errors.append(f"{branch}: active-rule evidence is malformed or exceeds the limit")
            elif not any(rule["type"] == "deletion" for rule in rules):
                errors.append(f"{branch}: no active deletion rule; apply protect-integration-branches "
                              "with the AEMS Apply Catylist Rulesets workflow before promotion")
        except GitHubError as exc:
            errors.append(f"{branch}: cannot read active rules (HTTP {exc.status}); retention is unverified")
    if errors:
        raise RetentionError("integration-branch preflight failed: " + "; ".join(errors))
    return heads


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    result: dict[str, Any] = {"repository": args.repository, "status": "blocked"}
    try:
        client = GitHubClient(os.environ.get("GITHUB_TOKEN") or None, agent="aems-branch-retention")
        result.update(status="pass", heads=inspect_branches(client, args.repository))
    except (RetentionError, GitHubError, ValueError, TypeError) as exc:
        result["diagnostic"] = str(exc)
    text = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as out:
            out.write("## Integration branch retention\n\n```json\n" + text + "```\n")
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
