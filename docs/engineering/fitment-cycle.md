# Fitment cycle

Status: Active
Owner: AEMS
Authority: [Catylist ADR-0013](https://github.com/dlworrell/Catylist/blob/main/docs/adr/ADR-0013-daily-fitment-and-release-branches.md)

## The flow

```text
fix/<issue>-<slug>, feat/<slug>, ...   (one author, cut from dev-daily)
        │  pull request, CI + ring-0
        ▼
    dev-daily      daily merge scope: bug fixes and current issues
        │  promotion PR opened by AEMS when dev-daily is ahead and green
        ▼
     fitment       AEMS agents review documentation and tests;
        │          findings → issues assigned to the authors;
        │          fixes come back through dev-daily
        │  release candidate PR opened by AEMS when the fitment check passes
        ▼
       main        released work; release workflow parks for owner approval,
                   then tags v<version>
```

## What runs

`.github/workflows/fitment-cycle.yml` runs `scripts/fitment_cycle.py` at :15 and
:45 every hour (between ring-0 sweeps) as the `catylist-ring-0` App. For each
repository in `config/fitment.json` it:

| Step | Result |
|---|---|
| Source rules | `fitment/source` on open pull requests: into `fitment` only from `dev-daily`, into `main` only from `fitment` |
| Fixes | A `fitment` issue closes when a commit with `Fixes #N` reaches `fitment` |
| Review | The [fitment reviewer](../../prompts/fitment-reviewer.md) reads the `fitment` commits not reviewed yet (file names, patches and commit messages; never runs code) |
| Findings | One issue per finding, labelled `fitment`, its severity and its kind, assigned to whoever last changed the file, and never filed twice while open |
| Follow-ups | A `minor` finding in a file changed by a commit that says `Fixes #N` for a `fitment` issue becomes a comment on #N, not a new issue, and is never posted twice. `blocker` and `major` findings always get their own issue. Follow-ups do not hold the gate |
| Gate | `fitment` on the `fitment` head fails while another check on it fails, a `blocker` or `major` fitment issue is open, or the review could not run |
| Promotion | Opens `dev-daily` → `fitment` when `dev-daily` is ahead and its CI is green, and `fitment` → `main` when the gate passes |

It never approves, merges or pushes. The owner merges every promotion. It opens a promotion
only from a branch a ruleset protects from deletion (`protect-integration-branches`);
otherwise merging it would let "delete branch on merge" remove `dev-daily` or
`fitment`, as happened once in the atarix trial.

## For contributors

1. Cut your branch from `dev-daily` (`git switch --no-track -c fix/42-short origin/dev-daily`) and open your pull request into `dev-daily`.
2. If the fitment review assigns you an issue, fix it on `fix/<issue>-<slug>` into `dev-daily` with `Fixes #<issue>` in the fix commit's message.
3. If a finding is wrong, say why on the issue. The owner closes it as not planned.
4. A minor follow-up posted on an issue you fixed is advisory: address it in a later change to that file, or file an issue if it should be tracked on its own.

## Trial

The cycle is trialled on AEMS itself and on atarix, which give the reviewer
real source code to review. In atarix, the generated reports that ring-0
publishes (Catylist ADR-0012) target `dev-daily`, so they are promoted and
reviewed with everything else.

## Operating it

- **Adopt a repository:** create `dev-daily` and `fitment` from its default
  branch, add the CI and release workflows from repo_templates, add the
  repository to `config/fitment.json`, then run the ruleset workflow so
  `protect-integration-branches` applies. Verify that both branches exist and
  each has an active deletion rule **before the first promotion**. After its first clean cycle, require
  `fitment` and `fitment/source` on `main`.
- **Dry run:** dispatch the workflow with `dry_run` left on.
- **Pause:** disable the workflow in the Actions tab.
- **State:** `fitment/state.json` on AEMS's `ring0/ledger` branch records the
  last reviewed `fitment` head per repository and the checks already posted.
  Deleting a repository's entry makes the next cycle review from `main` again.
- **Review retry limit:** a paid review of one `fitment` head is attempted at
  most `MAX_REVIEW_ATTEMPTS` (3) times. After that the `fitment` gate keeps
  failing with "it is retried when fitment changes", and no further model
  calls are made for that head. An unconfigured reviewer (no API key) costs
  nothing and does not use up attempts. To retry an unchanged head after an
  outage, remove `review_attempts`, `review_error_head` and `review_error` from
  that repository's entry in `fitment/state.json`, or move `fitment` (a new
  head resets the count).
- **Stored findings:** findings from a paid review are stored as
  `pending_findings` (with `pending_compare`) before
  they are filed. If filing fails, the next cycle files them without asking the
  model again, even if `fitment` has moved.

## Branch retention and recovery

Before reviewing or writing checks, issues or promotion PRs for a repository,
the cycle reads both branch heads and their effective active rules. A missing
branch, missing deletion rule or unreadable evidence blocks that repository.
This preflight is read-only and needs contents/metadata read access; it does
not grant the ring-0 App administration or branch-write permissions. A
`protected: true` flag alone does not establish deletion protection.

Run the same preflight locally or in a hosted workflow:

```sh
python3 scripts/check_integration_branches.py --repository dlworrell/AEMS
```

The composite action `.github/actions/integration-branches` exposes the check
to other repositories; pin it to the reviewed full commit SHA and grant only
`contents: read`. No target-repository checkout or model key is required.
It checks branch existence and active deletion rules, not complete ruleset
compliance, bypass actors, CI correctness or human approval.

For an existing repository, recover a deleted branch from its last verified
head in promotion history; inspect later PRs for any newer lost work. Creating
it from `main` can abandon unreleased daily work. If the branch already exists,
inspect it and never reset it automatically. Then run **Apply Catylist Rulesets**
with pinned Catylist and repo_templates commits, the affected repository filter
and `dry_run: true`. Inspect the plan, rerun with `dry_run: false`, and approve
the existing `ruleset-admin` environment gate. Verify effective deletion rules
on both branches before merging another promotion. Keep automatic deletion
enabled for ordinary topic branches as ADR-0006 requires.

Merging this code does not change repository settings. The ruleset rollout is
a separate required operation; an unsafe or unavailable live preflight must
remain red until that operation succeeds. Existing protection and promotion
history are never rewritten to make the check pass. The preflight observes
current state, not an atomic guarantee against a later settings change.

See the [2026-10-26 incident record](reports/fitment-branch-retention-20261026.md).
GitHub documents the [effective branch-rules endpoint](https://docs.github.com/en/rest/repos/rules#get-rules-for-a-branch),
which excludes disabled and evaluate-mode rulesets.

## Known limits

- The review sees patches, not whole files, and GitHub omits patches for very
  large files and changes of more than 300 files; the reviewer is told when a
  patch is missing.
- A finding is the model's judgement. It is evidence for the author and the
  owner, not a verdict, and the issue thread is where it is disputed.
- Without `ANTHROPIC_API_KEY` the review cannot run, so the `fitment` check
  holds every release until the key is set.
