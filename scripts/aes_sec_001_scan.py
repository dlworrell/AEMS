#!/usr/bin/env python3
"""AES-SEC-001 repository scanner.

This script is the first AEMS enforcement mechanism for
`AES-SEC-001: Secure C and C++ Coding Rules`.

It performs a local checkout scan and reports:

- whether a repository has adopted the local secure-coding profile;
- whether native-code files are present;
- whether native build/test/tooling surfaces are present;
- whether banned C/C++ APIs appear in project-owned source files;
- whether real static-analysis, sanitizer, fuzzing, or waiver evidence exists.

The scanner is intentionally dependency-free. It should run anywhere a
standard Python 3 interpreter is available.
"""

from __future__ import annotations

import argparse
import bisect
import hashlib
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Iterable

SECURE_PROFILE_PATH = Path("docs/engineering/SECURE-C-CXX.md")
DEFAULT_WAIVER_PATH = Path("docs/engineering/AES-SEC-001-waivers.md")
DEFAULT_REVIEW_DISPOSITIONS_PATH = Path(
    "docs/engineering/AES-SEC-001-review-dispositions.json"
)
REVIEW_DISPOSITION_SCHEMA_VERSION = "1.0.0"
REVIEW_DISPOSITION_CLASSES = {
    "approved-invariant",
    "wrapper-required",
    "replacement-planned",
    "fix-required",
    "resolved",
}

NATIVE_SOURCE_EXTENSIONS = {
    ".c",
    ".cc",
    ".cpp",
    ".cxx",
    ".h",
    ".hh",
    ".hpp",
    ".hxx",
    ".m",
    ".mm",
    ".S",
    ".s",
    ".asm",
    ".inc",
}

HARDWARE_SOURCE_EXTENSIONS = {
    ".v",
    ".sv",
    ".svh",
    ".vhd",
    ".vhdl",
    ".xdc",
    ".pcf",
    ".qsf",
}

BUILD_SURFACE_NAMES = {
    "Makefile",
    "makefile",
    "GNUmakefile",
    "CMakeLists.txt",
    "meson.build",
    "configure.ac",
    "configure.in",
}

BUILD_SURFACE_EXTENSIONS = {
    ".mk",
    ".cmake",
}

WORKFLOW_EXTENSIONS = {
    ".yml",
    ".yaml",
}

SCRIPT_EXTENSIONS = {
    ".sh",
    ".bash",
    ".zsh",
    ".py",
    ".pl",
    ".rb",
}

BANNED_APIS = {
    "gets",
    "strcpy",
    "strcat",
    "sprintf",
    "vsprintf",
    "atoi",
    "atol",
    "atoll",
    "tmpnam",
    "mktemp",
    "system",
    "popen",
}

DANGEROUS_PRIMITIVES = {
    "memcpy",
    "memmove",
    "memset",
    "strncpy",
    "strncat",
    "snprintf",
    "malloc",
    "calloc",
    "realloc",
    "free",
}

API_REMEDIATIONS = {
    "gets": "Use fgets with the destination capacity and validate truncation.",
    "strcpy": (
        "Use an explicit-length copy, a reviewed bounded wrapper, or strlcpy "
        "where that non-standard interface is available."
    ),
    "strcat": (
        "Track remaining capacity explicitly and use a reviewed bounded append "
        "wrapper or strlcat where available."
    ),
    "sprintf": "Use snprintf and check its return value for truncation.",
    "vsprintf": "Use vsnprintf and check its return value for truncation.",
    "atoi": "Use strtol or strtoul with end-pointer, range, and error checks.",
    "atol": "Use strtol with end-pointer, range, and error checks.",
    "atoll": "Use strtoll with end-pointer, range, and error checks.",
    "tmpnam": "Use a race-safe temporary-file API such as mkstemp.",
    "mktemp": "Use mkstemp or an equivalent race-safe temporary-file API.",
    "system": "Use an argument-vector process API and reject untrusted commands.",
    "popen": "Use an argument-vector process API with explicit pipe ownership.",
    "memcpy": "Use only after proving source, destination, and byte-count bounds.",
    "memmove": "Use only after proving source, destination, and byte-count bounds.",
    "memset": (
        "For ordinary initialization, prove the destination bound. For secret "
        "erasure, use explicit_bzero, memset_s where supported, or an approved "
        "non-optimizable wrapper."
    ),
    "strncpy": (
        "Do not treat strncpy as a safe string copy; use explicit bounds and "
        "termination, memcpy for fixed-size data, or a reviewed wrapper."
    ),
    "strncat": (
        "Track the destination capacity and current length explicitly; use a "
        "reviewed bounded append wrapper or strlcat where available."
    ),
    "snprintf": "Check the return value and handle truncation explicitly.",
    "malloc": "Check size arithmetic and the allocation result before use.",
    "calloc": "Check element-count arithmetic and the allocation result before use.",
    "realloc": "Use a temporary pointer and preserve the original allocation on failure.",
    "free": "Centralize ownership and prevent double-free or use-after-free paths.",
}

DEFAULT_EXCLUDED_DIRS = {
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

DEFAULT_EXCLUDED_PATH_PREFIXES = {
    "examples/fixtures",
    "tests/fixtures",
}

GENERATED_REPORT_NAMES = {
    "aes-sec-001-scan.json",
    "aes-sec-001-scan.md",
}

TEXT_FILE_LIMIT_BYTES = 2_000_000


@dataclass(frozen=True)
class ApiFinding:
    path: str
    line: int
    symbol: str
    severity: str
    text: str
    remediation: str
    finding_id: str
    source_fingerprint: str
    disposition_status: str | None = None
    disposition_classification: str | None = None


@dataclass(frozen=True)
class ReviewLedgerFinding:
    finding_id: str
    source_fingerprint: str
    path: str
    line: int
    symbol: str


@dataclass(frozen=True)
class ReviewDisposition:
    finding_id: str
    source_fingerprint: str
    path: str
    line: int
    symbol: str
    classification: str


@dataclass
class ReviewDispositionLedger:
    path: str
    present: bool
    schema_version: str | None = None
    repository: str | None = None
    baseline: dict[str, ReviewLedgerFinding] = field(default_factory=dict)
    dispositions: dict[str, ReviewDisposition] = field(default_factory=dict)


@dataclass(frozen=True)
class ReviewDispositionSummary:
    path: str
    present: bool
    evaluated: bool
    schema_version: str | None
    baseline_count: int
    disposition_count: int
    total: int
    reviewed: int
    unresolved: int
    new: int
    source_drifted: int
    stale: int

    @property
    def passes_ratchet(self) -> bool:
        return not self.evaluated or (self.unresolved == 0 and self.stale == 0)

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "present": self.present,
            "evaluated": self.evaluated,
            "schema_version": self.schema_version,
            "baseline_count": self.baseline_count,
            "disposition_count": self.disposition_count,
            "total": self.total,
            "reviewed": self.reviewed,
            "unresolved": self.unresolved,
            "new": self.new,
            "source_drifted": self.source_drifted,
            "stale": self.stale,
            "passes_ratchet": self.passes_ratchet,
        }


@dataclass
class ScanReport:
    repository: str
    root: str
    classification: str
    secure_profile_present: bool
    waiver_log_present: bool
    native_files: list[str] = field(default_factory=list)
    hardware_files: list[str] = field(default_factory=list)
    build_surfaces: list[str] = field(default_factory=list)
    static_analysis_signals: list[str] = field(default_factory=list)
    sanitizer_signals: list[str] = field(default_factory=list)
    fuzz_signals: list[str] = field(default_factory=list)
    waiver_signals: list[str] = field(default_factory=list)
    findings: list[ApiFinding] = field(default_factory=list)
    review_dispositions: ReviewDispositionSummary | None = None

    @property
    def has_native_code(self) -> bool:
        return bool(self.native_files)

    @property
    def has_banned_api_findings(self) -> bool:
        return any(f.severity == "banned" for f in self.findings)

    @property
    def requires_secure_profile(self) -> bool:
        return self.has_native_code or bool(self.build_surfaces)

    @property
    def passes_minimum_adoption_gate(self) -> bool:
        return (
            self.secure_profile_present
            and self.waiver_log_present
            and not self.has_banned_api_findings
        )

    @property
    def passes_review_ratchet(self) -> bool:
        return (
            self.review_dispositions is None
            or self.review_dispositions.passes_ratchet
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "repository": self.repository,
            "root": self.root,
            "classification": self.classification,
            "secure_profile_present": self.secure_profile_present,
            "waiver_log_present": self.waiver_log_present,
            "native_file_count": len(self.native_files),
            "hardware_file_count": len(self.hardware_files),
            "build_surface_count": len(self.build_surfaces),
            "native_files": self.native_files,
            "hardware_files": self.hardware_files,
            "build_surfaces": self.build_surfaces,
            "static_analysis_signals": self.static_analysis_signals,
            "sanitizer_signals": self.sanitizer_signals,
            "fuzz_signals": self.fuzz_signals,
            "waiver_signals": self.waiver_signals,
            "findings": [finding.__dict__ for finding in self.findings],
            "review_dispositions": (
                self.review_dispositions.to_dict()
                if self.review_dispositions is not None
                else None
            ),
            "summary": {
                "has_native_code": self.has_native_code,
                "has_banned_api_findings": self.has_banned_api_findings,
                "requires_secure_profile": self.requires_secure_profile,
                "passes_minimum_adoption_gate": self.passes_minimum_adoption_gate,
                "passes_review_ratchet": self.passes_review_ratchet,
            },
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scan a repository for AES-SEC-001 adoption and banned native-code APIs."
    )
    parser.add_argument(
        "root",
        nargs="?",
        default=".",
        help="Repository checkout path to scan. Defaults to the current directory.",
    )
    parser.add_argument(
        "--repo-name",
        default=None,
        help="Repository name to record in the report, for example dlworrell/AEMS.",
    )
    parser.add_argument(
        "--format",
        choices=("json", "markdown", "github"),
        default="json",
        help="Report format. Defaults to json.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero when adoption is missing or banned APIs are found.",
    )
    parser.add_argument(
        "--include-dangerous-primitives",
        action="store_true",
        help="Also report dangerous primitives that require review but are not outright banned.",
    )
    parser.add_argument(
        "--strict-review-ratchet",
        action="store_true",
        help=(
            "Exit non-zero when review-required findings are new, unresolved, "
            "source-drifted, or have stale ledger entries. This is opt-in "
            "during baseline migration."
        ),
    )
    return parser.parse_args()


def iter_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        rel_parts = rel.parts
        if any(part in DEFAULT_EXCLUDED_DIRS for part in rel_parts[:-1]):
            continue
        rel_text = rel.as_posix()
        if any(
            rel_text == prefix or rel_text.startswith(f"{prefix}/")
            for prefix in DEFAULT_EXCLUDED_PATH_PREFIXES
        ):
            continue
        if rel.name in GENERATED_REPORT_NAMES:
            continue
        yield path


def is_build_surface(path: Path) -> bool:
    return path.name in BUILD_SURFACE_NAMES or path.suffix in BUILD_SURFACE_EXTENSIONS


def is_workflow_file(root: Path, path: Path) -> bool:
    rel = path.relative_to(root)
    parts = rel.parts
    return (
        len(parts) >= 3
        and parts[0] == ".github"
        and parts[1] == "workflows"
        and path.suffix in WORKFLOW_EXTENSIONS
    )


def is_documentation_file(root: Path, path: Path) -> bool:
    rel = path.relative_to(root).as_posix().lower()
    return rel.startswith("docs/") or rel.endswith(".md") or rel.endswith(".rst")


def is_scanner_itself(root: Path, path: Path) -> bool:
    return path.relative_to(root).as_posix() == "scripts/aes_sec_001_scan.py"


def is_operational_evidence_candidate(root: Path, path: Path) -> bool:
    if is_scanner_itself(root, path):
        return False
    if is_documentation_file(root, path):
        return False
    return (
        is_workflow_file(root, path)
        or is_build_surface(path)
        or path.suffix in BUILD_SURFACE_EXTENSIONS
        or path.suffix in SCRIPT_EXTENSIONS
    )


def is_probably_text(path: Path) -> bool:
    try:
        return path.stat().st_size <= TEXT_FILE_LIMIT_BYTES
    except OSError:
        return False


def read_text_lossy(path: Path) -> str | None:
    if not is_probably_text(path):
        return None
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def classify(native_files: list[str], hardware_files: list[str], build_surfaces: list[str]) -> str:
    if native_files:
        return "native-code-active"
    if hardware_files and build_surfaces:
        return "hardware-or-fpga-with-host-tooling"
    if hardware_files:
        return "hardware-or-fpga"
    if build_surfaces:
        return "native-code-planned-or-build-surface"
    return "documentation-or-governance"


def is_explicit_waiver_file(root: Path, path: Path) -> bool:
    rel = path.relative_to(root).as_posix()
    rel_lower = rel.lower()
    name_lower = path.name.lower()
    if rel == DEFAULT_WAIVER_PATH.as_posix():
        return True
    if rel_lower in {
        "docs/engineering/waivers.md",
        "docs/security/waivers.md",
        "security/waivers.md",
    }:
        return True
    if "/waivers/" in f"/{rel_lower}" and path.suffix.lower() in {".md", ".json", ".yml", ".yaml"}:
        return True
    return name_lower in {"waivers.md", "waivers.yml", "waivers.yaml", "waivers.json"}


def collect_signals(root: Path, files: list[Path]) -> tuple[list[str], list[str], list[str], list[str]]:
    static_analysis: set[str] = set()
    sanitizers: set[str] = set()
    fuzzing: set[str] = set()
    waivers: set[str] = set()

    for path in files:
        rel = path.relative_to(root).as_posix()
        name = path.name.lower()
        rel_lower = rel.lower()

        if is_explicit_waiver_file(root, path):
            waivers.add(rel)

        if name == ".clang-tidy" or rel_lower.startswith(".github/codeql/"):
            static_analysis.add(rel)

        text = read_text_lossy(path)
        if text is None:
            continue

        if is_operational_evidence_candidate(root, path):
            if any(token in text for token in ("clang-tidy", "cppcheck", "CodeQL", "coverity", "pvs-studio")):
                static_analysis.add(rel)
            if any(token in text for token in ("-fsanitize", "AddressSanitizer", "UndefinedBehaviorSanitizer", "ThreadSanitizer")):
                sanitizers.add(rel)
            if any(token in text for token in ("LLVMFuzzerTestOneInput", "libFuzzer", "AFL++", "honggfuzz")):
                fuzzing.add(rel)

        if path.suffix in NATIVE_SOURCE_EXTENSIONS:
            if "LLVMFuzzerTestOneInput" in text:
                fuzzing.add(rel)

        if "fuzz" in rel_lower and (
            path.suffix in NATIVE_SOURCE_EXTENSIONS
            or is_operational_evidence_candidate(root, path)
        ):
            fuzzing.add(rel)

    return sorted(static_analysis), sorted(sanitizers), sorted(fuzzing), sorted(waivers)


def line_has_banned_scan_exemption(line: str) -> bool:
    lowered = line.lower()
    return "aes-sec-001: allow" in lowered or "aes-sec-001 waiver" in lowered


def strip_c_comments_and_literals(text: str) -> str:
    """Replace comments and literals with spaces while preserving line numbers."""

    result: list[str] = []
    state = "code"
    index = 0

    while index < len(text):
        char = text[index]
        next_char = text[index + 1] if index + 1 < len(text) else ""

        if state == "code":
            if char == "/" and next_char == "/":
                result.extend((" ", " "))
                index += 2
                state = "line-comment"
                continue
            if char == "/" and next_char == "*":
                result.extend((" ", " "))
                index += 2
                state = "block-comment"
                continue
            if char == '"':
                result.append(" ")
                index += 1
                state = "string"
                continue
            if char == "'":
                result.append(" ")
                index += 1
                state = "character"
                continue
            result.append(char)
            index += 1
            continue

        if char == "\n":
            result.append("\n")
            index += 1
            if state == "line-comment":
                state = "code"
            continue

        if state == "line-comment":
            result.append(" ")
            index += 1
            continue

        if state == "block-comment":
            if char == "*" and next_char == "/":
                result.extend((" ", " "))
                index += 2
                state = "code"
            else:
                result.append(" ")
                index += 1
            continue

        if state in {"string", "character"}:
            terminator = '"' if state == "string" else "'"
            if char == "\\":
                result.append(" ")
                index += 1
                if index < len(text):
                    escaped = text[index]
                    result.append("\n" if escaped == "\n" else " ")
                    index += 1
                continue
            result.append(" ")
            index += 1
            if char == terminator:
                state = "code"
            continue

    return "".join(result)


def normalize_call_source(text: str) -> str:
    """Return a whitespace/comment-insensitive representation of one call."""

    result: list[str] = []
    state = "code"
    index = 0

    while index < len(text):
        char = text[index]
        next_char = text[index + 1] if index + 1 < len(text) else ""

        if state == "code":
            if char.isspace():
                index += 1
                continue
            if char == "/" and next_char == "/":
                index += 2
                state = "line-comment"
                continue
            if char == "/" and next_char == "*":
                index += 2
                state = "block-comment"
                continue
            result.append(char)
            index += 1
            if char == '"':
                state = "string"
            elif char == "'":
                state = "character"
            continue

        if state == "line-comment":
            index += 1
            if char == "\n":
                state = "code"
            continue

        if state == "block-comment":
            if char == "*" and next_char == "/":
                index += 2
                state = "code"
            else:
                index += 1
            continue

        result.append(char)
        index += 1
        if char == "\\" and index < len(text):
            result.append(text[index])
            index += 1
            continue
        terminator = '"' if state == "string" else "'"
        if char == terminator:
            state = "code"

    return "".join(result)


def call_end_offset(code: str, open_parenthesis: int) -> int:
    """Return the offset immediately after the balanced call expression."""

    depth = 0
    for index in range(open_parenthesis, len(code)):
        char = code[index]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return index + 1
    return open_parenthesis + 1


def digest(parts: Iterable[str]) -> str:
    payload = "\0".join(parts).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def review_finding_identity(
    path: str,
    symbol: str,
    symbol_ordinal: int,
    normalized_call: str,
) -> tuple[str, str]:
    finding_id = "aes-sec-001:" + digest(
        ("review-finding-v1", path, symbol, str(symbol_ordinal))
    )
    source_fingerprint = "sha256:" + digest(
        ("review-source-v1", path, symbol, normalized_call)
    )
    return finding_id, source_fingerprint


def require_mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def require_string(
    value: object,
    label: str,
    *,
    allow_none: bool = False,
) -> str | None:
    if value is None and allow_none:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value


def require_line(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"{label} must be a positive integer")
    return value


def require_date(
    value: object,
    label: str,
    *,
    allow_none: bool = False,
) -> str | None:
    text = require_string(value, label, allow_none=allow_none)
    if text is None:
        return None
    try:
        date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{label} must be an ISO 8601 date") from exc
    return text


def validate_fingerprint(value: object, label: str, prefix: str) -> str:
    fingerprint = require_string(value, label)
    assert fingerprint is not None
    expected_length = len(prefix) + 64
    if (
        not fingerprint.startswith(prefix)
        or len(fingerprint) != expected_length
        or not re.fullmatch(r"[0-9a-f]{64}", fingerprint[len(prefix) :])
    ):
        raise ValueError(f"{label} must use {prefix}<64 lowercase hex characters>")
    return fingerprint


def parse_ledger_finding(value: object, label: str) -> ReviewLedgerFinding:
    item = require_mapping(value, label)
    return ReviewLedgerFinding(
        finding_id=validate_fingerprint(
            item.get("finding_id"),
            f"{label}.finding_id",
            "aes-sec-001:",
        ),
        source_fingerprint=validate_fingerprint(
            item.get("source_fingerprint"),
            f"{label}.source_fingerprint",
            "sha256:",
        ),
        path=require_string(item.get("path"), f"{label}.path") or "",
        line=require_line(item.get("line"), f"{label}.line"),
        symbol=require_string(item.get("symbol"), f"{label}.symbol") or "",
    )


def parse_disposition(value: object, label: str) -> ReviewDisposition:
    item = require_mapping(value, label)
    finding = parse_ledger_finding(item, label)
    classification = require_string(
        item.get("classification"),
        f"{label}.classification",
    )
    assert classification is not None
    if classification not in REVIEW_DISPOSITION_CLASSES:
        allowed = ", ".join(sorted(REVIEW_DISPOSITION_CLASSES))
        raise ValueError(
            f"{label}.classification must be one of: {allowed}"
        )

    require_string(item.get("rationale"), f"{label}.rationale")
    invariant = require_string(
        item.get("invariant"),
        f"{label}.invariant",
        allow_none=True,
    )
    if classification == "approved-invariant" and invariant is None:
        raise ValueError(
            f"{label}.invariant is required when classification is approved-invariant"
        )
    evidence = item.get("evidence")
    if (
        not isinstance(evidence, list)
        or not evidence
        or any(not isinstance(entry, str) or not entry.strip() for entry in evidence)
    ):
        raise ValueError(f"{label}.evidence must be a non-empty string array")
    require_string(item.get("owner"), f"{label}.owner")
    require_string(item.get("reviewer"), f"{label}.reviewer")
    require_date(item.get("reviewed_at"), f"{label}.reviewed_at")
    require_date(
        item.get("reassess_after"),
        f"{label}.reassess_after",
        allow_none=True,
    )
    resolution_commit = require_string(
        item.get("resolution_commit"),
        f"{label}.resolution_commit",
        allow_none=True,
    )
    if classification == "resolved" and resolution_commit is None:
        raise ValueError(
            f"{label}.resolution_commit is required when classification is resolved"
        )
    if resolution_commit is not None and len(resolution_commit) < 7:
        raise ValueError(f"{label}.resolution_commit must be at least 7 characters")

    return ReviewDisposition(
        finding_id=finding.finding_id,
        source_fingerprint=finding.source_fingerprint,
        path=finding.path,
        line=finding.line,
        symbol=finding.symbol,
        classification=classification,
    )


def load_review_disposition_ledger(
    root: Path,
    repository: str,
) -> ReviewDispositionLedger:
    relative_path = DEFAULT_REVIEW_DISPOSITIONS_PATH.as_posix()
    path = root / DEFAULT_REVIEW_DISPOSITIONS_PATH
    if not path.is_file():
        return ReviewDispositionLedger(path=relative_path, present=False)

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"failed to read {relative_path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {relative_path}: {exc}") from exc

    document = require_mapping(data, relative_path)
    schema_version = require_string(
        document.get("schema_version"),
        f"{relative_path}.schema_version",
    )
    if schema_version != REVIEW_DISPOSITION_SCHEMA_VERSION:
        raise ValueError(
            f"{relative_path}.schema_version must be "
            f"{REVIEW_DISPOSITION_SCHEMA_VERSION}"
        )
    ledger_repository = require_string(
        document.get("repository"),
        f"{relative_path}.repository",
    )
    assert ledger_repository is not None
    repository_matches = (
        ledger_repository == repository
        if "/" in repository
        else ledger_repository.rsplit("/", maxsplit=1)[-1] == repository
    )
    if not repository_matches:
        raise ValueError(
            f"{relative_path}.repository is {ledger_repository!r}, "
            f"expected {repository!r}"
        )

    baseline_document = require_mapping(
        document.get("baseline"),
        f"{relative_path}.baseline",
    )
    require_date(
        baseline_document.get("captured_at"),
        f"{relative_path}.baseline.captured_at",
    )
    require_string(
        baseline_document.get("source"),
        f"{relative_path}.baseline.source",
    )
    baseline_values = baseline_document.get("findings")
    if not isinstance(baseline_values, list):
        raise ValueError(
            f"{relative_path}.baseline.findings must be a JSON array"
        )

    disposition_values = document.get("dispositions")
    if not isinstance(disposition_values, list):
        raise ValueError(f"{relative_path}.dispositions must be a JSON array")

    baseline: dict[str, ReviewLedgerFinding] = {}
    for index, value in enumerate(baseline_values):
        item = parse_ledger_finding(
            value,
            f"{relative_path}.baseline.findings[{index}]",
        )
        if item.finding_id in baseline:
            raise ValueError(
                f"{relative_path} has duplicate baseline finding_id "
                f"{item.finding_id}"
            )
        baseline[item.finding_id] = item

    dispositions: dict[str, ReviewDisposition] = {}
    for index, value in enumerate(disposition_values):
        item = parse_disposition(
            value,
            f"{relative_path}.dispositions[{index}]",
        )
        if item.finding_id in dispositions:
            raise ValueError(
                f"{relative_path} has duplicate disposition finding_id "
                f"{item.finding_id}"
            )
        dispositions[item.finding_id] = item

    return ReviewDispositionLedger(
        path=relative_path,
        present=True,
        schema_version=schema_version,
        repository=ledger_repository,
        baseline=baseline,
        dispositions=dispositions,
    )


def apply_review_dispositions(
    findings: list[ApiFinding],
    ledger: ReviewDispositionLedger,
    *,
    evaluated: bool,
) -> tuple[list[ApiFinding], ReviewDispositionSummary]:
    if not evaluated:
        return findings, ReviewDispositionSummary(
            path=ledger.path,
            present=ledger.present,
            evaluated=False,
            schema_version=ledger.schema_version,
            baseline_count=len(ledger.baseline),
            disposition_count=len(ledger.dispositions),
            total=0,
            reviewed=0,
            unresolved=0,
            new=0,
            source_drifted=0,
            stale=0,
        )

    current_ids: set[str] = set()
    reviewed = 0
    new = 0
    source_drifted = 0
    updated: list[ApiFinding] = []

    for finding in findings:
        if finding.severity != "review-required":
            updated.append(finding)
            continue

        current_ids.add(finding.finding_id)
        baseline = ledger.baseline.get(finding.finding_id)
        disposition = ledger.dispositions.get(finding.finding_id)
        classification: str | None = None

        if disposition is not None:
            classification = disposition.classification
            if (
                disposition.source_fingerprint != finding.source_fingerprint
                or disposition.path != finding.path
                or disposition.symbol != finding.symbol
            ):
                status = "source-drifted"
                source_drifted += 1
            elif disposition.classification == "resolved":
                status = "unresolved"
            else:
                status = "reviewed"
                reviewed += 1
        elif baseline is None:
            status = "new"
            new += 1
        elif (
            baseline.source_fingerprint != finding.source_fingerprint
            or baseline.path != finding.path
            or baseline.symbol != finding.symbol
        ):
            status = "source-drifted"
            source_drifted += 1
        else:
            status = "unresolved"

        updated.append(
            ApiFinding(
                path=finding.path,
                line=finding.line,
                symbol=finding.symbol,
                severity=finding.severity,
                text=finding.text,
                remediation=finding.remediation,
                finding_id=finding.finding_id,
                source_fingerprint=finding.source_fingerprint,
                disposition_status=status,
                disposition_classification=classification,
            )
        )

    total = sum(
        1 for finding in updated if finding.severity == "review-required"
    )
    resolved_ids = {
        finding_id
        for finding_id, disposition in ledger.dispositions.items()
        if disposition.classification == "resolved"
    }
    tracked_ids = (set(ledger.baseline) | set(ledger.dispositions)) - resolved_ids
    stale = len(tracked_ids - current_ids)
    unresolved = total - reviewed
    return updated, ReviewDispositionSummary(
        path=ledger.path,
        present=ledger.present,
        evaluated=True,
        schema_version=ledger.schema_version,
        baseline_count=len(ledger.baseline),
        disposition_count=len(ledger.dispositions),
        total=total,
        reviewed=reviewed,
        unresolved=unresolved,
        new=new,
        source_drifted=source_drifted,
        stale=stale,
    )


def scan_source_for_apis(
    root: Path, path: Path, include_dangerous_primitives: bool
) -> list[ApiFinding]:
    text = read_text_lossy(path)
    if text is None:
        return []
    code = strip_c_comments_and_literals(text)

    symbols = set(BANNED_APIS)
    if include_dangerous_primitives:
        symbols |= DANGEROUS_PRIMITIVES

    pattern = re.compile(
        r"\b(" + "|".join(re.escape(symbol) for symbol in sorted(symbols)) + r")\s*\("
    )
    findings: list[ApiFinding] = []
    rel = path.relative_to(root).as_posix()
    raw_lines = text.splitlines()
    line_starts = [0]
    line_starts.extend(
        index + 1 for index, character in enumerate(code) if character == "\n"
    )
    symbol_ordinals: Counter[str] = Counter()

    for match in pattern.finditer(code):
        symbol = match.group(1)
        symbol_ordinals[symbol] += 1
        symbol_ordinal = symbol_ordinals[symbol]
        line_number = bisect.bisect_right(line_starts, match.start())
        raw_line = raw_lines[line_number - 1]
        if line_has_banned_scan_exemption(raw_line):
            continue
        open_parenthesis = code.find("(", match.start(), match.end())
        call_end = call_end_offset(code, open_parenthesis)
        normalized_call = normalize_call_source(
            text[match.start() : call_end]
        )
        finding_id, source_fingerprint = review_finding_identity(
            rel,
            symbol,
            symbol_ordinal,
            normalized_call,
        )
        severity = "banned" if symbol in BANNED_APIS else "review-required"
        findings.append(
            ApiFinding(
                path=rel,
                line=line_number,
                symbol=symbol,
                severity=severity,
                text=raw_line.strip()[:240],
                remediation=API_REMEDIATIONS[symbol],
                finding_id=finding_id,
                source_fingerprint=source_fingerprint,
            )
        )
    return findings


def scan(root: Path, repo_name: str | None, include_dangerous_primitives: bool) -> ScanReport:
    root = root.resolve()
    files = list(iter_files(root))
    repository = repo_name or root.name

    native_files = sorted(
        path.relative_to(root).as_posix()
        for path in files
        if path.suffix in NATIVE_SOURCE_EXTENSIONS
    )
    hardware_files = sorted(
        path.relative_to(root).as_posix()
        for path in files
        if path.suffix in HARDWARE_SOURCE_EXTENSIONS
    )
    build_surfaces = sorted(
        path.relative_to(root).as_posix() for path in files if is_build_surface(path)
    )

    findings: list[ApiFinding] = []
    for path in files:
        if path.suffix in NATIVE_SOURCE_EXTENSIONS:
            findings.extend(scan_source_for_apis(root, path, include_dangerous_primitives))

    ledger = load_review_disposition_ledger(root, repository)
    findings, review_dispositions = apply_review_dispositions(
        findings,
        ledger,
        evaluated=include_dangerous_primitives,
    )
    static_analysis, sanitizers, fuzzing, waivers = collect_signals(root, files)

    secure_profile_present = (root / SECURE_PROFILE_PATH).is_file()
    waiver_log_present = (root / DEFAULT_WAIVER_PATH).is_file()

    return ScanReport(
        repository=repository,
        root=str(root),
        classification=classify(native_files, hardware_files, build_surfaces),
        secure_profile_present=secure_profile_present,
        waiver_log_present=waiver_log_present,
        native_files=native_files,
        hardware_files=hardware_files,
        build_surfaces=build_surfaces,
        static_analysis_signals=static_analysis,
        sanitizer_signals=sanitizers,
        fuzz_signals=fuzzing,
        waiver_signals=waivers,
        findings=sorted(findings, key=lambda finding: (finding.path, finding.line, finding.symbol)),
        review_dispositions=review_dispositions,
    )


def format_markdown(report: ScanReport) -> str:
    data = report.to_dict()
    lines = [
        f"# AES-SEC-001 Scan Report: `{report.repository}`",
        "",
        f"- Classification: `{report.classification}`",
        f"- Secure profile present: `{report.secure_profile_present}`",
        f"- Waiver log present: `{report.waiver_log_present}`",
        f"- Native files: `{len(report.native_files)}`",
        f"- Hardware files: `{len(report.hardware_files)}`",
        f"- Build surfaces: `{len(report.build_surfaces)}`",
        f"- Banned API findings: `{sum(1 for f in report.findings if f.severity == 'banned')}`",
        f"- Review-required primitive findings: `{sum(1 for f in report.findings if f.severity == 'review-required')}`",
        f"- Passes minimum adoption gate: `{data['summary']['passes_minimum_adoption_gate']}`",
        f"- Passes review-disposition ratchet: `{data['summary']['passes_review_ratchet']}`",
        "",
        "## Operational Signals",
        "",
        f"- Static analysis: {', '.join(report.static_analysis_signals) if report.static_analysis_signals else 'none found'}",
        f"- Sanitizers: {', '.join(report.sanitizer_signals) if report.sanitizer_signals else 'none found'}",
        f"- Fuzzing: {', '.join(report.fuzz_signals) if report.fuzz_signals else 'none found'}",
        f"- Waivers: {', '.join(report.waiver_signals) if report.waiver_signals else 'none found'}",
        "",
    ]

    review = report.review_dispositions
    if review is not None:
        lines.extend(
            [
                "## Review-Disposition Status",
                "",
                f"- Ledger: `{review.path}`",
                f"- Ledger present: `{review.present}`",
                f"- Evaluation enabled: `{review.evaluated}`",
                f"- Baseline entries: `{review.baseline_count}`",
                f"- Dispositions: `{review.disposition_count}`",
                f"- Total current findings: `{review.total}`",
                f"- Reviewed: `{review.reviewed}`",
                f"- Unresolved: `{review.unresolved}`",
                f"- New: `{review.new}`",
                f"- Source-drifted: `{review.source_drifted}`",
                f"- Stale ledger entries: `{review.stale}`",
                "",
            ]
        )

    if report.findings:
        lines.extend(
            [
                "## Findings",
                "",
                "| Severity | Symbol | Path | Line | Disposition | Finding ID | Remediation |",
                "|---|---:|---|---:|---|---|---|",
            ]
        )
        for finding in report.findings:
            lines.append(
                f"| `{finding.severity}` | `{finding.symbol}` | "
                f"`{finding.path}` | {finding.line} | "
                f"`{finding.disposition_status or 'n/a'}` | "
                f"`{finding.finding_id}` | {finding.remediation} |"
            )
        lines.append("")
    else:
        lines.extend(["## Findings", "", "No banned API findings were detected.", ""])

    return "\n".join(lines)


def github_escape_data(value: str) -> str:
    return value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def github_escape_property(value: str) -> str:
    return (
        github_escape_data(value)
        .replace(":", "%3A")
        .replace(",", "%2C")
    )


def format_github(report: ScanReport) -> str:
    if not report.findings:
        return "::notice title=AES-SEC-001::No banned or review-required API findings."

    annotations: list[str] = []
    for finding in report.findings:
        level = "error" if finding.severity == "banned" else "warning"
        title = github_escape_property(
            f"AES-SEC-001 {finding.severity}: {finding.symbol}"
        )
        message = github_escape_data(
            f"{finding.symbol} detected"
            + (
                f" ({finding.disposition_status})"
                if finding.disposition_status
                else ""
            )
            + f". Finding ID: {finding.finding_id}. "
            f"Remedy: {finding.remediation}"
        )
        annotations.append(
            f"::{level} file={github_escape_property(finding.path)},"
            f"line={finding.line},title={title}::{message}"
        )
    return "\n".join(annotations)


def main() -> int:
    args = parse_args()
    root = Path(args.root)
    if not root.exists() or not root.is_dir():
        print(f"error: scan root is not a directory: {root}", file=sys.stderr)
        return 2

    report = scan(root, args.repo_name, args.include_dangerous_primitives)

    if args.format == "json":
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    elif args.format == "markdown":
        print(format_markdown(report))
    else:
        print(format_github(report))

    if args.strict and not report.passes_minimum_adoption_gate:
        return 1
    if args.strict_review_ratchet and not report.passes_review_ratchet:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
