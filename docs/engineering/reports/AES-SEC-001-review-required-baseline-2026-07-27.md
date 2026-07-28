# AES-SEC-001 Review-Required Baseline — 2026-07-27

## Purpose

This report retains the first ecosystem-wide dangerous-primitive inventory
after every project-owned future-C repository entered the AES-SEC-001 rollout.
It is evidence for the review-disposition migration tracked by AEMS issue 18;
it is not a waiver and it does not approve any listed operation.

## Provenance

- Workflow run: `30327790203`
- Artifact: `aes-sec-001-ecosystem-30327790203`
- Artifact identifier: `8676292176`
- Artifact digest:
  `sha256:d29ea776a6ccf9f5e40e92597235ffedf7ddb35e5364b68ca57f5a3bdda97679`
- Manifest repositories: `22`
- Project-owned repositories scanned: `16`
- Checkout failures: `0`
- Minimum-adoption gate failures: `0`
- Banned findings: `0`
- Review-required findings: `56`
- Aggregate result: `PASS`

The July 6 adoption report predates the expanded dangerous-primitive detector.
The increase from zero reported review findings to 56 is therefore a detector
surface change, not evidence that 56 regressions were introduced.

## Retained Baseline

| Repository | Findings | Production | Test | Symbols |
|---|---:|---:|---:|---|
| `dlworrell/atarix` | 49 | 22 | 27 | `memset` 40, `memcpy` 6, `malloc` 1, `free` 2 |
| `dlworrell/code-noodling` | 2 | 2 | 0 | `memset` 2 |
| `dlworrell/audiblebooks` | 3 | 0 | 3 | `snprintf` 3 |
| `dlworrell/evo` | 2 | 2 | 0 | `calloc` 1, `free` 1 |
| **Total** | **56** | **26** | **30** | |

The source artifact contains the repository, symbol, path, line, source text,
and remediation for every finding. The 56 repository, symbol, path, line, and
source-text records are retained beside this report in
`AES-SEC-001-review-required-baseline-2026-07-27.json`.
Repository-local migrations must capture
the scanner-generated `finding_id` and `source_fingerprint` in
`docs/engineering/AES-SEC-001-review-dispositions.json`; line numbers in this
report are evidence locators, not stable identities.

## Migration State

Review-ratchet enforcement is intentionally disabled while this baseline is
being classified. The migration order is:

1. `dlworrell/evo`
2. `dlworrell/code-noodling`
3. `dlworrell/audiblebooks`
4. `dlworrell/atarix`

After every retained finding has a repository-owned disposition, AEMS may
enable the blocking ratchet. At that point new, unresolved, source-drifted, or
stale entries fail while the banned-API gate continues to fail immediately.
