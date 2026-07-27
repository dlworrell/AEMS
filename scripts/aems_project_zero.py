#!/usr/bin/env python3
"""Run the AEMS implementation of the AES-002 Project Zero lifecycle."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aems.inventory import inventory_json, inventory_markdown
from aems.project_zero import assess_project_zero


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Determine Project Zero state, run enabled evidence modules, and "
            "report blockers and next actions."
        )
    )
    parser.add_argument("root", nargs="?", default=".", help="Repository root")
    parser.add_argument("--manifest", help="Override the AES-003 manifest path")
    parser.add_argument(
        "--output",
        default="build/aems/project-zero",
        help="Evidence output directory, relative to the repository by default",
    )
    parser.add_argument(
        "--format",
        choices=("all", "json", "markdown"),
        default="all",
        help="Evidence formats to retain",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero unless the repository is ENGINEERING_READY",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"error: repository root is not a directory: {root}", file=sys.stderr)
        return 2
    output = Path(args.output)
    if not output.is_absolute():
        output = root / output

    assessment = assess_project_zero(
        root,
        manifest_path=args.manifest,
        output_root=(
            output.relative_to(root).as_posix()
            if output.is_relative_to(root)
            else str(output)
        ),
    )
    output.mkdir(parents=True, exist_ok=True)

    if args.format in {"all", "json"}:
        (output / "assessment.json").write_text(
            assessment.to_json(), encoding="utf-8"
        )
        (output / "repository-inventory.json").write_text(
            inventory_json(assessment.inventory), encoding="utf-8"
        )
        (output / "issue-graph.json").write_text(
            assessment.issue_graph.to_json(), encoding="utf-8"
        )
    if args.format in {"all", "markdown"}:
        (output / "assessment.md").write_text(
            assessment.to_markdown(), encoding="utf-8"
        )
        (output / "repository-inventory.md").write_text(
            inventory_markdown(assessment.inventory), encoding="utf-8"
        )
        (output / "issue-graph.md").write_text(
            assessment.issue_graph.to_markdown(), encoding="utf-8"
        )

    print(f"PROJECT_ZERO_STATE={assessment.current_state}")
    print(f"PROJECT_ZERO_ENGINEERING_READY={str(assessment.engineering_ready).lower()}")
    print(f"PROJECT_ZERO_EVIDENCE={output}")
    if args.strict and not assessment.engineering_ready:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
