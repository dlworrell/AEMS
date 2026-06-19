# AEMS-001 – Project Charter

Status: Draft

## Purpose

AEMS is the Adaptive Engineering Management System.

Its purpose is to help engineering work remain evidence-based, traceable, reviewable, and reproducible across the Catalyst and Atarix ecosystem.

## Governing Principle

Engineering is evidence, not opinion.

AEMS exists to make that principle operational.

If a design changes, there should be a traceable reason. If a requirement is satisfied, there should be evidence. If a release ships, it should be reproducible.

## Relationship to AES

AEMS inherits engineering governance from AES.

AES defines the engineering principles, documentation discipline, traceability expectations, and decision-making standards. AEMS implements those ideas as working project infrastructure.

AEMS is therefore the first implementation customer of AES.

## Initial Scope

AEMS should provide structure for:

- requirements
- decisions
- research
- risks
- milestones
- evidence
- reviews
- releases
- traceability between engineering artifacts

## Non-Goals

AEMS should not begin as a broad project-management clone.

It should not attempt to replace every issue tracker, wiki, build system, or repository host at once.

Its first responsibility is to make engineering evidence durable and navigable.

## Operating Discipline

AEMS development follows AES discipline:

1. Observe the current repository state.
2. Understand the governing AES documents.
3. Improve through small, traceable commits.
4. Keep Git as the source of truth.
5. Treat chat as engineering discussion, not authoritative state.

## Success Standard

AEMS succeeds when a future maintainer can answer:

- What was required?
- Why was it required?
- What decision satisfied or changed it?
- What evidence proves the work was completed?
- What release included it?
- What risks remain?

If AEMS can answer those questions clearly, it is serving its purpose.
