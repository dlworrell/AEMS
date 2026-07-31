# AEMS

Adaptive Engineering Management System (AEMS)

> Engineering is evidence, not opinion.

AEMS is the engineering-management and enforcement layer in the Catalyst
authority chain:

```text
Catylist -> AES -> AEMS -> governed repositories
```

Catylist defines program governance and repository relationships. AES defines
engineering obligations and required evidence. AEMS turns those upstream rules
into inventories, scans, reports, evidence artifacts, and ratcheted gates. It
does not originate normative engineering requirements or replace
project-owned architecture.

## What exists today

AEMS currently provides:

- a deterministic AES-002 Project Zero lifecycle engine backed by an AES-003
  repository manifest;
- Git-index-first repository and documentation inventories;
- typed, cycle-checked issue dependency graphs and explicit, idempotent
  GitHub issue application;
- a lightweight artifact/traceability contract with semantic validation;
- local and aggregate AES-DEV-001 evidence scanners;
- local and aggregate AES-SEC-001 adoption and banned-API scanners, native
  control profiles, opt-in build presets, and explicit fuzz smoke support;
- AES-BLD-001 CMake/CTest/Clang/LLVM 18 and independent GCC/GNU
  build-parity validation,
  reference C library/application fixtures, reusable CI, and evidence schema;
- AES-SEC-002 applicability and detector reporting with positive and negative
  synthetic fixtures;
- role- and ownership-aware repository inventories for both standards;
- GitHub Actions workflows for local and ecosystem reporting;
- JSON and Markdown reports;
- durable compliance-evidence envelope packaging; and
- development/security profiles, enforcement plans, waiver tracking, and
  retained ecosystem baselines.

`dlworrell/MayaUSD2017Bridge` is enrolled as project-owned for AES-SEC-001
native controls. Its AES-SEC-002 applicability remains
`not-yet-classified` until a covered persisted boundary exists and can be
assessed from repository evidence.

## Quick start

Scan one checkout for development evidence:

```sh
python3 scripts/aes_dev_001_scan.py /path/to/repository \
  --repo-name owner/repository \
  --format markdown
```

Scan one checkout for secure C/C++ adoption:

```sh
python3 scripts/aes_sec_001_scan.py /path/to/repository \
  --repo-name owner/repository \
  --strict \
  --include-dangerous-primitives \
  --format markdown
```

Assess a repository through Project Zero:

```sh
python3 scripts/aems_project_zero.py /path/to/repository \
  --output build/aems/project-zero
```

Generate a deterministic inventory:

```sh
python3 scripts/aems_repository_inventory.py /path/to/repository \
  --format json \
  --output build/aems/repository-inventory.json
```

Validate and render a structured issue graph:

```sh
python3 scripts/aems_issue_graph.py issue-graph.json \
  --format markdown \
  --output build/aems/issue-graph.md
```

Discover native controls or run explicitly configured checks:

```sh
python3 scripts/aes_sec_001_native.py /path/to/repository \
  --profile c17-library \
  --format markdown

python3 scripts/aes_sec_001_native.py /path/to/repository \
  --run-controls \
  --smoke \
  --target-config .aems/aes-sec-001-native.json
```

Validate an AES-BLD-001 repository profile and declared build parity:

```sh
python3 scripts/aes_bld_001.py structure /path/to/repository \
  --profile .aems/aes-bld-001.json \
  --require-tools \
  --strict \
  --format markdown
```

Compare two empty-prefix staged installations:

```sh
python3 scripts/aes_bld_001.py parity \
  /tmp/cmake-stage/usr \
  /tmp/autotools-stage/usr \
  --profile /path/to/repository/.aems/aes-bld-001.json \
  --strict \
  --format markdown
```

Downstream repositories adopt the independent eight-path build matrix by
copying `templates/workflows/aes-bld-001-governance.yml` and adapting
`templates/native/aes-bld-001.example.json`. The workflow deliberately starts
the CMake, GNU, analysis, sanitizer, install-parity, and distribution jobs
independently so one failure does not silently skip the other evidence paths.

Adopt the distributed fast governance control by copying
`templates/native/.clang-tidy` to the repository root and
`templates/workflows/aes-sec-001-governance.yml` to `.github/workflows/`.
The caller uses AEMS's centrally maintained reusable workflow and emits
review-required primitives with their repository-owned dispositions. New,
unresolved, source-drifted, or stale review findings block by default, while
the adopted banned-API gate remains immediate.

Build the non-blocking AES-SEC-002 applicability report:

```sh
python3 scripts/aes_sec_002_aggregate.py \
  --format markdown \
  --output build/aems/aes-sec-002.md
```

Run the project-owned repository inventories:

```sh
python3 scripts/aes_dev_001_aggregate.py --format markdown
python3 scripts/aes_sec_001_aggregate.py --strict --format markdown
```

Aggregate scans check out listed repositories and therefore require suitable
GitHub access. External references and third-party mirrors are inventoried but
are not scanned by default.

## Repository map

- `aems/`: dependency-free Project Zero, inventory, issue-graph, and
  constrained structured-data modules;
- `aes-manifest.yaml`: AEMS AES-003 identity, classification, lifecycle, and
  automation declaration;
- `schemas/` and `examples/traceability/`: artifact graph contract and
  validated example;
- `config/aes-dev-001-repositories.json`: development-discipline inventory and
  documentation-authority declarations;
- `config/aes-sec-001-repositories.json`: secure-C/C++ adoption inventory and
  native profile assignments;
- `config/aes-sec-002-repositories.json`: reporting-mode applicability and
  rationale;
- `config/aes-bld-001-repositories.json`: active-native, planned-native,
  reference, and third-party build-parity rollout inventory;
- `scripts/aems_project_zero.py`: AES-002 lifecycle assessment and evidence;
- `scripts/aems_repository_inventory.py`: deterministic repository inventory;
- `scripts/aems_issue_graph.py`: typed dependency reporting and optional
  explicit GitHub issue application;
- `scripts/aes_dev_001_scan.py`: single-checkout development evidence scanner;
- `scripts/aes_dev_001_aggregate.py`: ecosystem development report runner;
- `scripts/aes_sec_001_scan.py`: single-checkout native-code security scanner;
- `scripts/aes_sec_001_aggregate.py`: ecosystem security report runner;
- `scripts/aes_sec_001_native.py`: native control discovery and explicit
  control/fuzz execution;
- `scripts/aes_bld_001.py`: AES-BLD-001 structure, evidence, waiver, install,
  package-content, and public-symbol parity validation;
- `.clang-tidy`, `.github/actions/aes-sec-001/`, and
  `.github/workflows/aes-sec-001-distributed.yml`: the distributed
  Clang-Tidy and fast banned-API governance control;
- `scripts/aes_sec_002_scan.py` and `scripts/aes_sec_002_aggregate.py`:
  non-blocking applicability and detector reports;
- `templates/`: opt-in native build and workflow presets;
- `scripts/package_compliance_evidence.py`: stable JSON evidence-envelope
  packager;
- `.github/workflows/`: pull-request, push, and manually dispatched scans;
- `docs/engineering/reports/`: retained baselines and adoption evidence.

## Enforcement model and limits

The current enforcement plans are initial ratchets:

1. detect;
2. report;
3. baseline existing gaps;
4. require evidence for new work; and
5. block stable, high-signal violations deliberately.

Scanner and graph output is evidence about repository state and relationships;
it is not proof of architectural correctness, engineering closure, product
readiness, or runtime security. AEMS implements a deliberately small typed
graph, not a general project-management database. AEMS has not adopted
Catylist's CAT-CON-001 closure schema, and it must not report schema
conformance as proof of closure.

## Authoritative documents

- [AEMS project charter](docs/AEMS-001-project-charter.md) — draft
- [Standards execution model](docs/architecture/standards-execution-model.md) —
  draft
- [Artifact and traceability model](docs/architecture/artifact-and-traceability-model.md)
  — draft implementation contract
- [AES-DEV-001 enforcement plan](docs/engineering/AES-DEV-001-enforcement-plan.md)
  — clean reporting ratchet
- [AES-SEC-001 enforcement plan](docs/engineering/AES-SEC-001-enforcement-plan.md)
  — implemented blocking review-disposition ratchet
- [AES-SEC-002 reporting plan](docs/engineering/AES-SEC-002-reporting-plan.md)
  — reporting only
- [AES-BLD-001 enforcement plan](docs/engineering/AES-BLD-001-enforcement-plan.md)
  — initial reference gate
- [Compliance evidence schema](docs/engineering/compliance-evidence-schema.md)
- [Development profile](docs/engineering/AES-DEV-001-development-principles.md)
- [Secure C/C++ profile](docs/engineering/SECURE-C-CXX.md)
- [Waiver log](docs/engineering/AES-SEC-001-waivers.md)

## License

See [LICENSE](LICENSE).
