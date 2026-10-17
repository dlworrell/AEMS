from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from aes_codeql import CATALOG, main, summarize_sarif
from check_real_header_evidence import BANNED_INTERFACES, missing_findings
from resolve_aes_codeql_suite import ROOT, check_resolved, upstream_pin
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



def real_header_evidence(*, drop=()):
    findings = [{"rule_id": "aes/cpp/banned-interface",
                 "message": f"AES-SEC-001: {name} is banned outside an explicitly approved exception."}
                for name in BANNED_INTERFACES if name not in drop]
    findings += [{"rule_id": rule, "message": "review"} for rule in
                 ("aes/cpp/candidate-secret-memset", "aes/cpp/discarded-snprintf-result")
                 if rule not in drop]
    return {"analysis": {"finding_count": len(findings), "findings": findings}}


class RealHeaderEvidenceTests(unittest.TestCase):
    def test_complete_evidence_has_nothing_missing(self):
        self.assertEqual(missing_findings(real_header_evidence()), [])

    def test_each_banned_interface_is_required_by_exact_name(self):
        # vsprintf and snprintf contain "sprintf"; they must not stand in for it.
        evidence = real_header_evidence(drop=("sprintf",))
        evidence["analysis"]["findings"].append({
            "rule_id": "aes/cpp/banned-interface",
            "message": "AES-SEC-001: snprintf requires review"})
        self.assertEqual(missing_findings(evidence), ["aes/cpp/banned-interface (sprintf)"])

    def test_missing_review_rules_are_reported(self):
        evidence = real_header_evidence(drop=("aes/cpp/candidate-secret-memset",))
        self.assertEqual(missing_findings(evidence), ["aes/cpp/candidate-secret-memset"])



class DefaultSuiteTests(unittest.TestCase):
    def test_pins_are_read_from_the_suite_files(self):
        self.assertEqual(upstream_pin(ROOT / "codeql/cpp/aes-security.qls"), "codeql/cpp-queries@1.9.1")
        self.assertEqual(upstream_pin(ROOT / "codeql/swift/aes-security.qls"), "codeql/swift-queries@1.3.12")

    def test_unpinned_import_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            suite = Path(directory) / "suite.qls"
            suite.write_text("- import: codeql-suites/x.qls\n  from: codeql/cpp-queries\n")
            with self.assertRaisesRegex(ValueError, "version"):
                upstream_pin(suite)

    def test_resolved_suite_needs_custom_and_upstream_queries(self):
        custom = sorted((ROOT / "codeql/cpp/queries").glob("*.ql"))
        upstream = ["/packs/codeql/cpp-queries/Security/CWE-120/BadlyBoundedWrite.ql"]
        self.assertEqual(check_resolved([str(q) for q in custom] + upstream, custom), [])
        problems = check_resolved([str(q) for q in custom[1:]] + upstream, custom)
        self.assertEqual(len(problems), 1)
        self.assertIn(custom[0].name, problems[0])
        self.assertIn("no upstream queries", check_resolved([str(q) for q in custom], custom)[0])


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
