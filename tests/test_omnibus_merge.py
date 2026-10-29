from __future__ import annotations

import base64
import datetime as dt
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import omnibus_merge as om


LEDGER = "dlworrell/AEMS"
TARGET = "dlworrell/atarix"
OTHER = "dlworrell/code-noodling"
PATH = "omnibus/wave-1.json"
HEAD_A = "a" * 40
HEAD_B = "b" * 40
MERGE = "c" * 40
BRANCH_COMMIT = "e" * 40
NOW = dt.datetime(2026, 10, 29, 12, 0, tzinfo=dt.timezone.utc)
CONFIG = om.Config(LEDGER, ("dlworrell",), ("dev-daily",), "omnibus", 100)
APPROVAL = om.Approval(90, "dlworrell", MERGE, "dev-daily", f"https://github.com/{LEDGER}/pull/90")


def manifest_text(entries=None, manifest_id="wave-1") -> str:
    entries = entries if entries is not None else [
        {"repository": TARGET, "pull_request": 7, "base": "dev-daily", "head_sha": HEAD_A, "title": "Adopt ADR-0000"},
        {"repository": OTHER, "pull_request": 3, "base": "main", "head_sha": HEAD_B, "title": "Adopt ADR-0013"},
    ]
    return json.dumps({"schema": om.MANIFEST_SCHEMA, "id": manifest_id, "summary": "Wave 1", "entries": entries})


def content(text: str) -> dict:
    return {"content": base64.b64encode(text.encode()).decode(), "encoding": "base64", "sha": "blob"}


def pull(number=7, head=HEAD_A, base="dev-daily", **overrides) -> dict:
    item = {"number": number, "state": "open", "merged": False, "draft": False, "mergeable": True,
            "mergeable_state": "clean", "title": "Adopt ADR-0000", "user": {"login": "dlworrell"},
            "head": {"sha": head, "label": "dlworrell:adopt"}, "base": {"ref": base}}
    item.update(overrides)
    return item


GREEN = {"check_runs": [{"name": "tests", "status": "completed", "conclusion": "success"}]}


class FakeGitHub:
    def __init__(self, routes: dict[str, object]):
        self.routes = routes
        self.posts: list[tuple[str, dict]] = []
        self.puts: list[tuple[str, dict]] = []
        self.gets: list[str] = []

    def get(self, path):
        self.gets.append(path)
        value = self.routes.get(path)
        if value is None:
            raise om.GitHubError(404, f"no route for {path}")
        if isinstance(value, list) and value and isinstance(value[0], tuple):  # sequential responses
            return value.pop(0)[1] if len(value) > 1 else value[0][1]
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
        return {}

    def put(self, path, body):
        self.puts.append((path, body))
        return {"sha": "9" * 40, "merged": True}

    def patch(self, path, body):
        return {}


def installed(*repos):
    return {"/installation/repositories?per_page=100": {"repositories": [{"full_name": r} for r in repos]}}


def target_routes(first=None, second=None) -> dict:
    routes = installed(TARGET, OTHER)
    routes[f"/repos/{TARGET}/pulls/7"] = first or pull()
    routes[f"/repos/{OTHER}/pulls/3"] = second or pull(3, HEAD_B, "main", title="Adopt ADR-0013")
    routes[f"/repos/{TARGET}/commits/{HEAD_A}/check-runs?per_page=100"] = GREEN
    routes[f"/repos/{OTHER}/commits/{HEAD_B}/check-runs?per_page=100"] = GREEN
    return routes


def executor(gh, dry_run=False, text=None):
    manifest = om.parse_manifest(text or manifest_text(), expected_id="wave-1", config=CONFIG)
    return om.Executor(github=gh, config=CONFIG, approval=APPROVAL, manifest=manifest, dry_run=dry_run,
                       sleep=lambda _s: None, log=lambda _m: None)


class ManifestTests(unittest.TestCase):
    def test_valid_manifest_keeps_order(self):
        manifest = om.parse_manifest(manifest_text(), expected_id="wave-1", config=CONFIG)
        self.assertEqual([e.key for e in manifest.entries], [f"{TARGET}#7", f"{OTHER}#3"])

    def test_every_problem_is_reported(self):
        bad = manifest_text([
            {"repository": "someone/else", "pull_request": 1, "base": "main", "head_sha": HEAD_A},
            {"repository": TARGET, "pull_request": 7, "base": "dev-daily", "head_sha": "abc"},
            {"repository": TARGET, "pull_request": 7, "base": "dev-daily", "head_sha": HEAD_A},
        ], manifest_id="other-id")
        with self.assertRaises(om.OmnibusError) as ctx:
            om.parse_manifest(bad, expected_id="wave-1", config=CONFIG)
        message = str(ctx.exception)
        for fragment in ("must match the file name", "not owned by an approver", "40-character", "listed twice"):
            self.assertIn(fragment, message)

    def test_empty_and_oversized_lists_are_refused(self):
        with self.assertRaisesRegex(om.OmnibusError, "non-empty"):
            om.parse_manifest(manifest_text([]), expected_id="wave-1", config=CONFIG)
        small = om.Config(LEDGER, ("dlworrell",), ("dev-daily",), "omnibus", 1)
        with self.assertRaisesRegex(om.OmnibusError, "the limit is 1"):
            om.parse_manifest(manifest_text(), expected_id="wave-1", config=small)

    def test_bots_cannot_be_approvers(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "omnibus.json"
            path.write_text(json.dumps({"schema": om.CONFIG_SCHEMA, "ledger_repository": LEDGER,
                                        "approvers": ["catylist-ring-0[bot]"], "approval_branches": ["dev-daily"]}))
            with self.assertRaisesRegex(om.OmnibusError, "bots cannot approve"):
                om.Config.load(path)

    def test_repository_config_loads(self):
        config = om.Config.load(Path(__file__).resolve().parents[1] / "config" / "omnibus.json")
        self.assertEqual(config.approval_branches, ("dev-daily",))
        self.assertIn("dlworrell", config.approvers)

    def test_body_lists_entries_in_order(self):
        body = om.render_omnibus_body(om.parse_manifest(manifest_text(), expected_id="wave-1", config=CONFIG))
        self.assertLess(body.index(f"{TARGET}#7"), body.index(f"{OTHER}#3"))
        self.assertIn("ADR-0016", body)


def approval_routes(merged_by="dlworrell", verified=True, current=None, history_pulls=None, files=None) -> dict:
    text = manifest_text()
    return {
        f"/repos/{LEDGER}/commits/{MERGE}/pulls": [{"number": 90, "merged_at": "2026-10-29T11:00:00Z",
                                                  "base": {"ref": "dev-daily"}}],
        f"/repos/{LEDGER}/pulls/90": {"number": 90, "merged_by": {"login": merged_by}, "merge_commit_sha": MERGE,
                                      "base": {"ref": "dev-daily"}, "html_url": "u"},
        f"/repos/{LEDGER}/commits/{MERGE}": {"commit": {"verification": {"verified": verified, "reason": "valid"}}},
        f"/repos/{LEDGER}/pulls/90/files?per_page=100": files or [{"filename": "omnibus/wave-1.json"}],
        f"/repos/{LEDGER}/commits?path=omnibus/wave-1.json&sha=dev-daily&per_page=100": [{"sha": BRANCH_COMMIT}],
        f"/repos/{LEDGER}/commits?path=omnibus/wave-1.json&sha=dev-daily&per_page=1": [{"sha": BRANCH_COMMIT}],
        f"/repos/{LEDGER}/commits/{BRANCH_COMMIT}/pulls": history_pulls or [
            {"number": 90, "merged_at": "2026-10-29T11:00:00Z", "base": {"ref": "dev-daily"}}],
        f"/repos/{LEDGER}/contents/omnibus/wave-1.json?ref={MERGE}": content(text),
        f"/repos/{LEDGER}/contents/omnibus/wave-1.json?ref=dev-daily": content(current or text),
    }


class ApprovalTests(unittest.TestCase):
    def test_owner_merge_on_push_is_the_approval(self):
        approval, text = om.find_approval(FakeGitHub(approval_routes()), CONFIG, PATH, MERGE)
        self.assertEqual((approval.pull_request, approval.merged_by), (90, "dlworrell"))
        self.assertEqual(text, manifest_text())

    def test_dispatch_finds_the_approving_pull_request(self):
        gh = FakeGitHub(approval_routes())
        gh.routes[f"/repos/{LEDGER}/commits/{BRANCH_COMMIT}/pulls"] = [
            {"number": 90, "merged_at": "2026-10-29T11:00:00Z", "base": {"ref": "dev-daily"}}]
        approval, _ = om.find_approval(gh, CONFIG, PATH, None)
        self.assertEqual(approval.pull_request, 90)

    def test_merge_by_someone_else_is_refused(self):
        with self.assertRaisesRegex(om.OmnibusError, "not an approver"):
            om.find_approval(FakeGitHub(approval_routes(merged_by="mallory")), CONFIG, PATH, MERGE)

    def test_manifest_inside_a_larger_change_is_not_an_approval(self):
        routes = approval_routes(files=[{"filename": "omnibus/wave-1.json"}, {"filename": "scripts/tool.py"}])
        with self.assertRaisesRegex(om.OmnibusError, "may only add manifests"):
            om.find_approval(FakeGitHub(routes), CONFIG, PATH, MERGE)

    def test_unverified_merge_commit_is_refused(self):
        with self.assertRaisesRegex(om.OmnibusError, "not verified"):
            om.find_approval(FakeGitHub(approval_routes(verified=False)), CONFIG, PATH, MERGE)

    def test_manifest_edited_by_a_later_pull_request_is_refused(self):
        routes = approval_routes(history_pulls=[{"number": 95, "merged_at": "x", "base": {"ref": "dev-daily"}}])
        with self.assertRaisesRegex(om.OmnibusError, "immutable"):
            om.find_approval(FakeGitHub(routes), CONFIG, PATH, MERGE)

    def test_manifest_that_differs_on_the_branch_is_refused(self):
        changed = manifest_text([{"repository": TARGET, "pull_request": 8, "base": "dev-daily", "head_sha": HEAD_A}])
        with self.assertRaisesRegex(om.OmnibusError, "immutable"):
            om.find_approval(FakeGitHub(approval_routes(current=changed)), CONFIG, PATH, MERGE)

    def test_pushed_commit_lists_only_added_manifests(self):
        gh = FakeGitHub({f"/repos/{LEDGER}/commits/{MERGE}": {"files": [
            {"filename": "omnibus/wave-1.json", "status": "added"},
            {"filename": "omnibus/wave-0.json", "status": "modified"},
            {"filename": "omnibus/README.md", "status": "added"},
            {"filename": "docs/omnibus/x.json", "status": "added"}]}})
        self.assertEqual(om.manifests_in_commit(gh, CONFIG, MERGE), ["wave-1"])


class ExecutorTests(unittest.TestCase):
    def test_merges_in_order_at_the_approved_commit(self):
        gh = FakeGitHub(target_routes())
        self.assertEqual(executor(gh).run(), 0)
        self.assertEqual([p for p, _ in gh.puts], [f"/repos/{TARGET}/pulls/7/merge", f"/repos/{OTHER}/pulls/3/merge"])
        first = gh.puts[0][1]
        self.assertEqual((first["merge_method"], first["sha"]), ("merge", HEAD_A))
        self.assertIn(f"{LEDGER}#90", first["commit_message"])
        comments = [p for p, _ in gh.posts]
        self.assertIn(f"/repos/{TARGET}/issues/7/comments", comments)
        self.assertIn(f"/repos/{LEDGER}/issues/90/comments", comments)

    def test_failed_comment_does_not_undo_a_merge(self):
        gh = FakeGitHub(target_routes())

        def post(path, body):
            if "/issues/7/" in path:
                raise om.GitHubError(500, "boom")
            gh.posts.append((path, body))
            return {}

        gh.post = post
        run = executor(gh)
        self.assertEqual(run.run(), 0)
        self.assertEqual(run.outcomes[0].status, "merged")
        self.assertIn("comment not posted", run.outcomes[0].detail)

    def test_moved_head_stops_the_run(self):
        gh = FakeGitHub(target_routes(first=pull(head="f" * 40)))
        run = executor(gh)
        self.assertEqual(run.run(), 1)
        self.assertEqual(gh.puts, [])
        self.assertEqual([o.status for o in run.outcomes], ["refused", "not-attempted"])
        self.assertIn("head moved", run.outcomes[0].detail)

    def test_ring0_never_merges_its_own_pull_request(self):
        gh = FakeGitHub(target_routes(first=pull(user={"login": "catylist-ring-0[bot]"})))
        run = executor(gh)
        self.assertEqual(run.run(), 1)
        self.assertEqual(gh.puts, [])
        self.assertIn("Code Law 4", run.outcomes[0].detail)

    def test_failing_or_pending_checks_are_refused(self):
        for runs, fragment in (({"check_runs": []}, "no check"),
                               ({"check_runs": [{"name": "ci", "status": "in_progress"}]}, "still running"),
                               ({"check_runs": [{"name": "ci", "status": "completed", "conclusion": "failure"}]},
                                "failing")):
            routes = target_routes()
            routes[f"/repos/{TARGET}/commits/{HEAD_A}/check-runs?per_page=100"] = runs
            gh = FakeGitHub(routes)
            run = executor(gh)
            run.run()
            self.assertEqual(gh.puts, [], fragment)
            self.assertIn(fragment, run.outcomes[0].detail)

    def test_blocked_draft_wrong_base_and_closed_are_refused(self):
        cases = ((pull(mergeable_state="blocked"), "not 'clean'"),
                 (pull(draft=True), "draft"),
                 (pull(base="main"), "targets main"),
                 (pull(state="closed"), "closed without merging"),
                 (pull(mergeable=False), "not mergeable"))
        for first, fragment in cases:
            gh = FakeGitHub(target_routes(first=first))
            run = executor(gh)
            run.run()
            self.assertEqual(gh.puts, [], fragment)
            self.assertIn(fragment, run.outcomes[0].detail)

    def test_already_merged_at_approved_commit_counts_as_done(self):
        gh = FakeGitHub(target_routes(first=pull(state="closed", merged=True, merge_commit_sha="m" * 40)))
        run = executor(gh)
        self.assertEqual(run.run(), 0)
        self.assertEqual([o.status for o in run.outcomes], ["already-merged", "merged"])
        self.assertEqual([p for p, _ in gh.puts], [f"/repos/{OTHER}/pulls/3/merge"])

    def test_waits_for_github_to_compute_mergeability(self):
        routes = target_routes()
        routes[f"/repos/{TARGET}/pulls/7"] = [("first", pull(mergeable=None)), ("then", pull())]
        gh = FakeGitHub(routes)
        self.assertEqual(executor(gh).run(), 0)
        self.assertEqual(len(gh.puts), 2)

    def test_app_not_installed_is_refused(self):
        routes = target_routes()
        routes.update(installed(OTHER))
        run = executor(FakeGitHub(routes))
        self.assertEqual(run.run(), 1)
        self.assertIn("not installed", run.outcomes[0].detail)

    def test_dry_run_writes_nothing(self):
        gh = FakeGitHub(target_routes())
        run = executor(gh, dry_run=True)
        self.assertEqual(run.run(), 0)
        self.assertEqual((gh.puts, gh.posts), ([], []))
        self.assertEqual([o.status for o in run.outcomes], ["dry-run", "dry-run"])


class LedgerTests(unittest.TestCase):
    def test_result_is_recorded_on_the_ledger_branch(self):
        gh = FakeGitHub(target_routes())
        run = executor(gh)
        run.run()
        ledger = FakeGitHub({f"/repos/{LEDGER}/git/ref/heads/ring0/ledger": {"object": {"sha": "1" * 40}}})
        with tempfile.TemporaryDirectory() as tmp:
            om.save_result(ledger, run, NOW, False, Path(tmp))
            local = json.loads((Path(tmp) / "omnibus-result.json").read_text())
        path, body = ledger.puts[-1]
        self.assertEqual(path, f"/repos/{LEDGER}/contents/omnibus/wave-1.json")
        self.assertEqual(body["branch"], "ring0/ledger")
        self.assertEqual(local["entries"][f"{TARGET}#7"]["status"], "merged")
        self.assertEqual(local["approval"]["pull_request"], 90)

    def test_reused_id_is_refused_before_merging(self):
        previous = {"approval": {"pull_request": 42}}
        with self.assertRaisesRegex(om.OmnibusError, "never reused"):
            om.check_not_reused(previous, APPROVAL, "wave-1")

    def test_dry_run_records_locally_only(self):
        run = executor(FakeGitHub(target_routes()), dry_run=True)
        run.run()
        ledger = FakeGitHub({})
        with tempfile.TemporaryDirectory() as tmp:
            om.save_result(ledger, run, NOW, True, Path(tmp))
            self.assertTrue((Path(tmp) / "omnibus-result.json").exists())
        self.assertEqual(ledger.puts, [])


class CliTests(unittest.TestCase):
    def test_validate_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "wave-1.json"
            path.write_text(manifest_text())
            config = Path(__file__).resolve().parents[1] / "config" / "omnibus.json"
            self.assertEqual(om.main(["--config", str(config), "validate", str(path)]), 0)
            bad = Path(tmp) / "wave-2.json"
            bad.write_text(manifest_text())
            with self.assertRaisesRegex(om.OmnibusError, "must match the file name"):
                om.main(["--config", str(config), "validate", str(bad)])

    def test_plan_records_current_heads(self):
        gh = FakeGitHub({f"/repos/{TARGET}/pulls/7": pull(), f"/repos/{OTHER}/pulls/3": pull(3, HEAD_B, "main")})
        text = om.plan(gh, CONFIG, "wave-1", "Wave 1", [f"{TARGET}#7", f"{OTHER}#3"])
        entries = json.loads(text)["entries"]
        self.assertEqual([(e["pull_request"], e["head_sha"], e["base"]) for e in entries],
                         [(7, HEAD_A, "dev-daily"), (3, HEAD_B, "main")])


if __name__ == "__main__":
    unittest.main()
