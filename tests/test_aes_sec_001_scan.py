from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from aes_sec_001_scan import (
    format_github,
    format_markdown,
    scan,
    scan_source_for_apis,
)


class AesSec001ScanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def source(self, content: str) -> Path:
        path = self.root / "source.c"
        path.write_text(content, encoding="utf-8")
        return path

    def adoption_markers(self) -> None:
        engineering = self.root / "docs" / "engineering"
        engineering.mkdir(parents=True, exist_ok=True)
        (engineering / "SECURE-C-CXX.md").write_text(
            "This repository inherits AES-SEC-001.\n",
            encoding="utf-8",
        )
        (engineering / "AES-SEC-001-waivers.md").write_text(
            "No waivers are approved.\n",
            encoding="utf-8",
        )

    def write_review_ledger(
        self,
        baseline_findings: list[object],
        dispositions: list[dict[str, object]],
    ) -> None:
        engineering = self.root / "docs" / "engineering"
        engineering.mkdir(parents=True, exist_ok=True)
        baseline = [
            {
                "finding_id": finding.finding_id,
                "source_fingerprint": finding.source_fingerprint,
                "path": finding.path,
                "line": finding.line,
                "symbol": finding.symbol,
            }
            for finding in baseline_findings
        ]
        document = {
            "schema_version": "1.0.0",
            "repository": "example/native",
            "baseline": {
                "captured_at": "2026-07-27",
                "source": "unit-test baseline",
                "findings": baseline,
            },
            "dispositions": dispositions,
        }
        (engineering / "AES-SEC-001-review-dispositions.json").write_text(
            json.dumps(document, indent=2) + "\n",
            encoding="utf-8",
        )

    @staticmethod
    def disposition(
        finding: object,
        classification: str = "approved-invariant",
    ) -> dict[str, object]:
        return {
            "finding_id": finding.finding_id,
            "source_fingerprint": finding.source_fingerprint,
            "path": finding.path,
            "line": finding.line,
            "symbol": finding.symbol,
            "classification": classification,
            "rationale": "The destination capacity is proven by the caller contract.",
            "invariant": "size never exceeds the destination object.",
            "evidence": ["tests/test_bounds.c"],
            "owner": "native-maintainer",
            "reviewer": "security-reviewer",
            "reviewed_at": "2026-07-27",
            "reassess_after": None,
            "resolution_commit": None,
        }

    def test_banned_and_review_required_apis_are_classified(self) -> None:
        path = self.source(
            """
void example(char *dst, const char *src, unsigned long size) {
    strcpy(dst, src);
    strncpy(dst, src, size);
    strncat(dst, src, size);
    memset(dst, 0, size);
}
"""
        )

        findings = scan_source_for_apis(
            self.root,
            path,
            include_dangerous_primitives=True,
        )

        self.assertEqual(
            [(finding.symbol, finding.severity) for finding in findings],
            [
                ("strcpy", "banned"),
                ("strncpy", "review-required"),
                ("strncat", "review-required"),
                ("memset", "review-required"),
            ],
        )
        for finding in findings:
            self.assertTrue(finding.remediation)
        memset = next(
            finding for finding in findings if finding.symbol == "memset"
        )
        self.assertIn("ordinary initialization", memset.remediation)
        self.assertIn("secret erasure", memset.remediation)

    def test_comments_strings_characters_and_exemptions_are_ignored(self) -> None:
        path = self.source(
            r'''
const char *message = "strcpy(destination, source)";
char marker = '(';
// gets(buffer);
/*
 * sprintf(buffer, "not code");
 */
void allowed(char *dst, const char *src) {
    strcpy(dst, src); /* aes-sec-001: allow; waiver SEC-001 */
}
'''
        )

        findings = scan_source_for_apis(
            self.root,
            path,
            include_dangerous_primitives=True,
        )

        self.assertEqual(findings, [])

    def test_multiline_comment_preserves_finding_line_number(self) -> None:
        path = self.source(
            """/*
strcpy(comment, only);
*/
void example(char *dst, const char *src) {
    strcpy(dst, src);
}
"""
        )

        findings = scan_source_for_apis(
            self.root,
            path,
            include_dangerous_primitives=False,
        )

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].line, 5)

    def test_finding_identity_survives_line_moves_and_detects_source_drift(
        self,
    ) -> None:
        path = self.source(
            """
void initialize(char *dst, unsigned long size) {
    memset(dst, 0, size);
}
"""
        )
        original = scan_source_for_apis(
            self.root,
            path,
            include_dangerous_primitives=True,
        )[0]

        path.write_text(
            """


void initialize(char *dst, unsigned long size) {
    memset( dst, /* initialization */ 0, size );
}
""",
            encoding="utf-8",
        )
        moved = scan_source_for_apis(
            self.root,
            path,
            include_dangerous_primitives=True,
        )[0]
        self.assertNotEqual(original.line, moved.line)
        self.assertEqual(original.finding_id, moved.finding_id)
        self.assertEqual(original.source_fingerprint, moved.source_fingerprint)

        path.write_text(
            """
void initialize(char *dst, unsigned long size) {
    memset(dst, 0, size + 1);
}
""",
            encoding="utf-8",
        )
        changed = scan_source_for_apis(
            self.root,
            path,
            include_dangerous_primitives=True,
        )[0]
        self.assertEqual(original.finding_id, changed.finding_id)
        self.assertNotEqual(
            original.source_fingerprint,
            changed.source_fingerprint,
        )

    def test_review_dispositions_report_new_reviewed_drift_and_stale(
        self,
    ) -> None:
        self.adoption_markers()
        path = self.source(
            """
void initialize(char *dst, unsigned long size) {
    memset(dst, 0, size);
}
"""
        )
        untracked = scan(
            self.root,
            repo_name="example/native",
            include_dangerous_primitives=True,
        )
        finding = untracked.findings[0]
        self.assertEqual(finding.disposition_status, "new")
        self.assertEqual(untracked.review_dispositions.new, 1)
        self.assertEqual(untracked.review_dispositions.unresolved, 1)
        self.assertFalse(untracked.passes_review_ratchet)

        self.write_review_ledger(
            [finding],
            [self.disposition(finding)],
        )
        reviewed = scan(
            self.root,
            repo_name="example/native",
            include_dangerous_primitives=True,
        )
        self.assertEqual(
            reviewed.findings[0].disposition_status,
            "reviewed",
        )
        self.assertEqual(reviewed.review_dispositions.reviewed, 1)
        self.assertEqual(reviewed.review_dispositions.unresolved, 0)
        self.assertTrue(reviewed.passes_review_ratchet)

        path.write_text(
            """
void initialize(char *dst, unsigned long size) {
    memset(dst, 0, size + 1);
}
""",
            encoding="utf-8",
        )
        drifted = scan(
            self.root,
            repo_name="example/native",
            include_dangerous_primitives=True,
        )
        self.assertEqual(
            drifted.findings[0].disposition_status,
            "source-drifted",
        )
        self.assertEqual(drifted.review_dispositions.source_drifted, 1)
        self.assertEqual(drifted.review_dispositions.unresolved, 1)
        self.assertFalse(drifted.passes_review_ratchet)

        path.write_text("void initialize(void) {}\n", encoding="utf-8")
        stale = scan(
            self.root,
            repo_name="example/native",
            include_dangerous_primitives=True,
        )
        self.assertEqual(stale.review_dispositions.total, 0)
        self.assertEqual(stale.review_dispositions.stale, 1)
        self.assertFalse(stale.passes_review_ratchet)

    def test_invalid_review_disposition_is_rejected(self) -> None:
        self.adoption_markers()
        self.source(
            """
void initialize(char *dst, unsigned long size) {
    memset(dst, 0, size);
}
"""
        )
        initial = scan(
            self.root,
            repo_name="example/native",
            include_dangerous_primitives=True,
        )
        invalid = self.disposition(initial.findings[0])
        invalid["evidence"] = []
        self.write_review_ledger(initial.findings, [invalid])

        with self.assertRaisesRegex(ValueError, "evidence"):
            scan(
                self.root,
                repo_name="example/native",
                include_dangerous_primitives=True,
            )

    def test_resolved_disposition_is_historical_until_finding_reappears(
        self,
    ) -> None:
        self.adoption_markers()
        path = self.source(
            """
void initialize(char *dst, unsigned long size) {
    memset(dst, 0, size);
}
"""
        )
        initial = scan(
            self.root,
            repo_name="example/native",
            include_dangerous_primitives=True,
        )
        finding = initial.findings[0]
        resolved = self.disposition(finding, classification="resolved")
        resolved["resolution_commit"] = "1234567"
        self.write_review_ledger([finding], [resolved])

        path.write_text("void initialize(void) {}\n", encoding="utf-8")
        absent = scan(
            self.root,
            repo_name="example/native",
            include_dangerous_primitives=True,
        )
        self.assertEqual(absent.review_dispositions.stale, 0)
        self.assertTrue(absent.passes_review_ratchet)

        path.write_text(
            """
void initialize(char *dst, unsigned long size) {
    memset(dst, 0, size);
}
""",
            encoding="utf-8",
        )
        reappeared = scan(
            self.root,
            repo_name="example/native",
            include_dangerous_primitives=True,
        )
        self.assertEqual(
            reappeared.findings[0].disposition_status,
            "unresolved",
        )
        self.assertFalse(reappeared.passes_review_ratchet)

    def test_synthetic_fixture_sources_are_not_governed_code(self) -> None:
        self.adoption_markers()
        fixture = self.root / "tests" / "fixtures" / "negative"
        fixture.mkdir(parents=True)
        (fixture / "unsafe.c").write_text(
            "void fixture(char *dst, const char *src) { strcpy(dst, src); }\n",
            encoding="utf-8",
        )
        report = scan(
            self.root,
            repo_name="example/native",
            include_dangerous_primitives=True,
        )

        self.assertEqual(report.findings, [])
        self.assertEqual(report.native_files, [])

    def test_markdown_and_github_formats_include_remediation(self) -> None:
        self.adoption_markers()
        self.source(
            """
void example(char *dst, const char *src) {
    strcpy(dst, src);
    memset(dst, 0, 4);
}
"""
        )
        report = scan(
            self.root,
            repo_name="example/native",
            include_dangerous_primitives=True,
        )

        markdown = format_markdown(report)
        annotations = format_github(report)

        self.assertIn("| Remediation |", markdown)
        self.assertIn("Use an explicit-length copy", markdown)
        self.assertIn("::error file=source.c,line=3", annotations)
        self.assertIn("::warning file=source.c,line=4", annotations)
        self.assertIn("Remedy:", annotations)

    def test_strict_cli_blocks_banned_but_not_review_required_findings(self) -> None:
        self.adoption_markers()
        path = self.source(
            """
void initialize(char *dst, unsigned long size) {
    memset(dst, 0, size);
}
"""
        )
        command = [
            sys.executable,
            str(ROOT / "scripts" / "aes_sec_001_scan.py"),
            str(self.root),
            "--strict",
            "--include-dangerous-primitives",
            "--format",
            "github",
        ]

        review_only = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(review_only.returncode, 0)
        self.assertIn("::warning", review_only.stdout)

        review_ratchet = subprocess.run(
            command + ["--strict-review-ratchet"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(review_ratchet.returncode, 1)
        self.assertIn("(new)", review_ratchet.stdout)

        path.write_text(
            """
void copy(char *dst, const char *src) {
    strcpy(dst, src);
}
""",
            encoding="utf-8",
        )
        banned = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(banned.returncode, 1)
        self.assertIn("::error", banned.stdout)

    def test_canonical_clang_tidy_configuration_matches_template(self) -> None:
        canonical = (ROOT / ".clang-tidy").read_text(encoding="utf-8")
        template = (ROOT / "templates" / "native" / ".clang-tidy").read_text(
            encoding="utf-8"
        )

        self.assertEqual(canonical, template)
        self.assertIn(
            "clang-analyzer-security.insecureAPI.DeprecatedOrUnsafeBufferHandling",
            canonical,
        )
        self.assertNotIn(
            "\n  security.insecureAPI.DeprecatedOrUnsafeBufferHandling",
            canonical,
        )
        warnings = canonical.split("WarningsAsErrors:", maxsplit=1)[1]
        self.assertNotIn("'*'", warnings.split("HeaderFilterRegex:", maxsplit=1)[0])
        self.assertNotIn(
            "DeprecatedOrUnsafeBufferHandling",
            warnings.split("HeaderFilterRegex:", maxsplit=1)[0],
        )

        profile_data = json.loads(
            (
                ROOT / "config" / "aes-sec-001-native-profiles.json"
            ).read_text(encoding="utf-8")
        )
        baseline = profile_data["clang_tidy_baseline"]
        self.assertEqual(baseline["canonical_path"], ".clang-tidy")
        self.assertIn(
            "clang-analyzer-security.insecureAPI.DeprecatedOrUnsafeBufferHandling",
            baseline["reporting_checks"],
        )
        self.assertNotIn(
            "clang-analyzer-security.insecureAPI.DeprecatedOrUnsafeBufferHandling",
            baseline["blocking_checks"],
        )

    def test_manifest_pre_adopts_all_future_c_project_repositories(self) -> None:
        manifest = json.loads(
            (
                ROOT / "config" / "aes-sec-001-repositories.json"
            ).read_text(encoding="utf-8")
        )
        entries = {
            entry["full_name"]: entry
            for entry in manifest["repositories"]
        }
        required_project_repositories = {
            "dlworrell/AEMS",
            "dlworrell/P0",
            "dlworrell/repo_templates",
            "dlworrell/Catylist",
            "dlworrell/AES",
            "dlworrell/atarix",
            "dlworrell/code-noodling",
            "dlworrell/audiblebooks",
            "dlworrell/engineering-docs-toolkit",
            "dlworrell/EWT",
            "dlworrell/herkules-1934-english",
            "dlworrell/JAG",
            "dlworrell/evo",
            "dlworrell/Just-a-Geek-LLC",
            "dlworrell/Rocket_demo",
            "dlworrell/MayaUSD2017Bridge",
        }

        self.assertTrue(required_project_repositories.issubset(entries))
        project_owned = {
            name: entry
            for name, entry in entries.items()
            if entry["ownership"] == "project-owned"
        }
        self.assertEqual(set(project_owned), required_project_repositories)
        self.assertTrue(
            all(entry["expected_profile"] for entry in project_owned.values())
        )
        self.assertEqual(
            entries["dlworrell/audiblebooks"]["native_profile"],
            "c17-library",
        )
        self.assertIn(
            "absence of C or C++ is not an exemption",
            manifest["policy"]["project_owned_future_native_policy"],
        )
        self.assertEqual(
            manifest["policy"]["review_ratchet_mode"],
            "reporting",
        )
        self.assertEqual(
            manifest["policy"]["default_review_dispositions"],
            "docs/engineering/AES-SEC-001-review-dispositions.json",
        )

        schema = json.loads(
            (
                ROOT
                / "schemas"
                / "aes-sec-001-review-dispositions-v1.schema.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(
            schema["properties"]["schema_version"]["const"],
            "1.0.0",
        )
        retained = json.loads(
            (
                ROOT
                / "docs"
                / "engineering"
                / "reports"
                / "AES-SEC-001-review-required-baseline-2026-07-27.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(retained["finding_count"], 56)
        self.assertEqual(len(retained["findings"]), 56)
        per_repository: dict[str, int] = {}
        for finding in retained["findings"]:
            repository = finding["repository"]
            per_repository[repository] = per_repository.get(repository, 0) + 1
        self.assertEqual(
            per_repository,
            {
                "dlworrell/atarix": 49,
                "dlworrell/code-noodling": 2,
                "dlworrell/audiblebooks": 3,
                "dlworrell/evo": 2,
            },
        )

    def test_distributed_workflow_uses_central_action_and_validates_policy(
        self,
    ) -> None:
        action = (
            ROOT / ".github" / "actions" / "aes-sec-001" / "action.yml"
        ).read_text(encoding="utf-8")
        reusable = (
            ROOT / ".github" / "workflows" / "aes-sec-001-distributed.yml"
        ).read_text(encoding="utf-8")
        caller = (
            ROOT / "templates" / "workflows" / "aes-sec-001-governance.yml"
        ).read_text(encoding="utf-8")

        self.assertIn("scripts/aes_sec_001_scan.py", action)
        self.assertIn("--format github", action)
        self.assertIn("clang-tidy --verify-config --config-file=.clang-tidy", reusable)
        self.assertIn(
            "uses: dlworrell/AEMS/.github/actions/aes-sec-001@main",
            reusable,
        )
        self.assertIn(
            "uses: dlworrell/AEMS/.github/workflows/"
            "aes-sec-001-distributed.yml@main",
            caller,
        )


if __name__ == "__main__":
    unittest.main()
