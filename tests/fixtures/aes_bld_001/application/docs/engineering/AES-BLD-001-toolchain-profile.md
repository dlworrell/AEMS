# AES-BLD-001 Reference C Application Profile

This synthetic active-native application is AEMS's positive reference for the
independent CMake/CTest/Clang and Autoconf/Automake/GNU Make/GCC paths.

- Language: C17
- Canonical presets: `aes-clang`, `aes-gcc`, `aes-clang-sanitizers`
- GNU bootstrap: `autoreconf -fvi`
- GNU builds: out-of-tree with both GCC and Clang
- Normative test: `tests/test_app.c`
- Installed smoke surface: `bin/aes_fixture_app`
- Distribution: `make distcheck`
- Waivers: `.aems/aes-bld-001-waivers.json`
