#!/usr/bin/env python3
"""Reporting-only AES-SEC-002 repository scanner.

The scanner reports evidence signals and high-confidence source-policy
violations.  It deliberately has no blocking mode: AES-SEC-002 adoption must
be baselined before any ratchet proposal.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Iterable


STANDARD_PATH = "standards/AES-SEC-002-cross-language-secret-storage-boundaries.md"
STANDARD_URL = (
    "https://github.com/dlworrell/AES/blob/main/"
    "standards/AES-SEC-002-cross-language-secret-storage-boundaries.md"
)
DEFAULT_PROFILE = "docs/engineering/AES-SEC-002-boundaries.md"
DEFAULT_WAIVER_LOG = "docs/engineering/AES-SEC-002-waivers.md"

APPLICABILITY_VALUES = {
    "in-scope",
    "out-of-scope",
    "not-yet-classified",
}

STATUS_VALUES = {
    "present",
    "absent-evidence",
    "violation",
    "untested",
    "not-applicable",
}

NATIVE_EXTENSIONS = {
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
}

SAFE_LANGUAGE_EXTENSIONS = {
    ".swift",
    ".rs",
    ".kt",
    ".java",
    ".cs",
}

TEXT_EXTENSIONS = (
    NATIVE_EXTENSIONS
    | SAFE_LANGUAGE_EXTENSIONS
    | {
        ".md",
        ".rst",
        ".txt",
        ".json",
        ".yaml",
        ".yml",
        ".toml",
        ".lock",
        ".sh",
        ".bash",
        ".py",
        ".mk",
        ".cmake",
    }
)

TEXT_NAMES = {
    ".gitignore",
    "Makefile",
    "CMakeLists.txt",
    "Package.swift",
    "Cargo.lock",
    "Package.resolved",
}

EXCLUDED_DIRECTORIES = {
    ".git",
    ".hg",
    ".svn",
    ".idea",
    ".vscode",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "out",
    "target",
    "third_party",
    "third-party",
    "vendor",
}

TEXT_LIMIT = 3_000_000

BANNED_STRING_APIS = {
    "gets",
    "strcpy",
    "strcat",
    "sprintf",
    "vsprintf",
    "strncpy",
    "strncat",
}

NATIVE_THREAD_APIS = {
    "pthread_create",
    "thrd_create",
    "CreateThread",
    "_beginthread",
    "_beginthreadex",
    "dispatch_async",
    "dispatch_async_f",
}

RULES: dict[str, tuple[str, str]] = {
    "AES-SEC-002-SCOPE-001": (
        "Applicability",
        f"{STANDARD_URL}#purpose",
    ),
    "AES-SEC-002-PROFILE-001": (
        "Required Local Profile",
        f"{STANDARD_URL}#required-local-profile",
    ),
    "AES-SEC-002-ABI-001": (
        "Bridge isolation and direct-call escapes",
        f"{STANDARD_URL}#abi-and-ownership-boundary",
    ),
    "AES-SEC-002-ABI-002": (
        "Pointer ownership and lifecycle anchors",
        f"{STANDARD_URL}#abi-and-ownership-boundary",
    ),
    "AES-SEC-002-CONC-001": (
        "Callback synchrony and native thread creation",
        f"{STANDARD_URL}#abi-and-ownership-boundary",
    ),
    "AES-SEC-002-CONC-002": (
        "Swift 6 strict concurrency and actor isolation",
        f"{STANDARD_URL}#swift-boundary",
    ),
    "AES-SEC-002-NATIVE-001": (
        "Banned native string APIs",
        f"{STANDARD_URL}#c-and-c-boundary",
    ),
    "AES-SEC-002-KEY-001": (
        "Read-only key buffers and explicit lengths",
        f"{STANDARD_URL}#secret-and-key-lifecycle",
    ),
    "AES-SEC-002-KEY-002": (
        "Project-owned secret erasure",
        f"{STANDARD_URL}#secret-and-key-lifecycle",
    ),
    "AES-SEC-002-STORE-001": (
        "Keyed temporary-store ordering",
        f"{STANDARD_URL}#encrypted-storage",
    ),
    "AES-SEC-002-STORE-002": (
        "Encrypted restore and private-file boundaries",
        f"{STANDARD_URL}#encrypted-storage",
    ),
    "AES-SEC-002-DEP-001": (
        "Immutable dependency pins",
        f"{STANDARD_URL}#dependencies",
    ),
    "AES-SEC-002-REPO-001": (
        "Repository private-data hygiene",
        f"{STANDARD_URL}#repository-data-and-history",
    ),
    "AES-SEC-002-HISTORY-001": (
        "History-migration prerequisites",
        f"{STANDARD_URL}#repository-data-and-history",
    ),
    "AES-SEC-002-ELF-001": (
        "Linux ELF hardening evidence",
        f"{STANDARD_URL}#platform-hardening",
    ),
    "AES-SEC-002-MACHO-001": (
        "Apple Mach-O and sandbox evidence",
        f"{STANDARD_URL}#platform-hardening",
    ),
    "AES-SEC-002-PLATFORM-001": (
        "ELF and Apple pipeline separation",
        f"{STANDARD_URL}#platform-hardening",
    ),
    "AES-SEC-002-WAIVER-001": (
        "Waiver representation",
        f"{STANDARD_URL}#waivers",
    ),
}


@dataclass(frozen=True)
class EvidenceFinding:
    rule_id: str
    status: str
    severity: str
    message: str
    path: str | None = None
    line: int | None = None
    evidence: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        domain, standard_url = RULES[self.rule_id]
        result: dict[str, Any] = {
            "rule_id": self.rule_id,
            "domain": domain,
            "standard": "AES-SEC-002",
            "standard_path": STANDARD_PATH,
            "standard_url": standard_url,
            "status": self.status,
            "severity": self.severity,
            "message": self.message,
            "evidence": list(self.evidence),
            "evidence_path": (
                f"{self.path}:{self.line}"
                if self.path is not None and self.line is not None
                else self.path
                if self.path is not None
                else self.evidence[0]
                if self.evidence
                else "none"
            ),
        }
        if self.path is not None:
            result["path"] = self.path
        if self.line is not None:
            result["line"] = self.line
        return result


@dataclass
class ScanReport:
    repository: str
    root: str
    applicability: str
    rationale: str
    source_revision: str | None
    platforms: list[str]
    languages: list[str]
    profile_path: str
    findings: list[EvidenceFinding] = field(default_factory=list)

    def count(self, status: str) -> int:
        return sum(finding.status == status for finding in self.findings)

    @property
    def result(self) -> str:
        if self.applicability == "out-of-scope":
            return "NOT_APPLICABLE"
        if self.applicability == "not-yet-classified":
            return "CLASSIFICATION_REQUIRED"
        return "REPORTED"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0.0",
            "standard": "AES-SEC-002",
            "standard_path": STANDARD_PATH,
            "mode": "reporting",
            "repository": self.repository,
            "root": self.root,
            "source_revision": self.source_revision,
            "applicability": self.applicability,
            "applicability_rationale": self.rationale,
            "platforms": self.platforms,
            "languages": self.languages,
            "profile_path": self.profile_path,
            "result": self.result,
            "summary": {
                status: self.count(status) for status in sorted(STATUS_VALUES)
            },
            "findings": [finding.to_dict() for finding in self.findings],
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Report AES-SEC-002 applicability, evidence signals, violations, "
            "and untested targets without blocking."
        )
    )
    parser.add_argument("root", nargs="?", default=".", help="Repository checkout")
    parser.add_argument("--repo-name", help="Repository owner/name")
    parser.add_argument(
        "--config",
        default="config/aes-sec-002-repositories.json",
        help="Applicability configuration",
    )
    parser.add_argument(
        "--applicability",
        choices=sorted(APPLICABILITY_VALUES),
        help="Override configured applicability for an ad-hoc scan",
    )
    parser.add_argument(
        "--rationale",
        default="Ad-hoc scanner invocation.",
        help="Applicability rationale used with --applicability",
    )
    parser.add_argument(
        "--format", choices=("json", "markdown"), default="json"
    )
    return parser.parse_args()


def _git(root: Path, *args: str) -> str | None:
    try:
        return subprocess.check_output(
            ["git", "-C", str(root), *args],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None


def _iter_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if any(part in EXCLUDED_DIRECTORIES for part in relative.parts[:-1]):
            continue
        if path.name not in TEXT_NAMES and path.suffix.lower() not in TEXT_EXTENSIONS:
            continue
        try:
            if path.stat().st_size > TEXT_LIMIT:
                continue
        except OSError:
            continue
        yield path


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _matches(
    root: Path,
    files: Iterable[Path],
    pattern: str,
    *,
    flags: int = re.IGNORECASE,
    paths: Iterable[str] | None = None,
) -> list[tuple[str, int, str]]:
    expression = re.compile(pattern, flags)
    allowed = tuple(value.rstrip("/") for value in paths or ())
    matches: list[tuple[str, int, str]] = []
    for path in files:
        relative = _relative(root, path)
        if allowed and not any(
            relative == candidate or relative.startswith(f"{candidate}/")
            for candidate in allowed
        ):
            continue
        for line_number, line in enumerate(_read(path).splitlines(), start=1):
            if expression.search(line):
                matches.append((relative, line_number, line.strip()[:240]))
    return matches


def _evidence(matches: Iterable[tuple[str, int, str]]) -> tuple[str, ...]:
    return tuple(
        sorted({f"{path}:{line}" for path, line, _ in matches})
    )


def _signal(
    rule_id: str,
    matches: list[tuple[str, int, str]],
    *,
    present_message: str,
    absent_message: str,
    absent_status: str = "absent-evidence",
) -> EvidenceFinding:
    if matches:
        return EvidenceFinding(
            rule_id=rule_id,
            status="present",
            severity="informational",
            message=present_message,
            evidence=_evidence(matches),
        )
    return EvidenceFinding(
        rule_id=rule_id,
        status=absent_status,
        severity="review",
        message=absent_message,
    )


def _not_applicable(rule_id: str, message: str) -> EvidenceFinding:
    return EvidenceFinding(
        rule_id=rule_id,
        status="not-applicable",
        severity="informational",
        message=message,
    )


def _entry_for(config: dict[str, Any], repository: str) -> dict[str, Any] | None:
    for entry in config.get("repositories", []):
        if isinstance(entry, dict) and entry.get("full_name") == repository:
            return entry
    return None


def load_config_entry(path: Path, repository: str) -> dict[str, Any]:
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"failed to read configuration {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON configuration {path}: {exc}") from exc
    entry = _entry_for(config, repository)
    if entry is None:
        raise ValueError(
            f"repository {repository!r} is absent from applicability configuration"
        )
    return entry


def _path_allowed(path: str, allowed: Iterable[str]) -> bool:
    return any(
        path == candidate.rstrip("/")
        or path.startswith(f"{candidate.rstrip('/')}/")
        for candidate in allowed
    )


def _scan_bridge(
    root: Path,
    files: list[Path],
    entry: dict[str, Any],
) -> list[EvidenceFinding]:
    native = [path for path in files if path.suffix.lower() in NATIVE_EXTENSIONS]
    safe = [
        path for path in files if path.suffix.lower() in SAFE_LANGUAGE_EXTENSIONS
    ]
    if not native or not safe:
        return [
            _not_applicable(
                "AES-SEC-002-ABI-001",
                "No safe-language/native-code pair was detected in this checkout.",
            ),
            _not_applicable(
                "AES-SEC-002-ABI-002",
                "No safe-language/native pointer boundary was detected.",
            ),
            _not_applicable(
                "AES-SEC-002-CONC-001",
                "No safe-language/native callback boundary was detected.",
            ),
        ]

    allowed = [str(value) for value in entry.get("bridge_paths", [])]
    prefixes = [str(value) for value in entry.get("ffi_symbol_prefixes", [])]
    bridge_matches = [
        (
            _relative(root, path),
            1,
            "configured bridge path",
        )
        for path in safe
        if _path_allowed(_relative(root, path), allowed)
    ]
    findings: list[EvidenceFinding] = [
        _signal(
            "AES-SEC-002-ABI-001",
            bridge_matches,
            present_message="Configured safe/native bridge locations are present.",
            absent_message=(
                "No configured bridge location was found for the detected "
                "safe/native language pair."
            ),
        )
    ]

    if prefixes:
        pattern = r"\b(?:" + "|".join(re.escape(prefix) for prefix in prefixes) + r")[A-Za-z0-9_]*\s*\("
        for match_path, line, text in _matches(root, safe, pattern):
            if _path_allowed(match_path, allowed):
                continue
            findings.append(
                EvidenceFinding(
                    rule_id="AES-SEC-002-ABI-001",
                    status="violation",
                    severity="high",
                    message="A configured FFI symbol is called outside the reviewed bridge.",
                    path=match_path,
                    line=line,
                    evidence=(text,),
                )
            )

    pointer_matches = _matches(
        root,
        safe,
        r"\b(?:Unsafe(?:Mutable)?(?:Raw)?Pointer|OpaquePointer|Unmanaged<)",
    )
    lifecycle_matches = _matches(
        root,
        files,
        r"\b(?:create|open|init|adopt|close|destroy|deinit|release|free)\b",
    )
    if pointer_matches:
        findings.append(
            _signal(
                "AES-SEC-002-ABI-002",
                lifecycle_matches,
                present_message="Pointer use has discoverable lifecycle anchors.",
                absent_message=(
                    "Pointer use was detected without discoverable constructor/"
                    "destructor or adopt/release anchors."
                ),
            )
        )
    else:
        findings.append(
            _not_applicable(
                "AES-SEC-002-ABI-002",
                "No safe-language pointer or opaque-handle surface was detected.",
            )
        )

    callback_matches = _matches(
        root,
        native,
        r"\b(?:callback|visitor|context)\b",
    )
    callback_contracts = _matches(
        root,
        files,
        r"\b(?:synchronous|synchronously|calling thread|executor|retained)\b",
    )
    if callback_matches:
        findings.append(
            _signal(
                "AES-SEC-002-CONC-001",
                callback_contracts,
                present_message="Callback synchrony or executor evidence is present.",
                absent_message=(
                    "Callback surfaces were detected without synchrony, thread, "
                    "executor, or retention evidence."
                ),
            )
        )
    else:
        findings.append(
            _not_applicable(
                "AES-SEC-002-CONC-001",
                "No native callback or visitor surface was detected.",
            )
        )

    thread_pattern = (
        r"\b(?:"
        + "|".join(re.escape(symbol) for symbol in sorted(NATIVE_THREAD_APIS))
        + r")\s*\("
    )
    for match_path, line, text in _matches(root, native, thread_pattern):
        findings.append(
            EvidenceFinding(
                rule_id="AES-SEC-002-CONC-001",
                status="absent-evidence",
                severity="review",
                message=(
                    "Native thread creation requires an explicit callback and "
                    "executor contract review."
                ),
                path=match_path,
                line=line,
                evidence=(text,),
            )
        )
    return findings


def _scan_swift(root: Path, files: list[Path]) -> EvidenceFinding:
    swift = [path for path in files if path.suffix.lower() == ".swift"]
    if not swift:
        return _not_applicable(
            "AES-SEC-002-CONC-002", "No Swift source was detected."
        )
    all_files = list(files)
    language_mode = _matches(
        root,
        all_files,
        r"(?:SWIFT_VERSION\s*[:=]\s*[\"']?6|swiftLanguageVersions.*\.v6)",
    )
    strict = _matches(
        root,
        all_files,
        r"SWIFT_STRICT_CONCURRENCY\s*[:=]\s*(?:complete|Complete)",
    )
    isolation = _matches(
        root,
        swift,
        r"(?:@MainActor|@globalActor|\bactor\s+[A-Za-z_])",
    )
    evidence = language_mode + strict + isolation
    if language_mode and strict and isolation:
        return EvidenceFinding(
            rule_id="AES-SEC-002-CONC-002",
            status="present",
            severity="informational",
            message="Swift 6, complete strict concurrency, and actor evidence are present.",
            evidence=_evidence(evidence),
        )
    missing = []
    if not language_mode:
        missing.append("Swift 6 language mode")
    if not strict:
        missing.append("complete strict-concurrency configuration")
    if not isolation:
        missing.append("actor/global-actor isolation")
    return EvidenceFinding(
        rule_id="AES-SEC-002-CONC-002",
        status="absent-evidence",
        severity="review",
        message="Missing " + ", ".join(missing) + ".",
        evidence=_evidence(evidence),
    )


def _scan_native_apis(root: Path, files: list[Path]) -> list[EvidenceFinding]:
    native = [path for path in files if path.suffix.lower() in NATIVE_EXTENSIONS]
    if not native:
        return [
            _not_applicable(
                "AES-SEC-002-NATIVE-001", "No project-owned native source was detected."
            )
        ]
    pattern = (
        r"\b("
        + "|".join(re.escape(symbol) for symbol in sorted(BANNED_STRING_APIS))
        + r")\s*\("
    )
    matches = _matches(root, native, pattern)
    findings: list[EvidenceFinding] = []
    for path, line, text in matches:
        symbol_match = re.search(pattern, text, re.IGNORECASE)
        symbol = symbol_match.group(1) if symbol_match else "banned API"
        findings.append(
            EvidenceFinding(
                rule_id="AES-SEC-002-NATIVE-001",
                status="violation",
                severity="high",
                message=f"Project-owned native code calls banned API `{symbol}`.",
                path=path,
                line=line,
                evidence=(text,),
            )
        )
    if not findings:
        findings.append(
            EvidenceFinding(
                rule_id="AES-SEC-002-NATIVE-001",
                status="present",
                severity="informational",
                message="No AES-SEC-002 banned native string APIs were detected.",
            )
        )
    return findings


def _scan_keys_and_storage(
    root: Path, files: list[Path], entry: dict[str, Any]
) -> list[EvidenceFinding]:
    text_files = list(files)
    key_surface = bool(entry.get("secret_material")) or bool(
        _matches(
            root,
            text_files,
            r"\b(?:keychain|secret|password|token|recovery key|sqlcipher|sqlite3_key)\b",
        )
    )
    if not key_surface:
        return [
            _not_applicable(
                "AES-SEC-002-KEY-001", "No key or secret boundary was detected."
            ),
            _not_applicable(
                "AES-SEC-002-KEY-002", "No project-owned secret buffer was detected."
            ),
            _not_applicable(
                "AES-SEC-002-STORE-001", "No keyed SQLite/SQLCipher store was detected."
            ),
            _not_applicable(
                "AES-SEC-002-STORE-002", "No encrypted restore boundary was detected."
            ),
        ]

    const_keys = _matches(
        root,
        text_files,
        r"\bconst\s+(?:unsigned\s+char|u?int8_t|char)\s*\*\s*[A-Za-z0-9_]*key[A-Za-z0-9_]*\s*,[^;\n]*(?:size_t|u?int(?:32|64)_t)\s+[A-Za-z0-9_]*(?:length|len|size)",
    )
    mutable_keys = _matches(
        root,
        [
            path
            for path in text_files
            if path.suffix.lower() in NATIVE_EXTENSIONS
        ],
        r"(?<!const\s)\b(?:unsigned\s+char|u?int8_t|char)\s*\*\s*[A-Za-z0-9_]*key[A-Za-z0-9_]*\s*,",
    )
    findings: list[EvidenceFinding] = [
        _signal(
            "AES-SEC-002-KEY-001",
            const_keys,
            present_message="Read-only key buffers with explicit lengths were detected.",
            absent_message=(
                "No read-only native key-buffer declaration with an explicit "
                "length was detected."
            ),
        )
    ]
    for path, line, text in mutable_keys:
        findings.append(
            EvidenceFinding(
                rule_id="AES-SEC-002-KEY-001",
                status="violation",
                severity="high",
                message="A native API appears to accept a mutable key pointer.",
                path=path,
                line=line,
                evidence=(text,),
            )
        )

    erasure = _matches(
        root,
        text_files,
        r"\b(?:explicit_bzero|memset_s|resetBytes|zero_bytes|secure_erase|volatile\s+(?:unsigned\s+char|u?int8_t))\b",
    )
    findings.append(
        _signal(
            "AES-SEC-002-KEY-002",
            erasure,
            present_message="Project-owned secret-erasure anchors were detected.",
            absent_message="No project-owned secret-erasure anchor was detected.",
        )
    )

    sqlcipher_files = [
        path
        for path in text_files
        if re.search(r"\b(?:sqlite3_key|sqlcipher)\b", _read(path), re.IGNORECASE)
    ]
    if not sqlcipher_files:
        findings.append(
            _not_applicable(
                "AES-SEC-002-STORE-001", "No keyed SQLite/SQLCipher store was detected."
            )
        )
    else:
        ordering_evidence: list[tuple[str, int, str]] = []
        ordering_violation = False
        for path in sqlcipher_files:
            text = _read(path)
            key_calls = [
                match
                for match in re.finditer(r"\bsqlite3_key\s*\(", text)
                if "extern" not in text[text.rfind("\n", 0, match.start()) + 1 : match.start()]
            ]
            temp_matches = list(
                re.finditer(
                    r"(?:PRAGMA\s+temp_store\s*=\s*MEMORY|SQLITE_TEMP_STORE\s*=\s*3)",
                    text,
                    re.IGNORECASE,
                )
            )
            if not key_calls or not temp_matches:
                continue
            key_position = key_calls[0].start()
            after = next(
                (match for match in temp_matches if match.start() > key_position),
                None,
            )
            if after is not None:
                line = text[: after.start()].count("\n") + 1
                ordering_evidence.append(
                    (_relative(root, path), line, after.group(0))
                )
            else:
                ordering_violation = True
                line = text[: temp_matches[0].start()].count("\n") + 1
                findings.append(
                    EvidenceFinding(
                        rule_id="AES-SEC-002-STORE-001",
                        status="violation",
                        severity="high",
                        message=(
                            "Temporary-storage policy was found only before the "
                            "connection key operation."
                        ),
                        path=_relative(root, path),
                        line=line,
                        evidence=(temp_matches[0].group(0),),
                    )
                )
        if ordering_evidence:
            findings.append(
                EvidenceFinding(
                    rule_id="AES-SEC-002-STORE-001",
                    status="present",
                    severity="informational",
                    message="Post-key in-memory temporary-store evidence was detected.",
                    evidence=_evidence(ordering_evidence),
                )
            )
        elif not ordering_violation:
            findings.append(
                EvidenceFinding(
                    rule_id="AES-SEC-002-STORE-001",
                    status="absent-evidence",
                    severity="review",
                    message=(
                        "Keyed storage was detected without mechanically visible "
                        "post-key in-memory temporary-store ordering."
                    ),
                )
            )

    restore = _matches(
        root,
        text_files,
        r"\b(?:restore_encrypted|encrypted restore|securityScoped|startAccessingSecurityScopedResource|O_EXCL|FileProtectionType\.complete)\b",
    )
    findings.append(
        _signal(
            "AES-SEC-002-STORE-002",
            restore,
            present_message="Encrypted restore or private-file boundary evidence was detected.",
            absent_message=(
                "No encrypted restore, exclusive creation, protected container, "
                "or security-scoped file evidence was detected."
            ),
        )
    )
    return findings


def _scan_dependencies_and_repository(
    root: Path, files: list[Path], entry: dict[str, Any]
) -> list[EvidenceFinding]:
    pins = _matches(
        root,
        files,
        r"(?:\bexactVersion\b|[\"'=:\s][0-9a-f]{40}[\"'\s]|Cargo\.lock|Package\.resolved|requirements[^/]*\.txt)",
    )
    findings = [
        _signal(
            "AES-SEC-002-DEP-001",
            pins,
            present_message="Immutable or exact dependency-pin evidence was detected.",
            absent_message="No immutable dependency-pin evidence was detected.",
        )
    ]

    ignore = root / ".gitignore"
    ignore_text = _read(ignore) if ignore.is_file() else ""
    required_groups = (
        (".env",),
        ("*.key", "*.pem", "*.p12", "*.pfx"),
        ("*.db", "*.sqlite", "*.sqlite3", "*.sqlcipher"),
    )
    missing_groups = [
        group
        for group in required_groups
        if not any(pattern in ignore_text for pattern in group)
    ]
    hygiene_scripts = _matches(
        root,
        files,
        r"(?:repository[-_ ]hygiene|git\s+ls-files|production[-_ ]isolation|secret scan|gitleaks|trufflehog)",
    )
    if not missing_groups and hygiene_scripts:
        findings.append(
            EvidenceFinding(
                rule_id="AES-SEC-002-REPO-001",
                status="present",
                severity="informational",
                message="Ignore rules and tracked-file/private-data gate evidence are present.",
                evidence=(".gitignore",) + _evidence(hygiene_scripts),
            )
        )
    else:
        missing = []
        if missing_groups:
            missing.append("secret/private-data ignore groups")
        if not hygiene_scripts:
            missing.append("tracked-file or private-data gate")
        findings.append(
            EvidenceFinding(
                rule_id="AES-SEC-002-REPO-001",
                status="absent-evidence",
                severity="review",
                message="Missing " + " and ".join(missing) + ".",
                evidence=(".gitignore",) if ignore.is_file() else (),
            )
        )

    history_status = str(entry.get("history_migration", "not-planned"))
    if history_status == "not-planned":
        findings.append(
            _not_applicable(
                "AES-SEC-002-HISTORY-001",
                "No Git-history migration is planned by the applicability record.",
            )
        )
    else:
        prerequisites = _matches(
            root,
            files,
            r"\b(?:encrypted backup|restore rehearsal|force[- ]push|rollback|branch protection|mirror planning|history migration)\b",
        )
        findings.append(
            _signal(
                "AES-SEC-002-HISTORY-001",
                prerequisites,
                present_message="History-migration prerequisite evidence was detected.",
                absent_message=(
                    "History migration is planned or deferred without discoverable "
                    "backup, restore, coordination, and rollback prerequisites."
                ),
            )
        )
    return findings


def _scan_platforms(
    root: Path, files: list[Path], entry: dict[str, Any]
) -> list[EvidenceFinding]:
    platforms = [str(value) for value in entry.get("platforms", [])]
    findings: list[EvidenceFinding] = []
    apple_files = [
        path
        for path in files
        if (
            "apple" in _relative(root, path).lower()
            or "xcode" in _relative(root, path).lower()
            or "macos" in _read(path).lower()
        )
    ]
    apple_paths = {_relative(root, path) for path in apple_files}
    non_apple_files = [
        path for path in files if _relative(root, path) not in apple_paths
    ]
    if "linux-elf" in platforms:
        elf = _matches(
            root,
            non_apple_files,
            r"(?:readelf|GNU_RELRO|BIND_NOW|-Wl,-z,(?:relro|now|noexecstack)|-fstack-protector-strong|-D_FORTIFY_SOURCE)",
        )
        findings.append(
            _signal(
                "AES-SEC-002-ELF-001",
                elf,
                present_message="Linux ELF construction or artifact-inspection evidence is present.",
                absent_message="Linux/ELF is declared but has no hardening artifact evidence.",
                absent_status="untested",
            )
        )
    else:
        findings.append(
            _not_applicable(
                "AES-SEC-002-ELF-001", "Linux/ELF is not a declared target."
            )
        )

    if "apple-macho" in platforms:
        macho = _matches(
            root,
            files,
            r"(?:otool|ENABLE_HARDENED_RUNTIME|ENABLE_APP_SANDBOX|ENABLE_USER_SELECTED_FILES|Mach-O|xcodebuild.*showBuildSettings)",
        )
        findings.append(
            _signal(
                "AES-SEC-002-MACHO-001",
                macho,
                present_message="Apple Mach-O, sandbox, or build-setting evidence is present.",
                absent_message="Apple/Mach-O is declared but has no hardening artifact evidence.",
                absent_status="untested",
            )
        )
    else:
        findings.append(
            _not_applicable(
                "AES-SEC-002-MACHO-001", "Apple/Mach-O is not a declared target."
            )
        )

    escaped = _matches(
        root,
        apple_files,
        r"(?:-Wl,-z,(?:relro|now|noexecstack)|\breadelf\b)",
    )
    if escaped:
        for path, line, text in escaped:
            findings.append(
                EvidenceFinding(
                    rule_id="AES-SEC-002-PLATFORM-001",
                    status="violation",
                    severity="high",
                    message="ELF-only hardening escaped into an Apple pipeline.",
                    path=path,
                    line=line,
                    evidence=(text,),
                )
            )
    else:
        findings.append(
            EvidenceFinding(
                rule_id="AES-SEC-002-PLATFORM-001",
                status="present",
                severity="informational",
                message="No ELF-only flags were detected in Apple pipeline files.",
            )
        )
    return findings


def scan(
    root: Path,
    *,
    repository: str,
    entry: dict[str, Any],
) -> ScanReport:
    root = root.resolve()
    applicability = str(entry.get("applicability", "not-yet-classified"))
    if applicability not in APPLICABILITY_VALUES:
        raise ValueError(
            f"invalid applicability for {repository}: {applicability!r}"
        )
    rationale = str(entry.get("rationale", "")).strip()
    if not rationale:
        raise ValueError(f"applicability rationale is required for {repository}")
    profile_path = str(entry.get("profile_path", DEFAULT_PROFILE))
    report = ScanReport(
        repository=repository,
        root=str(root),
        applicability=applicability,
        rationale=rationale,
        source_revision=_git(root, "rev-parse", "HEAD"),
        platforms=sorted(str(value) for value in entry.get("platforms", [])),
        languages=sorted(str(value) for value in entry.get("languages", [])),
        profile_path=profile_path,
    )

    if applicability == "out-of-scope":
        report.findings.append(
            _not_applicable(
                "AES-SEC-002-SCOPE-001",
                f"Repository is out of scope: {rationale}",
            )
        )
        return report
    if applicability == "not-yet-classified":
        report.findings.append(
            EvidenceFinding(
                rule_id="AES-SEC-002-SCOPE-001",
                status="untested",
                severity="review",
                message=f"Applicability classification remains open: {rationale}",
            )
        )
        return report

    files = sorted(_iter_files(root))
    profile = root / profile_path
    report.findings.append(
        EvidenceFinding(
            rule_id="AES-SEC-002-PROFILE-001",
            status="present" if profile.is_file() else "absent-evidence",
            severity="informational" if profile.is_file() else "review",
            message=(
                "Required local AES-SEC-002 profile is present."
                if profile.is_file()
                else "Required local AES-SEC-002 profile is absent."
            ),
            path=profile_path,
        )
    )
    report.findings.extend(_scan_bridge(root, files, entry))
    report.findings.append(_scan_swift(root, files))
    report.findings.extend(_scan_native_apis(root, files))
    report.findings.extend(_scan_keys_and_storage(root, files, entry))
    report.findings.extend(
        _scan_dependencies_and_repository(root, files, entry)
    )
    report.findings.extend(_scan_platforms(root, files, entry))

    waiver_path = str(entry.get("waiver_path", DEFAULT_WAIVER_LOG))
    report.findings.append(
        EvidenceFinding(
            rule_id="AES-SEC-002-WAIVER-001",
            status="present"
            if (root / waiver_path).is_file()
            else "absent-evidence",
            severity="informational"
            if (root / waiver_path).is_file()
            else "review",
            message=(
                "AES-SEC-002 waiver representation is present."
                if (root / waiver_path).is_file()
                else "AES-SEC-002 waiver representation is absent."
            ),
            path=waiver_path,
        )
    )
    report.findings.sort(
        key=lambda finding: (
            finding.rule_id,
            finding.status,
            finding.path or "",
            finding.line or 0,
        )
    )
    return report


def format_markdown(report: ScanReport) -> str:
    data = report.to_dict()
    summary = data["summary"]
    lines = [
        f"# AES-SEC-002 Reporting Baseline: `{report.repository}`",
        "",
        "- Mode: `reporting`",
        f"- Applicability: `{report.applicability}`",
        f"- Rationale: {report.rationale}",
        f"- Source revision: `{report.source_revision or 'unversioned'}`",
        f"- Platforms: `{', '.join(report.platforms) or 'none declared'}`",
        f"- Languages: `{', '.join(report.languages) or 'none declared'}`",
        f"- Result: `{report.result}`",
        f"- Violations: `{summary['violation']}`",
        f"- Absent evidence: `{summary['absent-evidence']}`",
        f"- Untested: `{summary['untested']}`",
        f"- Non-applicable: `{summary['not-applicable']}`",
        "",
        "## Findings",
        "",
        "| Rule | Status | Severity | Evidence path | Message |",
        "|---|---|---|---|---|",
    ]
    for finding in report.findings:
        path = (
            f"`{finding.path}:{finding.line}`"
            if finding.path and finding.line
            else f"`{finding.path}`" if finding.path else ""
        )
        if not path:
            path = "`none`"
        message = finding.message.replace("|", "\\|")
        lines.append(
            f"| [`{finding.rule_id}`]({RULES[finding.rule_id][1]}) | "
            f"`{finding.status}` | `{finding.severity}` | {path} | {message} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "This is reporting evidence, not a blocking gate or a certification. "
            "Absent evidence is not automatically a violation, and a detected "
            "signal is not proof that the underlying contract is correct.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    args = parse_args()
    root = Path(args.root)
    if not root.is_dir():
        print(f"error: scan root is not a directory: {root}", file=sys.stderr)
        return 2
    repository = args.repo_name or root.resolve().name
    if args.applicability:
        entry: dict[str, Any] = {
            "full_name": repository,
            "applicability": args.applicability,
            "rationale": args.rationale,
        }
    else:
        try:
            entry = load_config_entry(Path(args.config), repository)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
    try:
        report = scan(root, repository=repository, entry=entry)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.format == "json":
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    else:
        print(format_markdown(report), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
