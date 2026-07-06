# AES-DEV-001 Documentation Migration Plan

Status: Initial
Owner: AEMS
Related issue: #7

## Purpose

This plan moves project documentation from the current ATARIX-centered transitional state into the repositories that own the corresponding work.

The goal is repo-local ownership where the documentation truly governs a separate repository, not duplicated documentation and not migration for its own sake.

## Current State

The first AES-DEV-001 ecosystem baseline established:

- all repositories declare documentation authority;
- all repositories have traceable documentation authority;
- some project-owned repositories still point to `dlworrell/atarix` as documentation authority;
- evidence gaps are visible but not yet hard failures.

The transitional model is acceptable for inventory. It must now be refined so ATARIX-local material is not accidentally moved into supporting repositories.

## Desired State

Each project-owned repository should eventually contain its own authoritative development, specification, and ADR material when that material primarily governs that repository.

Shared ecosystem standards remain in `dlworrell/AES`.

Shared templates remain in `dlworrell/repo_templates`.

Cross-project orchestration and enforcement material remains in `dlworrell/AEMS`.

Project-specific architecture, specifications, ADRs, and implementation notes should move to the project repository they govern only when ownership is clear.

## Migration Rules

1. Move one logical document or document family at a time.
2. Preserve provenance in the destination document.
3. Leave a forwarding note or index entry in the source repository when needed.
4. Do not copy stale material merely to satisfy a scanner.
5. Do not split documents before ownership is understood.
6. Do not rewrite third-party mirrors/forks.
7. Prefer clean ownership over convenience.
8. Do not move ATARIX-local support or lineage material merely because it mentions another repository name.

## Provenance Requirement

Every migrated document should record:

- original repository;
- original path;
- migration date;
- reason for migration;
- owning repository after migration.

Suggested provenance block:

```text
Migrated-from: dlworrell/atarix:<path>
Migrated-to: <owning-repo>:<path>
Migration-date: YYYY-MM-DD
Reason: AES-DEV-001 repository-local documentation ownership
```

## Candidate Target Repositories

### `dlworrell/P0`

May own bootstrap and foundation material when that material governs P0 specifically.

Potential destination areas:

- `docs/architecture/`
- `docs/specs/`
- `docs/adr/`
- `docs/engineering/`

### `dlworrell/Catylist`

May own ecosystem governance and Catalyst/Catylist specification material when that material governs Catylist specifically.

Potential destination areas:

- `docs/architecture/`
- `docs/specs/`
- `docs/adr/`
- `docs/engineering/`

### `dlworrell/BB816-MATX-PCIE`

May own BB816 motherboard and PCIe hardware-platform material if that material is not ATARIX-local system architecture.

Potential destination areas:

- `docs/architecture/`
- `docs/specs/`
- `docs/adr/`
- `docs/hardware/`

### `dlworrell/JAG`

May own application-specific behavior, automation, architecture, and product documentation.

Potential destination areas:

- `docs/architecture/`
- `docs/specs/`
- `docs/adr/`
- `docs/engineering/`

## Explicit Non-Migration Targets

Do not migrate the following categories merely because they mention standalone repositories or boards. These are ATARIX-local support, reference, lineage, or integration material unless a later decision says otherwise:

- ULX3S material used by ATARIX;
- Vega816 material used by ATARIX;
- 65x02 processor/tooling material used by ATARIX.

For AES-DEV-001 reporting, these should be treated as delegated ATARIX-local documentation, not as pending migration debt.

## Material That Should Stay in ATARIX

Material should remain in `dlworrell/atarix` when it governs the ATARIX machine as a whole or ATARIX-local support/integration work, including:

- ATARIX system architecture;
- ATARIX discovery format;
- ATARIX mailbox protocol;
- ATARIX DMA model;
- ATARIX fabric controller;
- ATARIX supervisor model;
- ATARIX ring and capability model;
- ATARIX-specific local profile material;
- ULX3S material used as part of ATARIX design;
- Vega816 analysis used as ATARIX lineage or rationale;
- 65x02 CPU/tooling material used by ATARIX.

## Material That Should Probably Move to AES

Material should move to `dlworrell/AES` when it is an ecosystem-wide engineering standard, including:

- development-process standards;
- secure coding standards;
- governance rules that apply across repositories;
- reusable review checklists;
- non-project-specific engineering doctrine.

## Material That Should Probably Move to AEMS

Material should move to `dlworrell/AEMS` when it governs automation, reporting, enforcement, scanning, CI, or repository assessment.

## Migration Workflow

For each migration:

1. Identify the source document in `dlworrell/atarix`.
2. Decide the owning repository.
3. Confirm the document is not ATARIX-local support, lineage, or integration material.
4. Create the destination directory if needed.
5. Copy or adapt the document into the destination repository.
6. Add the provenance block.
7. Add a source-side forwarding note or index entry if needed.
8. Update `config/aes-dev-001-repositories.json` when ownership changes from transitional or delegated to local.
9. Re-run the AES-DEV-001 ecosystem scan.
10. Preserve a migration report after each batch.

## First Batch Candidate

Do not start with ULX3S, Vega816, or 65x02 material. Those are ATARIX-local unless later reclassified.

Start only with documents whose ownership is obvious and not ATARIX-local. The current likely first candidates are:

1. BB816-specific documents that govern `dlworrell/BB816-MATX-PCIE` rather than ATARIX as a whole.
2. JAG-specific documents that govern `dlworrell/JAG` rather than ATARIX as a whole.
3. Catylist-specific governance documents that clearly belong in `dlworrell/Catylist`.

Do not begin with ambiguous ecosystem governance, lineage, board-support, or CPU-support documents.

## AEMS Reporting Implication

During migration, AEMS should continue to accept `delegated` or `transitional` documentation authority.

When material is intentionally ATARIX-local and should remain in ATARIX, prefer `delegated` over `transitional` in the manifest.

After a repository's documentation has moved, change its manifest entry to:

```json
"documentation_authority": "local"
```

and remove migration metadata that no longer applies.

## Ratchet Direction

The next ratchet is not merely local profile adoption.

The next real ratchet is:

```text
Repositories with clear non-ATARIX-local ownership should migrate authoritative project documents from transitional ATARIX authority to local repository authority.
```

Local profile adoption remains useful, but it is secondary to moving the actual documents into the owning repositories when that ownership is real.
