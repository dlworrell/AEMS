# AES-BLD-001 Toolchain Profile

Status: Reference
Repository: `aems/reference-c-library`
Standard: `AES-BLD-001`

## Authority

This fixture implements the AES standard from `dlworrell/AES`. It is test
evidence for AEMS and does not redefine the normative requirements.

## Language and Frontends

- Language: ISO C17
- Canonical developer frontend: CMake and CTest
- Canonical diagnostics toolchain: Clang, clang-tidy, ASan, and UBSan
- GNU portability frontend: Autoconf, Automake, Libtool, and GNU Make
- GNU portability compiler: GCC

CMake and Autotools operate independently over the same source and test files.

## Commands

The canonical presets are `aes-clang`, `aes-gcc`, and
`aes-clang-sanitizers`.

The GNU path bootstraps with `autoreconf -fvi`, configures out of tree, runs
`make check`, stages installation through `DESTDIR`, supports `make uninstall`,
and validates the source archive with `make distcheck`.

## Parity

Both frontends build `src/fixture.c`, execute `tests/test_fixture.c`, install
the same public header, static library, and pkg-config file, and support the
consumer in `consumer/consumer.c`.

Libtool's installed `.la` metadata is the only declared frontend-specific
install exclusion. Compiled archives need not be byte-identical, but their
exported symbol sets must agree.

## Waivers

No waivers are approved for the reference fixture.
