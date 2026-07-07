# AES-DEV-001 Herkules Document Ownership Audit

Date: 2026-07-06
Owner: AEMS
Status: First targeted audit
Related standard: `AES-DEV-001`
Related inventory: `docs/engineering/reports/AES-DEV-001-document-ownership-inventory-2026-07-06.md`

## Purpose

This report audits `dlworrell/herkules-1934-english` documentation for ownership and migration readiness.

This report does not move files and does not approve source deletion.

## Result

No documents are approved for movement into or out of `herkules-1934-english` in this pass.

`herkules-1934-english` is already the correct owning repository for HERKULES-specific source assets, editorial history, translation work, glossary decisions, concordance and index material, generated project reports, and publication outputs.

## Audit Inputs

The first pass reviewed or sampled:

- `README.md`
- `edt/project.yml`
- `pyproject.toml`
- repository search for HERKULES-specific translation, report, archive, and reference material

## Ownership Findings

| Path or family | Classification | Proposed owner | Confidence | Rationale |
|---|---|---|---:|---|
| `README.md` | `ALREADY-CORRECT` | `dlworrell/herkules-1934-english` | High | Defines this repository as the working English technical edition and separates the book project from reusable EDT. |
| `edt/project.yml` | `ALREADY-CORRECT` | `dlworrell/herkules-1934-english` | High | HERKULES-specific EDT project manifest with source, OCR, translation, output, path, and preservation policy. |
| `pyproject.toml` | `ALREADY-CORRECT` | `dlworrell/herkules-1934-english` | High | Declares this as the HERKULES project repository and depends on EDT as the reusable engine. |
| `source/original/` | `ALREADY-CORRECT` | `dlworrell/herkules-1934-english` | High | Original PDFs, scans, checksums, and provenance notes are book-project source material. |
| `source/swedish/` | `ALREADY-CORRECT` | `dlworrell/herkules-1934-english` | High | Original-language transcription and page notes are HERKULES-specific. |
| `source/english/` | `ALREADY-CORRECT` | `dlworrell/herkules-1934-english` | High | English translated chapters are HERKULES-specific editorial output. |
| `reference/glossary/` | `ALREADY-CORRECT` | `dlworrell/herkules-1934-english` | High | Terminology decisions for the manual belong with the book project unless generalized into EDT examples later. |
| `reference/indexes/` | `ALREADY-CORRECT` | `dlworrell/herkules-1934-english` | High | Generated and curated indexes are project-specific publication material. |
| `reference/concordance/` | `ALREADY-CORRECT` | `dlworrell/herkules-1934-english` | High | Parts and cross-reference tables are HERKULES-specific. |
| `reference/tm/` | `ALREADY-CORRECT` | `dlworrell/herkules-1934-english` | High | Translation memory and TMX exports for Swedish-to-English HERKULES work belong with the project. |
| `reports/` | `ALREADY-CORRECT` | `dlworrell/herkules-1934-english` | High | OCR, semantic, translation, accessibility, and build reports are project-specific evidence. |
| `archive/pre-edt-work/` | `ALREADY-CORRECT` | `dlworrell/herkules-1934-english` | High | Older exploratory work is preserved for provenance and later review. |
| `build/scripts/` | `REVIEW-EDT-EXTRACTION` | `dlworrell/engineering-docs-toolkit` later, only if reusable | Medium | Legacy build tooling should remain here unless generalized into reusable EDT behavior. |
| `output/` | `ALREADY-CORRECT` | `dlworrell/herkules-1934-english` | Medium | Generated publication outputs belong here when intentionally committed. |
| EDT engine code and reusable document-processing behavior | `DO-NOT-MOVE` | `dlworrell/engineering-docs-toolkit` | High | HERKULES consumes EDT; it should not own reusable EDT engine behavior. |
| AES standards and doctrine | `DO-NOT-MOVE` | `dlworrell/AES` | High | HERKULES is a validation/project repository, not an engineering-standards repository. |
| AEMS evidence and enforcement logic | `DO-NOT-MOVE` | `dlworrell/AEMS` | High | HERKULES may produce project evidence, but AEMS owns cross-project enforcement. |
| Atarix system documents | `DO-NOT-MOVE` | `dlworrell/atarix` | High | Atarix material should not be moved into HERKULES merely because HERKULES validates EDT. |

## Clear-Move Set

None.

## Review Set

Future review should focus on whether any legacy `build/scripts/` material should be generalized into EDT. Do not move it until it is separated from HERKULES-specific assumptions.

## Decision

Do not move any documents into or out of `herkules-1934-english` yet.

HERKULES should remain the flagship EDT validation project and book-specific corpus. Reusable document-processing logic belongs in EDT. Cross-project governance belongs in AES and AEMS.

## Next Audit

Proceed to `dlworrell/code-noodling` next.
