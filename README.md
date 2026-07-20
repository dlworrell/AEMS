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

- local and aggregate AES-DEV-001 evidence scanners;
- local and aggregate AES-SEC-001 adoption and banned-API scanners;
- role- and ownership-aware repository inventories for both standards;
- GitHub Actions workflows for local and ecosystem reporting;
- JSON and Markdown reports;
- durable compliance-evidence envelope packaging; and
- development/security profiles, enforcement plans, waiver tracking, and
  retained ecosystem baselines.

`dlworrell/MayaUSD2017Bridge` is enrolled as a project-owned repository with a
required local development profile and an active native-C++ security surface.

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

Run the project-owned repository inventories:

```sh
python3 scripts/aes_dev_001_aggregate.py --format markdown
python3 scripts/aes_sec_001_aggregate.py --strict --format markdown
```

Aggregate scans check out listed repositories and therefore require suitable
GitHub access. External references and third-party mirrors are inventoried but
are not scanned by default.

## Repository map

- `config/aes-dev-001-repositories.json`: development-discipline inventory and
  documentation-authority declarations;
- `config/aes-sec-001-repositories.json`: secure-C/C++ adoption inventory;
- `scripts/aes_dev_001_scan.py`: single-checkout development evidence scanner;
- `scripts/aes_dev_001_aggregate.py`: ecosystem development report runner;
- `scripts/aes_sec_001_scan.py`: single-checkout native-code security scanner;
- `scripts/aes_sec_001_aggregate.py`: ecosystem security report runner;
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

Scanner output is evidence about repository signals; it is not proof of
architectural correctness, engineering closure, product readiness, or runtime
security. The typed engineering knowledge graph described by the architecture
is a direction, not a completed implementation. AEMS has not yet adopted
Catylist's CAT-CON-001 closure schema, and it must not report that schema
conformance proves closure.

## Authoritative documents

- [AEMS project charter](docs/AEMS-001-project-charter.md) — draft
- [Standards execution model](docs/architecture/standards-execution-model.md) —
  draft
- [AES-DEV-001 enforcement plan](docs/engineering/AES-DEV-001-enforcement-plan.md)
  — initial
- [AES-SEC-001 enforcement plan](docs/engineering/AES-SEC-001-enforcement-plan.md)
  — initial
- [Compliance evidence schema](docs/engineering/compliance-evidence-schema.md)
- [Development profile](docs/engineering/AES-DEV-001-development-principles.md)
- [Secure C/C++ profile](docs/engineering/SECURE-C-CXX.md)
- [Waiver log](docs/engineering/AES-SEC-001-waivers.md)

## License

See [LICENSE](LICENSE).
