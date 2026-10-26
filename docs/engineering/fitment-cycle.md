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

## Trial

The cycle is trialled on AEMS itself and on atarix, which give the reviewer
real source code to review. In atarix, the generated reports that ring-0
publishes (Catylist ADR-0012) target `dev-daily`, so they are promoted and
reviewed with everything else.

## Operating it

- **Adopt a repository:** create `dev-daily` and `fitment` from its default
  branch, add the CI and release workflows from repo_templates, add the
  repository to `config/fitment.json`, then run the ruleset workflow so
  `protect-integration-branches` applies. After its first clean cycle, require
  `fitment` and `fitment/source` on `main`.
- **Dry run:** dispatch the workflow with `dry_run` left on.
- **Pause:** disable the workflow in the Actions tab.
- **State:** `fitment/state.json` on AEMS's `ring0/ledger` branch records the
  last reviewed `fitment` head per repository and the checks already posted.
  Deleting a repository's entry makes the next cycle review from `main` again.

## Known limits

- The review sees patches, not whole files, and GitHub omits patches for very
  large files and changes of more than 300 files; the reviewer is told when a
  patch is missing.
- A finding is the model's judgement. It is evidence for the author and the
  owner, not a verdict, and the issue thread is where it is disputed.
- Without `ANTHROPIC_API_KEY` the review cannot run, so the `fitment` check
  holds every release until the key is set.
