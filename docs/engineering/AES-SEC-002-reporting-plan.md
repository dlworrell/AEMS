# AES-SEC-002 Reporting Plan

Status: Initial reporting implementation  
Owner: AEMS  
Issue: #10  
Upstream standard: `dlworrell/AES/standards/AES-SEC-002-cross-language-secret-storage-boundaries.md`

## Purpose

This plan defines the first AEMS implementation for adopted AES-SEC-002. It
inventories applicability, runs deterministic source detectors, and retains
evidence without blocking merges.

AEMS owns detector mechanics and report formats. AES owns the obligations.
Catylist owns the authority and standards-lifecycle relationship.

## Applicability before adoption

`config/aes-sec-002-repositories.json` records one of:

- `in-scope`: a covered safe/native, secret, or confidential encrypted-storage
  boundary is known;
- `out-of-scope`: current repository state has been inspected and no covered
  boundary is declared; or
- `not-yet-classified`: available evidence is not sufficient for a conclusion
  or a planned boundary has not been implemented.

Every classification requires a rationale. An out-of-scope decision is
revision-sensitive and must be revisited when its repository adds a language
boundary, secret, encrypted store, confidential import/export, platform
sandbox, or history migration.

`dlworrell/audiblebooks` is the initial proving implementation. It is not a
universal template for other platforms or products.

`dlworrell/MayaUSD2017Bridge` is currently `not-yet-classified`: its implemented
foundation is a C++ process boundary with no safe-language FFI, key lifecycle,
or encrypted store, but planned scene bridge packages may contain confidential
production data. Its classification trigger is M1 scene translation or any
persisted bridge package.

## Report statuses

Every detector emits one explicit status:

| Status | Meaning |
|---|---|
| `present` | A discoverable evidence signal exists; correctness is not proved |
| `absent-evidence` | The rule appears applicable, but expected evidence was not discovered |
| `violation` | A high-confidence prohibited source pattern was detected |
| `untested` | A target or repository has not been evaluated with the required source or platform |
| `not-applicable` | The rule does not apply under the recorded boundary |

Reports never collapse `absent-evidence`, `untested`, and `violation` into a
single failure count.

## Detector domains

`scripts/aes_sec_002_scan.py` reports:

- configured safe/native bridge locations and direct-call escape paths;
- pointer surfaces and constructor/destructor or adopt/release anchors;
- callback synchrony, executor language, and native thread-creation paths;
- Swift 6 language mode, complete strict concurrency, and actor isolation;
- AES-banned native string APIs;
- read-only key buffers with explicit lengths and suspicious mutable key APIs;
- project-owned secret-erasure anchors;
- keyed SQLCipher connection and in-memory temporary-store ordering;
- encrypted restore, exclusive creation, protected-container, and
  security-scoped-file signals;
- immutable dependency pins;
- ignore rules and tracked-file/private-data gates;
- history-migration backup, rehearsal, coordination, and rollback evidence;
- Linux/ELF hardening construction and artifact inspection;
- Apple/Mach-O build-setting, sandbox, and artifact inspection; and
- ELF-only flags escaping into Apple pipelines.

Each output finding includes the AEMS rule identifier, adopted AES standard
path, rule-section URL, evidence path and line when available, status, severity,
and explanation.

These source detectors are intentionally conservative. A `present` result
requires review before it supports closure.

## Platform separation

Linux/ELF and Apple/Mach-O checks are independent detector domains:

- ELF evidence includes release construction plus inspection using tools such
  as `readelf`.
- Apple evidence includes resolved Xcode build settings and Mach-O inspection
  using Apple tooling.
- Apple pipeline files are excluded from ELF evidence collection.
- ELF `-z` options or `readelf` inside an Apple pipeline are reported as a
  violation.

No missing Apple runner may be represented as a passing Linux result, or vice
versa.

## Synthetic proof

`tests/fixtures/aes_sec_002/positive` contains a fully synthetic positive
fixture. It includes no real catalogue, key, credential, personal data, or
provider response.

`tests/fixtures/aes_sec_002/negative` deliberately contains:

- a direct Swift-to-C call outside the bridge;
- mutable native key parameters;
- a banned string API;
- invalid keyed temporary-store ordering;
- missing profile, erasure, dependency, and repository-hygiene evidence; and
- ELF-only controls in an Apple workflow.

The tests require those categories to remain distinguishable.

## Waiver representation

An in-scope repository should retain a local waiver record at
`docs/engineering/AES-SEC-002-waivers.md` or a configured equivalent.

Each waiver must identify:

- AES rule identifier;
- repository, paths, and symbols;
- necessity and bounded safety invariant;
- supporting tests and evidence;
- owner and approval authority;
- approval and review dates;
- removal condition; and
- affected release scope.

An empty waiver record explicitly states that no waivers are approved.
Scanner exemptions without a resolvable waiver record are not waivers.

## Migration-window prerequisites

Blocking enforcement is not authorized by this implementation.

A ratchet proposal may begin only after:

1. a source-scan baseline is retained for each affected repository;
2. high-signal detectors have positive and negative proof;
3. affected owners receive a documented migration window;
4. waiver representation is operational;
5. untested hosted targets and compensating controls are explicit;
6. a proposed rule identifies legacy and new-violation behavior; and
7. Catylist and AES separately approve the authority and standards change.

Git-history rewriting has an additional destructive-operation boundary:

- verified encrypted external backup;
- successful restore rehearsal;
- exact reviewed target list;
- collaborator, deployment, branch-protection, and mirror coordination;
- tested rollback instructions; and
- explicit owner authorization immediately before refs change.

No scanner, issue, baseline, or workflow supplies that authorization.

## Commands

Local report:

```sh
python3 scripts/aes_sec_002_scan.py /path/to/repository \
  --repo-name owner/repository \
  --format markdown
```

Applicability-only ecosystem baseline:

```sh
python3 scripts/aes_sec_002_aggregate.py --format markdown
```

Source scan with an existing private checkout:

```sh
python3 scripts/aes_sec_002_aggregate.py \
  --scan-in-scope \
  --source-map /protected/path/source-map.json \
  --format markdown
```

The source map contains local paths only and must not be committed when it
exposes private workspace structure.

## Baseline interpretation

The first retained applicability baseline classifies the ecosystem and marks
the in-scope proving implementation untested until a source checkout is
explicitly supplied. Hosted implementation and CI evidence from
`audiblebooks` PR #8 remains linked as upstream evidence; it is not silently
converted into an AEMS local scan result.

That distinction is deliberate: evidence AEMS did not execute is referenced,
not impersonated.
