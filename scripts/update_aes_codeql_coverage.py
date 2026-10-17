#!/usr/bin/env python3
"""Regenerate non-normative CodeQL coverage from an exact local AES Git revision."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
AES_REVISION = "256bf6dd0e424b134d4f1c628f9aff30ea12566d"
STANDARD_PATHS = {
    "AES-SEC-001": "standards/AES-SEC-001-secure-c-cpp-coding-rules.md",
    "AES-SEC-002": "standards/AES-SEC-002-cross-language-secret-storage-boundaries.md",
}
MODAL = re.compile(r"\b(MUST|SHOULD|MAY|BANNED)\b")


def clauses(text: str):
    """Include normative paragraphs and list items inheriting a modal introduction."""
    lines = text.splitlines()
    section, inherited, fenced, index = "Purpose", False, False, 0
    while index < len(lines):
        line = lines[index]
        if line.startswith("```"):
            fenced = not fenced
            index += 1
            continue
        if fenced or not line.strip():
            index += 1
            continue
        if line.startswith("#"):
            section, inherited = line.lstrip("# ").strip(), False
            index += 1
            continue
        start = index
        bullet = bool(re.match(r"(?:- |\d+\. )", line))
        parts = [line]
        index += 1
        while (index < len(lines) and lines[index].strip()
               and not lines[index].startswith(("#", "```", "- "))
               and not re.match(r"\d+\. ", lines[index])):
            parts.append(lines[index])
            index += 1
        paragraph = " ".join(part.strip() for part in parts)
        explicit = MODAL.search(paragraph)
        if not bullet:
            inherited = bool(explicit) and paragraph.endswith(":")
        if explicit or bullet and inherited:
            yield {"section": section, "source_lines": [start + 1, index],
                   "text": paragraph, "level": explicit.group(1) if explicit else "inherited"}


def support(standard: str, section: str, text: str) -> list[str]:
    """Associate narrowly relevant detectors; all coverage remains partial."""
    result = set()
    lower = text.lower()
    if standard == "AES-SEC-001":
        if section == "Banned Interfaces":
            if "following interfaces" in lower:
                result.update(("aes/cpp/banned-interface", "aes/cpp/unbounded-scanf-string"))
            if "dangerous primitive" in lower:
                result.add("aes/cpp/review-required-primitive")
        if "strncpy" in lower or section == "C++ Ownership and Lifetime Rules" and any(word in lower for word in ("new", "delete", "raw owning")):
            result.add("aes/cpp/review-required-primitive")
        if "truncation" in lower:
            result.add("aes/cpp/discarded-snprintf-result")
        if "shell execution" in lower:
            result.add("aes/cpp/banned-interface")
    else:
        if section == "ABI and Ownership Boundary" and "callback" in lower:
            result.add("aes/cpp/native-thread-dispatch-review")
        if "unsafepointer" in lower or "unsafemutablepointer" in lower:
            result.add("aes/swift/unsafe-pointer-lifecycle")
        if "overwriting a borrowed" in lower:
            result.add("aes/cpp/borrowed-const-buffer-write")
        if "keys must cross apis" in lower:
            result.add("aes/cpp/key-buffer-contract")
        if "every mutable project-owned c" in lower:
            result.update(("aes/cpp/candidate-secret-memset", "aes/cpp/borrowed-const-buffer-write"))
        if section == "Encrypted Storage" and any(word in lower for word in ("temporary database", "temporary-storage")):
            result.add("aes/cpp/sqlite-disk-temp-storage")
    return sorted(result)


def build_catalog(aes_repository: Path, revision: str) -> dict:
    sources, requirements, queries = [], [], []
    for standard, path in STANDARD_PATHS.items():
        raw = subprocess.run(["git", "-C", str(aes_repository), "show", f"{revision}:{path}"],
                             check=True, capture_output=True, timeout=30).stdout
        sources.append({"id": standard, "repository": "dlworrell/AES", "revision": revision,
                        "path": path, "sha256": hashlib.sha256(raw).hexdigest()})
        for clause in clauses(raw.decode("utf-8")):
            start, end = clause["source_lines"]
            qids = support(standard, clause["section"], clause["text"])
            requirements.append({**clause, "locator": f"{standard}:L{start}-L{end}",
                "standard": standard,
                "source_url": f"https://github.com/dlworrell/AES/blob/{revision}/{path}#L{start}-L{end}",
                "codeql_coverage": "partial" if qids else "complementary-evidence-required",
                "query_ids": qids,
                "complementary_evidence": [
                    "Run existing AES adoption/boundary scanners and inspect their actual findings.",
                    "Review this exact clause and supply applicable tests, compiler/build/artifact results, threat-model or waiver evidence. Query success does not discharge this clause."]})
    for language in ("cpp", "swift"):
        for path in sorted((ROOT / "codeql" / language / "queries").glob("*.ql")):
            source = path.read_text()
            queries.append({"id": re.search(r"@id\s+(\S+)", source)[1], "language": language,
                            "path": path.relative_to(ROOT).as_posix(),
                            "standard": re.search(r"aes-sec-00[12]", source)[0].upper(),
                            "enforcement": "report-only",
                            "confidence": re.search(r"@precision\s+(\S+)", source)[1]})
    return {"schema": "aems.codeql-controls.v1", "status": "implementation-proposal-reporting-only",
        "standard_compliance_proven": False, "sources": sources, "queries": queries,
        "limitations": [
            "All custom clause coverage is partial. Unmapped clauses remain explicit complementary-evidence obligations.",
            "Profiles, waiver authority, governed scopes, ownership, runtime behavior, secret erasure, dependency provenance, artifact hardening and history-migration authorization require complementary evidence.",
            "Name-identified secret candidates are heuristics; differently named or unlabeled secrets can be missed.",
            "Indirect calls, cross-language flows, dynamic SQL and whole-program lifetime proofs are incomplete.",
            "Default vendor/build and synthetic-fixture exclusions require ownership review; a repository's authoritative manifest and existing scope/adoption gates remain applicable.",
            "CodeQL completion or zero findings never establishes AES-SEC-001/002 compliance."
        ], "requirements": requirements}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aes-repository", type=Path, required=True)
    parser.add_argument("--aes-revision", default=AES_REVISION)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if not re.fullmatch(r"[a-fA-F0-9]{40}", args.aes_revision):
        parser.error("--aes-revision must be a complete commit SHA")
    catalog = build_catalog(args.aes_repository, args.aes_revision)
    output = ROOT / "config/aes-codeql-controls.json"
    text = json.dumps(catalog, indent=2) + "\n"
    if args.check:
        if output.read_text() != text:
            parser.error("coverage catalog differs from the pinned AES sources or current queries")
    else:
        output.write_text(text)
    print(f"{len(catalog['requirements'])} source-pinned clauses; {len(catalog['queries'])} custom queries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
