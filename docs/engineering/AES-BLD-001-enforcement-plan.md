# AES-BLD-001 Enforcement Plan

Status: Reference gate with authoritative GNU and LLVM tool bindings

Owner: AEMS

Issues: #21, #23

Authority: `dlworrell/AES`

Normative source:
`standards/AES-BLD-001-native-build-toolchain-and-distribution-parity.md`

## Purpose

AEMS implements the adopted AES requirements without redefining them. This
plan establishes one canonical CMake/CTest/Clang/LLVM development path and one
independent Autoconf/Automake/Libtool/GNU Make/GCC portability path, then
compares their observable results.

## Initial implementation

The first gate provides:

- a dependency-free structure and install-parity validator in
  `scripts/aes_bld_001.py`;
- requirement-level JSON and Markdown evidence;
- a versioned JSON evidence schema;
- machine-readable local profiles and waiver logs with expiry enforcement;
- positive C library and C application reference repositories;
- regression fixtures for missing tools, empty or missing declarations,
  source/test/install/header/symbol drift, malformed evidence, and expired
  waivers;
- a 22-repository inventory containing all 16 project-owned eventual-C
  repositories and six explicit non-project-owned exclusions;
- a reusable strict/reporting workflow; and
- pre-adoption templates for downstream repositories.

## Independent CI jobs

The reusable workflow starts every required path independently. It does not
make one compiler or frontend job depend on another, and matrix
`fail-fast` is disabled. A CMake or Clang failure therefore cannot silently
skip the GNU jobs, and a GNU failure cannot silently skip Clang analysis,
sanitizers, parity, or distribution checks.

The required evidence paths are:

1. CMake, CTest, Clang, LLVM binary tools, and LLD;
2. CMake, CTest, GCC, GNU binutils, and GNU ld;
3. Autotools, GNU Make, GCC, GNU binutils, and GNU ld;
4. Autotools, GNU Make, Clang, LLVM binary tools, and LLD;
5. clang-tidy using the Clang preset's compilation database;
6. Clang ASan and UBSan;
7. staged CMake/GNU install, package or executable smoke, public-symbol
   comparison, and GNU uninstall; and
8. `make distcheck`.

CTest presets make an empty test inventory an error. The Automake jobs require
a non-empty `test-suite.log`. Each job archives its own evidence even when its
execution step fails.

## Parity boundary

The gate compares source and normative-test declarations before execution. It
then compares normalized installed path sets, public header and package
metadata content, expected payloads, and public library symbols. It runs a
consumer against each staged library or the installed smoke executable for an
application.

Compiled artifacts are not required to be byte-identical. Only profile-declared
frontend-specific metadata is excluded.

## Tool authority

The checked-in profile declares minimum version policy and explicit tool
bindings. Compliance jobs record the exact CMake, CTest, Clang, clang-tidy,
LLVM archiver, archive indexer, symbol and object inspectors, coverage and
profile-data tools, LLD, GCC, GNU binutils, GNU ld, Autoconf, Automake,
Libtool, GNU Make, and pkg-config versions they execute. The Clang and
clang-tidy major versions must agree.

The workflow resolves Clang 18, LLVM 18, LLD 18, and GCC 13 explicitly from
the pinned `ubuntu-24.04` runner image and its package repository. Clang paths
bind `llvm-ar`, `llvm-ranlib`, `llvm-nm`, `llvm-objdump`, and `ld.lld`; GCC
paths bind GNU `ar`, `ranlib`, `nm`, `objdump`, and `ld`. CMake, Autoconf,
Automake, Libtool, GNU Make, and pkg-config use the runner distribution's
stable release while retaining their exact versions in every
structure-evidence bundle.

## Rollout

1. Prove both reference projects in AEMS.
2. Move the library and application skeletons into `repo_templates`.
3. Adopt the gate in `evo` and `atarix` and baseline legitimate differences.
4. Enroll the remaining active-native repositories.
5. Add pre-adoption profiles to every planned-native repository.
6. Add ecosystem aggregation, freshness reporting, and trusted private-repo
   execution through the established `AEMS_ECOSYSTEM_TOKEN` path.

The initial repository inventory is reporting-only. A downstream repository
does not become enforcing until its local profile and caller set `strict:
true`.

## Downstream follow-up

The initial reference gate closed AEMS issue #21. Issue #23 makes the GNU and
LLVM binary-tool bindings executable and evidenced. Repository-specific
adoption remains downstream work; Evo tracks its representative adoption in
`dlworrell/evo#14`.
