# Omnibus merges

Implements Catylist ADR-0016. The owner approves a batch of pull requests,
across any repositories where `catylist-ring-0` is installed, by merging one
AEMS pull request. ring-0 then merges the batch in order, at the commits the
owner approved.

## Approving a batch

1. Write the manifest. `plan` records each pull request at its current head:

   ```sh
   python3 scripts/omnibus_merge.py plan --id adr-0000-wave-1 \
     --summary "Adopt ADR-0000 in the first five repositories" \
     dlworrell/atarix#97 dlworrell/code-noodling#80 > omnibus/adr-0000-wave-1.json
   python3 scripts/omnibus_merge.py validate --body omnibus/adr-0000-wave-1.json
   ```

   `validate --body` prints the table for the omnibus pull request body.
2. Open a pull request into AEMS `dev-daily` that adds only that file, with
   the table as its body. The **Omnibus Merge** workflow validates it.
3. The owner reads the table and merges. That merge is the approval.

## What happens on merge

The push to `dev-daily` runs **Omnibus Merge** in the `ring-0` environment,
with the executor checked out from AEMS `main`. For the manifest the push
added, it:

- confirms the omnibus pull request was merged by an approver in
  `config/omnibus.json` into `dev-daily`, that its merge commit is verified,
  and that no other pull request ever changed the manifest;
- for each entry in order, refuses unless the pull request is open, not a
  draft, on the listed base, at the approved head, `mergeable_state` is
  `clean`, every check on the head passed, and it was not authored by
  `catylist-ring-0[bot]` (except the classes below); then merges it by merge
  commit with the approved head as the expected `sha`, and comments the
  approval on it;
- stops at the first refusal, marking later entries `not-attempted`;
- comments the results on the omnibus pull request and records them in
  `omnibus/<id>.json` on the `ring0/ledger` branch.

## After a refusal

Fix the cause (push a fix, wait for checks, resolve a conflict), then approve
the remaining pull requests with a new manifest and a new id. Manifests are
immutable: editing one after approval, or reusing an id, is refused.

To repeat a run of an approved manifest, for example after checks finished,
dispatch **Omnibus Merge** with the id. It defaults to a dry run; set
`dry_run` to false to merge. Entries already merged at their approved commit
are reported as `already-merged`.

## ring-0's own pull requests

Catylist ADR-0017 (Code 1.2.0, Law 4) lets an omnibus carry pull requests
that ring-0 opened, in three classes only:

| Class | Head → base (same repository) | Also requires, posted by `catylist-ring-0` |
|---|---|---|
| promotion | `dev-daily` → `fitment` | `fitment/source` |
| release candidate | `fitment` → the default branch | `fitment/source` and `fitment` |
| automation | `automation/*` → any | nothing extra |

Any other ring-0-authored pull request is refused. The merge commit and the
comment name the class and ADR-0017. Merging a release candidate publishes
nothing: the release workflow still waits at the `release` environment.

## Limits

- ring-0 merges a pull request it authored only in the classes above, and
  only when an omnibus approved its exact head.
- An omnibus never publishes a release (Law 5).
- At most `max_entries` (100) pull requests per manifest.
- The approval is found among the 200 most recently updated closed pull
  requests into `dev-daily`. A push finds it at once; a dispatch of a manifest
  approved longer ago than that is refused and needs a new omnibus.
- The executor runs from `main`, so changes to it take effect after release.
