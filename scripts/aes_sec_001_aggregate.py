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
from github_checkout import (
    DEFAULT_GITHUB_TOKEN_ENV,
    git_clone_environment,
    redact_git_error,
    resolve_github_token,
)

DEFAULT_MANIFEST = Path("config/aes-sec-001-repositories.json")


@dataclass
class RepositoryEntry:
    full_name: str
    role: str
    ownership: str
    expected_profile: bool
    native_profile: str | None = None
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

    @property
    def review_dispositions(self) -> dict[str, Any]:
        if not isinstance(self.scan, dict):
            return {}
        value = self.scan.get("review_dispositions", {})
        return value if isinstance(value, dict) else {}

    def review_count(self, key: str) -> int:
        value = self.review_dispositions.get(key, 0)
        return value if isinstance(value, int) and not isinstance(value, bool) else 0

    @property
    def reviewed_finding_count(self) -> int:
        return self.review_count("reviewed")

    @property
    def unresolved_finding_count(self) -> int:
        return self.review_count("unresolved")

    @property
    def new_finding_count(self) -> int:
        return self.review_count("new")

    @property
    def source_drifted_finding_count(self) -> int:
        return self.review_count("source_drifted")

    @property
    def stale_disposition_count(self) -> int:
        return self.review_count("stale")

    @property
    def passes_review_ratchet(self) -> bool:
        if self.status != "scanned" or self.scan is None:
            return not self.expected_to_pass_gate
        if not self.expected_to_pass_gate:
            return True
        return bool(self.review_dispositions.get("passes_ratchet", False))

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
            "reviewed_finding_count": self.reviewed_finding_count,
            "unresolved_finding_count": self.unresolved_finding_count,
            "new_finding_count": self.new_finding_count,
            "source_drifted_finding_count": self.source_drifted_finding_count,
            "stale_disposition_count": self.stale_disposition_count,
            "passes_review_ratchet": self.passes_review_ratchet,
        }


@dataclass
class AggregateReport:
    standard: str
    standard_repository: str
    standard_path: str
    enforce_review_ratchet: bool = False
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
    def reviewed_finding_count(self) -> int:
        return sum(entry.reviewed_finding_count for entry in self.entries)

    @property
    def unresolved_finding_count(self) -> int:
        return sum(entry.unresolved_finding_count for entry in self.entries)

    @property
    def new_finding_count(self) -> int:
        return sum(entry.new_finding_count for entry in self.entries)

    @property
    def source_drifted_finding_count(self) -> int:
        return sum(entry.source_drifted_finding_count for entry in self.entries)

    @property
    def stale_disposition_count(self) -> int:
        return sum(entry.stale_disposition_count for entry in self.entries)

    @property
    def review_ratchet_failures(self) -> list[AggregateEntry]:
        if not self.enforce_review_ratchet:
            return []
        return [
            entry
            for entry in self.entries
            if entry.expected_to_pass_gate and not entry.passes_review_ratchet
        ]

    @property
    def passes(self) -> bool:
        return not self.expected_gate_failures and not self.review_ratchet_failures

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
                "reviewed_finding_count": self.reviewed_finding_count,
                "unresolved_finding_count": self.unresolved_finding_count,
                "new_finding_count": self.new_finding_count,
                "source_drifted_finding_count": self.source_drifted_finding_count,
                "stale_disposition_count": self.stale_disposition_count,
                "review_ratchet_enforced": self.enforce_review_ratchet,
                "review_ratchet_failure_count": len(self.review_ratchet_failures),
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
        "--enforce-review-ratchet",
        action="store_true",
        help=(
            "Include unresolved, new, source-drifted, and stale review "
            "dispositions in the aggregate gate. Leave disabled until the "
            "repository baselines are migrated."
        ),
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
    parser.add_argument(
        "--per-repository-dir",
        default=None,
        help=(
            "Write one JSON and one Markdown evidence report per manifest "
            "entry into this directory."
        ),
    )
    parser.add_argument(
        "--github-token-env",
        default=DEFAULT_GITHUB_TOKEN_ENV,
        help=(
            "Environment variable containing an optional GitHub token for "
            "private project-owned repositories."
        ),
    )
    parser.add_argument(
        "--require-github-token",
        action="store_true",
        help="Fail before the aggregate scan when --github-token-env is unset or empty.",
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
                native_profile=(
                    str(item["native_profile"])
                    if item.get("native_profile")
                    else None
                ),
                notes=str(item.get("notes", "")),
            )
        )
    return entries


def checkout_dir_for(work_dir: Path, full_name: str) -> Path:
    return work_dir / full_name.replace("/", "__")


def clone_url(full_name: str) -> str:
    return f"https://github.com/{full_name}.git"


def run_git_clone(
    full_name: str,
    destination: Path,
    github_token: str | None = None,
    github_token_env: str = DEFAULT_GITHUB_TOKEN_ENV,
) -> None:
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
    subprocess.run(
        cmd,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=git_clone_environment(
            github_token,
            token_env_name=github_token_env,
        ),
    )


def scan_entry(
    entry: RepositoryEntry,
    work_dir: Path,
    include_dangerous_primitives: bool,
    include_third_party: bool,
    github_token: str | None = None,
    github_token_env: str = DEFAULT_GITHUB_TOKEN_ENV,
) -> AggregateEntry:
    if entry.ownership != "project-owned" and not include_third_party:
        return AggregateEntry(repository=entry, status="not-scanned-third-party")

    destination = checkout_dir_for(work_dir, entry.full_name)
    try:
        run_git_clone(
            entry.full_name,
            destination,
            github_token,
            github_token_env,
        )
    except FileNotFoundError:
        return AggregateEntry(
            repository=entry,
            status="checkout-failed",
            checkout_path=str(destination),
            error="git executable was not found",
        )
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.strip() if exc.stderr else str(exc)
        stderr = redact_git_error(stderr, github_token)
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
    token_env = str(
        getattr(args, "github_token_env", DEFAULT_GITHUB_TOKEN_ENV)
    )
    try:
        github_token = resolve_github_token(
            token_env,
            required=bool(getattr(args, "require_github_token", False)),
        )
    except ValueError as exc:
        raise SystemExit(f"error: {exc}") from exc

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
            enforce_review_ratchet=bool(args.enforce_review_ratchet),
        )
        for entry in entries:
            aggregate.entries.append(
                scan_entry(
                    entry,
                    work_dir,
                    args.include_dangerous_primitives,
                    args.include_third_party,
                    github_token,
                    token_env,
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
    if value is None:
        return ""
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
        f"- Reviewed findings: `{report.reviewed_finding_count}`",
        f"- Unresolved findings: `{report.unresolved_finding_count}`",
        f"- New findings: `{report.new_finding_count}`",
        f"- Source-drifted findings: `{report.source_drifted_finding_count}`",
        f"- Stale disposition entries: `{report.stale_disposition_count}`",
        f"- Review ratchet enforced: `{report.enforce_review_ratchet}`",
        f"- Aggregate result: `{format_bool(report.passes)}`",
        "",
        "## Repository Results",
        "",
        "| Repository | Role | Ownership | Native profile | Status | Class | Local policy | Waiver log | Banned | Review | Reviewed | Unresolved | New | Drift | Stale | Adoption gate | Review ratchet |",
        "|---|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
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
            f"`{entry.repository.native_profile or 'n/a'}` | "
            f"`{entry.status}` | "
            f"`{classification}` | "
            f"`{profile}` | "
            f"`{waiver_log}` | "
            f"`{entry.banned_finding_count}` | "
            f"`{entry.review_required_finding_count}` | "
            f"`{entry.reviewed_finding_count}` | "
            f"`{entry.unresolved_finding_count}` | "
            f"`{entry.new_finding_count}` | "
            f"`{entry.source_drifted_finding_count}` | "
            f"`{entry.stale_disposition_count}` | "
            f"`{gate}` | "
            f"`{entry.passes_review_ratchet}` |"
        )

    if report.expected_gate_failures:
        lines.extend(["", "## Expected Gate Failures", ""])
        for entry in report.expected_gate_failures:
            reason = entry.error or "minimum adoption gate failed"
            lines.append(f"- `{entry.repository.full_name}`: {reason}")
    else:
        lines.extend(["", "## Expected Gate Failures", "", "None."])

    if report.enforce_review_ratchet:
        if report.review_ratchet_failures:
            lines.extend(["", "## Review Ratchet Failures", ""])
            for entry in report.review_ratchet_failures:
                lines.append(
                    f"- `{entry.repository.full_name}`: "
                    f"{entry.unresolved_finding_count} unresolved, "
                    f"{entry.new_finding_count} new, "
                    f"{entry.source_drifted_finding_count} source-drifted, "
                    f"{entry.stale_disposition_count} stale"
                )
        else:
            lines.extend(["", "## Review Ratchet Failures", "", "None."])

    if report.review_required_finding_count:
        lines.extend([
            "",
            "## Review-Required Findings",
            "",
            "These are not gate failures. They identify native-code operations that need review, wrapper decisions, or documented invariants.",
            "",
            "| Repository | Symbol | Path | Line | Status | Classification | Finding ID | Source fingerprint | Remediation |",
            "|---|---|---|---:|---|---|---|---|---|",
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
                    f"{finding_value(finding, 'line')} | "
                    f"`{finding_value(finding, 'disposition_status')}` | "
                    f"`{finding_value(finding, 'disposition_classification') or 'n/a'}` | "
                    f"`{finding_value(finding, 'finding_id')}` | "
                    f"`{finding_value(finding, 'source_fingerprint')}` | "
                    f"{finding_value(finding, 'remediation')} |"
                )
    else:
        lines.extend(["", "## Review-Required Findings", "", "None."])

    return "\n".join(lines)


def report_stem(full_name: str) -> str:
    return full_name.replace("/", "__")


def format_repository_markdown(entry: AggregateEntry) -> str:
    scan_data = entry.scan or {}
    summary = scan_data.get("summary", {}) if isinstance(scan_data, dict) else {}
    findings = entry.findings
    lines = [
        f"# AES-SEC-001 Repository Report: `{entry.repository.full_name}`",
        "",
        f"- Role: `{entry.repository.role}`",
        f"- Ownership: `{entry.repository.ownership}`",
        f"- Native profile: `{entry.repository.native_profile or 'not assigned'}`",
        f"- Scan status: `{entry.status}`",
        f"- Expected adoption gate: `{entry.expected_to_pass_gate}`",
        f"- Gate passes: `{entry.passes_expected_gate}`",
        f"- Banned findings: `{entry.banned_finding_count}`",
        f"- Review-required findings: `{entry.review_required_finding_count}`",
        f"- Reviewed findings: `{entry.reviewed_finding_count}`",
        f"- Unresolved findings: `{entry.unresolved_finding_count}`",
        f"- New findings: `{entry.new_finding_count}`",
        f"- Source-drifted findings: `{entry.source_drifted_finding_count}`",
        f"- Stale disposition entries: `{entry.stale_disposition_count}`",
        f"- Review ratchet passes: `{entry.passes_review_ratchet}`",
    ]
    if entry.repository.notes:
        lines.append(f"- Manifest note: {entry.repository.notes}")
    if entry.error:
        lines.append(f"- Error: `{entry.error}`")
    if scan_data:
        lines.extend(
            [
                "",
                "## Scan evidence",
                "",
                f"- Classification: `{scan_data.get('classification', 'n/a')}`",
                f"- Local secure policy: `{scan_data.get('secure_profile_present', 'n/a')}`",
                f"- Waiver log: `{scan_data.get('waiver_log_present', 'n/a')}`",
                f"- Native files: `{scan_data.get('native_file_count', 0)}`",
                f"- Build surfaces: `{scan_data.get('build_surface_count', 0)}`",
                "- Minimum adoption gate: "
                f"`{summary.get('passes_minimum_adoption_gate', 'n/a')}`",
            ]
        )
    if findings:
        lines.extend(
            [
                "",
                "## Findings",
                "",
                "| Severity | Symbol | Path | Line | Status | Classification | Finding ID | Source fingerprint | Remediation |",
                "|---|---|---|---:|---|---|---|---|---|",
            ]
        )
        for finding in findings:
            lines.append(
                "| "
                f"`{finding_value(finding, 'severity')}` | "
                f"`{finding_value(finding, 'symbol')}` | "
                f"`{finding_value(finding, 'path')}` | "
                f"{finding_value(finding, 'line')} | "
                f"`{finding_value(finding, 'disposition_status')}` | "
                f"`{finding_value(finding, 'disposition_classification') or 'n/a'}` | "
                f"`{finding_value(finding, 'finding_id')}` | "
                f"`{finding_value(finding, 'source_fingerprint')}` | "
                f"{finding_value(finding, 'remediation')} |"
            )
    else:
        lines.extend(["", "## Findings", "", "None."])
    return "\n".join(lines) + "\n"


def write_repository_reports(
    report: AggregateReport, output_dir: Path
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for entry in report.entries:
        stem = report_stem(entry.repository.full_name)
        json_path = output_dir / f"{stem}.json"
        markdown_path = output_dir / f"{stem}.md"
        json_path.write_text(
            json.dumps(entry.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        markdown_path.write_text(
            format_repository_markdown(entry),
            encoding="utf-8",
        )
        written.extend((json_path, markdown_path))
    return written


def main() -> int:
    args = parse_args()
    report = build_report(args)

    if args.per_repository_dir:
        write_repository_reports(report, Path(args.per_repository_dir))

    if args.format == "json":
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    else:
        print(format_markdown(report))

    if args.strict and not report.passes:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
