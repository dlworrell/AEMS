# AES-SEC-001 Control Profile Roll-Up

Date: 2026-07-26
Owner: AEMS
Standard: AES-SEC-001
Issue: #6

## Result

The missing AEMS-side AES-SEC-001 controls are implemented.

The July 6 adoption baseline remains historical evidence. This roll-up records
the later native-control layer and corrects the current manifest's ownership
classification without rewriting that earlier artifact.

## Acceptance Evidence

| Required result | Implemented evidence |
|---|---|
| Repository-by-repository reports | `scripts/aes_sec_001_aggregate.py --per-repository-dir …` writes JSON and Markdown evidence for every manifest entry. |
| Native warning profiles | `config/aes-sec-001-native-profiles.json` defines `c17-kernel`, `c17-library`, `cpp17-bridge`, and `experimental-native`. |
| Static-analysis workflow | `templates/workflows/aes-sec-001-native.yml` installs Clang analysis tooling and runs explicitly configured, typed repository-owned controls. |
| Sanitizer presets | `templates/native/` contains opt-in CMake, Make, and Meson settings for supported project-owned host targets. |
| Fuzz discovery and smoke tests | `scripts/aes_sec_001_native.py` discovers harnesses and executes explicit bounded argument-array targets from `.aems/aes-sec-001-native.json`. |
| Third-party separation | The manifest classifies mirrors/forks separately; the aggregate runner does not scan them by default. |
| Development-process separation | AES-DEV-001 has an independent manifest, scanner, workflow, baseline, and closure evidence. |

## Current Manifest

- Entries: `20`
- Project-owned: `14`
- External/reference: `4`
- Third-party mirror or fork: `2`
- Native profiles assigned: `4`

The external/reference classification applies to `65x02`,
`BB816-MATX-PCIE`, `ulx3s`, and `Vega816`. These repositories are evidence or
platform inputs, not AEMS-governed project code.

## Native Profile Assignments

| Repository | Profile | Reason |
|---|---|---|
| `dlworrell/atarix` | `c17-kernel` | C17/assembly kernel and host-supported target tests |
| `dlworrell/code-noodling` | `experimental-native` | Experimental C, C++, and CUDA work with a staged ratchet |
| `dlworrell/evo` | `c17-library` | Reusable C library with externally supplied engineering inputs |
| `dlworrell/MayaUSD2017Bridge` | `cpp17-bridge` | C++17 plug-in and framed-process bridge boundaries |

An assignment records required control intent. It is not evidence that a
downstream repository has adopted every control. Adoption must occur in that
repository through a reviewable, repository-owned change.

## Safety Boundary

This implementation does not:

- bulk-edit downstream repositories;
- treat external/reference or third-party code as project-owned;
- run arbitrary discovered binaries;
- invoke configured smoke commands through a shell; or
- claim that warnings, analyzers, sanitizers, or smoke tests prove runtime
  safety.

## Verification

`tests/test_aes_sec_001_native.py` covers signal discovery, profile loading,
fuzz-smoke success/failure recording, and per-repository report generation.
The full AEMS test suite exercises this layer alongside Project Zero,
traceability, and AES-SEC-002 reporting.
