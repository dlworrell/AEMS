# Atarix AEMS v0.1 Origin

Status: Historical
Canonical repository: `dlworrell/AEMS`
Source repository: `dlworrell/atarix`
Original path: `tools/aems/README.md`

## Purpose

The original Atarix Engineering Management System, or AEMS, was conceived as a repository-native engineering assistant for keeping specifications, reviews, issues, implementation work, and engineering gates synchronized.

The initial implementation was intentionally small, deterministic, auditable, scriptable, and safe to run in CI.

## Initial Commands

The Atarix-local prototype exposed commands equivalent to:

```sh
python3 tools/aems/aems.py list-specs
python3 tools/aems/aems.py check-specs
python3 tools/aems/aems.py next
python3 tools/aems/aems.py report
```

## Initial Scope

AEMS v0.1 tracked:

- specification IDs;
- specification titles;
- specification file paths;
- status values;
- dependency lists;
- related issue numbers;
- engineering notes.

## Initial Non-goals

The v0.1 prototype did not mutate GitHub Projects, close issues, create labels, or edit milestones. Those features were deferred until the local registry and validation flow became stable.

## Design Rules

- Markdown remains human-readable.
- JSON registries remain machine-readable.
- CI output must be deterministic.
- Missing files are failures.
- Missing issue links are warnings until issue synchronization exists.
- Specification dependency drift should be detected early.

## Planned Growth

The original plan anticipated:

- GitHub issue synchronization;
- GitHub Projects v2 synchronization;
- architecture dependency graph export;
- review-status tracking;
- engineering-gate integration;
- release and tag report generation;
- stale-issue detection;
- duplicate-issue detection;
- specification reconciliation checks.

## Migration Note

This document preserves the provenance of the Atarix-local AEMS prototype. AEMS is now a separate project-management, compliance, and enforcement repository governed by Catylist and implementing AES obligations. The original Atarix README is no longer authoritative.
