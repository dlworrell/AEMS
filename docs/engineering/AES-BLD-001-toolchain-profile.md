# AEMS AES-BLD-001 Toolchain Profile

Status: Pre-adoption

Repository: `dlworrell/AEMS`

Authority: `dlworrell/AES`

Normative requirements:
`standards/AES-BLD-001-native-build-toolchain-and-distribution-parity.md`

Machine-readable profile: `.aems/aes-bld-001.json`

Waiver log: `.aems/aes-bld-001-waivers.json`

## Applicability

AEMS is currently an enforcement orchestrator implemented in Python. It is
classified `planned-native` because project-owned repositories are expected to
become independently operable C-based systems over time.

No AEMS production C or C++ target exists today, so execution and parity
requirements remain not applicable to the AEMS repository itself. The C
library and application projects under `tests/fixtures/aes_bld_001/` are
synthetic reference repositories and are not AEMS production targets.

## Adoption boundary

Before the first AEMS native production source is merged:

1. replace `planned-native` with `active-native`;
2. adopt the current C application or library reference layout;
3. declare production sources, normative tests, options, install payload,
   supported compilers, and exact preset/build paths;
4. run the distributed workflow in strict mode; and
5. add any temporary exception to the machine-readable waiver log with an
   owner, reviewer, compensating validation, and expiry date.

The reference fixtures may evolve without silently changing this local
applicability marker.
