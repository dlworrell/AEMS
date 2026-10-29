#!/usr/bin/env python3
"""Merge an owner-approved batch of pull requests in order (Catylist ADR-0016).

An omnibus pull request adds ``omnibus/<id>.json`` to AEMS. When an approver
listed in ``config/omnibus.json`` merges it, the merge is the approval of every
listed pull request at its listed head commit. This script then:

1. confirms the approval: the manifest's pull request was merged by an
   approver into an approval branch, its merge commit is verified, and the
   manifest has not changed since;
2. merges each listed pull request in order, by merge commit, with the approved
   head as the expected head, after checking it is open, not a draft, on the
   listed base, mergeable with every check passed, and not authored by
   ring-0 itself; and
3. stops at the first entry that fails, comments on every merged pull request
   and on the omnibus pull request, and records results in
   ``omnibus/<id>.json`` on AEMS's ``ring0/ledger`` branch.

``validate`` checks a manifest offline. ``plan`` writes a manifest for the
listed pull requests at their current heads. ``run`` executes an approved one.
"""

from __future__ import annotations

import argparse
import base64
import dataclasses
import datetime as dt
import json
import os
from pathlib import Path
import re
import sys
import time
from typing import Any, Callable
import urllib.parse

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ring0_sweep import (  # noqa: E402  (shared GitHub I/O)
    APP_SLUG,
    FULL_NAME_PATTERN,
    LEDGER_BRANCH,
    Client,
    GitHubClient,
    GitHubError,
    LedgerStore,
    decode_content,
)

CONFIG_SCHEMA = "aems.omnibus-config.v1"
MANIFEST_SCHEMA = "aems.omnibus-manifest.v1"
RESULT_SCHEMA = "aems.omnibus-result.v1"
ADR = "Catylist ADR-0016"
BOT_LOGIN = f"{APP_SLUG}[bot]"

ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{2,63}$")
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
BRANCH_PATTERN = re.compile(r"^[A-Za-z0-9._/-]{1,100}$")
REF_PATTERN = re.compile(r"^([A-Za-z0-9-]+/[A-Za-z0-9._-]+)#([1-9][0-9]*)$")
PASSING_CONCLUSIONS = frozenset({"success", "neutral", "skipped"})
MERGEABLE_RETRIES = 5
MERGED_PULL_SCAN = 200


class OmnibusError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Configuration and manifests
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Config:
    ledger_repository: str
    approvers: tuple[str, ...]
    approval_branches: tuple[str, ...]
    manifest_dir: str
    max_entries: int

    @classmethod
    def load(cls, path: Path) -> "Config":
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("schema") != CONFIG_SCHEMA:
            raise OmnibusError(f"{path}: schema must be {CONFIG_SCHEMA}")
        ledger = data.get("ledger_repository", "")
        approvers = tuple(data.get("approvers") or ())
        branches = tuple(data.get("approval_branches") or ())
        manifest_dir = data.get("manifest_dir", "omnibus")
        max_entries = data.get("max_entries", 100)
        if not FULL_NAME_PATTERN.match(ledger):
            raise OmnibusError(f"{path}: ledger_repository must be owner/name")
        if not approvers or not all(isinstance(a, str) and a and not a.endswith("[bot]") for a in approvers):
            raise OmnibusError(f"{path}: approvers must list at least one person (bots cannot approve)")
        if not branches or not all(isinstance(b, str) and BRANCH_PATTERN.match(b) for b in branches):
            raise OmnibusError(f"{path}: approval_branches must list branch names")
        if not isinstance(max_entries, int) or not 1 <= max_entries <= 100:
            raise OmnibusError(f"{path}: max_entries must be between 1 and 100")
        return cls(ledger, approvers, branches, manifest_dir, max_entries)


@dataclasses.dataclass(frozen=True)
class Entry:
    repository: str
    pull_request: int
    base: str
    head_sha: str
    title: str

    @property
    def key(self) -> str:
        return f"{self.repository}#{self.pull_request}"


@dataclasses.dataclass(frozen=True)
class Manifest:
    id: str
    summary: str
    entries: tuple[Entry, ...]


def parse_manifest(text: str, *, expected_id: str, config: Config) -> Manifest:
    """Validate a manifest; every problem is reported, not just the first."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise OmnibusError(f"manifest is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise OmnibusError("manifest must be a JSON object")
    problems: list[str] = []
    if data.get("schema") != MANIFEST_SCHEMA:
        problems.append(f"schema must be {MANIFEST_SCHEMA}")
    manifest_id = data.get("id")
    if not isinstance(manifest_id, str) or not ID_PATTERN.match(manifest_id):
        problems.append("id must be 3-64 lowercase letters, digits or hyphens")
    elif manifest_id != expected_id:
        problems.append(f"id {manifest_id!r} must match the file name {expected_id!r}")
    summary = data.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        problems.append("summary must say what the batch does")
    raw_entries = data.get("entries")
    entries: list[Entry] = []
    if not isinstance(raw_entries, list) or not raw_entries:
        problems.append("entries must be a non-empty list")
        raw_entries = []
    elif len(raw_entries) > config.max_entries:
        problems.append(f"entries lists {len(raw_entries)} pull requests; the limit is {config.max_entries}")
    owners = {a.lower() for a in config.approvers}
    seen: set[str] = set()
    for index, item in enumerate(raw_entries, start=1):
        where = f"entry {index}"
        if not isinstance(item, dict):
            problems.append(f"{where}: must be an object")
            continue
        repository = item.get("repository")
        number = item.get("pull_request")
        base = item.get("base")
        head = item.get("head_sha")
        title = item.get("title", "")
        if not isinstance(repository, str) or not FULL_NAME_PATTERN.match(repository):
            problems.append(f"{where}: repository must be owner/name")
            continue
        if repository.split("/")[0].lower() not in owners:
            problems.append(f"{where}: {repository} is not owned by an approver")
        if not isinstance(number, int) or isinstance(number, bool) or number < 1:
            problems.append(f"{where}: pull_request must be a positive integer")
            continue
        if not isinstance(base, str) or not BRANCH_PATTERN.match(base):
            problems.append(f"{where}: base must be a branch name")
        if not isinstance(head, str) or not SHA_PATTERN.match(head):
            problems.append(f"{where}: head_sha must be a full 40-character commit SHA")
        if not isinstance(title, str):
            problems.append(f"{where}: title must be text")
        entry = Entry(repository, number, base if isinstance(base, str) else "",
                      head if isinstance(head, str) else "", title if isinstance(title, str) else "")
        if entry.key in seen:
            problems.append(f"{where}: {entry.key} is listed twice")
        seen.add(entry.key)
        entries.append(entry)
    if problems:
        raise OmnibusError("invalid manifest:\n" + "\n".join(f"- {p}" for p in problems))
    return Manifest(manifest_id, summary.strip(), tuple(entries))


def manifest_path(config: Config, manifest_id: str) -> str:
    if not ID_PATTERN.match(manifest_id):
        raise OmnibusError(f"{manifest_id!r} is not a valid manifest id")
    return f"{config.manifest_dir}/{manifest_id}.json"


def render_manifest(manifest_id: str, summary: str, entries: list[Entry]) -> str:
    data = {"schema": MANIFEST_SCHEMA, "id": manifest_id, "summary": summary,
            "entries": [{"repository": e.repository, "pull_request": e.pull_request, "base": e.base,
                         "head_sha": e.head_sha, "title": e.title} for e in entries]}
    return json.dumps(data, indent=2) + "\n"


def render_omnibus_body(manifest: Manifest) -> str:
    """The omnibus pull request body: the list the owner approves by merging."""
    lines = [manifest.summary, "", "Merging this pull request approves each pull request below at the listed "
             "commit, merged by `catylist-ring-0` in this order. A push to any of them after approval stops "
             "the run at that entry.", "", "| # | Pull request | Base | Approved head | Title |",
             "|---|---|---|---|---|"]
    for index, entry in enumerate(manifest.entries, start=1):
        title = entry.title.replace("|", "/")
        lines.append(f"| {index} | {entry.repository}#{entry.pull_request} | `{entry.base}` | "
                     f"`{entry.head_sha[:12]}` | {title} |")
    lines += ["", f"ADR: {ADR} (owner-approved omnibus merges)"]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Approval
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Approval:
    pull_request: int
    merged_by: str
    merge_commit: str
    base: str
    url: str


def read_file(client: Client, repository: str, path: str, ref: str) -> str:
    payload = client.get(f"/repos/{repository}/contents/{urllib.parse.quote(path)}?ref={urllib.parse.quote(ref)}")
    return decode_content(payload)


def merged_pulls(client: Client, config: Config, branch: str) -> list[dict[str, Any]]:
    """Recently merged pull requests into ``branch``, newest first.

    ``/commits/{sha}/pulls`` is not used: GitHub returns only open pull
    requests there for commits that are not on the default branch, and
    omnibus pull requests merge into ``dev-daily``.
    """
    pulls = client.get_all(f"/repos/{config.ledger_repository}/pulls?state=closed&base={urllib.parse.quote(branch)}"
                           f"&sort=updated&direction=desc&per_page=100", limit=MERGED_PULL_SCAN)
    return [p for p in pulls if p.get("merged_at")]


def locate_approval(client: Client, config: Config, path: str, push_commit: str | None) -> dict[str, Any]:
    """The merged pull request whose merge commit is ``push_commit``, or that added ``path``."""
    for branch in config.approval_branches:
        for pull in merged_pulls(client, config, branch):
            if push_commit:
                if pull.get("merge_commit_sha") == push_commit:
                    return pull
                continue
            files = client.get_all(f"/repos/{config.ledger_repository}/pulls/{pull['number']}/files?per_page=100")
            if any(f.get("filename") == path and f.get("status") == "added" for f in files):
                return pull
    raise OmnibusError(f"{path} did not reach {' or '.join(config.approval_branches)} through a merged pull request")


def verify_approval(client: Client, config: Config, number: int) -> Approval:
    """Confirm that pull request ``number`` is an approval: right merger, only manifests, verified merge."""
    pull = client.get(f"/repos/{config.ledger_repository}/pulls/{number}")
    if not pull.get("merged_at") or pull.get("base", {}).get("ref") not in config.approval_branches:
        raise OmnibusError(f"#{number} was not merged into {' or '.join(config.approval_branches)}")
    merged_by = (pull.get("merged_by") or {}).get("login", "")
    if merged_by not in config.approvers:
        raise OmnibusError(f"#{pull['number']} was merged by {merged_by or 'nobody'}, who is not an approver "
                           f"in config/omnibus.json")
    # The approval must be a deliberate omnibus, not a manifest riding along
    # in a larger change the owner merged for other reasons.
    files = client.get_all(f"/repos/{config.ledger_repository}/pulls/{pull['number']}/files?per_page=100")
    stray = sorted(f.get("filename", "") for f in files
                   if f.get("filename", "").rpartition("/")[0] != config.manifest_dir
                   or not f.get("filename", "").endswith(".json"))
    if stray:
        raise OmnibusError(f"#{pull['number']} changes more than omnibus manifests ({', '.join(stray[:5])}); "
                           "an omnibus pull request may only add manifests")
    merge_commit = pull.get("merge_commit_sha") or ""
    verification = ((client.get(f"/repos/{config.ledger_repository}/commits/{merge_commit}") or {})
                    .get("commit", {}).get("verification", {}))
    if not verification.get("verified"):
        raise OmnibusError(f"the merge commit of #{pull['number']} is not verified "
                           f"({verification.get('reason', 'unknown')})")
    return Approval(pull["number"], merged_by, merge_commit, pull["base"]["ref"], pull.get("html_url", ""))


def find_approval(client: Client, config: Config, path: str, push_commit: str | None) -> tuple[Approval, str]:
    """Locate and confirm the approval and return it with the approved manifest text.

    On a push the pushed commit is the omnibus merge. On a dispatch the
    merged pull request that added the manifest is the approval.
    """
    approval = verify_approval(client, config, locate_approval(client, config, path, push_commit)["number"])
    # Every commit that ever touched the manifest must belong to the approving
    # pull request: a later pull request that edits it is not a new approval.
    allowed = {c.get("sha") for c in client.get_all(
        f"/repos/{config.ledger_repository}/pulls/{approval.pull_request}/commits?per_page=100")}
    allowed.add(approval.merge_commit)
    history = client.get_all(f"/repos/{config.ledger_repository}/commits?path={urllib.parse.quote(path)}"
                             f"&sha={urllib.parse.quote(approval.base)}&per_page=100")
    for commit in history:
        if commit.get("sha") not in allowed:
            raise OmnibusError(f"{path} was changed outside #{approval.pull_request} (commit {commit['sha'][:12]}); "
                               "approved manifests are immutable, so open a new omnibus with a new id")
    approved = read_file(client, config.ledger_repository, path, approval.merge_commit)
    current = read_file(client, config.ledger_repository, path, approval.base)
    if current != approved:
        raise OmnibusError(f"{path} changed on {approval.base} after #{approval.pull_request} approved it; "
                           "approved manifests are immutable, so open a new omnibus with a new id")
    return approval, approved


def manifests_in_commit(client: Client, config: Config, commit: str) -> list[str]:
    """Ids of manifests a pushed commit added (compared with its first parent)."""
    files = (client.get(f"/repos/{config.ledger_repository}/commits/{commit}") or {}).get("files", [])
    ids = []
    for item in files:
        name = item.get("filename", "")
        folder, _, leaf = name.rpartition("/")
        if folder == config.manifest_dir and leaf.endswith(".json") and item.get("status") == "added":
            ids.append(leaf[:-len(".json")])
    return sorted(ids)


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class Outcome:
    entry: Entry
    status: str  # merged | already-merged | dry-run | refused | not-attempted
    detail: str
    merge_commit: str = ""


def checks_outcome(runs: list[dict[str, Any]]) -> tuple[bool, str]:
    if not runs:
        return False, "no check has run on the approved commit"
    pending = sorted(r.get("name", "?") for r in runs if r.get("status") != "completed")
    if pending:
        return False, f"checks still running: {', '.join(pending[:5])}"
    failed = sorted(r.get("name", "?") for r in runs if r.get("conclusion") not in PASSING_CONCLUSIONS)
    if failed:
        return False, f"checks failing: {', '.join(failed[:5])}"
    return True, f"all {len(runs)} checks passed"


class Executor:
    def __init__(self, *, github: Client, config: Config, approval: Approval, manifest: Manifest,
                 dry_run: bool, sleep: Callable[[float], None] = time.sleep, log: Callable[[str], None] = print) -> None:
        self.gh = github
        self.config = config
        self.approval = approval
        self.manifest = manifest
        self.dry_run = dry_run
        self.sleep = sleep
        self.log = log
        self.outcomes: list[Outcome] = []

    def run(self) -> int:
        installed = {r["full_name"] for r in self.gh.get_all("/installation/repositories?per_page=100")}
        stopped = False
        for entry in self.manifest.entries:
            if stopped:
                self.outcomes.append(Outcome(entry, "not-attempted", "an earlier entry was refused"))
                continue
            if entry.repository not in installed:
                outcome = Outcome(entry, "refused", f"the {APP_SLUG} App is not installed on {entry.repository}")
            else:
                try:
                    outcome = self.merge(entry)
                except GitHubError as exc:
                    outcome = Outcome(entry, "refused", f"GitHub refused: {exc}")
            self.outcomes.append(outcome)
            self.log(f"{entry.key}: {outcome.status}: {outcome.detail}")
            stopped = outcome.status == "refused"
        if not self.dry_run:
            self.comment_on_omnibus()
        return 1 if stopped else 0

    def fetch_pull(self, entry: Entry) -> dict[str, Any]:
        path = f"/repos/{entry.repository}/pulls/{entry.pull_request}"
        pull = self.gh.get(path)
        for _ in range(MERGEABLE_RETRIES):
            if pull.get("state") != "open" or pull.get("mergeable") is not None:
                break
            self.sleep(3)  # GitHub computes mergeability in the background
            pull = self.gh.get(path)
        return pull

    def merge(self, entry: Entry) -> Outcome:
        pull = self.fetch_pull(entry)
        head = pull.get("head", {}).get("sha", "")
        if pull.get("merged"):
            if head == entry.head_sha:
                return Outcome(entry, "already-merged", "merged at the approved commit",
                               pull.get("merge_commit_sha") or "")
            return Outcome(entry, "refused", f"already merged, but at {head[:12]}, not the approved commit")
        if pull.get("state") != "open":
            return Outcome(entry, "refused", "closed without merging")
        if (pull.get("user") or {}).get("login") == BOT_LOGIN:
            return Outcome(entry, "refused", f"authored by {BOT_LOGIN}; ring-0 never merges its own work "
                                             "(Code Law 4), so the owner merges it directly")
        if pull.get("draft"):
            return Outcome(entry, "refused", "is a draft")
        if pull.get("base", {}).get("ref") != entry.base:
            return Outcome(entry, "refused", f"targets {pull.get('base', {}).get('ref')}, not {entry.base}")
        if head != entry.head_sha:
            return Outcome(entry, "refused", f"head moved to {head[:12]} after approval of "
                                             f"{entry.head_sha[:12]}; approve the new commit in a new omnibus")
        if pull.get("mergeable") is not True:
            return Outcome(entry, "refused", "GitHub reports it is not mergeable (conflict, or not yet computed)")
        state = pull.get("mergeable_state")
        if state != "clean":
            return Outcome(entry, "refused", f"merge state is {state!r}, not 'clean' (a required check, review "
                                             "or rule is unmet, or the branch is behind)")
        runs = (self.gh.get(f"/repos/{entry.repository}/commits/{head}/check-runs?per_page=100") or {}).get("check_runs", [])
        passed, detail = checks_outcome(runs)
        if not passed:
            return Outcome(entry, "refused", detail)
        if self.dry_run:
            return Outcome(entry, "dry-run", f"would merge; {detail}")
        title = pull.get("title") or entry.title
        result = self.gh.put(f"/repos/{entry.repository}/pulls/{entry.pull_request}/merge", {
            "merge_method": "merge",
            "sha": entry.head_sha,
            "commit_title": f"Merge pull request #{entry.pull_request} from {pull.get('head', {}).get('label', '')}",
            "commit_message": f"{title}\n\nApproved by @{self.approval.merged_by} in "
                              f"{self.config.ledger_repository}#{self.approval.pull_request} "
                              f"(omnibus {self.manifest.id}, {ADR})."})
        merge_commit = (result or {}).get("sha", "")
        try:
            self.gh.post(f"/repos/{entry.repository}/issues/{entry.pull_request}/comments", {"body": (
                f"Merged at the approved commit `{entry.head_sha[:12]}` by `{APP_SLUG}` under omnibus "
                f"`{self.manifest.id}`, approved by @{self.approval.merged_by} in "
                f"{self.config.ledger_repository}#{self.approval.pull_request}.\n\nADR: {ADR}")})
        except GitHubError as exc:  # the merge stands; only the note failed
            detail += f"; approval comment not posted ({exc})"
        return Outcome(entry, "merged", detail, merge_commit)

    def comment_on_omnibus(self) -> None:
        self.gh.post(f"/repos/{self.config.ledger_repository}/issues/{self.approval.pull_request}/comments",
                     {"body": render_results(self) + f"\nADR: {ADR}\n"})


def render_results(executor: Executor) -> str:
    counts: dict[str, int] = {}
    for outcome in executor.outcomes:
        counts[outcome.status] = counts.get(outcome.status, 0) + 1
    tally = ", ".join(f"{n} {s}" for s, n in sorted(counts.items())) or "nothing to do"
    lines = [f"# Omnibus `{executor.manifest.id}`", "",
             f"- Mode: {'dry run (nothing merged)' if executor.dry_run else 'enforce'}",
             f"- Approval: {executor.config.ledger_repository}#{executor.approval.pull_request} merged by "
             f"@{executor.approval.merged_by} into `{executor.approval.base}` "
             f"(`{executor.approval.merge_commit[:12]}`)",
             f"- Result: {tally}", "", "| # | Pull request | Result | Detail |", "|---|---|---|---|"]
    for index, outcome in enumerate(executor.outcomes, start=1):
        lines.append(f"| {index} | {outcome.entry.key} | {outcome.status} | {outcome.detail.replace('|', '/')} |")
    return "\n".join(lines) + "\n"


def load_result(ledger: Client | None, config: Config, manifest_id: str) -> tuple[dict[str, Any], str | None]:
    if ledger is None:
        return {}, None
    try:
        payload = ledger.get(f"/repos/{config.ledger_repository}/contents/"
                             f"{urllib.parse.quote(f'omnibus/{manifest_id}.json')}?ref={LEDGER_BRANCH}")
    except GitHubError as exc:
        if exc.status == 404:
            return {}, None
        raise
    return json.loads(decode_content(payload)), payload.get("sha")


def check_not_reused(previous: dict[str, Any], approval: Approval, manifest_id: str) -> None:
    recorded = (previous.get("approval") or {}).get("pull_request")
    if recorded is not None and recorded != approval.pull_request:
        raise OmnibusError(f"the ledger already holds omnibus {manifest_id} approved by #{recorded}; "
                           "ids are never reused")


def save_result(ledger: Client | None, executor: Executor, now: dt.datetime, dry_run: bool, output_dir: Path) -> None:
    """Record the run in ``omnibus/<id>.json`` on the ledger branch (latest result per entry)."""
    path = f"omnibus/{executor.manifest.id}.json"
    previous, sha = load_result(ledger, executor.config, executor.manifest.id)
    check_not_reused(previous, executor.approval, executor.manifest.id)
    entries = dict(previous.get("entries", {}))
    for outcome in executor.outcomes:
        if outcome.status in ("merged", "already-merged", "refused"):
            entries[outcome.entry.key] = {"status": outcome.status, "detail": outcome.detail,
                                          "approved_head": outcome.entry.head_sha,
                                          "merge_commit": outcome.merge_commit,
                                          "at": now.strftime("%Y-%m-%dT%H:%M:%SZ")}
    record = {"schema": RESULT_SCHEMA, "id": executor.manifest.id,
              "approval": dataclasses.asdict(executor.approval), "entries": entries,
              "runs": previous.get("runs", []) + [{"at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                                                    "dry_run": dry_run,
                                                    "statuses": [o.status for o in executor.outcomes]}]}
    text = json.dumps(record, indent=2, sort_keys=True) + "\n"
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "omnibus-result.json").write_text(text, encoding="utf-8")
    if dry_run or ledger is None:
        return
    LedgerStore(ledger, executor.config.ledger_repository, False, output_dir).ensure_branch()
    body: dict[str, Any] = {"message": f"omnibus {executor.manifest.id} ({now.strftime('%Y-%m-%dT%H:%MZ')})",
                            "branch": LEDGER_BRANCH,
                            "content": base64.b64encode(text.encode("utf-8")).decode("ascii")}
    if sha:
        body["sha"] = sha
    ledger.put(f"/repos/{executor.config.ledger_repository}/contents/{urllib.parse.quote(path)}", body)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def plan(client: Client, config: Config, manifest_id: str, summary: str, refs: list[str]) -> str:
    entries = []
    for ref in refs:
        match = REF_PATTERN.match(ref.strip())
        if not match:
            raise OmnibusError(f"{ref!r} must look like owner/name#123")
        repository, number = match.group(1), int(match.group(2))
        pull = client.get(f"/repos/{repository}/pulls/{number}")
        if pull.get("state") != "open":
            raise OmnibusError(f"{ref} is not open")
        entries.append(Entry(repository, number, pull["base"]["ref"], pull["head"]["sha"], pull.get("title", "")))
    text = render_manifest(manifest_id, summary, entries)
    parse_manifest(text, expected_id=manifest_id, config=config)
    return text


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", type=Path, default=Path("config/omnibus.json"))
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate", help="check manifest files offline")
    validate.add_argument("paths", nargs="+", type=Path)
    validate.add_argument("--body", action="store_true", help="also print the omnibus pull request body")

    planner = sub.add_parser("plan", help="write a manifest for pull requests at their current heads")
    planner.add_argument("--id", required=True)
    planner.add_argument("--summary", required=True)
    planner.add_argument("refs", nargs="+", help="owner/name#number, in merge order")

    run = sub.add_parser("run", help="merge the pull requests of an approved manifest")
    target = run.add_mutually_exclusive_group(required=True)
    target.add_argument("--id", help="the manifest to run (a dispatch, or a re-run)")
    target.add_argument("--push-commit", help="a pushed commit: run every manifest it added")
    run.add_argument("--output-dir", type=Path, default=Path("build/aems/omnibus"))
    mode = run.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="check every entry; merge nothing")
    mode.add_argument("--enforce", action="store_true", help="merge, comment and record")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config = Config.load(args.config)
    if args.command == "validate":
        for path in args.paths:
            manifest = parse_manifest(path.read_text(encoding="utf-8"), expected_id=path.stem, config=config)
            print(f"{path}: {len(manifest.entries)} entries, valid")
            if args.body:
                print(render_omnibus_body(manifest))
        return 0
    token = os.environ.get("RING0_APP_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if args.command == "plan":
        sys.stdout.write(plan(GitHubClient(token, agent="aems-omnibus"), config, args.id, args.summary, args.refs))
        return 0
    if not os.environ.get("RING0_APP_TOKEN"):
        raise OmnibusError("RING0_APP_TOKEN is required (the catylist-ring-0 installation token)")
    github = GitHubClient(os.environ["RING0_APP_TOKEN"], agent="aems-omnibus")
    ledger_token = os.environ.get("LEDGER_TOKEN")
    ledger = GitHubClient(ledger_token) if ledger_token else None
    ids = [args.id] if args.id else manifests_in_commit(github, config, args.push_commit)
    if not ids:
        print("The pushed commit added no omnibus manifest; nothing to do.")
        return 0
    status = 0
    summaries = []
    for manifest_id in ids:
        status |= run_manifest(github, ledger, config, manifest_id, args.push_commit or None,
                               args.dry_run, args.output_dir / manifest_id, summaries)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "summary.md").write_text("\n".join(summaries), encoding="utf-8")
    print("\n".join(summaries))
    return status


def run_manifest(github: Client, ledger: Client | None, config: Config, manifest_id: str, push_commit: str | None,
                 dry_run: bool, output_dir: Path, summaries: list[str]) -> int:
    path = manifest_path(config, manifest_id)
    try:
        approval, text = find_approval(github, config, path, push_commit)
        manifest = parse_manifest(text, expected_id=manifest_id, config=config)
        check_not_reused(load_result(ledger, config, manifest_id)[0], approval, manifest_id)
    except (OmnibusError, GitHubError) as exc:  # report it and carry on with the other manifests
        summaries.append(f"# Omnibus `{manifest_id}`\n\nNot run: {exc}\n")
        return 1
    executor = Executor(github=github, config=config, approval=approval, manifest=manifest, dry_run=dry_run)
    status = executor.run()
    save_result(ledger, executor, dt.datetime.now(dt.timezone.utc), dry_run, output_dir)
    summaries.append(render_results(executor))
    return status


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OmnibusError, GitHubError) as exc:
        print(f"omnibus: {exc}", file=sys.stderr)
        sys.exit(2)
