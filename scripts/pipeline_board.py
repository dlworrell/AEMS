#!/usr/bin/env python3
"""Pipeline board: where every change stands in the Catylist ADR-0013 flow.

Reads the repositories in config/fitment.json and reports, for each one, what
is waiting at every stage of topic -> dev-daily -> fitment -> main -> release,
and which pull requests carried each recent change ("#137 in promotion #138 in
release candidate #140"). The report is written as the body of one pinned AEMS
issue so the owner can see it at a glance; it never merges, approves or
changes any repository.

Standard library only. Exit codes: 0 report produced (and published unless
--dry-run), 2 unusable configuration or GitHub error.
"""
from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import json
import os
from pathlib import Path
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ring0_sweep import FULL_NAME_PATTERN, Client, GitHubClient, GitHubError  # noqa: E402

DAILY = "dev-daily"
FITMENT = "fitment"
CONFIG_SCHEMA = "aems.fitment-config.v1"
DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "config" / "fitment.json"
BOARD_TITLE = "Pipeline board"
BOARD_LABEL = "pipeline-board"
STAMP_PREFIX = "_Updated "
RECENT_DAYS = 14
MAX_RECENT = 10


class BoardError(RuntimeError):
    pass


@dataclasses.dataclass(frozen=True)
class Change:
    """A merged topic pull request and how far it has travelled."""

    number: int
    title: str
    stage: str          # dev-daily, fitment, main or released
    promotion: int | None
    candidate: int | None
    release: str | None


@dataclasses.dataclass
class RepoStatus:
    repository: str
    default: str
    waiting_promotion: int = 0      # commits on dev-daily not yet on fitment
    waiting_candidate: int = 0      # commits on fitment not yet on main
    open_topic: list[dict[str, Any]] = dataclasses.field(default_factory=list)
    open_promotion: list[dict[str, Any]] = dataclasses.field(default_factory=list)
    open_candidate: list[dict[str, Any]] = dataclasses.field(default_factory=list)
    stray: list[dict[str, Any]] = dataclasses.field(default_factory=list)
    changes: list[Change] = dataclasses.field(default_factory=list)
    release: str | None = None
    problem: str | None = None


def load_repositories(path: Path) -> list[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    repos = data.get("repositories") if isinstance(data, dict) else None
    if not isinstance(data, dict) or data.get("schema") != CONFIG_SCHEMA or not isinstance(repos, list):
        raise BoardError(f"{path}: not an {CONFIG_SCHEMA} file")
    seen: set[str] = set()
    for repo in repos:
        if not isinstance(repo, str) or not FULL_NAME_PATTERN.match(repo) or repo.lower() in seen:
            raise BoardError(f"{path}: bad or duplicate repository {repo!r}")
        seen.add(repo.lower())
    return list(repos)


def _contains(gh: Client, repo: str, sha: str, ref: str) -> bool:
    """True when commit ``sha`` is reachable from ``ref``.

    A failing compare raises GitHubError rather than reading as "not contained": ``main`` turns it
    into the repository's warning row, so an API error is never shown as "up to date" or as an
    earlier stage.
    """
    status = gh.get(f"/repos/{repo}/compare/{sha}...{ref}").get("status")
    return status in ("ahead", "identical")


def _ahead(gh: Client, repo: str, base: str, head: str) -> int:
    """Commits on ``head`` not on ``base``; a failing compare raises (see ``_contains``)."""
    return int(gh.get(f"/repos/{repo}/compare/{base}...{head}").get("ahead_by", 0))


def _merged(gh: Client, repo: str, base: str, head: str | None = None) -> list[dict[str, Any]]:
    """Merged pull requests into ``base`` (optionally from ``head``), oldest merge first."""
    pulls = gh.get_all(f"/repos/{repo}/pulls?state=closed&base={base}&sort=updated&direction=desc&per_page=50",
                       limit=50)
    merged = [p for p in pulls if p.get("merged_at") and p.get("merge_commit_sha")
              and (head is None or p.get("head", {}).get("ref") == head)]
    return sorted(merged, key=lambda p: p["merged_at"])


def _carrier(gh: Client, repo: str, sha: str, carriers: list[dict[str, Any]]) -> int | None:
    """The first merged carrier pull request whose merge commit contains ``sha``."""
    for pull in carriers:
        if _contains(gh, repo, sha, pull["merge_commit_sha"]):
            return pull["number"]
    return None


def inspect(gh: Client, repo: str, now: dt.datetime) -> RepoStatus:
    meta = gh.get(f"/repos/{repo}")
    status = RepoStatus(repository=repo, default=meta["default_branch"])
    main = status.default
    try:
        gh.get(f"/repos/{repo}/branches/{DAILY}")
        gh.get(f"/repos/{repo}/branches/{FITMENT}")
    except GitHubError:
        status.problem = "dev-daily or fitment branch missing"
        return status
    status.waiting_promotion = _ahead(gh, repo, FITMENT, DAILY)
    status.waiting_candidate = _ahead(gh, repo, main, FITMENT)

    for pull in sorted(gh.get_all(f"/repos/{repo}/pulls?state=open&per_page=100", limit=100),
                       key=lambda p: p["number"]):
        base, head = pull["base"]["ref"], pull["head"]["ref"]
        entry = {"number": pull["number"], "title": pull["title"], "url": pull["html_url"],
                 "author": pull.get("user", {}).get("login", ""), "draft": bool(pull.get("draft"))}
        if base == FITMENT and head == DAILY:
            status.open_promotion.append(entry)
        elif base == main and head == FITMENT:
            status.open_candidate.append(entry)
        elif base == DAILY:
            status.open_topic.append(entry)
        elif base == main:
            status.stray.append(entry)  # skips the flow; the fitment/source check blocks it
    for entry in status.open_promotion + status.open_candidate:
        detail = gh.get(f"/repos/{repo}/pulls/{entry['number']}")
        entry["ready"] = detail.get("mergeable_state") == "clean"

    releases = gh.get_all(f"/repos/{repo}/releases?per_page=1", limit=1)
    status.release = releases[0]["tag_name"] if releases else None

    since = now - dt.timedelta(days=RECENT_DAYS)
    topics = [p for p in _merged(gh, repo, DAILY)
              if p.get("head", {}).get("ref") != FITMENT
              and dt.datetime.fromisoformat(p["merged_at"].replace("Z", "+00:00")) >= since]
    topics = topics[-MAX_RECENT:]
    promotions = _merged(gh, repo, FITMENT, DAILY) if topics else []
    candidates = _merged(gh, repo, main, FITMENT) if topics else []
    for pull in topics:
        # The stage comes from ancestry alone; the carrier pull request is optional detail, because a
        # squash merge, a direct push or a carrier outside the scanned window has none to show.
        sha = pull["merge_commit_sha"]
        on_fitment = _contains(gh, repo, sha, FITMENT)
        on_main = on_fitment and _contains(gh, repo, sha, main)
        released = on_main and bool(status.release) and _contains(gh, repo, sha, status.release)
        promotion = _carrier(gh, repo, sha, promotions) if on_fitment else None
        candidate = _carrier(gh, repo, sha, candidates) if on_main else None
        stage = ("released" if released else "main" if on_main else
                 "fitment" if on_fitment else "dev-daily")
        status.changes.append(Change(pull["number"], pull["title"], stage, promotion, candidate,
                                     status.release if released else None))
    return status


def _link(repo: str, number: int) -> str:
    return f"[#{number}](https://github.com/{repo}/pull/{number})"


def _chain(repo: str, change: Change) -> str:
    parts = [_link(repo, change.number)]
    if change.stage == "dev-daily":
        return " → ".join(parts + ["awaiting promotion"])
    parts.append(f"in promotion {_link(repo, change.promotion)}" if change.promotion
                 else "on fitment (carrier unknown)")
    if change.stage == "fitment":
        return " → ".join(parts + ["awaiting RC"])
    parts.append(f"in RC {_link(repo, change.candidate)}" if change.candidate else "on main (carrier unknown)")
    parts.append(f"released {change.release}" if change.release else "not in a release yet")
    return " → ".join(parts)


STAGE_MARK = {"dev-daily": "🟡 dev-daily", "fitment": "🟠 fitment", "main": "🟢 main", "released": "✅ released"}


def render(statuses: list[RepoStatus], now: dt.datetime) -> str:
    lines = ["# Pipeline board", "",
             f"{STAMP_PREFIX}{now.strftime('%Y-%m-%d %H:%M')} UTC by the AEMS pipeline-board workflow "
             "(Catylist ADR-0013). Read-only: it never merges or approves._", ""]
    needs = []
    for s in statuses:
        for pr in s.open_promotion:
            needs.append(f"- **{s.repository}** promotion {_link(s.repository, pr['number'])} "
                         f"(dev-daily → fitment): {'ready to merge' if pr.get('ready') else 'waiting on checks'}")
        for pr in s.open_candidate:
            needs.append(f"- **{s.repository}** release candidate {_link(s.repository, pr['number'])} "
                         f"(fitment → main): {'ready to merge' if pr.get('ready') else 'waiting on checks'}")
        for pr in s.stray:
            needs.append(f"- **{s.repository}** {_link(s.repository, pr['number'])} targets main directly "
                         f"({pr['author']}); route it through dev-daily or close it")
        if s.waiting_candidate and not s.open_candidate and not s.problem:
            needs.append(f"- **{s.repository}**: {s.waiting_candidate} commit(s) on fitment are not on main yet; "
                         "the fitment cycle opens the release candidate once fitment passes")
    lines += ["## Needs you", ""] + (needs or ["Nothing to merge right now."]) + [""]

    lines += ["## Stages", "",
              "| Repository | Topic PRs open | dev-daily → fitment | fitment → main | Last release |",
              "|---|---|---|---|---|"]
    for s in statuses:
        if s.problem:
            lines.append(f"| {s.repository} | ⚠️ {s.problem} | | | |")
            continue
        topic = ", ".join(_link(s.repository, p["number"]) for p in s.open_topic) or "—"
        promo = (f"{s.waiting_promotion} commit(s)" + (
            f" in {_link(s.repository, s.open_promotion[0]['number'])}" if s.open_promotion else "")
        ) if s.waiting_promotion else "up to date"
        cand = (f"{s.waiting_candidate} commit(s)" + (
            f" in {_link(s.repository, s.open_candidate[0]['number'])}" if s.open_candidate else "")
        ) if s.waiting_candidate else "up to date"
        lines.append(f"| {s.repository} | {topic} | {promo} | {cand} | {s.release or '—'} |")
    lines.append("")

    flight = [(s, c) for s in statuses for c in reversed(s.changes) if c.stage in ("dev-daily", "fitment")]
    lines += ["## In flight", ""]
    lines += [f"- {STAGE_MARK[c.stage]}: **{s.repository}** {_chain(s.repository, c)}: {c.title}"
              for s, c in flight] or ["Nothing between dev-daily and main."]
    lines.append("")

    landed = [s for s in statuses if any(c.stage in ("main", "released") for c in s.changes)]
    lines += [f"## Landed in the last {RECENT_DAYS} days", ""]
    if not landed:
        lines += ["Nothing reached main recently.", ""]
    for s in landed:
        done = [c for c in reversed(s.changes) if c.stage in ("main", "released")]
        lines += [f"<details><summary><b>{s.repository}</b>: {len(done)} change(s)</summary>", ""]
        lines += [f"- {STAGE_MARK[c.stage]}: {_chain(s.repository, c)}: {c.title}" for c in done]
        lines += ["", "</details>", ""]
    return "\n".join(lines).rstrip() + "\n"


def _without_stamp(body: str) -> str:
    return "\n".join(line for line in (body or "").splitlines() if not line.startswith(STAMP_PREFIX))


def publish(gh: Client, repo: str, body: str) -> str:
    """Create or update the board issue. Returns created, updated or unchanged."""
    issues = gh.get_all(f"/repos/{repo}/issues?state=open&labels={BOARD_LABEL}&per_page=10", limit=10)
    board = next((i for i in issues if i.get("title") == BOARD_TITLE and "pull_request" not in i), None)
    if board is None:
        gh.post(f"/repos/{repo}/issues", {"title": BOARD_TITLE, "body": body, "labels": [BOARD_LABEL]})
        return "created"
    if _without_stamp(board.get("body") or "") == _without_stamp(body):
        return "unchanged"
    gh.patch(f"/repos/{repo}/issues/{board['number']}", {"body": body})
    return "updated"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--board-repository", default="dlworrell/AEMS")
    parser.add_argument("--dry-run", action="store_true", help="print the board instead of publishing it")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None, *, reader: Client | None = None, writer: Client | None = None,
         now: dt.datetime | None = None) -> int:
    args = parse_args(argv)
    now = now or dt.datetime.now(dt.timezone.utc)
    try:
        repos = load_repositories(args.config)
        reader = reader or GitHubClient(os.environ.get("RING0_APP_TOKEN") or os.environ.get("GITHUB_TOKEN"),
                                        agent="aems-pipeline-board")
        statuses = []
        for repo in repos:
            try:
                statuses.append(inspect(reader, repo, now))
            except GitHubError as exc:
                statuses.append(RepoStatus(repository=repo, default="?", problem=f"unreadable ({exc})"[:120]))
        body = render(statuses, now)
        if args.dry_run:
            print(body)
            return 0
        writer = writer or GitHubClient(os.environ.get("BOARD_TOKEN") or os.environ.get("GITHUB_TOKEN"),
                                        agent="aems-pipeline-board")
        print(f"board {publish(writer, args.board_repository, body)}")
        return 0
    except (BoardError, GitHubError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
