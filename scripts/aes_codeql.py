#!/usr/bin/env python3
"""Run the supplemental AES query suite against an already extracted database.

Reporting only: completion is not a claim of AES-SEC-001/002 compliance.
Database creation/builds and existing AEMS gates remain repository-owned.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "config/aes-codeql-controls.json"


def summarize_sarif(document: dict[str, Any], expected_ids: set[str]) -> dict[str, Any]:
    """Reject absent, failed, incomplete, or suppressed analysis as a clean run."""
    if document.get("version") != "2.1.0" or not document.get("runs"):
        raise ValueError("missing SARIF 2.1.0 analysis runs")
    rules: set[str] = set()
    findings = []
    for run in document["runs"]:
        invocations = run.get("invocations", [])
        if not invocations or any(item.get("executionSuccessful") is not True for item in invocations):
            raise ValueError("SARIF does not establish successful analysis execution")
        if any(
            notification.get("level") == "error"
            for invocation in invocations
            for notification in invocation.get("toolExecutionNotifications", [])
        ):
            raise ValueError("SARIF contains an analysis error notification")
        driver = run.get("tool", {}).get("driver", {})
        rules.update(rule["id"] for rule in driver.get("rules", []) if "id" in rule)
        for extension in run.get("tool", {}).get("extensions", []):
            rules.update(rule["id"] for rule in extension.get("rules", []) if "id" in rule)
        for result in run.get("results", []):
            locations = result.get("locations", [])
            physical = locations[0].get("physicalLocation", {}) if locations else {}
            findings.append({
                "rule_id": result.get("ruleId"),
                "level": result.get("level", "warning"),
                "message": result.get("message", {}).get("text", ""),
                "uri": physical.get("artifactLocation", {}).get("uri"),
                "line": physical.get("region", {}).get("startLine"),
                "suppressions": result.get("suppressions", []),
                "baseline_state": result.get("baselineState"),
            })
    missing = sorted(expected_ids - rules)
    if missing:
        raise ValueError("SARIF is missing required custom queries: " + ", ".join(missing))
    return {
        "status": "completed-with-findings" if findings else "completed-no-findings",
        "query_ids": sorted(rules),
        "finding_count": len(findings),
        "suppressed_finding_count": sum(bool(item["suppressions"]) for item in findings),
        "findings": findings,
    }


def git_state() -> dict[str, Any]:
    def git(*arguments: str) -> str:
        return subprocess.run(
            ["git", "-C", str(ROOT), *arguments], check=True, text=True,
            capture_output=True, timeout=10,
        ).stdout.strip()
    try:
        return {"repository": "dlworrell/AEMS", "commit_sha": git("rev-parse", "HEAD"),
                "dirty": bool(git("status", "--porcelain"))}
    except (OSError, subprocess.SubprocessError):
        return {"repository": "dlworrell/AEMS", "commit_sha": None, "dirty": None}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--language", choices=("cpp", "swift"), required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--commit-sha", required=True,
                        help="Caller-asserted extraction commit; must identify the database's source.")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--codeql", default="codeql")
    parser.add_argument("--custom-only", action="store_true",
                        help="Run only AES additions; omit the pinned upstream security-extended suite.")
    parser.add_argument("--additional-packs", type=Path,
                        help="Optional matching official CodeQL library source checkout.")
    parser.add_argument("--timeout", type=int, default=900)
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[0-9a-fA-F]{40}", args.commit_sha):
        parser.error("--commit-sha must be a complete 40-character commit SHA")
    if args.timeout < 1:
        parser.error("--timeout must be positive")
    database = args.database.resolve()
    output = args.output_dir.resolve()
    # Evidence must not alter the CodeQL database or a pack during analysis.
    if output == database or database in output.parents or output == ROOT / "codeql" or ROOT / "codeql" in output.parents:
        parser.error("--output-dir must be outside the database and query packs")
    output.mkdir(parents=True, exist_ok=True)
    catalog_bytes = CATALOG.read_bytes()
    catalog = json.loads(catalog_bytes)
    expected = {q["id"] for q in catalog["queries"] if q["language"] == args.language}
    report: dict[str, Any] = {
        "schema": "aems.codeql-analysis.v1",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": "report-only",
        "query_profile": "custom-only" if args.custom_only else "security-extended-plus-aes",
        "subject": {"repository": args.repository, "commit_sha": args.commit_sha,
                    "provenance": "caller-asserted-database-extraction-commit",
                    "database": str(database), "language": args.language},
        "scanner": git_state(),
        "standards": catalog["sources"],
        "catalog_sha256": hashlib.sha256(catalog_bytes).hexdigest(),
        "standards_compliance": "NOT_ESTABLISHED",
        "analysis": {"status": "not-run", "findings": []},
        "coverage_limitations": catalog["limitations"],
        "complementary_evidence": {
            "status": "not-evaluated",
            "required": ["existing AES-SEC-001/002 scanners and waiver/review ledgers",
                         "applicable tests, sanitizers, fuzzing and concurrency compilation",
                         "threat-model, ownership, storage, dependency and artifact evidence"],
        },
    }
    # Preserve existing results under unique names; never parse a stale SARIF as a fresh run.
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    sarif = output / f"aes-{args.language}-{stamp}.sarif"
    pack = ROOT / "codeql" / args.language
    suite = pack / ("aes-custom.qls" if args.custom_only else "aes-security.qls")
    command = [args.codeql, "database", "analyze", str(database), str(suite),
               "--format=sarifv2.1.0", "--sarif-add-baseline-file-info",
               "--sarif-include-query-help=always", f"--output={sarif}",
               "--threads=2", "--ram=4096"]
    if args.additional_packs:
        command.append(f"--additional-packs={args.additional_packs.resolve()}")
    report["command"] = command
    report["sarif"] = str(sarif)
    report["suite_sha256"] = hashlib.sha256(suite.read_bytes()).hexdigest()
    report["query_sha256"] = {
        q["path"]: hashlib.sha256((ROOT / q["path"]).read_bytes()).hexdigest()
        for q in catalog["queries"] if q["language"] == args.language
    }
    report["pack_source_sha256"] = {
        path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(pack.rglob("*"))
        if path.is_file() and path.suffix in {".ql", ".qll", ".qls", ".yml"}
        and ".codeql" not in path.parts
    }
    exit_code = 0
    try:
        if not (database / "codeql-database.yml").is_file():
            raise ValueError("database metadata is missing; create a CodeQL database first")
        version = subprocess.run([args.codeql, "version", "--format=json"], check=True,
                                 text=True, capture_output=True, timeout=30)
        report["codeql"] = json.loads(version.stdout)
        result = subprocess.run(command, text=True, capture_output=True, timeout=args.timeout)
        report["process"] = {"exit_code": result.returncode,
                             "stdout_tail": result.stdout[-16000:],
                             "stderr_tail": result.stderr[-16000:]}
        if result.returncode:
            raise ValueError(f"CodeQL analysis failed with exit status {result.returncode}")
        report["analysis"] = summarize_sarif(json.loads(sarif.read_text()), expected)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        report["analysis"] = {"status": "failed", "error": str(error), "findings": []}
        exit_code = 2
    evidence = output / f"aes-{args.language}-{stamp}.json"
    evidence.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(evidence)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
