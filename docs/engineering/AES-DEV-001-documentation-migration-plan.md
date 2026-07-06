# AES-DEV-001 Documentation Migration Plan

Status: Revised
Owner: AEMS
Related issue: #7

## Purpose

This plan governs documentation ownership for the Catalyst tree.

The goal is repo-local ownership where the documentation truly governs a Catalyst project repository, not duplicated documentation and not migration for its own sake.

## Catalyst Tree

Catalyst repositories are organized as follows:

- `dlworrell/Catylist`: Catalyst program umbrella and managing organization.
- `dlworrell/AES`: engineering standards repository.
- `dlworrell/AEMS`: project management, assessment, reporting, and enforcement for everything under Catalyst.
- `dlworrell/atarix`: operating system for the hardware being built.
- `dlworrell/engineering-docs-toolkit`: engineering document toolkit.
- `dlworrell/repo_templates`: repository standard used as the default/start point for Catalyst repositories.
- `dlworrell/herkules-1934-english`: EDT validation project.
- `dlworrell/code-noodling`: experimentation and testing repository.

The following repositories are external/reference repositories used for ideas, lineage, compatibility research, or borrowed implementation patterns. They are not governed as Catalyst project repositories:

- `dlworrell/cglm`
- `dlworrell/CLK`
- `dlworrell/65x02`
- `dlworrell/BB816-MATX-PCIE`
- `dlworrell/ulx3s`
- `dlworrell/Vega816`

## Current State

The first AES-DEV-001 ecosystem baseline established that documentation authority is traceable. The manifest has since been corrected so external/reference repositories are no longer treated as project-owned Catalyst repositories.

The important correction is that Atarix may contain reference material about external repositories when that material supports Atarix design. That material is Atarix-local unless explicitly reclassified.

## Desired State

Each Catalyst project repository should contain its own authoritative development, specification, and ADR material when that material primarily governs that repository.

Shared ecosystem standards remain in `dlworrell/AES`.

Shared templates remain in `dlworrell/repo_templates`.

Cross-project orchestration, management, reporting, and enforcement material remains in `dlworrell/AEMS`.

Atarix system, OS, hardware-support, board-reference, lineage, and integration material remains in `dlworrell/atarix` when it governs Atarix.

External/reference repositories are not migration targets.

## Migration Rules

1. Move one logical document or document family at a time.
2. Preserve provenance in the destination document.
3. Leave a forwarding note or index entry in the source repository when needed.
4. Do not copy stale material merely to satisfy a scanner.
5. Do not split documents before ownership is understood.
6. Do not rewrite external/reference repositories.
7. Prefer clean ownership over convenience.
8. Do not move Atarix-local support, reference, lineage, or integration material merely because it mentions another repository name.

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

### `dlworrell/Catylist`

Move material here only when it governs the Catalyst program umbrella or managing organization.

Potential destination areas:

- `docs/architecture/`
- `docs/specs/`
- `docs/adr/`
- `docs/engineering/`

### `dlworrell/AES`

Move material here only when it is an ecosystem-wide engineering standard or reusable engineering doctrine.

Potential destination areas:

- `standards/`
- `docs/`

### `dlworrell/AEMS`

Move material here only when it governs project management, assessment, reporting, enforcement, scanners, manifests, or CI.

Potential destination areas:

- `docs/engineering/`
- `docs/engineering/reports/`
- `config/`
- `scripts/`

### `dlworrell/atarix`

Keep material here when it governs the Atarix operating system, target hardware integration, OS-level architecture, reference boards used by Atarix, lineage, or system rationale.

### `dlworrell/engineering-docs-toolkit`

Move material here only when it governs EDT behavior, formats, commands, generated output, validation strategy, or toolkit architecture.

### `dlworrell/repo_templates`

Move material here only when it governs repository layout, default files, shared templates, default policies, or Catalyst repo bootstrap behavior.

### `dlworrell/herkules-1934-english`

Move material here only when it governs the Herkules EDT validation project or its expected generated deliverables.

### `dlworrell/code-noodling`

Move material here only when it governs experimental code, test harnesses, exploratory algorithms, or temporary engineering investigations.

## Explicit Non-Migration Targets

Do not migrate documentation into these repositories as part of Catalyst governance:

- `dlworrell/cglm`
- `dlworrell/CLK`
- `dlworrell/65x02`
- `dlworrell/BB816-MATX-PCIE`
- `dlworrell/ulx3s`
- `dlworrell/Vega816`

These repositories are external/reference repositories. They are used to borrow ideas from and should not be rewritten to satisfy Catalyst policy.

## Material That Should Stay in Atarix

Material should remain in `dlworrell/atarix` when it governs the Atarix machine as a whole or Atarix-local support/integration work, including:

- Atarix system architecture;
- Atarix discovery format;
- Atarix mailbox protocol;
- Atarix DMA model;
- Atarix fabric controller;
- Atarix supervisor model;
- Atarix ring and capability model;
- Atarix-specific local profile material;
- ULX3S material used as part of Atarix design;
- Vega816 analysis used as Atarix lineage or rationale;
- 65x02 CPU/tooling material used by Atarix;
- BB816-MATX-PCIE material used as external hardware reference for Atarix.

## Migration Workflow

For each migration:

1. Identify the source document.
2. Decide the owning Catalyst repository.
3. Confirm the document is not Atarix-local support, reference, lineage, or integration material.
4. Confirm the destination repository is a Catalyst project repository, not an external/reference repository.
5. Create the destination directory if needed.
6. Copy or adapt the document into the destination repository.
7. Add the provenance block.
8. Add a source-side forwarding note or index entry if needed.
9. Update `config/aes-dev-001-repositories.json` when ownership changes.
10. Re-run the AES-DEV-001 ecosystem scan.
11. Preserve a migration report after each batch.

## First Batch Candidate

Do not start with external/reference repositories.

Start with documents whose Catalyst ownership is obvious and not Atarix-local. The current likely first candidates are:

1. AEMS-specific enforcement, reporting, scanner, or workflow material.
2. AES-specific ecosystem standards or engineering doctrine.
3. EDT-specific toolkit behavior and validation documents.
4. repo_templates-specific repository-standard material.
5. Herkules-specific EDT validation material.
6. JAG-specific material only if JAG remains a Catalyst project repository and the document governs JAG directly.

Do not begin with ambiguous ecosystem governance, lineage, board-support, CPU-support, or hardware-reference documents.

## AEMS Reporting Implication

AEMS should report three distinct classes:

- Catalyst project repositories;
- external/reference repositories;
- third-party mirrors/forks.

External/reference repositories should normally be listed but not scanned. They are not policy targets.

## Ratchet Direction

The next ratchet is not merely local profile adoption.

The next real ratchet is:

```text
Catalyst project repositories with clear ownership should keep their authoritative project documents locally; external/reference repositories remain outside Catalyst governance.
```

Local profile adoption remains useful, but it is secondary to correct repository classification and real document ownership.
