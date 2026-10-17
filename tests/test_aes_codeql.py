from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from aes_codeql import CATALOG, main, summarize_sarif
from update_aes_codeql_coverage import clauses, support


def sarif():
    return {"version": "2.1.0", "runs": [{
        "tool": {"driver": {"name": "CodeQL", "rules": [{"id": "aes/test"}]}},
        "invocations": [{"executionSuccessful": True}], "results": [],
    }]}


class EvidenceTests(unittest.TestCase):
    def test_zero_findings_only_establishes_analysis_completion(self):
        result = summarize_sarif(sarif(), {"aes/test"})
        self.assertEqual(result["status"], "completed-no-findings")
        self.assertNotIn("compliant", result)

    def test_missing_run_and_failed_invocation_are_not_clean(self):
        for document in ({"version": "2.1.0", "runs": []}, sarif(), sarif()):
            if document["runs"]:
                document["runs"][0]["invocations"] = []
            with self.assertRaises(ValueError):
                summarize_sarif(document, {"aes/test"})
        document = sarif()
        document["runs"][0]["invocations"][0]["executionSuccessful"] = False
        with self.assertRaises(ValueError):
            summarize_sarif(document, {"aes/test"})

    def test_partially_executed_suite_is_not_clean(self):
        with self.assertRaisesRegex(ValueError, "missing required custom queries"):
            summarize_sarif(sarif(), {"aes/test", "aes/missing"})

    def test_error_notification_overrides_success_flag(self):
        document = sarif()
        document["runs"][0]["invocations"][0]["toolExecutionNotifications"] = [{"level": "error"}]
        with self.assertRaises(ValueError):
            summarize_sarif(document, {"aes/test"})

    def test_suppressed_and_baselined_findings_remain_visible(self):
        document = sarif()
        document["runs"][0]["results"] = [{
            "ruleId": "aes/test", "message": {"text": "candidate"},
            "suppressions": [{"kind": "external"}], "baselineState": "unchanged",
            "locations": [{"physicalLocation": {"artifactLocation": {"uri": "src/core.c"},
                                                   "region": {"startLine": 12}}}],
        }]
        result = summarize_sarif(document, {"aes/test"})
        self.assertEqual(result["status"], "completed-with-findings")
        self.assertEqual(result["suppressed_finding_count"], 1)
        self.assertEqual(result["findings"][0]["line"], 12)
        self.assertEqual(result["findings"][0]["baseline_state"], "unchanged")

    def test_failed_second_run_cannot_reuse_stale_sarif(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database, output = root / "database", root / "evidence"
            database.mkdir()
            (database / "codeql-database.yml").write_text("language: cpp\n")
            output.mkdir()
            stale = output / "previous.sarif"
            stale.write_text(json.dumps(sarif()))
            code = main(["--database", str(database), "--language", "cpp", "--repository", "example/test",
                         "--commit-sha", "a" * 40, "--output-dir", str(output),
                         "--codeql", str(root / "missing-codeql")])
            self.assertEqual(code, 2)
            evidence = json.loads(next(output.glob("*.json")).read_text())
            self.assertEqual(evidence["analysis"]["status"], "failed")
            self.assertEqual(evidence["standards_compliance"], "NOT_ESTABLISHED")
            self.assertEqual(evidence["complementary_evidence"]["status"], "not-evaluated")
            self.assertEqual(json.loads(stale.read_text()), sarif())


class CoverageTests(unittest.TestCase):
    def test_inherited_lists_and_multiline_clauses_are_inventoried(self):
        source = "## Required\nA project MUST provide:\n\n- a bounded input;\n- a failure test.\n\nA profile SHOULD record\nits rationale.\n\n```text\nExample MUST NOT count.\n```\n"
        extracted = list(clauses(source))
        self.assertEqual(len(extracted), 4)
        self.assertEqual(extracted[1]["level"], "inherited")
        self.assertEqual(extracted[3]["source_lines"], [7, 8])
        self.assertEqual(extracted[3]["text"], "A profile SHOULD record its rationale.")

    def test_non_static_obligations_are_not_marked_as_query_coverage(self):
        self.assertEqual(support("AES-SEC-002", "Repository Data and History",
                                 "History rewriting requires authorization."), [])
        self.assertEqual(support("AES-SEC-001", "Integer and Size Rules",
                                 "Multiplication MUST be checked for overflow."), [])

    def test_catalog_is_pinned_complete_and_non_normative(self):
        catalog = json.loads(CATALOG.read_text())
        self.assertFalse(catalog["standard_compliance_proven"])
        self.assertEqual({source["id"] for source in catalog["sources"]}, {"AES-SEC-001", "AES-SEC-002"})
        self.assertEqual(len(catalog["sources"][0]["revision"]), 40)
        ids = {query["id"] for query in catalog["queries"]}
        self.assertEqual(len(ids), 10)
        locators = [item["locator"] for item in catalog["requirements"]]
        self.assertEqual(len(locators), len(set(locators)))
        self.assertGreater(len(locators), 150)
        for item in catalog["requirements"]:
            self.assertTrue(set(item["query_ids"]) <= ids)
            self.assertNotEqual(item["codeql_coverage"], "complete")
            self.assertTrue(item["complementary_evidence"])
        for query in catalog["queries"]:
            text = (CATALOG.parents[1] / query["path"]).read_text()
            self.assertIn("@id " + query["id"], text)
            self.assertEqual(query["enforcement"], "report-only")


if __name__ == "__main__":
    unittest.main()
