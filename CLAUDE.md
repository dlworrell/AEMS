# AEMS agent context

Purpose: Implement the upstream AES engineering obligations as deterministic inventories, validators, scanners, reports, and gates.
Layout: scripts/ contains dependency-free command entry points; aems/ contains lifecycle and structured-data helpers; tests/ contains unittest cases and fixtures; schemas/, templates/, docs/engineering/, and .github/ carry contracts and integration.
Template source revision: dlworrell/repo_templates@f9e3f20efdf47daf7536759c3028acda38496303 (agent_instructions 0.1.0)

## Read first

Read `README.md`, `aes-manifest.yaml`, applicable scope READMEs, and their linked
architecture, specifications, ADRs and engineering evidence before changing code.
The manifest and owning documents determine applicability and authority.

## Repository commands and conventions

- Tests: `python3 -m unittest discover -s tests -v`
- Local scan: `python3 scripts/aes_sec_001_scan.py . --repo-name dlworrell/AEMS --include-dangerous-primitives --strict --strict-review-ratchet --format markdown`
- Observed conventions: Use standard-library Python, pathlib, typed records and sorted deterministic reports; exercise positive and refusal cases with temporary repositories. Preserve existing CLI defaults and ledger identities; explain schema changes and test legacy ledgers.

## Authoritative references

- https://github.com/dlworrell/Catylist/blob/7a1ede0bb073477be226aa572fc3c20db3312df1/docs/adr/ADR-0004-governed-project-scopes.md
- https://github.com/dlworrell/Catylist/blob/7a1ede0bb073477be226aa572fc3c20db3312df1/docs/adr/ADR-0005-agent-instruction-files.md
- https://github.com/dlworrell/Catylist/blob/7a1ede0bb073477be226aa572fc3c20db3312df1/docs/adr/ADR-0006-default-branch-protection-and-signed-commits.md
- https://github.com/dlworrell/Catylist/blob/7a1ede0bb073477be226aa572fc3c20db3312df1/docs/adr/ADR-0007-governed-check-in-and-shared-automation.md
- https://github.com/dlworrell/AES/blob/2a29348533bbc29f9e645c45316bcce33d75ae0c/standards/AES-DEV-001-development-principles-and-check-in-discipline.md

These references own the requirements; this context file does not restate them.
