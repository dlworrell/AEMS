# AES-BLD-001 Toolchain Profile

Status: Pre-adoption template

Authority: `dlworrell/AES`

Normative requirements:
`standards/AES-BLD-001-native-build-toolchain-and-distribution-parity.md`

Machine-readable profile: `.aems/aes-bld-001.json`

Waiver log: `.aems/aes-bld-001-waivers.json`

## Applicability

Record whether the repository is `active-native`, `planned-native`, or
`not-applicable`. Project-owned repositories that will eventually contain C or
C++ use `planned-native` before their first production source is merged.

## Canonical developer path

Document the checked-in CMake configure, build, and CTest presets for Clang,
GCC, and the Clang ASan+UBSan path. Record the C/C++ standards, warning policy,
clang-tidy configuration, compilation-database location, supported hosts, and
cross-compilation limitations.

## Independent GNU path

Document `autoreconf -fvi`, the out-of-tree `configure` command, GNU Make
build/test/install/uninstall commands, GCC and Clang interchange, Libtool use,
and `make distcheck` applicability.

## Parity map

List production targets and sources, normative tests, user-visible options,
install paths, package metadata, public symbols, and the downstream consumer
that must agree between the two frontends. Record only narrowly scoped
frontend-specific metadata exclusions.

## Version and offline policy

Record minimum supported versions and retain the exact versions emitted by the
AEMS compliance job. Describe dependencies that must be installed or vendored
before configure/build/test/install can proceed without network access.

## Waivers

Waivers identify an AES-BLD-001 requirement, technical constraint, owner,
reviewer, compensating validation, and expiry date. Expired or malformed
waivers fail the AEMS evidence gate.
