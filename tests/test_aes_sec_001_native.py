from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from aes_sec_001_aggregate import (
    AggregateEntry,
    AggregateReport,
    RepositoryEntry,
    write_repository_reports,
)
from aes_sec_001_native import (
    discover,
    run_control_commands,
    run_fuzz_targets,
)


class AesSec001NativeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @property
    def profiles(self) -> Path:
        return (
            Path(__file__).resolve().parents[1]
            / "config"
            / "aes-sec-001-native-profiles.json"
        )

    def test_discovers_native_control_evidence(self) -> None:
        (self.root / "CMakeLists.txt").write_text(
            """
add_compile_options(-Wall -fsanitize=address)
set(CMAKE_C_CLANG_TIDY clang-tidy)
""",
            encoding="utf-8",
        )
        source = self.root / "fuzz_parser.c"
        source.write_text(
            "int LLVMFuzzerTestOneInput(const unsigned char *data, unsigned long size) { return 0; }\n",
            encoding="utf-8",
        )
        report = discover(
            self.root,
            repository="example/native",
            profile_id="c17-library",
            profiles_path=self.profiles,
            target_config={"fuzz_targets": []},
            smoke=False,
        )
        self.assertEqual(report.build_systems, ["cmake"])
        self.assertTrue(report.warning_signals)
        self.assertTrue(report.static_analysis_signals)
        self.assertTrue(report.sanitizer_signals)
        self.assertEqual(report.fuzz_harnesses, ["fuzz_parser.c"])
        self.assertEqual(report.profile, "c17-library")

    def test_examples_and_scanner_sources_are_not_adoption_evidence(self) -> None:
        (self.root / "templates").mkdir()
        (self.root / "templates" / "CMakeLists.txt").write_text(
            "add_compile_options(-Wall -fsanitize=address)\n",
            encoding="utf-8",
        )
        fixture = self.root / "tests" / "fixtures"
        fixture.mkdir(parents=True)
        (fixture / "fuzz.c").write_text(
            "int LLVMFuzzerTestOneInput(const unsigned char *data, unsigned long size) { return 0; }\n",
            encoding="utf-8",
        )
        scripts = self.root / "scripts"
        scripts.mkdir()
        (scripts / "aes_sec_001_native.py").write_text(
            "TOOLS = ['clang-tidy', '-fsanitize=address', '-Wall']\n",
            encoding="utf-8",
        )
        report = discover(
            self.root,
            repository="example/non-operational",
            profile_id=None,
            profiles_path=self.profiles,
            target_config={},
        )
        self.assertEqual(report.build_systems, [])
        self.assertEqual(report.warning_signals, [])
        self.assertEqual(report.static_analysis_signals, [])
        self.assertEqual(report.sanitizer_signals, [])
        self.assertEqual(report.fuzz_harnesses, [])

    def test_fuzz_smoke_uses_argument_list_and_records_failure(self) -> None:
        results = run_fuzz_targets(
            self.root,
            {
                "fuzz_targets": [
                    {
                        "id": "pass",
                        "command": [sys.executable, "-c", "raise SystemExit(0)"],
                        "timeout_seconds": 5,
                    },
                    {
                        "id": "fail",
                        "command": [sys.executable, "-c", "raise SystemExit(7)"],
                        "timeout_seconds": 5,
                    },
                ]
            },
        )
        self.assertEqual([result.status for result in results], ["passed", "failed"])
        self.assertEqual(results[1].returncode, 7)

    def test_control_commands_are_typed_and_executed(self) -> None:
        results = run_control_commands(
            self.root,
            {
                "control_commands": [
                    {
                        "id": "warnings",
                        "kind": "warnings",
                        "command": [
                            sys.executable,
                            "-c",
                            "raise SystemExit(0)",
                        ],
                        "timeout_seconds": 5,
                    },
                    {
                        "id": "analysis",
                        "kind": "static-analysis",
                        "command": [
                            sys.executable,
                            "-c",
                            "raise SystemExit(0)",
                        ],
                        "timeout_seconds": 5,
                    },
                    {
                        "id": "sanitizers",
                        "kind": "sanitizer-test",
                        "command": [
                            sys.executable,
                            "-c",
                            "raise SystemExit(0)",
                        ],
                        "timeout_seconds": 5,
                    },
                ]
            },
        )
        self.assertEqual(
            [result.kind for result in results],
            ["warnings", "static-analysis", "sanitizer-test"],
        )
        self.assertTrue(all(result.status == "passed" for result in results))

    def test_writes_repository_scoped_json_and_markdown(self) -> None:
        repository = RepositoryEntry(
            full_name="example/native",
            role="native-library",
            ownership="project-owned",
            expected_profile=True,
            native_profile="c17-library",
        )
        entry = AggregateEntry(
            repository=repository,
            status="scanned",
            scan={
                "classification": "native-code-active",
                "secure_profile_present": True,
                "waiver_log_present": True,
                "native_file_count": 2,
                "build_surface_count": 1,
                "findings": [
                    {
                        "severity": "review-required",
                        "symbol": "memset",
                        "path": "src/example.c",
                        "line": 7,
                        "text": "memset(example, 0, sizeof(*example));",
                        "remediation": "Prove the bound or use secure erasure.",
                        "finding_id": "aes-sec-001:" + ("1" * 64),
                        "source_fingerprint": "sha256:" + ("2" * 64),
                        "disposition_status": "new",
                        "disposition_classification": None,
                    }
                ],
                "review_dispositions": {
                    "total": 1,
                    "reviewed": 0,
                    "unresolved": 1,
                    "new": 1,
                    "source_drifted": 0,
                    "stale": 0,
                    "passes_ratchet": False,
                },
                "summary": {
                    "passes_minimum_adoption_gate": True,
                    "passes_review_ratchet": False,
                },
            },
        )
        report = AggregateReport(
            standard="AES-SEC-001",
            standard_repository="dlworrell/AES",
            standard_path="standards/AES-SEC-001-secure-c-cpp-coding-rules.md",
            entries=[entry],
        )
        output = self.root / "reports"
        written = write_repository_reports(report, output)
        self.assertEqual(
            [path.name for path in written],
            ["example__native.json", "example__native.md"],
        )
        data = json.loads((output / "example__native.json").read_text())
        self.assertEqual(
            data["repository"]["native_profile"],
            "c17-library",
        )
        markdown = (output / "example__native.md").read_text()
        self.assertIn("`c17-library`", markdown)
        self.assertIn("Gate passes: `True`", markdown)
        self.assertIn("New findings: `1`", markdown)
        self.assertIn("Review ratchet passes: `False`", markdown)
        self.assertIn("Prove the bound or use secure erasure.", markdown)

        reporting = AggregateReport(
            standard="AES-SEC-001",
            standard_repository="dlworrell/AES",
            standard_path="standards/AES-SEC-001-secure-c-cpp-coding-rules.md",
            entries=[entry],
        )
        enforcing = AggregateReport(
            standard="AES-SEC-001",
            standard_repository="dlworrell/AES",
            standard_path="standards/AES-SEC-001-secure-c-cpp-coding-rules.md",
            enforce_review_ratchet=True,
            entries=[entry],
        )
        self.assertTrue(reporting.passes)
        self.assertFalse(enforcing.passes)
        self.assertEqual(enforcing.new_finding_count, 1)
        self.assertEqual(enforcing.review_ratchet_failures, [entry])


if __name__ == "__main__":
    unittest.main()
