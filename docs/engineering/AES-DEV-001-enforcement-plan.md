# AES-DEV-001 Enforcement Plan

Status: Initial
Owner: AEMS
Issue: #7

## Purpose

This document describes the first enforcement layer for `AES-DEV-001: Development Principles and Check-In Discipline`.

AES-DEV-001 applies across project-owned repositories. It covers development process, architecture governance, documentation-first discipline, curl-style check-in behavior, observability, recovery, ADRs, and authority-model documentation.

AES-DEV-001 is separate from AES-SEC-001. AES-SEC-001 governs secure C and C++ coding rules. AES-DEV-001 governs how project work enters and evolves across the ecosystem.

## Enforcement Model

AEMS enforcement proceeds in five stages:

1. Inventory project-owned repositories.
2. Detect development-process evidence.
3. Report gaps without blocking legacy work.
4. Preserve a first ecosystem baseline.
5. Ratchet future changes toward required evidence.

The first scanner is evidence-oriented. It does not attempt to prove architectural correctness.

## Local Scanner

The local scanner is:

```text
scripts/aes_dev_001_scan.py
```

It reports:

- whether a local development-principles profile exists;
- whether specification or architecture directories exist;
- whether ADR directories exist;
- documentation file count;
- versioning evidence;
- observability evidence;
- recovery evidence;
- security, trust-boundary, or authority-model evidence;
- check-in discipline evidence.

## Local Scanner Use

From a repository checkout:

```sh
python3 scripts/aes_dev_001_scan.py . --repo-name dlworrell/AEMS --format markdown
```

JSON output:

```sh
python3 scripts/aes_dev_001_scan.py . --repo-name dlworrell/AEMS --format json
```

Strict mode exists only for future ratcheting. In the initial phase it should not be used to block legacy repositories for missing evidence.

## Aggregate Runner

The aggregate runner is:

```text
scripts/aes_dev_001_aggregate.py
```

It reads:

```text
config/aes-dev-001-repositories.json
```

For each manifest entry, it records:

- repository name;
- role;
- ownership classification;
- checkout or scan status;
- local profile status;
- specification-directory status;
- ADR-directory status;
- evidence category count;
- ratchet readiness;
- evidence gaps.

By default, third-party mirror/fork repositories are listed but not scanned. Use `--include-third-party` only when third-party inventory evidence is needed.

Manual use from AEMS:

```sh
python3 scripts/aes_dev_001_aggregate.py --format markdown
```

The initial reporting gate fails only on checkout or scanner failure. Evidence gaps are reported, not hard failures.

## Repository Manifest

The AES-DEV-001 repository manifest is:

```text
config/aes-dev-001-repositories.json
```

This manifest is separate from the AES-SEC-001 manifest because development-process expectations differ from secure-C/C++ expectations.

The manifest supports:

- project-owned repositories;
- third-party mirrors/forks;
- optional local profile paths;
- whether a local profile is currently required;
- ratcheting notes.

## Evidence Categories

The initial scanner reports five evidence categories:

- versioning;
- observability;
- recovery;
- security and authority;
- check-in discipline.

These are keyword-based evidence signals. They are not proof of design quality.

A repository can therefore have evidence and still need design work. The purpose of this phase is to make the gaps visible.

## Local Profiles

The ecosystem-wide governing standard is:

```text
dlworrell/AES/standards/AES-DEV-001-development-principles-and-check-in-discipline.md
```

A project may add a local profile when it needs more specific rules.

For example, ATARIX has:

```text
dlworrell/atarix/docs/engineering/ATARIX-DEV-001-development-principles.md
```

Local profiles extend the ecosystem standard. They should not weaken it without an ADR or waiver.

## Minimum Initial Reporting Gate

The initial AEMS reporting gate passes when:

- repositories can be checked out;
- scans complete;
- report artifacts are produced.

Evidence gaps do not initially fail the gate.

## Future Ratchet

AEMS should later ratchet toward stronger enforcement:

1. Require local development profiles in project-owned repositories.
2. Require specs for externally visible interfaces.
3. Require ADRs for major architecture decisions.
4. Require versioning evidence for interface changes.
5. Require observability and recovery sections for subsystem specifications.
6. Require trust-boundary or authority-model documentation for security-sensitive paths.
7. Require test or test-rationale evidence for meaningful changes.

## Engineering Rule

Do not turn architectural governance into a noisy checkbox machine.

First, report evidence. Then preserve the baseline. Then ratchet where the signal is strong.
