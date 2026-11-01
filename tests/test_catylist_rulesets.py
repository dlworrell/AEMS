from __future__ import annotations

import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import catylist_rulesets as cr


BRANCH_RULESET = {
    "name": "protect-default-branch",
    "target": "branch",
    "enforcement": "active",
    "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
    "bypass_actors": [],
    "rules": [
        {"type": "deletion"},
        {"type": "non_fast_forward"},
        {"type": "required_signatures"},
        {
            "type": "pull_request",
            "parameters": {
                "required_approving_review_count": 0,
                "dismiss_stale_reviews_on_push": False,
                "require_code_owner_review": False,
                "require_last_push_approval": False,
                "required_review_thread_resolution": False,
                "allowed_merge_methods": ["merge"],
            },
        },
    ],
}

TAG_RULESET = {
    "name": "protect-release-tags",
    "target": "tag",
    "enforcement": "active",
    "conditions": {"ref_name": {"include": ["refs/tags/v*"], "exclude": []}},
    "bypass_actors": [],
    "rules": [
        {"type": "deletion"},
        {"type": "non_fast_forward"},
        {"type": "update"},
    ],
}

COMPLIANT_SETTINGS = {
    "allow_merge_commit": True,
    "allow_squash_merge": False,
    "allow_rebase_merge": False,
    "delete_branch_on_merge": True,
}

SHA = "0123456789abcdef0123456789abcdef01234567"


def desired() -> list[dict]:
    return [
        cr.validate_desired_ruleset(
            BRANCH_RULESET,
            expected_name="protect-default-branch",
            expected_target="branch",
        ),
        cr.validate_desired_ruleset(
            TAG_RULESET,
            expected_name="protect-release-tags",
            expected_target="tag",
        ),
    ]


def as_current(ruleset: dict, ruleset_id: int) -> dict:
    """Shape a ruleset the way GET /repos/{repo}/rulesets/{id} returns it."""

    current = copy.deepcopy(ruleset)
    current.update(
        {
            "id": ruleset_id,
            "source_type": "Repository",
            "source": "example/repo",
            "current_user_can_bypass": "never",
        }
    )
    for rule in current["rules"]:
        if rule["type"] == "pull_request":
            # The API reports parameters the baseline does not declare.
            rule["parameters"]["required_reviewers"] = []
            rule["parameters"]["allowed_merge_methods"] = ["merge"]
    return current


def inventory() -> dict:
    return {
        "schema": "catylist.repository-inventory.v1",
        "repositories": [
            {"full_name": "dlworrell/AEMS", "default_branch_policy": "protected"},
            {"full_name": "dlworrell/JAG", "default_branch_policy": "protected"},
            {"full_name": "dlworrell/CLK", "default_branch_policy": "excluded"},
            {
                "full_name": "dlworrell/rea",
                "default_branch_policy": "pending-classification",
            },
        ],
    }


OWNER_ID = 1865560
COMPLIANT_ENVIRONMENT = {
    "name": "release", "can_admins_bypass": False,
    "deployment_branch_policy": {"protected_branches": False, "custom_branch_policies": True},
    "protection_rules": [{"type": "required_reviewers", "prevent_self_review": False,
                          "reviewers": [{"type": "User", "reviewer": {"id": OWNER_ID, "login": "example"}}]}],
}


class FakeClient:
    def __init__(self, rulesets: list[dict], settings: dict, *, branches=("dev-daily", "fitment"),
                 environment=COMPLIANT_ENVIRONMENT, policies=(("main", "branch"),)) -> None:
        self.rulesets = {item["id"]: copy.deepcopy(item) for item in rulesets}
        self.settings = dict(settings)
        self.writes: list[tuple[str, str]] = []
        self.bodies: list[tuple[str, str, object]] = []
        self.next_id = 100
        self.branches = {name: "b" * 40 for name in branches}
        self.environment = copy.deepcopy(environment)
        self.policies = [{"name": n, "type": k} for n, k in policies]

    def list_rulesets(self, repository: str) -> list[dict]:
        return [
            {"id": item["id"], "name": item["name"], "source_type": "Repository"}
            for item in self.rulesets.values()
        ]

    def request(self, method: str, path: str, body=None):
        if method == "GET":
            if "/rulesets/" in path:
                return copy.deepcopy(self.rulesets[int(path.rsplit("/", 1)[1])])
            if path.startswith("/users/"):
                return {"id": OWNER_ID}
            if "/branches/" in path:
                name = path.rsplit("/", 1)[1]
                if name not in self.branches:
                    raise cr.GitHubError(404, "Branch not found")
                return {"commit": {"sha": self.branches[name]}}
            if path.endswith("/environments/release"):
                if self.environment is None:
                    raise cr.GitHubError(404, "Not Found")
                return copy.deepcopy(self.environment)
            if "/deployment-branch-policies" in path:
                return {"branch_policies": copy.deepcopy(self.policies)}
            if "/git/ref/heads/" in path:
                name = path.rsplit("/heads/", 1)[1]
                if name == "main":
                    return {"object": {"sha": "a" * 40}}
                if name not in self.branches:
                    raise cr.GitHubError(404, "Not Found")
                return {"object": {"sha": self.branches[name]}}
            return dict(self.settings, archived=False, default_branch="main")
        self.writes.append((method, path))
        self.bodies.append((method, path, copy.deepcopy(body)))
        if path.endswith("/git/refs"):
            self.branches[body["ref"].removeprefix("refs/heads/")] = body["sha"]
        elif path.endswith("/environments/release"):
            self.environment = {
                "name": "release", "can_admins_bypass": True,
                "deployment_branch_policy": body["deployment_branch_policy"],
                "protection_rules": [{"type": "required_reviewers", "prevent_self_review": body["prevent_self_review"],
                                      "reviewers": [{"type": r["type"], "reviewer": {"id": r["id"]}}
                                                    for r in body["reviewers"]]}]}
        elif path.endswith("/deployment-branch-policies"):
            self.policies.append(dict(body))
        elif method == "POST":
            self.next_id += 1
            self.rulesets[self.next_id] = dict(copy.deepcopy(body), id=self.next_id)
        elif method == "PUT":
            ruleset_id = int(path.rsplit("/", 1)[1])
            self.rulesets[ruleset_id] = dict(copy.deepcopy(body), id=ruleset_id)
        elif method == "PATCH":
            self.settings.update(body)
        return {}


class ShaValidationTests(unittest.TestCase):
    def test_accepts_full_sha_and_normalizes_case(self) -> None:
        self.assertEqual(cr.validate_sha(SHA.upper(), "ref"), SHA)

    def test_rejects_branch_short_sha_and_injection(self) -> None:
        for value in ("main", SHA[:7], SHA + "0", "", SHA[:-1] + "g",
                      f"{SHA[:39]};"):
            with self.subTest(value=value):
                with self.assertRaises(cr.PlanError):
                    cr.validate_sha(value, "ref")


class SelectionTests(unittest.TestCase):
    def test_only_protected_entries_are_selected(self) -> None:
        selected, skipped = cr.select_repositories(inventory(), [])
        self.assertEqual(selected, ["dlworrell/AEMS", "dlworrell/JAG"])
        self.assertEqual(skipped, [])

    def test_repos_filter_intersects_and_reports_policy_skips(self) -> None:
        names = cr.parse_repos_filter(" dlworrell/jag , dlworrell/CLK,,dlworrell/rea")
        selected, skipped = cr.select_repositories(inventory(), names)
        self.assertEqual(selected, ["dlworrell/JAG"])
        self.assertEqual(
            [item["repository"] for item in skipped],
            ["dlworrell/CLK", "dlworrell/rea"],
        )

    def test_unknown_filter_name_is_rejected(self) -> None:
        with self.assertRaises(cr.PlanError):
            cr.select_repositories(inventory(), ["dlworrell/not-there"])

    def test_sandbox_may_be_selected_explicitly(self) -> None:
        selected, _ = cr.select_repositories(
            inventory(), ["dlworrell/ruleset-sandbox"]
        )
        self.assertEqual(selected, ["dlworrell/ruleset-sandbox"])

    def test_invalid_filter_and_inventory_are_rejected(self) -> None:
        with self.assertRaises(cr.PlanError):
            cr.parse_repos_filter("dlworrell/AEMS;rm -rf")
        bad = inventory()
        bad["repositories"][0]["default_branch_policy"] = "maybe"
        with self.assertRaises(cr.PlanError):
            cr.select_repositories(bad, [])
        bad = inventory()
        bad["schema"] = "other"
        with self.assertRaises(cr.PlanError):
            cr.select_repositories(bad, [])


class DesiredRulesetTests(unittest.TestCase):
    def test_rejects_required_linear_history(self) -> None:
        ruleset = copy.deepcopy(BRANCH_RULESET)
        ruleset["rules"].append({"type": "required_linear_history"})
        with self.assertRaises(cr.PlanError):
            cr.validate_desired_ruleset(
                ruleset,
                expected_name="protect-default-branch",
                expected_target="branch",
            )

    def test_rejects_status_checks_bypass_and_wrong_name(self) -> None:
        cases = []
        ruleset = copy.deepcopy(BRANCH_RULESET)
        ruleset["rules"].append({"type": "required_status_checks"})
        cases.append(ruleset)
        ruleset = copy.deepcopy(BRANCH_RULESET)
        ruleset["bypass_actors"] = [
            {"actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "always"}
        ]
        cases.append(ruleset)
        ruleset = copy.deepcopy(BRANCH_RULESET)
        ruleset["name"] = "other"
        cases.append(ruleset)
        for ruleset in cases:
            with self.subTest(ruleset=ruleset["name"]):
                with self.assertRaises(cr.PlanError):
                    cr.validate_desired_ruleset(
                        ruleset,
                        expected_name="protect-default-branch",
                        expected_target="branch",
                    )


class DriftTests(unittest.TestCase):
    def plan(self, rulesets: list[dict], settings: dict) -> dict:
        return cr.plan_repository("example/repo", desired(), rulesets, settings)

    def test_matching_state_has_no_changes(self) -> None:
        plan = self.plan(
            [as_current(BRANCH_RULESET, 1), as_current(TAG_RULESET, 2)],
            COMPLIANT_SETTINGS,
        )
        self.assertFalse(cr.plan_has_changes(plan))
        self.assertEqual([item["action"] for item in plan["rulesets"]], ["none", "none"])

    def test_missing_ruleset_is_created(self) -> None:
        plan = self.plan([as_current(TAG_RULESET, 2)], COMPLIANT_SETTINGS)
        branch = plan["rulesets"][0]
        self.assertEqual(branch["action"], "create")
        self.assertEqual(branch["drift"][0]["current"], "missing")
        self.assertEqual(branch["payload"]["name"], "protect-default-branch")

    def test_differing_rules_are_updated(self) -> None:
        current = as_current(BRANCH_RULESET, 1)
        current["rules"] = [r for r in current["rules"] if r["type"] != "required_signatures"]
        current["rules"].append({"type": "required_linear_history"})
        for rule in current["rules"]:
            if rule["type"] == "pull_request":
                rule["parameters"]["allowed_merge_methods"] = ["merge", "squash"]
        plan = self.plan([current, as_current(TAG_RULESET, 2)], COMPLIANT_SETTINGS)
        branch = plan["rulesets"][0]
        self.assertEqual(branch["action"], "update")
        self.assertEqual(branch["ruleset_id"], 1)
        fields = {item["field"] for item in branch["drift"]}
        self.assertEqual(
            fields,
            {
                "rules.required_signatures",
                "rules.required_linear_history",
                "rules.pull_request.parameters.allowed_merge_methods",
            },
        )

    def test_extra_bypass_actor_is_drift(self) -> None:
        current = as_current(TAG_RULESET, 2)
        current["bypass_actors"] = [
            {"actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "always"}
        ]
        plan = self.plan([as_current(BRANCH_RULESET, 1), current], COMPLIANT_SETTINGS)
        tag = plan["rulesets"][1]
        self.assertEqual(tag["action"], "update")
        self.assertEqual([item["field"] for item in tag["drift"]], ["bypass_actors"])
        self.assertEqual(tag["payload"]["bypass_actors"], [])

    def test_enforcement_and_conditions_drift(self) -> None:
        current = as_current(BRANCH_RULESET, 1)
        current["enforcement"] = "evaluate"
        current["conditions"] = {"ref_name": {"include": ["refs/heads/main"], "exclude": []}}
        plan = self.plan([current, as_current(TAG_RULESET, 2)], COMPLIANT_SETTINGS)
        self.assertEqual(
            [item["field"] for item in plan["rulesets"][0]["drift"]],
            ["enforcement", "conditions"],
        )

    def test_wrong_merge_settings_are_patched(self) -> None:
        settings = dict(COMPLIANT_SETTINGS, allow_squash_merge=True,
                        delete_branch_on_merge=False)
        plan = self.plan(
            [as_current(BRANCH_RULESET, 1), as_current(TAG_RULESET, 2)], settings
        )
        self.assertEqual(plan["merge_settings"]["action"], "patch")
        self.assertEqual(
            plan["merge_settings"]["payload"],
            {"allow_squash_merge": False, "delete_branch_on_merge": True},
        )

    def test_unreadable_merge_settings_are_drift(self) -> None:
        drift = cr.diff_merge_settings({})
        self.assertEqual(len(drift), 4)

    def test_duplicate_named_rulesets_are_rejected(self) -> None:
        with self.assertRaises(cr.PlanError):
            self.plan(
                [as_current(BRANCH_RULESET, 1), as_current(BRANCH_RULESET, 3)],
                COMPLIANT_SETTINGS,
            )


class ProcessTests(unittest.TestCase):
    def test_compliant_repository_makes_no_writes_even_when_applying(self) -> None:
        client = FakeClient(
            [as_current(BRANCH_RULESET, 1), as_current(TAG_RULESET, 2)],
            COMPLIANT_SETTINGS,
        )
        result = cr.process_repository(client, "example/repo", desired(), apply=True)
        self.assertEqual(result["status"], "compliant")
        self.assertEqual(client.writes, [])

    def test_dry_run_makes_no_writes(self) -> None:
        client = FakeClient([], dict(COMPLIANT_SETTINGS, allow_rebase_merge=True))
        result = cr.process_repository(client, "example/repo", desired(), apply=False)
        self.assertEqual(result["status"], "drift")
        self.assertIsNone(result["after"])
        self.assertEqual(client.writes, [])

    def test_apply_converges_and_second_run_is_idempotent(self) -> None:
        stale = as_current(BRANCH_RULESET, 7)
        stale["rules"].append({"type": "required_linear_history"})
        client = FakeClient([stale], dict(COMPLIANT_SETTINGS, allow_squash_merge=True))
        result = cr.process_repository(client, "example/repo", desired(), apply=True)
        self.assertEqual(result["status"], "applied", result.get("error"))
        self.assertEqual(
            client.writes,
            [
                ("PUT", "/repos/example/repo/rulesets/7"),
                ("POST", "/repos/example/repo/rulesets"),
                ("PATCH", "/repos/example/repo"),
            ],
        )
        self.assertFalse(cr.plan_has_changes(result["after"]))

        client.writes.clear()
        again = cr.process_repository(client, "example/repo", desired(), apply=True)
        self.assertEqual(again["status"], "compliant")
        self.assertEqual(client.writes, [])

    def test_report_renders_before_and_after(self) -> None:
        client = FakeClient([], COMPLIANT_SETTINGS)
        result = cr.process_repository(client, "example/repo", desired(), apply=True)
        report = cr.build_report(
            mode="apply",
            catylist_ref=SHA,
            templates_ref=SHA,
            repos_filter=[],
            skipped=[{"repository": "dlworrell/CLK", "reason": "excluded"}],
            results=[result],
        )
        self.assertEqual(report["summary"], {"applied": 1})
        self.assertNotIn("payload", report["repositories"][0]["before"]["rulesets"][0])
        markdown = cr.render_markdown(report)
        self.assertIn("| `example/repo` | `protect-default-branch` | missing | create | compliant |", markdown)
        self.assertIn("dlworrell/CLK", markdown)


INTEGRATION_RULESET = dict(
    copy.deepcopy(BRANCH_RULESET),
    name="protect-integration-branches",
    conditions={"ref_name": {"include": ["refs/heads/dev-daily", "refs/heads/fitment"], "exclude": []}},
)


def desired_with_integration() -> list[dict]:
    return desired() + [cr.validate_desired_ruleset(
        INTEGRATION_RULESET, expected_name="protect-integration-branches", expected_target="branch")]


class IntegrationBranchTests(unittest.TestCase):
    """Catylist ADR-0013: dev-daily and fitment only where adopted."""

    def write_config(self, names: list[str]) -> Path:
        import json, tempfile
        tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        json.dump({"schema": "aems.fitment-config.v1", "repositories": names}, tmp)
        tmp.close()
        self.addCleanup(Path(tmp.name).unlink)
        return Path(tmp.name)

    def test_only_adopted_repositories_get_the_integration_ruleset(self) -> None:
        adopted = cr.load_adopted(self.write_config(["dlworrell/ruleset-sandbox"]))
        names = lambda repo: [r["name"] for r in cr.desired_for(repo, desired_with_integration(), adopted)]
        self.assertIn("protect-integration-branches", names("dlworrell/Ruleset-Sandbox"))
        self.assertNotIn("protect-integration-branches", names("dlworrell/AEMS"))

    def test_missing_config_adopts_nothing_and_bad_config_is_refused(self) -> None:
        self.assertEqual(cr.load_adopted(Path("/nonexistent/fitment.json")), frozenset())
        with self.assertRaises(cr.PlanError):
            cr.load_adopted(self.write_config(["not a repo"]))

    def test_one_missing_branch_is_never_recreated_from_the_default_branch(self) -> None:
        for present in ("dev-daily", "fitment"):
            with self.subTest(present=present):
                client = FakeClient([], COMPLIANT_SETTINGS, branches=(present,))
                result = cr.process_repository(client, "example/repo", desired_with_integration(), apply=True)
                self.assertEqual(result["status"], "error")
                self.assertIn("is missing but", result["error"])
                self.assertIn("promotion history", result["error"])
                self.assertEqual(client.writes, [])

    def test_existing_branches_get_the_ruleset_created(self) -> None:
        client = FakeClient([], COMPLIANT_SETTINGS)
        result = cr.process_repository(client, "example/repo", desired_with_integration(), apply=True)
        self.assertEqual(result["status"], "applied", result.get("error"))
        created = {r["name"] for r in client.rulesets.values()}
        self.assertIn("protect-integration-branches", created)
        self.assertFalse([p for _, p in client.writes if "/git/refs" in p or "/environments/" in p])

    def test_first_adoption_creates_branches_environment_and_rulesets_in_order(self) -> None:
        client = FakeClient([], COMPLIANT_SETTINGS, branches=(), environment=None, policies=())
        result = cr.process_repository(client, "example/repo", desired_with_integration(), apply=True)
        self.assertEqual(result["status"], "applied", result.get("error"))
        paths = [p for _, p in client.writes]
        self.assertEqual(paths[:4], ["/repos/example/repo/git/refs", "/repos/example/repo/git/refs",
                                     "/repos/example/repo/environments/release",
                                     "/repos/example/repo/environments/release/deployment-branch-policies"])
        self.assertTrue(all(p.endswith("/rulesets") for p in paths[4:]))
        self.assertEqual(sorted(client.branches), ["dev-daily", "fitment"])
        env_body = next(b for m, p, b in client.bodies if p.endswith("/environments/release"))
        self.assertEqual(env_body["reviewers"], [{"type": "User", "id": OWNER_ID}])
        self.assertFalse(env_body["prevent_self_review"])
        self.assertEqual(env_body["deployment_branch_policy"],
                         {"protected_branches": False, "custom_branch_policies": True})
        self.assertIn({"name": "main", "type": "branch"}, client.policies)
        self.assertEqual(result["adr0013"]["status"], "applied")

    def test_dry_run_reports_the_setup_without_writing(self) -> None:
        client = FakeClient([], COMPLIANT_SETTINGS, branches=(), environment=None, policies=())
        result = cr.process_repository(client, "example/repo", desired_with_integration(), apply=False)
        self.assertEqual(result["status"], "drift")
        self.assertEqual(client.writes, [])
        setup = result["adr0013"]["before"]
        self.assertEqual(setup["branches"]["action"], "create")
        self.assertIn("environment missing", setup["environment"]["drift"])

    def test_environment_without_owner_or_with_self_review_blocked_is_repaired_keeping_reviewers(self) -> None:
        env = copy.deepcopy(COMPLIANT_ENVIRONMENT)
        env["protection_rules"][0]["reviewers"] = [{"type": "Team", "reviewer": {"id": 42}}]
        env["protection_rules"][0]["prevent_self_review"] = True
        env["deployment_branch_policy"] = None
        client = FakeClient([], COMPLIANT_SETTINGS, environment=env, policies=())
        result = cr.process_repository(client, "example/repo", desired_with_integration(), apply=True)
        self.assertEqual(result["status"], "applied", result.get("error"))
        drift = result["adr0013"]["before"]["environment"]["drift"]
        self.assertEqual(len(drift), 4, drift)
        env_body = next(b for m, p, b in client.bodies if p.endswith("/environments/release"))
        self.assertEqual(env_body["reviewers"], [{"type": "Team", "id": 42}, {"type": "User", "id": OWNER_ID}])

    def test_extra_branch_policies_are_kept_and_reported(self) -> None:
        client = FakeClient([], COMPLIANT_SETTINGS, policies=(("main", "branch"), ("v*", "tag")))
        result = cr.process_repository(client, "example/repo", desired_with_integration(), apply=True)
        self.assertEqual(result["status"], "applied", result.get("error"))
        self.assertFalse([p for _, p in client.writes if "/environments/" in p])
        report = cr.build_report(mode="apply", catylist_ref="c" * 40, templates_ref="t" * 40,
                                 repos_filter=[], skipped=[], results=[result])
        markdown = cr.render_markdown(report)
        self.assertIn("other deployment branch policies kept: tag:v*", markdown)
        self.assertIn("environment release", markdown)

    def test_second_branch_failing_twice_says_how_to_finish_the_first_adoption(self) -> None:
        # Fixes #95: a half-created first adoption must not get the "restore from promotion history" advice.
        client = FakeClient([], COMPLIANT_SETTINGS, branches=(), environment=None, policies=())
        original = client.request
        calls = []

        def request(method, path, body=None):
            if method == "POST" and path.endswith("/git/refs") and body["ref"].endswith("/fitment"):
                calls.append(body)
                raise cr.GitHubError(502, "Bad Gateway")
            return original(method, path, body)
        client.request = request
        result = cr.process_repository(client, "example/repo", desired_with_integration(), apply=True)
        self.assertEqual(result["status"], "error")
        self.assertIn("created dev-daily from the default branch", result["error"])
        self.assertIn(f"create fitment from the same commit ({'a' * 40})", result["error"])
        self.assertNotIn("promotion history", result["error"])
        self.assertEqual(len(calls), 2)  # retried once
        self.assertFalse([p for _, p in client.writes if "/environments/" in p or p.endswith("/rulesets")])

    def test_transient_branch_failure_is_retried_once(self) -> None:
        client = FakeClient([], COMPLIANT_SETTINGS, branches=(), environment=None, policies=())
        original = client.request
        failures = []

        def request(method, path, body=None):
            if method == "POST" and path.endswith("/git/refs") and body["ref"].endswith("/fitment") and not failures:
                failures.append(body)
                raise cr.GitHubError(502, "Bad Gateway")
            return original(method, path, body)
        client.request = request
        result = cr.process_repository(client, "example/repo", desired_with_integration(), apply=True)
        self.assertEqual(result["status"], "applied", result.get("error"))
        self.assertEqual(sorted(client.branches), ["dev-daily", "fitment"])

    def test_write_that_succeeded_despite_an_error_is_not_a_failure(self) -> None:
        # Fixes #160: GitHub created the ref but returned an error; the retry would say "already exists".
        for flaky in ("dev-daily", "fitment"):
            with self.subTest(flaky=flaky):
                client = FakeClient([], COMPLIANT_SETTINGS, branches=(), environment=None, policies=())
                original = client.request
                posts = []

                def request(method, path, body=None, flaky=flaky, original=original, posts=posts, client=client):
                    if method == "POST" and path.endswith("/git/refs"):
                        posts.append(body["ref"])
                        name = body["ref"].removeprefix("refs/heads/")
                        if name in client.branches:
                            raise cr.GitHubError(422, "Reference already exists")
                        if name == flaky and posts.count(body["ref"]) == 1:
                            original(method, path, body)  # created on GitHub's side...
                            raise cr.GitHubError(502, "Bad Gateway")  # ...but reported as an error
                    return original(method, path, body)
                client.request = request
                result = cr.process_repository(client, "example/repo", desired_with_integration(), apply=True)
                self.assertEqual(result["status"], "applied", result.get("error"))
                self.assertEqual(sorted(client.branches), ["dev-daily", "fitment"])
                self.assertEqual(posts.count(f"refs/heads/{flaky}"), 1)  # checked, not resent

    def test_existing_ref_at_another_commit_is_still_an_error(self) -> None:
        client = FakeClient([], COMPLIANT_SETTINGS, branches=(), environment=None, policies=())
        original = client.request

        def request(method, path, body=None):
            if method == "POST" and path.endswith("/git/refs") and body["ref"].endswith("/fitment"):
                client.branches["fitment"] = "9" * 40  # someone else's branch appeared
                raise cr.GitHubError(422, "Reference already exists")
            return original(method, path, body)
        client.request = request
        result = cr.process_repository(client, "example/repo", desired_with_integration(), apply=True)
        self.assertEqual(result["status"], "error")
        self.assertIn(f"fitment appeared at {'9' * 12}", result["error"])

    def test_setup_that_still_differs_after_apply_is_an_error_before_rulesets(self) -> None:
        # Fixes #96: the re-read after apply catches a write GitHub accepted but did not keep.
        client = FakeClient([], COMPLIANT_SETTINGS, environment=None, policies=())
        original = client.request

        def request(method, path, body=None):
            if method == "PUT" and path.endswith("/environments/release"):
                client.writes.append((method, path))
                return {}  # accepted, not applied
            return original(method, path, body)
        client.request = request
        result = cr.process_repository(client, "example/repo", desired_with_integration(), apply=True)
        self.assertEqual(result["status"], "error")
        self.assertIn("ADR-0013 setup still differs after apply: environment missing", result["error"])
        self.assertFalse([p for _, p in client.writes if p.endswith("/rulesets")])

    def test_admin_bypass_warning_and_dry_run_rows_are_rendered(self) -> None:
        # Fixes #97.
        env = dict(copy.deepcopy(COMPLIANT_ENVIRONMENT), can_admins_bypass=True)
        result = cr.process_repository(FakeClient([], COMPLIANT_SETTINGS, environment=env), "example/repo",
                                       desired_with_integration(), apply=False)
        report = cr.build_report(mode="dry-run", catylist_ref="c" * 40, templates_ref="t" * 40,
                                 repos_filter=[], skipped=[], results=[result])
        self.assertIn("administrators may bypass the release gate", cr.render_markdown(report))
        first = cr.process_repository(FakeClient([], COMPLIANT_SETTINGS, branches=(), environment=None, policies=()),
                                      "example/repo", desired_with_integration(), apply=False)
        report = cr.build_report(mode="dry-run", catylist_ref="c" * 40, templates_ref="t" * 40,
                                 repos_filter=[], skipped=[], results=[first])
        markdown = cr.render_markdown(report)
        self.assertRegex(markdown, r"dev-daily \+ fitment[^\n]*would create")
        self.assertRegex(markdown, r"environment release[^\n]*would create")

    def test_compliant_setup_alone_reports_compliant(self) -> None:
        client = FakeClient([as_current(BRANCH_RULESET, 1), as_current(TAG_RULESET, 2),
                             as_current(INTEGRATION_RULESET, 3)], COMPLIANT_SETTINGS)
        result = cr.process_repository(client, "example/repo", desired_with_integration(), apply=True)
        self.assertEqual(result["status"], "compliant", result.get("error"))
        self.assertEqual(client.writes, [])


class RequiredChecksTests(unittest.TestCase):
    """ADR-0006 section 4: per-repository required checks, one ruleset per branch."""

    def write(self, data) -> Path:
        import json, tempfile
        path = Path(tempfile.mkdtemp()) / "required-checks.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def config(self, branches):
        return {"schema": cr.REQUIRED_CHECKS_SCHEMA,
                "apps": {"github-actions": 15368, "catylist-ring-0": 5474337},
                "repositories": {"dlworrell/demo": branches}}

    def test_repository_config_is_valid(self):
        required = cr.load_required_checks(cr.DEFAULT_REQUIRED_CHECKS)
        self.assertIn("dlworrell/aems", required)
        for rulesets in required.values():
            for ruleset in rulesets:
                checks = ruleset["rules"][0]["parameters"]["required_status_checks"]
                self.assertTrue(checks)
                self.assertTrue(ruleset["name"].startswith(cr.REQUIRED_CHECKS_PREFIX))

    def test_each_branch_gets_its_own_ruleset_and_empty_lists_none(self):
        required = cr.load_required_checks(self.write(self.config({
            "dev-daily": [],
            "fitment": [{"context": "fitment/source", "app": "catylist-ring-0"}],
            "main": [{"context": "test", "app": "github-actions"},
                     {"context": "fitment", "app": "catylist-ring-0"}],
        })))["dlworrell/demo"]
        self.assertEqual([r["name"] for r in required], ["require-ci-fitment", "require-ci-main"])
        main = required[1]
        self.assertEqual(main["conditions"]["ref_name"]["include"], ["~DEFAULT_BRANCH"])
        self.assertEqual(main["bypass_actors"], [])
        params = main["rules"][0]["parameters"]
        self.assertEqual(params["required_status_checks"],
                         [{"context": "test", "integration_id": 15368},
                          {"context": "fitment", "integration_id": 5474337}])
        self.assertFalse(params["strict_required_status_checks_policy"])

    def test_refusals(self):
        bad = [
            self.config({"release": [{"context": "x", "app": "github-actions"}]}),
            self.config({"main": [{"context": "x", "app": "unknown-app"}]}),
            self.config({"main": [{"context": "", "app": "github-actions"}]}),
            self.config({"main": [{"context": "x", "app": "github-actions"},
                                  {"context": "x", "app": "github-actions"}]}),
            {"schema": "wrong", "apps": {}, "repositories": {}},
            # Fixes #116: apps validation and malformed shapes.
            dict(self.config({}), apps={"x": True}),
            dict(self.config({}), apps={"x": 0}),
            dict(self.config({}), apps={"x": -1}),
            dict(self.config({}), apps={"x": "15368"}),
            dict(self.config({}), repositories={"not a repo": {}}),
            dict(self.config({}), repositories={"dlworrell/demo": []}),
            self.config({"main": {}}),
            self.config({"main": ["x"]}),
            dict(self.config({}), repositories=[]),
        ]
        for data in bad:
            with self.subTest(data=data), self.assertRaises(cr.PlanError):
                cr.load_required_checks(self.write(data))

    def test_required_checks_option_reaches_the_plan_through_main(self):
        # Fixes #117: --required-checks is parsed and its rulesets are planned by main().
        import io, json, os, tempfile
        from contextlib import redirect_stdout
        from unittest import mock

        tmp = Path(tempfile.mkdtemp())
        required = self.write({"schema": cr.REQUIRED_CHECKS_SCHEMA, "apps": {"github-actions": 15368},
                               "repositories": {"dlworrell/JAG": {"main": [{"context": "build",
                                                                            "app": "github-actions"}]}}})
        fitment = tmp / "fitment.json"
        fitment.write_text(json.dumps({"schema": cr.FITMENT_CONFIG_SCHEMA, "repositories": []}))

        class Source:
            def __init__(self, *_a, **_k):
                pass

            def get_file(self, repository, path, ref):
                if path == cr.INVENTORY_PATH:
                    return inventory()
                return copy.deepcopy(TAG_RULESET if path == cr.TAG_RULESET_PATH else BRANCH_RULESET)

        admin = FakeClient([], COMPLIANT_SETTINGS)
        clients = iter([Source(), admin])
        argv = ["--catylist-ref", "c" * 40, "--templates-ref", "d" * 40, "--repos", "dlworrell/JAG",
                "--output-dir", str(tmp / "out"), "--fitment-config", str(fitment),
                "--required-checks", str(required)]
        with mock.patch.dict(os.environ, {cr.ADMIN_TOKEN_ENV: "x"}), \
                mock.patch.object(cr, "GitHubClient", side_effect=lambda *_a, **_k: next(clients)), \
                redirect_stdout(io.StringIO()):
            self.assertEqual(cr.main(argv), 0)
        report = json.loads((tmp / "out" / "report.json").read_text())
        planned = [r["name"] for entry in report["repositories"] for r in entry["before"]["rulesets"]]
        self.assertIn("require-ci-main", planned)
        created = [b for m, p, b in admin.bodies if m == "POST" and p.endswith("/rulesets")]
        self.assertEqual(created, [])  # a dry run plans the ruleset but writes nothing
        self.assertEqual(cr.parse_args(argv).required_checks, required)

    def test_case_duplicate_repository_is_refused(self):
        # Fixes #119 and #139: every spelling order is refused, not only lower-case first.
        branches = {"main": [{"context": "a", "app": "github-actions"}]}
        for first, second in (("dlworrell/demo", "dlworrell/DEMO"),
                              ("dlworrell/DEMO", "dlworrell/demo"),
                              ("Dlworrell/Demo", "dlworrell/DEMO"),
                              ("DLWORRELL/demo", "dlworrell/demo")):
            data = self.config(branches)
            data["repositories"] = {first: branches, second: branches}
            with self.subTest(first=first, second=second), \
                    self.assertRaisesRegex(cr.PlanError, "duplicates another entry"):
                cr.load_required_checks(self.write(data))

    def test_missing_file_means_no_required_checks(self):
        self.assertEqual(cr.load_required_checks(Path("/nonexistent/required.json")), {})

    def test_only_default_branch_checks_apply_before_adoption(self):
        required = cr.load_required_checks(self.write(self.config({
            "dev-daily": [{"context": "a", "app": "github-actions"}],
            "main": [{"context": "a", "app": "github-actions"}],
        })))
        names = lambda adopted: [r["name"] for r in cr.desired_for(
            "dlworrell/demo", [], adopted, required)]
        self.assertEqual(names(frozenset()), ["require-ci-main"])
        self.assertEqual(names(frozenset({"dlworrell/demo"})),
                         ["require-ci-dev-daily", "require-ci-main"])

    def test_applied_ruleset_with_api_defaults_shows_no_drift(self):
        ruleset = cr.load_required_checks(self.write(self.config({
            "main": [{"context": "a", "app": "github-actions"}],
        })))["dlworrell/demo"][0]
        current = copy.deepcopy(ruleset)
        current["id"] = 7
        current["source_type"] = "Repository"
        self.assertEqual(cr.diff_ruleset(ruleset, current), [])
        current["rules"][0]["parameters"]["required_status_checks"] = []
        self.assertTrue(cr.diff_ruleset(ruleset, current))


if __name__ == "__main__":
    unittest.main()
