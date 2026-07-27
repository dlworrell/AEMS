#!/usr/bin/env python3
"""Discover AES-SEC-001 native controls and run explicit fuzz smoke targets."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field, replace
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Iterable


DEFAULT_PROFILES = Path("config/aes-sec-001-native-profiles.json")
DEFAULT_TARGET_CONFIG = Path(".aems/aes-sec-001-native.json")

SOURCE_EXTENSIONS = {
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
    ".cu",
}

TEXT_EXTENSIONS = SOURCE_EXTENSIONS | {
    ".cmake",
    ".json",
    ".mk",
    ".py",
    ".sh",
    ".yaml",
    ".yml",
}

TEXT_NAMES = {
    "CMakeLists.txt",
    "Makefile",
    "GNUmakefile",
    "meson.build",
}

EXCLUDED_DIRECTORIES = {
    ".git",
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

NON_OPERATIONAL_PREFIXES = {
    "templates",
    "tests/fixtures",
}

SCANNER_NAMES = {
    "aes_sec_001_native.py",
    "aes_sec_001_scan.py",
    "aes_sec_002_scan.py",
}

CONTROL_KINDS = {
    "warnings",
    "static-analysis",
    "sanitizer-test",
}


@dataclass(frozen=True)
class FuzzSmokeResult:
    identifier: str
    command: tuple[str, ...]
    timeout_seconds: int
    status: str
    returncode: int | None
    stdout: str
    stderr: str
    kind: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result = {
            "id": self.identifier,
            "command": list(self.command),
            "timeout_seconds": self.timeout_seconds,
            "status": self.status,
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
        }
        if self.kind is not None:
            result["kind"] = self.kind
        return result


@dataclass
class NativeControlReport:
    repository: str
    root: str
    profile: str | None
    profile_definition: dict[str, Any] | None
    build_systems: list[str] = field(default_factory=list)
    warning_signals: list[str] = field(default_factory=list)
    static_analysis_signals: list[str] = field(default_factory=list)
    sanitizer_signals: list[str] = field(default_factory=list)
    fuzz_harnesses: list[str] = field(default_factory=list)
    fuzz_target_count: int = 0
    control_results: list[FuzzSmokeResult] = field(default_factory=list)
    smoke_results: list[FuzzSmokeResult] = field(default_factory=list)

    @property
    def control_passes(self) -> bool:
        return bool(self.control_results) and all(
            result.status == "passed" for result in self.control_results
        )

    @property
    def smoke_passes(self) -> bool:
        return bool(self.smoke_results) and all(
            result.status == "passed" for result in self.smoke_results
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0.0",
            "standard": "AES-SEC-001",
            "repository": self.repository,
            "root": self.root,
            "profile": self.profile,
            "profile_definition": self.profile_definition,
            "build_systems": self.build_systems,
            "warning_signals": self.warning_signals,
            "static_analysis_signals": self.static_analysis_signals,
            "sanitizer_signals": self.sanitizer_signals,
            "fuzz_harnesses": self.fuzz_harnesses,
            "fuzz_target_count": self.fuzz_target_count,
            "control_results": [
                result.to_dict() for result in self.control_results
            ],
            "smoke_results": [
                result.to_dict() for result in self.smoke_results
            ],
            "summary": {
                "profile_assigned": self.profile_definition is not None,
                "warning_evidence_present": bool(self.warning_signals),
                "static_analysis_evidence_present": bool(
                    self.static_analysis_signals
                ),
                "sanitizer_evidence_present": bool(self.sanitizer_signals),
                "fuzz_harness_present": bool(self.fuzz_harnesses),
                "controls_executed": bool(self.control_results),
                "controls_pass": self.control_passes,
                "smoke_executed": bool(self.smoke_results),
                "smoke_passes": self.smoke_passes,
            },
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Discover native warning/static/sanitizer/fuzz evidence and "
            "optionally run configured fuzz smoke targets."
        )
    )
    parser.add_argument("root", nargs="?", default=".", help="Repository root")
    parser.add_argument("--repo-name", help="Repository owner/name")
    parser.add_argument(
        "--profiles",
        default=str(DEFAULT_PROFILES),
        help="AEMS native profile catalogue",
    )
    parser.add_argument("--profile", help="Assigned native profile identifier")
    parser.add_argument(
        "--target-config",
        default=str(DEFAULT_TARGET_CONFIG),
        help="Repository-local native control and fuzz-target configuration",
    )
    parser.add_argument(
        "--run-controls",
        action="store_true",
        help=(
            "Run configured warning, static-analysis, and sanitizer-test "
            "commands without a shell"
        ),
    )
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Run configured fuzz targets without a shell",
    )
    parser.add_argument(
        "--format", choices=("json", "markdown"), default="json"
    )
    return parser.parse_args()


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"failed to read {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc


def _iter_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if any(part in EXCLUDED_DIRECTORIES for part in relative.parts[:-1]):
            continue
        relative_text = relative.as_posix()
        if any(
            relative_text == prefix
            or relative_text.startswith(f"{prefix}/")
            for prefix in NON_OPERATIONAL_PREFIXES
        ):
            continue
        if path.name in SCANNER_NAMES or path.name.startswith(
            ("test_aes_sec_001_", "test_aes_sec_002")
        ):
            continue
        if relative_text == "config/aes-sec-001-native-profiles.json":
            continue
        if path.name in TEXT_NAMES or path.suffix.lower() in TEXT_EXTENSIONS:
            yield path


def _read(path: Path) -> str:
    try:
        if path.stat().st_size > 3_000_000:
            return ""
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _signals(root: Path, files: list[Path], pattern: str) -> list[str]:
    expression = re.compile(pattern, re.IGNORECASE)
    result: set[str] = set()
    for path in files:
        text = _read(path)
        if expression.search(text):
            result.add(path.relative_to(root).as_posix())
    return sorted(result)


def _build_systems(root: Path, files: list[Path]) -> list[str]:
    names = {path.name for path in files}
    result = []
    if "CMakeLists.txt" in names:
        result.append("cmake")
    if names & {"Makefile", "GNUmakefile"}:
        result.append("make")
    if "meson.build" in names:
        result.append("meson")
    return result


def _profile(
    catalogue_path: Path, identifier: str | None
) -> dict[str, Any] | None:
    if identifier is None:
        return None
    catalogue = _load_json(catalogue_path)
    if not isinstance(catalogue, dict):
        raise ValueError("native profile catalogue must be an object")
    profiles = catalogue.get("profiles")
    if not isinstance(profiles, dict) or identifier not in profiles:
        raise ValueError(f"unknown native profile: {identifier}")
    definition = profiles[identifier]
    if not isinstance(definition, dict):
        raise ValueError(f"native profile {identifier} must be an object")
    return definition


def load_target_config(path: Path, *, required: bool) -> dict[str, Any]:
    if not path.is_file():
        if required:
            raise ValueError(f"fuzz target configuration is missing: {path}")
        return {}
    value = _load_json(path)
    if not isinstance(value, dict):
        raise ValueError("native target configuration must be an object")
    if value.get("schema_version") != "1.0.0":
        raise ValueError("native target configuration schema_version must be 1.0.0")
    return value


def run_fuzz_targets(
    root: Path, target_config: dict[str, Any]
) -> list[FuzzSmokeResult]:
    raw_targets = target_config.get("fuzz_targets", [])
    if not isinstance(raw_targets, list):
        raise ValueError("fuzz_targets must be a list")
    if not raw_targets:
        raise ValueError("fuzz_targets must contain at least one smoke target")

    results: list[FuzzSmokeResult] = []
    seen: set[str] = set()
    for raw in raw_targets:
        if not isinstance(raw, dict):
            raise ValueError("each fuzz target must be an object")
        identifier = str(raw.get("id", "")).strip()
        if not identifier or identifier in seen:
            raise ValueError("fuzz target ids must be non-empty and unique")
        seen.add(identifier)
        command = raw.get("command")
        if (
            not isinstance(command, list)
            or not command
            or not all(isinstance(value, str) and value for value in command)
        ):
            raise ValueError(f"{identifier}: command must be a non-empty string list")
        timeout = int(raw.get("timeout_seconds", 30))
        if timeout < 1 or timeout > 300:
            raise ValueError(f"{identifier}: timeout_seconds must be from 1 through 300")
        try:
            completed = subprocess.run(
                command,
                cwd=root,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=timeout,
                check=False,
            )
            results.append(
                FuzzSmokeResult(
                    identifier=identifier,
                    command=tuple(command),
                    timeout_seconds=timeout,
                    status="passed" if completed.returncode == 0 else "failed",
                    returncode=completed.returncode,
                    stdout=completed.stdout[-4000:],
                    stderr=completed.stderr[-4000:],
                )
            )
        except FileNotFoundError as exc:
            results.append(
                FuzzSmokeResult(
                    identifier=identifier,
                    command=tuple(command),
                    timeout_seconds=timeout,
                    status="not-executable",
                    returncode=None,
                    stdout="",
                    stderr=str(exc),
                )
            )
        except subprocess.TimeoutExpired as exc:
            results.append(
                FuzzSmokeResult(
                    identifier=identifier,
                    command=tuple(command),
                    timeout_seconds=timeout,
                    status="timed-out",
                    returncode=None,
                    stdout=str(exc.stdout or "")[-4000:],
                    stderr=str(exc.stderr or "")[-4000:],
                )
            )
    return results


def run_control_commands(
    root: Path, target_config: dict[str, Any]
) -> list[FuzzSmokeResult]:
    raw_commands = target_config.get("control_commands", [])
    if not isinstance(raw_commands, list):
        raise ValueError("control_commands must be a list")
    if not raw_commands:
        raise ValueError(
            "control_commands must contain at least one explicit command"
        )

    results: list[FuzzSmokeResult] = []
    seen: set[str] = set()
    for raw in raw_commands:
        if not isinstance(raw, dict):
            raise ValueError("each control command must be an object")
        identifier = str(raw.get("id", "")).strip()
        if not identifier or identifier in seen:
            raise ValueError(
                "control command ids must be non-empty and unique"
            )
        seen.add(identifier)
        kind = str(raw.get("kind", "")).strip()
        if kind not in CONTROL_KINDS:
            allowed = ", ".join(sorted(CONTROL_KINDS))
            raise ValueError(
                f"{identifier}: kind must be one of {allowed}"
            )
        result = run_fuzz_targets(
            root,
            {
                "fuzz_targets": [
                    {
                        "id": identifier,
                        "command": raw.get("command"),
                        "timeout_seconds": raw.get("timeout_seconds", 120),
                    }
                ]
            },
        )[0]
        results.append(replace(result, kind=kind))
    return results


def discover(
    root: Path,
    *,
    repository: str,
    profile_id: str | None,
    profiles_path: Path,
    target_config: dict[str, Any],
    smoke: bool = False,
    run_controls: bool = False,
) -> NativeControlReport:
    root = root.resolve()
    files = sorted(_iter_files(root))
    definition = _profile(profiles_path, profile_id)
    native_files = [
        path for path in files if path.suffix.lower() in SOURCE_EXTENSIONS
    ]
    harnesses = _signals(
        root,
        native_files,
        r"(?:LLVMFuzzerTestOneInput|\bAFL_LOOP\b|honggfuzz|libFuzzer)",
    )
    if not harnesses:
        harnesses = sorted(
            path.relative_to(root).as_posix()
            for path in files
            if "fuzz" in path.relative_to(root).as_posix().lower()
            and path.suffix.lower() in SOURCE_EXTENSIONS
        )

    targets = target_config.get("fuzz_targets", [])
    if not isinstance(targets, list):
        raise ValueError("fuzz_targets must be a list")
    report = NativeControlReport(
        repository=repository,
        root=str(root),
        profile=profile_id,
        profile_definition=definition,
        build_systems=_build_systems(root, files),
        warning_signals=_signals(
            root,
            files,
            r"(?:-Wall|/W4|warning_level\s*=\s*['\"]3|COMPILE_WARNING_AS_ERROR)",
        ),
        static_analysis_signals=_signals(
            root,
            files,
            r"(?:clang-tidy|scan-build|cppcheck|CodeQL|coverity|pvs-studio)",
        ),
        sanitizer_signals=_signals(
            root,
            files,
            r"(?:-fsanitize|AddressSanitizer|UndefinedBehaviorSanitizer|ThreadSanitizer)",
        ),
        fuzz_harnesses=harnesses,
        fuzz_target_count=len(targets),
    )
    if run_controls:
        report.control_results = run_control_commands(root, target_config)
    if smoke:
        report.smoke_results = run_fuzz_targets(root, target_config)
    return report


def format_markdown(report: NativeControlReport) -> str:
    lines = [
        f"# AES-SEC-001 Native Control Report: `{report.repository}`",
        "",
        f"- Profile: `{report.profile or 'unassigned'}`",
        f"- Build systems: `{', '.join(report.build_systems) or 'none'}`",
        f"- Warning signals: `{len(report.warning_signals)}`",
        f"- Static-analysis signals: `{len(report.static_analysis_signals)}`",
        f"- Sanitizer signals: `{len(report.sanitizer_signals)}`",
        f"- Fuzz harnesses: `{len(report.fuzz_harnesses)}`",
        f"- Configured fuzz targets: `{report.fuzz_target_count}`",
        f"- Native controls executed: `{bool(report.control_results)}`",
        f"- Native controls pass: `{report.control_passes}`",
        f"- Fuzz smoke executed: `{bool(report.smoke_results)}`",
        f"- Fuzz smoke passes: `{report.smoke_passes}`",
        "",
        "## Evidence paths",
        "",
        f"- Warnings: {', '.join(f'`{path}`' for path in report.warning_signals) or 'none'}",
        f"- Static analysis: {', '.join(f'`{path}`' for path in report.static_analysis_signals) or 'none'}",
        f"- Sanitizers: {', '.join(f'`{path}`' for path in report.sanitizer_signals) or 'none'}",
        f"- Fuzz harnesses: {', '.join(f'`{path}`' for path in report.fuzz_harnesses) or 'none'}",
    ]
    if report.control_results:
        lines.extend(
            [
                "",
                "## Native control results",
                "",
                "| Control | Kind | Status | Return code | Timeout |",
                "|---|---|---|---:|---:|",
            ]
        )
        for result in report.control_results:
            lines.append(
                f"| `{result.identifier}` | `{result.kind}` | "
                f"`{result.status}` | `{result.returncode}` | "
                f"`{result.timeout_seconds}` |"
            )
    if report.smoke_results:
        lines.extend(
            [
                "",
                "## Fuzz smoke results",
                "",
                "| Target | Status | Return code | Timeout |",
                "|---|---|---:|---:|",
            ]
        )
        for result in report.smoke_results:
            lines.append(
                f"| `{result.identifier}` | `{result.status}` | "
                f"`{result.returncode}` | `{result.timeout_seconds}` |"
            )
    return "\n".join(lines) + "\n"


def main() -> int:
    args = parse_args()
    root = Path(args.root)
    if not root.is_dir():
        print(f"error: repository root is not a directory: {root}", file=sys.stderr)
        return 2
    config_path = Path(args.target_config)
    if not config_path.is_absolute():
        config_path = root / config_path
    try:
        target_config = load_target_config(
            config_path,
            required=args.smoke or args.run_controls,
        )
        profile_id = args.profile or (
            str(target_config["profile"]) if target_config.get("profile") else None
        )
        report = discover(
            root,
            repository=args.repo_name or root.resolve().name,
            profile_id=profile_id,
            profiles_path=Path(args.profiles),
            target_config=target_config,
            smoke=args.smoke,
            run_controls=args.run_controls,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.format == "json":
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    else:
        print(format_markdown(report), end="")
    if args.run_controls and not report.control_passes:
        return 1
    if args.smoke and not report.smoke_passes:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
