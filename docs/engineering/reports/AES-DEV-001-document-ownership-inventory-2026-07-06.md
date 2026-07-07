# AES-DEV-001 Document Ownership Inventory

Date: 2026-07-06
Owner: AEMS
Status: Initial inventory
Related standard: `AES-DEV-001`
Related plan: `docs/engineering/AES-DEV-001-documentation-migration-plan.md`

## Purpose

This inventory records document ownership decisions before any further documentation migration.

It is intentionally conservative. A document should move only when its governing authority is clear. This report does not move files and does not authorize deleting source material.

## Inventory Status

This is a seed inventory based on the corrected Catalyst tree, AES-DEV-001 evidence reports, known governance documents, and local profiles created during the AES-DEV-001 ratchet.

It is not yet a complete filesystem crawl of every Markdown file in every repository.

## Classification Values

| Classification | Meaning |
|---|---|
| `ALREADY-CORRECT` | The document is already in its owning repository. |
| `CLEAR-MOVE` | The document should be moved to the named owning repository. |
| `STAY-ATARIX` | The document should remain in Atarix because it governs the Atarix system, target hardware integration, OS architecture, lineage, or local rationale. |
| `EXTERNAL-REFERENCE` | The document belongs to an external/reference repository and is not governed by Catalyst migration. |
| `REVIEW` | Ownership is not yet clear. Do not move until reviewed. |
| `DO-NOT-MOVE` | The document should remain where it is, even if referenced elsewhere. |

## Clear-Move Test

A document may be moved only when all of the following are true:

1. The document governs one Catalyst repository more than Atarix as a whole.
2. Future edits naturally belong in the destination repository.
3. Moving the document improves ownership clarity rather than merely satisfying a scanner.
4. The document is current enough to preserve.
5. The destination is a Catalyst project-owned repository, not an external/reference repository.

## Authority Matrix

| Governing subject | Owning repository |
|---|---|
| Catalyst program umbrella, repository tree, program governance | `dlworrell/Catylist` |
| Ecosystem engineering standards and reusable engineering doctrine | `dlworrell/AES` |
| Project management, assessment, reporting, manifests, scanners, CI, enforcement | `dlworrell/AEMS` |
| Atarix OS, target hardware integration, OS architecture, board-reference, lineage, system rationale | `dlworrell/atarix` |
| EDT behavior, document formats, commands, generated output, validation strategy, toolkit architecture | `dlworrell/engineering-docs-toolkit` |
| Repository layout, default files, shared templates, default policies, Catalyst repo bootstrap | `dlworrell/repo_templates` |
| Herkules EDT validation project and expected generated deliverables | `dlworrell/herkules-1934-english` |
| Experimental code, test harnesses, exploratory algorithms, temporary engineering investigations | `dlworrell/code-noodling` |
| External/reference material used for ideas, lineage, compatibility research, or borrowed implementation patterns | owning external/reference repository; no Catalyst migration |

## Known Document Inventory

| Current repository | Current path or family | Proposed owner | Classification | Confidence | Rationale |
|---|---|---|---|---:|---|
| `dlworrell/AEMS` | `docs/engineering/AES-DEV-001-documentation-migration-plan.md` | `dlworrell/AEMS` | `ALREADY-CORRECT` | High | Governs migration workflow, ownership assessment, and AEMS-managed evidence process. |
| `dlworrell/AEMS` | `docs/engineering/AES-DEV-001-enforcement-plan.md` | `dlworrell/AEMS` | `ALREADY-CORRECT` | High | Governs AEMS enforcement/reporting behavior for AES-DEV-001. |
| `dlworrell/AEMS` | `docs/engineering/reports/AES-DEV-001-*.md` | `dlworrell/AEMS` | `ALREADY-CORRECT` | High | Evidence reports are AEMS-managed assessment artifacts. |
| `dlworrell/AEMS` | `config/aes-dev-001-repositories.json` | `dlworrell/AEMS` | `ALREADY-CORRECT` | High | Manifest is AEMS enforcement and reporting configuration. |
| `dlworrell/AEMS` | `scripts/aes_dev_001_scan.py` | `dlworrell/AEMS` | `ALREADY-CORRECT` | High | Scanner implementation belongs to AEMS. |
| `dlworrell/AEMS` | `scripts/aes_dev_001_aggregate.py` | `dlworrell/AEMS` | `ALREADY-CORRECT` | High | Aggregate scanner implementation belongs to AEMS. |
| `dlworrell/AEMS` | `.github/workflows/aes-dev-001-scan.yml` | `dlworrell/AEMS` | `ALREADY-CORRECT` | High | Workflow executes AEMS evidence reporting. |
| `dlworrell/AES` | `standards/AES-DEV-001-development-principles-and-check-in-discipline.md` | `dlworrell/AES` | `ALREADY-CORRECT` | High | Ecosystem engineering standard. |
| `dlworrell/AES` | `docs/engineering/AES-DEV-001-development-principles.md` | `dlworrell/AES` | `ALREADY-CORRECT` | High | AES local inheritance profile for the standards repository. |
| `dlworrell/Catylist` | `docs/engineering/AES-DEV-001-development-principles.md` | `dlworrell/Catylist` | `ALREADY-CORRECT` | High | Catylist local inheritance profile for program governance. |
| `dlworrell/Catylist` | `docs/adr/README.md` | `dlworrell/Catylist` | `ALREADY-CORRECT` | High | Catylist program-governance ADR index. |
| `dlworrell/Catylist` | `docs/adr/ADR-0001-catalyst-repository-tree.md` | `dlworrell/Catylist` | `ALREADY-CORRECT` | High | Records Catalyst repository ownership and external/reference classification. |
| `dlworrell/AEMS` | `docs/engineering/AES-DEV-001-development-principles.md` | `dlworrell/AEMS` | `ALREADY-CORRECT` | High | AEMS local inheritance profile for enforcement/reporting work. |
| `dlworrell/atarix` | `docs/engineering/ATARIX-DEV-001-development-principles.md` | `dlworrell/atarix` | `ALREADY-CORRECT` | High | Atarix-local development principles and system engineering profile. |
| `dlworrell/engineering-docs-toolkit` | `docs/engineering/AES-DEV-001-development-principles.md` | `dlworrell/engineering-docs-toolkit` | `ALREADY-CORRECT` | High | EDT local inheritance profile. |
| `dlworrell/repo_templates` | `docs/engineering/AES-DEV-001-development-principles.md` | `dlworrell/repo_templates` | `ALREADY-CORRECT` | High | repo_templates local inheritance profile. |
| `dlworrell/atarix` | Atarix architecture, discovery, mailbox, DMA, fabric, supervisor, ring/capability, OS/hardware integration documents | `dlworrell/atarix` | `STAY-ATARIX` | High | These govern the Atarix machine or its OS-level architecture. |
| `dlworrell/atarix` | ULX3S, Vega816, 65x02, BB816-MATX-PCIE support/reference/lineage material used by Atarix | `dlworrell/atarix` | `STAY-ATARIX` | High | Reference material remains Atarix-local when it supports Atarix design or lineage. |
| `dlworrell/repo_templates` | `shared/docs/`, `shared/config/`, repository layout/default policy material | `dlworrell/repo_templates` | `ALREADY-CORRECT` | Medium | These appear to govern template behavior; audit before moving any related documents from elsewhere. |
| `dlworrell/engineering-docs-toolkit` | EDT command, format, validation, generated-output, and toolkit architecture material | `dlworrell/engineering-docs-toolkit` | `ALREADY-CORRECT` | Medium | These belong to EDT when they describe toolkit behavior. Full file inventory still needed. |
| `dlworrell/herkules-1934-english` | Herkules build-book validation documents and expected EDT output | `dlworrell/herkules-1934-english` | `ALREADY-CORRECT` | Medium | These belong to Herkules when they validate EDT output or govern the Herkules project itself. |
| `dlworrell/code-noodling` | Experimental notes, test harness notes, exploratory code documents | `dlworrell/code-noodling` | `ALREADY-CORRECT` | Medium | These belong to code-noodling when they are experimental or temporary investigations. |
| `dlworrell/cglm` | Any upstream or reference documentation | external/reference owner | `EXTERNAL-REFERENCE` | High | Not a Catalyst migration target. |
| `dlworrell/CLK` | Any upstream or reference documentation | external/reference owner | `EXTERNAL-REFERENCE` | High | Not a Catalyst migration target. |
| `dlworrell/65x02` | Any upstream or reference documentation | external/reference owner | `EXTERNAL-REFERENCE` | High | Not a Catalyst migration target. |
| `dlworrell/BB816-MATX-PCIE` | Any upstream or reference documentation | external/reference owner | `EXTERNAL-REFERENCE` | High | Not a Catalyst migration target. |
| `dlworrell/ulx3s` | Any upstream or reference documentation | external/reference owner | `EXTERNAL-REFERENCE` | High | Not a Catalyst migration target. |
| `dlworrell/Vega816` | Any upstream or reference documentation | external/reference owner | `EXTERNAL-REFERENCE` | High | Not a Catalyst migration target. |

## Initial Clear-Move Set

No documents are approved for immediate movement by this initial inventory.

The current evidence work created missing local profiles, reports, and ADRs in their correct owning repositories rather than moving existing documents blindly.

## Review Queue

The next audit should inspect existing documents in this order:

1. `dlworrell/atarix/docs/` for any document that governs Catalyst, AES, AEMS, EDT, repo templates, Herkules, or code-noodling more than it governs Atarix.
2. `dlworrell/repo_templates/` for documents that define repository layout or shared defaults.
3. `dlworrell/engineering-docs-toolkit/` for EDT-specific behavior and validation documents.
4. `dlworrell/herkules-1934-english/` for EDT validation material.
5. `dlworrell/code-noodling/` for experimental material that should remain explicitly non-governing.

## Migration Procedure

For each future `CLEAR-MOVE` document:

1. Move one logical document or document family per commit.
2. Preserve a provenance block in the destination.
3. Leave a forwarding note or source index entry when needed.
4. Do not delete the source document until the forwarding trail is clear.
5. Update AEMS manifest or reports only when ownership semantics change.

Suggested provenance block:

```text
Migrated-from: <source-repo>:<source-path>
Migrated-to: <destination-repo>:<destination-path>
Migration-date: YYYY-MM-DD
Reason: AES-DEV-001 repository-local documentation ownership
```

## Decision

Do not move documents yet.

Proceed with targeted repository audits and mark only high-confidence documents as `CLEAR-MOVE` before any file movement occurs.
