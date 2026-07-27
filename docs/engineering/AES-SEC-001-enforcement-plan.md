# AES-SEC-001 Enforcement Plan

Status: Implemented reporting ratchet
Owner: AEMS
Issues: #6, #12

## Purpose

This document describes the implemented enforcement layer for `AES-SEC-001: Secure C and C++ Coding Rules`.

The policy exists in AES. AEMS turns it into repeatable adoption, source,
native-control, and ecosystem evidence.

## Enforcement Model

AEMS enforcement proceeds in four stages:

1. Inventory repositories.
2. Classify native-code and hardware/tooling surfaces.
3. Detect adoption and operational safety signals.
4. Report violations, waivers, and follow-up work.

The local scanners are checkout based. The aggregate runner reads the
repository manifest, checks out governed repositories, runs the adoption
scanner, writes an ecosystem report, and can emit one JSON and one Markdown
report for each manifest entry.

## Local Scanner

The local scanner is:

```text
scripts/aes_sec_001_scan.py
```

It reports:

- whether `docs/engineering/SECURE-C-CXX.md` exists;
- whether `docs/engineering/AES-SEC-001-waivers.md` exists;
- whether C, C++, Objective-C, Objective-C++, assembly, or include files are present;
- whether hardware/FPGA files are present;
- whether native build surfaces are present;
- whether operational static-analysis signals exist;
- whether operational sanitizer signals exist;
- whether operational fuzzing signals exist;
- whether explicit waiver-log files exist;
- whether banned C/C++ APIs appear in project-owned source files;
- whether review-required native primitives appear when requested.

## Local Scanner Use

From a repository checkout:

```sh
python3 scripts/aes_sec_001_scan.py . --repo-name dlworrell/AEMS --format markdown
```

For strict CI behavior:

```sh
python3 scripts/aes_sec_001_scan.py . --repo-name dlworrell/AEMS --strict
```

Strict mode exits non-zero when the minimum adoption gate fails.

## Aggregate Runner

The aggregate runner is:

```text
scripts/aes_sec_001_aggregate.py
```

It reads:

```text
config/aes-sec-001-repositories.json
```

For each manifest entry, it records:

- repository name;
- role;
- ownership classification;
- checkout or scan status;
- local scanner classification;
- secure profile status;
- waiver log status;
- banned finding count;
- review-required finding count;
- assigned native-control profile; and
- minimum adoption gate result.

By default, third-party mirror/fork repositories are listed but not scanned. Use `--include-third-party` when third-party inventory evidence is needed.

Manual use from AEMS:

```sh
python3 scripts/aes_sec_001_aggregate.py --format markdown
```

To retain repository-scoped evidence:

```sh
python3 scripts/aes_sec_001_aggregate.py \
  --format json \
  --per-repository-dir build/aes-sec-001/repositories
```

Strict aggregate use:

```sh
python3 scripts/aes_sec_001_aggregate.py --strict --format markdown
```

The strict aggregate gate fails only when an expected project-owned repository fails its expected adoption gate or cannot be scanned.

### Private Repository Authentication

The aggregate runner shares the credential-safe checkout implementation used
by AES-DEV-001. By default, it reads an optional token from:

```text
AEMS_ECOSYSTEM_TOKEN
```

The token is carried in a process-local Git HTTP authorization header rather
than a clone URL and is redacted from checkout errors. Git terminal prompting
is disabled.

For a strict trusted run:

```sh
AEMS_ECOSYSTEM_TOKEN=... \
  python3 scripts/aes_sec_001_aggregate.py \
    --strict \
    --require-github-token \
    --format markdown
```

The token should be fine-grained and limited to read-only `Contents` access for
the project-owned repositories in the manifest. GitHub Actions reads the
`AEMS_ECOSYSTEM_TOKEN` secret only for trusted `push` and
`workflow_dispatch` events.

Pull-request ecosystem scans run without the cross-repository credential and
remain report-only. Strict ecosystem enforcement is limited to trusted manual
dispatch. A manual dispatch skips the ecosystem job only when
`ecosystem_scan=false`.

## GitHub Actions

The workflow is:

```text
.github/workflows/aes-sec-001-scan.yml
```

It runs the local scanner on pull requests, pushes to `main`, and manual dispatch.

Manual dispatch also supports an optional ecosystem scan:

- `ecosystem_scan=true` runs the aggregate manifest scan;
- `include_third_party=true` also scans repositories classified as third-party mirrors/forks;
- `include_dangerous_primitives=true` includes review-required native primitives;
- `strict=true` enforces the relevant gate.

Workflow reports are uploaded before strict gate enforcement so that failed strict runs still leave reviewable JSON and Markdown artifacts.

## Native-Control Profiles and Presets

The profile catalogue is:

```text
config/aes-sec-001-native-profiles.json
```

It assigns language-appropriate warning, static-analysis, sanitizer, and
fuzzing expectations. Current profile identifiers are:

- `c17-kernel`;
- `c17-library`;
- `cpp17-bridge`; and
- `experimental-native`.

Profiles describe control intent. A repository must still attach the selected
flags and tools to its own build targets and preserve the resulting evidence.

Reusable, opt-in presets are:

```text
templates/native/aes-sec-001-cmake.cmake
templates/native/aes-sec-001.mk
templates/native/aes-sec-001-meson.ini
templates/native/aes-sec-001-native.example.json
templates/workflows/aes-sec-001-native.yml
```

The presets apply to project-owned code and supported host tests. They do not
silently rewrite upstream, vendored, target-only, or toolchain-incompatible
code.

## Native-Control Discovery and Fuzz Smoke

The native-control helper is:

```text
scripts/aes_sec_001_native.py
```

It reports discovered build systems and operational warning,
static-analysis, sanitizer, and fuzz-harness signals. With `--run-controls`,
it runs explicitly declared `warnings`, `static-analysis`, and
`sanitizer-test` commands. With `--smoke`, it runs only explicitly declared
fuzz targets. Both are configured in:

```text
.aems/aes-sec-001-native.json
```

Commands are argument arrays, run without a shell, use bounded timeouts, and
retain stdout, stderr, exit status, category, and target identity. Discovery
does not claim runtime coverage. A passing control or smoke target proves only
that the declared bounded command completed successfully.

## Review-Required Primitive Review

By default, the scanner reports only APIs banned by AES-SEC-001.

To also report dangerous-but-sometimes-necessary primitives such as `memcpy`, `malloc`, `free`, and `snprintf`, run:

```sh
python3 scripts/aes_sec_001_scan.py . --include-dangerous-primitives --format markdown
```

The aggregate workflow can run the same review mode through manual dispatch by setting:

```text
include_dangerous_primitives=true
strict=false
ecosystem_scan=true
include_third_party=false
```

Those results are review-required findings, not automatic failures unless a local repository profile elevates them. The aggregate Markdown report includes both a per-repository review finding count and a detailed review-required findings table.

## Operational Signal Rules

The scanner distinguishes operational evidence from documentation mentions.

Operational evidence is counted only when it appears in relevant configuration, workflow, build, script, or source files. Mentions inside general documentation, generated scan reports, or the scanner implementation itself are not counted as proof of coverage.

The current operational-signal categories are:

- static analysis: `.clang-tidy`, CodeQL configuration, or workflow/build/script references to tools such as `clang-tidy`, `cppcheck`, `CodeQL`, `coverity`, or `pvs-studio`;
- sanitizers: workflow/build/script references to `-fsanitize`, AddressSanitizer, UndefinedBehaviorSanitizer, or ThreadSanitizer;
- fuzzing: native fuzz entry points such as `LLVMFuzzerTestOneInput`, or workflow/build/source files explicitly tied to fuzzing;
- waivers: explicit waiver files such as `docs/engineering/AES-SEC-001-waivers.md`.

## Waiver Log

The default waiver log is:

```text
docs/engineering/AES-SEC-001-waivers.md
```

This file must exist even when there are no approved waivers. An empty waiver log should say that no waivers are currently approved.

## Repository Manifest

The repository manifest is:

```text
config/aes-sec-001-repositories.json
```

It identifies project-owned repositories, template repositories, documentation/governance repositories, and third-party mirrors/forks.

Third-party mirrors must not be rewritten as if they were project-owned code. Local patches to mirrors should be tracked separately.

External/reference repositories are also inventoried without being treated as
governed project code. Reclassification requires a Catylist ownership
decision, followed by a manifest change and new baseline evidence.

## Minimum Adoption Gate

A repository passes the minimum adoption gate when:

- its expected local secure profile exists;
- its explicit waiver log exists; and
- no banned API findings are detected in project-owned native code.

This is deliberately weaker than final compliance. It establishes a non-noisy first enforcement layer.

## Implemented Baseline and Remaining Ratchets

The first clean adoption baseline is retained at:

```text
docs/engineering/reports/AES-SEC-001-ecosystem-baseline-2026-07-06.md
```

The profile/control implementation and current ownership corrections are
reconciled at:

```text
docs/engineering/reports/AES-SEC-001-control-profile-rollup-2026-07-26.md
```

Remaining ratchets are deliberately narrower:

- adopt the selected profile and workflow in each active native repository
  through repository-owned changes;
- classify review-required primitives by wrapper, invariant, or planned
  replacement;
- improve source parsing around comments, generated code, and local waiver
  markers; and
- baseline newly enrolled repositories before enabling a blocking gate.

## Engineering Rule

Do not turn every warning on everywhere at once.

Adoption should ratchet:

1. detect;
2. report;
3. baseline legacy violations;
4. block new violations;
5. eliminate waivers over time.
