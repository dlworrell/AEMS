# AEMS-P0-001 Project Zero Certification Candidate

Status: Candidate  
Owner: AEMS  
Governing standards: AES-002, AES-003  
Issue set: AEMS #1, #3, #4, #5

## Claim

The AEMS repository contains a reviewable candidate implementation of the
generic Project Zero execution layer:

- an AES-003 repository manifest;
- deterministic repository and documentation inventory generation;
- explicit AES-002 lifecycle-state evaluation;
- missing-input, blocker, and next-action reporting;
- typed issue dependency graphs with cycle detection and stable execution
  order;
- optional, explicit, idempotent GitHub issue application;
- machine-readable JSON and generated Markdown evidence; and
- deterministic unit and integration tests.

## Certification boundary

This document does not approve its own claim. The manifest therefore records
`project_zero.state: CERTIFICATION` and certification status `candidate`.

The repository may transition to `ENGINEERING_READY` only after:

1. the implementation and its governing documents are reviewed;
2. the full test suite passes on the reviewed commit;
3. the AEMS and Atarix inventory integration checks pass;
4. the retained Project Zero evidence names the reviewed commit; and
5. the reviewer approves the certification in a separate, traceable change.

## Reproducible commands

```sh
python3 -m unittest discover -s tests -v
python3 scripts/aems_project_zero.py . --output build/aems/project-zero
python3 scripts/aems_repository_inventory.py ../atarix \
  --repository dlworrell/atarix \
  --format json \
  --output build/aems/atarix-inventory.json
python3 scripts/validate_traceability.py \
  examples/traceability/project-zero-engine.json
```

## Accepted deferrals

None are approved by this candidate record.
