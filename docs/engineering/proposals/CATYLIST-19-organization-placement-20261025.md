# Proposed Catylist ADR: current repository placement

Status: PROPOSED — maintainer decision pending.
Owner: Catylist. Prepared 2026-10-25. Related: Catylist #19.
This is a review draft, not an accepted ADR or transfer authorization.

## Context

The protected inventory currently contains 17 repositories under dlworrell.
AEMS's existing per-repository applier has run successfully, and a current
read-only comparison reports all 17 matching the accepted ADR-0006 baseline.
An organization transfer is therefore not necessary to repair the observed
ruleset drift, which is already zero. This evidence does not resolve broader
ownership, administration or multi-maintainer preferences.

## Proposed decision

Retain the present personal-account placement for this remediation cycle.
Continue to treat the versioned Catylist inventory as authority and AEMS as the
enforcement mechanism. Defer any organization transfer to a separate approved
migration ADR with its own inventory, integration, credential, redirect,
private-repository feature and recovery verification.

This proposal does not assert current product-plan pricing or assume that
integration permissions transfer automatically. Those facts must be verified
at the time a specific organization and migration are approved.

## Alternatives and consequences

Moving now would create additional repository/integration migration work while
the manifest/back-pointer and conformance rollout are unfinished. It may be
appropriate once the maintainer identifies organizational ownership or a
multi-maintainer administration requirement. Retaining placement avoids that
immediate migration but keeps per-repository ruleset reconciliation necessary.

## Authority, security and recovery

Catylist owns this placement decision. It does not change AES authority or
AEMS's delegated implementation role. No repository, secret, installation,
team, permission, payment plan or URL is changed by this draft. If migration is
later selected, validate a sandbox first and record recovery/redirect behavior
before changing governed repositories. Existing evidence stays bound to its
original repository identities and commits.

## Acceptance

A maintainer records Accepted, Revised or Rejected in a Catylist ADR. An
accepted retain-current-placement decision satisfies #19 without representing
a transfer as completed. This AI review has not supplied that decision.
