# AES-DEV-001 Documentation Migration Plan

Status: Initial
Owner: AEMS
Related issue: #7

## Purpose

This plan moves project documentation from the current ATARIX-centered transitional state into the repositories that own the corresponding work.

The goal is repo-local ownership, not duplicated documentation.

## Current State

The first AES-DEV-001 ecosystem baseline established:

- all repositories declare documentation authority;
- all repositories have traceable documentation authority;
- seven project-owned repositories still point to `dlworrell/atarix` as transitional documentation authority;
- evidence gaps are visible but not yet hard failures.

The transitional model is acceptable for inventory. It is not the desired end state.

## Desired State

Each project-owned repository should eventually contain its own authoritative development, specification, and ADR material when that material primarily governs that repository.

Shared ecosystem standards remain in `dlworrell/AES`.

Shared templates remain in `dlworrell/repo_templates`.

Cross-project orchestration and enforcement material remains in `dlworrell/AEMS`.

Project-specific architecture, specifications, ADRs, and implementation notes should move to the project repository they govern.

## Migration Rules

1. Move one logical document or document family at a time.
2. Preserve provenance in the destination document.
3. Leave a forwarding note or index entry in the source repository when needed.
4. Do not copy stale material merely to satisfy a scanner.
5. Do not split documents before ownership is understood.
6. Do not rewrite third-party mirrors/forks.
7. Prefer clean ownership over convenience.

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

## Target Repositories

### `dlworrell/P0`

Likely owns bootstrap and foundation material.

Potential destination areas:

- `docs/architecture/`
- `docs/specs/`
- `docs/adr/`
- `docs/engineering/`

### `dlworrell/Catylist`

Likely owns ecosystem governance and Catalyst/Catylist specification material.

Potential destination areas:

- `docs/architecture/`
- `docs/specs/`
- `docs/adr/`
- `docs/engineering/`

### `dlworrell/65x02`

Likely owns processor, tooling, and 65x02-family research material.

Potential destination areas:

- `docs/architecture/`
- `docs/specs/`
- `docs/adr/`
- `docs/engineering/`

### `dlworrell/BB816-MATX-PCIE`

Likely owns BB816 motherboard and PCIe hardware-platform material.

Potential destination areas:

- `docs/architecture/`
- `docs/specs/`
- `docs/adr/`
- `docs/hardware/`

### `dlworrell/JAG`

Likely owns application-specific behavior, automation, architecture, and product documentation.

Potential destination areas:

- `docs/architecture/`
- `docs/specs/`
- `docs/adr/`
- `docs/engineering/`

### `dlworrell/ulx3s`

Likely owns ULX3S FPGA platform material.

Potential destination areas:

- `docs/architecture/`
- `docs/specs/`
- `docs/adr/`
- `docs/fpga/`

### `dlworrell/Vega816`

Likely owns Vega816 system and hardware material.

Potential destination areas:

- `docs/architecture/`
- `docs/specs/`
- `docs/adr/`
- `docs/engineering/`

## Material That Should Probably Stay in ATARIX

Material should remain in `dlworrell/atarix` when it governs the ATARIX machine as a whole, including:

- ATARIX system architecture;
- ATARIX discovery format;
- ATARIX mailbox protocol;
- ATARIX DMA model;
- ATARIX fabric controller;
- ATARIX supervisor model;
- ATARIX ring and capability model;
- ATARIX-specific local profile material.

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
3. Create the destination directory if needed.
4. Copy or adapt the document into the destination repository.
5. Add the provenance block.
6. Add a source-side forwarding note or index entry if needed.
7. Update `config/aes-dev-001-repositories.json` when ownership changes from transitional to local.
8. Re-run the AES-DEV-001 ecosystem scan.
9. Preserve a migration report after each batch.

## First Batch Candidate

Start with documents whose ownership is obvious and low-risk:

1. BB816-specific documents to `dlworrell/BB816-MATX-PCIE`.
2. ULX3S-specific documents to `dlworrell/ulx3s`.
3. Vega816-specific documents to `dlworrell/Vega816`.
4. 65x02 processor/tooling documents to `dlworrell/65x02`.

Do not begin with ambiguous ecosystem governance documents.

## AEMS Reporting Implication

During migration, AEMS should continue to accept `transitional` documentation authority.

After a repository's documentation has moved, change its manifest entry to:

```json
"documentation_authority": "local"
```

and remove transitional migration metadata that no longer applies.

## Ratchet Direction

The next ratchet is not merely local profile adoption.

The next real ratchet is:

```text
Repositories with clear ownership should migrate authoritative project documents from transitional ATARIX authority to local repository authority.
```

Local profile adoption remains useful, but it is secondary to moving the actual documents into the owning repositories.
