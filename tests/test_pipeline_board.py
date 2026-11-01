import datetime as dt
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
spec = importlib.util.spec_from_file_location("pipeline_board", ROOT / "scripts/pipeline_board.py")
pb = importlib.util.module_from_spec(spec)
sys.modules["pipeline_board"] = pb
spec.loader.exec_module(pb)

NOW = dt.datetime(2026, 11, 1, 19, 0, tzinfo=dt.timezone.utc)
REPO = "dlworrell/demo"


def pull(number, base, head, merged=None, sha=None, title="t", user="dlworrell"):
    return {"number": number, "title": f"{title} {number}", "html_url": f"https://github.com/{REPO}/pull/{number}",
            "base": {"ref": base}, "head": {"ref": head}, "user": {"login": user}, "draft": False,
            "merged_at": merged, "merge_commit_sha": sha}


class FakeGitHub:
    """Commit graph: a topic merged into dev-daily (t1) promoted (p1) and released (r1); t2 only on fitment."""

    def __init__(self, contains=None, branches=True, open_pulls=None, fail=None, mergeable="clean",
                 promotions=None, candidates=None):
        self.contains = contains if contains is not None else {
            ("t1", "fitment"), ("t1", "main"), ("t1", "v1.0.0"), ("t1", "p1"), ("t1", "r1"),
            ("t2", "fitment"), ("t2", "p2")}
        self.branches = branches
        self.open_pulls = open_pulls if open_pulls is not None else [
            pull(9, "dev-daily", "feature"), pull(8, "main", "fitment"),
            pull(7, "main", "dependabot/pip/x", user="dependabot[bot]")]
        self.fail = fail            # path fragment whose GET raises GitHubError(500)
        self.mergeable = mergeable
        self.promotions = promotions if promotions is not None else [
            pull(4, "fitment", "dev-daily", "2026-10-30T06:00:00Z", "p1"),
            pull(6, "fitment", "dev-daily", "2026-10-31T06:00:00Z", "p2")]
        self.candidates = candidates if candidates is not None else [
            pull(5, "main", "fitment", "2026-10-30T12:00:00Z", "r1")]
        self.posts, self.patches = [], []
        self.issues = []

    def get(self, path):
        if self.fail and self.fail in path:
            raise pb.GitHubError(500, "Server Error")
        if path == f"/repos/{REPO}":
            return {"default_branch": "main"}
        if "/branches/" in path:
            if not self.branches:
                raise pb.GitHubError(404, "Branch not found")
            return {}
        if "/compare/" in path:
            base, head = path.rsplit("/compare/", 1)[1].split("...")
            if base == "fitment" and head == "dev-daily":
                return {"ahead_by": 0}
            if base == "main" and head == "fitment":
                return {"ahead_by": 2}
            return {"status": "ahead" if (base, head) in self.contains else "diverged"}
        if path.startswith(f"/repos/{REPO}/pulls/"):
            return {"mergeable_state": self.mergeable}
        raise AssertionError(path)

    def get_all(self, path, limit=1000):
        if "pulls?state=open" in path:
            return self.open_pulls
        if "pulls?state=closed&base=dev-daily" in path:
            return [pull(1, "dev-daily", "fix/1", "2026-10-30T00:00:00Z", "t1"),
                    pull(2, "dev-daily", "fix/2", "2026-10-31T00:00:00Z", "t2"),
                    pull(3, "dev-daily", "old", "2026-09-01T00:00:00Z", "t0")]
        if "pulls?state=closed&base=fitment" in path:
            return self.promotions
        if "pulls?state=closed&base=main" in path:
            return self.candidates
        if "/releases" in path:
            return [{"tag_name": "v1.0.0"}]
        if "/issues?" in path:
            return self.issues
        raise AssertionError(path)

    def post(self, path, body):
        self.posts.append((path, body))
        return {"number": 50}

    def patch(self, path, body):
        self.patches.append((path, body))
        return {}


class PipelineBoardTests(unittest.TestCase):
    def test_stages_and_nested_carriers(self):
        status = pb.inspect(FakeGitHub(), REPO, NOW)
        self.assertEqual(status.waiting_candidate, 2)
        self.assertEqual([p["number"] for p in status.open_topic], [9])
        self.assertEqual([p["number"] for p in status.open_candidate], [8])
        self.assertEqual([p["number"] for p in status.stray], [7])
        self.assertTrue(status.open_candidate[0]["ready"])
        changes = {c.number: c for c in status.changes}
        self.assertNotIn(3, changes)  # older than the window
        self.assertEqual((changes[1].stage, changes[1].promotion, changes[1].candidate, changes[1].release),
                         ("released", 4, 5, "v1.0.0"))
        self.assertEqual((changes[2].stage, changes[2].promotion, changes[2].candidate), ("fitment", 6, None))

    def test_render_shows_needs_flight_and_landed(self):
        body = pb.render([pb.inspect(FakeGitHub(), REPO, NOW)], NOW)
        self.assertIn("release candidate [#8]", body)
        self.assertIn("ready to merge", body)
        self.assertIn("[#7](https://github.com/dlworrell/demo/pull/7) targets main directly", body)
        self.assertIn("🟠 fitment: **dlworrell/demo** [#2]", body)
        self.assertIn("in promotion [#6]", body)
        self.assertIn("[#1](https://github.com/dlworrell/demo/pull/1) → in promotion [#4]"
                      "(https://github.com/dlworrell/demo/pull/4) → in RC [#5]", body)
        self.assertIn("released v1.0.0", body)
        self.assertEqual(body, pb.render([pb.inspect(FakeGitHub(), REPO, NOW)], NOW))  # deterministic

    def test_missing_branches_are_reported_not_raised(self):
        status = pb.inspect(FakeGitHub(branches=False), REPO, NOW)
        self.assertEqual(status.problem, "dev-daily or fitment branch missing")
        self.assertIn("⚠️ dev-daily or fitment branch missing", pb.render([status], NOW))

    def test_publish_creates_then_skips_timestamp_only_changes_then_updates(self):
        gh = FakeGitHub()
        body = pb.render([pb.inspect(gh, REPO, NOW)], NOW)
        self.assertEqual(pb.publish(gh, "dlworrell/AEMS", body), "created")
        self.assertEqual(gh.posts[0][1]["labels"], [pb.BOARD_LABEL])
        gh.issues = [{"number": 50, "title": pb.BOARD_TITLE, "body": body}]
        later = pb.render([pb.inspect(gh, REPO, NOW + dt.timedelta(hours=1))], NOW + dt.timedelta(hours=1))
        self.assertEqual(pb.publish(gh, "dlworrell/AEMS", later), "unchanged")
        self.assertEqual(pb.publish(gh, "dlworrell/AEMS", later + "\nchanged\n"), "updated")
        self.assertEqual(gh.patches[0][0], "/repos/dlworrell/AEMS/issues/50")

    def test_config_refusals_and_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fitment.json"
            for bad in ({"schema": "x", "repositories": []},
                        {"schema": pb.CONFIG_SCHEMA, "repositories": ["a/b", "A/B"]},
                        {"schema": pb.CONFIG_SCHEMA, "repositories": ["not a repo"]}):
                path.write_text(json.dumps(bad))
                with self.subTest(bad=bad), self.assertRaises(pb.BoardError):
                    pb.load_repositories(path)
            path.write_text(json.dumps({"schema": pb.CONFIG_SCHEMA, "repositories": [REPO]}))
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(pb.main(["--config", str(path), "--dry-run"], reader=FakeGitHub(), now=NOW), 0)
            self.assertIn("# Pipeline board", out.getvalue())
            gh = FakeGitHub()
            with redirect_stdout(io.StringIO()):
                self.assertEqual(pb.main(["--config", str(path)], reader=gh, writer=gh, now=NOW), 0)
            self.assertEqual(len(gh.posts), 1)
            with redirect_stderr(io.StringIO()):
                self.assertEqual(pb.main(["--config", str(Path(tmp) / "missing.json"), "--dry-run"],
                                         reader=FakeGitHub(), now=NOW), 2)

    def test_stage_follows_ancestry_when_no_carrier_matches(self):
        # Fixes #145: a squash merge, direct push or carrier outside the window still shows its real stage.
        status = pb.inspect(FakeGitHub(promotions=[], candidates=[]), REPO, NOW)
        changes = {c.number: c for c in status.changes}
        self.assertEqual((changes[1].stage, changes[1].promotion, changes[1].candidate, changes[1].release),
                         ("released", None, None, "v1.0.0"))
        self.assertEqual((changes[2].stage, changes[2].promotion), ("fitment", None))
        body = pb.render([status], NOW)
        self.assertIn("on fitment (carrier unknown) → on main (carrier unknown) → released v1.0.0", body)
        self.assertIn("[#2](https://github.com/dlworrell/demo/pull/2) → on fitment (carrier unknown) → awaiting RC",
                      body)

    def test_compare_errors_become_the_warning_row(self):
        # Fixes #146: a failing compare must not read as "up to date" or an earlier stage.
        for fragment in ("/compare/fitment...dev-daily", "/compare/t1...fitment"):
            with self.subTest(fragment=fragment):
                with self.assertRaises(pb.GitHubError):
                    pb.inspect(FakeGitHub(fail=fragment), REPO, NOW)
                with tempfile.TemporaryDirectory() as tmp:
                    path = Path(tmp) / "fitment.json"
                    path.write_text(json.dumps({"schema": pb.CONFIG_SCHEMA, "repositories": [REPO]}))
                    out = io.StringIO()
                    with redirect_stdout(out):
                        self.assertEqual(pb.main(["--config", str(path), "--dry-run"],
                                                 reader=FakeGitHub(fail=fragment), now=NOW), 0)
                self.assertIn(f"| {REPO} | ⚠️ unreadable (", out.getvalue())
                self.assertNotIn("up to date", out.getvalue())

    def test_unreadable_repository_and_remaining_needs_lines(self):
        # Fixes #148.
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fitment.json"
            path.write_text(json.dumps({"schema": pb.CONFIG_SCHEMA, "repositories": [REPO]}))
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(pb.main(["--config", str(path), "--dry-run"],
                                         reader=FakeGitHub(fail=f"/repos/{REPO}"), now=NOW), 0)
        self.assertIn(f"| {REPO} | ⚠️ unreadable (", out.getvalue())
        self.assertIn("Nothing to merge right now.", out.getvalue())
        no_rc = pb.render([pb.inspect(FakeGitHub(open_pulls=[pull(9, "dev-daily", "feature")]), REPO, NOW)], NOW)
        self.assertIn("**dlworrell/demo**: 2 commit(s) on fitment are not on main yet", no_rc)
        promoting = FakeGitHub(open_pulls=[pull(10, "fitment", "dev-daily")], mergeable="blocked")
        body = pb.render([pb.inspect(promoting, REPO, NOW)], NOW)
        self.assertIn("**dlworrell/demo** promotion [#10](https://github.com/dlworrell/demo/pull/10) "
                      "(dev-daily → fitment): waiting on checks", body)

    def test_committed_config_loads(self):
        self.assertIn("dlworrell/AEMS", pb.load_repositories(pb.DEFAULT_CONFIG))


if __name__ == "__main__":
    unittest.main()
