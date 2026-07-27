#!/usr/bin/env python3
"""Aggregate reporting-mode AES-SEC-002 applicability and detector evidence."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any

from aes_sec_002_scan import EvidenceFinding, ScanReport, scan


DEFAULT_CONFIG = Path("config/aes-sec-002-repositories.json")


@dataclass
class AggregateEntry:
    repository: str
    role: str
    ownership: str
    applicability: str
    rationale: str
    status: str
    source: str | None = None
    report: dict[str, Any] | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "repository": self.repository,
            "role": self.role,
            "ownership": self.ownership,
            "applicability": self.applicability,
            "rationale": self.rationale,
            "status": self.status,
            "source": self.source,
            "report": self.report,
            "error": self.error,
        }


@dataclass
class AggregateReport:
    standard: str
    standard_repository: str
    standard_path: str
    baseline_date: str
    owner: str
    entries: list[AggregateEntry] = field(default_factory=list)

    def status_count(self, status: str) -> int:
        return sum(entry.status == status for entry in self.entries)

    def applicability_count(self, applicability: str) -> int:
        return sum(
            entry.applicability == applicability for entry in self.entries
        )

    def finding_count(self, status: str) -> int:
        total = 0
        for entry in self.entries:
            report = entry.report or {}
            summary = report.get("summary", {})
            if isinstance(summary, dict):
                total += int(summary.get(status, 0))
        return total

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0.0",
            "standard": self.standard,
            "standard_repository": self.standard_repository,
            "standard_path": self.standard_path,
            "baseline_date": self.baseline_date,
            "owner": self.owner,
            "mode": "reporting",
            "blocking_enforcement": False,
            "summary": {
                "repository_count": len(self.entries),
                "in_scope_count": self.applicability_count("in-scope"),
                "out_of_scope_count": self.applicability_count("out-of-scope"),
                "not_yet_classified_count": self.applicability_count(
                    "not-yet-classified"
                ),
                "scanned_count": self.status_count("scanned"),
                "classification_only_count": self.status_count(
                    "classification-only"
                ),
                "untested_checkout_count": self.status_count(
                    "untested-checkout"
                ),
                "violation_count": self.finding_count("violation"),
                "absent_evidence_count": self.finding_count("absent-evidence"),
                "untested_finding_count": self.finding_count("untested"),
                "not_applicable_finding_count": self.finding_count(
                    "not-applicable"
                ),
            },
            "entries": [entry.to_dict() for entry in self.entries],
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build an AES-SEC-002 applicability and reporting baseline."
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG),
        help="Applicability configuration JSON",
    )
    parser.add_argument(
        "--source-map",
        help=(
            "Optional JSON object mapping owner/name to an existing checkout. "
            "Mapped sources are used instead of cloning."
        ),
    )
    parser.add_argument(
        "--work-dir",
        help="Clone directory; defaults to a temporary directory",
    )
    parser.add_argument(
        "--scan-in-scope",
        action="store_true",
        help=(
            "Scan in-scope repositories. Without this option, the command emits "
            "an applicability-only baseline."
        ),
    )
    parser.add_argument(
        "--format", choices=("json", "markdown"), default="markdown"
    )
    parser.add_argument(
        "--output",
        help="Write the selected report to this path instead of standard output",
    )
    parser.add_argument(
        "--keep-work-dir",
        action="store_true",
        help="Retain an automatically created clone directory",
    )
    return parser.parse_args()


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"failed to read {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc


def _clone(repository: str, destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "git",
            "clone",
            "--depth",
            "1",
            "--quiet",
            f"https://github.com/{repository}.git",
            str(destination),
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _classification_report(entry: dict[str, Any]) -> ScanReport:
    applicability = str(entry.get("applicability", "not-yet-classified"))
    rationale = str(entry.get("rationale", ""))
    report = ScanReport(
        repository=str(entry["full_name"]),
        root="not-scanned",
        applicability=applicability,
        rationale=rationale,
        source_revision=None,
        platforms=sorted(str(value) for value in entry.get("platforms", [])),
        languages=sorted(str(value) for value in entry.get("languages", [])),
        profile_path=str(
            entry.get(
                "profile_path",
                "docs/engineering/AES-SEC-002-boundaries.md",
            )
        ),
    )
    if applicability == "out-of-scope":
        report.findings.append(
            EvidenceFinding(
                rule_id="AES-SEC-002-SCOPE-001",
                status="not-applicable",
                severity="informational",
                message=f"Repository is out of scope: {rationale}",
            )
        )
    else:
        report.findings.append(
            EvidenceFinding(
                rule_id="AES-SEC-002-SCOPE-001",
                status="untested",
                severity="review",
                message=(
                    "Applicability classification remains open: "
                    f"{rationale}"
                ),
            )
        )
    return report


def _untested_in_scope_report(entry: dict[str, Any]) -> ScanReport:
    report = ScanReport(
        repository=str(entry["full_name"]),
        root="not-scanned",
        applicability="in-scope",
        rationale=str(entry["rationale"]),
        source_revision=None,
        platforms=sorted(str(value) for value in entry.get("platforms", [])),
        languages=sorted(str(value) for value in entry.get("languages", [])),
        profile_path=str(
            entry.get(
                "profile_path",
                "docs/engineering/AES-SEC-002-boundaries.md",
            )
        ),
    )
    report.findings.append(
        EvidenceFinding(
            rule_id="AES-SEC-002-SCOPE-001",
            status="untested",
            severity="review",
            message=(
                "Repository is classified in scope, but source scanning was not "
                "requested for this applicability-only run."
            ),
        )
    )
    return report


def build_report(args: argparse.Namespace) -> AggregateReport:
    config = _load_json(Path(args.config))
    if not isinstance(config, dict):
        raise ValueError("configuration root must be an object")
    raw_entries = config.get("repositories")
    if not isinstance(raw_entries, list):
        raise ValueError("configuration repositories must be a list")

    source_map: dict[str, str] = {}
    if args.source_map:
        loaded_map = _load_json(Path(args.source_map))
        if not isinstance(loaded_map, dict):
            raise ValueError("source map must be an object")
        source_map = {str(key): str(value) for key, value in loaded_map.items()}

    temporary: tempfile.TemporaryDirectory[str] | None = None
    if args.work_dir:
        work_dir = Path(args.work_dir)
        work_dir.mkdir(parents=True, exist_ok=True)
    else:
        temporary = tempfile.TemporaryDirectory(prefix="aes-sec-002-")
        work_dir = Path(temporary.name)

    report = AggregateReport(
        standard=str(config.get("standard", "AES-SEC-002")),
        standard_repository=str(config.get("standard_repository", "")),
        standard_path=str(config.get("standard_path", "")),
        baseline_date=str(config.get("baseline_date", "not-recorded")),
        owner=str(config.get("owner", "AEMS")),
    )
    try:
        for raw in raw_entries:
            if not isinstance(raw, dict):
                raise ValueError("each repository entry must be an object")
            repository = str(raw.get("full_name", ""))
            applicability = str(
                raw.get("applicability", "not-yet-classified")
            )
            base = {
                "repository": repository,
                "role": str(raw.get("role", "unknown")),
                "ownership": str(raw.get("ownership", "unknown")),
                "applicability": applicability,
                "rationale": str(raw.get("rationale", "")),
            }

            if applicability != "in-scope" or not args.scan_in_scope:
                classification = (
                    _classification_report(raw)
                    if applicability != "in-scope"
                    else _untested_in_scope_report(raw)
                )
                report.entries.append(
                    AggregateEntry(
                        **base,
                        status="classification-only",
                        report=classification.to_dict(),
                    )
                )
                continue

            source: Path
            source_kind: str
            if repository in source_map:
                source = Path(source_map[repository]).resolve()
                source_kind = "source-map"
                if not source.is_dir():
                    report.entries.append(
                        AggregateEntry(
                            **base,
                            status="untested-checkout",
                            source=str(source),
                            error="mapped source is not a directory",
                        )
                    )
                    continue
            else:
                source = work_dir / repository.replace("/", "__")
                source_kind = "clone"
                try:
                    _clone(repository, source)
                except (FileNotFoundError, subprocess.CalledProcessError) as exc:
                    error = (
                        exc.stderr.strip()
                        if isinstance(exc, subprocess.CalledProcessError)
                        and exc.stderr
                        else str(exc)
                    )
                    report.entries.append(
                        AggregateEntry(
                            **base,
                            status="untested-checkout",
                            source=str(source),
                            error=error[:1000],
                        )
                    )
                    continue

            try:
                local_report = scan(source, repository=repository, entry=raw)
            except Exception as exc:  # noqa: BLE001 - retain aggregate evidence.
                report.entries.append(
                    AggregateEntry(
                        **base,
                        status="untested-checkout",
                        source=f"{source_kind}:{source}",
                        error=f"{type(exc).__name__}: {exc}",
                    )
                )
                continue
            report.entries.append(
                AggregateEntry(
                    **base,
                    status="scanned",
                    source=f"{source_kind}:{source}",
                    report=local_report.to_dict(),
                )
            )
        return report
    finally:
        if temporary is not None and not args.keep_work_dir:
            temporary.cleanup()


def format_markdown(report: AggregateReport) -> str:
    data = report.to_dict()
    summary = data["summary"]
    lines = [
        "# AES-SEC-002 Ecosystem Reporting Baseline",
        "",
        "- Mode: `reporting`",
        "- Blocking enforcement: `false`",
        f"- Baseline date: `{report.baseline_date}`",
        f"- Owner: `{report.owner}`",
        f"- Repositories: `{summary['repository_count']}`",
        f"- In scope: `{summary['in_scope_count']}`",
        f"- Out of scope: `{summary['out_of_scope_count']}`",
        f"- Not yet classified: `{summary['not_yet_classified_count']}`",
        f"- Scanned: `{summary['scanned_count']}`",
        f"- Untested checkouts: `{summary['untested_checkout_count']}`",
        f"- Violations: `{summary['violation_count']}`",
        f"- Absent evidence: `{summary['absent_evidence_count']}`",
        "",
        "## Repository applicability",
        "",
        "| Repository | Ownership | Applicability | Status | Violations | Absent | Untested | Rationale |",
        "|---|---|---|---|---:|---:|---:|---|",
    ]
    for entry in report.entries:
        local_summary = (entry.report or {}).get("summary", {})
        if not isinstance(local_summary, dict):
            local_summary = {}
        rationale = entry.rationale.replace("|", "\\|")
        lines.append(
            f"| `{entry.repository}` | `{entry.ownership}` | "
            f"`{entry.applicability}` | `{entry.status}` | "
            f"`{local_summary.get('violation', 0)}` | "
            f"`{local_summary.get('absent-evidence', 0)}` | "
            f"`{local_summary.get('untested', 0)}` | {rationale} |"
        )
    lines.extend(
        [
            "",
            "## Ratchet boundary",
            "",
            "This report does not authorize blocking enforcement. A future ratchet "
            "requires retained source-scan baselines, an affected-repository "
            "migration window, operational waivers, reviewed high-signal "
            "detectors, and a separate governance and standards decision.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    args = parse_args()
    try:
        report = build_report(args)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    rendered = (
        json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n"
        if args.format == "json"
        else format_markdown(report)
    )
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
