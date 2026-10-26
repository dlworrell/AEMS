"""Exercise publication boundaries with a stateful GitHub API double; no network."""
import base64
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest
import urllib.parse

spec = importlib.util.spec_from_file_location("repair", Path(__file__).resolve().parents[1] / "scripts/publish_reviewed_repair.py")
repair = importlib.util.module_from_spec(spec)
spec.loader.exec_module(repair)
BASE, TREE, SIGNED, OTHER = (char * 40 for char in "abcd")
REPO, BRANCH = "dlworrell/AEMS", "signing/test-repair"
ENV = {"GITHUB_REPOSITORY": REPO, "GITHUB_EVENT_NAME": "push", "GITHUB_ACTOR": "dlworrell",
       "GITHUB_REF_NAME": "bootstrap/test-repair", "EXPECTED_BOOTSTRAP_BRANCH": "bootstrap/test-repair"}


def payload():
    content = b"reviewed content\n"
    return {"repository": REPO, "branch": BRANCH, "base_sha": BASE, "tree_sha": TREE,
            "message": {"headline": "fix: resume reviewed publication"},
            "file_changes": {"additions": [{"path": "docs/result.md",
                "contents": base64.b64encode(content).decode(),
                "blob_sha": hashlib.sha1(b"blob " + str(len(content)).encode() + b"\0" + content).hexdigest()}]}}


class GitHub:
    def __init__(self, head=None, current=BASE):
        self.refs = {"main": current}
        if head is not None:
            self.refs[BRANCH] = head
        self.calls = []
        self.record = {"sha": SIGNED, "commit": {"tree": {"sha": TREE},
            "verification": {"verified": True, "reason": "valid"}},
            "parents": [{"sha": BASE}], "committer": {"login": "web-flow"}}
        self.graphql_errors = None
        self.create_race = None
        self.advance_on_create = False
        self.move_on_verify = False
        self.unverified_reads = 0
        self.merged_prs = []

    @property
    def writes(self):
        return [call for call in self.calls if call[0] != "GET"]

    def __call__(self, method, path, body=None):
        self.calls.append((method, path, copy.deepcopy(body)))
        if method == "GET" and path == f"/repos/{REPO}":
            return {"default_branch": "main"}
        if method == "GET" and "/pulls?" in path:
            page = int(urllib.parse.parse_qs(path.split("?", 1)[1])["page"][0])
            return copy.deepcopy(self.merged_prs[(page - 1) * 100:page * 100])
        if method == "GET" and "/pulls/" in path:
            number = int(path.rsplit("/", 1)[1])
            return copy.deepcopy(next(pr for pr in self.merged_prs if pr["number"] == number))
        if method == "GET" and "/git/ref/heads/" in path:
            name = path.split("/git/ref/heads/", 1)[1]
            if name not in self.refs:
                raise repair.APIError(404, method, path)
            return {"ref": "refs/heads/" + name, "object": {"type": "commit", "sha": self.refs[name]}}
        if method == "POST" and path.endswith("/git/refs"):
            if self.create_race:
                self.refs[BRANCH] = self.create_race
                raise repair.APIError(422, method, path)
            if BRANCH in self.refs:
                raise repair.APIError(422, method, path)
            self.refs[BRANCH] = body["sha"]
            if self.advance_on_create:
                self.refs["main"] = OTHER
            return {"ref": body["ref"]}
        if method == "POST" and path == "/graphql":
            if self.graphql_errors:
                return {"errors": self.graphql_errors}
            if self.refs[BRANCH] != body["variables"]["input"]["expectedHeadOid"]:
                return {"errors": [{"type": "STALE_DATA", "message": "Branch head moved"}]}
            self.refs[BRANCH] = SIGNED
            return {"data": {"createCommitOnBranch": {"commit": {
                "oid": SIGNED, "url": f"https://github.com/{REPO}/commit/{SIGNED}"}}}}
        if method == "GET" and "/commits/" in path:
            value = copy.deepcopy(self.record)
            if self.unverified_reads:
                self.unverified_reads -= 1
                value["commit"]["verification"] = {"verified": False, "reason": "unsigned"}
            if self.move_on_verify:
                self.refs[BRANCH] = OTHER
            return value
        raise AssertionError(f"Unexpected API call: {method} {path}")


class ReviewedRepair(unittest.TestCase):
    def merged_pr(self):
        return {"number": 42, "merged": True, "merged_at": "2026-10-26T04:59:20Z",
                "head": {"ref": BRANCH, "sha": SIGNED, "repo": {"full_name": REPO}},
                "base": {"ref": "main", "repo": {"full_name": REPO}}}

    def run_repair(self, api, value=None, env=None, digest=None):
        raw = json.dumps(value if value is not None else payload()).encode()
        return repair.publish(raw, digest or hashlib.sha256(raw).hexdigest(), env or ENV,
                              api=api, sleep=lambda _: None)

    def test_new_publication_uses_reviewed_parent_and_excludes_blob_metadata(self):
        api = GitHub()
        result = self.run_repair(api)
        self.assertEqual(result["status"], "published")
        self.assertEqual([call[1] for call in api.writes], [f"/repos/{REPO}/git/refs", "/graphql"])
        mutation = api.writes[-1][2]["variables"]["input"]
        self.assertEqual(mutation["expectedHeadOid"], BASE)
        self.assertEqual(mutation["branch"]["branchName"], BRANCH)
        self.assertNotIn("blob_sha", mutation["fileChanges"]["additions"][0])
        self.assertEqual(api.refs["main"], BASE)

    def test_empty_branch_left_by_failed_commit_is_resumed(self):
        api = GitHub(head=BASE)
        self.assertEqual(self.run_repair(api)["status"], "published")
        self.assertEqual([call[1] for call in api.writes], ["/graphql"])

    def test_verified_complete_branch_is_read_only_even_after_default_advances(self):
        for current in (BASE, OTHER):
            with self.subTest(current=current):
                api = GitHub(head=SIGNED, current=current)
                result = self.run_repair(api)
                self.assertEqual(result["status"], "already_published")
                self.assertEqual(result["observed_default"], current)
                self.assertEqual(api.writes, [])

    def test_stale_missing_or_empty_branch_refuses_before_any_write(self):
        for head in (None, BASE):
            with self.subTest(head=head):
                api = GitHub(head=head, current=OTHER)
                with self.assertRaisesRegex(repair.RepairError, f"STALE_BASE: expected {BASE}; observed {OTHER}"):
                    self.run_repair(api)
                self.assertEqual(api.writes, [])

    def test_deleted_merged_branch_is_recovered_from_exact_signed_pr(self):
        api = GitHub(current=OTHER)
        api.merged_prs = [self.merged_pr()]
        result = self.run_repair(api)
        self.assertEqual(result["status"], "already_published")
        self.assertEqual(result["completion_source"], "merged_pull_request")
        self.assertEqual(result["pull_request"], 42)
        self.assertFalse(result["branch_present"])
        self.assertEqual(api.writes, [])

    def test_closed_unmerged_wrong_branch_base_or_repository_is_not_completion(self):
        for change in (lambda p: p.update(merged=False), lambda p: p.update(merged_at=None),
                       lambda p: p["head"].update(ref="signing/unrelated"),
                       lambda p: p["base"].update(ref="other"),
                       lambda p: p["head"]["repo"].update(full_name="other/AEMS")):
            api = GitHub(current=OTHER)
            pr = self.merged_pr()
            change(pr)
            api.merged_prs = [pr]
            with self.assertRaisesRegex(repair.RepairError, "STALE_BASE"):
                self.run_repair(api)
            self.assertEqual(api.writes, [])

    def test_merged_pr_does_not_hide_unsigned_or_altered_artifact(self):
        for change in (lambda c: c["commit"].update(verification={"verified": False, "reason": "unsigned"}),
                       lambda c: c["commit"].update(tree={"sha": OTHER}),
                       lambda c: c.update(parents=[{"sha": OTHER}])):
            api = GitHub(current=OTHER)
            api.merged_prs = [self.merged_pr()]
            change(api.record)
            with self.assertRaisesRegex(repair.RepairError, "STALE_BASE"):
                self.run_repair(api)
            self.assertEqual(api.writes, [])

    def test_branch_recreated_during_merged_pr_verification_is_refused(self):
        api = GitHub(current=OTHER)
        api.merged_prs = [self.merged_pr()]
        api.move_on_verify = True
        with self.assertRaisesRegex(repair.RepairError, "moved during verification"):
            self.run_repair(api)
        self.assertEqual(api.writes, [])

    def test_unavailable_merged_pr_evidence_never_becomes_success(self):
        api = GitHub(current=OTHER)
        def endpoint(method, path, body=None):
            if "/pulls?" in path:
                raise repair.APIError(403, method, path)
            return api(method, path, body)
        with self.assertRaises(repair.APIError):
            self.run_repair(endpoint)
        self.assertEqual(api.writes, [])

    def test_deleted_branch_lookup_follows_closed_pr_pagination(self):
        api = GitHub(current=OTHER)
        api.merged_prs = [{"number": 1000 + i, "merged_at": None} for i in range(100)] + [self.merged_pr()]
        self.assertEqual(self.run_repair(api)["status"], "already_published")
        self.assertEqual(sum("/pulls?" in call[1] for call in api.calls), 2)
        self.assertEqual(api.writes, [])

    def test_unsigned_or_inconsistent_completed_branch_never_passes(self):
        for evidence in ({"verified": False, "reason": "unsigned"},
                         {"verified": True, "reason": "unsigned"}, {}):
            with self.subTest(evidence=evidence):
                api = GitHub(head=SIGNED, current=OTHER)
                api.record["commit"]["verification"] = evidence
                with self.assertRaisesRegex(repair.RepairError, "did not verify"):
                    self.run_repair(api)
                self.assertEqual(api.writes, [])

    def test_wrong_commit_tree_parent_or_merge_ancestry_is_refused(self):
        for mutation in (lambda c: c.update(sha=OTHER),
                         lambda c: c["commit"].update(tree={"sha": OTHER}),
                         lambda c: c.update(parents=[{"sha": OTHER}]),
                         lambda c: c["parents"].append({"sha": OTHER})):
            api = GitHub(head=SIGNED)
            mutation(api.record)
            with self.assertRaisesRegex(repair.RepairError, "identity, tree or ancestry"):
                self.run_repair(api)
            self.assertEqual(api.writes, [])

    def test_default_branch_target_refused(self):
        value = payload()
        value["branch"] = "main"
        api = GitHub()
        with self.assertRaises(repair.RepairError):
            self.run_repair(api, value)
        self.assertEqual(api.calls, [])

    def test_default_named_like_signing_branch_still_refused(self):
        api = GitHub()
        def endpoint(method, path, body=None):
            if path == f"/repos/{REPO}":
                return {"default_branch": BRANCH}
            return api(method, path, body)
        with self.assertRaisesRegex(repair.RepairError, "Default branch writes forbidden"):
            self.run_repair(endpoint)
        self.assertEqual(api.writes, [])

    def test_default_advance_between_branch_creation_and_commit_is_detected(self):
        api = GitHub()
        api.advance_on_create = True
        with self.assertRaisesRegex(repair.RepairError, "STALE_BASE"):
            self.run_repair(api)
        self.assertEqual(len(api.writes), 1)
        self.assertTrue(api.writes[0][1].endswith("/git/refs"))
        self.assertEqual(api.refs["main"], OTHER)

    def test_concurrent_creator_is_rechecked_and_completed_commit_reused(self):
        api = GitHub()
        api.create_race = SIGNED
        self.assertEqual(self.run_repair(api)["status"], "already_published")
        self.assertEqual(len(api.writes), 1)

    def test_concurrent_empty_branch_can_be_resumed(self):
        api = GitHub()
        api.create_race = BASE
        self.assertEqual(self.run_repair(api)["status"], "published")

    def test_graphql_head_lease_failure_keeps_diagnostic_and_does_not_retry(self):
        api = GitHub(head=BASE)
        api.graphql_errors = [{"type": "STALE_DATA", "message": "Branch head moved"}]
        with self.assertRaisesRegex(repair.RepairError, "STALE_DATA.*Branch head moved"):
            self.run_repair(api)
        self.assertEqual(len(api.writes), 1)
        self.assertEqual(api.refs[BRANCH], BASE)

    def test_branch_moved_while_signature_was_checked_is_refused(self):
        api = GitHub(head=SIGNED)
        api.move_on_verify = True
        with self.assertRaisesRegex(repair.RepairError, "moved during verification"):
            self.run_repair(api)
        self.assertEqual(api.writes, [])

    def test_signature_verification_can_settle_within_bounded_retry(self):
        api = GitHub(head=SIGNED)
        api.unverified_reads = 3
        self.assertTrue(self.run_repair(api)["verified"])
        self.assertEqual(sum("/commits/" in call[1] for call in api.calls), 4)

    def test_payload_digest_is_checked_before_api(self):
        api = GitHub()
        with self.assertRaisesRegex(repair.RepairError, "Payload identity mismatch"):
            self.run_repair(api, digest="0" * 64)
        self.assertEqual(api.calls, [])

    def test_file_blob_tampering_refused_before_api(self):
        value = payload()
        value["file_changes"]["additions"][0]["blob_sha"] = OTHER
        api = GitHub()
        with self.assertRaisesRegex(repair.RepairError, "file hash mismatch"):
            self.run_repair(api, value)
        self.assertEqual(api.calls, [])

    def test_unsafe_and_duplicate_paths_are_refused_before_api(self):
        for path in ("/etc/passwd", "../file", "docs/../file", "docs//file", ".git/config", "docs/./file", "docs\\file", "bad\0file", ""):
            with self.subTest(path=path):
                value = payload()
                value["file_changes"]["additions"][0]["path"] = path
                api = GitHub()
                with self.assertRaises(repair.RepairError):
                    self.run_repair(api, value)
                self.assertEqual(api.calls, [])
        value = payload()
        value["file_changes"]["deletions"] = [{"path": "docs/result.md"}]
        with self.assertRaisesRegex(repair.RepairError, "duplicate"):
            self.run_repair(GitHub(), value)

    def test_untrusted_events_actor_repository_and_branch_are_refused_before_api(self):
        changes = [{"GITHUB_EVENT_NAME": "pull_request_target"}, {"GITHUB_ACTOR": "other"},
                   {"GITHUB_TRIGGERING_ACTOR": "other"}, {"GITHUB_REF_NAME": "main"},
                   {"GITHUB_REPOSITORY": "other/AEMS"}, {"EXPECTED_BOOTSTRAP_BRANCH": ""}]
        for change in changes:
            with self.subTest(change=change):
                api = GitHub()
                with self.assertRaises(repair.RepairError):
                    self.run_repair(api, env={**ENV, **change})
                self.assertEqual(api.calls, [])

    def test_owner_dispatch_on_expected_bootstrap_branch_is_supported(self):
        result = self.run_repair(GitHub(), env={**ENV, "GITHUB_EVENT_NAME": "workflow_dispatch"})
        self.assertEqual(result["status"], "published")

    def test_unsafe_ref_and_unknown_change_operation_are_refused(self):
        for branch in ("signing/../main", "signing/a.lock", "signing/a//b", "signing/.hidden", "signing/a."):
            value = payload()
            value["branch"] = branch
            with self.assertRaisesRegex(repair.RepairError, "Unsafe repair branch"):
                self.run_repair(GitHub(), value)
        value = payload()
        value["file_changes"]["renames"] = []
        with self.assertRaisesRegex(repair.RepairError, "Unknown file-change"):
            self.run_repair(GitHub(), value)

    def test_read_permission_error_is_not_treated_as_missing_branch(self):
        api = GitHub()
        def endpoint(method, path, body=None):
            if "/git/ref/heads/" in path:
                raise repair.APIError(403, method, path)
            return api(method, path, body)
        with self.assertRaises(repair.APIError) as context:
            self.run_repair(endpoint)
        self.assertEqual(context.exception.status, 403)
        self.assertEqual(api.writes, [])

    def test_deletions_are_forwarded_without_addition_metadata(self):
        value = payload()
        value["file_changes"]["deletions"] = [{"path": "docs/obsolete.md"}]
        api = GitHub()
        self.assertEqual(self.run_repair(api, value)["files"], 2)
        self.assertEqual(api.writes[-1][2]["variables"]["input"]["fileChanges"]["deletions"],
                         [{"path": "docs/obsolete.md"}])


if __name__ == "__main__":
    unittest.main()
