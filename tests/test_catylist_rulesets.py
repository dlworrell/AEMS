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


class FakeClient:
    def __init__(self, rulesets: list[dict], settings: dict) -> None:
        self.rulesets = {item["id"]: copy.deepcopy(item) for item in rulesets}
        self.settings = dict(settings)
        self.writes: list[tuple[str, str]] = []
        self.next_id = 100

    def list_rulesets(self, repository: str) -> list[dict]:
        return [
            {"id": item["id"], "name": item["name"], "source_type": "Repository"}
            for item in self.rulesets.values()
        ]

    def request(self, method: str, path: str, body=None):
        if method == "GET" and "/rulesets/" in path:
            return copy.deepcopy(self.rulesets[int(path.rsplit("/", 1)[1])])
        if method == "GET":
            return dict(self.settings, archived=False)
        self.writes.append((method, path))
        if method == "POST":
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


class MissingBranchClient(FakeClient):
    def __init__(self, missing: str, *args) -> None:
        super().__init__(*args)
        self.missing = missing

    def request(self, method: str, path: str, body=None):
        if method == "GET" and path.endswith(f"/branches/{self.missing}"):
            raise cr.GitHubError(404, "Branch not found")
        return super().request(method, path, body)


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

    def test_branches_must_exist_before_the_ruleset_is_applied(self) -> None:
        for branch in ("dev-daily", "fitment"):
            with self.subTest(branch=branch):
                client = MissingBranchClient(branch, [], COMPLIANT_SETTINGS)
                result = cr.process_repository(client, "example/repo", desired_with_integration(), apply=True)
                self.assertEqual(result["status"], "error")
                self.assertIn(f"create the {branch} branch", result["error"])
                self.assertEqual(client.writes, [])

    def test_existing_branches_get_the_ruleset_created(self) -> None:
        client = FakeClient([], COMPLIANT_SETTINGS)
        result = cr.process_repository(client, "example/repo", desired_with_integration(), apply=True)
        self.assertEqual(result["status"], "applied", result.get("error"))
        created = {r["name"] for r in client.rulesets.values()}
        self.assertIn("protect-integration-branches", created)


if __name__ == "__main__":
    unittest.main()
