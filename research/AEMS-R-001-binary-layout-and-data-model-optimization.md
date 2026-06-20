# AEMS-R-001 – Binary Layout and Data Model Optimization

Status: Research

## Purpose

This research note records an optimization path for lookup-heavy binaries that combine:

- hash table or lookup acceleration paths
- explicit data model versioning
- endian conversion between stored data and host execution format
- post-link binary layout optimization
- profile-guided evidence collection

The goal is not to mandate a toolchain. The goal is to preserve the investigation path, constraints, and acceptance criteria.

## Governing Rule

Engineering is evidence, not opinion.

AEMS should not assume that a binary layout optimization, packed data structure, branch hint, or endian transformation improves the system merely because it appears theoretically favorable.

The optimization is accepted only if measurement shows improvement without breaking portability, correctness, or traceability.

## Context

Lookup engines often contain biased execution paths:

- hot path: hash computation, primary bucket probe, successful match
- warm path: short collision path or secondary comparison
- cold path: resize, malformed data, missing key, error handling, recovery

This makes the code a plausible candidate for profile-guided optimization and post-link layout tools.

## Post-Link Binary Layout Optimization

LLVM BOLT is the primary modern tool to investigate for ELF targets.

BOLT optimizes an already-linked binary using execution profiles. It can reorder basic blocks and functions, split hot and cold code, and improve instruction-cache and translation-lookaside-buffer behavior when a program has measurable front-end pressure.

Important constraints:

- BOLT currently targets X86-64 and AArch64 ELF binaries.
- The input binary should retain symbols.
- Maximum benefit generally requires preserved relocation metadata, such as `--emit-relocs` or equivalent linker options.
- Profiles must be representative of real workloads.
- Stale profiles must be treated as degraded evidence.

## Candidate Linux BOLT Pipeline

```sh
clang -O3 -g -Wl,--emit-relocs hash_table.c lookup_core.c -o lookup_engine

perf record -e cycles:u -j any,u -o perf.data -- ./lookup_engine --benchmark representative

perf2bolt -p perf.data -o lookup_engine.fdata lookup_engine

llvm-bolt lookup_engine \
  -o lookup_engine.bolt \
  -data=lookup_engine.fdata \
  -reorder-blocks=ext-tsp \
  -reorder-functions=cdsort \
  -split-functions \
  -split-all-cold \
  -split-eh \
  -dyno-stats
```

This pipeline is a research candidate, not yet a project standard.

## Native PGO Alternative

Compiler-native PGO should also be evaluated.

```sh
clang -O3 -fprofile-generate=profiles hash_table.c lookup_core.c -o lookup_engine.instrumented

./lookup_engine.instrumented --benchmark representative

llvm-profdata merge -output=lookup_engine.profdata profiles/*.profraw

clang -O3 -fprofile-use=lookup_engine.profdata hash_table.c lookup_core.c -o lookup_engine.pgo
```

PGO and BOLT should be compared separately and together where practical.

## Endianness Handling

Stored data format must not be confused with host execution format.

For fixed-width integer conversion, GCC and Clang support byte-swap builtins such as:

```c
__builtin_bswap16(x)
__builtin_bswap32(x)
__builtin_bswap64(x)
```

These are preferable to hand-written shift-and-mask macros when the compiler can lower them to efficient target instructions.

Endian conversion should occur at explicit boundaries:

- file or wire format ingestion
- serialized data model decoding
- hash key normalization
- version migration
- output serialization

Internal hot-path lookup code should operate on normalized host-order values unless measurement proves otherwise.

## Data Model Layout

Data model layout must be explicit and testable.

Packed structures may be useful for serialized on-disk or wire-format records, but they should not be used casually as in-memory hot-path structures.

Packed layout can create unaligned accesses, reduce compiler freedom, and cause traps or penalties on some targets.

Recommended pattern:

1. Define serialized record layout explicitly.
2. Decode serialized data into an aligned host-native structure.
3. Run hot lookup logic on host-native structures.
4. Encode back to serialized form only at boundaries.

Example serialized record:

```c
#include <stdint.h>

struct __attribute__((packed)) atx_hash_entry_v1_disk {
    uint32_t hash_key_be;
    uint16_t version_id_be;
    uint8_t flags;
};
```

Example host-native record:

```c
#include <stdint.h>
#include <stdalign.h>

struct alignas(64) atx_hash_entry_v1_host {
    uint32_t hash_key;
    uint16_t version_id;
    uint8_t flags;
};
```

The project should use compile-time assertions to preserve layout assumptions:

```c
_Static_assert(sizeof(struct atx_hash_entry_v1_disk) == 7, "unexpected disk record size");
_Static_assert(_Alignof(struct atx_hash_entry_v1_host) == 64, "unexpected host record alignment");
```

## Cross-Compilation

Clang can cross-compile by selecting a target triple:

```sh
clang -target mips-linux-gnu -O3 hash_table.c lookup_core.c -o lookup_engine.mips
clang -target powerpc-unknown-linux-gnu -O3 hash_table.c lookup_core.c -o lookup_engine.ppc
```

GCC cross-compilation generally depends on a target-specific compiler and binutils/sysroot arrangement:

```sh
powerpc-linux-gnu-gcc -mbig-endian -O3 hash_table.c lookup_core.c -o lookup_engine.elf
```

The `-mbig-endian` flag is target-specific. It should not be documented as a universal GCC option.

## Link-Time Optimization

LTO may improve lookup code by allowing cross-translation-unit inlining and dead-code elimination.

```sh
gcc -O3 -flto hash_table.c lookup_core.c -o lookup_engine.gcc.lto
clang -O3 -flto=thin hash_table.c lookup_core.c -o lookup_engine.clang.thinlto
```

Do not combine LTO, PGO, and BOLT into one assumed-good build by default. Evaluate them incrementally so performance changes remain attributable.

## Measurement Plan

AEMS should capture at least:

- wall-clock benchmark time
- CPU cycles
- instructions retired
- branch misses
- L1 instruction-cache misses
- iTLB misses, where available
- binary size
- resident set size, where relevant
- page faults, where relevant
- correctness test results

Candidate Linux measurement commands:

```sh
perf stat -e cycles,instructions,branches,branch-misses,L1-icache-load-misses \
  ./lookup_engine --benchmark representative
```

Additional events may vary by CPU and kernel.

## Acceptance Criteria

The optimization path may advance from research to standard only if:

1. Correctness tests pass before and after optimization.
2. The benchmark workload is documented and reproducible.
3. The optimized binary shows measurable improvement on relevant hardware.
4. The improvement is not offset by unacceptable binary size, portability, or maintainability costs.
5. The build pipeline records compiler version, linker version, target triple, profile source, and benchmark command.
6. The resulting artifact can be reproduced from committed instructions.

## Risks

- Representative profiles may be difficult to collect.
- Packed structures may introduce unaligned-access penalties or traps.
- Branch prediction hints may be wrong; real PGO should be preferred where available.
- Cross-compilation may require target sysroots, libraries, and linkers not captured by a simple compiler command.
- BOLT support is target-format dependent and should not be assumed for every operating system or executable format.
- Data model migration can silently fail if structure size, alignment, or endian assumptions are not tested.

## Research Conclusion

This optimization path is promising for lookup-heavy AEMS-adjacent tooling, but it must remain evidence-gated.

The project should first define the data model, serialization boundaries, correctness tests, and benchmark workload. Only then should PGO, LTO, or BOLT be promoted from experiment to standard build procedure.
