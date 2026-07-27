#!/usr/bin/env python3
"""Generate deterministic machine- and human-readable repository inventories."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aems.inventory import build_inventory, inventory_json, inventory_markdown
from aems.structured import StructuredDataError, load_structured


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate the AES-002 repository and documentation inventory."
    )
    parser.add_argument("root", nargs="?", default=".", help="Repository root")
    parser.add_argument("--repository", help="Repository identifier for the report")
    parser.add_argument("--manifest", help="Optional JSON/YAML repository manifest")
    parser.add_argument(
        "--format", choices=("json", "markdown"), default="json"
    )
    parser.add_argument(
        "--output",
        help="Write the selected report to this path instead of standard output",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(args.root)
    if not root.is_dir():
        print(f"error: repository root is not a directory: {root}", file=sys.stderr)
        return 2

    manifest = None
    if args.manifest:
        try:
            loaded = load_structured(Path(args.manifest))
        except StructuredDataError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        if not isinstance(loaded, dict):
            print("error: manifest root must be a mapping", file=sys.stderr)
            return 2
        manifest = loaded

    report = build_inventory(
        root,
        repository=args.repository,
        manifest=manifest,
        excluded_roots=(
            str(Path(args.output).parent) if args.output else "",
        ),
    )
    rendered = (
        inventory_json(report)
        if args.format == "json"
        else inventory_markdown(report)
    )
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
