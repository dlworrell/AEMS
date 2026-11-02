"""Tests for scripts/ruleset_drift_audit.py.

Each acceptance case is isolated: one fixture changes one thing from a fully
clean, fully verified baseline, so a case cannot pass because of drift or an
error elsewhere. The cases map to the requirements in the module docstring
and in docs/engineering/catylist-default-branch-rulesets.md (Drift audit).
"""
import base64
import importlib.util
import io
import json
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("ruleset_drift_audit", ROOT / "scripts/ruleset_drift_audit.py")
audit = importlib.util.module_from_spec(spec)
sys.modules["ruleset_drift_audit"] = audit
spec.loader.exec_module(audit)

REPO = "dlworrell/demo"
PRIVATE = "dlworrell/secret-thing"
HIDDEN = "dlworrell/hidden-thing"
LEAKS = (PRIVATE, HIDDEN, "secret-thing", "hidden-thing", "api.github.com", "Not Found", "Traceback", "boom")
GHA = 15368
GOOD_RULES = [{"type": "deletion"}, {"type": "non_fast_forward"}, {"type": "required_signatures"},
              {"type": "pull_request", "parameters": {"allowed_merge_methods": ["merge"]}}]


def checks(*contexts, app=GHA):
    return {"type": "required_status_checks",
            "parameters": {"required_status_checks": [{"context": c, "integration_id": app} for c in contexts]}}


class FakeGitHub:
    """A clean, fully verified public repository, plus an excluded entry; every write recorded."""

    def __init__(self):
        self.inventory = {"schema": "catylist.repository-inventory.v1",
                          "repositories": [{"full_name": REPO, "default_branch_policy": "protected"},
                                           {"full_name": "dlworrell/ext", "default_branch_policy": "excluded"}]}
        self.meta = {"default_branch": "main", "private": False, "allow_merge_commit": True,
                     "allow_squash_merge": False, "allow_rebase_merge": False}
        self.rulesets = [{"name": n, "enforcement": "active"} for n in
                         ("protect-default-branch", "protect-release-tags", "protect-integration-branches")]
        self.rules = {"main": GOOD_RULES + [checks("build")], "dev-daily": list(GOOD_RULES),
                      "fitment": list(GOOD_RULES)}
        self.issues = []
        self.posts, self.patches, self.requests = [], [], []
        self.private_meta = None  # set by add_private()

    def add_private(self):
        self.inventory["repositories"] += [{"full_name": PRIVATE, "default_branch_policy": "protected"},
                                           {"full_name": HIDDEN, "default_branch_policy": "protected"}]
        # Drift everywhere: none of it may reach any public sink or the outcome.
        self.private_meta = dict(self.meta, private=True, allow_squash_merge=True)

    def get(self, path):
        self.requests.append(path)
        if path.endswith("/contents/inventory/repositories.json"):
            return {"encoding": "base64", "content": base64.b64encode(json.dumps(self.inventory).encode()).decode()}
        if path == f"/repos/{REPO}":
            return self.meta
        if path == f"/repos/{PRIVATE}" and self.private_meta:
            return self.private_meta
        if path == f"/repos/{HIDDEN}":
            raise audit.GitHubError(404, f"GET https://api.github.com/repos/{HIDDEN}: Not Found")
        raise AssertionError(path)

    def get_all(self, path, limit=1000):
        self.requests.append(path)
        if PRIVATE in path or HIDDEN in path:
            raise AssertionError(f"excluded repository was audited: {path}")
        if "/rulesets?" in path:
            return self.rulesets
        if "/rules/branches/" in path:
            branch = path.split("/rules/branches/")[1].split("?")[0]
            if branch not in self.rules:
                raise audit.GitHubError(404, f"GET https://api.github.com/repos/{REPO}/rules: Not Found")
            return self.rules[branch]
        if "/issues?" in path:
            return self.issues
        raise AssertionError(path)

    def post(self, path, body):
        self.posts.append((path, body))
        return {"number": 9}

    def patch(self, path, body):
        self.patches.append((path, body))
        return {}


def required(main=("build",), app="github-actions", **branches):
    return {"schema": "aems.required-checks.v1", "apps": {"github-actions": GHA, "other-app": 999},
            "repositories": {REPO: {"main": [{"context": c, "app": app} for c in main],
                                    **{b: [{"context": c, "app": "github-actions"} for c in v]
                                       for b, v in branches.items()}}}}


class _Case(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        tmp = Path(self.tmp.name)
        self.fitment = tmp / "fitment.json"
        self.fitment.write_text(json.dumps({"schema": "aems.fitment-config.v1", "repositories": [REPO]}))
        self.required = tmp / "required.json"
        self.required.write_text(json.dumps(required()))
        self.report = tmp / "report.md"
        self.result = tmp / "result.json"

    def run_audit(self, gh, *extra):
        """Run main(); return (exit code, stdout, stderr, every sink's text joined)."""
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = audit.main(["--fitment-config", str(self.fitment), "--required-checks", str(self.required),
                               "--output", str(self.report), "--result-json", str(self.result), *extra],
                              reader=gh, writer=gh)
        sinks = [out.getvalue(), err.getvalue(), *(json.dumps(b) for _, b in gh.posts + gh.patches)]
        sinks += [p.read_text() for p in (self.report, self.result) if p.exists()]
        return code, out.getvalue(), err.getvalue(), "\n".join(sinks)

    def result_json(self):
        return json.loads(self.result.read_text())

    def assert_safe(self, text):
        for leak in LEAKS:
            self.assertNotIn(leak, text)


class BaselineAndDriftTests(_Case):
    def test_clean_verified_baseline(self):
        gh = FakeGitHub()
        code, out, _, _ = self.run_audit(gh, "--dry-run")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.result_json()["outcome"], "clean")
        self.assertIn("**Outcome: clean.**", out)
        self.assertEqual((gh.posts, gh.patches), ([], []))

    def test_each_kind_of_drift_alone(self):
        cases = {
            "squash merging on": (lambda g: g.meta.update(allow_squash_merge=True),
                                  "allow_squash_merge is true, expected false"),
            "ruleset disabled": (lambda g: g.rulesets[0].update(enforcement="disabled"),
                                 "ruleset protect-default-branch is disabled, not active"),
            "tag ruleset missing": (lambda g: g.rulesets.pop(1), "ruleset protect-release-tags is missing"),
            "signatures dropped": (lambda g: g.rules["main"].pop(2), "main: no required_signatures rule"),
            "linear history added": (lambda g: g.rules["fitment"].append({"type": "required_linear_history"}),
                                     "fitment: required_linear_history is set"),
            "squash allowed by rule": (lambda g: g.rules["dev-daily"].__setitem__(
                3, {"type": "pull_request", "parameters": {"allowed_merge_methods": ["merge", "squash"]}}),
                "dev-daily: pull_request allows merge, squash, not merge only"),
            "unexpected required check": (lambda g: g.rules["main"].__setitem__(4, checks("build", "lint")),
                                          "unexpected lint (app 15368)"),
        }
        for label, (mutate, expected) in cases.items():
            gh = FakeGitHub()
            mutate(gh)
            with self.subTest(label):
                code, out, _, _ = self.run_audit(gh, "--dry-run")
                self.assertEqual(code, 1)
                self.assertEqual(self.result_json()["outcome"], "drift")
                self.assertIn(expected, out)

    def test_missing_required_check_alone(self):
        self.required.write_text(json.dumps(required(**{"dev-daily": ["verify"]})))
        code, out, _, _ = self.run_audit(FakeGitHub(), "--dry-run")
        self.assertEqual(code, 1)
        self.assertIn("dev-daily: required checks differ from config/required-checks.json "
                      "(missing verify (app 15368))", out)


class RequiredCheckIdentityTests(_Case):
    """Finding 5: a check is its context and the App that must report it."""

    def test_same_context_from_another_app_is_drift(self):
        gh = FakeGitHub()
        gh.rules["main"][4] = checks("build", app=999)
        code, out, _, _ = self.run_audit(gh, "--dry-run")
        self.assertEqual(code, 1)
        self.assertIn("missing build (app 15368); unexpected build (app 999)", out)

    def test_rule_without_an_app_id_does_not_satisfy_a_pinned_check(self):
        gh = FakeGitHub()
        gh.rules["main"][4] = {"type": "required_status_checks",
                               "parameters": {"required_status_checks": [{"context": "build"}]}}
        code, out, _, _ = self.run_audit(gh, "--dry-run")
        self.assertEqual(code, 1)
        self.assertIn("unexpected build (app any)", out)

    def test_config_naming_another_app_is_compared_by_id(self):
        self.required.write_text(json.dumps(required(app="other-app")))
        code, out, _, _ = self.run_audit(FakeGitHub(), "--dry-run")
        self.assertEqual(code, 1)
        self.assertIn("missing build (app 999)", out)


class UnverifiedIsNotCleanTests(_Case):
    """Findings 2 and 3: unavailable evidence is unverified (exit 3), never clean or drift."""

    def test_hidden_merge_settings_alone_are_unverified(self):
        gh = FakeGitHub()
        for key in ("allow_merge_commit", "allow_squash_merge", "allow_rebase_merge"):
            del gh.meta[key]
        code, out, _, _ = self.run_audit(gh, "--dry-run")
        self.assertEqual(code, 3)
        self.assertEqual(self.result_json()["outcome"], "unverified")
        self.assertIn("not verified: merge settings: allow_merge_commit is not visible to this token", out)
        self.assertNotIn("No drift in the public repositories", out)

    def test_one_hidden_merge_setting_alone_is_unverified(self):
        gh = FakeGitHub()
        del gh.meta["allow_rebase_merge"]
        self.assertEqual(self.run_audit(gh, "--dry-run")[0], 3)

    def test_branch_rules_404_alone_is_unverified_not_missing(self):
        gh = FakeGitHub()
        del gh.rules["fitment"]
        code, out, _, sinks = self.run_audit(gh, "--dry-run")
        self.assertEqual(code, 3)
        self.assertIn("not verified: fitment: effective rules not readable (HTTP 404)", out)
        self.assertNotIn("branch missing", out)
        self.assert_safe(sinks)

    def test_rulesets_500_alone_is_unverified_with_status_only(self):
        gh = FakeGitHub()
        real = gh.get_all
        gh.get_all = lambda p, limit=1000: (_ for _ in ()).throw(audit.GitHubError(
            500, f"GET https://api.github.com/repos/{REPO}/rulesets: boom")) if "/rulesets?" in p else real(p, limit)
        code, out, _, sinks = self.run_audit(gh, "--dry-run")
        self.assertEqual(code, 3)
        self.assertIn("not verified: could not audit (HTTP 500)", out)
        self.assert_safe(sinks)

    def test_unknown_visibility_alone_is_unverified_and_unnamed(self):
        def lookup_fails(gh):
            real = gh.get
            gh.get = lambda p: (_ for _ in ()).throw(audit.GitHubError(
                502, f"GET https://api.github.com/repos/{REPO}: boom")) if p == f"/repos/{REPO}" else real(p)
        for label, mutate in (("field missing", lambda g: g.meta.pop("private")), ("lookup 502", lookup_fails)):
            gh = FakeGitHub()
            mutate(gh)
            with self.subTest(label):
                code, out, _, sinks = self.run_audit(gh, "--dry-run")
                self.assertEqual(code, 3)
                self.assertNotIn(REPO, out)
                self.assertEqual(self.result_json()["visibility_unknown"], 1)
                self.assertIn("the outcome cannot be clean", out)
                self.assert_safe(sinks)


class PrivateBoundaryTests(_Case):
    """Finding 6 and the original leak: excluded repositories never reach a public sink or the outcome."""

    def test_private_only_drift_leaves_a_clean_public_result(self):
        gh = FakeGitHub()
        gh.add_private()
        code, out, _, sinks = self.run_audit(gh)  # live run: issue behavior too
        self.assertEqual(code, 0)
        self.assertEqual(self.result_json(), {"schema": audit.RESULT_SCHEMA, "outcome": "clean", "repositories": 3,
                                              "public": 1, "public_drift": 0, "public_unverified": 0,
                                              "excluded": 2, "visibility_unknown": 0})
        self.assertEqual(gh.posts, [])  # no issue opened for private drift
        self.assertIn("Excluded: 2 repositories are private or not visible to this token", out)
        self.assert_safe(sinks)

    def test_excluded_repositories_get_no_request_beyond_visibility(self):
        gh = FakeGitHub()
        gh.add_private()
        self.run_audit(gh, "--dry-run")  # get_all raises if an excluded repository is audited
        self.assertEqual([p for p in gh.requests if "secret" in p or "hidden" in p],
                         [f"/repos/{PRIVATE}", f"/repos/{HIDDEN}"])

    def test_mixed_public_and_private_drift_reports_public_only(self):
        gh = FakeGitHub()
        gh.add_private()
        gh.meta["allow_rebase_merge"] = True
        code, out, _, sinks = self.run_audit(gh)
        self.assertEqual(code, 1)
        result = self.result_json()
        self.assertEqual((result["public_drift"], result["excluded"]), (1, 2))
        self.assertIn("allow_rebase_merge is true", out)
        self.assertNotIn("allow_squash_merge is true", out)  # the private repository's drift
        self.assertEqual(len(gh.posts), 1)
        self.assert_safe(sinks)

    def test_dry_run_prints_the_same_report_and_writes_nothing(self):
        gh = FakeGitHub()
        gh.add_private()
        dry = self.run_audit(gh, "--dry-run")[1]
        self.assertEqual((gh.posts, gh.patches), ([], []))
        live = self.run_audit(FakeGitHub())[1]
        self.assertTrue(live.startswith(dry.split("Excluded:")[0].replace("3 protected", "1 protected")
                                        .replace("2 excluded", "0 excluded")))


class ErrorPathTests(_Case):
    """Finding 1: no exception text reaches any sink, and the result file says error."""

    def assert_error(self, gh, *extra):
        code, out, err, sinks = self.run_audit(gh, *extra)
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertTrue(err.startswith("error: "))
        self.assert_safe(sinks)
        return err

    def test_unusable_fitment_config(self):
        self.fitment.write_text(json.dumps({"schema": "aems.fitment-config.v1", "repositories": [PRIVATE + "!!"]}))
        err = self.assert_error(FakeGitHub(), "--dry-run")
        self.assertIn("unusable configuration", err)
        self.assertEqual(self.result_json(), {"schema": audit.RESULT_SCHEMA, "outcome": "error"})

    def test_unparseable_required_checks(self):
        self.required.write_text("{not json " + PRIVATE)
        self.assertIn("unusable configuration", self.assert_error(FakeGitHub(), "--dry-run"))

    def test_required_checks_naming_a_private_repository_badly(self):
        self.required.write_text(json.dumps({"schema": "aems.required-checks.v1", "apps": {"a": 1},
                                             "repositories": {PRIVATE: {"main": [{"context": "x", "app": "b"}]}}}))
        self.assert_error(FakeGitHub(), "--dry-run")

    def test_invalid_inventory_entry_naming_a_private_repository(self):
        gh = FakeGitHub()
        gh.inventory["repositories"].append({"full_name": PRIVATE, "default_branch_policy": "bogus"})
        self.assertIn("inventory is unusable", self.assert_error(gh, "--dry-run"))

    def test_inventory_read_failure_reports_status_only(self):
        gh = FakeGitHub()
        gh.get = lambda p: (_ for _ in ()).throw(audit.GitHubError(
            403, f"GET https://api.github.com/repos/{PRIVATE}/contents: Forbidden"))
        self.assertIn("(HTTP 403)", self.assert_error(gh, "--dry-run"))

    def test_output_file_write_failure(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = audit.main(["--fitment-config", str(self.fitment), "--required-checks", str(self.required),
                               "--dry-run", "--output", str(Path(self.tmp.name) / "missing-dir" / PRIVATE)],
                              reader=FakeGitHub(), writer=FakeGitHub())
        self.assertEqual(code, 2)
        self.assertEqual(err.getvalue(), "error: could not write an output file (FileNotFoundError)\n")

    def test_issue_update_failure_reports_status_only(self):
        gh = FakeGitHub()
        gh.meta["allow_squash_merge"] = True
        gh.post = lambda p, b: (_ for _ in ()).throw(audit.GitHubError(
            422, f"POST https://api.github.com/repos/dlworrell/AEMS/issues: {PRIVATE}"))
        code, _, err, _ = self.run_audit(gh)
        self.assertEqual(code, 2)
        self.assertEqual(err, "error: issue update failed (HTTP 422)\n")


class PreservedIssueTests(_Case):
    """The evidence issue #170 (title "Ruleset drift", label ruleset-drift) is never touched."""

    EVIDENCE = {"number": 170, "title": "Ruleset drift", "labels": [{"name": "ruleset-drift"}],
                "body": "# Ruleset drift audit\n\n(evidence of the first version)"}

    def touched(self, gh, number):
        return [c for c in gh.posts + gh.patches if f"/issues/{number}" in c[0]]

    def test_preserved_issue_survives_drift_unverified_and_clean_runs(self):
        for label, mutate, expected_code in (
                ("drift", lambda g: g.meta.update(allow_squash_merge=True), 1),
                ("unverified", lambda g: g.meta.pop("allow_rebase_merge"), 3),
                ("clean", lambda g: None, 0)):
            for body in (self.EVIDENCE["body"], audit.ISSUE_MARKER + "\nold"):  # even with the marker
                gh = FakeGitHub()
                gh.issues = [dict(self.EVIDENCE, body=body)]
                mutate(gh)
                with self.subTest(label, marker=body.startswith(audit.ISSUE_MARKER)):
                    self.assertEqual(self.run_audit(gh)[0], expected_code)
                    self.assertEqual(self.touched(gh, 170), [])

    def test_drift_opens_a_new_issue_instead_of_using_170(self):
        gh = FakeGitHub()
        gh.issues = [dict(self.EVIDENCE, title="Ruleset drift audit", body=audit.ISSUE_MARKER + "\nold")]
        gh.meta["allow_squash_merge"] = True
        self.run_audit(gh)
        self.assertEqual(gh.posts[0][0], "/repos/dlworrell/AEMS/issues")
        self.assertEqual(gh.posts[0][1]["title"], "Ruleset drift audit")

    def test_title_alone_never_selects_an_issue(self):
        gh = FakeGitHub()
        gh.issues = [{"number": 12, "title": "Ruleset drift audit", "body": "someone else's issue"}]
        self.run_audit(gh)  # clean
        self.assertEqual(self.touched(gh, 12), [])

    def test_extra_preserved_issue_is_never_touched(self):
        gh = FakeGitHub()
        gh.issues = [{"number": 9, "title": "Ruleset drift audit", "body": audit.ISSUE_MARKER + "\nold"}]
        self.run_audit(gh, "--preserve-issue", "9")
        self.assertEqual(self.touched(gh, 9), [])


class OwnIssueLifecycleTests(_Case):
    def test_opens_updates_and_closes_only_when_clean(self):
        gh = FakeGitHub()
        gh.meta["allow_rebase_merge"] = True
        code, out, _, _ = self.run_audit(gh)
        self.assertEqual((code, gh.posts[0][1]["labels"]), (1, ["ruleset-drift"]))
        self.assertIn("issue opened", out)
        gh.issues = [{"number": 9, "title": "Ruleset drift audit", "body": gh.posts[0][1]["body"]}]
        self.assertIn("issue unchanged", self.run_audit(gh)[1])
        gh.meta["allow_squash_merge"] = True
        self.assertIn("issue updated", self.run_audit(gh)[1])
        # Unverified: updated, never closed.
        gh.meta.update(allow_squash_merge=False)
        del gh.meta["allow_rebase_merge"]
        code, out, _, _ = self.run_audit(gh)
        self.assertEqual(code, 3)
        self.assertIn("issue updated", out)
        self.assertNotIn(("/repos/dlworrell/AEMS/issues/9", {"state": "closed", "state_reason": "completed"}),
                         gh.patches)
        # Clean and verified: closed.
        gh.meta["allow_rebase_merge"] = False
        code, out, _, _ = self.run_audit(gh)
        self.assertEqual(code, 0)
        self.assertIn("issue closed", out)
        self.assertIn(("/repos/dlworrell/AEMS/issues/9", {"state": "closed", "state_reason": "completed"}),
                      gh.patches)

    def test_unverified_never_opens_an_issue(self):
        gh = FakeGitHub()
        del gh.meta["allow_merge_commit"]
        self.assertEqual(self.run_audit(gh)[0], 3)
        self.assertEqual(gh.posts, [])

    def test_not_adopted_repository_skips_integration_branches(self):
        self.fitment.write_text(json.dumps({"schema": "aems.fitment-config.v1", "repositories": []}))
        gh = FakeGitHub()
        gh.rulesets.pop(2)
        del gh.rules["fitment"], gh.rules["dev-daily"]
        self.assertEqual(self.run_audit(gh, "--dry-run")[0], 0)


class WorkflowContractTests(unittest.TestCase):
    """Finding 4: the workflow keeps the unverified outcome; it is never turned into a pass."""

    def setUp(self):
        self.text = (ROOT / ".github/workflows/ruleset-drift-audit.yml").read_text()

    def test_exit_status_is_passed_through(self):
        self.assertIn('exit "$status"', self.text)
        self.assertNotIn("exit 0", self.text)

    def test_outcome_is_published_as_a_step_output(self):
        self.assertIn("--result-json", self.text)
        self.assertIn("outcome=", self.text)
        self.assertIn("GITHUB_OUTPUT", self.text)


if __name__ == "__main__":
    unittest.main()
