from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import check_integration_branches as cb
from tests.test_fitment_cycle import DAILY, FIT, REPO, FakeGitHub, routes


class RetentionTests(unittest.TestCase):
    def test_existing_branches_with_active_deletion_rules_pass_without_writes(self):
        github = FakeGitHub(routes())
        self.assertEqual(cb.inspect_branches(github, REPO), {"dev-daily": DAILY, "fitment": FIT})
        self.assertEqual((github.posts, github.puts, github.patches), ([], [], []))

    def test_reports_both_missing_branches_and_protections(self):
        values = routes()
        for branch in cb.BRANCHES:
            values[f"/repos/{REPO}/branches/{branch}"] = cb.GitHubError(404, "missing")
            values[f"/repos/{REPO}/rules/branches/{branch}"] = []
        with self.assertRaises(cb.RetentionError) as caught:
            cb.inspect_branches(FakeGitHub(values), REPO)
        for branch in cb.BRANCHES:
            self.assertIn(f"{branch}: branch is missing", str(caught.exception))
            self.assertIn(f"{branch}: no active deletion rule", str(caught.exception))
        self.assertIn("last verified head", str(caught.exception))

    def test_protected_flag_does_not_substitute_for_a_deletion_rule(self):
        for branch in cb.BRANCHES:
            with self.subTest(branch=branch):
                values = routes()
                values[f"/repos/{REPO}/branches/{branch}"]["protected"] = True
                values[f"/repos/{REPO}/rules/branches/{branch}"] = [{"type": "non_fast_forward"}]
                with self.assertRaisesRegex(cb.RetentionError, f"{branch}: no active deletion rule"):
                    cb.inspect_branches(FakeGitHub(values), REPO)

    def test_active_inherited_deletion_rules_are_accepted(self):
        values = routes()
        for branch in cb.BRANCHES:
            values[f"/repos/{REPO}/rules/branches/{branch}"] = [
                {"type": "deletion", "ruleset_source_type": "Organization", "ruleset_id": 7}]
        self.assertEqual(len(cb.inspect_branches(FakeGitHub(values), REPO)), 2)

    def test_unreadable_branch_is_not_reported_as_missing(self):
        values = routes()
        values[f"/repos/{REPO}/branches/dev-daily"] = cb.GitHubError(403, "forbidden")
        with self.assertRaises(cb.RetentionError) as caught:
            cb.inspect_branches(FakeGitHub(values), REPO)
        self.assertIn("cannot read branch (HTTP 403)", str(caught.exception))
        self.assertNotIn("branch is missing", str(caught.exception))

    def test_rule_api_failures_cannot_pass(self):
        for status in (403, 404, 429, 500):
            with self.subTest(status=status):
                values = routes()
                values[f"/repos/{REPO}/rules/branches/fitment"] = cb.GitHubError(status, "unavailable")
                with self.assertRaisesRegex(cb.RetentionError, "retention is unverified"):
                    cb.inspect_branches(FakeGitHub(values), REPO)

    def test_malformed_heads_cannot_pass(self):
        for value in (None, [], {}, {"commit": {"sha": "short"}}, {"commit": {"sha": 123}}):
            with self.subTest(value=value):
                values = routes()
                values[f"/repos/{REPO}/branches/fitment"] = value
                with self.assertRaisesRegex(cb.RetentionError, "head is malformed"):
                    cb.inspect_branches(FakeGitHub(values), REPO)

    def test_malformed_or_truncated_rules_cannot_pass(self):
        for value in ([None], [{}], [{"type": 1}], [{"type": "deletion"}] * (cb.RULES_LIMIT + 1)):
            with self.subTest(length=len(value)):
                values = routes()
                values[f"/repos/{REPO}/rules/branches/fitment"] = value
                with self.assertRaisesRegex(cb.RetentionError, "malformed or exceeds"):
                    cb.inspect_branches(FakeGitHub(values), REPO)

    def test_invalid_repository_is_rejected_before_network_access(self):
        for name in ("", "owner/repo/extra", "../repo", "owner/repo?query=x"):
            with self.subTest(name=name), self.assertRaisesRegex(cb.RetentionError, "owner/name"):
                cb.inspect_branches(FakeGitHub({}), name)

    def test_shared_client_paginates_effective_rules(self):
        github = cb.GitHubClient(None)
        pages = iter([(b'[{"type":"non_fast_forward"}]', {"Link":
            '<https://api.github.com/repos/owner/repo/rules/branches/fitment?page=2>; rel="next"'}),
                      (b'[{"type":"deletion"}]', {})])
        with patch.object(github, "_open", side_effect=lambda *_a: next(pages)) as request:
            rules = github.get_all("/repos/owner/repo/rules/branches/fitment?per_page=100",
                                   limit=cb.RULES_LIMIT + 1)
        self.assertEqual([r["type"] for r in rules], ["non_fast_forward", "deletion"])
        self.assertEqual(request.call_count, 2)

    def test_cli_records_observed_heads_and_returns_success(self):
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()), \
                patch.object(cb, "GitHubClient", return_value=FakeGitHub(routes())):
            output = Path(tmp) / "preflight.json"
            self.assertEqual(cb.main(["--repository", REPO, "--output", str(output)]), 0)
            result = json.loads(output.read_text())
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["heads"], {"dev-daily": DAILY, "fitment": FIT})

    def test_cli_records_block_and_returns_failure(self):
        values = routes()
        values[f"/repos/{REPO}/rules/branches/dev-daily"] = []
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()), \
                patch.object(cb, "GitHubClient", return_value=FakeGitHub(values)):
            output = Path(tmp) / "preflight.json"
            self.assertEqual(cb.main(["--repository", REPO, "--output", str(output)]), 1)
            result = json.loads(output.read_text())
        self.assertEqual(result["status"], "blocked")
        self.assertNotIn("heads", result)
        self.assertIn("no active deletion rule", result["diagnostic"])


if __name__ == "__main__":
    unittest.main()
