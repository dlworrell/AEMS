#!/usr/bin/env python3
"""Rekey existing AES-SEC-001 review history for a path-only scope move.

Inputs are never overwritten. Approval/rationale/date fields are copied, not
created. New source is scanned twice, using its old and new path identities.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import sys

from aes_sec_001_scan import (
    DEFAULT_REVIEW_DISPOSITIONS_PATH, NATIVE_SOURCE_EXTENSIONS,
    checkout_root, is_local_file, load_review_disposition_ledger,
    relative_prefix, scan_source_for_apis,
)


def rekey(ledger: dict, repository_root: Path, new_scope: str, path_map: dict) -> tuple[dict, dict, dict]:
    root = repository_root.resolve()
    scope = relative_prefix(new_scope)
    scope_root = root / scope
    if not scope_root.is_dir() or scope_root.is_symlink() or checkout_root(scope_root) != root:
        raise ValueError("new scope must be a real directory inside the repository checkout")
    if not isinstance(path_map, dict) or not path_map:
        raise ValueError("path map must be a nonempty object of old paths to new scope-relative paths")
    mapping = {relative_prefix(old): relative_prefix(new) for old, new in path_map.items()}
    if len(mapping) != len(path_map):
        raise ValueError("ambiguous path map: multiple aliases identify one old path")
    if len(set(mapping.values())) != len(mapping):
        raise ValueError("ambiguous path map: multiple old paths map to one destination")
    if ledger.get("scope", ".").rstrip("/") != ".":
        raise ValueError("input ledger must use repository-root identities")
    moved = copy.deepcopy(ledger)
    remainder = copy.deepcopy(ledger)
    moved["scope"] = scope
    moved["baseline"]["findings"] = []
    moved["dispositions"] = []
    changes: dict[str, dict] = {}
    for old_path, new_path in mapping.items():
        source = scope_root / new_path
        if source.suffix not in NATIVE_SOURCE_EXTENSIONS or not is_local_file(scope_root, Path(new_path)):
            raise ValueError(f"mapped destination is not a scope-local native source: {new_path}")
        old_findings = scan_source_for_apis(scope_root, source, True, identity_path=old_path)
        new_findings = scan_source_for_apis(scope_root, source, True)
        pairs = {old.finding_id: (old, new) for old, new in zip(old_findings, new_findings, strict=True)}
        entries = [entry for entry in ledger["baseline"]["findings"] if entry["path"] == old_path]
        dispositions = [entry for entry in ledger["dispositions"] if entry["path"] == old_path]
        if not entries and not dispositions:
            raise ValueError(f"mapped old path has no retained history: {old_path}")
        for collection, destination in ((entries, moved["baseline"]["findings"]), (dispositions, moved["dispositions"])):
            for entry in collection:
                pair = pairs.get(entry["finding_id"])
                if pair is None:
                    raise ValueError(f"no exact current source match for {entry['finding_id']}")
                old, new = pair
                if old.source_fingerprint != entry["source_fingerprint"] or old.symbol != entry["symbol"]:
                    raise ValueError(f"source fingerprint changed for {entry['finding_id']}")
                updated = copy.deepcopy(entry)
                updated.update(finding_id=new.finding_id, source_fingerprint=new.source_fingerprint,
                               path=new.path, line=new.line, symbol=new.symbol)
                destination.append(updated)
                changes[entry["finding_id"]] = {
                    "old_finding_id": entry["finding_id"], "new_finding_id": new.finding_id,
                    "old_path": old_path, "new_path": new_path,
                    "old_source_fingerprint": entry["source_fingerprint"],
                    "new_source_fingerprint": new.source_fingerprint,
                }
    for key, container in (("findings", "baseline"), ("dispositions", None)):
        before = ledger[container][key] if container else ledger[key]
        remaining = [entry for entry in before if entry["path"] not in mapping]
        if container:
            remainder[container][key] = remaining
            after = moved[container][key]
        else:
            remainder[key] = remaining
            after = moved[key]
        if len(before) != len(remaining) + len(after):
            raise ValueError(f"history conservation failed for {key}")
        ids = [entry["finding_id"] for entry in after]
        if len(ids) != len(set(ids)):
            raise ValueError("ambiguous rekey: duplicate destination finding IDs")
    report = {"schema_version": "1.0.0", "scope": scope, "approvals_created": 0,
              "baseline_before": len(ledger["baseline"]["findings"]),
              "baseline_moved": len(moved["baseline"]["findings"]),
              "baseline_remaining": len(remainder["baseline"]["findings"]),
              "dispositions_before": len(ledger["dispositions"]),
              "dispositions_moved": len(moved["dispositions"]),
              "dispositions_remaining": len(remainder["dispositions"]),
              "identities": sorted(changes.values(), key=lambda item: item["old_finding_id"])}
    return moved, remainder, report


def unique_json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repository_root", type=Path)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--new-scope", required=True)
    parser.add_argument("--path-map", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    args = parser.parse_args()
    try:
        root = args.repository_root.resolve()
        if args.ledger.resolve() != (root / DEFAULT_REVIEW_DISPOSITIONS_PATH).resolve():
            raise ValueError("input ledger must be the repository-root ledger")
        raw = json.loads(args.ledger.read_text())
        load_review_disposition_ledger(root, raw["repository"])
        result = rekey(raw, root, args.new_scope, json.loads(args.path_map.read_text(), object_pairs_hook=unique_json_object))
        output = args.output_directory.resolve()
        names = ("scope-ledger.json", "remainder-ledger.json", "rekey-report.json")
        if any((output / name).exists() for name in names):
            raise ValueError("refusing to overwrite an existing output; choose a new directory")
        output.mkdir(parents=True, exist_ok=True)
        for name, document in zip(names, result, strict=True):
            with (output / name).open("x", encoding="utf-8") as handle:
                handle.write(json.dumps(document, indent=2) + "\n")
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
