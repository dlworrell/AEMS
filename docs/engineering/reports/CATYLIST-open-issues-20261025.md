# Catylist open-issue remediation and evidence record

Observed 2026-10-25. Initial scope: 11 open issues in dlworrell/Catylist.
This record applies the actual issue acceptance criteria; unrelated successful
runs, nearby datasets and proposed documents do not substitute for missing
required evidence. Work is AI-assisted and self-reviewed, not independent
human certification.

## Prompt selection and evidence method

The Dropbox `/prompt` index and prompt contents were read. PRM-0030 supplied
acceptance-case comparison; PRM-0068 supplied missing-data classification and
the next discriminating check. PRM-0005 was the specific AEMS scoped-scan
implementation prompt. PRM-0029 supplied bounded feature implementation;
PRM-0004 describes the remaining project separation under #28, subordinate to
current ADR-0004 and its one-scope-per-PR migration order. Historical prompt
instructions do not supersede newer accepted governance or authorize human
sign-off. No source data, review approval or qualification has been invented.

The closest verified sources are the current accepted Catylist records and
inventory, exact owning-repository source commits, authenticated ruleset state,
and actual workflow logs/artifacts for those commits. Their sufficiency is
claim-specific: the ruleset evidence closes #22, while a similar-looking
manifest or a green unrelated workflow cannot close #18/#23/#27.

## Acceptance cases

| Issue | Result | Evidence and remaining discriminator |
|---|---|---|
| #14 parent management tracker | OPEN | Child composition remains incomplete; closing two children does not close the parent. |
| #18 desired inventory / manifest back-pointer | EXPECTATION_UNKNOWN | v1 inventory lacks the desired-state contract; AES-003 explicitly leaves the back-pointer undefined. [Concrete owning-authority proposal](../proposals/AES-003-governance-back-pointer-20261025.md) prepared; acceptance and validated migration remain required. |
| #19 organization placement | EXPECTATION_UNKNOWN | No accepted placement ADR observed. [Concrete retain-current-placement proposal](../proposals/CATYLIST-19-organization-placement-20261025.md) prepared; no transfer or product-plan assumption made. |
| #22 ruleset implementation / rollout | MATCH — CLOSED | Existing pinned applier, real sandbox/live rollout logs, and current comparison of all 17 protected repositories: zero drift. [Evidence](CATYLIST-22-ruleset-closure-20261025.md). |
| #23 conformance workflow / drift management | DIVERGENCE | No complete per-repository conformance rollout observed. Depends on accepted #18 oracle, pinned validator, all-PR-commit signature checks, read-only scheduled audit, and tested issue idempotence/closure. |
| #24 AEMS scoped scanner | LOCAL MATCH; DOWNSTREAM NOT RUN | [AEMS PR #31](https://github.com/dlworrell/AEMS/pull/31) merged at `8eeb8a03e53e2f3e1e5dc23dc1ff87c456f853bc`; 159 tests and successful PR CI. [Nine-file code-noodling adoption patch](../proposals/code-noodling-scope-adoption-20261025.patch) passes locally, conserves all 22 dispositions, and requires target personal sign-off plus downstream CI. Issue stays open. |
| #26 scope and agent templates | MATCH — CLOSED | [repo_templates PR #11](https://github.com/dlworrell/repo_templates/pull/11) merged at `f9e3f20efdf47daf7536759c3028acda38496303`; 32 tests, five successful PR workflows and 13 verified commits. |
| #27 ecosystem P0 remediation | DIVERGENCE | [17-repository census](CATYLIST-27-source-census-20261025.md): seven root manifests, ten missing. EVO unsigned automation repaired in [PR #129](https://github.com/dlworrell/evo/pull/129), merged after 18 successful PR workflows. Manifest/back-pointer and scope readiness remain. |
| #28 remaining code-noodling migration | DIVERGENCE | Crypto and election declarations/earlier election audit repairs exist. Prime and dice still share a scope tree, and their separate migration/CI/evidence/dependency record remains to be implemented one scope per PR. Existing source data is preserved. |
| #29 signing from every used client | EXPECTATION_UNKNOWN | Working Copy is retired by user direction. Signed browser commits and signed sandbox PR #2 are observed; a maintainer phone-origin commit proof is not. Do not generate/register new keys, restore Working Copy, or equate a desktop/browser commit with unobserved phone evidence. |
| #34 ATARIX SQLite evidence index | EXPECTATION_UNKNOWN | Correct project-local authority and [testable review/ADR proposal](../proposals/ATARIX-SQLite-evidence-index-20261025.md) prepared from current ATARIX/AES records and primary SQLite/Python documentation. Owning ADR acceptance and implementation evidence have not been observed. |

## Completed implementation validation

Scope scanning preserves default behavior: the original scanner at
`a1f3d5c6be8f39f4b752d6eafc2c4ff0028285b5` and the updated scanner produced
identical existing report fields on AEMS and code-noodling. Added tests execute
scope/exclusion CLI paths, the composite shell action, workflow path/config
selection, legacy/scope ledgers, source-drift and ambiguity refusals, history
conservation, aggregate adoption and applicability contradictions. The strict
AEMS self-scan passes. No scope finding's approval metadata was regenerated.

The prepared code-noodling adoption rekeys 19 crypto dispositions to local
identities, leaves three prime-source dispositions in the root remainder,
retains an exact identity/count migration map, pins the AEMS engine and tests
coverage/election non-native applicability separately. Both strict ratchets and
the combined aggregate pass locally with zero new, unresolved or stale
findings. The nine-file patch is an atomic target-PR proposal; it has not been
merged or presented as downstream CI evidence.

EVO's retained manual Project Zero workflow now uses the unchanged canonical
verified-commit helper instead of local unsigned commit/push. Its 15 helper
tests, self-test guard, and all 18 PR workflows passed. This does not rerun or
reclassify EVO's previously completed onboarding.

## Concrete blocked action

Catylist and code-noodling's GitHub upload forms require **Sign off and commit
changes** as the maintainer. ADR-0007 states: "AI agents may author changes;
they may not grant licenses, approve their own work, or sign as a human."
These personal sign-offs have not been supplied by the agent. The prepared
[Catylist closure patch](../proposals/Catylist-ruleset-closure-20261025.patch)
and code-noodling adoption patch expose the exact proposed content for review.
No protection was disabled and no unsigned route was substituted.

## Next executable order

1. Record maintainer dispositions for the concrete AES/Catylist back-pointer,
   placement and ATARIX local-storage proposals in their owning repositories.
2. Personally sign off the prepared Catylist/code-noodling target changes;
   complete signed PR publication and downstream CI before closing #24.
3. Migrate prime/dice separately under ADR-0004/PRM-0004, keeping program
   behavior, optional prime-seed data interface and hardware limitations
   explicit; then evaluate #28 against actual CI.
4. Migrate the ten missing manifests and remaining desired-state records
   against the accepted #18 schema and verified repo-local lifecycle/evidence.
5. Implement and qualify #23's pinned read-only conformance engine and
   scheduled drift-issue lifecycle, roll it out to all 17 repositories, then
   complete #27 and reevaluate parent #14.

Nine issues remain open. This is the observed state, not a claim of zero
outstanding audit issues or general production readiness.
