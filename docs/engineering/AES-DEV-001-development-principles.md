# AES-DEV-001 Local Profile

Status: Active
Owner: AEMS
Repository: `dlworrell/AEMS`

## Inheritance

This repository inherits `AES-DEV-001: Development Principles and Check-In Discipline`.

Governing standard:

```text
dlworrell/AES/standards/AES-DEV-001-development-principles-and-check-in-discipline.md
```

## Repository Role

AEMS provides project management, assessment, reporting, and enforcement for everything under Catalyst.

## Documentation Authority

Documentation authority is local to this repository for project management, repository assessment, manifests, scanners, reports, workflows, and enforcement plans.

Authoritative paths:

- `docs/engineering/`
- `docs/engineering/reports/`
- `config/`
- `scripts/`
- `.github/workflows/`

## Local Expectations

AEMS work should prefer observable reporting before hard gates.

Scanners should distinguish missing evidence, policy violations, checkout failures, and intentional external/reference repositories.

Baselines should be preserved before ratcheting enforcement.

## Deviations

Changes that alter enforcement policy, scanner gates, repository ownership, or ratchet behavior require an ADR, issue record, or explicit engineering-plan update.
