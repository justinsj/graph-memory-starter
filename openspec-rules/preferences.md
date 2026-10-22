# Preferences for pre-answered OpenSpec questions

The OpenSpec propose workflow answers its own questions instead of stopping to
ask (see `rules.md` in this folder). When the request, the project and the code
do not settle a question, it picks the answer one of these preferences points to,
and lists that preference under "Preferences used" in the change's
`decisions.md`.

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
