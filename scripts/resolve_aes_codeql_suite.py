#!/usr/bin/env python3
"""Resolve and check the pinned AES CodeQL default suite for one language.

codeql/<language>/aes-security.qls imports the upstream security-extended
suite at a pinned pack version and adds the AES custom queries. The .qls file
is the single source of truth for that pin.

  pin     print "<pack>@<version>" of the upstream import, for `codeql pack download`
  verify  run `codeql resolve queries` on the suite and require every custom query
          plus at least one upstream query in the resolved set
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def upstream_pin(suite: Path) -> str:
    """Return "<pack>@<version>" for the single upstream import in a .qls file."""
    pack = version = None
    for line in suite.read_text(encoding="utf-8").splitlines():
        key, _, value = line.strip().lstrip("- ").partition(":")
        if key == "from":
            pack = value.strip()
        elif key == "version":
            version = value.strip()
    if not pack or not version:
        raise ValueError(f"{suite} has no upstream `from:` pack with a `version:` pin")
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", pack) or not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError(f"{suite} has an unexpected upstream pin: {pack}@{version}")
    return f"{pack}@{version}"


def check_resolved(resolved: list[str], custom: list[Path]) -> list[str]:
    """Return problems with a resolved query list; empty means the suite is sound."""
    resolved_paths = {Path(path).resolve() for path in resolved}
    problems = [f"custom query missing from resolved suite: {query.relative_to(ROOT)}"
                for query in custom if query.resolve() not in resolved_paths]
    upstream = len(resolved_paths - {query.resolve() for query in custom})
    if upstream == 0:
        problems.append("resolved suite contains no upstream queries; the pinned import did not resolve")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=("pin", "verify"))
    parser.add_argument("--language", choices=("cpp", "swift"), required=True)
    parser.add_argument("--codeql", default="codeql")
    args = parser.parse_args(argv)
    pack = ROOT / "codeql" / args.language
    suite = pack / "aes-security.qls"
    if args.action == "pin":
        print(upstream_pin(suite))
        return 0
    output = subprocess.run(
        [args.codeql, "resolve", "queries", "--format=json",
         f"--additional-packs={ROOT / 'codeql'}", str(suite)],
        check=True, text=True, capture_output=True, timeout=600,
    ).stdout
    resolved = json.loads(output)
    custom = sorted((pack / "queries").glob("*.ql"))
    problems = check_resolved(resolved, custom)
    upstream = len(resolved) - len(custom)
    print(f"{args.language}: {upstream_pin(suite)} resolved {len(resolved)} queries "
          f"({len(custom)} AES custom + {upstream} upstream)")
    for problem in problems:
        print(f"error: {problem}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
