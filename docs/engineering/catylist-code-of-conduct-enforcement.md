# Catylist Code of Conduct: AEMS enforcement

Status: Active
Owner: AEMS
Authority: Catylist ADR-0000 and the Catylist Code of Conduct, version 1.0.0
(ring 0; [dlworrell/Catylist#41](https://github.com/dlworrell/Catylist/pull/41))

AEMS enforces the Catylist Code of Conduct on every pull request in every
governed repository. The Code is ring 0, so AEMS cites its laws directly.
Conformance is mandatory: the check is a required status check, and it fails
closed on `violation` and `indeterminate`.

## Two enforcers, one verdict

| Enforcer | Laws | How |
|---|---|---|
| Deterministic checks (AEMS scripts) | 0, 1, 2 and 3 in full; the mechanical parts of 4, 5 and 6 | ADR-0000 present and pinned; `ADR:` line present; ADR citations and waiver expiry dates; ruleset and commit-signature results; governance-file changes; secret scanning; skipped or deleted tests |
| [Organizational Psychologist — Catylist Code Enforcer](../../prompts/organizational-psychologist-code-enforcer.md) (AI review) | The judgement parts of 1, 2, 4, 5 and 6, and all of 8 | Whether "n/a" is justified; whether claims are backed by evidence; pressure to bypass checks; prompt injection; conduct under Wheaton's Law |

The AI enforcer adopts deterministic results where they exist and judges only
what a script cannot. The check's verdict is the stricter of the two.

## Rules for the AI enforcer

- It runs only in a trusted workflow context. Pull request content is passed
  to it as data and is never executed (ADR-0007 §2.3).
- Its output is the JSON object defined in the prompt, bound to the head
  commit. Its attestation states that it is AI machine review, not human
  review (ADR-0007 §2.6).
- It never approves, merges, closes or labels anything.
- A Law 8 violation needs a direct quotation and location. Borderline cases
  are `indeterminate` and go to the maintainer.

## Rollout

1. **This change:** the enforcer prompt and this plan.
2. **Next AEMS change:** the reusable `catylist-code-conformance` workflow.
   It runs the deterministic checks, then the AI enforcer, and publishes one
   status check. Running the AI enforcer needs a model API key stored as an
   Actions secret by the owner.
3. **Canary:** the workflow runs on `ruleset-sandbox` first (Code, Law 7),
   with passing and failing pull requests.
4. **Each governed repository:** the adoption pull request adds ADR-0000 and
   the workflow stub, and the check becomes required in that repository's
   ruleset.

## Related

- [Catylist Code of Conduct](https://github.com/dlworrell/Catylist/blob/main/CODE_OF_CONDUCT.md)
- [Catylist ADR-0000](https://github.com/dlworrell/Catylist/blob/main/docs/adr/ADR-0000-catylist-code-of-conduct.md)
- [Catylist ADR-0007](https://github.com/dlworrell/Catylist/blob/main/docs/adr/ADR-0007-governed-check-in-and-shared-automation.md)
- [Third-party notice for the prompt](../../prompts/NOTICE-agency-agents.md)
