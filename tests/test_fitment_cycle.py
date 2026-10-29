from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import fitment_cycle as fc


REPO = "dlworrell/ruleset-sandbox"
NOW = dt.datetime(2026, 10, 26, 12, 0, tzinfo=dt.timezone.utc)
FIT = "f" * 40
DAILY = "d" * 40
MAIN = "a" * 40
FAKE_KEY = "sk-" + "ant-" + "x" * 30
CONFIG = fc.Config("dlworrell/AEMS", "claude-opus-5-5", "medium", (REPO,))


def finding(**overrides) -> dict:
    item = {"file": "src/tool.py", "kind": "test", "severity": "major", "title": "New --strict flag has no test",
            "detail": "The patch adds --strict but no test exercises it.", "remedy": "Add a refusal-case test."}
    item.update(overrides)
    return item


class FakeBlock:
    def __init__(self, text):
        self.type = "text"
        self.text = text


class FakeResponse:
    def __init__(self, text, stop_reason="end_turn"):
        self.content = [FakeBlock(text)]
        self.stop_reason = stop_reason


class FakeModel:
    def __init__(self, responder):
        self.responder = responder
        self.requests: list[dict] = []
        self.beta = self
        self.messages = self

    def create(self, **kwargs):
        self.requests.append(kwargs)
        return self.responder(kwargs)


def reviewer(findings=None, key=FAKE_KEY, responder=None):
    model = FakeModel(responder or (lambda _r: FakeResponse(json.dumps({"findings": findings or [], "summary": "ok"}))))
    return fc.Reviewer(prompt="prompt", model="claude-opus-5-5", effort="medium", api_key=key,
                       client_factory=lambda _k: model), model


class FakeGitHub:
    def __init__(self, routes: dict[str, object]):
        self.routes = routes
        self.posts: list[tuple[str, dict]] = []
        self.patches: list[tuple[str, dict]] = []
        self.puts: list[tuple[str, dict]] = []

    def get(self, path):
        if path in self.routes:
            value = self.routes[path]
        else:
            matches = [k for k in self.routes if path.startswith(k + "?")]
            if not matches:
                raise fc.GitHubError(404, f"no route for {path}")
            value = self.routes[max(matches, key=len)]
        if isinstance(value, Exception):
            raise value
        return value

    def get_all(self, path, limit=1000):
        value = self.get(path)
        if isinstance(value, dict) and "repositories" in value:
            value = value["repositories"]
        return list(value)[:limit]

    def post(self, path, body):
        self.posts.append((path, body))
        return {"number": 100 + len(self.posts)}

    def put(self, path, body):
        self.puts.append((path, body))
        return {}

    def patch(self, path, body):
        self.patches.append((path, body))
        return {}

    def graphql(self, query, variables):
        return {}

    def raw(self, url):
        return None


def green(*names):
    return {"check_runs": [{"name": n, "status": "completed", "conclusion": "success"} for n in names or ("Test",)]}


def routes(**extra) -> dict:
    base = {
        "/installation/repositories": {"repositories": [{"full_name": REPO}]},
        f"/repos/{REPO}": {"default_branch": "main"},
        f"/repos/{REPO}/branches/dev-daily": {"commit": {"sha": DAILY}},
        f"/repos/{REPO}/branches/fitment": {"commit": {"sha": FIT}},
        # The shared fixture models branches with both deletion and PR rules.
        f"/repos/{REPO}/rules/branches/dev-daily": [{"type": "deletion"}, {"type": "pull_request"}],
        f"/repos/{REPO}/rules/branches/fitment": [{"type": "deletion"}, {"type": "pull_request"}],
        f"/repos/{REPO}/pulls?state=open&base=fitment&per_page=100": [],
        f"/repos/{REPO}/pulls?state=open&base=main&per_page=100": [],
        f"/repos/{REPO}/issues?state=open&labels=fitment&per_page=100": [],
        f"/repos/{REPO}/compare/main...fitment": {"ahead_by": 0, "commits": [], "files": []},
        f"/repos/{REPO}/compare/main...{FIT}": {"ahead_by": 0, "commits": [], "files": []},
        f"/repos/{REPO}/compare/fitment...dev-daily": {"ahead_by": 0},
        f"/repos/{REPO}/commits/{FIT}/check-runs": green(),
        f"/repos/{REPO}/commits/{DAILY}/check-runs": green(),
        f"/repos/{REPO}/pulls?state=open&head=dlworrell:dev-daily&base=fitment&per_page=10": [],
        f"/repos/{REPO}/pulls?state=open&head=dlworrell:fitment&base=main&per_page=10": [],
        f"/repos/{REPO}/commits": [{"author": {"login": "contributor"}}],
        f"/repos/{REPO}/assignees/contributor": {},
    }
    base.update(extra)
    return base


def promoted(files=("src/tool.py",), messages=("feat: add --strict",)) -> dict:
    return {"ahead_by": len(messages), "status": "ahead",
            "html_url": f"https://github.com/{REPO}/compare/main...{FIT}",
            "commits": [{"sha": "c" * 40, "commit": {"message": m}} for m in messages],
            "files": [{"filename": f, "status": "modified", "patch": "@@ -1 +1,2 @@\n x\n+y"} for f in files]}


class PureTests(unittest.TestCase):
    def test_parse_review_validates_and_scopes_findings(self):
        found, summary = fc.parse_review({"findings": [finding(), finding(file="other.py")], "summary": "s"},
                                         {"src/tool.py"})
        self.assertEqual([f.file for f in found], ["src/tool.py"])
        self.assertEqual(summary, "s")
        for bad in ({}, {"findings": "x"}, {"findings": [finding(kind="style")]},
                    {"findings": [finding(severity="critical")]}, {"findings": [finding(title="")]}, {"findings": [1]}):
            with self.subTest(bad=bad), self.assertRaises(fc.ReviewUnavailable):
                fc.parse_review(bad, {"src/tool.py"})

    def test_fingerprint_ignores_case_and_punctuation_but_not_file_or_kind(self):
        a = fc.ReviewFinding("a.py", "test", "major", "New --strict flag has no test!", "", "")
        b = fc.ReviewFinding("a.py", "test", "minor", "new strict FLAG has no test", "x", "y")
        self.assertEqual(a.fingerprint, b.fingerprint)
        self.assertNotEqual(a.fingerprint, fc.ReviewFinding("b.py", "test", "major", a.title, "", "").fingerprint)
        self.assertNotEqual(a.fingerprint, fc.ReviewFinding("a.py", "documentation", "major", a.title, "", "").fingerprint)

    def test_batches_split_and_omit_oversized_patches_without_truncating(self):
        files = [{"path": f"f{i}", "status": "modified", "patch": "x" * 400} for i in range(10)]
        batches = fc.review_batches(files, limit=1200)
        self.assertGreater(len(batches), 1)
        self.assertEqual(sum(len(b) for b in batches), 10)
        huge = fc.review_batches([{"path": "big", "status": "added", "patch": "x" * 5000}], limit=1200)
        self.assertIsNone(huge[0][0]["patch"])
        self.assertIn("patch_omitted", huge[0][0])

    def test_closing_references(self):
        self.assertEqual(fc.closing_references("Fixes #12, closes #3 and resolved #40; see #7"), {12, 3, 40})

    def test_ci_outcome(self):
        self.assertFalse(fc.ci_outcome([])[0])
        self.assertFalse(fc.ci_outcome([{"name": "fitment", "status": "completed", "conclusion": "success"}])[0])
        self.assertIn("Waiting", fc.ci_outcome([{"name": "Test", "status": "in_progress"}])[1])
        self.assertIn("Failing: Test", fc.ci_outcome([{"name": "Test", "status": "completed", "conclusion": "failure"}])[1])
        self.assertTrue(fc.ci_outcome(green("Test", "Lint")["check_runs"])[0])

    def test_gate(self):
        ok = (True, "fine")
        self.assertEqual(fc.gate(ok, [], ok)[0], "success")
        self.assertEqual(fc.gate((False, "Failing: Test."), [], ok)[0], "failure")
        self.assertEqual(fc.gate(ok, [], (False, "could not run"))[0], "failure")
        conclusion, _, summary = fc.gate(ok, [{"number": 7}], ok)
        self.assertEqual(conclusion, "failure")
        self.assertIn("#7", summary)

    def test_source_rules(self):
        self.assertEqual(fc.source_outcome("fitment", "dev-daily", "main")[0], "success")
        self.assertEqual(fc.source_outcome("fitment", "fix/1-x", "main")[0], "failure")
        self.assertEqual(fc.source_outcome("main", "fitment", "main")[0], "success")
        self.assertEqual(fc.source_outcome("main", "dev-daily", "main")[0], "failure")
        self.assertIsNone(fc.source_outcome("dev-daily", "fix/1-x", "main"))

    def test_config_refuses_bad_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "c.json"
            for data in ({"schema": "x"},
                         {"schema": fc.CONFIG_SCHEMA, "ledger_repository": "dlworrell/AEMS", "model": "m",
                          "effort": "huge", "repositories": []},
                         {"schema": fc.CONFIG_SCHEMA, "ledger_repository": "dlworrell/AEMS", "model": "m",
                          "effort": "medium", "repositories": ["no slash"]}):
                path.write_text(json.dumps(data))
                with self.subTest(data=data), self.assertRaises(fc.FitmentError):
                    fc.Config.load(path)


class CycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def make(self, gh, review=None, dry_run=False, state=None):
        review = review or reviewer()[0]
        store = fc.StateStore(None, "dlworrell/AEMS", dry_run, Path(self.tmp.name))
        if state is not None:
            store.load = lambda: state  # type: ignore[assignment]
        return fc.Cycle(github=gh, store=store, reviewer=review, config=CONFIG, now=NOW, dry_run=dry_run,
                        log=lambda _m: None)

    def checks(self, gh, name):
        return [b for p, b in gh.posts if p.endswith("/check-runs") and b["name"] == name]

    def test_missing_branch_is_an_error(self):
        gh = FakeGitHub(routes(**{f"/repos/{REPO}/branches/fitment": fc.GitHubError(404, "missing")}))
        cycle = self.make(gh)
        self.assertEqual(cycle.run(), 1)
        self.assertIn("fitment: branch is missing", cycle.errors[0])
        self.assertEqual((gh.posts, gh.patches, gh.puts), ([], [], []))

    def test_unprotected_integration_branch_stops_before_any_cycle_write(self):
        for branch in (fc.DAILY, fc.FITMENT):
            with self.subTest(branch=branch):
                gh = FakeGitHub(routes(**{
                    f"/repos/{REPO}/rules/branches/{branch}": [],
                    f"/repos/{REPO}/compare/fitment...dev-daily": {"ahead_by": 1},
                    f"/repos/{REPO}/compare/main...{FIT}": promoted(),
                }))
                review, model = reviewer([finding()])
                cycle = self.make(gh, review)
                self.assertEqual(cycle.run(), 1)
                self.assertIn(f"{branch}: no active deletion rule", cycle.errors[0])
                self.assertEqual((gh.posts, gh.patches, gh.puts), ([], [], []))
                self.assertEqual(model.requests, [])

    def test_unavailable_retention_evidence_stops_even_a_dry_run(self):
        gh = FakeGitHub(routes(**{
            f"/repos/{REPO}/rules/branches/dev-daily": fc.GitHubError(403, "forbidden"),
        }))
        cycle = self.make(gh, dry_run=True)
        self.assertEqual(cycle.run(), 1)
        self.assertIn("retention is unverified", cycle.errors[0])
        self.assertEqual((gh.posts, gh.patches, gh.puts), ([], [], []))

    def test_finding_is_filed_to_the_author_and_holds_the_gate(self):
        open_issues = []
        gh = FakeGitHub(routes(**{
            f"/repos/{REPO}/compare/main...{FIT}": promoted(),
            f"/repos/{REPO}/compare/main...fitment": promoted(),
            f"/repos/{REPO}/issues?state=open&labels=fitment&per_page=100": open_issues,
        }))
        review, model = reviewer([finding()])
        original_post = gh.post

        def post(path, body):  # issues filed this run become open issues for the gate
            result = original_post(path, body)
            if path == f"/repos/{REPO}/issues":
                open_issues.append({"number": result["number"], "body": body["body"],
                                    "labels": [{"name": n} for n in body["labels"]]})
            return result
        gh.post = post
        cycle = self.make(gh, review)
        self.assertEqual(cycle.run(), 0, cycle.errors)
        issues = [b for p, b in gh.posts if p == f"/repos/{REPO}/issues"]
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["assignees"], ["contributor"])
        self.assertEqual(issues[0]["labels"], ["fitment", "major", "test"])
        self.assertIn("@contributor", issues[0]["body"])
        self.assertIn("Fixes #<this issue number>", issues[0]["body"])
        self.assertIn("Not human review", issues[0]["body"])
        gate = self.checks(gh, "fitment")
        self.assertEqual((gate[0]["head_sha"], gate[0]["conclusion"]), (FIT, "failure"))
        self.assertFalse([b for p, b in gh.posts if p.endswith("/pulls")])
        self.assertEqual(cycle.state["repos"][REPO]["reviewed"], FIT)
        sent = json.loads(model.requests[0]["messages"][0]["content"].split("<change>\n", 1)[1].rsplit("\n</change>", 1)[0])
        self.assertEqual(sent["files"][0]["path"], "src/tool.py")
        self.assertEqual(model.requests[0]["output_config"]["format"]["schema"], fc.REVIEW_SCHEMA)

    def test_known_finding_is_not_filed_again(self):
        fp = fc.ReviewFinding(**finding()).fingerprint
        gh = FakeGitHub(routes(**{
            f"/repos/{REPO}/compare/main...{FIT}": promoted(),
            f"/repos/{REPO}/issues?state=open&labels=fitment&per_page=100": [
                {"number": 5, "body": f"<!-- fitment:fp={fp} -->", "labels": [{"name": "fitment"}, {"name": "minor"}]}],
        }))
        cycle = self.make(gh, reviewer([finding()])[0])
        cycle.run()
        self.assertFalse([p for p, _ in gh.posts if p == f"/repos/{REPO}/issues"])

    def test_bot_author_is_not_assigned(self):
        gh = FakeGitHub(routes(**{
            f"/repos/{REPO}/compare/main...{FIT}": promoted(),
            f"/repos/{REPO}/commits": [{"author": {"login": "github-actions[bot]"}}],
        }))
        self.make(gh, reviewer([finding(severity="minor")])[0]).run()
        issue = next(b for p, b in gh.posts if p == f"/repos/{REPO}/issues")
        self.assertNotIn("assignees", issue)
        self.assertIn("the owner", issue["body"])

    def test_unassignable_author_falls_back_to_the_owner_without_a_mention(self):
        gh = FakeGitHub(routes(**{
            f"/repos/{REPO}/compare/main...{FIT}": promoted(),
            f"/repos/{REPO}/commits": [{"author": {"login": "claude"}}],
        }))
        cycle = self.make(gh, reviewer([finding(severity="minor")])[0])
        self.assertEqual(cycle.run(), 0, cycle.errors)
        issue = next(b for p, b in gh.posts if p == f"/repos/{REPO}/issues")
        self.assertEqual(issue["assignees"], ["dlworrell"])
        self.assertNotIn("@claude", issue["body"])
        self.assertIn("`claude` last changed this file but cannot be assigned", issue["body"])

    def test_review_that_cannot_run_holds_the_gate_and_is_retried(self):
        gh = FakeGitHub(routes(**{f"/repos/{REPO}/compare/main...{FIT}": promoted()}))
        review, model = reviewer(key=None)
        cycle = self.make(gh, review)
        cycle.run()
        gate = self.checks(gh, "fitment")[0]
        self.assertEqual(gate["conclusion"], "failure")
        self.assertIn("could not run", gate["output"]["summary"])
        self.assertNotIn("reviewed", cycle.state["repos"][REPO])
        self.assertEqual(model.requests, [])

    def test_refusal_and_malformed_reviews_hold_the_gate(self):
        for responder in (lambda _r: FakeResponse("{}", stop_reason="refusal"),
                          lambda _r: FakeResponse("not json")):
            with self.subTest():
                gh = FakeGitHub(routes(**{f"/repos/{REPO}/compare/main...{FIT}": promoted()}))
                self.make(gh, reviewer(responder=responder)[0]).run()
                self.assertEqual(self.checks(gh, "fitment")[0]["conclusion"], "failure")

    def test_clean_fitment_opens_the_release_candidate(self):
        gh = FakeGitHub(routes(**{f"/repos/{REPO}/compare/main...fitment": promoted()}))
        cycle = self.make(gh, state={"repos": {REPO: {"reviewed": FIT}}, "posted": {}})
        self.assertEqual(cycle.run(), 0, cycle.errors)
        self.assertEqual(self.checks(gh, "fitment")[0]["conclusion"], "success")
        pulls = [b for p, b in gh.posts if p == f"/repos/{REPO}/pulls"]
        self.assertEqual([(b["head"], b["base"]) for b in pulls], [("fitment", "main")])
        self.assertIn("ADR: Catylist ADR-0013", pulls[0]["body"])
        self.assertIn("never approves or merges", pulls[0]["body"])
        self.assertFalse(gh.patches)

    def test_failing_ci_on_fitment_blocks_release(self):
        gh = FakeGitHub(routes(**{
            f"/repos/{REPO}/compare/main...fitment": promoted(),
            f"/repos/{REPO}/commits/{FIT}/check-runs": {"check_runs": [
                {"name": "Test", "status": "completed", "conclusion": "failure"}]},
        }))
        self.make(gh, state={"repos": {REPO: {"reviewed": FIT}}, "posted": {}}).run()
        self.assertEqual(self.checks(gh, "fitment")[0]["conclusion"], "failure")
        self.assertFalse([b for p, b in gh.posts if p == f"/repos/{REPO}/pulls"])

    def test_green_dev_daily_ahead_is_promoted_once(self):
        gh = FakeGitHub(routes(**{f"/repos/{REPO}/compare/fitment...dev-daily": {"ahead_by": 3}}))
        self.make(gh, state={"repos": {REPO: {"reviewed": FIT}}, "posted": {}}).run()
        pulls = [(b["head"], b["base"]) for p, b in gh.posts if p == f"/repos/{REPO}/pulls"]
        self.assertEqual(pulls, [("dev-daily", "fitment")])
        gh = FakeGitHub(routes(**{
            f"/repos/{REPO}/compare/fitment...dev-daily": {"ahead_by": 3},
            f"/repos/{REPO}/pulls?state=open&head=dlworrell:dev-daily&base=fitment&per_page=10": [{"number": 9}],
        }))
        self.make(gh, state={"repos": {REPO: {"reviewed": FIT}}, "posted": {}}).run()
        self.assertFalse([b for p, b in gh.posts if p == f"/repos/{REPO}/pulls"])

    def test_unprotected_head_branch_is_never_promoted(self):
        # Regression: atarix #86 merged dev-daily into fitment before
        # protect-integration-branches applied; delete-on-merge removed
        # dev-daily and GitHub retargeted atarix #83 to fitment.
        for branch, extra in (("dev-daily", {f"/repos/{REPO}/compare/fitment...dev-daily": {"ahead_by": 2}}),
                              ("fitment", {f"/repos/{REPO}/compare/main...fitment": promoted()})):
            with self.subTest(branch=branch):
                gh = FakeGitHub(routes(**extra, **{f"/repos/{REPO}/rules/branches/{branch}": []}))
                cycle = self.make(gh, state={"repos": {REPO: {"reviewed": FIT}}, "posted": {}})
                self.assertEqual(cycle.run(), 1)
                self.assertFalse([b for p, b in gh.posts if p == f"/repos/{REPO}/pulls"])
                # inspect_branches (the shared preflight in cycle_repository)
                # is the single retention check: it reads every page of
                # effective rules before any write. Bind the diagnostic to the
                # affected branch and retain the no-side-effects check.
                self.assertIn(f"{branch}: no active deletion rule", cycle.errors[0])
                self.assertEqual((gh.posts, gh.patches, gh.puts), ([], [], []))

    def test_red_dev_daily_is_not_promoted(self):
        gh = FakeGitHub(routes(**{
            f"/repos/{REPO}/compare/fitment...dev-daily": {"ahead_by": 3},
            f"/repos/{REPO}/commits/{DAILY}/check-runs": {"check_runs": [
                {"name": "Test", "status": "completed", "conclusion": "failure"}]},
        }))
        self.make(gh, state={"repos": {REPO: {"reviewed": FIT}}, "posted": {}}).run()
        self.assertFalse([b for p, b in gh.posts if p == f"/repos/{REPO}/pulls" and b["base"] == "fitment"])

    def test_fix_reaching_fitment_closes_its_issue(self):
        gh = FakeGitHub(routes(**{
            f"/repos/{REPO}/issues?state=open&labels=fitment&per_page=100": [
                {"number": 12, "body": "", "labels": [{"name": "fitment"}, {"name": "major"}]}],
            f"/repos/{REPO}/compare/main...fitment": promoted(messages=("fix(tool): test --strict\n\nFixes #12",)),
        }))
        self.make(gh, state={"repos": {REPO: {"reviewed": FIT}}, "posted": {}}).run()
        self.assertIn((f"/repos/{REPO}/issues/12", {"state": "closed", "state_reason": "completed"}), gh.patches)
        self.assertTrue(any(p == f"/repos/{REPO}/issues/12/comments" for p, _ in gh.posts))

    def test_source_check_on_promotion_pull_requests(self):
        def pr(number, head):
            return {"number": number, "head": {"ref": head, "sha": str(number) * 40, "repo": {"full_name": REPO}}}
        gh = FakeGitHub(routes(**{
            f"/repos/{REPO}/pulls?state=open&base=fitment&per_page=100": [pr(1, "dev-daily"), pr(2, "fix/3-x")],
            f"/repos/{REPO}/pulls?state=open&base=main&per_page=100": [pr(4, "feat/y")],
        }))
        self.make(gh, state={"repos": {REPO: {"reviewed": FIT}}, "posted": {}}).run()
        source = {b["head_sha"][0]: b["conclusion"] for b in self.checks(gh, "fitment/source")}
        self.assertEqual(source, {"1": "success", "2": "failure", "4": "failure"})

    def test_unchanged_checks_are_not_reposted(self):
        state = {"repos": {REPO: {"reviewed": FIT}}, "posted": {}}
        gh = FakeGitHub(routes())
        self.make(gh, state=state).run()
        first = len(self.checks(gh, "fitment"))
        self.make(gh, state=state).run()
        self.assertEqual(len(self.checks(gh, "fitment")), first)

    def test_dry_run_writes_nothing(self):
        gh = FakeGitHub(routes(**{
            f"/repos/{REPO}/compare/main...{FIT}": promoted(),
            f"/repos/{REPO}/compare/fitment...dev-daily": {"ahead_by": 2},
        }))
        cycle = self.make(gh, reviewer([finding()])[0], dry_run=True)
        cycle.run()
        self.assertEqual((gh.posts, gh.patches, gh.puts), ([], [], []))
        self.assertTrue(any(action == "issue" for _, action, _ in cycle.summary))
        self.assertTrue((Path(self.tmp.name) / "fitment-state.json").exists())

    def test_never_approves_merges_or_pushes(self):
        gh = FakeGitHub(routes(**{f"/repos/{REPO}/compare/main...fitment": promoted(),
                                  f"/repos/{REPO}/compare/fitment...dev-daily": {"ahead_by": 1}}))
        self.make(gh, state={"repos": {REPO: {"reviewed": FIT}}, "posted": {}}).run()
        for path, _ in gh.posts + gh.puts + gh.patches:
            self.assertNotRegex(path, r"/reviews|/merge|/git/refs|/contents/")


class StateStoreTests(unittest.TestCase):
    def test_save_creates_the_ledger_branch_when_missing(self):
        # Regression: the first scheduled cycle ran before any ring-0 sweep had
        # created ring0/ledger, and the state write failed with 404.
        gh = FakeGitHub({
            "/repos/dlworrell/AEMS/git/ref/heads/ring0/ledger": fc.GitHubError(404, "Not Found"),
            "/repos/dlworrell/AEMS": {"default_branch": "main"},
            "/repos/dlworrell/AEMS/git/ref/heads/main": {"object": {"sha": MAIN}},
        })
        with tempfile.TemporaryDirectory() as tmp:
            store = fc.StateStore(gh, "dlworrell/AEMS", False, Path(tmp))
            store.save({"schema": fc.STATE_SCHEMA, "repos": {}, "posted": {}}, NOW)
        self.assertEqual(gh.posts, [("/repos/dlworrell/AEMS/git/refs",
                                     {"ref": "refs/heads/ring0/ledger", "sha": MAIN})])
        self.assertEqual(gh.puts[0][1]["branch"], "ring0/ledger")

    def test_save_leaves_an_existing_ledger_branch_alone(self):
        gh = FakeGitHub({"/repos/dlworrell/AEMS/git/ref/heads/ring0/ledger": {"object": {"sha": MAIN}}})
        with tempfile.TemporaryDirectory() as tmp:
            fc.StateStore(gh, "dlworrell/AEMS", False, Path(tmp)).save({"repos": {}, "posted": {}}, NOW)
        self.assertEqual(gh.posts, [])
        self.assertEqual(len(gh.puts), 1)


if __name__ == "__main__":
    unittest.main()
