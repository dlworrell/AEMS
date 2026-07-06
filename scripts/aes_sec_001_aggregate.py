#!/usr/bin/env python3
"""Aggregate AES-SEC-001 scanner.

This script reads the AEMS repository manifest, checks out the listed repositories,
runs the local AES-SEC-001 scanner against each checkout, and writes one ecosystem
adoption report.

The runner is intentionally dependency-free. It requires Python 3 and `git`.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aes_sec_001_scan import ScanReport, scan

DEFAULT_MANIFEST = Path("config/aes-sec-001-repositories.json")


@dataclass
class RepositoryEntry:
    full_name: str
    role: str
    ownership: str
    expected_profile: bool
    notes: str = ""


@dataclass
class AggregateEntry:
    repository: RepositoryEntry
    status: str
    checkout_path: str | None = None
    scan: dict[str, Any] | None = None
    error: str | None = None

    @property
    def project_owned(self) -> bool:
        return self.repository.ownership == "project-owned"

    @property
    def expected_to_pass_gate(self) -> bool:
        return self.project_owned and self.repository.expected_profile

    @property
    def passes_expected_gate(self) -> bool:
        if self.status != "scanned" or self.scan is None:
            return not self.expected_to_pass_gate
        if not self.expected_to_pass_gate:
            return True
        summary = self.scan.get("summary", {})
        return bool(summary.get("passes_minimum_adoption_gate", False))

    @property
    def findings(self) -> list[dict[str, Any]]:
        if not isinstance(self.scan, dict):
            return []
        findings = self.scan.get("findings", [])
        if not isinstance(findings, list):
            return []
        return [finding for finding in findings if isinstance(finding, dict)]

    @property
    def banned_finding_count(self) -> int:
        return sum(1 for finding in self.findings if finding.get("severity") == "banned")

    @property
    def review_required_finding_count(self) -> int:
        return sum(1 for finding in self.findings if finding.get("severity") == "review-required")

    def to_dict(self) -> dict[str, Any]:
        return {
            "repository": self.repository.__dict__,
            "status": self.status,
            "checkout_path": self.checkout_path,
            "scan": self.scan,
            "error": self.error,
            "expected_to_pass_gate": self.expected_to_pass_gate,
            "passes_expected_gate": self.passes_expected_gate,
            "banned_finding_count": self.banned_finding_count,
            "review_required_finding_count": self.review_required_finding_count,
        }


@dataclass
class AggregateReport:
    standard: str
    standard_repository: str
    standard_path: str
    entries: list[AggregateEntry] = field(default_factory=list)

    @property
    def scanned_count(self) -> int:
        return sum(1 for entry in self.entries if entry.status == "scanned")

    @property
    def failed_checkout_count(self) -> int:
        return sum(1 for entry in self.entries if entry.status == "checkout-failed")

    @property
    def expected_gate_failures(self) -> list[AggregateEntry]:
        return [entry for entry in self.entries if not entry.passes_expected_gate]

    @property
    def banned_finding_count(self) -> int:
        return sum(entry.banned_finding_count for entry in self.entries)

    @property
    def review_required_finding_count(self) -> int:
        return sum(entry.review_required_finding_count for entry in self.entries)

    @property
    def passes(self) -> bool:
        return not self.expected_gate_failures

    def to_dict(self) -> dict[str, Any]:
        return {
            "standard": self.standard,
            "standard_repository": self.standard_repository,
            "standard_path": self.standard_path,
            "summary": {
                "repository_count": len(self.entries),
                "scanned_count": self.scanned_count,
                "checkout_failed_count": self.failed_checkout_count,
                "expected_gate_failure_count": len(self.expected_gate_failures),
                "banned_finding_count": self.banned_finding_count,
                "review_required_finding_count": self.review_required_finding_count,
                "passes": self.passes,
            },
            "entries": [entry.to_dict() for entry in self.entries],
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run AES-SEC-001 scans for repositories listed in the AEMS manifest."
    )
    parser.add_argument(
        "--manifest",
        default=str(DEFAULT_MANIFEST),
        help="Path to the repository manifest. Defaults to config/aes-sec-001-repositories.json.",
    )
    parser.add_argument(
        "--work-dir",
        default=None,
        help="Directory where repositories will be cloned. Defaults to a temporary directory.",
    )
    parser.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="markdown",
        help="Report format. Defaults to markdown.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero when an expected project-owned repository fails its gate.",
    )
    parser.add_argument(
        "--include-dangerous-primitives",
        action="store_true",
        help="Also report dangerous primitives that require review but are not outright banned.",
    )
    parser.add_argument(
        "--include-third-party",
        action="store_true",
        help="Scan third-party mirror/fork repositories too. By default they are listed but not scanned.",
    )
    parser.add_argument(
        "--keep-work-dir",
        action="store_true",
        help="Do not delete the temporary work directory after the run.",
    )
    return parser.parse_args()


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise SystemExit(f"error: failed to read manifest {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"error: invalid JSON manifest {path}: {exc}") from exc


def repository_entries(manifest: dict[str, Any]) -> list[RepositoryEntry]:
    entries = []
    for item in manifest.get("repositories", []):
        entries.append(
            RepositoryEntry(
                full_name=str(item["full_name"]),
                role=str(item.get("role", "unknown")),
                ownership=str(item.get("ownership", "unknown")),
                expected_profile=bool(item.get("expected_profile", False)),
                notes=str(item.get("notes", "")),
            )
        )
    return entries


def checkout_dir_for(work_dir: Path, full_name: str) -> Path:
    return work_dir / full_name.replace("/", "__")


def clone_url(full_name: str) -> str:
    return f"https://github.com/{full_name}.git"


def run_git_clone(full_name: str, destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "git",
        "clone",
        "--depth",
        "1",
        "--quiet",
        clone_url(full_name),
        str(destination),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def scan_entry(
    entry: RepositoryEntry,
    work_dir: Path,
    include_dangerous_primitives: bool,
    include_third_party: bool,
) -> AggregateEntry:
    if entry.ownership != "project-owned" and not include_third_party:
        return AggregateEntry(repository=entry, status="not-scanned-third-party")

    destination = checkout_dir_for(work_dir, entry.full_name)
    try:
        run_git_clone(entry.full_name, destination)
    except FileNotFoundError:
        return AggregateEntry(
            repository=entry,
            status="checkout-failed",
            checkout_path=str(destination),
            error="git executable was not found",
        )
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.strip() if exc.stderr else str(exc)
        return AggregateEntry(
            repository=entry,
            status="checkout-failed",
            checkout_path=str(destination),
            error=stderr[:1000],
        )

    try:
        scan_report: ScanReport = scan(destination, entry.full_name, include_dangerous_primitives)
    except Exception as exc:  # noqa: BLE001 - aggregate reporting must continue across repositories.
        return AggregateEntry(
            repository=entry,
            status="scan-failed",
            checkout_path=str(destination),
            error=f"{type(exc).__name__}: {exc}",
        )

    return AggregateEntry(
        repository=entry,
        status="scanned",
        checkout_path=str(destination),
        scan=scan_report.to_dict(),
    )


def build_report(args: argparse.Namespace) -> AggregateReport:
    manifest_path = Path(args.manifest)
    manifest = load_manifest(manifest_path)
    entries = repository_entries(manifest)

    temporary_dir: tempfile.TemporaryDirectory[str] | None = None
    if args.work_dir is None:
        temporary_dir = tempfile.TemporaryDirectory(prefix="aes-sec-001-")
        work_dir = Path(temporary_dir.name)
    else:
        work_dir = Path(args.work_dir)
        work_dir.mkdir(parents=True, exist_ok=True)

    try:
        aggregate = AggregateReport(
            standard=str(manifest.get("standard", "AES-SEC-001")),
            standard_repository=str(manifest.get("standard_repository", "")),
            standard_path=str(manifest.get("standard_path", "")),
        )
        for entry in entries:
            aggregate.entries.append(
                scan_entry(
                    entry,
                    work_dir,
                    args.include_dangerous_primitives,
                    args.include_third_party,
                )
            )
        return aggregate
    finally:
        if temporary_dir is not None and not args.keep_work_dir:
            temporary_dir.cleanup()


def format_bool(value: bool) -> str:
    return "PASS" if value else "FAIL"


def finding_value(finding: dict[str, Any], key: str) -> str:
    value = finding.get(key, "")
    return str(value).replace("|", "\\|")


def format_markdown(report: AggregateReport) -> str:
    lines = [
        "# AES-SEC-001 Ecosystem Adoption Report",
        "",
        f"- Standard: `{report.standard}`",
        f"- Standard repository: `{report.standard_repository}`",
        f"- Standard path: `{report.standard_path}`",
        f"- Repositories listed: `{len(report.entries)}`",
        f"- Repositories scanned: `{report.scanned_count}`",
        f"- Checkout failures: `{report.failed_checkout_count}`",
        f"- Expected gate failures: `{len(report.expected_gate_failures)}`",
        f"- Banned findings: `{report.banned_finding_count}`",
        f"- Review-required findings: `{report.review_required_finding_count}`",
        f"- Aggregate result: `{format_bool(report.passes)}`",
        "",
        "## Repository Results",
        "",
        "| Repository | Role | Ownership | Status | Class | Profile | Waiver Log | Banned Findings | Review Findings | Gate |",
        "|---|---|---|---|---|---:|---:|---:|---:|---:|",
    ]

    for entry in report.entries:
        scan_data = entry.scan or {}
        summary = scan_data.get("summary", {}) if isinstance(scan_data, dict) else {}
        classification = scan_data.get("classification", "n/a") if isinstance(scan_data, dict) else "n/a"
        profile = scan_data.get("secure_profile_present", "n/a") if isinstance(scan_data, dict) else "n/a"
        waiver_log = scan_data.get("waiver_log_present", "n/a") if isinstance(scan_data, dict) else "n/a"
        gate = summary.get("passes_minimum_adoption_gate", "n/a") if isinstance(summary, dict) else "n/a"
        lines.append(
            "| "
            f"`{entry.repository.full_name}` | "
            f"`{entry.repository.role}` | "
            f"`{entry.repository.ownership}` | "
            f"`{entry.status}` | "
            f"`{classification}` | "
            f"`{profile}` | "
            f"`{waiver_log}` | "
            f"`{entry.banned_finding_count}` | "
            f"`{entry.review_required_finding_count}` | "
            f"`{gate}` |"
        )

    if report.expected_gate_failures:
        lines.extend(["", "## Expected Gate Failures", ""])
        for entry in report.expected_gate_failures:
            reason = entry.error or "minimum adoption gate failed"
            lines.append(f"- `{entry.repository.full_name}`: {reason}")
    else:
        lines.extend(["", "## Expected Gate Failures", "", "None."])

    if report.review_required_finding_count:
        lines.extend([
            "",
            "## Review-Required Findings",
            "",
            "These are not gate failures. They identify native-code operations that need review, wrapper decisions, or documented invariants.",
            "",
            "| Repository | Symbol | Path | Line |",
            "|---|---|---|---:|",
        ])
        for entry in report.entries:
            for finding in entry.findings:
                if finding.get("severity") != "review-required":
                    continue
                lines.append(
                    "| "
                    f"`{entry.repository.full_name}` | "
                    f"`{finding_value(finding, 'symbol')}` | "
                    f"`{finding_value(finding, 'path')}` | "
                    f"{finding_value(finding, 'line')} |"
                )
    else:
        lines.extend(["", "## Review-Required Findings", "", "None."])

    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    report = build_report(args)

    if args.format == "json":
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    else:
        print(format_markdown(report))

    if args.strict and not report.passes:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
