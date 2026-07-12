# Machine-Readable Compliance Evidence

Status: Active
Owner: AEMS
Schema: `catalyst.aems.compliance-evidence.v1`

## Purpose

AEMS compliance scans produce two complementary artifacts:

- Markdown for human review;
- JSON for automation, historical comparison, dashboards, and regression detection.

The JSON artifact is the canonical machine-readable evidence record. It wraps the raw scanner result with provenance and execution metadata.

## Required Artifact Names

For each standard, repositories should publish paired artifacts:

```text
reports/aes-dev-001.md
reports/aes-dev-001.json
reports/aes-sec-001.md
reports/aes-sec-001.json
```

## Evidence Envelope

```json
{
  "schema": "catalyst.aems.compliance-evidence.v1",
  "standard": {
    "id": "AES-DEV-001",
    "version": "<AES repository commit SHA>"
  },
  "subject": {
    "repository": "owner/name",
    "commit_sha": "<scanned commit SHA>"
  },
  "scanner": {
    "repository": "dlworrell/AEMS",
    "commit_sha": "<scanner commit SHA>"
  },
  "scan": {
    "timestamp": "<UTC RFC 3339 timestamp>",
    "passed": true
  },
  "result": {}
}
```

## Provenance Rules

The evidence record must identify:

- the repository and exact commit scanned;
- the governing standard and exact AES revision used;
- the AEMS scanner revision used;
- the UTC scan timestamp;
- the evaluated gate result;
- the complete raw scanner result.

A report without commit-level provenance is informative but not durable compliance evidence.

## Failure Behavior

Workflows must generate and upload evidence before enforcing the gate. Failed scans must still leave reviewable Markdown and JSON artifacts.

The JSON `scan.passed` field is the authoritative machine-readable gate result. Workflow exit status should be derived from that field after evidence upload.

## Tooling

Use:

```text
scripts/package_compliance_evidence.py
```

to wrap raw scanner JSON in the stable evidence envelope.

## Compatibility

Schema changes that remove or redefine fields require a new schema identifier. Additive fields may be introduced without changing the v1 identifier when existing consumers remain compatible.
