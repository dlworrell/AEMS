# Ring-0 change gate

Ring-0's scheduled jobs used to run in full on every tick, even when nothing in any adopted repository had changed. Most runs ended "Nothing to do" after installing the model SDK and walking every repository.

`scripts/ring0_gate.py` lets a scheduled job skip that work when nothing it reacts to has changed.

## What counts as a change

For every repository in the job's configuration (`config/fitment.json` for the fitment cycle), the gate fingerprints:

- the heads of `dev-daily`, `fitment` and the default branch, including a branch that disappears;
- the open pull requests, with their base and head;
- CI results on the `fitment` head, and on the heads of open pull requests into `fitment` or the default branch.

The gate leaves out ring-0's own `fitment` and `fitment/source` checks, so the cycle's own output cannot retrigger it.

## How a scheduled run decides

1. `ring0_gate.py check` computes the fingerprint and compares it with the one recorded after the last successful run, which is stored on the `ring0/ledger` branch at `ring0/gate-<name>.json`.
2. The job runs when any of these hold:
   - the fingerprint differs;
   - nothing has been recorded yet;
   - the last recorded run is older than `--max-age-hours`, which defaults to 6. This is the safety net for anything the fingerprint does not capture.
3. Otherwise the job's later steps are skipped, and the job summary says so.
4. After a successful enforce run, `ring0_gate.py record --config …` recomputes the fingerprint. The recorded state therefore already includes the pull requests, issues and checks the job itself created, and the job's own output does not cause an extra run.

## Fail-safe behaviour

- Manual (`workflow_dispatch`) runs always go ahead.
- If the gate cannot decide, for example because of a GitHub error, the job runs.
- A failed run records nothing, so the next tick tries again.
- Dry runs record nothing.

## Where it is used

- **Fitment cycle** (`.github/workflows/fitment-cycle.yml`): gated.
- **Ring-0 sweep:** not yet gated. It also reacts to comments and labels, which this fingerprint does not capture.
