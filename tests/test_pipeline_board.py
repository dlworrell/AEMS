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

    def __init__(self, contains=None, branches=True):
        self.contains = contains if contains is not None else {
            ("t1", "fitment"), ("t1", "main"), ("t1", "v1.0.0"), ("t1", "p1"), ("t1", "r1"),
            ("t2", "fitment"), ("t2", "p2")}
        self.branches = branches
        self.posts, self.patches = [], []
        self.issues = []

    def get(self, path):
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
            return {"mergeable_state": "clean"}
        raise AssertionError(path)

    def get_all(self, path, limit=1000):
        if "pulls?state=open" in path:
            return [pull(9, "dev-daily", "feature"), pull(8, "main", "fitment"),
                    pull(7, "main", "dependabot/pip/x", user="dependabot[bot]")]
        if "pulls?state=closed&base=dev-daily" in path:
            return [pull(1, "dev-daily", "fix/1", "2026-10-30T00:00:00Z", "t1"),
                    pull(2, "dev-daily", "fix/2", "2026-10-31T00:00:00Z", "t2"),
                    pull(3, "dev-daily", "old", "2026-09-01T00:00:00Z", "t0")]
        if "pulls?state=closed&base=fitment" in path:
            return [pull(4, "fitment", "dev-daily", "2026-10-30T06:00:00Z", "p1"),
                    pull(6, "fitment", "dev-daily", "2026-10-31T06:00:00Z", "p2")]
        if "pulls?state=closed&base=main" in path:
            return [pull(5, "main", "fitment", "2026-10-30T12:00:00Z", "r1")]
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

    def test_committed_config_loads(self):
        self.assertIn("dlworrell/AEMS", pb.load_repositories(pb.DEFAULT_CONFIG))


if __name__ == "__main__":
    unittest.main()
