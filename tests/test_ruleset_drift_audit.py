import base64
import copy
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
GOOD_RULES = [{"type": "deletion"}, {"type": "non_fast_forward"}, {"type": "required_signatures"},
              {"type": "pull_request", "parameters": {"allowed_merge_methods": ["merge"]}}]


def checks(*contexts):
    return {"type": "required_status_checks",
            "parameters": {"required_status_checks": [{"context": c} for c in contexts]}}


class FakeGitHub:
    def __init__(self):
        inventory = {"schema": "catylist.repository-inventory.v1",
                     "repositories": [{"full_name": REPO, "default_branch_policy": "protected"},
                                      {"full_name": "dlworrell/ext", "default_branch_policy": "excluded"}]}
        self.inventory = inventory
        self.meta = {"default_branch": "main", "allow_merge_commit": True, "allow_squash_merge": False,
                     "allow_rebase_merge": False}
        self.rulesets = [{"name": n, "enforcement": "active"} for n in
                         ("protect-default-branch", "protect-release-tags", "protect-integration-branches")]
        self.rules = {"main": GOOD_RULES + [checks("build")], "dev-daily": list(GOOD_RULES),
                      "fitment": list(GOOD_RULES)}
        self.issues = []
        self.posts, self.patches = [], []

    def get(self, path):
        if path.endswith("/contents/inventory/repositories.json"):
            return {"encoding": "base64", "content": base64.b64encode(json.dumps(self.inventory).encode()).decode()}
        if path == f"/repos/{REPO}":
            return self.meta
        raise AssertionError(path)

    def get_all(self, path, limit=1000):
        if "/rulesets?" in path:
            return self.rulesets
        if "/rules/branches/" in path:
            branch = path.split("/rules/branches/")[1].split("?")[0]
            if branch not in self.rules:
                raise audit.GitHubError(404, "Not Found")
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


def required(main=("build",), **branches):
    data = {"schema": "aems.required-checks.v1", "apps": {"github-actions": 15368},
            "repositories": {REPO: {"main": [{"context": c, "app": "github-actions"} for c in main],
                                    **{b: [{"context": c, "app": "github-actions"} for c in v]
                                       for b, v in branches.items()}}}}
    return data


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        tmp = Path(self.tmp.name)
        self.fitment = tmp / "fitment.json"
        self.fitment.write_text(json.dumps({"schema": "aems.fitment-config.v1", "repositories": [REPO]}))
        self.required = tmp / "required.json"
        self.required.write_text(json.dumps(required()))

    def run_audit(self, gh, *extra):
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            code = audit.main(["--fitment-config", str(self.fitment), "--required-checks", str(self.required),
                               *extra], reader=gh, writer=gh)
        return code, out.getvalue()

    def test_clean_repository_passes_and_skips_unprotected_entries(self):
        gh = FakeGitHub()
        code, out = self.run_audit(gh, "--dry-run")
        self.assertEqual(code, 0, out)
        self.assertIn("1 repositories checked; 0 with drift", out)
        self.assertEqual((gh.posts, gh.patches), ([], []))

    def test_each_kind_of_drift_is_reported(self):
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
            "integration branch deleted": (lambda g: g.rules.pop("fitment"), "fitment: branch missing"),
            "required check drift": (lambda g: g.rules["main"].__setitem__(4, checks("build", "lint")),
                                     "main: required checks differ from config/required-checks.json "
                                     "(unexpected lint)"),
        }
        for label, (mutate, expected) in cases.items():
            gh = FakeGitHub()
            mutate(gh)
            with self.subTest(label):
                code, out = self.run_audit(gh, "--dry-run")
                self.assertEqual(code, 1)
                self.assertIn(expected, out)

    def test_missing_required_check_and_hidden_merge_settings(self):
        self.required.write_text(json.dumps(required(**{"dev-daily": ["verify"]})))
        gh = FakeGitHub()
        for key in ("allow_merge_commit", "allow_squash_merge", "allow_rebase_merge"):
            del gh.meta[key]
        code, out = self.run_audit(gh, "--dry-run")
        self.assertEqual(code, 1)
        self.assertIn("dev-daily: required checks differ from config/required-checks.json (missing verify)", out)
        self.assertIn("Not verified with this token: allow_merge_commit is not visible", out)
        self.assertNotIn("merge settings:", out)  # invisible is not drift

    def test_issue_opens_updates_and_closes(self):
        gh = FakeGitHub()
        gh.meta["allow_rebase_merge"] = True
        code, out = self.run_audit(gh)
        self.assertEqual(code, 1)
        self.assertIn("issue opened", out)
        self.assertEqual(gh.posts[0][1]["labels"], ["ruleset-drift"])
        gh.issues = [{"number": 9, "title": "Ruleset drift", "body": gh.posts[0][1]["body"]}]
        self.assertIn("issue unchanged", self.run_audit(gh)[1])
        gh.meta["allow_squash_merge"] = True
        self.assertIn("issue updated", self.run_audit(gh)[1])
        gh.meta.update(allow_rebase_merge=False, allow_squash_merge=False)
        code, out = self.run_audit(gh)
        self.assertEqual(code, 0)
        self.assertIn("issue closed", out)
        self.assertIn(("/repos/dlworrell/AEMS/issues/9", {"state": "closed", "state_reason": "completed"}),
                      gh.patches)

    def test_unreadable_repository_is_drift_and_bad_input_exits_2(self):
        gh = FakeGitHub()
        gh.get_all = lambda path, limit=1000: (_ for _ in ()).throw(audit.GitHubError(500, "boom"))
        code, out = self.run_audit(gh, "--dry-run")
        self.assertEqual(code, 1)
        self.assertIn("could not audit", out)
        self.fitment.write_text("{}")
        self.assertEqual(self.run_audit(FakeGitHub(), "--dry-run")[0], 2)

    def test_not_adopted_repository_skips_integration_branches(self):
        self.fitment.write_text(json.dumps({"schema": "aems.fitment-config.v1", "repositories": []}))
        gh = FakeGitHub()
        gh.rulesets.pop(2)
        del gh.rules["fitment"], gh.rules["dev-daily"]
        self.assertEqual(self.run_audit(gh, "--dry-run")[0], 0)


if __name__ == "__main__":
    unittest.main()
