# AES-DEV-001 Ecosystem Baseline

Date: 2026-07-06
Owner: AEMS
Standard: AES-DEV-001
Standard repository: `dlworrell/AES`
Standard path: `standards/AES-DEV-001-development-principles-and-check-in-discipline.md`

## Baseline Interpretation

This report records the first AES-DEV-001 ecosystem evidence baseline.

The baseline establishes:

- all project-owned repositories scanned successfully;
- all repositories declare documentation authority;
- all documentation authority declarations are traceable;
- much of the non-ATARIX project documentation remains transitional and centralized in `dlworrell/atarix`;
- evidence gaps are inventory items, not hard gate failures.

## Run Summary

- Repositories listed: `17`
- Project-owned repositories: `15`
- Repositories scanned: `15`
- Project-owned repositories scanned: `15`
- Checkout failures: `0`
- Scan failures: `0`
- Documentation authority declared: `17`
- Documentation traceable: `17`
- Local documentation authority: `8`
- Delegated documentation authority: `0`
- Transitional documentation authority: `7`
- External documentation authority: `2`
- Repositories with evidence gaps: `12`
- Documentation authority gaps: `0`
- Documentation traceability gaps: `0`
- Local profile gaps: `11`
- Specification gaps: `4`
- ADR gaps: `1`
- Evidence gaps: `0`
- Reporting gate: `PASS`

## Repository Results

| Repository | Role | Ownership | Status | Docs | Doc Reference | Profile | Specs | ADRs | Evidence | Ratchet | Gaps |
|---|---|---|---|---|---|---:|---:|---:|---:|---:|---|
| `dlworrell/AEMS` | `enforcement-orchestrator` | `project-owned` | `scanned` | `local` | `local` | `False` | `False` | `False` | `5/5` | `True` | `local-profile, specs, adrs` |
| `dlworrell/P0` | `bootstrap-repository` | `project-owned` | `scanned` | `transitional` | `dlworrell/atarix:docs/architecture, docs/specs, docs/adr, docs/engineering` | `False` | `False` | `True` | `5/5` | `True` | `local-profile` |
| `dlworrell/repo_templates` | `template-source` | `project-owned` | `scanned` | `local` | `local` | `False` | `False` | `False` | `4/5` | `True` | `local-profile, specs` |
| `dlworrell/Catylist` | `ecosystem-governance` | `project-owned` | `scanned` | `transitional` | `dlworrell/atarix:docs/architecture, docs/specs, docs/adr, docs/engineering` | `False` | `True` | `False` | `4/5` | `True` | `local-profile` |
| `dlworrell/65x02` | `processor-and-tooling-research` | `project-owned` | `scanned` | `transitional` | `dlworrell/atarix:docs/architecture, docs/specs, docs/adr, docs/engineering` | `False` | `False` | `False` | `3/5` | `True` | `local-profile` |
| `dlworrell/atarix` | `system-project` | `project-owned` | `scanned` | `local` | `local` | `True` | `True` | `True` | `5/5` | `True` | `none` |
| `dlworrell/BB816-MATX-PCIE` | `hardware-platform` | `project-owned` | `scanned` | `transitional` | `dlworrell/atarix:docs/architecture, docs/specs, docs/adr, docs/engineering` | `False` | `False` | `False` | `2/5` | `True` | `local-profile` |
| `dlworrell/code-noodling` | `experimental-native-code` | `project-owned` | `scanned` | `local` | `local` | `False` | `False` | `False` | `3/5` | `True` | `none` |
| `dlworrell/engineering-docs-toolkit` | `documentation-tooling` | `project-owned` | `scanned` | `local` | `local` | `False` | `True` | `False` | `5/5` | `True` | `local-profile` |
| `dlworrell/herkules-1934-english` | `documentation-and-build-book` | `project-owned` | `scanned` | `local` | `local` | `False` | `False` | `False` | `4/5` | `True` | `specs` |
| `dlworrell/JAG` | `application-project` | `project-owned` | `scanned` | `transitional` | `dlworrell/atarix:docs/architecture, docs/specs, docs/adr, docs/engineering` | `False` | `False` | `False` | `2/5` | `True` | `local-profile` |
| `dlworrell/Just-a-Geek-LLC` | `organization-governance` | `project-owned` | `scanned` | `local` | `local` | `False` | `False` | `False` | `2/5` | `True` | `local-profile, specs` |
| `dlworrell/Rocket_demo` | `demo-project` | `project-owned` | `scanned` | `local` | `local` | `False` | `False` | `False` | `2/5` | `True` | `none` |
| `dlworrell/ulx3s` | `fpga-platform` | `project-owned` | `scanned` | `transitional` | `dlworrell/atarix:docs/architecture, docs/specs, docs/adr, docs/engineering` | `False` | `False` | `False` | `5/5` | `True` | `local-profile` |
| `dlworrell/Vega816` | `system-or-hardware-project` | `project-owned` | `scanned` | `transitional` | `dlworrell/atarix:docs/architecture, docs/specs, docs/adr, docs/engineering` | `False` | `False` | `False` | `3/5` | `True` | `local-profile` |
| `dlworrell/cglm` | `third-party-c-library` | `third-party-mirror-or-fork` | `not-scanned-third-party` | `external` | `external` | `n/a` | `n/a` | `n/a` | `n/a` | `n/a` | `none` |
| `dlworrell/CLK` | `third-party-emulator` | `third-party-mirror-or-fork` | `not-scanned-third-party` | `external` | `external` | `n/a` | `n/a` | `n/a` | `n/a` | `n/a` | `none` |

## Checkout or Scan Failures

None.

## Evidence Gaps

- `dlworrell/AEMS`: local-profile, specs, adrs
- `dlworrell/P0`: local-profile
- `dlworrell/repo_templates`: local-profile, specs
- `dlworrell/Catylist`: local-profile
- `dlworrell/65x02`: local-profile
- `dlworrell/BB816-MATX-PCIE`: local-profile
- `dlworrell/engineering-docs-toolkit`: local-profile
- `dlworrell/herkules-1934-english`: specs
- `dlworrell/JAG`: local-profile
- `dlworrell/Just-a-Geek-LLC`: local-profile, specs
- `dlworrell/ulx3s`: local-profile
- `dlworrell/Vega816`: local-profile

## Delegated or Transitional Documentation

- `dlworrell/P0`: `transitional` -> `dlworrell/atarix:docs/architecture, docs/specs, docs/adr, docs/engineering`; migration: centralized-in-atarix-pending-split
- `dlworrell/Catylist`: `transitional` -> `dlworrell/atarix:docs/architecture, docs/specs, docs/adr, docs/engineering`; migration: centralized-in-atarix-pending-split
- `dlworrell/65x02`: `transitional` -> `dlworrell/atarix:docs/architecture, docs/specs, docs/adr, docs/engineering`; migration: centralized-in-atarix-pending-split
- `dlworrell/BB816-MATX-PCIE`: `transitional` -> `dlworrell/atarix:docs/architecture, docs/specs, docs/adr, docs/engineering`; migration: centralized-in-atarix-pending-split
- `dlworrell/JAG`: `transitional` -> `dlworrell/atarix:docs/architecture, docs/specs, docs/adr, docs/engineering`; migration: centralized-in-atarix-pending-split
- `dlworrell/ulx3s`: `transitional` -> `dlworrell/atarix:docs/architecture, docs/specs, docs/adr, docs/engineering`; migration: centralized-in-atarix-pending-split
- `dlworrell/Vega816`: `transitional` -> `dlworrell/atarix:docs/architecture, docs/specs, docs/adr, docs/engineering`; migration: centralized-in-atarix-pending-split

## Immediate Interpretation

The first ratchet rule is satisfied: every repository declares traceable documentation authority.

The next useful ratchet is to reduce local-profile gaps. Local profiles should be lightweight inheritance documents, not full duplicated architecture documents.
