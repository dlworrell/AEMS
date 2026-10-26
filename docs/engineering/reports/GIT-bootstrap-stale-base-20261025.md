# AEMS signing bootstrap: stale-base incident and recovery

Incident date: 2026-10-25 (Pacific). Technical event timestamps below are UTC.
Method: Git Workflow Master prompt, stateful controlled replay, negative-case
regression tests, and exact-object GitHub evidence. AI-assisted work by ChatGPT
for Donovan Worrell; no independent or human review is asserted.

## Observation and causal sequence

The supplied traceback is [run 40242417804, attempt 3](https://github.com/dlworrell/AEMS/actions/runs/40242417804/attempts/3),
job `121329918937`, at 2026-10-25T23:53:53Z. Its immutable workflow source is
[`b53d797b9a7c4decf1ec48e6dc5776cd3acb1e67`](https://github.com/dlworrell/AEMS/blob/b53d797b9a7c4decf1ec48e6dc5776cd3acb1e67/.github/workflows/pr-signature-preflight-bootstrap.yml).
The payload SHA-256 is
`1264e9997ecec9ef1e7de3a4aa4ca8b7fb299c5ebdad9007c0120ec9ebb365b8`;
its base is `2901c715651a10c700d0c7c3cbd683c86c748170` and proposed tree is
`03a9015a7cc0fd08a2a2e792e87bb99caae34af1`.

1. Attempt 1, job `121316857751`, failed at 22:55:40Z with the generic
   `GraphQL commit creation failed` error, after creating the signing ref.
   The original logger discarded GraphQL error details. Its precise API cause
   is not established; permissions and workflow-file restrictions are not
   presented as confirmed diagnoses.
2. A different, narrower publication delivered four files through
   [PR #36](https://github.com/dlworrell/AEMS/pull/36), merged at 22:58:05Z.
   Its verified head is `bd440a238d16de98475a50ffc1c4ea1aebc33785`, its single
   parent is `7eb3292dac8cecdd3d665bbdfbad54385cb204a3`, its tree is
   `16a53d0e51e9f54182423b77f5c2ca1858f94f79`, and its merge is
   `4873b770f8499ed4233261e56f5496b3522ecb77`.
3. PR #37 subsequently advanced the default to
   `8bbbe33e23c971615b78ecaead13736db296c266` at 23:03:50Z. Attempts 2 and 3
   reused the earlier payload and correctly failed its default-base guard.
   The supplied failure happens before any branch/commit mutation in that
   attempt. Repeating it cannot refresh the immutable payload.
4. At this investigation's inspected default,
   `9fe3e55a2823c10086f7dc0eabc9cee175f15aba`, the obsolete signing branch
   `signing/pr-signature-preflight-v2-20261025` still points to its original
   base. It is an unfinished publication, not the verified PR #36 head.

The five-file original payload was **not** delivered unchanged. Its action,
runbook, scanner and regression-test blobs match PR #36 and the inspected
default. Its proposed `.github/workflows/pr-signatures.yml` is absent from both
that PR and this default. PR #36 explicitly kept caller enrollment under
Catylist #23 and used [separate hosted validation](https://github.com/dlworrell/AEMS/actions/runs/40242543684).
This repair does not silently install that omitted workflow or call it complete.

## Hypotheses and falsifiable predictions

H1: The supplied failure is payload/base staleness, not a Python import or
signing-key failure. Prediction: executing the original script against a moved
default produces the same exception before any mutating API call.

H2: Reusing a fresh but empty signing branch fails for a separate reason.
Prediction: the original unconditionally posts the ref and receives HTTP 422;
a publisher that inspects the existing ref can resume at the unchanged base.

H3: A complete verified artifact can be recognized without replaying it.
Prediction: an exact signed tree and single reviewed parent can return
`already_published` after default movement, with zero mutating requests.
An unsigned, altered or differently parented head must still fail.

## Controlled experiment: before and after

The original inline Python was extracted from the immutable workflow and
executed unchanged with its HTTP boundary replaced by a stateful API double.
Both versions received identical synthetic object IDs, payload contents,
environment and repository states. The positive control was also executed.
Synthetic GitHub signature records exercise decision logic; they are not
cryptographic or live-host evidence. Results are retained in the
[machine record](GIT-bootstrap-stale-base-20261025.json).

| Controlled state | Original result | Repaired result | Original / repaired mutating requests |
|---|---|---|---:|
| Fresh base; missing signing branch | Published | Published and verified | 2 / 2 |
| Moved default; empty signing branch | Same `Default branch moved` exception as supplied | Refused with expected/observed SHAs and re-preparation instructions | 0 / 0 |
| Fresh base; existing empty signing branch | HTTP 422 creating an existing ref | Resumed; published and verified | 1 failed / 1 successful |
| Moved default; complete exact verified signing head | Stale-base exception | `already_published`, read only | 0 / 0 |
| Moved default; exact merged PR whose signing branch was deleted | Stale-base exception | Exact merged-PR/head verification, then `already_published` | 0 / 0 |

All three predictions held; the fifth case was added after the live post-merge
experiment below exposed branch deletion. Stale payload rejection is retained because it
protects reviewed tree/base identity. The operational repair is to reconstruct
the still-needed delta on the latest inspected default and recompute its tree
and SHA-256, then execute the maintained publisher in a new workflow run.

## Implemented correction and validation

`scripts/publish_reviewed_repair.py` validates payload and execution context
before network access, inspects existing refs, resumes only an empty branch at
the reviewed base, and accepts an existing completed artifact only after exact
commit/tree/parent/signature checks and a final signing-ref reread. New
publication retains the feature-head lease and checks default freshness again
immediately before commit creation. GraphQL errors retain bounded type/message
diagnostics. It never changes a protected default, signing key or ruleset.

Local focused validation: **35 tests passed** — 22 new publisher tests and the
13 existing PR-signature tests. The existing source/test files were matched by
Git blob SHA to the inspected default before execution. Cases include stale
missing/empty branches, concurrent ref creation, head changes, default movement
between checks, payload/file tampering, wrong ancestry/tree/identity, unverified
or missing signature evidence, permission errors, unsafe context and paths.
This is the focused suite, not an assertion that every AEMS test was run.

Hosted acceptance for the superseding workflow runs the same 35 tests before
publication, then invokes the exact publisher twice: the second invocation
must report `already_published` for the same verified commit. Its signed branch
starts at the freshly inspected default and excludes bootstrap ancestry.
The resulting PR and workflow retain the exact payload/tree/parent/run mapping;
publication is not human approval or architectural acceptance.

## Live post-merge experiment and second correction

[PR #42](https://github.com/dlworrell/AEMS/pull/42) delivered the first repair
and merged at 2026-10-26T04:59:20Z. Its signed head was
`fbc4837f9c885b612d149cc5d31b0936b102e7ee`; the verified merge
`85b5e1d26d6dfc9a9bb06015234d1110be138d58` has tree
`332d5f4fe5b0231ff24f56582977047fc4cdb2ff` and parents consisting of the old
default `9fe3e55a2823c10086f7dc0eabc9cee175f15aba` plus that head.
In [run 40271707114, attempt 1](https://github.com/dlworrell/AEMS/actions/runs/40271707114/attempts/1),
35 tests passed, publication succeeded and the immediate second invocation
returned `already_published` for the same commit.

The deliberate [post-merge rerun, attempt 2](https://github.com/dlworrell/AEMS/actions/runs/40271707114/attempts/2),
job `121406277225`, then **failed** at 05:00:05Z. GitHub had deleted the
temporary signing branch after merge. The first repair saw a missing branch
and an advanced default, and could not distinguish merged work from incomplete
work. This is a discovered gap in the first repair, not a passing test.

The second correction performs a read-only, paginated closed-PR lookup when
the ref is missing and the default moved. An actually merged PR must match the
same repository, head and base refs; its immutable head must independently
match the reviewed tree, single parent, commit identity and valid signature.
The signing ref is reread and must remain absent. The result retains
`already_published` and adds the completion PR number. No merged evidence means
the original stale-base refusal remains. A closed unmerged PR is insufficient.

Six additional regression cases cover deleted merged refs, wrong/unmerged PR
metadata, unsigned/altered artifacts, branch recreation during verification,
unavailable API evidence and pagination. Final focused local validation is
**41 passed**: 28 publisher tests plus the 13 existing signature tests. The
updated hosted workflow requires those 41 tests, a fresh signed publication and
an identical read-only repeat. After merging that correction, the same workflow
is rerun against the advanced default and deleted branch to validate this live
condition. Exact hosted and final merge results are retained in the correction
PR and the user-facing completion report.

## Recovery and limits

Use the new push-triggered run, not another rerun of run 40242417804. GitHub
reruns retain the original workflow SHA/ref; historical failed attempts remain
valid evidence. For a later stale-base refusal, re-read and reconstruct the
reviewed delta rather than editing just its base SHA or removing the guard.

The original first-attempt GraphQL cause remains unknown because its response
was not logged. The original five-file payload remains superseded, not
retroactively successful. Downstream caller rollout and release qualification
remain separately tracked. Default and feature refs are not locked in a single
cross-ref transaction; later default movement still requires normal PR review.

Rollback is a reviewed revert of this change. Preserve existing signed/default
history and the original failure logs; never merge an unsigned bootstrap ref.

Authority: [Catylist ADR-0006](https://github.com/dlworrell/Catylist/blob/7a1ede0bb073477be226aa572fc3c20db3312df1/docs/adr/ADR-0006-default-branch-protection-and-signed-commits.md),
[AES-DEV-001](https://github.com/dlworrell/AES/blob/2a29348533bbc29f9e645c45316bcce33d75ae0c/standards/AES-DEV-001-development-principles-and-check-in-discipline.md).
Platform sources: [rerun semantics](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/re-run-workflows-and-jobs)
and [GitHub commit mutation](https://docs.github.com/en/graphql/reference/commits).
