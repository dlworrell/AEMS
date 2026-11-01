#!/usr/bin/env python3
"""Set up the Catylist ADR-0013 branches and release gate in one repository.

Used by ``catylist_rulesets.py`` for repositories listed in AEMS
``config/fitment.json``, before it applies ``protect-integration-branches``:

* **Branches.** ``dev-daily`` and ``fitment`` are created from the default
  branch head when *both* are missing (a first adoption). When only one is
  missing it is never recreated from the default branch, because the
  survivor may hold unreleased work that the missing branch also held; the
  run stops and asks for it to be restored from promotion history. On a first
  adoption each branch creation is retried once; if the second still fails
  after the first succeeded, the error names the commit to create it from.
* **Release environment.** ``release`` requires the repository owner's
  approval, keeps any other reviewers already configured, allows the
  person who dispatched a run to approve it (a single-owner repository has
  no one else), and accepts deployments from ``main`` only. Extra
  deployment branch policies are reported, never removed.

Nothing is deleted. A dry run reads only.
"""

from __future__ import annotations

from typing import Any, Protocol


INTEGRATION_BRANCHES = ("dev-daily", "fitment")
RELEASE_ENVIRONMENT = "release"
RELEASE_BRANCH = "main"
DESIRED_BRANCH_POLICY = {"protected_branches": False, "custom_branch_policies": True}


class SetupError(ValueError):
    """A state this tool must not repair on its own."""


class Client(Protocol):
    def request(self, method: str, path: str, body: Any | None = None) -> Any: ...


def _status(exc: Exception) -> int | None:
    return getattr(exc, "status", None)


def _get_or_none(client: Client, path: str) -> Any | None:
    try:
        return client.request("GET", path)
    except Exception as exc:  # the caller's GitHubError carries .status
        if _status(exc) == 404:
            return None
        raise


# ---------------------------------------------------------------------------
# Reading state
# ---------------------------------------------------------------------------


def read_state(client: Client, repository: str) -> dict[str, Any]:
    owner = repository.split("/", 1)[0]
    branches = {
        name: (_get_or_none(client, f"/repos/{repository}/branches/{name}") or {}).get("commit", {}).get("sha")
        for name in INTEGRATION_BRANCHES
    }
    environment = _get_or_none(client, f"/repos/{repository}/environments/{RELEASE_ENVIRONMENT}")
    policies: list[dict[str, Any]] = []
    if environment is not None and (environment.get("deployment_branch_policy") or {}).get("custom_branch_policies"):
        listing = client.request(
            "GET", f"/repos/{repository}/environments/{RELEASE_ENVIRONMENT}/deployment-branch-policies?per_page=100")
        policies = list((listing or {}).get("branch_policies", []))
    owner_id = client.request("GET", f"/users/{owner}")["id"]
    return {"owner": owner, "owner_id": owner_id, "branches": branches,
            "environment": environment, "policies": policies}


def _reviewers(environment: dict[str, Any] | None) -> tuple[list[dict[str, Any]], bool | None]:
    """Configured reviewers as PUT entries, and the prevent_self_review flag."""
    for rule in (environment or {}).get("protection_rules", []):
        if rule.get("type") == "required_reviewers":
            entries = [{"type": item.get("type"), "id": (item.get("reviewer") or {}).get("id")}
                       for item in rule.get("reviewers", [])]
            return entries, rule.get("prevent_self_review")
    return [], None


# ---------------------------------------------------------------------------
# Planning (pure)
# ---------------------------------------------------------------------------


def plan(repository: str, state: dict[str, Any]) -> dict[str, Any]:
    """What must change; raises SetupError for a state it must not repair."""
    missing = [name for name, sha in state["branches"].items() if not sha]
    if len(missing) == len(INTEGRATION_BRANCHES):
        branches = {"action": "create", "detail": f"create {', '.join(INTEGRATION_BRANCHES)} from the default branch"}
    elif missing:
        present = [name for name in INTEGRATION_BRANCHES if name not in missing]
        raise SetupError(
            f"{repository}: {missing[0]} is missing but {present[0]} exists. It is not recreated from the "
            f"default branch, which could drop unreleased work; restore {missing[0]} from its promotion "
            "history (the last promotion pull request's head), then run again")
    else:
        branches = {"action": "none", "detail": "both exist"}

    environment = state["environment"]
    reviewers, prevent_self_review = _reviewers(environment)
    drift: list[str] = []
    if environment is None:
        drift.append("environment missing")
    if not any(r["type"] == "User" and r["id"] == state["owner_id"] for r in reviewers):
        drift.append(f"@{state['owner']} is not a required reviewer")
    if prevent_self_review:
        drift.append("prevent self-review is on, so the only reviewer could not approve")
    if environment is not None and (environment.get("deployment_branch_policy") or None) != DESIRED_BRANCH_POLICY:
        drift.append("deployments are not limited to selected branches")
    names = {(p.get("name"), p.get("type", "branch")) for p in state["policies"]}
    if (RELEASE_BRANCH, "branch") not in names:
        drift.append(f"no deployment branch policy for {RELEASE_BRANCH}")
    extra = sorted(f"{t}:{n}" for n, t in names if (n, t) != (RELEASE_BRANCH, "branch"))
    warnings = [f"other deployment branch policies kept: {', '.join(extra)}"] if extra else []
    if environment is not None and environment.get("can_admins_bypass"):
        warnings.append("administrators may bypass the release gate (set in the environment's settings)")

    desired_reviewers = [r for r in reviewers if r["id"] is not None]
    if not any(r["type"] == "User" and r["id"] == state["owner_id"] for r in desired_reviewers):
        desired_reviewers.append({"type": "User", "id": state["owner_id"]})
    return {
        "branches": branches,
        "environment": {
            "action": ("create" if environment is None else "update") if drift else "none",
            "drift": drift,
            "warnings": warnings,
            "payload": {"prevent_self_review": False, "reviewers": desired_reviewers,
                        "deployment_branch_policy": DESIRED_BRANCH_POLICY} if drift else None,
            "add_main_policy": (RELEASE_BRANCH, "branch") not in names,
        },
    }


def has_changes(setup: dict[str, Any]) -> bool:
    return setup["branches"]["action"] != "none" or setup["environment"]["action"] != "none"


# ---------------------------------------------------------------------------
# Applying
# ---------------------------------------------------------------------------


def apply(client: Client, repository: str, setup: dict[str, Any]) -> None:
    if setup["branches"]["action"] == "create":
        default = client.request("GET", f"/repos/{repository}")["default_branch"]
        sha = client.request("GET", f"/repos/{repository}/git/ref/heads/{default}")["object"]["sha"]
        created: list[str] = []
        for name in INTEGRATION_BRANCHES:
            body = {"ref": f"refs/heads/{name}", "sha": sha}
            try:
                client.request("POST", f"/repos/{repository}/git/refs", body)
            except Exception as first:  # the client's own error type; retried once, as for a transient failure
                try:
                    client.request("POST", f"/repos/{repository}/git/refs", body)
                except Exception as second:
                    if not created:
                        raise second from first
                    # The next run would see one branch missing and refuse to repair it, with advice
                    # that does not fit a first adoption, so say exactly how to finish it instead.
                    raise SetupError(
                        f"{repository}: created {', '.join(created)} from the default branch at {sha[:12]}, but "
                        f"creating {name} failed twice ({second}). Nothing unreleased can be lost yet: create "
                        f"{name} from the same commit ({sha}), then run again") from second
            created.append(name)
    environment = setup["environment"]
    if environment["action"] != "none":
        client.request("PUT", f"/repos/{repository}/environments/{RELEASE_ENVIRONMENT}", environment["payload"])
        if environment["add_main_policy"]:
            client.request("POST", f"/repos/{repository}/environments/{RELEASE_ENVIRONMENT}/deployment-branch-policies",
                           {"name": RELEASE_BRANCH, "type": "branch"})


def process(client: Client, repository: str, *, apply_changes: bool) -> dict[str, Any]:
    """Plan, optionally apply and re-check. Raises SetupError or the client's error."""
    before = plan(repository, read_state(client, repository))
    result: dict[str, Any] = {"before": before, "after": None}
    if not has_changes(before):
        result["status"] = "compliant"
    elif not apply_changes:
        result["status"] = "drift"
    else:
        apply(client, repository, before)
        after = plan(repository, read_state(client, repository))
        result["after"] = after
        if has_changes(after):
            raise SetupError(f"{repository}: ADR-0013 setup still differs after apply: "
                             f"{'; '.join(after['environment']['drift']) or after['branches']['detail']}")
        result["status"] = "applied"
    return result
