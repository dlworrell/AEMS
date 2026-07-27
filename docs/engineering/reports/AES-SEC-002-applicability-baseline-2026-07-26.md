# AES-SEC-002 Ecosystem Reporting Baseline

- Mode: `reporting`
- Blocking enforcement: `false`
- Baseline date: `2026-07-26`
- Owner: `AEMS`
- Repositories: `21`
- In scope: `1`
- Out of scope: `18`
- Not yet classified: `2`
- Scanned: `0`
- Untested checkouts: `0`
- Violations: `0`
- Absent evidence: `0`

## Repository applicability

| Repository | Ownership | Applicability | Status | Violations | Absent | Untested | Rationale |
|---|---|---|---|---:|---:|---:|---|
| `dlworrell/audiblebooks` | `project-owned` | `in-scope` | `classification-only` | `0` | `0` | `1` | The current implementation crosses Swift 6 and C, owns SQLCipher key material, imports encrypted catalogues, and supports Linux/ELF plus Apple/Mach-O targets. |
| `dlworrell/MayaUSD2017Bridge` | `project-owned` | `not-yet-classified` | `classification-only` | `0` | `0` | `1` | The implemented foundation is a C++ process bridge with no safe-language FFI, key lifecycle, or encrypted store. Planned M1 scene bridge packages may carry confidential production data, so applicability must be reassessed when translation and staging land. |
| `dlworrell/JAG` | `project-owned` | `not-yet-classified` | `classification-only` | `0` | `0` | `1` | Application architecture, language boundaries, secret material, and confidential local-storage behavior have not yet been inventoried against AES-SEC-002. |
| `dlworrell/AEMS` | `project-owned` | `out-of-scope` | `classification-only` | `0` | `0` | `0` | AEMS currently consists of Python reporting tools and documentation; it has no memory-safe/native ABI, secret lifecycle, or confidential encrypted local store. |
| `dlworrell/Catylist` | `project-owned` | `out-of-scope` | `classification-only` | `0` | `0` | `0` | Catylist is governance and schema tooling without a safe/native ABI, secret lifecycle, or confidential encrypted local store. |
| `dlworrell/AES` | `project-owned` | `out-of-scope` | `classification-only` | `0` | `0` | `0` | AES owns the standard but does not currently implement an application boundary covered by it. |
| `dlworrell/P0` | `project-owned` | `out-of-scope` | `classification-only` | `0` | `0` | `0` | P0 currently contains bootstrap documentation and no covered ABI, secret, or encrypted-storage boundary. |
| `dlworrell/repo_templates` | `project-owned` | `out-of-scope` | `classification-only` | `0` | `0` | `0` | Repository templates may distribute future controls but do not themselves implement a covered application boundary. |
| `dlworrell/atarix` | `project-owned` | `out-of-scope` | `classification-only` | `0` | `0` | `0` | Current Atarix code is native C/RTL without a memory-safe-language FFI, application secret lifecycle, or encrypted confidential local store; AES-SEC-001 remains applicable. |
| `dlworrell/evo` | `project-owned` | `out-of-scope` | `classification-only` | `0` | `0` | `0` | EVO is a native library with no currently declared safe/native ABI consumer, secret lifecycle, or encrypted store. |
| `dlworrell/code-noodling` | `project-owned` | `out-of-scope` | `classification-only` | `0` | `0` | `0` | Experimental native programs are covered by AES-SEC-001; no AES-SEC-002 boundary is currently declared. |
| `dlworrell/engineering-docs-toolkit` | `project-owned` | `out-of-scope` | `classification-only` | `0` | `0` | `0` | The documentation toolchain has no declared safe/native ABI, secret lifecycle, or encrypted confidential local store. |
| `dlworrell/herkules-1934-english` | `project-owned` | `out-of-scope` | `classification-only` | `0` | `0` | `0` | The publication project has no declared safe/native ABI, secret lifecycle, or encrypted confidential local store. |
| `dlworrell/Just-a-Geek-LLC` | `project-owned` | `out-of-scope` | `classification-only` | `0` | `0` | `0` | The administrative repository has no covered application implementation. |
| `dlworrell/Rocket_demo` | `project-owned` | `out-of-scope` | `classification-only` | `0` | `0` | `0` | No safe/native ABI, secret lifecycle, or confidential encrypted local store is declared in the current demo. |
| `dlworrell/65x02` | `external-reference` | `out-of-scope` | `classification-only` | `0` | `0` | `0` | External/reference processor material is not a Catalyst-owned application boundary. |
| `dlworrell/BB816-MATX-PCIE` | `external-reference` | `out-of-scope` | `classification-only` | `0` | `0` | `0` | External/reference hardware material is not a Catalyst-owned application boundary. |
| `dlworrell/ulx3s` | `external-reference` | `out-of-scope` | `classification-only` | `0` | `0` | `0` | External/reference FPGA material is not a Catalyst-owned application boundary. |
| `dlworrell/Vega816` | `external-reference` | `out-of-scope` | `classification-only` | `0` | `0` | `0` | External/reference system material is not a Catalyst-owned application boundary. |
| `dlworrell/cglm` | `third-party-mirror-or-fork` | `out-of-scope` | `classification-only` | `0` | `0` | `0` | A third-party C-library mirror is not rewritten as a Catalyst application boundary. |
| `dlworrell/CLK` | `third-party-mirror-or-fork` | `out-of-scope` | `classification-only` | `0` | `0` | `0` | A third-party emulator mirror is not rewritten as a Catalyst application boundary. |

## Ratchet boundary

This report does not authorize blocking enforcement. A future ratchet requires retained source-scan baselines, an affected-repository migration window, operational waivers, reviewed high-signal detectors, and a separate governance and standards decision.
