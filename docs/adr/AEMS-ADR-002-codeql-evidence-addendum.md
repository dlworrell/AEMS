# AEMS-ADR-002: CodeQL Evidence Addendum

Stable draft ID: DRAFT-AEMS-002-CODEQL-ADDENDUM
Date: 2026-10-25
AI-assisted drafting: ChatGPT; no independent review asserted.
Status: Accepted addendum; the unfiled base AEMS-ADR-002 remains Proposed
Decision authority: Donovan Worrell
Implementation qualification: Open; CQL-A01–08 evidence remains required
Owner: AEMS
Target: docs/adr/AEMS-ADR-002-development-adapter-contract.md, when the owning proposal is reconciled and filed.
Source: CONSOLIDATED-ADRS.md version 6, AEMS-ADR-002 v0.2.0, particularly §§2.2, 2.4, 2.8 and recovery reconciliation.
Dependencies: accepted Catylist ADR-0007; Catylist ADR-0009 for CodeQL governance; repository-specific mandatory promotion remains separate; applicable adopted AES requirements. Unaccepted sibling proposals do not become policy through this addendum.

## Context
The existing proposal already covers independent exact-subject evaluation. The CodeQL guide exposes a specific unresolved boundary: a database's supplied commit SHA is caller-asserted, while database construction may execute untrusted build code. Extend the existing contract instead of building another evidence gate.

## Accepted additions; implementation qualification open
### Extend §2.2 — Extraction and evaluation provenance
Record repository and governed scope; exact requested commit and checked-out tree; clean/dirty state; submodule/generated-source identities where applicable; database/extraction identity or retained digest manifest; complete extraction commands, build flags, compiler/SDK/OS and container/runner image identity; completion and source coverage/exclusions; raw log and report hashes. Declare unavailable dimensions explicitly.

Bind the extraction and analysis producer identities and workflow revisions to those inputs. Treat a database plus a claimed SHA as unverified until independently corroborated. Do not trust an uploaded PR artifact merely because its filename or embedded label names the expected commit.

### Extend §2.4 — Result distinctions and compatibility
Preserve the current reporting envelope and NOT_ESTABLISHED standards-compliance claim. Add versioned provenance and review references through a documented schema evolution/migration, rather than silently changing meanings of existing fields or exit codes.
Represent extraction completion, analysis completion, finding disposition, complementary evidence and gate authorization separately. Adapter-specific outcomes map explicitly to pass/violation/indeterminate at a qualified gate; failed extraction or incomplete mandatory coverage cannot map to pass.
Reuse current AEMS reporting and issue-graph producers. Any index or Notion publication is a derived projection with canonical source links, stable IDs and idempotent updates.

### Extend §2.8 — Untrusted artifacts and trusted signing
Independently validate subject, policy lock, artifacts, producer workflow identity, event/trigger, permissions and signer authorization before accepting trusted evidence. Artifact integrity and a valid signature are necessary evidence components, not proof that a privileged workflow safely produced them.
Keep execution of PR build code isolated from trusted attestation signing and ruleset administration. A trusted follow-on job must not execute scripts extracted from an untrusted artifact. Bound artifact parsing, paths, sizes and resource use.

## Acceptance additions to §4
| ID | Expected evidence |
|---|---|
| CQL-A01 | Matching checkout/extraction/analysis produces correlated exact-subject evidence with all required provenance fields |
| CQL-A02 | Database from commit A relabeled as B fails provenance validation |
| CQL-A03 | Trusted evaluator ignores a PR-supplied replacement validator; modified evaluator lock requires requalification |
| CQL-A04 | Altered report/artifact fails integrity verification; wrong producer workflow and wrong trigger fail separate tests |
| CQL-A05 | Real fork PR produces only permitted unprivileged reporting; signing/admin credentials remain unavailable |
| CQL-A06 | Partial/skipped language, failed extraction, malformed SARIF and timeout remain explicit nonpassing required outcomes |
| CQL-A07 | Resolved suites include intended custom and pinned upstream queries; existing positive/negative and plain/fortified fixtures still pass |
| CQL-A08 | Current evidence readers remain compatible or fail with an explicit schema-version/migration diagnostic; no false compliance upgrade |

Retain exact revisions, expected and observed outcomes and raw logs. No passing result is asserted here.

## Alternatives, consequences and rollback
Keeping only caller assertions is simpler but leaves provenance unverified. Building a second gate duplicates the accepted architecture. The accepted direction is to extend the existing versioned contract; it adds schema and isolation work while preserving one engine and one evidence lineage.
Introduce changes in report-only mode. Preserve historical envelopes and verification tools. Roll back a defective producer through a reviewed version pin; never relabel old evidence as newly verified.


## Source and filing status

The base AEMS-ADR-002 is a proposal in [CONSOLIDATED-ADRS.md, Library version 6](https://chatgpt.com/library?file_id=libfile_7e4f98747cd88191b133682189c4c069&account_id=personal), mirrored in the [decision record](https://app.notion.com/p/402ae4dd715381a696a7d1eeb6248445). It is not present in AEMS main at dac93871987b3234743854cc39c8b3dc89009a4d. This separately reviewable addendum preserves that existing decision identity; it does not invent an accepted base record. Incorporate it into the base proposal when that proposal is filed and reconciled. Acceptance of this addendum alone cannot accept its base or change upstream policy.

The [review package](https://chatgpt.com/library?file_id=libfile_bf517bbea7ec8191b5de98af02721c7f&account_id=personal) retains the drafting rationale and alternatives. Current [CodeQL implementation](../engineering/AES-CodeQL.md) remains report-only. The [current audit census](../engineering/reports/CATYLIST-27-source-census-20261025.md) records later scope-scanning delivery and remaining onboarding gaps; this addendum does not restart completed work or claim those gaps are closed.

Formal approval must identify the exact reviewed revision and record the maintainer's acceptance or requested revisions. The CQL-A tests above define required qualification evidence; no results are asserted by this publication.



## Maintainer acceptance of this addendum — 2026-10-25

Donovan Worrell reported approval of the review PRs and directed repair of their merge blockers. This records acceptance of the bounded CodeQL evidence additions and CQL-A01–08 criteria reviewed in PR #35 at `55dea7cdfd281c9fa6e598d383d1e07ea083dbae`, republished with the identical complete tree as verified `a9aa7dbd4d591dadceb6a478f588361be6ed6269` and merged at `2901c715651a10c700d0c7c3cbd683c86c748170`.

Acceptance is effective when this signed record merges and is limited to this addendum. The unfiled base AEMS-ADR-002 remains Proposed and must still be reconciled. No sibling proposal, implementation, required-check rollout or test outcome is accepted by implication. Current CodeQL operation remains report-only until its separate qualification and promotion succeed. AI preparation of this record does not assert independent human review or substitute a machine signature for the maintainer's review decision.
