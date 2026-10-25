# Proposed AES-003 / Catylist #18 contract for review

Status: PROPOSED — not adopted, not an AEMS requirement.
Owning authorities: AES for manifest fields; Catylist for inventory desired state.
Prepared 2026-10-25 by an AI agent; requires owning-authority disposition.

## Verified problem

AES `2a29348533bbc29f9e645c45316bcce33d75ae0c`,
`docs/standards/AES-003-manifest-fields.md`, explicitly says the Catylist
back-pointer planned under #18 is not defined. Catylist's current inventory
is `catylist.repository-inventory.v1` and records ownership/class/protection,
not the full desired-state contract requested by #18. Inventing producer
fields independently would create competing expectations.

## Concrete proposed shape

Extend AES-003 with one optional, then ratcheted, manifest mapping:

```yaml
governance:
  catylist:
    repository: dlworrell/Catylist
    inventory_path: inventory/repositories.json
    inventory_commit: <40-character immutable Git commit>
    entry: <owner/repository>
```

The entry is the exact `repository.full_name`; owner/class are read from that
pinned inventory entry rather than guessed from the display name. If a local
class is declared, it must agree. Unknown or inaccessible inventory revisions,
duplicate entries and identity/ownership/class disagreement fail visibly.
The field is proposed in AES, not made normative by this review packet.

Version the Catylist inventory as `catylist.repository-inventory.v2`. Each
protected entry retains v1 identity/classification/protection fields and adds:

- `desired.ruleset_profile`: immutable repo_templates source commit plus the
  exact branch/tag template paths and profile version;
- `desired.standards`: explicit standard ID, applicability, reason for every
  not-applicable value, authority revision and evidence references;
- `desired.scopes`: expected scope IDs/paths/class and standard applicability,
  including explicit repository-remainder coverage;
- `desired.required_checks`: exact names with supporting run ID, workflow path
  and source commit. An empty list records the current ADR-0006 baseline and
  does not invent an unobserved check or enable enforcement;
- `desired.manifest_contract`: the accepted AES-003 revision to validate.

Do not fill unknown standard applicability or missing lifecycle/certification
with inferred success. Keep unresolved values in a separate migration-gap
record; a required unresolved value prevents conformance qualification.

## Compatibility and migration

1. AES reviews and versions the back-pointer definition; Catylist reviews the
   v2 inventory shape and desired-state records together.
2. Test positive and negative fixtures: wrong/unknown revision, wrong entry,
   copied identity, class mismatch, duplicate scope, evidence escape, missing
   not-applicable reason, unknown check name and old-version compatibility.
3. Preserve v1 read support in existing appliers; do not rewrite historical
   inventory revisions or imply old records met new requirements.
4. Commit the v2 inventory first. The following Catylist manifest commit can
   reference that already existing commit, avoiding a self-referential SHA.
5. Migrate each governed repository by signed PR, citing source evidence for
   its lifecycle, standards and scope declarations; retain one remediation
   result per repository. Enable #23 enforcement only after observed passes.

## Disposition needed

Accept, revise or reject this exact field shape and migration order in the
owning AES/Catylist records. Acceptance is not inferred from this AI-authored
proposal or from a passing parser test. No field has been enforced or rolled
out based on this draft.
