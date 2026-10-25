#!/usr/bin/env python3
"""Read-only, exact-head PR signature preflight for Catylist ADR-0006.

This checks GitHub's verification record for every PR commit. It does not
approve a PR, qualify its code, or claim that all merge requirements pass.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

SHA = re.compile(r"[0-9a-f]{40}\Z")
REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
SCHEMA = "aems.pr-signatures.v1"


class PreflightError(RuntimeError):
    pass


def assess(before: dict, commits: list, after: dict, expected_head: str) -> dict:
    report = {"schema": SCHEMA, "expected_head": expected_head,
              "outcome": "indeterminate", "commits": [], "diagnostics": []}
    diagnostic = report["diagnostics"].append
    if not isinstance(expected_head, str) or not SHA.fullmatch(expected_head):
        diagnostic("Expected PR head must be a full commit SHA.")
        return report
    if not isinstance(before, dict) or not isinstance(after, dict):
        diagnostic("Missing PR snapshots.")
        return report
    if (not isinstance(before.get("head"), dict) or not isinstance(after.get("head"), dict)
            or before["head"].get("sha") != expected_head or after["head"].get("sha") != expected_head):
        diagnostic("PR head changed or differs from the requested subject; rerun against the new head.")
        return report
    count = before.get("commits")
    if (type(count) is not int or count < 1 or type(after.get("commits")) is not int or after.get("commits") != count
            or not isinstance(commits, list) or len(commits) != count):
        diagnostic("PR commit enumeration is incomplete or changed during inspection.")
        return report
    ids = [c.get("sha") if isinstance(c, dict) else None for c in commits]
    if (any(not isinstance(s, str) or not SHA.fullmatch(s) for s in ids)
            or len(set(ids)) != len(ids) or ids[-1] != expected_head):
        diagnostic("Commit identities are malformed, repeated, or do not end at the expected head.")
        return report
    unknown = False
    violation = False
    for commit in commits:
        details = commit.get("commit")
        verification = details.get("verification") if isinstance(details, dict) else None
        if not isinstance(verification, dict):
            unknown = True
            verification = {}
        verified = verification.get("verified")
        reason = verification.get("reason")
        report["commits"].append({"sha": commit["sha"], "verified": verified, "reason": reason})
        if verified is False:
            violation = True
            diagnostic(f"Commit {commit['sha']} is not verified ({reason or 'unknown reason'}). A review or sign-off cannot sign it.")
        elif verified is not True or reason != "valid":
            unknown = True
            diagnostic(f"Commit {commit['sha']} has incomplete or inconsistent verification evidence.")
    report["outcome"] = "violation" if violation else "indeterminate" if unknown else "pass"
    return report


def get_json(path: str, token: str | None):
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        headers["Authorization"] = "Bearer " + token
    request = urllib.request.Request("https://api.github.com" + path, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read(16 * 1024 * 1024 + 1)
        if len(raw) > 16 * 1024 * 1024:
            raise PreflightError("GitHub response exceeded the preflight size limit.")
        return json.loads(raw)
    except urllib.error.HTTPError as error:
        raise PreflightError(f"GitHub read failed with HTTP {error.code}; no passing result is available.") from None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        raise PreflightError("GitHub response unavailable or invalid; no passing result is available.") from None


def collect(repository: str, number: int, expected_head: str, request=get_json, token=None) -> dict:
    if not REPOSITORY.fullmatch(repository) or number < 1 or not SHA.fullmatch(expected_head):
        raise PreflightError("A repository, positive PR number and full expected head SHA are required.")
    prefix = f"/repos/{repository}/pulls/{number}"
    before = request(prefix, token)
    commits = []
    # The pull-commits endpoint has a host-side limit. The declared count is
    # independently checked below, so truncation can never become a pass.
    for page in range(1, 41):
        batch = request(prefix + f"/commits?per_page=100&page={page}", token)
        if not isinstance(batch, list):
            raise PreflightError("GitHub returned a non-list commit page.")
        commits.extend(batch)
        if len(batch) < 100:
            break
    else:
        raise PreflightError("Commit pagination exceeded the bounded preflight limit.")
    after = request(prefix, token)
    return {"repository": repository, "pull_request": number,
            **assess(before, commits, after, expected_head)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repository", required=True)
    parser.add_argument("--pr", type=int, required=True)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        report = collect(args.repository, args.pr, args.expected_head,
                         token=os.environ.get("GITHUB_TOKEN"))
    except PreflightError as error:
        report = {"schema": SCHEMA, "repository": args.repository,
                  "pull_request": args.pr, "expected_head": args.expected_head,
                  "outcome": "indeterminate", "commits": [], "diagnostics": [str(error)]}
    text = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return {"pass": 0, "violation": 1, "indeterminate": 2}[report["outcome"]]


if __name__ == "__main__":
    sys.exit(main())
