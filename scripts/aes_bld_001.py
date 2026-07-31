#!/usr/bin/env python3
"""Validate AES-BLD-001 structure and observable install parity."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from fnmatch import fnmatch
import hashlib
import json
import platform
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any, Iterable


STANDARD = "AES-BLD-001"
SCHEMA_VERSION = "1.0.0"
DEFAULT_PROFILE = Path(".aems/aes-bld-001.json")

REQUIRED_TOOL_COMMANDS: dict[str, tuple[str, ...]] = {
    "cmake": ("cmake", "--version"),
    "ctest": ("ctest", "--version"),
    "clang": ("clang", "--version"),
    "clang-tidy": ("clang-tidy", "--version"),
    "gcc": ("gcc", "--version"),
    "autoconf": ("autoconf", "--version"),
    "automake": ("automake", "--version"),
    "libtoolize": ("libtoolize", "--version"),
    "make": ("make", "--version"),
    "pkg-config": ("pkg-config", "--version"),
}

REQUIRED_CI_JOBS = {
    "cmake-clang",
    "cmake-gcc",
    "autotools-gcc",
    "autotools-clang",
    "clang-tidy",
    "clang-sanitizers",
    "install-parity",
    "distcheck",
}

CONTENT_PARITY_SUFFIXES = {
    ".cmake",
    ".h",
    ".hh",
    ".hpp",
    ".md",
    ".pc",
    ".txt",
}


@dataclass(frozen=True)
class RequirementCheck:
    requirement: str
    status: str
    message: str
    evidence: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "requirement": self.requirement,
            "status": self.status,
            "message": self.message,
            "evidence": list(self.evidence),
        }


@dataclass
class EvidenceReport:
    mode: str
    repository: str
    root: str
    profile: str
    checks: list[RequirementCheck] = field(default_factory=list)
    tools: dict[str, dict[str, str | None]] = field(default_factory=dict)
    manifests: dict[str, list[dict[str, str | None]]] = field(
        default_factory=dict
    )
    waivers: list[dict[str, Any]] = field(default_factory=list)
    generated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )

    @property
    def passes(self) -> bool:
        return all(check.status != "failed" for check in self.checks)

    def to_dict(self) -> dict[str, Any]:
        counts = {
            status: sum(
                check.status == status
                for check in self.checks
            )
            for status in ("passed", "failed", "not-applicable")
        }
        return {
            "schema_version": SCHEMA_VERSION,
            "standard": STANDARD,
            "mode": self.mode,
            "repository": self.repository,
            "root": self.root,
            "profile": self.profile,
            "generated_at": self.generated_at,
            "runner": {
                "system": platform.system(),
                "release": platform.release(),
                "machine": platform.machine(),
                "python": platform.python_version(),
            },
            "tools": self.tools,
            "checks": [check.to_dict() for check in self.checks],
            "manifests": self.manifests,
            "waivers": self.waivers,
            "summary": {
                **counts,
                "result": "PASS" if self.passes else "FAIL",
            },
        }


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"failed to read {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _check(
    checks: list[RequirementCheck],
    requirement: str,
    condition: bool,
    success: str,
    failure: str,
    evidence: Iterable[str] = (),
) -> None:
    checks.append(
        RequirementCheck(
            requirement=requirement,
            status="passed" if condition else "failed",
            message=success if condition else failure,
            evidence=tuple(evidence),
        )
    )


def _not_applicable(
    checks: list[RequirementCheck], requirement: str, message: str
) -> None:
    checks.append(
        RequirementCheck(
            requirement=requirement,
            status="not-applicable",
            message=message,
        )
    )


def _profile_path(root: Path, profile_path: Path) -> Path:
    return profile_path if profile_path.is_absolute() else root / profile_path


def _existing_paths(root: Path, paths: Iterable[str]) -> list[str]:
    return sorted(path for path in paths if (root / path).is_file())


def _tool_versions() -> dict[str, dict[str, str | None]]:
    result: dict[str, dict[str, str | None]] = {}
    for name, command in REQUIRED_TOOL_COMMANDS.items():
        executable = shutil.which(command[0])
        if executable is None:
            result[name] = {"status": "missing", "version": None}
            continue
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
        output = completed.stdout or completed.stderr
        first_line = output.splitlines()[0].strip() if output else ""
        result[name] = {
            "status": "available" if completed.returncode == 0 else "failed",
            "version": first_line or None,
        }
    return result


def _waivers(
    root: Path,
    profile: dict[str, Any],
    repository: str,
) -> tuple[list[dict[str, Any]], bool, str]:
    waiver_path = profile.get("waiver_log")
    if not isinstance(waiver_path, str) or not waiver_path:
        return [], False, "Profile does not declare a waiver log."
    resolved = root / waiver_path
    try:
        value = _read_json(resolved)
    except ValueError as exc:
        return [], False, str(exc)
    entries = value.get("waivers")
    if (
        value.get("schema_version") != SCHEMA_VERSION
        or value.get("standard") != STANDARD
        or value.get("repository") != repository
        or not isinstance(entries, list)
    ):
        return (
            [],
            False,
            "Waiver log schema, standard, repository, or waiver list is invalid.",
        )

    normalized: list[dict[str, Any]] = []
    valid = True
    messages: list[str] = []
    required = {
        "requirement",
        "rationale",
        "owner",
        "reviewer",
        "compensating_validation",
        "expires_on",
    }
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict) or not required <= set(entry):
            valid = False
            messages.append(f"waiver[{index}] is malformed")
            continue
        if (
            re.fullmatch(
                r"AES-BLD-001-R\d{3}",
                str(entry.get("requirement", "")),
            )
            is None
            or any(
                not isinstance(entry.get(field), str)
                or not str(entry[field]).strip()
                for field in required - {"expires_on"}
            )
        ):
            valid = False
            messages.append(f"waiver[{index}] has invalid required values")
            continue
        try:
            expires_on = date.fromisoformat(str(entry["expires_on"]))
        except ValueError:
            valid = False
            messages.append(f"waiver[{index}] has an invalid expiry date")
            continue
        state = "active" if expires_on >= date.today() else "expired"
        if state == "expired":
            valid = False
            messages.append(
                f"{entry['requirement']} waiver expired {expires_on.isoformat()}"
            )
        normalized.append({**entry, "state": state})
    return (
        normalized,
        valid,
        "; ".join(messages) if messages else "waiver log is valid",
    )


def _preset_names(
    preset_data: dict[str, Any], key: str
) -> set[str]:
    entries = preset_data.get(key, [])
    if not isinstance(entries, list):
        return set()
    return {
        entry["name"]
        for entry in entries
        if isinstance(entry, dict) and isinstance(entry.get("name"), str)
    }


def validate_structure(
    root: Path,
    *,
    profile_path: Path = DEFAULT_PROFILE,
    require_tools: bool = False,
) -> EvidenceReport:
    root = root.resolve()
    resolved_profile = _profile_path(root, profile_path)
    profile_display = str(resolved_profile.relative_to(root))

    try:
        profile = _read_json(resolved_profile)
    except ValueError as exc:
        return EvidenceReport(
            mode="structure",
            repository="unknown",
            root=str(root),
            profile=profile_display,
            checks=[
                RequirementCheck(
                    requirement="AES-BLD-001-R010",
                    status="failed",
                    message=str(exc),
                )
            ],
        )

    repository = str(profile.get("repository", "unknown"))
    report = EvidenceReport(
        mode="structure",
        repository=repository,
        root=str(root),
        profile=profile_display,
    )
    checks = report.checks

    applicability = profile.get("applicability")
    waivers, waiver_log_ok, waiver_message = _waivers(
        root,
        profile,
        repository,
    )
    report.waivers = waivers
    authority = profile.get("authority", {})
    if not isinstance(authority, dict):
        authority = {}
    _check(
        checks,
        "AES-BLD-001-R001",
        (
            profile.get("standard") == STANDARD
            and authority.get("repository") == "dlworrell/AES"
            and authority.get("requirement_source")
            == (
                "standards/AES-BLD-001-native-build-toolchain-and-"
                "distribution-parity.md"
            )
        ),
        "Profile traces to the AES authority and adopted standard.",
        "Profile does not trace to the adopted AES-BLD-001 authority.",
        (profile_display,),
    )

    profile_document = profile.get(
        "profile_document",
        "docs/engineering/AES-BLD-001-toolchain-profile.md",
    )
    profile_document_exists = (
        isinstance(profile_document, str)
        and (root / profile_document).is_file()
    )
    _check(
        checks,
        "AES-BLD-001-R010",
        (
            profile.get("schema_version") == SCHEMA_VERSION
            and profile_document_exists
            and waiver_log_ok
            and applicability
            in {"active-native", "planned-native", "not-applicable"}
        ),
        "Machine-readable and human-readable toolchain profiles are present.",
        (
            "Toolchain profile schema, applicability, profile document, "
            f"or waiver log is invalid: {waiver_message}"
        ),
        (
            profile_display,
            str(profile_document),
            str(profile.get("waiver_log")),
        ),
    )

    if applicability != "active-native":
        for requirement in (
            "AES-BLD-001-R002",
            "AES-BLD-001-R003",
            "AES-BLD-001-R004",
            "AES-BLD-001-R011",
            "AES-BLD-001-R020",
            "AES-BLD-001-R021",
            "AES-BLD-001-R022",
            "AES-BLD-001-R023",
            "AES-BLD-001-R024",
            "AES-BLD-001-R025",
            "AES-BLD-001-R026",
            "AES-BLD-001-R030",
            "AES-BLD-001-R031",
            "AES-BLD-001-R032",
            "AES-BLD-001-R033",
            "AES-BLD-001-R034",
            "AES-BLD-001-R035",
            "AES-BLD-001-R036",
            "AES-BLD-001-R040",
            "AES-BLD-001-R041",
            "AES-BLD-001-R042",
            "AES-BLD-001-R043",
            "AES-BLD-001-R044",
            "AES-BLD-001-R045",
            "AES-BLD-001-R050",
            "AES-BLD-001-R051",
            "AES-BLD-001-R060",
            "AES-BLD-001-R061",
            "AES-BLD-001-R062",
        ):
            _not_applicable(
                checks,
                requirement,
                f"Repository applicability is {applicability!r}.",
            )
        return report

    build = profile.get("build", {})
    cmake = profile.get("cmake", {})
    autotools = profile.get("autotools", {})
    parity = profile.get("parity", {})
    ci = profile.get("ci", {})
    tools = profile.get("tools", {})
    for name, value in (
        ("build", build),
        ("cmake", cmake),
        ("autotools", autotools),
        ("parity", parity),
        ("ci", ci),
        ("tools", tools),
    ):
        if not isinstance(value, dict):
            checks.append(
                RequirementCheck(
                    requirement="AES-BLD-001-R010",
                    status="failed",
                    message=f"Profile field {name!r} must be an object.",
                )
            )

    production_sources = build.get("production_sources", [])
    normative_tests = build.get("normative_tests", [])
    consumer_sources = build.get("consumer_sources", [])
    build_kind = build.get("kind")
    declared_sources = (
        isinstance(production_sources, list)
        and bool(production_sources)
        and not (
            set(production_sources)
            - set(_existing_paths(root, production_sources))
        )
    )
    _check(
        checks,
        "AES-BLD-001-R002",
        declared_sources,
        "Repository-owned production sources and targets are declared.",
        "Production sources are absent, missing, or not repository-owned.",
        tuple(str(item) for item in production_sources)
        if isinstance(production_sources, list)
        else (),
    )
    _check(
        checks,
        "AES-BLD-001-R003",
        profile.get("independent_frontends") is True,
        "CMake and Autotools are declared independent.",
        "Independent frontend operation is not declared.",
        (profile_display,),
    )
    _check(
        checks,
        "AES-BLD-001-R004",
        profile.get("no_hidden_build") is True,
        "No hidden third build implementation is declared.",
        "Profile does not prohibit a hidden third build implementation.",
        (profile_display,),
    )

    required_tool_value = tools.get("required", [])
    declared_tool_names = (
        set(required_tool_value)
        if isinstance(required_tool_value, list)
        and all(isinstance(item, str) for item in required_tool_value)
        else set()
    )
    minimum_versions = tools.get("minimum_versions")
    tool_declaration_ok = (
        isinstance(minimum_versions, dict)
        and declared_tool_names == set(REQUIRED_TOOL_COMMANDS)
        and set(REQUIRED_TOOL_COMMANDS) <= set(minimum_versions)
    )
    if require_tools:
        report.tools = _tool_versions()
        tool_declaration_ok = tool_declaration_ok and all(
            value["status"] == "available"
            for value in report.tools.values()
        )
    _check(
        checks,
        "AES-BLD-001-R011",
        tool_declaration_ok,
        "Required tool policy and exact available versions are recorded.",
        "Required tool declarations are incomplete or a required tool is unavailable.",
        tuple(
            f"{name}: {value.get('version') or value.get('status')}"
            for name, value in sorted(report.tools.items())
        )
        if report.tools
        else tuple(sorted(declared_tool_names)),
    )

    cmake_path = root / "CMakeLists.txt"
    cmake_text = _text(cmake_path)
    _check(
        checks,
        "AES-BLD-001-R020",
        (
            cmake_path.is_file()
            and "cmake_minimum_required" in cmake_text
            and re.search(r"\bproject\s*\(", cmake_text) is not None
            and re.search(r"\binstall\s*\(", cmake_text) is not None
        ),
        "Root CMake project declares the project and installation.",
        "Root CMake project or required project/install declarations are missing.",
        ("CMakeLists.txt",),
    )

    presets_path = root / "CMakePresets.json"
    try:
        preset_data = _read_json(presets_path)
    except ValueError:
        preset_data = {}
    configure_names = _preset_names(preset_data, "configurePresets")
    build_names = _preset_names(preset_data, "buildPresets")
    test_names = _preset_names(preset_data, "testPresets")
    declared_presets = cmake.get("presets", {})
    if not isinstance(declared_presets, dict):
        declared_presets = {}
    binary_dirs = cmake.get("binary_dirs", {})
    if not isinstance(binary_dirs, dict):
        binary_dirs = {}
    required_presets = {
        declared_presets.get("clang"),
        declared_presets.get("gcc"),
        declared_presets.get("sanitizers"),
    }
    required_presets.discard(None)
    _check(
        checks,
        "AES-BLD-001-R021",
        (
            presets_path.is_file()
            and len(required_presets) == 3
            and required_presets <= configure_names
            and required_presets <= build_names
            and required_presets <= test_names
            and set(binary_dirs) == {"clang", "gcc", "sanitizers"}
            and all(
                isinstance(path, str)
                and path.startswith("build/")
                and ".." not in Path(path).parts
                for path in binary_dirs.values()
            )
        ),
        "Checked-in CMake configure/build/test presets cover Clang, GCC, and sanitizers.",
        "CMake presets do not cover all required configure/build/test paths.",
        tuple(sorted(str(item) for item in required_presets)),
    )

    cmake_tests_ok = (
        isinstance(normative_tests, list)
        and bool(normative_tests)
        and all(
            isinstance(test, dict)
            and isinstance(test.get("source"), str)
            and (root / test["source"]).is_file()
            and isinstance(test.get("cmake"), str)
            and test["source"] in cmake_text
            and test["cmake"] in cmake_text
            for test in normative_tests
        )
    )
    _check(
        checks,
        "AES-BLD-001-R022",
        cmake_tests_ok
        and (
            "enable_testing" in cmake_text
            or re.search(
                r"\binclude\s*\(\s*CTest(?:\s|\))",
                cmake_text,
                re.IGNORECASE,
            )
            is not None
        ),
        "Normative tests are registered with CTest.",
        "CTest registration is missing or does not cover normative tests.",
        tuple(
            str(test.get("source"))
            for test in normative_tests
            if isinstance(test, dict)
        )
        if isinstance(normative_tests, list)
        else (),
    )

    preset_text = _text(presets_path)
    _check(
        checks,
        "AES-BLD-001-R023",
        "CMAKE_EXPORT_COMPILE_COMMANDS" in f"{cmake_text}\n{preset_text}",
        "Canonical CMake path exports compile_commands.json.",
        "CMake compilation-database export is not enabled.",
        ("CMakeLists.txt", "CMakePresets.json"),
    )
    _check(
        checks,
        "AES-BLD-001-R024",
        (root / ".clang-tidy").is_file(),
        "Repository owns a Clang-Tidy configuration.",
        "Repository .clang-tidy configuration is missing.",
        (".clang-tidy",),
    )
    sanitizer_name = declared_presets.get("sanitizers")
    sanitizer_entry = next(
        (
            entry
            for entry in preset_data.get("configurePresets", [])
            if isinstance(entry, dict)
            and entry.get("name") == sanitizer_name
        ),
        {},
    )
    sanitizer_cache = sanitizer_entry.get("cacheVariables", {})
    _check(
        checks,
        "AES-BLD-001-R025",
        (
            isinstance(sanitizer_cache, dict)
            and any(
                "SANIT" in str(key).upper()
                and str(value).upper() in {"ON", "TRUE", "1"}
                for key, value in sanitizer_cache.items()
            )
        ),
        "Clang sanitizer preset explicitly enables sanitizer instrumentation.",
        "Sanitizer preset does not explicitly enable sanitizers.",
        (f"CMakePresets.json:{sanitizer_name}",),
    )

    pkg_config = build.get("pkg_config", {})
    pkg_path = pkg_config.get("path") if isinstance(pkg_config, dict) else None
    cmake_install_ok = "GNUInstallDirs" in cmake_text and (
        build_kind != "c-library"
        or (
            isinstance(pkg_path, str)
            and (root / pkg_path).is_file()
        )
    )
    _check(
        checks,
        "AES-BLD-001-R026",
        cmake_install_ok,
        "CMake install contract uses GNUInstallDirs and package metadata.",
        "CMake install contract lacks GNUInstallDirs or package metadata.",
        ("CMakeLists.txt", str(pkg_path or "not-required")),
    )

    configure_path = root / "configure.ac"
    automake_path = root / "Makefile.am"
    configure_text = _text(configure_path)
    automake_text = _text(automake_path)
    autotools_structure_ok = (
        configure_path.is_file()
        and automake_path.is_file()
        and (root / "m4").is_dir()
        and (root / "build-aux").is_dir()
        and (
            build_kind != "c-library"
            or "LT_INIT" in configure_text
        )
    )
    _check(
        checks,
        "AES-BLD-001-R030",
        autotools_structure_ok,
        "Autoconf, Automake, auxiliary, macro, and required Libtool inputs are present.",
        "GNU Autotools structure or required Libtool initialization is missing.",
        ("configure.ac", "Makefile.am", "m4", "build-aux"),
    )
    bootstrap = autotools.get("bootstrap")
    _check(
        checks,
        "AES-BLD-001-R031",
        (
            autotools.get("out_of_tree") is True
            and isinstance(bootstrap, list)
            and bootstrap[:2] == ["autoreconf", "-fvi"]
        ),
        "GNU bootstrap and out-of-tree build contract is declared.",
        "GNU bootstrap or out-of-tree build contract is incomplete.",
        tuple(str(item) for item in bootstrap)
        if isinstance(bootstrap, list)
        else (),
    )
    compilers = set(autotools.get("compilers", []))
    _check(
        checks,
        "AES-BLD-001-R032",
        {"gcc", "make"} <= compilers,
        "GNU path declares GCC and GNU Make.",
        "GNU path does not declare both GCC and GNU Make.",
        tuple(sorted(compilers)),
    )
    _check(
        checks,
        "AES-BLD-001-R033",
        (
            "clang" in compilers
            and isinstance(declared_presets.get("gcc"), str)
        ),
        "Cross-frontend compiler interchange is declared.",
        "Autotools+Clang or CMake+GCC interchange is missing.",
        tuple(sorted(compilers | required_presets)),
    )

    automake_tests_ok = (
        isinstance(normative_tests, list)
        and bool(normative_tests)
        and all(
            isinstance(test, dict)
            and isinstance(test.get("autotools"), str)
            and test.get("source") in automake_text
            and test["autotools"] in automake_text
            for test in normative_tests
        )
    )
    _check(
        checks,
        "AES-BLD-001-R034",
        automake_tests_ok and "TESTS" in automake_text,
        "Normative tests are registered with Automake.",
        "Automake test harness does not cover normative tests.",
        ("Makefile.am",),
    )

    expected_install_paths = parity.get("expected_install_paths", [])
    _check(
        checks,
        "AES-BLD-001-R035",
        (
            autotools.get("uninstall") is True
            and isinstance(expected_install_paths, list)
            and bool(expected_install_paths)
        ),
        "GNU staged install and uninstall contract is declared.",
        "GNU staged install or uninstall contract is incomplete.",
        tuple(str(item) for item in expected_install_paths)
        if isinstance(expected_install_paths, list)
        else (),
    )
    release_capable = build.get("release_capable") is True
    _check(
        checks,
        "AES-BLD-001-R036",
        not release_capable or autotools.get("distcheck") is True,
        "Source-distribution validation is declared where applicable.",
        "Release-capable repository does not declare make distcheck.",
        (profile_display,),
    )

    source_parity_ok = (
        isinstance(production_sources, list)
        and bool(production_sources)
        and all(
            isinstance(source, str)
            and source in cmake_text
            and source in automake_text
            for source in production_sources
        )
    )
    _check(
        checks,
        "AES-BLD-001-R040",
        source_parity_ok,
        "Production source inventory is represented in both frontends.",
        "Production source inventory has CMake/Automake drift.",
        tuple(str(item) for item in production_sources)
        if isinstance(production_sources, list)
        else (),
    )
    option_mappings = build.get("option_mappings")
    option_mapping_ok = (
        isinstance(option_mappings, list)
        and bool(option_mappings)
        and all(
        isinstance(item, dict)
        and {"id", "cmake", "autotools", "default"} <= set(item)
        for item in option_mappings
        )
    )
    _check(
        checks,
        "AES-BLD-001-R041",
        option_mapping_ok,
        "Target and feature-option parity is explicitly mapped.",
        "Target and feature-option parity mapping is missing or malformed.",
        tuple(
            str(item.get("id"))
            for item in option_mappings
            if isinstance(item, dict)
        )
        if isinstance(option_mappings, list)
        else (),
    )
    _check(
        checks,
        "AES-BLD-001-R042",
        cmake_tests_ok and automake_tests_ok,
        "Normative test inventory is shared by both frontends.",
        "Normative test inventory differs between CTest and Automake.",
        tuple(
            str(test.get("source"))
            for test in normative_tests
            if isinstance(test, dict)
        )
        if isinstance(normative_tests, list)
        else (),
    )
    _check(
        checks,
        "AES-BLD-001-R043",
        (
            isinstance(expected_install_paths, list)
            and bool(expected_install_paths)
            and isinstance(parity.get("metadata_exclusions"), list)
        ),
        "Install-manifest contract and explicit exclusions are declared.",
        "Install-manifest contract or exclusion declaration is missing.",
        tuple(str(item) for item in expected_install_paths)
        if isinstance(expected_install_paths, list)
        else (),
    )
    if build_kind == "c-library":
        _check(
            checks,
            "AES-BLD-001-R044",
            parity.get("symbol_check") is True,
            "ABI-facing symbol parity is required for the library.",
            "Library profile does not require symbol parity.",
            (profile_display,),
        )
    else:
        _not_applicable(
            checks,
            "AES-BLD-001-R044",
            "ABI-facing symbol comparison applies to library repositories.",
        )
    consumer_ok = (
        isinstance(consumer_sources, list)
        and bool(consumer_sources)
        and not (
            set(consumer_sources)
            - set(_existing_paths(root, consumer_sources))
        )
    )
    if build_kind == "c-library":
        _check(
            checks,
            "AES-BLD-001-R045",
            consumer_ok,
            "Downstream consumer smoke source is present.",
            "Library downstream consumer smoke source is missing.",
            tuple(str(item) for item in consumer_sources)
            if isinstance(consumer_sources, list)
            else (),
        )
    else:
        _not_applicable(
            checks,
            "AES-BLD-001-R045",
            "Downstream library-consumer smoke applies to library repositories.",
        )

    jobs = set(ci.get("jobs", []))
    _check(
        checks,
        "AES-BLD-001-R050",
        REQUIRED_CI_JOBS <= jobs,
        "CI profile declares every required build and parity job.",
        "CI profile omits one or more required AES-BLD-001 jobs.",
        tuple(sorted(jobs)),
    )
    evidence_output = ci.get("evidence_output")
    _check(
        checks,
        "AES-BLD-001-R051",
        (
            isinstance(evidence_output, str)
            and evidence_output.startswith("build/aems/aes-bld-001/")
            and waiver_log_ok
        ),
        "Machine-readable evidence output is declared under the AEMS build root.",
        (
            "AEMS evidence output path or active-waiver evidence is invalid: "
            f"{waiver_message}"
        ),
        (str(evidence_output), str(profile.get("waiver_log"))),
    )
    generated_paths = build.get("generated_paths")
    _check(
        checks,
        "AES-BLD-001-R060",
        (
            isinstance(generated_paths, list)
            and {"build", "autom4te.cache"} <= set(generated_paths)
        ),
        "Generated build/bootstrap paths are explicitly isolated.",
        "Generated build/bootstrap path policy is incomplete.",
        tuple(str(item) for item in generated_paths)
        if isinstance(generated_paths, list)
        else (),
    )
    _check(
        checks,
        "AES-BLD-001-R061",
        build.get("offline_after_bootstrap") is True,
        "Build, test, and install are declared offline after dependency bootstrap.",
        "Offline build boundary is not declared.",
        (profile_display,),
    )
    workflow = ci.get("workflow")
    _check(
        checks,
        "AES-BLD-001-R062",
        isinstance(workflow, str) and (root / workflow).is_file(),
        "Repository CI reproduces the declared command surface.",
        "Repository AES-BLD-001 workflow is missing.",
        (str(workflow),),
    )
    return report


def _excluded(relative: str, patterns: Iterable[str]) -> bool:
    return any(
        relative == pattern or fnmatch(relative, pattern)
        for pattern in patterns
    )


def _digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(131072), b""):
            hasher.update(block)
    return f"sha256:{hasher.hexdigest()}"


def _manifest(
    root: Path, exclusions: Iterable[str]
) -> dict[str, dict[str, str | None]]:
    result: dict[str, dict[str, str | None]] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file() and not path.is_symlink():
            continue
        relative = path.relative_to(root).as_posix()
        if _excluded(relative, exclusions):
            continue
        suffix = path.suffix.lower()
        digest = None
        if suffix in CONTENT_PARITY_SUFFIXES or path.name in {
            "LICENSE",
            "COPYING",
            "NOTICE",
        }:
            digest = _digest(path)
        result[relative] = {
            "path": relative,
            "kind": "symlink" if path.is_symlink() else "file",
            "digest": digest,
        }
    return result


def _symbols(path: Path) -> set[str]:
    completed = subprocess.run(
        ["nm", "-g", "--defined-only", str(path)],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if completed.returncode != 0:
        raise ValueError(
            f"nm failed for {path}: {completed.stderr.strip()}"
        )
    result = set()
    for line in completed.stdout.splitlines():
        stripped = line.strip()
        if not stripped or stripped.endswith(":"):
            continue
        fields = stripped.split()
        if len(fields) >= 2:
            symbol = fields[-1]
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.$@]*", symbol):
                result.add(symbol)
    return result


def compare_installs(
    cmake_stage: Path,
    autotools_stage: Path,
    *,
    profile_path: Path,
) -> EvidenceReport:
    cmake_stage = cmake_stage.resolve()
    autotools_stage = autotools_stage.resolve()
    profile = _read_json(profile_path.resolve())
    repository = str(profile.get("repository", "unknown"))
    parity = profile.get("parity", {})
    if not isinstance(parity, dict):
        parity = {}
    exclusions = parity.get("metadata_exclusions", [])
    if not isinstance(exclusions, list):
        exclusions = []

    report = EvidenceReport(
        mode="parity",
        repository=repository,
        root=str(cmake_stage.parent),
        profile=str(profile_path),
    )
    if not cmake_stage.is_dir() or not autotools_stage.is_dir():
        report.checks.append(
            RequirementCheck(
                requirement="AES-BLD-001-R043",
                status="failed",
                message="Both staged installation roots must exist.",
                evidence=(str(cmake_stage), str(autotools_stage)),
            )
        )
        return report

    cmake_manifest = _manifest(cmake_stage, exclusions)
    autotools_manifest = _manifest(autotools_stage, exclusions)
    report.manifests = {
        "cmake": list(cmake_manifest.values()),
        "autotools": list(autotools_manifest.values()),
    }
    cmake_paths = set(cmake_manifest)
    autotools_paths = set(autotools_manifest)
    expected = set(parity.get("expected_install_paths", []))
    shared_paths = cmake_paths & autotools_paths
    content_mismatches = sorted(
        path
        for path in shared_paths
        if cmake_manifest[path]["digest"] is not None
        and cmake_manifest[path]["digest"]
        != autotools_manifest[path]["digest"]
    )
    missing_expected = sorted(
        (expected - cmake_paths) | (expected - autotools_paths)
    )
    manifest_ok = (
        cmake_paths == autotools_paths
        and not content_mismatches
        and not missing_expected
    )
    differences = [
        *(f"cmake-only: {path}" for path in sorted(cmake_paths - autotools_paths)),
        *(
            f"autotools-only: {path}"
            for path in sorted(autotools_paths - cmake_paths)
        ),
        *(f"content-mismatch: {path}" for path in content_mismatches),
        *(f"missing-expected: {path}" for path in missing_expected),
    ]
    _check(
        report.checks,
        "AES-BLD-001-R043",
        manifest_ok,
        "Normalized staged installation manifests are equivalent.",
        "Normalized staged installation manifests differ.",
        differences or tuple(sorted(shared_paths)),
    )

    if parity.get("symbol_check") is True:
        if shutil.which("nm") is None:
            _check(
                report.checks,
                "AES-BLD-001-R044",
                False,
                "",
                "nm is required for configured symbol-parity checks.",
            )
        else:
            libraries = sorted(
                path
                for path in shared_paths
                if path.endswith((".a", ".so", ".dylib"))
            )
            symbol_differences = []
            for relative in libraries:
                try:
                    cmake_symbols = _symbols(cmake_stage / relative)
                    autotools_symbols = _symbols(autotools_stage / relative)
                except ValueError as exc:
                    symbol_differences.append(str(exc))
                    continue
                if cmake_symbols != autotools_symbols:
                    symbol_differences.append(
                        f"{relative}: "
                        f"cmake-only={sorted(cmake_symbols - autotools_symbols)}, "
                        "autotools-only="
                        f"{sorted(autotools_symbols - cmake_symbols)}"
                    )
            _check(
                report.checks,
                "AES-BLD-001-R044",
                bool(libraries) and not symbol_differences,
                "Installed library public symbol sets are equivalent.",
                "Installed library symbol sets differ or no library was found.",
                symbol_differences or libraries,
            )
    else:
        _not_applicable(
            report.checks,
            "AES-BLD-001-R044",
            "Profile does not require symbol comparison.",
        )
    return report


def render_markdown(report: EvidenceReport) -> str:
    data = report.to_dict()
    lines = [
        f"# {STANDARD} Evidence",
        "",
        f"- Repository: `{report.repository}`",
        f"- Mode: `{report.mode}`",
        f"- Result: `{data['summary']['result']}`",
        f"- Passed: `{data['summary']['passed']}`",
        f"- Failed: `{data['summary']['failed']}`",
        f"- Not applicable: `{data['summary']['not-applicable']}`",
        "",
        "## Requirements",
        "",
        "| Requirement | Status | Message |",
        "|---|---|---|",
    ]
    for check in report.checks:
        lines.append(
            f"| `{check.requirement}` | `{check.status}` | "
            f"{check.message.replace('|', '\\|')} |"
        )
    if report.tools:
        lines.extend(
            [
                "",
                "## Tool Versions",
                "",
                "| Tool | Status | Version |",
                "|---|---|---|",
            ]
        )
        for name, value in sorted(report.tools.items()):
            lines.append(
                f"| `{name}` | `{value['status']}` | "
                f"`{value['version'] or 'n/a'}` |"
            )
    return "\n".join(lines) + "\n"


def evidence_errors(value: dict[str, Any]) -> list[str]:
    """Return dependency-free validation errors for an evidence document."""
    errors: list[str] = []
    required = {
        "schema_version",
        "standard",
        "mode",
        "repository",
        "root",
        "profile",
        "generated_at",
        "runner",
        "tools",
        "checks",
        "manifests",
        "waivers",
        "summary",
    }
    missing = sorted(required - set(value))
    if missing:
        errors.append(f"missing top-level fields: {', '.join(missing)}")
    if value.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if value.get("standard") != STANDARD:
        errors.append(f"standard must be {STANDARD}")
    if value.get("mode") not in {"structure", "parity"}:
        errors.append("mode must be structure or parity")
    for field_name in ("repository", "root", "profile", "generated_at"):
        if not isinstance(value.get(field_name), str) or not value.get(
            field_name
        ):
            errors.append(f"{field_name} must be a non-empty string")
    for field_name in ("runner", "tools", "manifests", "summary"):
        if not isinstance(value.get(field_name), dict):
            errors.append(f"{field_name} must be an object")
    if not isinstance(value.get("waivers"), list):
        errors.append("waivers must be an array")

    checks = value.get("checks")
    statuses = {"passed", "failed", "not-applicable"}
    counts = {status: 0 for status in statuses}
    if not isinstance(checks, list) or not checks:
        errors.append("checks must be a non-empty array")
    else:
        seen = set()
        for index, check in enumerate(checks):
            if not isinstance(check, dict):
                errors.append(f"checks[{index}] must be an object")
                continue
            requirement = check.get("requirement")
            if (
                not isinstance(requirement, str)
                or re.fullmatch(r"AES-BLD-001-R\d{3}", requirement) is None
            ):
                errors.append(
                    f"checks[{index}].requirement is not an AES-BLD-001 ID"
                )
            elif requirement in seen:
                errors.append(f"duplicate requirement result: {requirement}")
            else:
                seen.add(requirement)
            status = check.get("status")
            if status not in statuses:
                errors.append(f"checks[{index}].status is invalid")
            else:
                counts[status] += 1
            if not isinstance(check.get("message"), str):
                errors.append(f"checks[{index}].message must be a string")
            evidence = check.get("evidence")
            if (
                not isinstance(evidence, list)
                or not all(isinstance(item, str) for item in evidence)
            ):
                errors.append(
                    f"checks[{index}].evidence must be a string array"
                )

    summary = value.get("summary")
    if isinstance(summary, dict):
        for status, count in counts.items():
            if summary.get(status) != count:
                errors.append(
                    f"summary.{status} does not match requirement results"
                )
        expected = "FAIL" if counts["failed"] else "PASS"
        if summary.get("result") != expected:
            errors.append(f"summary.result must be {expected}")
    return errors


def _write_report(
    report: EvidenceReport, output_format: str, output: Path | None
) -> None:
    if output_format == "json":
        rendered = json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n"
    else:
        rendered = render_markdown(report)
    if output is None:
        sys.stdout.write(rendered)
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate AES-BLD-001 structure and install parity."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    structure = subparsers.add_parser(
        "structure", help="Validate repository build/toolchain structure."
    )
    structure.add_argument("root", nargs="?", default=".")
    structure.add_argument("--profile", default=str(DEFAULT_PROFILE))
    structure.add_argument("--require-tools", action="store_true")
    structure.add_argument("--strict", action="store_true")
    structure.add_argument(
        "--format", choices=("json", "markdown"), default="json"
    )
    structure.add_argument("--output", type=Path)

    parity = subparsers.add_parser(
        "parity", help="Compare CMake and Autotools staged installations."
    )
    parity.add_argument("cmake_stage", type=Path)
    parity.add_argument("autotools_stage", type=Path)
    parity.add_argument("--profile", type=Path, required=True)
    parity.add_argument("--strict", action="store_true")
    parity.add_argument(
        "--format", choices=("json", "markdown"), default="json"
    )
    parity.add_argument("--output", type=Path)

    evidence = subparsers.add_parser(
        "evidence", help="Validate an AES-BLD-001 evidence document."
    )
    evidence.add_argument("evidence_path", type=Path)
    evidence.add_argument("--strict", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.command == "structure":
            report = validate_structure(
                Path(args.root),
                profile_path=Path(args.profile),
                require_tools=args.require_tools,
            )
        elif args.command == "parity":
            report = compare_installs(
                args.cmake_stage,
                args.autotools_stage,
                profile_path=args.profile,
            )
        else:
            value = _read_json(args.evidence_path)
            errors = evidence_errors(value)
            print(
                json.dumps(
                    {
                        "schema_version": SCHEMA_VERSION,
                        "standard": STANDARD,
                        "valid": not errors,
                        "errors": errors,
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return 1 if args.strict and errors else 0
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"aes_bld_001: {exc}", file=sys.stderr)
        return 2
    _write_report(report, args.format, args.output)
    if args.strict and not report.passes:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
