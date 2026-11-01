#!/usr/bin/env python3
"""Ring-0 change gate: run a scheduled ring-0 job only when something changed.

``check`` fingerprints what a ring-0 job reacts to in every repository of a
config (branch heads of dev-daily, fitment and the default branch; open pull
requests and their heads; CI results on the fitment head and on open
promotion and release-candidate heads, excluding ring-0's own checks) and
compares it with the fingerprint recorded after the last successful run. It
prints ``run=true`` or ``run=false`` (also to ``$GITHUB_OUTPUT``). A run is
forced when nothing was recorded yet, or the last recorded run is older than
``--max-age-hours`` (default 6).

``record`` stores a fingerprint on the ``ring0/ledger`` branch; workflows call
it only after the gated job succeeded, so a failed run is retried next time.
With ``--config`` it recomputes the fingerprint after the job, so the pull
requests and issues the job itself opened do not trigger an extra run.

Standard library only. Exit codes: 0 decision made or recorded, 2 unusable
input or GitHub error.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any
import base64
import urllib.parse

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ring0_sweep import LEDGER_BRANCH, Client, GitHubClient, GitHubError, decode_content  # noqa: E402
from pipeline_board import DAILY, FITMENT, BoardError, load_repositories  # noqa: E402

GATE_SCHEMA = "aems.ring0-gate.v1"
OWN_CHECKS = frozenset({"fitment", "fitment/source"})  # posted by ring-0 itself; must not retrigger it
DEFAULT_MAX_AGE_HOURS = 6.0


def _checks(gh: Client, repo: str, sha: str) -> list[list[str]]:
    payload = gh.get(f"/repos/{repo}/commits/{sha}/check-runs?per_page=100") or {}
    runs = [[r.get("name", ""), r.get("status", ""), r.get("conclusion") or ""]
            for r in payload.get("check_runs", []) if r.get("name") not in OWN_CHECKS]
    return sorted(runs)


def snapshot(gh: Client, repo: str) -> dict[str, Any]:
    """What a ring-0 job reacts to in one repository, in a stable order."""
    meta = gh.get(f"/repos/{repo}")
    default = meta["default_branch"]
    heads: dict[str, str | None] = {}
    for branch in (DAILY, FITMENT, default):
        try:
            heads[branch] = gh.get(f"/repos/{repo}/branches/{branch}")["commit"]["sha"]
        except GitHubError as exc:
            if exc.status != 404:
                raise
            heads[branch] = None
    pulls = []
    for pull in sorted(gh.get_all(f"/repos/{repo}/pulls?state=open&per_page=100", limit=100),
                       key=lambda p: p["number"]):
        base, sha = pull["base"]["ref"], pull["head"]["sha"]
        entry: dict[str, Any] = {"number": pull["number"], "base": base, "head": sha}
        if base in (FITMENT, default):
            entry["checks"] = _checks(gh, repo, sha)
        pulls.append(entry)
    fitment_checks = _checks(gh, repo, heads[FITMENT]) if heads[FITMENT] else []
    return {"heads": heads, "pulls": pulls, "fitment_checks": fitment_checks}


def fingerprint(gh: Client, repos: list[str]) -> str:
    state = {repo: snapshot(gh, repo) for repo in sorted(repos, key=str.lower)}
    return hashlib.sha256(json.dumps(state, sort_keys=True).encode("utf-8")).hexdigest()


def _path(name: str) -> str:
    return f"ring0/gate-{name}.json"


def load_record(gh: Client, ledger: str, name: str) -> tuple[dict[str, Any] | None, str | None]:
    try:
        payload = gh.get(f"/repos/{ledger}/contents/{urllib.parse.quote(_path(name))}?ref={LEDGER_BRANCH}")
    except GitHubError as exc:
        if exc.status == 404:
            return None, None
        raise
    record = json.loads(decode_content(payload))
    if not isinstance(record, dict) or record.get("schema") != GATE_SCHEMA:
        return None, payload.get("sha")
    return record, payload.get("sha")


def decide(record: dict[str, Any] | None, current: str, now: dt.datetime, max_age_hours: float) -> tuple[bool, str]:
    if not record:
        return True, "no recorded run yet"
    try:
        recorded = dt.datetime.fromisoformat(record["recorded_at"])
    except (KeyError, TypeError, ValueError):
        return True, "unreadable record"
    if now - recorded >= dt.timedelta(hours=max_age_hours):
        return True, f"last full run is older than {max_age_hours:g} h"
    if record.get("fingerprint") != current:
        return True, "something changed"
    return False, "nothing changed since the last successful run"


def record_run(gh: Client, ledger: str, name: str, value: str, now: dt.datetime) -> None:
    _, sha = load_record(gh, ledger, name)
    text = json.dumps({"schema": GATE_SCHEMA, "fingerprint": value,
                       "recorded_at": now.isoformat(timespec="seconds")}, sort_keys=True) + "\n"
    body: dict[str, Any] = {"message": f"ring0 gate: {name} ran", "branch": LEDGER_BRANCH,
                            "content": base64.b64encode(text.encode("utf-8")).decode("ascii")}
    if sha:
        body["sha"] = sha
    gh.put(f"/repos/{ledger}/contents/{urllib.parse.quote(_path(name))}", body)


def _emit(**values: str) -> None:
    lines = "".join(f"{k}={v}\n" for k, v in values.items())
    print(lines, end="")
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as handle:
            handle.write(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("check", "record"):
        p = sub.add_parser(name)
        p.add_argument("--name", required=True, help="gated job name, e.g. fitment-cycle")
        p.add_argument("--ledger-repository", default="dlworrell/AEMS")
    check = sub.choices["check"]
    check.add_argument("--config", type=Path, required=True)
    check.add_argument("--max-age-hours", type=float, default=DEFAULT_MAX_AGE_HOURS)
    group = sub.choices["record"].add_mutually_exclusive_group(required=True)
    group.add_argument("--fingerprint", help="a fingerprint printed by check")
    group.add_argument("--config", type=Path, help="recompute the fingerprint now, after the job ran")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None, *, reader: Client | None = None, ledger: Client | None = None,
         now: dt.datetime | None = None) -> int:
    args = parse_args(argv)
    now = now or dt.datetime.now(dt.timezone.utc)
    try:
        if not args.name.replace("-", "").isalnum():
            raise ValueError("--name must be letters, digits and dashes")
        ledger = ledger or GitHubClient(os.environ.get("LEDGER_TOKEN") or os.environ.get("GITHUB_TOKEN"),
                                        agent="aems-ring0-gate")
        reader = reader or GitHubClient(os.environ.get("RING0_APP_TOKEN"), agent="aems-ring0-gate")
        if args.command == "record":
            value = args.fingerprint or fingerprint(reader, load_repositories(args.config))
            if len(value) != 64:
                raise ValueError("--fingerprint must be a sha256 hex digest")
            record_run(ledger, args.ledger_repository, args.name, value, now)
            print(f"recorded {args.name}")
            return 0
        current = fingerprint(reader, load_repositories(args.config))
        record, _ = load_record(ledger, args.ledger_repository, args.name)
        run, reason = decide(record, current, now, args.max_age_hours)
        _emit(run="true" if run else "false", fingerprint=current)
        print(f"reason: {reason}")
        return 0
    except (BoardError, GitHubError, OSError, ValueError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
