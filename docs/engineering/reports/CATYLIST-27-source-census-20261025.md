# Catylist #27: current remediation source census

Observed 2026-10-25 against Catylist inventory
`7a1ede0bb073477be226aa572fc3c20db3312df1`. This is an AI-assisted authenticated
read-only census, not certification. The [machine record](CATYLIST-27-source-census-20261025.json)
contains one remediation record for each of the 17 protected inventory entries.
All 109 selected source blobs (7 manifests and 102 workflows) were hashed as
Git blobs and matched their immutable tree identities. Complete trees were retrieved;
none was truncated. Raw authenticated source, including private metadata, is
not republished here.

## Findings

- Seven repositories provide a root `aes-manifest.yaml`; their full repository
  identity and ownership agree with Catylist. Ten lack that entry point.
- Five existing manifests omit the class in the inspected field. One further
  existing manifest explicitly contradicts the authoritative class; its
  correction is prepared, with private source values omitted here. The absent
  class/back-pointer fields are unresolved contract expectations: AES-003 explicitly leaves the Catylist
  back-pointer undefined under #18. The EWT manifest now identifies EWT and is
  not the formerly copied AES identity.
- EVO's retained Project Zero workflow still creates an unsigned local bot
  commit. [EVO PR #129](https://github.com/dlworrell/evo/pull/129) replaces it
  with the unchanged canonical verified-commit helper and adds regression
  checks. It merged at `ec23d960cbf5f5271306a88442023c0107cd50ff` after all 18
  PR workflows passed, with five verified source commits. This later repair
  does not erase the captured defect or close the remaining #27 criteria.
- The inspected workflow text contains no detected direct default-branch push
  route. This is a lexical screen, not an end-to-end proof of every referenced
  helper or reusable workflow. Referenced publishing helpers and credential/
  event boundaries require separate review before a conformance claim.
- openCUDA is project-owned/experimental by the accepted CAT-DISP-002
  disposition, but lacks the root manifest and the inspected AES-SEC-001
  adoption files. Older AEMS derived inventories must not override that
  Catylist classification. Closest-looking reference/fork entries are not
  sufficient evidence of a waiver or exclusion.
- Current ruleset/settings comparison reports zero drift for all 17 entries.
  This does not repair missing manifests, define new schema fields, or provide
  scope readiness by itself.

## Remaining closure requirements

AES must define the manifest back-pointer before producers add fields or AEMS
requires them. Catylist #18 must version the desired-state inventory and record
standards/applicability, declared scope expectations and actual observed check
identities. Only then can the #23 conformance rollout compare each manifest
against an accepted oracle. A missing applicability record stays unresolved;
it must not be replaced with a convenient not-applicable assertion.

AEMS scope scanning is merged in [PR #31](https://github.com/dlworrell/AEMS/pull/31)
with 159 tests and successful CI. The prepared code-noodling adoption preserves
22 dispositions (19 crypto, 3 remainder) and passes local scope/remainder and
aggregate checks. Target-repository personal sign-off and downstream CI are
still outstanding. Prime/dice scope migration under #28 also remains open.

Historical rulesets were already applied before this full remediation census.
This record preserves that chronology; it does not retroactively claim the
original ordering requirement was satisfied or certify all protected projects.
