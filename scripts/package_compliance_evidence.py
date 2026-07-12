#!/usr/bin/env python3
"""Wrap an AEMS scanner JSON report in a stable evidence envelope."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = "catalyst.aems.compliance-evidence.v1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Package an AEMS scanner report as durable JSON evidence.")
    parser.add_argument("--input", required=True, help="Path to the raw scanner JSON report.")
    parser.add_argument("--output", required=True, help="Path for the packaged evidence JSON.")
    parser.add_argument("--standard", required=True, help="Standard identifier, such as AES-DEV-001.")
    parser.add_argument("--standard-version", required=True, help="Version or revision of the governing standard.")
    parser.add_argument("--repository", required=True, help="Repository in owner/name form.")
    parser.add_argument("--commit-sha", required=True, help="Commit SHA scanned.")
    parser.add_argument("--scanner-repository", default="dlworrell/AEMS")
    parser.add_argument("--scanner-commit-sha", required=True, help="AEMS scanner commit SHA.")
    parser.add_argument("--passed", choices=("true", "false"), required=True)
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError("scanner report must be a JSON object")
    return value


def main() -> int:
    args = parse_args()
    report = load_json(Path(args.input))
    envelope = {
        "schema": SCHEMA,
        "standard": {
            "id": args.standard,
            "version": args.standard_version,
        },
        "subject": {
            "repository": args.repository,
            "commit_sha": args.commit_sha,
        },
        "scanner": {
            "repository": args.scanner_repository,
            "commit_sha": args.scanner_commit_sha,
        },
        "scan": {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "passed": args.passed == "true",
        },
        "result": report,
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        json.dump(envelope, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
