# Proposed ATARIX local ADR and Catylist #34 review disposition

Status: PROPOSED; AI review completed; maintainer acceptance pending.
Owning repository: ATARIX. Prepared 2026-10-25.
No SQLite adoption, program-wide database standard or production qualification
is approved by this document.

## Verified authority and current evidence

ATARIX `5854e74fd6f7053571ca562c8da92302c637b090` accepts the authority chain in
ADR-0015. ATX-SPEC-090/092 are project-local draft specifications. SPEC-092
separates a release from a tag and records release-manifest persistence as
future work. No owning SQLite adoption ADR was observed in this main tree.
The existing release-evidence implementation and retained Git/JSON/artifacts
are the closest relevant sources; their existence does not establish a
SQLite schema, migration result or reconstructed historical verification.

Catylist's decision process routes this storage/recovery design to an ATARIX
ADR. AES owns reusable normative evidence/security/recovery requirements;
AEMS owns reusable ingestion, indexing and enforcement mechanics. ATARIX's
integration and local schema remain local. A separate program-wide Catylist ADR
is necessary only if authority, shared namespaces, lifecycle policy or
cross-project dependency direction changes; no such expansion is proposed.

## Proposed decision

Use Python sqlite3 only as a derived, disposable operational index. Retained
Git commits, approved documents, versioned JSON manifests and authenticated CI
artifacts remain source authority. Model repositories, commits/parents,
requirements/specifications, trace edges, workflow runs/results, artifact
identities/digests and releases as explicit related entities. A database row
must never turn absent evidence into a verified result or authorize a release.

Imports are transactional and idempotent by immutable source identity. Enable
and verify foreign-key enforcement on every connection before starting the
import transaction. Record schema version/migrations, source SHA-256 digests,
UTC observation times, tool/runtime versions and reconciliation results.
Parameterize SQL values. Define size/depth limits, schema validation and safe
path resolution for untrusted JSON/CI metadata. Reject path traversal,
symlink artifacts, digest mismatch, unknown source commits and partial input.
Do not load arbitrary extensions or commit a live database to Git.

Release decisions revalidate the exact commit, required gate profile, complete
manifest and retained artifact bytes independently of cached rows. Missing,
failed, cancelled, wrong-SHA or unavailable evidence refuses promotion. No
new automatic tagging or release publishing is included.

## Historical reconstruction and retention

For 2026-06-17 through 2026-10-18, record each observation as contemporaneous,
retrospective or unverified/missing. Retrospective execution names both the
historical source commit and current evaluator commit/configuration. Do not
assume modern tooling existed at the old commit, reuse a neighboring passing
run, or backdate an approval. Git history alone proves a stored commit exists,
not that required tests ran.

Specify artifact retention/export and restoration procedures. Backups use a
consistent SQLite backup mechanism and are restored and reconciled against
retained sources; an arbitrary copy of a live main database file is not the
recovery protocol. WAL, if chosen, requires explicit checkpoint/backup tests.
The database is rebuildable; lost authoritative evidence is a visible gap.

## Testable acceptance matrix

| Case | Required observation |
|---|---|
| Fresh schema / supported upgrade | Correct version, expected relations and readable older evidence; unsupported downgrade refuses without modifying source evidence. |
| Duplicate import | Same logical records/digests; no duplicate authority or approval. |
| Out-of-order parent import | Deterministic reconciliation or explicit unresolved parent; no invented commit relation. |
| Referential integrity | Invalid source links fail; each new connection confirms enforcement before import. |
| Failed/missing/cancelled CI | Retained as failed or unknown; release refuses. |
| Wrong commit / wrong gate profile | Refusal even when an unrelated row says pass. |
| Digest mismatch / missing artifact | Refusal; no cache-only promotion. |
| Interrupted write | Whole transaction rolls back or completes; restart is idempotent. |
| Corrupt/missing index | Rebuild from retained sources yields the same canonical JSON projection. |
| Backup / restore | Restored projection and source digests reconcile; failure is explicit. |
| Malicious JSON/path/symlink/SQL value | Input is bounded and rejected or safely parameterized; no external file access or executable metadata. |
| Representative history/performance | Record actual fixture size, import/query timings and resource bounds; maintainer-set thresholds remain unresolved until measured and agreed. |
| Historical provenance | Contemporaneous, retrospective and unknown cases remain distinct in exports and release decisions. |
| Incomplete release manifest | Fail closed regardless of database health or generic gate success. |

All cases above are NOT RUN for a SQLite implementation; this matrix is an
acceptance proposal, not passing implementation evidence. SHA-256 integrity is
not an approval signature. AES-DEV-001 supplies documentation/versioning,
verified-commit/PR, observability, threat-model and recovery obligations.
AES-SEC-001 applies to native surfaces; AES-SEC-002 applies if a covered
secret/FFI/encrypted-storage boundary actually exists. A metadata-only Python
index does not justify a blanket secret-storage applicability assertion.

## Primary implementation references

- SQLite foreign-key behavior: https://www.sqlite.org/foreignkeys.html
- SQLite PRAGMA semantics: https://www.sqlite.org/pragma.html
- SQLite online backup: https://sqlite.org/backup.html
- SQLite WAL behavior: https://www.sqlite.org/wal.html
- Python sqlite3 parameter binding/backup: https://docs.python.org/3/library/sqlite3.html

These references were checked on 2026-10-25. They inform mechanics, not Catalyst
policy. AES should review reusable evidence-persistence coverage separately;
this review does not invent a new accepted AES standard.

## Required disposition

Record this proposal and AI review in ATARIX, then have the maintainer accept,
revise or reject the owning ADR before implementation. Acceptance authorizes
the local architecture direction, not release qualification. Preserve #34 as
open until that disposition is recorded; do not relabel this AI review as an
independent human sign-off.
