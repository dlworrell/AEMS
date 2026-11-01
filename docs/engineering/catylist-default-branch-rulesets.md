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
| `templates_ref` | `dlworrell/repo_templates` | `rulesets/protect-default-branch.json`, `rulesets/protect-release-tags.json`, and `rulesets/protect-integration-branches.json` for adopted repositories |

The run fails before contacting any target repository if a baseline ruleset
does not meet ADR-0006: an unexpected name or target, enforcement other than
`active`, any bypass actor, or a `required_linear_history`,
`required_status_checks`, or `code_scanning` rule.

The desired merge settings are fixed by ADR-0006 section 2:
`allow_merge_commit: true`, `allow_squash_merge: false`,
`allow_rebase_merge: false`, `delete_branch_on_merge: true`.

## Daily and fitment branches (Catylist ADR-0013)

A repository listed in AEMS `config/fitment.json` also gets
`protect-integration-branches`, which gives `dev-daily` and `fitment` the
default-branch rules. Other repositories are not offered the ruleset, and a
`templates_ref` older than the ruleset file still works for them.

Before that ruleset, `scripts/adr0013_setup.py` sets up the rest of the
repository's ADR-0013 model, so adoption needs no manual settings:

- **Branches.** When both `dev-daily` and `fitment` are missing (a first
  adoption), both are created from the default branch head. When only one is
  missing, the run stops for that repository: the missing branch is never
  recreated from the default branch, because the other may hold unreleased
  work. Restore it from the head of its last promotion pull request.
- **`release` environment.** The repository owner becomes a required
  reviewer; other reviewers already configured are kept. "Prevent
  self-review" is turned off, because a single-owner repository has nobody
  else to approve. Deployments are limited to `main` through a deployment
  branch policy. Other branch policies are reported, never removed. If
  administrators may bypass the gate, the report says so; the REST API cannot
  change that setting, so change it in the environment's settings.

A dry run reports both as `would create` or `would update` and writes
nothing. An apply re-reads them and fails the repository if anything still
differs.

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
run. The AEMS implementation retains a legacy explicit-selection exception for
`dlworrell/ruleset-sandbox`. Making that repository optional experimental work,
rather than a required testbed or acceptance gate, is proposed in **pending
Catylist ADR-0014**; it is not yet accepted upstream. Normal inventory selection
can use its proposed experimental entry after the governing Catylist change
merges. See the retained proposal and its status below.

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

GitHub API calls to target repositories use the secret `RULESET_ADMIN_TOKEN`,
stored in the protected `ruleset-admin` environment, not as a repository
secret. The job declares `environment: ruleset-admin`, so it cannot read the
token until the maintainer approves that run.

1. Create a fine-grained personal access token. The resource owner is
   `dlworrell`. Give it a short expiry.
2. Under repository access, choose **Only select repositories**. Select
   only the in-scope repositories for the current rollout stage.
3. Grant exactly these repository permissions:
   - **Administration: Read and write** (rulesets, merge settings, and the
     `release` environment with its deployment branch policy);
   - **Contents: Read and write** (creating `dev-daily` and `fitment` in
     repositories that adopt ADR-0013; not needed otherwise);
   - **Metadata: Read-only** (granted automatically).

   Grant no other permissions.
4. In dlworrell/AEMS, open **Settings → Environments → New environment**,
   name it `ruleset-admin`, and configure:
   - **Required reviewers:** the maintainer. Leave "Prevent self-review"
     off while the program has a single maintainer, so the maintainer can
     approve their own dispatch.
   - **Deployment branches and tags:** **Selected branches and tags**, with
     the single rule `main`.
5. In that environment, add the environment secret `RULESET_ADMIN_TOKEN`.
   Do not also store it as a repository secret.

The workflow's own `GITHUB_TOKEN` has `contents: read` only. It is used to
read the public Catylist inventory and the repo_templates rulesets. The admin
token is passed to a single step through the environment. It is never placed
on a command line or echoed, and request errors are redacted. Every run
waits for approval in the Actions UI before the token is released. Revoke or
rotate the token after each rollout stage.

## Operating procedure

Always run with `dry_run: true` first and review the drift report. Then
re-run with the same inputs and `dry_run: false`.

Rollout order:

1. Record positive and refusal validation for the exact ruleset version using
   controlled fixtures or appropriate owning-repository evidence. Include
   signed PR publication and the applicable history, deletion and tag rules;
   distinguish simulated evidence from live GitHub evidence. While ADR-0014
   is pending, the accepted obligations still name `ruleset-sandbox`:
   [ADR-0006](https://github.com/dlworrell/Catylist/blob/ae617db4074b676795ea5a8f9e1a4d50ab047930/docs/adr/ADR-0006-default-branch-protection-and-signed-commits.md)
   (*Recovery and migration impact*, step 2) requires each ruleset version to
   be validated in `ruleset-sandbox` before any other repository, and
   [Code Law 7](https://github.com/dlworrell/Catylist/blob/ae617db4074b676795ea5a8f9e1a4d50ab047930/CODE_OF_CONDUCT.md)
   requires each Code version to be trialled there first. Sandbox validation is
   therefore a prerequisite for step 2 today.
2. `dlworrell/code-noodling`, only after its P0 remediation is complete.
   Direct unsigned pushes to its `main` stop working at this point.
3. The remaining protected repositories, filtered in small groups or
   unfiltered.

## Pending experimental-sandbox proposal (Catylist ADR-0014)

ADR-0014 has not merged into Catylist. The accepted Catylist Code of Conduct
and ADR-0006 remain the governing authority; this implementation document does
not accept or supersede them.

The [retained Catylist proposal patch](Catylist-experimental-sandbox-20261026.patch)
contains the proposed ADR-0014, Code version 1.2.0 amendment, experimental
inventory entry and related ADR updates. It is kept in AEMS for upstream review
and traceability. Its phrase "effective on owner-approved merge" describes the
proposed future effect, not an approval already recorded in Catylist.

The proposal would make `ruleset-sandbox` optional experimental work, with its
availability and results no longer acting as a prerequisite for other
repositories. It would retain recorded positive/refusal validation, historical
evidence about its original subjects, dry-run review, owner approval and
signature requirements. Until acceptance, these proposed changes must not be
cited as current Catylist policy.

After an owner-approved Catylist merge, replace this pending notice with the
accepted ADR link and its merge evidence. Retaining the patch alone does not
establish acceptance.

## Traceability

- Catylist ADR-0006, sections 2 and 3: the rules applied.
- AES-DEV-001-R001 to R007 (Default-Branch Integrity): the obligations that this implements.
- dlworrell/Catylist#25: the repo_templates baseline that this reads.
- dlworrell/Catylist#22: this implementation.

Required status checks and code-scanning rules are outside this baseline
(ADR-0006 section 4) and are never added by this workflow.

## Required CI checks (ADR-0006 section 4)

Required status checks are per repository and are kept out of the shared baseline. `config/required-checks.json` lists them for each repository and branch. Each branch with a non-empty list gets its own ruleset, named `require-ci-dev-daily`, `require-ci-fitment` or `require-ci-main`. The `require-ci-main` ruleset targets the default branch, whatever it is called. Each ruleset holds only the `required_status_checks` rule, so the shared baseline stays unchanged.

- **Which checks are listed:** only checks that ran on every recent merged pull request into that branch, from workflows without path filters. A required check that never reports blocks every merge.
- **Empty lists:** an empty list creates no ruleset. This is the case for AEMS and atarix `dev-daily` for now.
- **Check sources:** every check is pinned to the App that posts it:
  - `github-actions` (15368) for CI jobs;
  - `catylist-ring-0` (5474337) for `fitment/source` and `fitment`.
- **What the ring-0 checks guard:** requiring `fitment/source` on `fitment` and `main` stops a manual merge from the wrong source branch. Requiring `fitment` on `main` stops a manual release-candidate merge while the fitment gate is red.
- **Up-to-date heads are not required** (`strict_required_status_checks_policy` is false). Promotions and release candidates are never rebased onto their base, so requiring it would block them.
- **One entry per repository:** repository names are matched case-insensitively, as GitHub matches them. Two spellings of the same repository (for example `dlworrell/AEMS` and `dlworrell/aems`) are refused when the file is loaded, rather than one silently replacing the other's checks.
- **Before adoption:** `dev-daily` and `fitment` rulesets apply only to repositories in `config/fitment.json`. Other repositories get `require-ci-main` at most.

To change a list, edit `config/required-checks.json` through a pull request. Then run the workflow as a dry run and read the plan before applying.

- **Another file:** `scripts/catylist_rulesets.py --required-checks PATH` reads a different file (the default is `config/required-checks.json`). A missing file means no required-check rulesets.
- **Removing checks:** the workflow only creates and updates rulesets; it never deletes one. Emptying a branch's list, or removing a repository's entry, stops planning that `require-ci-<branch>` ruleset but leaves an already-applied one in place. Delete it by hand in the repository's **Settings → Rules → Rulesets**.
