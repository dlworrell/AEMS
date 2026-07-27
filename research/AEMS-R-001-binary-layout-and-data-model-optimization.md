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

## Host Tooling Versus 65C816 Target Code

BOLT, native compiler PGO, `perf`, and ELF relocation analysis apply to modern
host tools, emulators, builders, and analysis programs. They do not apply
directly to the final 65C816 kernel image.

The target equivalent is a measured layout discipline implemented before or
during linking:

- explicit hot, warm, and cold segments;
- bank-local placement of common call paths and their data;
- deliberate use of short calls within a program bank and long calls only
  across a measured boundary;
- explicit direct-page ownership and lifetime;
- explicit stack reservations in bank 0;
- stable serialized layouts separated from execution structures; and
- map-file and image analysis retained with benchmark evidence.

No host optimization result may be cited as evidence for target improvement.
Host and target measurements require separate artifacts, commands, and
conclusions.

## 65C816 Execution Constraints

The W65C816S presents a 24-bit address space through separate program-bank and
data-bank state. The program counter remains bank-local; ordinary branches and
short subroutine calls therefore do not replace deliberate cross-bank
placement. The data bank affects ordinary data references, while stack,
direct-page, and interrupt behavior retain bank-0 constraints.

The layout model must account for:

- program-bank boundaries and the cost and correctness of `JSL`/`RTL` or long
  jump paths;
- data-bank state at every public entry point and interrupt boundary;
- direct page residing in bank 0, with ownership explicit for tasks,
  interrupt handlers, and kernel services;
- stack and interrupt entry in bank 0;
- accumulator and index widths controlled by M and X state;
- callable interfaces that document required processor mode, register widths,
  data bank, direct page, and clobbers;
- `MVN`/`MVP` changing the data-bank register as a visible side effect;
- serialized 24-bit pointers or offsets never being mistaken for a host C
  pointer; and
- emulator cycle counts being calibrated against target-hardware observations
  before they support a final performance claim.

Every assembly module should either establish its required M/X and bank state
or declare those preconditions in a mechanically checkable interface
convention. A benchmark that enters with undocumented processor state is not
reproducible evidence.

## Candidate 65C816 Toolchains

Toolchain selection remains an experiment. AEMS records comparable evidence;
Atarix owns the final target-toolchain and kernel-layout decision.

| Candidate | Current 65C816 surface | Appropriate evaluation role | Required qualification |
|---|---|---|---|
| `ca65` / `ld65` | `ca65` accepts 65816 assembly and `ld65` provides configurable segments and memory areas | Assembly-first reference pipeline and linker-layout experiments | Do not describe the `cc65` C compiler as a native 65C816 C solution without separate evidence; verify emitted modes, bank placement, relocation behavior, map output, and debugger/emulator integration |
| WDC tools | WDC supplies a 65C816 assembler, linker, librarian, and WDC816 C compiler family | Vendor-reference ABI, object, and C-code-generation comparison | Record exact edition, host support, license, optimization settings, object format, diagnostics, and reproducible installation inputs |
| `vbcc` 65816 | Current distribution lists a 65816 compiler, assembler, linker, libraries, and simulator/SNES/Apple IIgs surfaces | Retargetable C and assembly comparison | Pin the distribution/source revision, define the Atarix memory model and runtime, and measure generated code rather than inferring quality from target availability |
| `llvm-mos` | Current Clang documentation exposes `--target=mos` and `-mcpu=mosw65816` with a freestanding C surface | Modern IR-based experimental compiler, diagnostics, and differential-code-generation candidate | Pin the revision; treat the backend and ABI as evolving; prove instruction, relocation, bank, M/X-state, and runtime behavior with focused tests |
| Calypsi | Current toolchain lists a WDC 65816 target, ISO C99-oriented compiler, debugger, and target support packages | Independent commercial/closed-source comparison and debugger reference | Record version, host constraints, hobby/commercial license boundary, ABI, runtime, reproducibility limits, and whether retained binaries can be rebuilt later |
| `64tass` and related assemblers | Assembly-only 65xx tools can provide independent encoding and image comparisons | Differential assembly, fixture generation, and minimal bring-up | Pin exact version and syntax mode; do not infer linker, ABI, C, or whole-program optimization support from opcode support |

The comparison must not collapse “accepts 65816 opcodes,” “generates 65816 C,”
“links a banked kernel image,” and “supports the Atarix ABI” into one claim.
Each is a separate capability with separate evidence.

## Target Benchmark and Evidence Matrix

Before any layout or toolchain choice becomes architecture, compare at least
these target workloads:

1. same-bank leaf call and return;
2. cross-bank call and return;
3. direct-page versus absolute and long data access;
4. fixed-size copy within a bank and across banks;
5. hash lookup with hit, short-collision, miss, and malformed-input paths;
6. interrupt entry, service, and return under the declared M/X and bank
   convention;
7. serialized-record decode into a host-native target structure; and
8. representative kernel service dispatch.

For every candidate, retain:

- source revision and toolchain archive or immutable provenance;
- compiler, assembler, linker, librarian, and emulator versions;
- complete command lines and configuration files;
- ABI, calling convention, integer model, pointer model, and structure-layout
  declarations;
- binary image, symbol/map file, section and bank placement, and digest;
- static instruction bytes and size;
- emulator cycles with emulator identity and configuration;
- target hardware, clock, wait-state, memory, and measurement method;
- correctness, boundary, and negative test results;
- differences from the reference implementation; and
- a conclusion limited to the measured workload.

Evidence should compare correctness first, then code size, cycle count, bank
crossings, direct-page pressure, stack high-water mark, and build
reproducibility. A compiler that wins one microbenchmark but cannot express or
verify the kernel ABI does not win the toolchain decision.

## Architecture Disposition

This AEMS note remains the research registry and evidence contract.

Material should move into Atarix only after a reviewed target decision:

- the selected toolchain, ABI, memory model, and bank convention belong in an
  Atarix architecture specification or ADR;
- kernel linker scripts and target benchmarks belong in Atarix;
- measured evidence belongs with the producing Atarix commit and may be
  indexed by AEMS; and
- comparative experiments that have not been adopted remain here or in the
  repository that ran them.

Moving a conclusion does not require deleting this note. This note preserves
the alternatives, evidence requirements, and provenance of the decision.

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

This optimization path is promising for lookup-heavy AEMS-adjacent host
tooling and for bank-aware 65C816 target layout, but those are separate
experiments and must remain evidence-gated.

The project should first define the data model, serialization boundaries,
correctness tests, target ABI, processor-state convention, and benchmark
workload. Only then should host PGO/LTO/BOLT or a target toolchain/layout
technique be promoted from experiment to an adopted build procedure.

## Primary References

- WDC, [W65C816S data sheet](https://www.westerndesigncenter.com/wdc/documentation/w65c816s.pdf).
- WDC, [65xx software development tools](https://www.westerndesigncenter.com/wdc/tools.cfm).
- cc65 project, [ca65 users guide](https://cc65.github.io/doc/ca65.html).
- cc65 project, [ld65 users guide](https://cc65.github.io/doc/ld65.html).
- vbcc project, [portable ISO C compiler and 65816 target](https://www.compilers.de/vbcc.html).
- llvm-mos, [C compiler target documentation](https://llvm-mos.org/wiki/C_compiler).
- Calypsi, [toolchain targets and licensing](https://www.calypsi.cc/).
- 64tass project, [cross-assembler distribution](https://sourceforge.net/projects/tass64/).
