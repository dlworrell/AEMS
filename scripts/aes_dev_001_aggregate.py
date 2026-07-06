#!/usr/bin/env python3
"""Aggregate AES-DEV-001 development-principles evidence."""

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
DOC_AUTH_VALUES = {"local", "delegated", "transitional", "external"}


@dataclass
class RepositoryEntry:
    full_name: str
    role: str
    ownership: str
    expected_profile: bool
    profile_required: bool
    local_profile_path: str = ""
    documentation_authority: str = ""
    documentation_repository: str = ""
    documentation_paths: list[str] = field(default_factory=list)
    migration_status: str = ""
    notes: str = ""

    @property
    def project_owned(self) -> bool:
        return self.ownership == "project-owned"

    @property
    def doc_auth_declared(self) -> bool:
        return self.documentation_authority in DOC_AUTH_VALUES

    @property
    def docs_delegated(self) -> bool:
        return self.documentation_authority in {"delegated", "transitional"}


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
        if not self.scanned or not isinstance(self.scan, dict):
            return {}
        value = self.scan.get("summary", {})
        return value if isinstance(value, dict) else {}

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
    def docs_traceable(self) -> bool:
        repo = self.repository
        if not repo.doc_auth_declared:
            return False
        if repo.documentation_authority == "local":
            return True
        if repo.documentation_authority == "external":
            return not repo.project_owned
        if repo.docs_delegated:
            return bool(repo.documentation_repository and repo.documentation_paths)
        return False

    @property
    def ready_for_ratchet(self) -> bool:
        if self.repository.docs_delegated and self.docs_traceable:
            return True
        return bool(self.summary.get("ready_for_ratchet", False))

    @property
    def doc_reference(self) -> str:
        repo = self.repository
        if repo.documentation_authority in {"local", "external"}:
            return repo.documentation_authority
        if repo.docs_delegated:
            return f"{repo.documentation_repository}:{', '.join(repo.documentation_paths)}"
        return "undeclared"

    @property
    def local_doc_gaps_apply(self) -> bool:
        return self.repository.documentation_authority not in {"delegated", "transitional", "external"}

    @property
    def gap_names(self) -> list[str]:
        repo = self.repository
        if self.status == "not-scanned-third-party":
            return []
        if not self.scanned:
            return ["scan-unavailable"]

        gaps: list[str] = []
        if repo.project_owned and not repo.doc_auth_declared:
            gaps.append("documentation-authority")
        elif repo.project_owned and not self.docs_traceable:
            gaps.append("documentation-traceability")

        if repo.profile_required and not self.local_profile_present:
            gaps.append("local-profile")

        if self.local_doc_gaps_apply and repo.project_owned and repo.role not in {"demo-project", "experimental-native-code"}:
            if not self.specs_present:
                gaps.append("specs")

        adr_roles = {
            "system-project",
            "hardware-platform",
            "fpga-platform",
            "system-or-hardware-project",
            "ecosystem-governance",
            "enforcement-orchestrator",
        }
        if self.local_doc_gaps_apply and repo.project_owned and repo.role in adr_roles and not self.adrs_present:
            gaps.append("adrs")

        if self.local_doc_gaps_apply and self.evidence_present_count == 0:
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
            "documentation_traceable": self.docs_traceable,
            "documentation_reference": self.doc_reference,
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
        return sum(1 for e in self.entries if e.status == "scanned")

    @property
    def project_owned_count(self) -> int:
        return sum(1 for e in self.entries if e.repository.project_owned)

    @property
    def project_owned_scanned_count(self) -> int:
        return sum(1 for e in self.entries if e.repository.project_owned and e.status == "scanned")

    @property
    def failed_checkout_count(self) -> int:
        return sum(1 for e in self.entries if e.status == "checkout-failed")

    @property
    def scan_failed_count(self) -> int:
        return sum(1 for e in self.entries if e.status == "scan-failed")

    @property
    def doc_auth_declared_count(self) -> int:
        return sum(1 for e in self.entries if e.repository.doc_auth_declared)

    @property
    def docs_traceable_count(self) -> int:
        return sum(1 for e in self.entries if e.docs_traceable)

    @property
    def local_docs_count(self) -> int:
        return sum(1 for e in self.entries if e.repository.documentation_authority == "local")

    @property
    def delegated_docs_count(self) -> int:
        return sum(1 for e in self.entries if e.repository.documentation_authority == "delegated")

    @property
    def transitional_docs_count(self) -> int:
        return sum(1 for e in self.entries if e.repository.documentation_authority == "transitional")

    @property
    def external_docs_count(self) -> int:
        return sum(1 for e in self.entries if e.repository.documentation_authority == "external")

    @property
    def entries_with_gaps(self) -> list[AggregateEntry]:
        return [e for e in self.entries if e.has_gaps]

    def gap_count(self, name: str) -> int:
        return sum(1 for e in self.entries if name in e.gap_names)

    @property
    def failures(self) -> list[AggregateEntry]:
        return [e for e in self.entries if e.status in {"checkout-failed", "scan-failed"}]

    @property
    def passes_reporting_gate(self) -> bool:
        return not self.failures

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
                "documentation_authority_declared_count": self.doc_auth_declared_count,
                "documentation_traceable_count": self.docs_traceable_count,
                "local_documentation_count": self.local_docs_count,
                "delegated_documentation_count": self.delegated_docs_count,
                "transitional_documentation_count": self.transitional_docs_count,
                "external_documentation_count": self.external_docs_count,
                "entries_with_gap_count": len(self.entries_with_gaps),
                "documentation_authority_gap_count": self.gap_count("documentation-authority"),
                "documentation_traceability_gap_count": self.gap_count("documentation-traceability"),
                "profile_gap_count": self.gap_count("local-profile"),
                "specs_gap_count": self.gap_count("specs"),
                "adr_gap_count": self.gap_count("adrs"),
                "evidence_gap_count": self.gap_count("evidence"),
                "passes_reporting_gate": self.passes_reporting_gate,
            },
            "entries": [e.to_dict() for e in self.entries],
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run AES-DEV-001 scans for repositories in the manifest.")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--work-dir", default=None)
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    parser.add_argument("--include-third-party", action="store_true")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--keep-work-dir", action="store_true")
    parser.add_argument("--max-hits", type=int, default=5)
    return parser.parse_args()


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise SystemExit(f"error: failed to read manifest {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"error: invalid JSON manifest {path}: {exc}") from exc


def repository_entries(manifest: dict[str, Any]) -> list[RepositoryEntry]:
    entries: list[RepositoryEntry] = []
    for item in manifest.get("repositories", []):
        raw_paths = item.get("documentation_paths", [])
        doc_paths = [str(p) for p in raw_paths] if isinstance(raw_paths, list) else []
        entries.append(
            RepositoryEntry(
                full_name=str(item["full_name"]),
                role=str(item.get("role", "unknown")),
                ownership=str(item.get("ownership", "unknown")),
                expected_profile=bool(item.get("expected_profile", False)),
                profile_required=bool(item.get("profile_required", item.get("expected_profile", False))),
                local_profile_path=str(item.get("local_profile_path", "")),
                documentation_authority=str(item.get("documentation_authority", "")),
                documentation_repository=str(item.get("documentation_repository", "")),
                documentation_paths=doc_paths,
                migration_status=str(item.get("migration_status", "")),
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
    subprocess.run(
        ["git", "clone", "--depth", "1", "--quiet", clone_url(full_name), str(destination)],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def scan_entry(entry: RepositoryEntry, work_dir: Path, include_third_party: bool, max_hits: int) -> AggregateEntry:
    if entry.ownership != "project-owned" and not include_third_party:
        return AggregateEntry(repository=entry, status="not-scanned-third-party")

    destination = checkout_dir_for(work_dir, entry.full_name)
    try:
        run_git_clone(entry.full_name, destination)
    except FileNotFoundError:
        return AggregateEntry(entry, "checkout-failed", str(destination), error="git executable was not found")
    except subprocess.CalledProcessError as exc:
        return AggregateEntry(entry, "checkout-failed", str(destination), error=(exc.stderr or str(exc))[:1000])

    try:
        scan_report: Dev001Report = scan(destination, entry.full_name, max_hits=max_hits)
    except Exception as exc:
        return AggregateEntry(entry, "scan-failed", str(destination), error=f"{type(exc).__name__}: {exc}")

    return AggregateEntry(entry, "scanned", str(destination), scan=scan_report.to_dict())


def build_report(args: argparse.Namespace) -> AggregateReport:
    manifest = load_manifest(Path(args.manifest))
    entries = repository_entries(manifest)
    temporary_dir: tempfile.TemporaryDirectory[str] | None = None

    if args.work_dir is None:
        temporary_dir = tempfile.TemporaryDirectory(prefix="aes-dev-001-")
        work_dir = Path(temporary_dir.name)
    else:
        work_dir = Path(args.work_dir)
        work_dir.mkdir(parents=True, exist_ok=True)

    try:
        report = AggregateReport(
            standard=str(manifest.get("standard", "AES-DEV-001")),
            standard_repository=str(manifest.get("standard_repository", "")),
            standard_path=str(manifest.get("standard_path", "")),
        )
        for entry in entries:
            report.entries.append(scan_entry(entry, work_dir, args.include_third_party, args.max_hits))
        return report
    finally:
        if temporary_dir is not None and not args.keep_work_dir:
            temporary_dir.cleanup()


def passfail(value: bool) -> str:
    return "PASS" if value else "FAIL"


def format_markdown(report: AggregateReport) -> str:
    summary = report.to_dict()["summary"]
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
        f"- Documentation authority declared: `{summary['documentation_authority_declared_count']}`",
        f"- Documentation traceable: `{summary['documentation_traceable_count']}`",
        f"- Local documentation authority: `{summary['local_documentation_count']}`",
        f"- Delegated documentation authority: `{summary['delegated_documentation_count']}`",
        f"- Transitional documentation authority: `{summary['transitional_documentation_count']}`",
        f"- External documentation authority: `{summary['external_documentation_count']}`",
        f"- Repositories with evidence gaps: `{summary['entries_with_gap_count']}`",
        f"- Documentation authority gaps: `{summary['documentation_authority_gap_count']}`",
        f"- Documentation traceability gaps: `{summary['documentation_traceability_gap_count']}`",
        f"- Local profile gaps: `{summary['profile_gap_count']}`",
        f"- Specification gaps: `{summary['specs_gap_count']}`",
        f"- ADR gaps: `{summary['adr_gap_count']}`",
        f"- Evidence gaps: `{summary['evidence_gap_count']}`",
        f"- Reporting gate: `{passfail(report.passes_reporting_gate)}`",
        "",
        "## Repository Results",
        "",
        "| Repository | Role | Ownership | Status | Docs | Doc Reference | Profile | Specs | ADRs | Evidence | Ratchet | Gaps |",
        "|---|---|---|---|---|---|---:|---:|---:|---:|---:|---|",
    ]

    for entry in report.entries:
        evidence = f"{entry.evidence_present_count}/{entry.evidence_category_count}" if entry.scanned else "n/a"
        gaps = ", ".join(entry.gap_names) if entry.gap_names else "none"
        doc_ref = entry.doc_reference.replace("|", "\\|")
        lines.append(
            "| "
            f"`{entry.repository.full_name}` | "
            f"`{entry.repository.role}` | "
            f"`{entry.repository.ownership}` | "
            f"`{entry.status}` | "
            f"`{entry.repository.documentation_authority or 'undeclared'}` | "
            f"`{doc_ref}` | "
            f"`{entry.local_profile_present if entry.scanned else 'n/a'}` | "
            f"`{entry.specs_present if entry.scanned else 'n/a'}` | "
            f"`{entry.adrs_present if entry.scanned else 'n/a'}` | "
            f"`{evidence}` | "
            f"`{entry.ready_for_ratchet if entry.scanned else 'n/a'}` | "
            f"`{gaps}` |"
        )

    if report.failures:
        lines.extend(["", "## Checkout or Scan Failures", ""])
        for entry in report.failures:
            lines.append(f"- `{entry.repository.full_name}`: {entry.error or 'unknown failure'}")
    else:
        lines.extend(["", "## Checkout or Scan Failures", "", "None."])

    if report.entries_with_gaps:
        lines.extend(["", "## Evidence Gaps", ""])
        for entry in report.entries_with_gaps:
            lines.append(f"- `{entry.repository.full_name}`: {', '.join(entry.gap_names)}")
    else:
        lines.extend(["", "## Evidence Gaps", "", "None."])

    delegated = [e for e in report.entries if e.repository.docs_delegated]
    if delegated:
        lines.extend(["", "## Delegated or Transitional Documentation", ""])
        for entry in delegated:
            suffix = f"; migration: {entry.repository.migration_status}" if entry.repository.migration_status else ""
            lines.append(f"- `{entry.repository.full_name}`: `{entry.repository.documentation_authority}` -> `{entry.doc_reference}`{suffix}")

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
