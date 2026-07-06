#!/usr/bin/env python3
"""Aggregate AES-DEV-001 development-principles evidence.

This runner reads the AES-DEV-001 repository manifest, checks out project
repositories, runs the local AES-DEV-001 scanner, and writes one ecosystem report.

The first version reports evidence and gaps. It is intentionally conservative about
hard gates so that legacy repositories can be baselined before the policy ratchets.
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

from aes_dev_001_scan import Dev001Report, scan

DEFAULT_MANIFEST = Path("config/aes-dev-001-repositories.json")


@dataclass
class RepositoryEntry:
    full_name: str
    role: str
    ownership: str
    expected_profile: bool
    profile_required: bool
    local_profile_path: str = ""
    notes: str = ""

    @property
    def project_owned(self) -> bool:
        return self.ownership == "project-owned"


@dataclass
class AggregateEntry:
    repository: RepositoryEntry
    status: str
    checkout_path: str | None = None
    scan: dict[str, Any] | None = None
    error: str | None = None

    @property
    def scanned(self) -> bool:
        return self.status == "scanned" and isinstance(self.scan, dict)

    @property
    def summary(self) -> dict[str, Any]:
        if not self.scanned or self.scan is None:
            return {}
        summary = self.scan.get("summary", {})
        return summary if isinstance(summary, dict) else {}

    @property
    def local_profile_present(self) -> bool:
        return bool(self.summary.get("local_profile_present", False))

    @property
    def specs_present(self) -> bool:
        return bool(self.summary.get("specs_present", False))

    @property
    def adrs_present(self) -> bool:
        return bool(self.summary.get("adrs_present", False))

    @property
    def evidence_present_count(self) -> int:
        return int(self.summary.get("evidence_present_count", 0))

    @property
    def evidence_category_count(self) -> int:
        return int(self.summary.get("evidence_category_count", 0))

    @property
    def ready_for_ratchet(self) -> bool:
        return bool(self.summary.get("ready_for_ratchet", False))

    @property
    def gap_names(self) -> list[str]:
        if self.status == "not-scanned-third-party":
            return []
        if not self.scanned:
            return ["scan-unavailable"]

        gaps = []
        if self.repository.profile_required and not self.local_profile_present:
            gaps.append("local-profile")
        if self.repository.project_owned and self.repository.role not in {"demo-project", "experimental-native-code"}:
            if not self.specs_present:
                gaps.append("specs")
        if self.repository.project_owned and self.repository.role in {
            "system-project",
            "hardware-platform",
            "fpga-platform",
            "system-or-hardware-project",
            "ecosystem-governance",
            "enforcement-orchestrator",
        }:
            if not self.adrs_present:
                gaps.append("adrs")
        if self.evidence_present_count == 0:
            gaps.append("evidence")
        return gaps

    @property
    def has_gaps(self) -> bool:
        return bool(self.gap_names)

    def to_dict(self) -> dict[str, Any]:
        return {
            "repository": self.repository.__dict__,
            "status": self.status,
            "checkout_path": self.checkout_path,
            "scan": self.scan,
            "error": self.error,
            "gaps": self.gap_names,
            "ready_for_ratchet": self.ready_for_ratchet,
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
    def scan_failed_count(self) -> int:
        return sum(1 for entry in self.entries if entry.status == "scan-failed")

    @property
    def project_owned_count(self) -> int:
        return sum(1 for entry in self.entries if entry.repository.project_owned)

    @property
    def project_owned_scanned_count(self) -> int:
        return sum(1 for entry in self.entries if entry.repository.project_owned and entry.status == "scanned")

    @property
    def entries_with_gaps(self) -> list[AggregateEntry]:
        return [entry for entry in self.entries if entry.has_gaps]

    @property
    def profile_gap_count(self) -> int:
        return sum(1 for entry in self.entries if "local-profile" in entry.gap_names)

    @property
    def specs_gap_count(self) -> int:
        return sum(1 for entry in self.entries if "specs" in entry.gap_names)

    @property
    def adr_gap_count(self) -> int:
        return sum(1 for entry in self.entries if "adrs" in entry.gap_names)

    @property
    def evidence_gap_count(self) -> int:
        return sum(1 for entry in self.entries if "evidence" in entry.gap_names)

    @property
    def checkout_or_scan_failures(self) -> list[AggregateEntry]:
        return [entry for entry in self.entries if entry.status in {"checkout-failed", "scan-failed"}]

    @property
    def passes_reporting_gate(self) -> bool:
        return not self.checkout_or_scan_failures

    def to_dict(self) -> dict[str, Any]:
        return {
            "standard": self.standard,
            "standard_repository": self.standard_repository,
            "standard_path": self.standard_path,
            "summary": {
                "repository_count": len(self.entries),
                "project_owned_count": self.project_owned_count,
                "scanned_count": self.scanned_count,
                "project_owned_scanned_count": self.project_owned_scanned_count,
                "checkout_failed_count": self.failed_checkout_count,
                "scan_failed_count": self.scan_failed_count,
                "entries_with_gap_count": len(self.entries_with_gaps),
                "profile_gap_count": self.profile_gap_count,
                "specs_gap_count": self.specs_gap_count,
                "adr_gap_count": self.adr_gap_count,
                "evidence_gap_count": self.evidence_gap_count,
                "passes_reporting_gate": self.passes_reporting_gate,
            },
            "entries": [entry.to_dict() for entry in self.entries],
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run AES-DEV-001 evidence scans for repositories listed in the AEMS manifest."
    )
    parser.add_argument(
        "--manifest",
        default=str(DEFAULT_MANIFEST),
        help="Path to the repository manifest. Defaults to config/aes-dev-001-repositories.json.",
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
        "--include-third-party",
        action="store_true",
        help="Scan third-party mirror/fork repositories too. By default they are listed but not scanned.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero on checkout or scan failure. Does not yet fail on evidence gaps.",
    )
    parser.add_argument(
        "--keep-work-dir",
        action="store_true",
        help="Do not delete the temporary work directory after the run.",
    )
    parser.add_argument(
        "--max-hits",
        type=int,
        default=5,
        help="Maximum sample hits per evidence category per repository. Defaults to 5.",
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
                profile_required=bool(item.get("profile_required", item.get("expected_profile", False))),
                local_profile_path=str(item.get("local_profile_path", "")),
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
    cmd = ["git", "clone", "--depth", "1", "--quiet", clone_url(full_name), str(destination)]
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def scan_entry(entry: RepositoryEntry, work_dir: Path, include_third_party: bool, max_hits: int) -> AggregateEntry:
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
        scan_report: Dev001Report = scan(destination, entry.full_name, max_hits=max_hits)
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
        temporary_dir = tempfile.TemporaryDirectory(prefix="aes-dev-001-")
        work_dir = Path(temporary_dir.name)
    else:
        work_dir = Path(args.work_dir)
        work_dir.mkdir(parents=True, exist_ok=True)

    try:
        aggregate = AggregateReport(
            standard=str(manifest.get("standard", "AES-DEV-001")),
            standard_repository=str(manifest.get("standard_repository", "")),
            standard_path=str(manifest.get("standard_path", "")),
        )
        for entry in entries:
            aggregate.entries.append(scan_entry(entry, work_dir, args.include_third_party, args.max_hits))
        return aggregate
    finally:
        if temporary_dir is not None and not args.keep_work_dir:
            temporary_dir.cleanup()


def format_bool(value: bool) -> str:
    return "PASS" if value else "FAIL"


def format_markdown(report: AggregateReport) -> str:
    lines = [
        "# AES-DEV-001 Ecosystem Evidence Report",
        "",
        f"- Standard: `{report.standard}`",
        f"- Standard repository: `{report.standard_repository}`",
        f"- Standard path: `{report.standard_path}`",
        f"- Repositories listed: `{len(report.entries)}`",
        f"- Project-owned repositories: `{report.project_owned_count}`",
        f"- Repositories scanned: `{report.scanned_count}`",
        f"- Project-owned repositories scanned: `{report.project_owned_scanned_count}`",
        f"- Checkout failures: `{report.failed_checkout_count}`",
        f"- Scan failures: `{report.scan_failed_count}`",
        f"- Repositories with evidence gaps: `{len(report.entries_with_gaps)}`",
        f"- Local profile gaps: `{report.profile_gap_count}`",
        f"- Specification gaps: `{report.specs_gap_count}`",
        f"- ADR gaps: `{report.adr_gap_count}`",
        f"- Evidence gaps: `{report.evidence_gap_count}`",
        f"- Reporting gate: `{format_bool(report.passes_reporting_gate)}`",
        "",
        "## Repository Results",
        "",
        "| Repository | Role | Ownership | Status | Profile | Specs | ADRs | Evidence | Ratchet | Gaps |",
        "|---|---|---|---|---:|---:|---:|---:|---:|---|",
    ]

    for entry in report.entries:
        evidence = f"{entry.evidence_present_count}/{entry.evidence_category_count}" if entry.scanned else "n/a"
        gaps = ", ".join(entry.gap_names) if entry.gap_names else "none"
        lines.append(
            "| "
            f"`{entry.repository.full_name}` | "
            f"`{entry.repository.role}` | "
            f"`{entry.repository.ownership}` | "
            f"`{entry.status}` | "
            f"`{entry.local_profile_present if entry.scanned else 'n/a'}` | "
            f"`{entry.specs_present if entry.scanned else 'n/a'}` | "
            f"`{entry.adrs_present if entry.scanned else 'n/a'}` | "
            f"`{evidence}` | "
            f"`{entry.ready_for_ratchet if entry.scanned else 'n/a'}` | "
            f"`{gaps}` |"
        )

    if report.checkout_or_scan_failures:
        lines.extend(["", "## Checkout or Scan Failures", ""])
        for entry in report.checkout_or_scan_failures:
            reason = entry.error or "unknown failure"
            lines.append(f"- `{entry.repository.full_name}`: {reason}")
    else:
        lines.extend(["", "## Checkout or Scan Failures", "", "None."])

    if report.entries_with_gaps:
        lines.extend(["", "## Evidence Gaps", ""])
        for entry in report.entries_with_gaps:
            lines.append(f"- `{entry.repository.full_name}`: {', '.join(entry.gap_names)}")
    else:
        lines.extend(["", "## Evidence Gaps", "", "None."])

    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    report = build_report(args)

    if args.format == "json":
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    else:
        print(format_markdown(report))

    if args.strict and not report.passes_reporting_gate:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
