#!/usr/bin/env python3
"""Scan one checkout for AES-DEV-001 development-principles evidence.

This scanner intentionally reports evidence before enforcing hard gates. AES-DEV-001
covers development process, architecture governance, documentation-first discipline,
observability, recovery, trust boundaries, authority models, ADRs, and check-in
behavior. These are architectural signals, not simple compiler errors.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

STANDARD = "AES-DEV-001"

EXCLUDED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".idea",
    ".vscode",
    "node_modules",
    "vendor",
    "third_party",
    "third-party",
    "external",
    "build",
    "dist",
    "out",
    "target",
    "DerivedData",
    "__pycache__",
}

DOC_EXTENSIONS = {".md", ".markdown", ".rst", ".txt", ".adoc"}

LOCAL_PROFILE_PATHS = (
    Path("docs/engineering/AES-DEV-001-development-principles.md"),
    Path("docs/engineering/DEVELOPMENT.md"),
    Path("docs/engineering/DEVELOPMENT-PRINCIPLES.md"),
    Path("docs/engineering/PROJECT-DEVELOPMENT.md"),
    Path("docs/engineering/ATARIX-DEV-001-development-principles.md"),
)

SPEC_DIRS = (
    Path("docs/specs"),
    Path("docs/spec"),
    Path("docs/architecture"),
    Path("docs/design"),
    Path("docs/protocols"),
    Path("docs/interfaces"),
    Path("specs"),
    Path("spec"),
    Path("architecture"),
)

ADR_DIRS = (
    Path("docs/adr"),
    Path("docs/adrs"),
    Path("docs/architecture/adr"),
    Path("adr"),
    Path("adrs"),
    Path("decisions"),
)

EVIDENCE_PATTERNS: dict[str, list[re.Pattern[str]]] = {
    "versioning": [
        re.compile(r"\bv[0-9]+\b", re.IGNORECASE),
        re.compile(r"\bversion(?:ed|ing)?\b", re.IGNORECASE),
        re.compile(r"\b(schema|format|protocol|interface) version\b", re.IGNORECASE),
        re.compile(r"\bdeprecated\b", re.IGNORECASE),
        re.compile(r"\bcompatib(?:le|ility)\b", re.IGNORECASE),
    ],
    "observability": [
        re.compile(r"\bstatus\b", re.IGNORECASE),
        re.compile(r"\bcounters?\b", re.IGNORECASE),
        re.compile(r"\bmetrics?\b", re.IGNORECASE),
        re.compile(r"\bhealth\b", re.IGNORECASE),
        re.compile(r"\bfault history\b", re.IGNORECASE),
        re.compile(r"\bdiagnostics?\b", re.IGNORECASE),
        re.compile(r"\btelemetry\b", re.IGNORECASE),
        re.compile(r"\btrace\b", re.IGNORECASE),
        re.compile(r"\bdebug(?:ging|gability)?\b", re.IGNORECASE),
    ],
    "recovery": [
        re.compile(r"\bfailure modes?\b", re.IGNORECASE),
        re.compile(r"\brecover(?:y|able|ing)?\b", re.IGNORECASE),
        re.compile(r"\breset behavior\b", re.IGNORECASE),
        re.compile(r"\bfault handling\b", re.IGNORECASE),
        re.compile(r"\bdegraded\b", re.IGNORECASE),
        re.compile(r"\brestart\b", re.IGNORECASE),
        re.compile(r"\bfail visibly\b", re.IGNORECASE),
    ],
    "security_authority": [
        re.compile(r"\btrust boundaries?\b", re.IGNORECASE),
        re.compile(r"\bleast privilege\b", re.IGNORECASE),
        re.compile(r"\bprivilege separation\b", re.IGNORECASE),
        re.compile(r"\bcapabilit(?:y|ies)\b", re.IGNORECASE),
        re.compile(r"\bauthorit(?:y|ies)\b", re.IGNORECASE),
        re.compile(r"\bcredential\b", re.IGNORECASE),
        re.compile(r"\bauthentication\b", re.IGNORECASE),
        re.compile(r"\bauthorization\b", re.IGNORECASE),
        re.compile(r"\brevocation\b", re.IGNORECASE),
        re.compile(r"\bsandbox\b", re.IGNORECASE),
        re.compile(r"\brings?\b", re.IGNORECASE),
    ],
    "check_in_discipline": [
        re.compile(r"\bsmall commits?\b", re.IGNORECASE),
        re.compile(r"\bsmall pull requests?\b", re.IGNORECASE),
        re.compile(r"\bcode review\b", re.IGNORECASE),
        re.compile(r"\breview(?:able|s)?\b", re.IGNORECASE),
        re.compile(r"\bgit bisect\b", re.IGNORECASE),
        re.compile(r"\btest rationale\b", re.IGNORECASE),
        re.compile(r"\bcommit subject\b", re.IGNORECASE),
        re.compile(r"\barea prefix\b", re.IGNORECASE),
    ],
}


@dataclass
class EvidenceHit:
    path: str
    line: int
    text: str

    def to_dict(self) -> dict[str, Any]:
        return {"path": self.path, "line": self.line, "text": self.text}


@dataclass
class EvidenceCategory:
    name: str
    present: bool = False
    count: int = 0
    hits: list[EvidenceHit] = field(default_factory=list)

    def add_hit(self, hit: EvidenceHit, max_hits: int) -> None:
        self.present = True
        self.count += 1
        if len(self.hits) < max_hits:
            self.hits.append(hit)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "present": self.present,
            "count": self.count,
            "hits": [hit.to_dict() for hit in self.hits],
        }


@dataclass
class Dev001Report:
    repo_name: str
    root: str
    local_profiles: list[str]
    spec_directories: list[str]
    adr_directories: list[str]
    doc_file_count: int
    evidence: dict[str, EvidenceCategory]

    @property
    def local_profile_present(self) -> bool:
        return bool(self.local_profiles)

    @property
    def specs_present(self) -> bool:
        return bool(self.spec_directories)

    @property
    def adrs_present(self) -> bool:
        return bool(self.adr_directories)

    @property
    def evidence_present_count(self) -> int:
        return sum(1 for category in self.evidence.values() if category.present)

    @property
    def evidence_category_count(self) -> int:
        return len(self.evidence)

    @property
    def ready_for_ratchet(self) -> bool:
        return self.local_profile_present or self.specs_present or self.adrs_present or self.evidence_present_count > 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "standard": STANDARD,
            "repo_name": self.repo_name,
            "root": self.root,
            "summary": {
                "local_profile_present": self.local_profile_present,
                "specs_present": self.specs_present,
                "adrs_present": self.adrs_present,
                "doc_file_count": self.doc_file_count,
                "evidence_present_count": self.evidence_present_count,
                "evidence_category_count": self.evidence_category_count,
                "ready_for_ratchet": self.ready_for_ratchet,
            },
            "local_profiles": self.local_profiles,
            "spec_directories": self.spec_directories,
            "adr_directories": self.adr_directories,
            "evidence": {name: category.to_dict() for name, category in self.evidence.items()},
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scan one checkout for AES-DEV-001 evidence.")
    parser.add_argument("root", nargs="?", default=".", help="Repository checkout root. Defaults to current directory.")
    parser.add_argument("--repo-name", default="unknown", help="Repository name for reports.")
    parser.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="markdown",
        help="Report format. Defaults to markdown.",
    )
    parser.add_argument(
        "--max-hits",
        type=int,
        default=8,
        help="Maximum sample hits per evidence category. Defaults to 8.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero when no AES-DEV-001 evidence is found. Intended for future ratcheting only.",
    )
    return parser.parse_args()


def is_excluded(path: Path) -> bool:
    return any(part in EXCLUDED_DIRS for part in path.parts)


def relative_existing_dirs(root: Path, candidates: tuple[Path, ...]) -> list[str]:
    existing = []
    for candidate in candidates:
        full_path = root / candidate
        if full_path.is_dir():
            existing.append(candidate.as_posix())
    return existing


def relative_existing_files(root: Path, candidates: tuple[Path, ...]) -> list[str]:
    existing = []
    for candidate in candidates:
        full_path = root / candidate
        if full_path.is_file():
            existing.append(candidate.as_posix())
    return existing


def iter_doc_files(root: Path) -> list[Path]:
    docs = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if is_excluded(rel):
            continue
        if path.suffix.lower() in DOC_EXTENSIONS:
            docs.append(path)
    return sorted(docs)


def scan_text_file(root: Path, path: Path, categories: dict[str, EvidenceCategory], max_hits: int) -> None:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return

    rel = path.relative_to(root).as_posix()
    for line_number, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped:
            continue
        for category_name, patterns in EVIDENCE_PATTERNS.items():
            if any(pattern.search(stripped) for pattern in patterns):
                categories[category_name].add_hit(
                    EvidenceHit(path=rel, line=line_number, text=stripped[:180]),
                    max_hits=max_hits,
                )


def scan(root: Path, repo_name: str, max_hits: int = 8) -> Dev001Report:
    root = root.resolve()
    categories = {name: EvidenceCategory(name=name) for name in EVIDENCE_PATTERNS}
    local_profiles = relative_existing_files(root, LOCAL_PROFILE_PATHS)
    spec_directories = relative_existing_dirs(root, SPEC_DIRS)
    adr_directories = relative_existing_dirs(root, ADR_DIRS)
    doc_files = iter_doc_files(root)

    for doc_file in doc_files:
        scan_text_file(root, doc_file, categories, max_hits=max_hits)

    return Dev001Report(
        repo_name=repo_name,
        root=str(root),
        local_profiles=local_profiles,
        spec_directories=spec_directories,
        adr_directories=adr_directories,
        doc_file_count=len(doc_files),
        evidence=categories,
    )


def format_bool(value: bool) -> str:
    return "True" if value else "False"


def format_markdown(report: Dev001Report) -> str:
    data = report.to_dict()
    summary = data["summary"]
    lines = [
        f"# AES-DEV-001 Scan Report: `{report.repo_name}`",
        "",
        f"- Standard: `{STANDARD}`",
        f"- Local profile present: `{format_bool(report.local_profile_present)}`",
        f"- Specification directories present: `{format_bool(report.specs_present)}`",
        f"- ADR directories present: `{format_bool(report.adrs_present)}`",
        f"- Documentation files scanned: `{summary['doc_file_count']}`",
        f"- Evidence categories present: `{summary['evidence_present_count']}` / `{summary['evidence_category_count']}`",
        f"- Ready for ratchet: `{format_bool(report.ready_for_ratchet)}`",
        "",
        "## Structural Evidence",
        "",
        f"- Local profiles: {', '.join(f'`{p}`' for p in report.local_profiles) if report.local_profiles else 'none found'}",
        f"- Specification directories: {', '.join(f'`{p}`' for p in report.spec_directories) if report.spec_directories else 'none found'}",
        f"- ADR directories: {', '.join(f'`{p}`' for p in report.adr_directories) if report.adr_directories else 'none found'}",
        "",
        "## Evidence Categories",
        "",
        "| Category | Present | Hits |",
        "|---|---:|---:|",
    ]

    for category in report.evidence.values():
        lines.append(f"| `{category.name}` | `{format_bool(category.present)}` | `{category.count}` |")

    for category in report.evidence.values():
        if not category.hits:
            continue
        lines.extend(["", f"### {category.name}", ""])
        for hit in category.hits:
            safe_text = hit.text.replace("`", "'")
            lines.append(f"- `{hit.path}:{hit.line}` — {safe_text}")

    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    report = scan(Path(args.root), args.repo_name, max_hits=args.max_hits)

    if args.format == "json":
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    else:
        print(format_markdown(report))

    if args.strict and not report.ready_for_ratchet:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
