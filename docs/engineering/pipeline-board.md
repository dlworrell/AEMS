# Pipeline board

Catylist ADR-0013 moves every change through four places:

1. a topic pull request into `dev-daily`;
2. a promotion pull request from `dev-daily` into `fitment`;
3. a release-candidate pull request from `fitment` into the default branch;
4. a release.

The pipeline board shows where each change is in that sequence, in one place.

## Where to look

The board is the open AEMS issue titled **Pipeline board**, labelled `pipeline-board`. Pin it once from the issue page (**Pin issue**) so it stays at the top of AEMS's issue list, including in the GitHub mobile app.

## What it shows

- **Needs you.** Promotion and release-candidate pull requests, each marked *ready to merge* or *waiting on checks*. Also listed:
  - repositories whose `fitment` branch is ahead of the default branch but which have no release candidate open yet;
  - pull requests that target the default branch directly, skipping the flow. Examples are Dependabot security updates and bot-opened pull requests. Route these through `dev-daily`, or close them.
- **Stages.** One row per repository in `config/fitment.json`, with:
  - open topic pull requests;
  - commits waiting to move `dev-daily → fitment`;
  - commits waiting to move `fitment → main`;
  - the latest release.
- **In flight.** Each recent topic pull request that has not reached the default branch yet, with the pull request that carried it. For example: `#137 → in promotion #138 → awaiting RC`.
- **Landed.** Recent changes that reached the default branch, collapsed under each repository. Each shows its full chain, for example `#59 → in promotion #60 → in RC #63 → released v0.1.2`.

"Recent" means topic pull requests merged into `dev-daily` in the last 14 days, up to 10 per repository.

## How it works

`.github/workflows/pipeline-board.yml` runs `scripts/pipeline_board.py` at :20 and :50, five minutes after each fitment cycle. It can also be started manually.

- **Reading.** The workflow reads every repository with a catylist-ring-0 App token that has read-only `contents` and `pull-requests` permissions.
- **Writing.** It edits only the AEMS board issue, using the workflow's own `issues: write` token.
- **No noise.** When nothing but the timestamp would change, the issue is not edited.

A change counts as having reached a branch when its merge commit is an ancestor of that branch. Its carrier is the first merged promotion or release-candidate pull request whose merge commit contains it.

To run it locally (read-only):

```sh
RING0_APP_TOKEN=… python3 scripts/pipeline_board.py --dry-run
```

## Limits

- The board reports state; it never merges, approves, retries, or changes settings.
- A repository it cannot read, or one missing `dev-daily` or `fitment`, shows a warning row instead of failing the whole board.
- The release column shows the latest GitHub release. A change counts as released only when the latest release's tag contains it.
