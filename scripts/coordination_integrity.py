#!/usr/bin/env python3
"""Offline integrity manifest and check for coordination records.

Pilot agreed between Em and Claude Code and approved by the owner on
31 October 2026. ``build`` writes a deterministic sha256 manifest of a records
directory, chained to the previous manifest. ``verify`` checks a directory
against a manifest and reports ``verified``, ``unverified`` or ``rejected``.

Matching hashes show only that the files equal what the manifest lists. They
do not show who wrote the records, that anyone authorized them, or that the
data and its manifest were not replaced together. The result is ``verified``
only when the manifest's digest matches an anchor kept somewhere the records'
writers cannot change (``--anchor``) and its chain predecessor was checked
(``--expected-predecessor``); otherwise it is at most ``unverified``. A matching
anchor does not show the manifest is the latest one. Integrity evidence is not
task status, engineering closure or owner approval.

The records directory itself must not be a symlink, in ``build`` and
``verify`` alike; directories above it may be, as system paths often are.
Record identity is the file's own top-level ``id`` field only; other ID fields
such as ``event_id`` are not read until the coordinator's schema is agreed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys

SCHEMA = "aems.coordination-manifest.v1"
REPORT_SCHEMA = "aems.coordination-integrity.v1"
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
LIMITS = ("Matching hashes do not establish authorship or authorization, and an "
          "unanchored manifest does not protect against replacement of both the "
          "records and the manifest.")
FRESHNESS = ("A matching anchor shows the records equal that manifest; it does not show "
             "the manifest is the latest one.")


class IntegrityError(ValueError):
    pass


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _record_id(data: bytes) -> str | None:
    """The record's own ``id`` when the file is a JSON object that has one."""
    try:
        value = json.loads(data)
    except (ValueError, UnicodeDecodeError):
        return None
    if isinstance(value, dict) and isinstance(value.get("id"), (str, int)):
        return str(value["id"])
    return None


def manifest_digest(manifest: dict) -> str:
    """Canonical digest of a manifest: what an anchor or a successor records."""
    return _sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode())


def _safe_path(value: object) -> bool:
    if not isinstance(value, str) or not value or "\\" in value:
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and ".." not in path.parts and str(path) == value


def scan(root: Path) -> tuple[dict[str, dict], list[str]]:
    """Every regular file under ``root``; symlinks and other types are problems."""
    files, problems = {}, []
    if not root.is_dir() or root.is_symlink():
        raise IntegrityError(f"{root} is not a directory")
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            problems.append(f"symlink not allowed: {relative}")
        elif path.is_file():
            data = path.read_bytes()
            files[relative] = {"path": relative, "sha256": _sha256(data),
                               "size": len(data), "record_id": _record_id(data)}
        elif not path.is_dir():
            problems.append(f"not a regular file: {relative}")
    return files, problems


def build(root: Path, predecessor: dict | None = None) -> dict:
    files, problems = scan(root)
    if problems:
        raise IntegrityError("; ".join(problems))
    empty = sorted(path for path, entry in files.items() if entry["record_id"] == "")
    if empty:
        raise IntegrityError(f"empty record id: {', '.join(empty)}")
    ids = [entry["record_id"] for entry in files.values() if entry["record_id"]]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        raise IntegrityError(f"duplicate record ids: {', '.join(duplicates)}")
    return {"schema": SCHEMA,
            "predecessor_sha256": manifest_digest(predecessor) if predecessor else None,
            "files": [files[path] for path in sorted(files)]}


def _manifest_problems(manifest: dict) -> list[str]:
    if not isinstance(manifest, dict) or manifest.get("schema") != SCHEMA:
        return [f"manifest schema is not {SCHEMA}"]
    problems = []
    predecessor = manifest.get("predecessor_sha256")
    if predecessor is not None and not (isinstance(predecessor, str) and SHA256.match(predecessor)):
        problems.append("predecessor_sha256 is not a sha256 digest")
    entries = manifest.get("files")
    if not isinstance(entries, list):
        return problems + ["files is not a list"]
    paths, ids = [], []
    for entry in entries:
        if not isinstance(entry, dict) or not _safe_path(entry.get("path")):
            problems.append(f"unsafe or malformed path: {entry.get('path') if isinstance(entry, dict) else entry!r}")
            continue
        if not (isinstance(entry.get("sha256"), str) and SHA256.match(entry["sha256"])):
            problems.append(f"malformed sha256: {entry['path']}")
        size, record_id = entry.get("size"), entry.get("record_id")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            problems.append(f"malformed size: {entry['path']}")
        if record_id is not None and not (isinstance(record_id, str) and record_id):
            problems.append(f"malformed record_id: {entry['path']}")
        paths.append(entry["path"])
        if isinstance(record_id, str) and record_id:
            ids.append(record_id)
    problems += [f"duplicate path: {p}" for p in sorted({p for p in paths if paths.count(p) > 1})]
    problems += [f"duplicate record id: {i}" for i in sorted({i for i in ids if ids.count(i) > 1})]
    return problems


def verify(root: Path, manifest: dict, expected_predecessor: str | None = None,
           anchor: str | None = None) -> dict:
    """Check ``root`` against ``manifest``.

    ``expected_predecessor`` is the digest of the manifest this one must follow
    (``"genesis"`` for the first). ``anchor`` is the trusted digest of this
    manifest, read from somewhere outside the records' control.
    """
    problems = _manifest_problems(manifest)
    digest = manifest_digest(manifest) if isinstance(manifest, dict) else None
    try:
        actual, scan_problems = scan(root)
    except IntegrityError as error:
        actual, scan_problems = {}, [str(error)]
    problems += scan_problems
    if not problems:
        listed = {entry["path"]: entry for entry in manifest["files"]}
        problems += [f"missing: {p}" for p in sorted(set(listed) - set(actual))]
        problems += [f"extra: {p}" for p in sorted(set(actual) - set(listed))]
        for path in sorted(set(listed) & set(actual)):
            if listed[path]["sha256"] != actual[path]["sha256"] or listed[path].get("size") != actual[path]["size"]:
                problems.append(f"changed: {path}")
            elif listed[path].get("record_id") != actual[path]["record_id"]:
                problems.append(f"record id does not match the file: {path}")
        problems += [f"empty record id: {p}" for p in sorted(actual) if actual[p]["record_id"] == ""]
        ids = [entry["record_id"] for entry in actual.values() if entry["record_id"]]
        problems += [f"duplicate record id on disk: {i}" for i in sorted({i for i in ids if ids.count(i) > 1})]
    chain_checked = expected_predecessor is not None
    if chain_checked and isinstance(manifest, dict):
        want = None if expected_predecessor == "genesis" else expected_predecessor
        if manifest.get("predecessor_sha256") != want:
            problems.append("predecessor does not match the expected previous manifest")
    if anchor is not None and digest != anchor:
        problems.append("manifest digest does not match the trusted anchor")
    # "verified" needs both a trusted anchor and a checked chain predecessor.
    if problems:
        status = "rejected"
    elif anchor is None or not chain_checked:
        status = "unverified"
    else:
        status = "verified"
    notes = []
    if anchor is None:
        notes.append("No trusted anchor was given, so the manifest itself is not trusted.")
    if not chain_checked:
        notes.append("No expected predecessor was given, so the manifest's place in the chain was not checked.")
    notes += [FRESHNESS, LIMITS]
    return {"schema": REPORT_SCHEMA, "status": status, "manifest_sha256": digest,
            "anchor_checked": anchor is not None, "chain_checked": chain_checked,
            "files": len(actual), "problems": problems, "notes": notes}


def _load(path: str | None) -> dict | None:
    if path is None:
        return None
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise IntegrityError(f"cannot read {path}: {error}") from error


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    make = commands.add_parser("build", help="write a manifest for a records directory")
    make.add_argument("root")
    make.add_argument("--predecessor", help="the previous manifest file, if any")
    make.add_argument("--output", required=True, help="manifest file to write (outside root)")
    check = commands.add_parser("verify", help="check a records directory against a manifest")
    check.add_argument("root")
    check.add_argument("--manifest", required=True)
    check.add_argument("--expected-predecessor",
                       help="sha256 of the previous manifest, or 'genesis' for the first")
    check.add_argument("--anchor", help="trusted sha256 of this manifest")
    check.add_argument("--format", choices=("json", "markdown"), default="json")
    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            given = Path(args.root)
            if given.is_symlink():
                raise IntegrityError(f"{given} is not a directory")
            root, output = given.resolve(), Path(args.output).resolve()
            if output == root or root in output.parents:
                raise IntegrityError("the manifest must be written outside the records directory")
            manifest = build(given, _load(args.predecessor))
            output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            print(manifest_digest(manifest))
            return 0
        report = verify(Path(args.root), _load(args.manifest),
                        args.expected_predecessor, args.anchor)
    except IntegrityError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.format == "markdown":
        lines = [f"# Coordination record integrity: {report['status']}", "",
                 f"- Manifest sha256: `{report['manifest_sha256']}`",
                 f"- Files checked: {report['files']}", ""]
        lines += [f"- Problem: {p}" for p in report["problems"]]
        lines += [""] + [f"> {n}" for n in report["notes"]]
        print("\n".join(lines))
    else:
        print(json.dumps(report, indent=2, sort_keys=True))
    return {"verified": 0, "unverified": 1, "rejected": 3}[report["status"]]


if __name__ == "__main__":
    sys.exit(main())
