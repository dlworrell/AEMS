# AES-DEV-001 Atarix Document Ownership Audit

Date: 2026-07-06
Owner: AEMS
Status: First targeted audit
Related standard: `AES-DEV-001`
Related inventory: `docs/engineering/reports/AES-DEV-001-document-ownership-inventory-2026-07-06.md`

## Purpose

This report audits `dlworrell/atarix` documentation for possible repository-local ownership migration.

This report does not move files and does not approve source deletion.

## Result

No `atarix/docs/` document is approved for immediate movement in this pass.

The dominant finding is that the Atarix documentation is mostly Atarix-local. It governs the Atarix operating system, machine architecture, target hardware integration, reference-platform analysis, engineering evidence, or project-specific tooling.

## Documents Reviewed

The first pass reviewed or sampled these Atarix document families:

- core architecture documents under `docs/`
- ATX-100 architecture-book material under `docs/architecture/ATX-100/`
- Atarix specification documents under `docs/architecture/`
- Atarix design documents under `docs/design/`
- Atarix engineering-process documents under `docs/engineering/`
- Atarix ADRs under `docs/adr/`
- Atarix review material under `docs/reviews/`
- hardware-reference and lineage notes under `docs/`
- Atarix-local AEMS tooling under `tools/aems/`
- Atarix-local engineering scripts under `scripts/engineering/`
- `docs/roadmap/repository-extraction-plan.md`

## Ownership Findings

| Path or family | Classification | Proposed owner | Confidence | Rationale |
|---|---|---|---:|---|
| `docs/security.md` | `STAY-ATARIX` | `dlworrell/atarix` | High | Atarix system architecture. |
| `docs/bus-architecture.md` and related bus/fabric/addressing documents | `STAY-ATARIX` | `dlworrell/atarix` | High | Atarix machine architecture and target-hardware behavior. |
| `docs/capability-model.md` and related authority-model documents | `STAY-ATARIX` | `dlworrell/atarix` | High | Atarix-local authority model. |
| `docs/vega816-analysis.md` | `STAY-ATARIX` | `dlworrell/atarix` | High | Atarix-local lineage and reference-design analysis. |
| `docs/ulx3s-backplane-controller.md` | `STAY-ATARIX` | `dlworrell/atarix` | High | Atarix target-hardware integration decision. |
| `docs/specification-roadmap.md` | `STAY-ATARIX` | `dlworrell/atarix` | High | Tracks Atarix specifications and implementation outputs. |
| `docs/architecture/ATX-100/` | `STAY-ATARIX` | `dlworrell/atarix` | High | Canonical Atarix architecture-book material. |
| `docs/architecture/ATX-100/chapters/20-aems-and-engineering-gates.md` | `STAY-ATARIX` | `dlworrell/atarix` | Medium | ATX-100 chapter about Atarix engineering evidence. |
| `docs/architecture/ATX-SPEC-090-Atarix-Engineering-Management-System.md` | `REVIEW-AEMS-EXTRACTION` | `dlworrell/AEMS` later, if generalized | Medium | Currently Atarix-specific; may inform a future standalone AEMS specification. |
| `docs/architecture/ATX-SPEC-091-Requirements-and-Traceability-Model.md` | `REVIEW-AEMS-EXTRACTION` | `dlworrell/AEMS` later, if generalized | Medium | Currently Atarix-specific; may inform future reusable AEMS traceability rules. |
| `docs/engineering/Documentation-Taxonomy-and-Style-Guide.md` | `STAY-ATARIX` | `dlworrell/atarix` | High | Atarix documentation taxonomy and lifecycle guidance. |
| `docs/design/ATX-DESIGN-003-Engineering-Principles.md` | `STAY-ATARIX` | `dlworrell/atarix` | High | Atarix engineering principles. |
| `docs/design/ATX-DESIGN-005-Evolution-Strategy.md` | `STAY-ATARIX` | `dlworrell/atarix` | High | Atarix evolution strategy. |
| `tools/aems/` | `REVIEW-AEMS-EXTRACTION` | `dlworrell/AEMS` later, if reusable | Medium | Atarix-local AEMS tooling that may later be split into reusable AEMS. |
| `scripts/engineering/` | `STAY-ATARIX` | `dlworrell/atarix` | Medium | Atarix project gates and local documentation checks. |
| `docs/roadmap/repository-extraction-plan.md` | `REVIEW-SUPERSEDED` | undecided | Low | Cross-repository plan appears stale relative to the corrected Catalyst tree. Do not migrate stale material. |

## Clear-Move Set

None.

## Review Set

These items deserve later review but are not approved for movement now:

1. `docs/architecture/ATX-SPEC-090-Atarix-Engineering-Management-System.md`
2. `docs/architecture/ATX-SPEC-091-Requirements-and-Traceability-Model.md`
3. `tools/aems/`
4. `docs/roadmap/repository-extraction-plan.md`

## Decision

Do not move any Atarix documents yet.

Atarix remains the correct owner for its architecture, system specifications, reference-platform analysis, hardware-lineage material, ATX-100 material, and Atarix-local engineering evidence.

AEMS extraction should be handled later as a deliberate split of reusable AEMS specifications and tools, not as a file relocation exercise.

## Next Audit

Proceed to `dlworrell/repo_templates` next.
