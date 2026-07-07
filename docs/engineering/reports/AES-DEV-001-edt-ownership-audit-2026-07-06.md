# AES-DEV-001 EDT Document Ownership Audit

Date: 2026-07-06
Owner: AEMS
Status: First targeted audit
Related standard: `AES-DEV-001`
Related inventory: `docs/engineering/reports/AES-DEV-001-document-ownership-inventory-2026-07-06.md`

## Purpose

This report audits `dlworrell/engineering-docs-toolkit` documentation for ownership and migration readiness.

This report does not move files and does not approve source deletion.

## Result

No documents are approved for movement into or out of `engineering-docs-toolkit` in this pass.

`engineering-docs-toolkit` is already the correct owning repository for EDT behavior, document formats, commands, generated output, validation strategy, semantic document modeling, provenance handling, and toolkit architecture.

## Audit Inputs

The first pass reviewed or sampled:

- `README.md`
- `PROJECT_CHARTER.md`
- `docs/engineering/AES-DEV-001-development-principles.md`
- repository search for EDT-specific terminology
- repository search for HERKULES-specific ownership markers

## Ownership Findings

| Path or family | Classification | Proposed owner | Confidence | Rationale |
|---|---|---|---:|---|
| `README.md` | `ALREADY-CORRECT` | `dlworrell/engineering-docs-toolkit` | High | Defines EDT as the semantic document engineering platform and describes import, recognition, EDOM, validation, publishing, accessibility, and translation capabilities. |
| `PROJECT_CHARTER.md` | `ALREADY-CORRECT` | `dlworrell/engineering-docs-toolkit` | High | Defines EDT mission, vision, purpose, scope, non-goals, principles, and relationship to Catalyst. |
| `docs/engineering/AES-DEV-001-development-principles.md` | `ALREADY-CORRECT` | `dlworrell/engineering-docs-toolkit` | High | Local AES-DEV-001 inheritance profile for EDT authority. |
| EDT architecture handbook material | `REVIEW-POPULATE` | `dlworrell/engineering-docs-toolkit` | Medium | README identifies this as planned documentation work. Add when ready; do not import unrelated architecture documents from Atarix. |
| EDT user guide material | `REVIEW-POPULATE` | `dlworrell/engineering-docs-toolkit` | Medium | Belongs here when it describes EDT usage, not a book-specific workflow. |
| EDT developer guide material | `REVIEW-POPULATE` | `dlworrell/engineering-docs-toolkit` | Medium | Belongs here when it describes EDT implementation and extension points. |
| EDOM specification | `REVIEW-POPULATE` | `dlworrell/engineering-docs-toolkit` | Medium | Belongs here when it defines the Engineering Document Object Model. |
| Validation, reference graph, and quality report specifications | `REVIEW-POPULATE` | `dlworrell/engineering-docs-toolkit` | Medium | Belong here when they define EDT reusable behavior. |
| HERKULES source material, editorial structure, translation assets, generated outputs, and project-specific reports | `DO-NOT-MOVE` | `dlworrell/herkules-1934-english` | High | EDT README states book-specific repositories should hold project-specific materials and reports. |
| AEMS scanner, governance, evidence, and enforcement reports | `DO-NOT-MOVE` | `dlworrell/AEMS` | High | AEMS evaluates compliance; EDT provides semantic document engineering. |
| AES standards and doctrine | `DO-NOT-MOVE` | `dlworrell/AES` | High | AES defines engineering doctrine; EDT implements document tooling. |
| Atarix documentation taxonomy, ATX-100, and Atarix-local engineering documents | `DO-NOT-MOVE` | `dlworrell/atarix` | High | Atarix-local documentation should not move into EDT merely because it concerns documents. |

## Clear-Move Set

None.

## Review Set

Future EDT documentation work should focus on populating EDT-native documents rather than migrating unrelated project documents:

1. Architecture handbook
2. User guide
3. Developer guide
4. EDOM specification
5. Validation specification
6. Reference graph specification
7. Quality report specification
8. First real book workflow, only where it documents reusable EDT behavior

## Decision

Do not move any documents into or out of `engineering-docs-toolkit` yet.

EDT should own reusable document-engine behavior. It should not absorb HERKULES project material, AEMS governance material, AES doctrine, or Atarix-local documentation simply because those materials involve documents.

## Next Audit

Proceed to `dlworrell/herkules-1934-english` next.
