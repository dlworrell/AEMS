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
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

SECURE_PROFILE_PATH = Path("docs/engineering/SECURE-C-CXX.md")
DEFAULT_WAIVER_PATH = Path("docs/engineering/AES-SEC-001-waivers.md")

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
            "summary": {
                "has_native_code": self.has_native_code,
                "has_banned_api_findings": self.has_banned_api_findings,
                "requires_secure_profile": self.requires_secure_profile,
                "passes_minimum_adoption_gate": self.passes_minimum_adoption_gate,
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
    code_lines = code.splitlines()
    for line_number, code_line in enumerate(code_lines, start=1):
        if not code_line.strip():
            continue
        raw_line = raw_lines[line_number - 1]
        if line_has_banned_scan_exemption(raw_line):
            continue
        for match in pattern.finditer(code_line):
            symbol = match.group(1)
            severity = "banned" if symbol in BANNED_APIS else "review-required"
            findings.append(
                ApiFinding(
                    path=rel,
                    line=line_number,
                    symbol=symbol,
                    severity=severity,
                    text=raw_line.strip()[:240],
                    remediation=API_REMEDIATIONS[symbol],
                )
            )
    return findings


def scan(root: Path, repo_name: str | None, include_dangerous_primitives: bool) -> ScanReport:
    root = root.resolve()
    files = list(iter_files(root))

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

    static_analysis, sanitizers, fuzzing, waivers = collect_signals(root, files)

    secure_profile_present = (root / SECURE_PROFILE_PATH).is_file()
    waiver_log_present = (root / DEFAULT_WAIVER_PATH).is_file()

    return ScanReport(
        repository=repo_name or root.name,
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
        "",
        "## Operational Signals",
        "",
        f"- Static analysis: {', '.join(report.static_analysis_signals) if report.static_analysis_signals else 'none found'}",
        f"- Sanitizers: {', '.join(report.sanitizer_signals) if report.sanitizer_signals else 'none found'}",
        f"- Fuzzing: {', '.join(report.fuzz_signals) if report.fuzz_signals else 'none found'}",
        f"- Waivers: {', '.join(report.waiver_signals) if report.waiver_signals else 'none found'}",
        "",
    ]

    if report.findings:
        lines.extend(
            [
                "## Findings",
                "",
                "| Severity | Symbol | Path | Line | Remediation |",
                "|---|---:|---|---:|---|",
            ]
        )
        for finding in report.findings:
            lines.append(
                f"| `{finding.severity}` | `{finding.symbol}` | "
                f"`{finding.path}` | {finding.line} | {finding.remediation} |"
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
            f"{finding.symbol} detected. Remedy: {finding.remediation}"
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
