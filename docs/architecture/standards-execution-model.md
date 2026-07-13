# AEMS Standards Execution Model

Status: Draft
Owner: AEMS
Upstream authority: Catylist and AES

## Purpose

AEMS is the engineering-management and enforcement layer in the Catalyst authority chain:

```text
Catylist -> AES -> AEMS -> governed repositories
```

AEMS consumes Catylist governance and AES standards. It does not originate normative engineering authority.

## Responsibilities

AEMS owns executable mechanisms for:

- repository discovery and classification;
- standards and profile resolution;
- document-authority analysis;
- policy evaluation;
- CI and engineering-gate generation;
- requirements and traceability graphs;
- evidence collection and packaging;
- compliance reporting;
- ratcheted enforcement;
- repository bootstrapping and controlled repair.

## Non-Responsibilities

AEMS shall not:

- define Catylist governance;
- create new engineering obligations without an AES requirement;
- become the canonical owner of project architecture;
- silently modify repositories without a declared repair plan, evidence, and reviewable change;
- treat tool behavior as normative when it conflicts with the applicable AES revision.

## Model-Driven Operation

AEMS should operate as a compiler for engineering policy:

```text
Catylist governance
        +
AES standards and profiles
        +
repository manifest and local extensions
        -> resolved engineering model
        -> checks, gates, reports, and evidence
```

The resolved model should contain typed entities such as:

- organization;
- program;
- project;
- repository;
- component;
- requirement;
- architecture record;
- interface;
- implementation artifact;
- test;
- evidence artifact;
- waiver;
- release.

Relationships shall be explicit and machine-readable.

## Rule Traceability

Every AEMS rule shall identify:

- rule identifier;
- originating AES standard and requirement identifier;
- applicable profile or repository class;
- evidence produced;
- severity and ratchet stage;
- waiver behavior;
- remediation guidance.

Rules without an upstream authority reference are advisory experiments and shall not block merges.

## Evidence Contract

AEMS shall emit human-readable and machine-readable evidence. Evidence envelopes shall identify:

- schema version;
- repository;
- scanned commit SHA;
- Catylist governance revision when applicable;
- AES standard revision;
- AEMS scanner revision;
- UTC timestamp;
- pass/fail result;
- findings, waivers, and supporting evidence.

## Ratcheting

Enforcement shall progress deliberately:

1. detect;
2. report;
3. baseline existing gaps;
4. require evidence for new work;
5. block repeated or unreviewed violations;
6. enforce stable requirements across the repository class.

AEMS shall preserve evidence before applying a blocking result.

## Repository Interface

A governed repository should declare only project-specific facts and extensions, for example:

```yaml
project:
  name: example
profiles:
  - c-library
local_extensions: []
evidence:
  traceability: required
```

AEMS resolves inherited obligations from Catylist and AES and generates or validates the corresponding engineering gates.

## Repair Operations

Automated repair shall be conservative and auditable. A repair operation shall:

- state the violated requirement;
- identify the intended canonical state;
- produce a reviewable change;
- preserve provenance;
- avoid destructive moves until references are updated;
- run validation after the repair;
- record the resulting evidence.

## Architectural Direction

AEMS should evolve toward a typed engineering knowledge graph from which CI, documentation indexes, traceability matrices, dashboards, and compliance evidence are derived. The graph is an execution model; Catylist and AES remain the sources of authority.
