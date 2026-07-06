# AES-SEC-001 Ecosystem Baseline

Date: 2026-07-06
Owner: AEMS
Standard: AES-SEC-001
Standard repository: `dlworrell/AES`
Standard path: `standards/AES-SEC-001-secure-c-cpp-coding-rules.md`

## Baseline Interpretation

This report records the first clean AES-SEC-001 ecosystem baseline for project-owned repositories.

The baseline establishes:

- the minimum adoption gate passes across project-owned repositories;
- banned findings are zero;
- review-required findings are zero;
- third-party mirrors/forks are listed but not scanned as project-owned code.

## Run Summary

- Repositories listed: `17`
- Repositories scanned: `15`
- Checkout failures: `0`
- Expected gate failures: `0`
- Banned findings: `0`
- Review-required findings: `0`
- Aggregate result: `PASS`

## Repository Results

| Repository | Role | Ownership | Status | Class | Profile | Waiver Log | Banned Findings | Review Findings | Gate |
|---|---|---|---|---|---:|---:|---:|---:|---:|
| `dlworrell/AEMS` | `enforcement-orchestrator` | `project-owned` | `scanned` | `documentation-or-governance` | `True` | `True` | `0` | `0` | `True` |
| `dlworrell/P0` | `bootstrap-repository` | `project-owned` | `scanned` | `documentation-or-governance` | `True` | `True` | `0` | `0` | `True` |
| `dlworrell/repo_templates` | `template-source` | `project-owned` | `scanned` | `documentation-or-governance` | `True` | `True` | `0` | `0` | `True` |
| `dlworrell/Catylist` | `ecosystem-governance` | `project-owned` | `scanned` | `documentation-or-governance` | `True` | `True` | `0` | `0` | `True` |
| `dlworrell/65x02` | `processor-and-tooling-research` | `project-owned` | `scanned` | `documentation-or-governance` | `True` | `True` | `0` | `0` | `True` |
| `dlworrell/atarix` | `system-project` | `project-owned` | `scanned` | `native-code-active` | `True` | `True` | `0` | `0` | `True` |
| `dlworrell/BB816-MATX-PCIE` | `hardware-platform` | `project-owned` | `scanned` | `documentation-or-governance` | `True` | `True` | `0` | `0` | `True` |
| `dlworrell/code-noodling` | `experimental-native-code` | `project-owned` | `scanned` | `native-code-active` | `True` | `True` | `0` | `0` | `True` |
| `dlworrell/engineering-docs-toolkit` | `documentation-tooling` | `project-owned` | `scanned` | `native-code-planned-or-build-surface` | `True` | `True` | `0` | `0` | `True` |
| `dlworrell/herkules-1934-english` | `documentation-and-build-book` | `project-owned` | `scanned` | `native-code-planned-or-build-surface` | `True` | `True` | `0` | `0` | `True` |
| `dlworrell/JAG` | `application-project` | `project-owned` | `scanned` | `documentation-or-governance` | `True` | `True` | `0` | `0` | `True` |
| `dlworrell/Just-a-Geek-LLC` | `organization-governance` | `project-owned` | `scanned` | `documentation-or-governance` | `True` | `True` | `0` | `0` | `True` |
| `dlworrell/Rocket_demo` | `demo-project` | `project-owned` | `scanned` | `documentation-or-governance` | `True` | `True` | `0` | `0` | `True` |
| `dlworrell/ulx3s` | `fpga-platform` | `project-owned` | `scanned` | `native-code-planned-or-build-surface` | `True` | `True` | `0` | `0` | `True` |
| `dlworrell/Vega816` | `system-or-hardware-project` | `project-owned` | `scanned` | `documentation-or-governance` | `True` | `True` | `0` | `0` | `True` |
| `dlworrell/cglm` | `third-party-c-library` | `third-party-mirror-or-fork` | `not-scanned-third-party` | `n/a` | `n/a` | `n/a` | `0` | `0` | `n/a` |
| `dlworrell/CLK` | `third-party-emulator` | `third-party-mirror-or-fork` | `not-scanned-third-party` | `n/a` | `n/a` | `n/a` | `0` | `0` | `n/a` |

## Expected Gate Failures

None.

## Review-Required Findings

None.

## Follow-Up Work

This baseline completes the first AES-SEC-001 adoption phase. Follow-up work should ratchet from adoption evidence to stronger native-code engineering controls:

- native warning profiles for active native-code repositories;
- static-analysis workflow templates;
- sanitizer build/test presets;
- fuzz-harness discovery and smoke-test support;
- separate development-process checks for ATARIX architecture and check-in discipline.
