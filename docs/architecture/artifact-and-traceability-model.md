# AEMS Artifact and Traceability Model

Status: Draft implementation contract
Owner: AEMS
Issue: #1
Upstream authority: Catylist, AES-002, AES-003, CAN-130

## Purpose

This document defines the lightweight artifact index and traceability graph
that AEMS uses to relate engineering work without taking ownership of
repository-local architecture, specifications, implementation documents, or
evidence.

AEMS records identity, location, ownership, lifecycle, and typed
relationships. The repository named by an artifact record remains the
canonical owner of the artifact itself.

## Authority boundary

The governing chain is:

```text
Catylist -> AES -> AEMS -> governed repositories
```

- Catylist decides what is governed and how repositories relate.
- AES defines normative obligations and evidence requirements.
- AEMS validates and reports identities and relationships.
- Governed repositories own project architecture, implementation, tests, and
  locally produced evidence.

An AEMS node is an index record, not a second canonical copy. AEMS may retain a
report or graph snapshot as evidence, but changing that snapshot cannot change
the authority, content, or lifecycle of its referenced artifact.

## Artifact classes

| Class | Meaning | Normal owner |
|---|---|---|
| `governance` | Program authority, lifecycle, taxonomy, or repository relationship | Catylist |
| `standard` | Normative engineering obligation | AES |
| `requirement` | Testable project or product obligation | Governed repository |
| `specification` | Interface, behavior, architecture, or implementation contract | Governed repository |
| `decision` | ADR or equivalent reviewed decision | Repository making the decision |
| `research` | Evidence-gated investigation that is not normative | Repository conducting the research |
| `risk` | Identified hazard, uncertainty, or residual exposure | Repository accepting or mitigating it |
| `issue` | Planned or tracked unit of work | Repository issue tracker |
| `commit` | Version-control change identity | Repository history |
| `implementation` | Source, configuration, hardware, or documentation implementation | Governed repository |
| `test` | Test, simulation, analysis, or inspection definition | Governed repository |
| `evidence` | Immutable or versioned observation supporting a claim | Producing repository or evidence store |
| `waiver` | Explicit, bounded exception to an applicable obligation | Repository plus approving authority |
| `release` | Versioned delivery or certification boundary | Releasing repository |

Classes describe what an artifact is. They do not raise an artifact's
authority. A research node remains non-normative even when it is heavily
referenced.

## Qualified identifiers

Every node and relationship in one graph must have a unique identifier.
Canonical document identifiers remain unchanged in their owning repositories;
the graph qualifies them to avoid cross-repository collisions.

| Artifact | Qualified identifier form | Example |
|---|---|---|
| Canonical document | `artifact:<owner>/<repo>:<document-id>` | `artifact:dlworrell/AES:AES-002` |
| GitHub issue | `issue:<owner>/<repo>#<number>` | `issue:dlworrell/AEMS#3` |
| Git commit | `commit:<owner>/<repo>@<full-sha>` | `commit:dlworrell/AEMS@0123…` |
| Repository file | `file:<owner>/<repo>@<ref>:<path>` | `file:dlworrell/AEMS@main:scripts/aems_project_zero.py` |
| Release | `release:<owner>/<repo>@<version>` | `release:dlworrell/AEMS@0.1.0` |
| Relationship | `rel:<graph-id>:<sequence>` | `rel:AEMS-P0-TRACE-001:0001` |

Mutable branch names are permitted for discovery reports. Closure,
certification, and release evidence should use an immutable commit SHA or tag.

## Relationship types

| Relationship | Meaning |
|---|---|
| `governs` | Source grants authority or lifecycle rules to target |
| `defines` | Source normatively defines target |
| `derives-from` | Target was informed or produced from source without transferring authority |
| `depends-on` | Source cannot safely proceed without target |
| `tracks` | Issue or work item tracks target |
| `implements` | Source implementation realizes target requirement or specification |
| `verifies` | Source test or evidence checks target |
| `evidences` | Source observation supports a claim about target |
| `mitigates` | Source control reduces target risk |
| `waives` | Source waiver explicitly bounds a target obligation |
| `supersedes` | Source replaces target while preserving lineage |
| `released-in` | Source artifact is included in target release |
| `owned-by` | Source artifact's canonical authority is target repository or owner |

The edge direction is semantic and must match the definitions above. For
example, an implementation `implements` a requirement; a requirement does not
`implement` source code.

## Minimum node fields

Every node records:

- qualified `id`;
- `artifact_class`;
- human-readable `title`;
- canonical `repository`;
- immutable `path`, `url`, or other locator where practical;
- `authority` as `canonical`, `reference`, or `generated-evidence`; and
- lifecycle `status`.

Every relationship records:

- unique `id`;
- allowed `type`;
- resolvable `source` and `target` node identifiers; and
- an optional rationale or evidence locator when the relationship is not
  self-evident.

## Example traceability chains

### Project Zero automation

```text
Catylist authority
  governs AES-002
AES-002
  defines AEMS Project Zero requirements
AEMS issue #3
  tracks the implementation
scripts/aems_project_zero.py
  implements AES-002
Project Zero unit tests
  verify the implementation
retained assessment report
  evidences the tested repository state
```

### Repository-local architecture

```text
Atarix requirement
  depends-on an Atarix ADR
Atarix implementation
  implements the Atarix specification
Atarix test
  verifies the implementation
AEMS graph
  indexes those nodes and relationships
```

The second chain does not move the Atarix documents into AEMS. The Atarix
repository continues to own and version them.

## Validation

The machine contract is
[`schemas/aems-traceability-v1.schema.json`](../../schemas/aems-traceability-v1.schema.json).
`scripts/validate_traceability.py` additionally checks semantic constraints
that JSON Schema alone cannot express:

- node identifiers are unique;
- relationship identifiers are unique;
- relationship endpoints resolve;
- node repository and authority are explicit;
- relationship types are recognized; and
- self-relationships are rejected unless a future relationship type
  explicitly allows them.

Validation establishes graph consistency, not truth or engineering closure.
Review authority still decides whether a relationship is semantically
sufficient.

## Provenance

This generalized model is informed by the Atarix-local
`ATX-SPEC-091: Requirements and Traceability Model`. It preserves that
document's requirement-to-release chain while moving only the reusable AEMS
mechanism into AEMS. `ATX-SPEC-091` remains owned by Atarix.

## Non-goals

- Replacing GitHub Issues, Git, or repository-local document systems.
- Copying every project document into AEMS.
- Treating the graph as proof that a claim is true.
- Inventing normative obligations not present in Catylist or AES.
- Building a general-purpose project-management clone.
