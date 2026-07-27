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
        engineering.mkdir(parents=True)
        (engineering / "SECURE-C-CXX.md").write_text(
            "This repository inherits AES-SEC-001.\n",
            encoding="utf-8",
        )
        (engineering / "AES-SEC-001-waivers.md").write_text(
            "No waivers are approved.\n",
            encoding="utf-8",
        )

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
