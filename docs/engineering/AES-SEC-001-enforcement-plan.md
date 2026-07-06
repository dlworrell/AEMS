# AES-SEC-001 Enforcement Plan

Status: Initial
Owner: AEMS
Issue: #6

## Purpose

This document describes the next enforcement layer for `AES-SEC-001: Secure C and C++ Coding Rules`.

The policy now exists in AES and local adoption markers exist in the first wave of project repositories. AEMS is responsible for turning that policy into repeatable evidence.

## Enforcement Model

AEMS enforcement proceeds in four stages:

1. Inventory repositories.
2. Classify native-code and hardware/tooling surfaces.
3. Detect adoption and safety signals.
4. Report violations, waivers, and follow-up work.

The initial scanner is intentionally local-checkout based. This keeps it simple, reproducible, and independent of GitHub API behavior. A later AEMS runner may clone or fetch each repository automatically and aggregate reports.

## Scanner

The initial scanner is:

```text
scripts/aes_sec_001_scan.py
```

It reports:

- whether `docs/engineering/SECURE-C-CXX.md` exists;
- whether C, C++, Objective-C, Objective-C++, assembly, or include files are present;
- whether hardware/FPGA files are present;
- whether native build surfaces are present;
- whether static-analysis signals exist;
- whether sanitizer signals exist;
- whether fuzzing signals exist;
- whether waiver signals exist;
- whether banned C/C++ APIs appear in project-owned source files.

## Basic Use

From a repository checkout:

```sh
python3 scripts/aes_sec_001_scan.py . --repo-name dlworrell/AEMS --format markdown
```

For strict CI behavior:

```sh
python3 scripts/aes_sec_001_scan.py . --repo-name dlworrell/AEMS --strict
```

Strict mode exits non-zero when the local secure-coding profile is missing or banned APIs are detected.

## Dangerous Primitive Review

By default, the scanner reports only APIs banned by AES-SEC-001.

To also report dangerous-but-sometimes-necessary primitives such as `memcpy`, `malloc`, `free`, and `snprintf`, run:

```sh
python3 scripts/aes_sec_001_scan.py . --include-dangerous-primitives --format markdown
```

Those results are review-required findings, not automatic failures unless a local repository profile elevates them.

## Repository Manifest

The repository manifest is:

```text
config/aes-sec-001-repositories.json
```

It identifies project-owned repositories, template repositories, documentation/governance repositories, and third-party mirrors/forks.

Third-party mirrors must not be rewritten as if they were project-owned code. Local patches to mirrors should be tracked separately.

## Minimum Adoption Gate

A repository passes the minimum adoption gate when:

- its expected local secure profile exists; and
- no banned API findings are detected in project-owned native code.

This is deliberately weaker than final compliance. It establishes a non-noisy first enforcement layer.

## Future Work

AEMS still needs these follow-up pieces:

- repository checkout/fetch orchestration;
- aggregate report generation across all manifest entries;
- CI workflow templates for native-code repositories;
- waiver-log template generation;
- CodeQL or equivalent static-analysis workflow templates;
- sanitizer build presets for CMake, Make, and Meson projects;
- fuzz-harness discovery and smoke-test execution;
- banned API detection that understands comments, generated code, vendored code, and local waiver markers more precisely.

## Engineering Rule

Do not turn every warning on everywhere at once.

Adoption should ratchet:

1. detect;
2. report;
3. baseline legacy violations;
4. block new violations;
5. eliminate waivers over time.
