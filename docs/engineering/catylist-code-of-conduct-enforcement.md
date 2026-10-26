# Catylist Code of Conduct: AEMS enforcement (ring 0)

Status: Active
Owner: AEMS
Authority: Catylist ADR-0000 (the Code is ring 0), ADR-0010 (every input is
checked; untrusted until verified) and ADR-0011 (agent attribution), Catylist
Code of Conduct 1.1.0

AEMS enforces the Catylist Code of Conduct on every input to every covered
repository. The Code is ring 0, so AEMS cites its laws directly. Conformance is
mandatory: check runs fail closed on `violation` and `indeterminate`.

## How it runs

| Piece | File |
|---|---|
| Workflow, every 30 minutes and on manual dispatch | `.github/workflows/ring-0-sweep.yml` |
| Sweep: checks, GitHub I/O, ledger | `scripts/ring0_sweep.py` |
| AI enforcer prompt | `prompts/organizational-psychologist-code-enforcer.md` |
| Coverage, model and effort | `config/ring0.json` |
| Tests | `tests/test_ring0_sweep.py` |

The sweep acts as the GitHub App **`catylist-ring-0`** (App ID 5474337). Each run
exchanges the App's private key for an installation token that expires within
an hour and carries only Checks, Issues, Pull requests and Discussions write and
Contents read. AEMS's own workflow token writes only the ledger branch in AEMS.

## What it checks

| Input | Deterministic checks | AI enforcer | Action on failure |
|---|---|---|---|
| Open pull request (every new head commit, body edit or owner approval) | Laws 0–7 (below) | Laws 1, 2, 4, 6 judgement, and Law 8 | `ring-0` and `ring-0/conduct` check runs fail; no merge |
| Issue and pull request comments, review comments, commit comments, discussion comments | Law 5 secrets | Laws 4, 6, 8 | Hidden (reversible) and reported in Catylist |
| Issues, reviews, discussions, releases | Law 5 secrets | Laws 4, 6, 8 | Reported in Catylist. GitHub cannot hide these types |
| Wiki edits | Law 5 secrets | Laws 4, 6, 8 | Reported for the maintainer to revert |
| Pushes to other branches | Law 5 secrets, Law 3 signatures | — | Recorded; secrets reported |
| Tags | — | — | Recorded |

**Deterministic pull request checks:**

| Law | Check |
|---|---|
| 0 | ADR-0000 exists and pins the current Code version; the pull request changes nothing in it except the "Code version" line |
| 1 | The body has an `ADR:` line naming an ADR, or `ADR: n/a` with a reason; bots pass only with a standing ADR in `config/ring0.json` |
| 2 | Any waiver ADR added or changed has an unexpired `Expires:` date |
| 3 | Every commit is signed and verified |
| 4 | Governance files (the Code, ADRs, `.github/workflows/`, `.github/rulesets/`, agent instruction files) change only with the owner's comment `ring-0: owner approves governance change`, posted after the latest push and not written by an agent; an agent-written body starts with its title line (below) |
| 5 | No secret pattern in the body or added lines (the value is never repeated) |
| 6 | No skipped or deleted test unless the `ADR:` line names an ADR and the owner comments `ring-0: owner approves test change` after the latest push |
| 7 | No `CODE_OF_CONDUCT.md` outside Catylist restates the laws |

## Agent attribution

AI agents act under a person's prompt and post from that person's account
(Catylist ADR-0011). Every post, pull request body and comment an agent
writes starts with a title line naming the agent and the prompting user:

```text
**Claude for @dlworrell**
```

The sweep checks it on every input (Law 4):

- a title naming a different user than the posting account is a violation;
- agent-written text without a title (recognised by markers such as the
  Claude Code footer or a `Co-Authored-By: Claude` line) is a violation;
- an agent-written comment never counts as the owner's approval.

## Trust

Every contributor is untrusted until listed in the trusted-contributor list
(ADR-0010 section 3). The sweep reads it from the AEMS secret `RING0_TRUSTED`
(entries separated by commas or newlines) until Catylist decides where it
lives. An empty or missing list means everyone is untrusted.

Entries are GitHub logins (for example `dlworrell`) and agent names (`claude`,
`chatgpt`, `notion`). An agent-titled post is trusted only when both the agent
and the prompting user are listed and the post comes from that user's account.

| Outcome | Untrusted | Trusted |
|---|---|---|
| `pass` | Shown (and shown again if ring 0 hid it earlier) | Shown |
| `indeterminate` | Hidden until it passes | Shown; reported to the maintainer |
| `violation` | Hidden and reported | Hidden and reported |

## The AI enforcer

- Calls Claude through the official Anthropic Python SDK (`requirements/ring0.txt`),
  installed only in the workflow. The rest of AEMS stays standard-library only.
- Model `claude-opus-5-5` at effort `medium`, set in `config/ring0.json`.
  Server-side refusal fallbacks are enabled (`fallbacks: "default"`).
- The prompt and the pinned Code text are cached; each input is sent as data
  with a JSON schema for the verdict.
- A refusal, an API error, malformed output, a missing `ANTHROPIC_API_KEY`, or
  an input larger than the limit (never truncated) is `indeterminate`.
- It never approves, merges or deletes anything, and its check run states that
  it is AI review, not human review (ADR-0007 §2.6).

## Ledger

Every evaluated input appends one JSON line to `ledger/YYYY/MM/DD.jsonl` on the
`ring0/ledger` branch of AEMS: repository, kind, link, author, trust tier,
SHA-256 of the content (never the content), outcome, action and the non-passing
findings. `state.json` on the same branch holds the last sweep time per
repository, the hashes already checked, the posts ring 0 has hidden, and the
violation issues it has opened. Indeterminate results are not cached, so they
are retried on every sweep.

## Operating it

- **Pause:** disable the workflow in the Actions tab.
- **Dry run:** dispatch the workflow with `dry_run` left on. Nothing is written
  to GitHub; the summary and ledger lines are in the run's artifact.
- **Add a repository:** after it adopts ADR-0000, add it to
  `config/ring0.json`, then add `ring-0` and `ring-0/conduct` to its ruleset as
  required checks from the `catylist-ring-0` App.
- **Secrets (AEMS):** `RING0_APP_PRIVATE_KEY` (required), `ANTHROPIC_API_KEY`
  (without it `ring-0/conduct` is always indeterminate), `RING0_TRUSTED`
  (optional). The workflow uses the `ring-0` environment; restricting that
  environment to the `main` branch keeps the secrets out of other branches.

## Known limits

- GitHub publishes conversation before ring 0 sees it; a failing post can be
  visible for up to one sweep interval, and scheduled runs can start late.
- Issues, reviews, discussions and releases cannot be hidden through the API.
- Wiki pages of private repositories cannot be read; their edits are
  `indeterminate` and go to the maintainer.
- The events API keeps about 300 recent events per repository, which covers a
  30-minute window comfortably.

## Related

- [Catylist Code of Conduct](https://github.com/dlworrell/Catylist/blob/main/CODE_OF_CONDUCT.md)
- [Catylist ADR-0000](https://github.com/dlworrell/Catylist/blob/main/docs/adr/ADR-0000-catylist-code-of-conduct.md)
- [Catylist ADR-0010](https://github.com/dlworrell/Catylist/blob/main/docs/adr/ADR-0010-ring-0-input-gate-and-trust.md)
- [Third-party notice for the prompt](../../prompts/NOTICE-agency-agents.md)
