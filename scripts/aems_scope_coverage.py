#!/usr/bin/env python3
"""Verify disjoint AES-003 scope ownership and emit the complete scan plan."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from aems.structured import load_structured
from aes_sec_001_scan import checkout_root, relative_prefix


def coverage(root: Path, manifest: dict, files: list[str]) -> dict:
    root = root.resolve()
    if not isinstance(manifest, dict):
        raise ValueError("manifest must be a mapping")
    scopes = manifest.get("scopes", [])
    if not isinstance(scopes, list):
        raise ValueError("manifest scopes must be an array")
    paths: dict[str, str] = {}
    ids = set()
    for scope in scopes:
        if not isinstance(scope, dict) or not isinstance(scope.get("id"), str) or not scope["id"]:
            raise ValueError("each scope requires an id and path")
        path = relative_prefix(scope.get("path"))
        if "/" in path:
            raise ValueError("ADR-0004 scopes must be top-level directories")
        if scope["id"] in ids or path in paths:
            raise ValueError("scope IDs and paths must be unique and disjoint")
        if not (root / path).is_dir() or (root / path).is_symlink():
            raise ValueError(f"scope directory is missing or a symlink: {path}")
        ids.add(scope["id"])
        paths[path] = scope["id"]
    assignments = {".": []}
    assignments.update({path: [] for path in sorted(paths)})
    for filename in sorted(set(files)):
        relative_prefix(filename)
        owners = [p for p in paths if filename.startswith(p + "/")]
        if len(owners) > 1:
            raise ValueError(f"overlapping scope ownership: {filename}")
        assignments[owners[0] if owners else "."].append(filename)
    if sum(map(len, assignments.values())) != len(set(files)):
        raise ValueError("scope assignment is not exhaustive")
    return {"schema_version": "1.0.0", "coverage": "disjoint-and-exhaustive",
            "tracked_file_count": len(set(files)),
            "scan_plan": [{"scan_root": ".", "exclude_paths": sorted(paths)}] +
                         [{"scan_root": p, "exclude_paths": []} for p in sorted(paths)],
            "ownership": assignments,
            "qualification": "Path coverage only; does not certify adoption, test success, or production readiness."}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=".", type=Path)
    parser.add_argument("--manifest", default="aes-manifest.yaml")
    args = parser.parse_args()
    try:
        root = args.root.resolve()
        if checkout_root(root) != root:
            raise ValueError("coverage requires the repository checkout root")
        tracked = subprocess.check_output(["git", "-C", str(root), "ls-files", "-z"], text=True).split("\0")
        result = coverage(root, load_structured(root / args.manifest), [p for p in tracked if p])
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
