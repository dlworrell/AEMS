# Fitment branch retention incident — 2026-10-26

Status: code repair prepared; live integration-ruleset rollout still required.
Authority: Catylist ADR-0013, extending ADR-0006. AI-assisted investigation and
tests; no independent human review is claimed.

## Observed failure

The supplied [Fitment Cycle job](https://github.com/dlworrell/AEMS/actions/runs/40382778583/job/121783849779)
passed its cycle tests, created the installation token and then failed with
both `dlworrell/AEMS` and `dlworrell/atarix` missing `dev-daily`. The workflow
source was AEMS `268089d78e4c58f16fbcc2edfdcdcd2914543c81`, attempt 2.
This failure occurred in branch preflight, before publication or model review;
the earlier signing-publisher incident is a different failure.

Both repositories had `delete_branch_on_merge: true` and only the active
`protect-default-branch` and `protect-release-tags` rulesets. Neither had
`protect-integration-branches`. Their retained `fitment` branches were also
unprotected. AEMS's cleanup script already keeps both integration branch names.

| Repository | Last daily promotion | Missing branch's recorded head | Retained fitment head |
|---|---|---|---|
| AEMS | [PR #48](https://github.com/dlworrell/AEMS/pull/48), merged 11:30:03 UTC | `89b443eabc325cac9d9fc54809ec8a1ef9b359ec` | `ecad36ecca1ac98628fa3ea9e4422e6b6bca73b7` |
| atarix | [PR #86](https://github.com/dlworrell/atarix/pull/86), merged 12:10:48 UTC | `822b990fed8f2aa070ca798e6fbfbe2de1866b32` | `eaa04cd9a586bb21106042320f279f372ac79c2f` |

The observed sequence and enabled automatic deletion support the hypothesis
that GitHub deleted the unprotected daily heads after promotion. A deletion
audit event was not obtained, so the specific deleting actor is not asserted.
The confirmed root configuration gap is the absent active retention rule.

Each recorded daily head was proved to be the merge base of its retained
`fitment` head, with zero commits behind and one commit ahead. After a fresh
404 for the missing daily ref, that ref was recreated at the exact recorded
head. Existing refs, default history and fitment heads were not moved.

## Controlled before-and-after experiment

The original cycle at the recovered AEMS head and the repaired cycle ran
against the same in-memory GitHub fixtures. The daily head was ahead with
passing CI. No live API mutations were used in the experiment.

| Fixture | Before | After |
|---|---|---|
| Daily branch missing | Exit 1; no writes; advice to create from main | Exit 1; no writes; recovery advice preserves the last promoted head and reports absent rules |
| Both branches exist, no active deletion rules | Exit 0; opens one promotion and posts a check | Exit 1; no repository writes or model calls |
| Both branches exist, active deletion rules | Exit 0; opens one promotion and posts a check | Same permitted behavior |

The missing-branch failure is not hidden or converted to a successful skip.
All **92 focused tests passed** across retention preflight, the full existing
fitment tests, ruleset planning and merged-branch cleanup. Tests include
unreadable/malformed evidence, a misleading `protected` flag, paginated active
rules, both integration branch names and the protected positive control.
The repository's full required suite also passed: **304 tests** via
`python3 -m unittest discover -s tests -q`.
Machine results: [controlled experiment](fitment-branch-retention-20261026.json).

Live read-only checks after branch restoration still returned `blocked` for
both repositories: both daily and fitment lacked an active deletion rule.
That is the expected truthful result until settings are repaired; unit-test
success is not represented as successful live rollout.

## Repair and acceptance

1. Review and merge the signed topic PRs into each recovered `dev-daily`.
2. In AEMS **Apply Catylist Rulesets**, select only
   `dlworrell/AEMS,dlworrell/atarix`, pin the Catylist inventory and
   repo_templates source commits, and inspect a `dry_run: true` plan.
3. Apply the reviewed plan with `dry_run: false` through the existing
   `ruleset-admin` environment approval. The existing planner already selects
   integration protection for both adopted repositories. Do not weaken the
   existing signature or merge requirements.
4. Run the preflight in each repo. Both refs must exist and each must return
   an active effective `deletion` rule. Independently inspect the full ruleset
   for the other ADR-0006 obligations, including no bypass actors.
5. Let the scheduled AEMS cycle observe the repaired state. Only then merge
   subsequent `dev-daily` → `fitment` and `fitment` → `main` promotions.
   Confirm both long-lived refs remain after promotion and retain this record.

The code adds no administration token, branch writes, automatic merges or
new signing key. Atarix consumes the same read-only action pinned to the
reviewed AEMS commit; the model key remains central. The new retention check
is diagnostic until explicitly adopted as a required check. Roll back code
only through reviewed revert PRs; retain integration deletion protection.

## Git Supervisor development-plan alignment

Applied `/repo/prompt/PRM-0008+git-supervisor-branch-protection-signing-skill.txt`
and `/repo/prompt/PRM-0224+git-workflow-master-skill.txt`, with the repository's
`prompts/git-workflow-dev-environment.md` governing Catylist-specific differences.
The already completed signing/ruleset setup phases are not restarted. No new
key, phone Git client or relaxed signature protection is required.

Topic changes branch from the recovered `dev-daily` heads and target
`dev-daily`. The release path remains owner-merged `dev-daily` → `fitment` →
`main`; published history is not rebased, squashed or force-pushed. PRs include
the agent identity, governing ADRs, completed repository checklist and exact
test/commit evidence. Workflow changes require the owner's governance-approval
comment after the final push. These repairs remain for the owner to approve
and merge; machine signing is not an owner approval. Live ruleset application
retains the existing dry-run-first, approval-gated process.

## Sources

- [Catylist ADR-0013](https://github.com/dlworrell/Catylist/blob/main/docs/adr/ADR-0013-daily-fitment-and-release-branches.md)
- [Integration ruleset template](https://github.com/dlworrell/repo_templates/blob/main/rulesets/protect-integration-branches.json)
- [GitHub effective branch rules](https://docs.github.com/en/rest/repos/rules#get-rules-for-a-branch): returns active rules, including inherited rules; requires metadata read access.
- [GitHub automatic branch deletion](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-the-automatic-deletion-of-branches): protection and rulesets can prevent head-branch deletion.
