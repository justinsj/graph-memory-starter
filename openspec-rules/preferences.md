# Preferences for pre-answered OpenSpec questions

The OpenSpec propose workflow answers its own questions instead of stopping to
ask (see `rules.md` in this folder). When the request, the project and the code
do not settle a question, it picks the answer one of these preferences points to,
and lists that preference under "Preferences used" in the change's
`decisions.md`.

A CLAUDE.md rule can extend this to every other question (chat, the
AskUserQuestion tool, plans and reports). Those questions follow the same order
of authority, and each one settled this way is shown as a decision block whose
`Source:` names the preference.

Edit this file to change how future proposals decide. Keep the IDs stable,
because past `decisions.md` files cite them. Add a new preference at the end
with the next free ID instead of reusing an old one.

## Order of authority

When two sources disagree, the higher one wins:

1. What the user said in the request or in the conversation.
2. The project: the `context` in `openspec/config.yaml`, `AGENTS.md`, convention
   docs, decision records, and what the code already does.
3. The user's standing rules: the `CLAUDE.md` files in scope and
   `~/.claude/profile.md`.
4. The preferences below.
5. If the question is still open: the option that is cheapest to reverse.

## The preferences

Each entry has a short label (used in the summary), the rule, and when it does
not apply.

### P1. Workaround instead of full refactor

Make the smallest change that meets the request: a targeted fix or a workaround
inside the existing structure.

Does not apply when the request asks for the refactor, or when the fix cannot
work without it. Then the decision says why.

### P2. Additive, not breaking

Keep contracts backward compatible. Add a field, column, parameter or endpoint
version instead of changing or removing an existing one.

Does not apply when the request asks for the breaking change. A breaking change
to something another team consumes always needs the user's yes.

### P3. Reuse what exists

Use the repo's existing patterns, helpers, libraries and configuration
mechanism. Add no new dependency.

Does not apply when nothing in the repo does this kind of work.

### P4. Fail loudly

Raise errors with enough context to diagnose them. Route unmatched records to a
catch-all that counts them, or fail the run. No silent fallback, no swallowed
error, and no warning in place of an error.

Always applies.

### P5. Read-only data access

Investigation, checks and backtests read from the read-only replica or with a
read-only login, and issue only `SELECT`.

A write, a backfill, a migration or a DDL change is never pre-approved. The plan
can include it, but the decision is marked `Needs your yes`.

### P6. Tests for happy, edge and error paths

Every behavior change gets tests for the happy path, the edge cases and the
error cases. Mocks are allowed where the real dependency cannot be reached.

Does not apply to documentation-only changes.

### P7. Defer extras to follow-ups

Nice-to-have and adjacent work goes into a "Follow-ups" list in the proposal,
not into this change.

Does not apply when the request names that work.

### P8. Ship dark behind the existing flag

A risky behavior change ships behind the repo's existing feature flag or config
switch, off by default.

Does not apply when the repo has no flag mechanism. Do not add one for this
change.

### P9. Dev, then staging, then prod

Rollout tasks go to dev first, then staging, then prod. No plan touches prod
first.

Always applies.

### P10. One shippable change per PR

A PR holds one change that can ship and be checked on its own: the behavior, its
tests and its documentation. Split a change only where each part can go to
production alone and be verified there, or to keep a mechanical change (renames,
moves, formatting, dependency bumps) apart from a behavior change. Do not split
into PRs that only work together, because each one pays the full test run and
review without shipping anything sooner.

When a PR's non-test changes pass about 400 lines, look for a cut that meets
these rules. If there is none, keep the PR whole and say why in its description.
Do not combine separate changes to save a test run: when the full test suite is
the bottleneck, propose running the affected tests on each PR and the full suite
once per batch.

A request for a large refactor keeps its full scope (P1 and P7 do not cut it)
and ships as a series of such PRs. New behavior ships behind the existing flag
when there is one (P8) and goes to dev first (P9).

### P11. Plan in the repo that owns the code

An OpenSpec change lives in the repository whose code it changes. When that
repository has no OpenSpec root, set one up there (`openspec init`) and record
it as a decision, instead of planning the change in another repository that
already has one.

Does not apply when the change spans several repositories: then it lives in the
shared planning repository, and the decision names it. Does not apply when the
user did not ask for OpenSpec.

P12 is not used. It was proposed ("One PR, with its docs") and declined in
favor of P10.

### P13. Test the real path on one unit first

To check that a deployed change works, trigger the real automated path (the
scheduled job, the queue consumer, the step that fires the refresh) on the
smallest unit, such as one message or one client, and watch it finish before
running the rest. Prefer this over a manual substitute for the path, and over
waiting for the next scheduled run. A repair to production data is tested
locally first.

When the action needs the user's yes (`rules.md` section 1), this preference
picks the recommended option. It does not replace the yes.

### P14. One general rule over a special case

Prefer a rule that covers every similar case (a naming pattern, the same output
shape in every period) over a fix for one client, one account or one period.
Keep an output the same shape even when an edge case repeats a value.

When the general rule also changes other clients' results, the decision lists
them.

### P15. Separate worktree, changes through PRs

Work that runs beside other work goes into its own git worktree, not a branch
parked in the same checkout. Changes reach a shared branch (main, dev, staging)
through a PR from the feature branch, never by merging locally and pushing. A
branch starts from the branch where the code it needs already lives.

Does not apply to a repository whose owner commits to its main branch directly.

### P16. Install tools for the whole machine

Install a developer tool so it works everywhere: user-wide or machine-wide
rather than inside one project. A skill is installed in `~/.claude/skills` as
well as in the project.

Does not apply when a project pins its own version of the tool (for example a
`.nvmrc` file or a project virtual environment). The project keeps its version.
