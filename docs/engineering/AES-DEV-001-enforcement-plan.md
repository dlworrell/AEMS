# AES-DEV-001 Enforcement Plan

Status: Clean reporting ratchet established
Owner: AEMS
Issue: #7

## Purpose

This document describes the implemented enforcement layer for `AES-DEV-001: Development Principles and Check-In Discipline`.

AES-DEV-001 applies across project-owned repositories. It covers development process, architecture governance, documentation-first discipline, curl-style check-in behavior, observability, recovery, ADRs, and authority-model documentation.

AES-DEV-001 is separate from AES-SEC-001. AES-SEC-001 governs secure C and C++ coding rules. AES-DEV-001 governs how project work enters and evolves across the ecosystem.

## Enforcement Model

AEMS enforcement proceeds in five stages:

1. Inventory project-owned repositories.
2. Declare documentation authority for each repository.
3. Detect development-process evidence.
4. Report gaps without blocking legacy work.
5. Preserve a first ecosystem baseline and ratchet future changes toward required evidence.

The scanner is evidence-oriented. It does not attempt to prove architectural
correctness. The corrected Catalyst-tree baseline currently reports zero
evidence gaps.

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

Strict mode exists for deliberate future ratcheting. The clean reporting
baseline does not retroactively block legacy repositories.

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
- documentation authority;
- documentation reference;
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

The reporting gate fails only on checkout or scanner failure. Evidence gaps
are reported separately from infrastructure failures.

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
- documentation authority;
- delegated documentation repository;
- delegated documentation paths;
- migration status;
- ratcheting notes.

## Documentation Authority

A repository's authoritative development, specification, and ADR documentation may be:

- `local`: owned inside the repository;
- `delegated`: owned by another project repository;
- `transitional`: currently centralized elsewhere pending later migration;
- `external`: owned by an upstream third-party project.

The former transitional inventory has been reconciled. Atarix architecture
remains owned by `dlworrell/atarix`; AEMS owns enforcement and evidence;
AES owns standards; and other project repositories own their local
specifications and decisions according to the manifest. No bulk document move
is authorized by this plan.

The first ratchet rule is therefore:

```text
Every project-owned repository must declare where its authoritative development, specification, and ADR documents currently live.
```

This is deliberately weaker than requiring every repository to contain every document locally.

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

## Current Reporting Gate

The AEMS reporting gate passes when:

- repositories can be checked out;
- scans complete;
- report artifacts are produced.

Evidence gaps remain visible and do not automatically fail the gate. The
retained clean baseline is the reference point for reviewing new gaps.

## Retained Evidence

The implemented state is supported by:

```text
docs/engineering/reports/AES-DEV-001-role-aware-baseline-2026-07-06.md
docs/engineering/reports/AES-DEV-001-local-profile-adoption-2026-07-06.md
docs/engineering/reports/AES-DEV-001-clean-ratchet-2026-07-06.md
docs/engineering/reports/AES-DEV-001-migration-decision-rollup-2026-07-06.md
docs/engineering/reports/AES-DEV-001-issue-7-closure-2026-07-26.md
```

Together these artifacts record ownership correction, role-aware scanning,
required profile adoption, zero outstanding evidence gaps, and the decision
to leave already-correct documents with their repository owners.

## Future Ratchet

AEMS may ratchet toward stronger enforcement when the signal is stable:

1. Require documentation authority declarations in project-owned repositories.
2. Require local development profiles in project-owned repositories where the manifest says they are required.
3. Require specs for externally visible interfaces, either locally or by delegated reference.
4. Require ADRs for major architecture decisions, either locally or by delegated reference.
5. Require versioning evidence for interface changes.
6. Require observability and recovery sections for subsystem specifications.
7. Require trust-boundary or authority-model documentation for security-sensitive paths.
8. Require test or test-rationale evidence for meaningful changes.

## Engineering Rule

Do not turn architectural governance into a noisy checkbox machine.

First, declare where the truth lives. Then report evidence. Then preserve the baseline. Then ratchet where the signal is strong.
