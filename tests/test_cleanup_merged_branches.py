from __future__ import annotations

import copy
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
import urllib.error

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import cleanup_merged_branches as cmb


REPO = "dlworrell/AEMS"
SHA = "0123456789abcdef0123456789abcdef01234567"


def sha(n: int) -> str:
    return f"{n:040x}"


def branch(name: str, tip: str, protected: bool = False) -> dict:
    return {"name": name, "commit": {"sha": tip}, "protected": protected}


def pull(
    number: int,
    head_ref: str,
    head_sha: str,
    *,
    state: str = "closed",
    merged: bool = False,
    base_ref: str = "main",
    head_repo: str | None = REPO,
) -> dict:
    return {
        "number": number,
        "state": state,
        "merged_at": "2026-01-01T00:00:00Z" if merged else None,
        "head": {
            "ref": head_ref,
            "sha": head_sha,
            "repo": {"full_name": head_repo} if head_repo else None,
        },
        "base": {"ref": base_ref, "repo": {"full_name": REPO}},
    }


def inventory() -> dict:
    return {
        "schema": "catylist.repository-inventory.v1",
        "repositories": [
            {"full_name": "dlworrell/AEMS", "default_branch_policy": "protected"},
            {"full_name": "dlworrell/JAG", "default_branch_policy": "protected"},
            {"full_name": "dlworrell/CLK", "default_branch_policy": "excluded"},
        ],
    }


class FakeClient:
    """In-memory stand-in for GitHubClient for a single repository."""

    def __init__(
        self,
        branches: list[dict],
        pulls: list[dict],
        ahead: dict[str, int] | None = None,
        *,
        default_branch: str = "main",
        delete_errors: dict[str, cmb.GitHubError] | None = None,
    ) -> None:
        self.branches = {item["name"]: copy.deepcopy(item) for item in branches}
        self.pulls = pulls
        self.ahead = ahead or {}
        self.default_branch = default_branch
        self.delete_errors = delete_errors or {}
        self.calls: list[tuple[str, str]] = []

    def request(self, method: str, path: str, body=None):
        self.calls.append((method, path))
        if method == "GET" and path == f"/repos/{REPO}":
            return {"default_branch": self.default_branch, "archived": False}
        if method == "GET" and "/compare/" in path:
            tip = path.rsplit("...", 1)[1]
            return {"ahead_by": self.ahead[tip]}
        prefix_get = f"/repos/{REPO}/git/ref/heads/"
        if method == "GET" and path.startswith(prefix_get):
            name = cmb.urllib.parse.unquote(path[len(prefix_get):])
            if name not in self.branches:
                raise cmb.GitHubError(404, "Not Found", "Not Found")
            return {"object": {"sha": self.branches[name]["commit"]["sha"]}}
        prefix_del = f"/repos/{REPO}/git/refs/heads/"
        if method == "DELETE" and path.startswith(prefix_del):
            name = cmb.urllib.parse.unquote(path[len(prefix_del):])
            if name in self.delete_errors:
                raise self.delete_errors[name]
            self.branches.pop(name, None)
            return None
        raise AssertionError(f"unexpected request {method} {path}")

    def list_all(self, path: str) -> list[dict]:
        self.calls.append(("GET", path))
        if path.startswith(f"/repos/{REPO}/branches"):
            return copy.deepcopy(list(self.branches.values()))
        if path.startswith(f"/repos/{REPO}/pulls"):
            return copy.deepcopy(self.pulls)
        raise AssertionError(f"unexpected list {path}")

    def writes(self) -> list[tuple[str, str]]:
        return [call for call in self.calls if call[0] != "GET"]


def run(client: FakeClient, *, apply: bool, keep: str = "") -> dict:
    return cmb.process_repository(
        client, REPO, cmb.parse_keep_patterns(keep), apply=apply
    )


def decisions(result: dict) -> dict[str, dict]:
    return {item["branch"]: item for item in result["delete"] + result["keep"]}


class ClassificationTests(unittest.TestCase):
    def test_default_and_protected_never_deleted(self) -> None:
        client = FakeClient(
            [branch("main", sha(1), protected=True), branch("release", sha(2), True),
             branch("unprot-default", sha(3))],
            [pull(1, "release", sha(2), merged=True)],
            {sha(1): 0, sha(2): 0, sha(3): 0},
            default_branch="unprot-default",
        )
        result = decisions(run(client, apply=False))
        self.assertEqual(result["unprot-default"]["reason"], cmb.REASON_DEFAULT)
        self.assertEqual(result["main"]["reason"], cmb.REASON_PROTECTED)
        self.assertEqual(result["release"]["reason"], cmb.REASON_PROTECTED)
        self.assertTrue(all(d["action"] == "keep" for d in result.values()))

    def test_missing_protected_flag_is_treated_as_protected(self) -> None:
        item = {"name": "x", "commit": {"sha": sha(5)}}
        client = FakeClient([item], [], {sha(5): 0})
        self.assertEqual(
            decisions(run(client, apply=False))["x"]["reason"], cmb.REASON_PROTECTED
        )

    def test_open_pr_head_and_base_kept(self) -> None:
        client = FakeClient(
            [branch("main", sha(1), True), branch("feature", sha(2)),
             branch("integration", sha(3))],
            [
                pull(7, "feature", sha(2), state="open", base_ref="integration"),
                pull(3, "feature", sha(2), merged=True),
            ],
            {sha(2): 0, sha(3): 0},
        )
        result = decisions(run(client, apply=False))
        self.assertEqual(result["feature"]["reason"], cmb.REASON_OPEN_PR_HEAD)
        self.assertEqual(result["integration"]["reason"], cmb.REASON_OPEN_PR_BASE)
        self.assertIn("#7", result["integration"]["detail"])

    def test_open_fork_pr_head_does_not_protect_same_named_branch(self) -> None:
        client = FakeClient(
            [branch("main", sha(1), True), branch("patch-1", sha(2))],
            [pull(9, "patch-1", sha(9), state="open", head_repo="someone/AEMS")],
            {sha(2): 0},
        )
        result = decisions(run(client, apply=False))
        self.assertEqual(result["patch-1"]["reason"], cmb.REASON_CONTAINED)

    def test_backup_and_keep_patterns_kept(self) -> None:
        client = FakeClient(
            [branch("main", sha(1), True), branch("backup/old", sha(2)),
             branch("archive/2025", sha(3)), branch("wip-x", sha(4))],
            [pull(1, "backup/old", sha(2), merged=True)],
            {sha(2): 0, sha(3): 0, sha(4): 0},
        )
        result = decisions(run(client, apply=False, keep="archive/*, wip-*"))
        self.assertEqual(result["backup/old"]["reason"], cmb.REASON_KEEP_PATTERN)
        self.assertEqual(result["archive/2025"]["reason"], cmb.REASON_KEEP_PATTERN)
        self.assertEqual(result["wip-x"]["pattern"], "wip-*")

    def test_merged_pr_with_matching_tip_deleted_without_compare(self) -> None:
        client = FakeClient(
            [branch("main", sha(1), True), branch("feat", sha(2))],
            [pull(4, "feat", sha(2), merged=True)],
        )
        result = decisions(run(client, apply=False))
        self.assertEqual(result["feat"]["action"], "delete")
        self.assertEqual(result["feat"]["reason"], cmb.REASON_MERGED_PR)
        self.assertEqual(result["feat"]["pull"], 4)
        self.assertFalse(any("/compare/" in path for _, path in client.calls))

    def test_merged_pr_with_commits_after_merge_kept(self) -> None:
        client = FakeClient(
            [branch("main", sha(1), True), branch("feat", sha(3))],
            [pull(4, "feat", sha(2), merged=True)],
            {sha(3): 2},
        )
        result = decisions(run(client, apply=False))
        self.assertEqual(result["feat"]["action"], "keep")
        self.assertEqual(result["feat"]["reason"], cmb.REASON_COMMITS_AFTER_MERGE)

    def test_merged_pr_with_later_commits_contained_is_deleted(self) -> None:
        client = FakeClient(
            [branch("main", sha(1), True), branch("feat", sha(3))],
            [pull(4, "feat", sha(2), merged=True)],
            {sha(3): 0},
        )
        result = decisions(run(client, apply=False))
        self.assertEqual(result["feat"]["reason"], cmb.REASON_CONTAINED)

    def test_closed_unmerged_kept_unless_contained(self) -> None:
        client = FakeClient(
            [branch("main", sha(1), True), branch("abandoned", sha(2)),
             branch("superseded", sha(3))],
            [pull(5, "abandoned", sha(2)), pull(6, "superseded", sha(3))],
            {sha(2): 4, sha(3): 0},
        )
        result = decisions(run(client, apply=False))
        self.assertEqual(result["abandoned"]["reason"], cmb.REASON_CLOSED_UNMERGED)
        self.assertEqual(result["abandoned"]["action"], "keep")
        self.assertEqual(result["superseded"]["reason"], cmb.REASON_CONTAINED)
        self.assertEqual(result["superseded"]["action"], "delete")

    def test_no_pr_branch_contained_deleted_and_with_commits_kept(self) -> None:
        client = FakeClient(
            [branch("main", sha(1), True), branch("old", sha(2)),
             branch("local-work", sha(3))],
            [],
            {sha(2): 0, sha(3): 1},
        )
        result = decisions(run(client, apply=False))
        self.assertEqual(result["old"]["action"], "delete")
        self.assertEqual(result["old"]["reason"], cmb.REASON_CONTAINED)
        self.assertEqual(result["local-work"]["action"], "keep")
        self.assertEqual(result["local-work"]["reason"], cmb.REASON_UNMERGED_COMMITS)

    def test_compare_uses_classified_tip_sha(self) -> None:
        client = FakeClient(
            [branch("main", sha(1), True), branch("a/b", sha(2))], [], {sha(2): 0}
        )
        run(client, apply=False)
        self.assertIn(
            ("GET", f"/repos/{REPO}/compare/main...{sha(2)}"), client.calls
        )

    def test_invalid_ahead_by_is_an_error(self) -> None:
        client = FakeClient([branch("main", sha(1), True), branch("x", sha(2))], [])
        client.ahead = {sha(2): None}  # type: ignore[dict-item]
        result = run(client, apply=False)
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["delete"], [])


class ApplyTests(unittest.TestCase):
    def fixture(self, **kwargs) -> FakeClient:
        return FakeClient(
            [branch("main", sha(1), True), branch("feat", sha(2)),
             branch("old", sha(3)), branch("keep-me", sha(4))],
            [pull(4, "feat", sha(2), merged=True)],
            {sha(3): 0, sha(4): 2},
            **kwargs,
        )

    def test_dry_run_performs_no_delete(self) -> None:
        client = self.fixture()
        result = run(client, apply=False)
        self.assertEqual(result["status"], "planned")
        self.assertEqual(client.writes(), [])
        self.assertEqual(
            sorted(d["branch"] for d in result["delete"]), ["feat", "old"]
        )
        self.assertIn("feat", client.branches)

    def test_apply_deletes_and_relists(self) -> None:
        client = self.fixture()
        result = run(client, apply=True)
        self.assertEqual(result["status"], "cleaned", result["error"])
        self.assertEqual(
            sorted(path for method, path in client.writes()),
            [f"/repos/{REPO}/git/refs/heads/feat", f"/repos/{REPO}/git/refs/heads/old"],
        )
        self.assertEqual(result["remaining_branches"], ["keep-me", "main"])

    def test_branch_names_are_url_encoded(self) -> None:
        client = FakeClient(
            [branch("main", sha(1), True), branch("claude/x#1", sha(2))],
            [pull(4, "claude/x#1", sha(2), merged=True)],
        )
        run(client, apply=True)
        self.assertIn(
            ("DELETE", f"/repos/{REPO}/git/refs/heads/claude%2Fx%231"), client.calls
        )

    def test_already_deleted_ref_tolerated(self) -> None:
        client = self.fixture()

        class GoneDuringRun(FakeClient):
            def request(self, method: str, path: str, body=None):
                if method == "GET" and path.endswith("/git/ref/heads/old"):
                    # Deleted by someone else after planning.
                    self.branches.pop("old", None)
                if method == "DELETE" and path.endswith("/heads/feat"):
                    self.calls.append((method, path))
                    self.branches.pop("feat", None)
                    raise cmb.GitHubError(
                        422, "DELETE ...: Reference does not exist",
                        "Reference does not exist",
                    )
                return super().request(method, path, body)

        client.__class__ = GoneDuringRun
        result = run(client, apply=True)
        outcomes = {item["branch"]: item["result"] for item in result["deletions"]}
        self.assertEqual(outcomes, {"feat": "already-gone", "old": "already-gone"})
        self.assertEqual(result["status"], "cleaned", result["error"])

    def test_other_delete_failure_marks_repo_error_but_continues(self) -> None:
        denied = cmb.GitHubError(403, "DELETE ...: Resource not accessible",
                                 "Resource not accessible")
        client = self.fixture(delete_errors={"feat": denied})
        result = run(client, apply=True)
        outcomes = {item["branch"]: item["result"] for item in result["deletions"]}
        self.assertEqual(outcomes, {"feat": "failed", "old": "deleted"})
        self.assertEqual(result["status"], "error")
        self.assertIn("feat", result["error"])

    def test_tip_moved_after_planning_is_not_deleted(self) -> None:
        client = self.fixture()
        original_list = client.list_all

        def list_all(path: str) -> list[dict]:
            items = original_list(path)
            if path.startswith(f"/repos/{REPO}/branches"):
                client.branches["feat"]["commit"]["sha"] = sha(99)
            return items

        client.list_all = list_all  # type: ignore[method-assign]
        result = run(client, apply=True)
        outcomes = {item["branch"]: item["result"] for item in result["deletions"]}
        self.assertEqual(outcomes["feat"], "skipped-tip-changed")
        self.assertNotIn(("DELETE", f"/repos/{REPO}/git/refs/heads/feat"),
                         client.calls)
        self.assertEqual(result["status"], "error")


class InputTests(unittest.TestCase):
    def test_sha_validation(self) -> None:
        self.assertEqual(cmb.validate_sha(SHA.upper(), "ref"), SHA)
        for bad in ("main", SHA[:39], SHA + "0", "g" * 40, "", None):
            with self.assertRaises(cmb.PlanError):
                cmb.validate_sha(bad, "catylist_ref")  # type: ignore[arg-type]

    def test_main_rejects_bad_sha_before_any_request(self) -> None:
        with mock.patch.object(cmb.GitHubClient, "_open") as opened, \
                mock.patch("sys.stderr", new_callable=io.StringIO):
            self.assertEqual(cmb.main(["--catylist-ref", "main"]), 2)
        opened.assert_not_called()

    def test_selection_and_unknown_repo_fails(self) -> None:
        selected, skipped = cmb.select_repositories(inventory(), [])
        self.assertEqual(selected, ["dlworrell/AEMS", "dlworrell/JAG"])
        selected, skipped = cmb.select_repositories(
            inventory(), ["dlworrell/ruleset-sandbox", "dlworrell/clk"]
        )
        self.assertEqual(selected, ["dlworrell/ruleset-sandbox"])
        self.assertEqual(skipped[0]["repository"], "dlworrell/CLK")
        with self.assertRaises(cmb.PlanError):
            cmb.select_repositories(inventory(), ["dlworrell/nope"])
        with self.assertRaises(cmb.PlanError):
            cmb.parse_repos_filter("not a repo")

    def test_sandbox_not_selected_without_filter(self) -> None:
        selected, _ = cmb.select_repositories(inventory(), [])
        self.assertNotIn(cmb.SANDBOX_REPOSITORY, selected)

    def test_keep_patterns_always_include_backup(self) -> None:
        self.assertEqual(cmb.parse_keep_patterns(""), ["backup/*", "dev-daily", "fitment"])
        self.assertEqual(
            cmb.parse_keep_patterns(" release/*, ,backup/*"),
            ["backup/*", "dev-daily", "fitment", "release/*"],
        )


class ClientTests(unittest.TestCase):
    TOKEN = "github_pat_SECRET123"

    def test_token_never_appears_in_error_text(self) -> None:
        body = io.BytesIO(
            ('{"message": "bad credentials ' + self.TOKEN + '"}').encode()
        )
        error = urllib.error.HTTPError(
            "https://api.github.com/x", 401, "Unauthorized " + self.TOKEN, {}, body
        )
        client = cmb.GitHubClient(self.TOKEN)
        with mock.patch("urllib.request.urlopen", side_effect=error):
            with self.assertRaises(cmb.GitHubError) as caught:
                client.request("GET", "/repos/dlworrell/AEMS")
        self.assertNotIn(self.TOKEN, str(caught.exception))
        self.assertNotIn(self.TOKEN, caught.exception.detail)

        url_error = urllib.error.URLError("proxy said " + self.TOKEN)
        with mock.patch("urllib.request.urlopen", side_effect=url_error):
            with self.assertRaises(cmb.GitHubError) as caught:
                client.request("GET", "/repos/dlworrell/AEMS")
        self.assertNotIn(self.TOKEN, str(caught.exception))

    def test_refuses_pagination_outside_api(self) -> None:
        class Response:
            headers = {"Link": '<https://evil.example/next>; rel="next"'}

            def read(self) -> bytes:
                return b"[]"

            def __enter__(self):
                return self

            def __exit__(self, *args) -> None:
                return None

        client = cmb.GitHubClient(self.TOKEN)
        with mock.patch("urllib.request.urlopen", return_value=Response()) as opened:
            with self.assertRaises(cmb.GitHubError):
                client.list_all("/repos/dlworrell/AEMS/branches?per_page=100")
        self.assertEqual(opened.call_count, 1)

    def test_sends_api_version_header(self) -> None:
        class Response:
            headers: dict = {}

            def read(self) -> bytes:
                return b"{}"

            def __enter__(self):
                return self

            def __exit__(self, *args) -> None:
                return None

        client = cmb.GitHubClient(self.TOKEN)
        with mock.patch("urllib.request.urlopen", return_value=Response()) as opened:
            client.request("GET", "/repos/dlworrell/AEMS")
        request = opened.call_args.args[0]
        self.assertEqual(request.get_header("X-github-api-version"), "2022-11-28")


class ReportTests(unittest.TestCase):
    def test_report_schema_and_markdown(self) -> None:
        client = FakeClient(
            [branch("main", sha(1), True), branch("feat", sha(2)),
             branch("wip", sha(3))],
            [pull(4, "feat", sha(2), merged=True)],
            {sha(3): 1},
        )
        result = run(client, apply=False)
        report = cmb.build_report(
            mode="dry-run", catylist_ref=SHA, repos_filter=[],
            keep_patterns=["backup/*"], skipped=[], results=[result],
        )
        self.assertEqual(report["schema"], "aems.branch-cleanup-report.v1")
        self.assertEqual(report["summary"]["branches"]["delete"], 1)
        markdown = cmb.render_markdown(report)
        self.assertIn("Would delete (1)", markdown)
        self.assertIn("merged PR #4", markdown)
        self.assertIn("no pull request", markdown)

    def test_main_writes_reports_in_dry_run(self) -> None:
        client = FakeClient(
            [branch("main", sha(1), True), branch("feat", sha(2))],
            [pull(4, "feat", sha(2), merged=True)],
        )
        source = mock.Mock()
        source.get_file.return_value = inventory()
        clients = iter([source, client])
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.dict("os.environ", {"BRANCH_CLEANUP_TOKEN": "t"}), \
                mock.patch.object(cmb, "GitHubClient",
                                  side_effect=lambda *a, **k: next(clients)), \
                mock.patch("sys.stdout", new_callable=io.StringIO):
            code = cmb.main([
                "--catylist-ref", SHA, "--repos", REPO, "--output-dir", tmp,
            ])
            self.assertEqual(code, 0)
            self.assertTrue((Path(tmp) / "report.json").exists())
            self.assertTrue((Path(tmp) / "report.md").exists())
        self.assertEqual(client.writes(), [])


if __name__ == "__main__":
    unittest.main()
