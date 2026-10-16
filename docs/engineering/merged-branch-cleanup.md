# Merged-Branch Cleanup

Status: Draft implementation; not yet run
Owner: AEMS
Issue: dlworrell/Catylist#14
Related decision: `dlworrell/Catylist/docs/adr/ADR-0006-default-branch-protection-and-signed-commits.md`

## Purpose

The Catalyst repositories have accumulated many head branches whose pull
requests were merged long ago. This workflow deletes those branches in one
pass and can be re-run occasionally. It is not a standing control.

Going forward, the ADR-0006 merge settings set `delete_branch_on_merge: true`
(applied by the Catylist ruleset workflow proposed in dlworrell/AEMS#27), so GitHub
deletes a pull request's head branch when it merges and new stale branches
should be rare.

## Components

- `.github/workflows/cleanup-merged-branches.yml`: manually dispatched
  workflow.
- `scripts/cleanup_merged_branches.py`: planner and deleter (Python standard
  library only). Branch classification is a set of pure functions. GitHub I/O
  is kept separate.
- `tests/test_cleanup_merged_branches.py`: unit tests.

## Deletion rule

A branch is deleted only if ALL of the following hold:

1. It is not the repository's default branch and is not a protected branch
   (`protected: true` in the branches API).
2. It is not the head or the base of any OPEN pull request in that
   repository.
3. Its name does not match a keep pattern: `backup/*` always, plus the
   optional `keep` input (comma-separated `fnmatch` patterns).
4. EITHER (a) a MERGED pull request (`merged_at` non-null) has this branch as
   its head AND the branch's current tip SHA equals that pull request's
   `head.sha` (so no commits were added after the merge), OR (b) the compare
   API `GET /repos/{r}/compare/{default}...{branch}` reports `ahead_by == 0`
   (the branch is fully contained in the default branch).

Everything else is kept and listed in the report with the reason: open pull
request (head or base), closed-unmerged pull request, commits after merge,
unmerged commits, keep pattern, protected, or default branch.

Implementation notes:

- Pull requests are matched to branches by `head.ref` only when
  `head.repo.full_name` is the repository itself, so a fork branch with the
  same name does not count. Open pull request base refs always count.
- A branch whose `protected` field is missing is treated as protected.
- The compare API is called only for branches that rule 4a does not decide.
  Its head is the branch's tip SHA as listed, not the branch name, so the
  answer always describes the commit that was classified.
- Immediately before each delete, the branch ref is re-read. If its tip has
  moved since planning, the branch is not deleted and the repository is
  reported as an error.
- Deletion uses `DELETE /repos/{owner}/{repo}/git/refs/heads/{branch}` with
  the branch name URL-encoded. A 404, or a 422 "Reference does not exist", is
  recorded as already gone.
- After deleting, the branches are listed again. The remaining branches are
  reported, and a branch reported deleted that is still listed is an error.

## History

Deleting a merged branch does not lose work. Merged work stays in the
default branch's history. For squash-merged pull requests, whose individual
commits are not in the default branch, GitHub keeps the pull request's head
ref `refs/pull/N/head`, so the branch commits remain addressable through the
pull request (for example `git fetch origin pull/N/head`). Branches with
commits that are in neither place are kept by rule 4.

## Workflow inputs

| Input | Required | Default | Meaning |
|---|---|---|---|
| `dry_run` | no | `true` | Report only. Set it to `false` to delete. |
| `repos` | no | empty | A comma-separated `full_name` filter, applied after the policy filter. |
| `keep` | no | empty | Extra comma-separated `fnmatch` keep patterns. `backup/*` is always kept. |
| `catylist_ref` | yes | none | The 40-hex commit SHA of dlworrell/Catylist. |

The target set is every entry in `inventory/repositories.json`
(`catylist.repository-inventory.v1`) at `catylist_ref` whose
`default_branch_policy` is `protected`. The inventory is read with the
workflow's own `GITHUB_TOKEN`. A filter name whose policy is `excluded` or
`pending-classification` is skipped and listed in the report. A filter name
that is not in the inventory fails the run. The one exception is
`dlworrell/ruleset-sandbox`, which is processed only when named in `repos`.

Each repository is processed independently. An error in one repository does
not stop the others, but the job fails if any repository errored.

## Report

The job summary shows, per repository, the branches deleted (or that would
be deleted in a dry run) with the reason (`merged PR #N` or `contained in
default branch`), the branches kept with the reason, and after a deleting run
the branches that remain. The `branch-cleanup-report` artifact contains
`report.json` (`aems.branch-cleanup-report.v1`) and `report.md`.

## Token setup

GitHub API calls to target repositories use the secret
`BRANCH_CLEANUP_TOKEN`, stored in the existing protected `ruleset-admin`
environment (required reviewer: the maintainer; deployment branches: `main`
only), not as a repository secret. The job declares
`environment: ruleset-admin`, so it cannot read the token until the
maintainer approves that run.

1. Create a fine-grained personal access token. The resource owner is
   `dlworrell`. Give it a short expiry.
2. Under repository access, choose **Only select repositories**. Select
   only the repositories to clean.
3. Grant exactly these repository permissions:
   - **Contents: Read and write** (list and delete branches, compare);
   - **Pull requests: Read-only** (list pull requests);
   - **Metadata: Read-only** (granted automatically).

   Grant no other permissions.
4. In dlworrell/AEMS, open **Settings → Environments → ruleset-admin** and
   add the environment secret `BRANCH_CLEANUP_TOKEN`. Do not also store it
   as a repository secret.
5. Revoke the token after the run.

The workflow's own `GITHUB_TOKEN` has `contents: read` only. Workflow inputs
reach the script through environment variables and are never interpolated
into the shell script. The cleanup token is passed to a single step through
the environment. It is never placed on a command line or echoed, request
errors are redacted, and the client sends requests only to
`https://api.github.com`, including pagination links.

## Operating procedure

1. Create the token and environment secret as above.
2. Dispatch the workflow from `main` with `dry_run: true`, a pinned
   `catylist_ref`, and the intended `repos` and `keep` values. Approve the
   run in the Actions UI.
3. Review the job summary or the `branch-cleanup-report` artifact. Add
   `keep` patterns for anything that must survive.
4. Dispatch again with the same inputs and `dry_run: false`. Approve the
   run.
5. Review the post-deletion branch lists in the report, then revoke the
   token.
