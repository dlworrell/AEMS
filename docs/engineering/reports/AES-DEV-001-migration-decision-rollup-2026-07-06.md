# AES-DEV-001 Migration Decision Roll-Up

Date: 2026-07-06
Owner: AEMS
Status: Initial migration decision
Related standard: `AES-DEV-001`
Related inventory: `docs/engineering/reports/AES-DEV-001-document-ownership-inventory-2026-07-06.md`
Related clean ratchet: `docs/engineering/reports/AES-DEV-001-clean-ratchet-2026-07-06.md`

## Purpose

This report closes the first AES-DEV-001 document-ownership audit loop.

It summarizes the targeted audits completed after the clean AES-DEV-001 ratchet and records the current migration decision.

## Decision

Do not move documents yet.

The current `CLEAR-MOVE` set is empty.

The evidence baseline is clean, and the first ownership audits found no high-confidence document that should be physically moved into another repository immediately.

## Completed Audit Reports

| Repository | Audit report | Clear-move set | Decision |
|---|---|---:|---|
| `dlworrell/atarix` | `docs/engineering/reports/AES-DEV-001-atarix-docs-ownership-audit-2026-07-06.md` | `0` | Keep Atarix architecture, ATX-100, system specs, hardware-reference analysis, and Atarix-local engineering evidence in Atarix. |
| `dlworrell/repo_templates` | `docs/engineering/reports/AES-DEV-001-repo-templates-ownership-audit-2026-07-06.md` | `0` | Do not move documents into or out of repo_templates yet; populate template authority paths deliberately. |
| `dlworrell/engineering-docs-toolkit` | `docs/engineering/reports/AES-DEV-001-edt-ownership-audit-2026-07-06.md` | `0` | EDT owns reusable document-engine behavior; do not absorb project-specific materials. |
| `dlworrell/herkules-1934-english` | `docs/engineering/reports/AES-DEV-001-herkules-ownership-audit-2026-07-06.md` | `0` | HERKULES owns book-project source assets, translation work, glossary, reports, and outputs. |
| `dlworrell/code-noodling` | `docs/engineering/reports/AES-DEV-001-code-noodling-ownership-audit-2026-07-06.md` | `0` | Keep experimental material local until it graduates into a reusable or production project. |

## Migration Boundary Confirmed

The first audit series confirms these ownership boundaries:

- `dlworrell/Catylist` owns Catalyst program governance and repository-tree decisions.
- `dlworrell/AES` owns ecosystem engineering standards and reusable doctrine.
- `dlworrell/AEMS` owns assessment, reporting, manifests, scanners, workflows, migration evidence, and enforcement.
- `dlworrell/atarix` owns Atarix architecture, OS, target hardware integration, ATX-100 material, system specifications, and reference-platform analysis used by Atarix.
- `dlworrell/repo_templates` owns repository layout defaults, shared templates, default policies, bootstrap conventions, and common repository structure.
- `dlworrell/engineering-docs-toolkit` owns reusable EDT document-engine behavior.
- `dlworrell/herkules-1934-english` owns the HERKULES book project, source material, translation assets, reports, and publication outputs.
- `dlworrell/code-noodling` owns exploratory experiments and temporary engineering investigations.
- External/reference repositories remain non-governed by Catalyst migration unless explicitly reclassified by Catylist ADR.

## Review Queue

The following items remain review candidates, not migration approvals:

| Item | Current owner | Possible future owner | Status | Reason |
|---|---|---|---|---|
| `dlworrell/atarix:docs/architecture/ATX-SPEC-090-Atarix-Engineering-Management-System.md` | `dlworrell/atarix` | `dlworrell/AEMS` | Review later | Current text is Atarix-specific but may inform a future generalized AEMS specification. |
| `dlworrell/atarix:docs/architecture/ATX-SPEC-091-Requirements-and-Traceability-Model.md` | `dlworrell/atarix` | `dlworrell/AEMS` | Review later | Current text is Atarix-specific but may inform reusable AEMS traceability rules. |
| `dlworrell/atarix:tools/aems/` | `dlworrell/atarix` | `dlworrell/AEMS` | Review later | Current tooling is Atarix-local; extract only after a stable reusable AEMS interface exists. |
| `dlworrell/atarix:docs/roadmap/repository-extraction-plan.md` | `dlworrell/atarix` | undecided | Review as stale | Appears superseded by the corrected Catalyst tree. Do not migrate stale material. |
| `dlworrell/herkules-1934-english:build/scripts/` | `dlworrell/herkules-1934-english` | `dlworrell/engineering-docs-toolkit` | Review later | Extract only if legacy build behavior is generalized into reusable EDT behavior. |
| `dlworrell/code-noodling` experiment documents | `dlworrell/code-noodling` | varies | Review on graduation | Promote only when an experiment becomes reusable infrastructure, formal evidence, or a production project. |

## Rules Going Forward

A document may move only when all are true:

1. The destination repository is the clear governing authority.
2. The document is current enough to preserve.
3. Future edits naturally belong in the destination repository.
4. Moving the document improves ownership clarity.
5. The destination is a Catalyst project-owned repository, not an external/reference repository.
6. Provenance is preserved in the destination.
7. A source-side forwarding note or index entry is added when needed.

## Migration Procedure

For every future migration:

1. Move one logical document or document family per commit.
2. Preserve provenance.
3. Do not delete the source until the forwarding trail is clear.
4. Update AEMS manifest or reports only when ownership semantics change.
5. Re-run the AES-DEV-001 ecosystem evidence report after meaningful ownership changes.

## Current Ratchet Position

AES-DEV-001 has a clean baseline and a completed first ownership audit series.

The next ratchet should not be document movement. The next ratchet should be one of:

1. strengthen documentation-authority language in the AES-DEV-001 standard;
2. update the AEMS enforcement plan to reference the clean baseline and audit series;
3. create a specific future AEMS extraction issue for Atarix-local AEMS material;
4. populate repo_templates authority paths deliberately;
5. populate EDT-native architecture/user/developer/specification documents deliberately.

## Final Decision

No migration is authorized by this roll-up.

The correct engineering move is to preserve the ownership boundary and only migrate later when a document has a clear owner, clear value, and preserved provenance.
