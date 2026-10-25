# Scoped AES-SEC-001 scans

Implementation of Catylist ADR-0004 and Catylist #24, using PRM-0005 from
Dropbox `/prompt`. AES-003 owns scope declarations; this mechanism does not
change applicability, approve a waiver, or certify a project.

## Local commands

Run from the governed repository checkout, with an immutable AEMS checkout
available as `$AEMS`. Use the exact AEMS revision recorded by the adopting PR.

```sh
python3 "$AEMS/scripts/aems_scope_coverage.py" .
python3 "$AEMS/scripts/aes_sec_001_scan.py" crypto_pipeline \
  --repo-name dlworrell/code-noodling --include-dangerous-primitives \
  --strict --strict-review-ratchet --format json
python3 "$AEMS/scripts/aes_sec_001_scan.py" . \
  --exclude crypto_pipeline --exclude election-analysis \
  --repo-name dlworrell/code-noodling --include-dangerous-primitives \
  --strict --strict-review-ratchet --format markdown
python3 "$AEMS/scripts/aes_sec_001_scan.py" crypto_pipeline \
  --repo-name dlworrell/code-noodling --include-dangerous-primitives \
  --annotation-prefix crypto_pipeline --format github
```

Exclusions are literal segment prefixes relative to the scan root, repeatable,
and never globs. Traversal, absolute paths and exclusions of the entire root
are rejected. JSON/Markdown finding paths and IDs stay scan-relative;
`--annotation-prefix` changes only GitHub's displayed file paths. Reports also
record `scan_root` and `excluded_paths`. Source and adoption evidence cannot be
borrowed through symlinks. An explicitly requested scan root must be real and
inside the checkout when using the action or coverage planner.

The profile, waiver log and disposition ledger are loaded from the selected
root's `docs/engineering/`. A missing scope profile cannot inherit a passing
root profile. A scope explicitly classified not applicable by AES-003 can be
scanned for information without `--strict`; that is not a passing adoption
gate. Record the reason and check that no native surface has appeared. The
repository-level remainder continues its adopted strict scan.

`aems_scope_coverage.py` reads the actual manifest and Git-tracked paths. It
rejects duplicate IDs/paths, nested, missing or symlink scope directories and
emits one scan per declared scope plus the root remainder excluding them all.
Every tracked file receives exactly one owner. Path coverage does not establish
engineering applicability or successful project tests. The constrained YAML
loader now accepts the single-paragraph `>-` reason form used by AES-003
manifests; unsupported forms still fail with diagnostics.

## Re-key existing history after path-only movement

Provide a JSON object mapping each old repository-relative native source path
to its new scope-relative path. For a source already inside a declared scope,
for example, map `crypto_pipeline/crypto_multiplier.c` to `crypto_multiplier.c`.

```sh
python3 "$AEMS/scripts/aes_sec_001_rekey.py" . \
  --ledger docs/engineering/AES-SEC-001-review-dispositions.json \
  --new-scope crypto_pipeline --path-map reviewed-path-map.json \
  --output-directory build/aems/rekey-crypto
```

The helper scans each destination using both its old and new identity paths.
It requires an exact old finding ID, symbol and normalized-call fingerprint;
missing, changed, duplicate or ambiguous matches fail. Resolved history with
no current source match must remain unresolved for manual treatment rather
than gaining a guessed identity. It never writes the input ledger and refuses
existing output files. It emits a scope ledger, a root remainder ledger and
an identity/count conservation report. Review classification, rationale,
invariant, evidence, owner, reviewer and dates are copied unchanged; no new
approval is generated. Inspect the report, install both ledgers in one PR,
then run all scope and remainder ratchets.

## Schema compatibility decision

The v1 ledger schema keeps `schema_version: 1.0.0` and gains optional `scope`.
All previously valid ledgers remain valid and old Python callers keep their
three positional arguments. An absent scope retains legacy behavior. When
present, scope must equal the actual checkout-relative scan root (`.` for the
root ledger), or scanning fails. This is an additive reader/schema extension;
older strict schema validators may reject the new optional field and must
use the adopting pinned AEMS revision. Finding identity/fingerprint formulas
are unchanged. The helper explicitly rekeys path changes rather than resetting
the ratchet baseline.

## CI integration

`aes-sec-001-distributed.yml` accepts `scan_root` (default `.`), `exclude_paths`
(newline-separated, default empty) and `evidence_name` (default derived from
scope). Existing callers preserve whole-repository behavior. The composite
action accepts `scan-root` and `exclude-paths` and computes the annotation
prefix from the checkout. String inputs enter shell steps through environment
variables and arrays. The reusable workflow validates scope-local `.clang-tidy`
when present, otherwise the root configuration; symlink configurations fail.

Artifact names sanitize the label and hash the original scope/label pair to
avoid sanitization collisions. Evidence directories are scope-specific. Give
repeated matrix executions of the same scope distinct `evidence_name` values.
Consumers must pin the reusable workflow to a full published commit SHA; the
workflow pins its central scanner action separately to a verified source
commit containing the implementation. No write token, `pull_request_target`,
self-hosted runner, or human approval attestation is introduced.

## Validation

The tests execute the composite shell action, workflow identity/configuration
steps, CLI refusal cases, legacy and scope-local ledger reads, path-only rekey,
changed/missing source refusal, ambiguous mappings, conservation and copied
review metadata. This is AI-assisted implementation and self-review, not an
independent human review or cryptographic/production certification. Downstream
qualification must name its exact source and CI evidence.
