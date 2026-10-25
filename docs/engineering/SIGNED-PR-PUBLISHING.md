# Signed PR publication and repair

Implements the existing signed-commit obligation in Catylist ADR-0006 and
AES-DEV-001. This runbook does not add an approval threshold or a new signing key.

## Publish a change

Use the verified Project Zero publisher in `repo_templates/tools/project_zero_commit.py`
at reviewed commit `3f26587d7f3f84df0c2a510cd2d1cae4c2d25af7`, or the equivalent
reviewed publisher already installed in the owning repository. It uses GitHub
GraphQL `createCommitOnBranch`, then checks the returned commit's GitHub
verification and exact expected parent before reporting success. Retain the
AI-assistance trailer and do not claim independent human authorship or review.

Raw Git Database and Contents connector writes have produced unsigned commits.
Treat them as staging only until independent GitHub verification succeeds. Do
not publish another review PR and send its maintainer to configure a signing
client to repair agent-generated unsigned history.

1. Read the latest base and approved changes; record exact paths and contents.
2. Create a separate branch from the inspected base and use the verified publisher.
3. Check every commit introduced by the PR, not just its tip. Reject missing or
   unverified signature evidence before handing the PR to the maintainer.
4. Open the PR, run its normal checks, and bind review evidence to its exact head.
5. Merge with the expected head and the existing merge-commit-only protection.
6. Verify the resulting merge commit and update the source-linked project record.

The workflow token signs as automation. A human review or `Signed-off-by` trailer
is a separate record; neither can add a cryptographic signature to an old commit.
No desktop or Working Copy setup is a prerequisite for cloud publication or iOS review.

## Repair an existing unsigned PR

Preserve the old feature head under an archive ref. Reconstruct the exact
reviewed file changes on the current inspected base using a verified publisher.
Verify the resulting complete tree equals the reviewed tree (or explicitly
review any base-change delta), and verify the parent and GitHub signature.
Replace only the feature ref using an expected-head lease. Keep the same PR,
retain the old/new SHA and tree mapping, and rerun checks. Never rewrite default
history, append a signed tip over unsigned ancestors, or disable signature protection.

## Reusable read-only preflight

`scripts/pr_signatures.py` reads the PR before and after paginated commit
enumeration. The requested immutable head, declared commit count, unique commit
identities and every GitHub verification record must agree. Missing pages,
API errors, missing evidence or a moved head are `indeterminate`; an unverified
commit is a `violation`. Only complete matching evidence yields `pass`.

Run it with an authorized read-only token:

```sh
python3 scripts/pr_signatures.py --repository OWNER/REPO --pr NUMBER \
  --expected-head FULL_SHA --output build/pr-signatures.json
```

The composite action `.github/actions/pr-signatures` packages the same check.
Downstream workflows must pin it to the verified commit that delivers this
change. Use `pull_request`, a standard hosted Ubuntu runner, `contents: read`
and `pull-requests: read`; pass the event's exact `head.sha`. No PR checkout,
PR script execution, signing permission, administration secret or self-hosted
runner is needed. This check is diagnostic until an owning-repository rollout
records its actual check name and required-check transition. Native signature
protection remains the merge boundary throughout.

A passing signature check does not prove functional correctness, security,
review approval, standards conformance, or complete merge readiness.

## Observed repair on 2026-10-25

| PR | Unsigned head | Verified identical-tree replacement |
|---|---|---|
| Catylist #39 | `87a6f3891103bfbb85b5c69b5389155d76d55b11` | `3131a3846bab4b6d5dd794e3983a9d2d33135d5f` |
| AEMS #35 | `55dea7cdfd281c9fa6e598d383d1e07ea083dbae` | `a9aa7dbd4d591dadceb6a478f588361be6ed6269` |

Each replacement has one inspected base parent. Both GitHub verification records
are `verified: true`, `reason: valid`. Full tree identities are respectively
`3fe8e8d8699b909d1af699ff2cfc60c9cb28b25a` and
`58713f155ad8951604279597345089f3641895a0`. Rulesets and existing default history
were preserved. This evidence does not establish phone-origin commit signing.

Sources: [GitHub signed mutation](https://docs.github.com/en/graphql/reference/commits),
[Catylist ADR-0006](https://github.com/dlworrell/Catylist/blob/7a1ede0bb073477be226aa572fc3c20db3312df1/docs/adr/ADR-0006-default-branch-protection-and-signed-commits.md),
[canonical publisher](https://github.com/dlworrell/repo_templates/blob/3f26587d7f3f84df0c2a510cd2d1cae4c2d25af7/tools/project_zero_commit.py).
