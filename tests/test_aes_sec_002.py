from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from aes_sec_002_scan import scan


def entry() -> dict[str, object]:
    return {
        "full_name": "example/aes-sec-002",
        "applicability": "in-scope",
        "rationale": "Synthetic safe/native secret-storage fixture.",
        "languages": ["c17", "swift-6"],
        "platforms": ["apple-macho", "linux-elf"],
        "profile_path": "docs/engineering/SECURITY-BOUNDARIES.md",
        "waiver_path": "docs/engineering/AES-SEC-002-waivers.md",
        "bridge_paths": ["src/apple/App/CatalogueClient.swift"],
        "ffi_symbol_prefixes": ["ab_"],
        "secret_material": True,
        "history_migration": "deferred",
    }


class AesSec002Tests(unittest.TestCase):
    @property
    def fixtures(self) -> Path:
        return Path(__file__).resolve().parent / "fixtures" / "aes_sec_002"

    def test_positive_fixture_has_no_violations(self) -> None:
        report = scan(
            self.fixtures / "positive",
            repository="example/positive",
            entry=entry(),
        )
        self.assertEqual(report.result, "REPORTED")
        self.assertEqual(report.count("violation"), 0)
        self.assertEqual(report.count("absent-evidence"), 0)
        present = {
            finding.rule_id
            for finding in report.findings
            if finding.status == "present"
        }
        self.assertIn("AES-SEC-002-ABI-001", present)
        self.assertIn("AES-SEC-002-CONC-002", present)
        self.assertIn("AES-SEC-002-STORE-001", present)
        self.assertIn("AES-SEC-002-ELF-001", present)
        self.assertIn("AES-SEC-002-MACHO-001", present)

    def test_negative_fixture_distinguishes_violations_and_absence(self) -> None:
        report = scan(
            self.fixtures / "negative",
            repository="example/negative",
            entry=entry(),
        )
        violations = {
            finding.rule_id
            for finding in report.findings
            if finding.status == "violation"
        }
        absent = {
            finding.rule_id
            for finding in report.findings
            if finding.status == "absent-evidence"
        }
        self.assertTrue(
            {
                "AES-SEC-002-ABI-001",
                "AES-SEC-002-NATIVE-001",
                "AES-SEC-002-KEY-001",
                "AES-SEC-002-STORE-001",
                "AES-SEC-002-PLATFORM-001",
            }
            <= violations
        )
        self.assertIn("AES-SEC-002-PROFILE-001", absent)
        self.assertIn("AES-SEC-002-CONC-002", absent)
        self.assertIn("AES-SEC-002-KEY-002", absent)
        self.assertIn("AES-SEC-002-REPO-001", absent)

    def test_scope_statuses_do_not_run_detectors(self) -> None:
        out_entry = {
            "applicability": "out-of-scope",
            "rationale": "No covered boundary.",
        }
        out_report = scan(
            self.fixtures / "negative",
            repository="example/out",
            entry=out_entry,
        )
        self.assertEqual(out_report.result, "NOT_APPLICABLE")
        self.assertEqual(out_report.count("not-applicable"), 1)
        self.assertEqual(len(out_report.findings), 1)

        open_entry = {
            "applicability": "not-yet-classified",
            "rationale": "Boundary inventory is pending.",
        }
        open_report = scan(
            self.fixtures / "negative",
            repository="example/open",
            entry=open_entry,
        )
        self.assertEqual(open_report.result, "CLASSIFICATION_REQUIRED")
        self.assertEqual(open_report.count("untested"), 1)
        self.assertEqual(len(open_report.findings), 1)


if __name__ == "__main__":
    unittest.main()
