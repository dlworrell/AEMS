# Catylist Default-Branch Rulesets

Status: Draft implementation; not yet authorized for apply runs
Owner: AEMS
Issue: dlworrell/Catylist#22
Upstream decision: `dlworrell/Catylist/docs/adr/ADR-0006-default-branch-protection-and-signed-commits.md`
Upstream obligation: AES-DEV-001-R001 to R007 (Default-Branch Integrity)

## Purpose

Catylist ADR-0006 requires default-branch protection, signed commits, merge
commits only, and protected release tags on every repository whose inventory
entry has `default_branch_policy: protected`. AES-DEV-001 records the
obligations as AES-DEV-001-R001 to R007. dlworrell/repo_templates holds the
baseline rulesets (dlworrell/Catylist#25). AEMS applies them and reports
drift.

AEMS does not originate these rules. Changes to the baseline go to
repo_templates. Changes to which repositories are in scope go to the Catylist
inventory.

## Components

- `.github/workflows/apply-catylist-rulesets.yml`: manually dispatched
  workflow.
- `scripts/catylist_rulesets.py`: planner and applier (Python standard
  library only). Planning and drift detection are pure functions. GitHub I/O
  is kept separate.
- `tests/test_catylist_rulesets.py`: unit tests.

## Sources

Each run reads every input at a pinned commit SHA. A branch or tag name is
rejected.

| Input | Repository | Path |
|---|---|---|
| `catylist_ref` | `dlworrell/Catylist` | `inventory/repositories.json` (`catylist.repository-inventory.v1`) |
| `templates_ref` | `dlworrell/repo_templates` | `rulesets/protect-default-branch.json`, `rulesets/protect-release-tags.json` |

The run fails before contacting any target repository if a baseline ruleset
does not meet ADR-0006: an unexpected name or target, enforcement other than
`active`, any bypass actor, or a `required_linear_history`,
`required_status_checks`, or `code_scanning` rule.

The desired merge settings are fixed by ADR-0006 section 2:
`allow_merge_commit: true`, `allow_squash_merge: false`,
`allow_rebase_merge: false`, `delete_branch_on_merge: true`.

## Workflow inputs

| Input | Required | Default | Meaning |
|---|---|---|---|
| `dry_run` | no | `true` | Report drift only. Set it to `false` to apply. |
| `repos` | no | empty | A comma-separated `full_name` filter, applied after the policy filter. |
| `catylist_ref` | yes | none | The 40-hex commit SHA of dlworrell/Catylist. |
| `templates_ref` | yes | none | The 40-hex commit SHA of dlworrell/repo_templates. |

Only entries with `default_branch_policy: protected` are processed. A filter
name whose policy is `excluded` or `pending-classification` is skipped and
listed in the report. A filter name that is not in the inventory fails the
run. The one exception is `dlworrell/ruleset-sandbox`, which is not a Catalyst
repository but can be named explicitly for rollout testing.

## Drift model

For each repository the planner reads:

- the repository-level rulesets (`GET /repos/{repo}/rulesets?includes_parents=false`).
  The full ruleset is then read (`GET /repos/{repo}/rulesets/{id}`) for
  each ruleset whose name matches a baseline ruleset;
- the merge settings (`GET /repos/{repo}`).

Rulesets are matched by name. Drift is:

- a missing ruleset, which is created (`POST /repos/{repo}/rulesets`);
- a differing `target`, `enforcement`, or `conditions`, any bypass actor, a
  missing baseline rule, a rule that is not in the baseline (for example
  `required_linear_history`), or a differing value for a parameter that the
  baseline declares. Any of these updates the ruleset in place
  (`PUT /repos/{repo}/rulesets/{id}`) with the complete baseline. Parameters
  that the API reports but the baseline does not declare are ignored;
- a merge setting that differs from the desired value or is not readable.
  The differing keys are patched (`PATCH /repos/{repo}`).

A repository with no drift receives no write requests, so repeated runs are
idempotent. Two rulesets with the same managed name are an error that must be
resolved by hand. Rulesets with other names are left alone and listed as
unmanaged in the report.

After an apply, the planner re-reads the repository and records the result as
the "after" state. Drift that remains is an error.

## Report

The job summary shows a Markdown table with one row per repository and item
(each ruleset and the merge settings). Each row gives the before state, the
action, and the after state. The drift details follow the table. The
`catylist-rulesets-report` artifact contains `report.json`
(`aems.catylist-rulesets-report.v1`) and `report.md`. The job fails if any
repository errors, for example when the token cannot reach it, the repository
is archived, or the plan does not support rulesets.

## Token setup

GitHub API calls to target repositories use the Actions secret
`RULESET_ADMIN_TOKEN`. Configure it as follows:

1. Create a fine-grained personal access token. The resource owner is
   `dlworrell`. Give it a short expiry.
2. Under repository access, choose **Only select repositories**. Select
   only the in-scope repositories for the current rollout stage.
3. Grant exactly these repository permissions:
   - **Administration: Read and write** (rulesets and merge settings);
   - **Metadata: Read-only** (granted automatically).

   Grant no other permissions.
4. Store the token as the repository Actions secret `RULESET_ADMIN_TOKEN` in
   dlworrell/AEMS.

The workflow's own `GITHUB_TOKEN` has `contents: read` only. It is used to
read the public Catylist inventory and the repo_templates rulesets. The admin
token is passed to a single step through the environment. It is never placed
on a command line or echoed, and request errors are redacted. Revoke or
rotate the token after each rollout stage.

## Operating procedure

Always run with `dry_run: true` first and review the drift report. Then
re-run with the same inputs and `dry_run: false`.

Rollout order:

1. `dlworrell/ruleset-sandbox`: `repos: dlworrell/ruleset-sandbox`. Confirm
   that a signed pull request merges, and that unsigned commits, force pushes,
   branch deletion, squash merges, rebase merges, and `v*` tag moves are
   rejected.
2. `dlworrell/code-noodling`, only after its P0 remediation is complete.
   Direct unsigned pushes to its `main` stop working at this point.
3. The remaining protected repositories, filtered in small groups or
   unfiltered.

## Traceability

- Catylist ADR-0006, sections 2 and 3: the rules applied.
- AES-DEV-001-R001 to R007 (Default-Branch Integrity): the obligations that this implements.
- dlworrell/Catylist#25: the repo_templates baseline that this reads.
- dlworrell/Catylist#22: this implementation.

Required status checks and code-scanning rules are outside this baseline
(ADR-0006 section 4) and are never added by this workflow.
