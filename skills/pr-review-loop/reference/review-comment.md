# The outcome comment

The record. One comment per reviewed commit, posted whatever the outcome. Copy
the body below the last horizontal rule and substitute the `{braces}`. Every
sentence you substitute is written in Strict Simplified Technical English and
linted before posting, as stage 6 of `review-procedure.md` describes.

## The marker

The first line is an HTML comment naming the reviewed commit:

```
<!-- automated-review: {sha} -->
```

**This is what stops every run re-reviewing the same commit.** Without a record
of what has already been looked at, a pull request pays for a fresh review every
time the loop starts, and collects identical comments doing it.

Keying it to the head SHA rather than the pull request number is what makes a new
push get a fresh review while an idle branch costs nothing. It lives in the
comment rather than in a file for the same reason the outcome does: it belongs on
the object it describes, and it needs no storage that has to be set up before any
of this works.

## When not to write one at all

A **deferral** writes nothing: no comment, no marker. The mergeability was not
computed yet, the head moved, the call failed, the response would not parse, the
linter could not run. None of those are verdicts about the commit, and recording
one as though it were makes a transient condition permanent, because the marker
stops anything looking again.

A refusal is an answer. A deferral is the absence of one. The only difference in
the output is that a deferral has none.

## Failed conditions are bullet lists

Every blocker and every failed check is explained the same way: one bullet that
names it, then four sub-bullets in this order, with these labels.

- `Symptom:` what is wrong, as a reader of the pull request would see it.
- `Example:` the evidence. A file and line, a count, or a quoted line, in a code
  span.
- `Root cause:` why it is wrong. Write `Not known.` when the diff does not show
  it. Never guess.
- `Fix:` the change that would clear this condition. It changes the code, the
  tests or the description, never the check.

The labels and their order never change, so the fixer reads each finding without
interpretation and a person can compare two rounds line by line. Each sub-bullet
is one sentence where possible and two at most.

An `engineering` or `architecture` failure with more than one scenario gets one
`Scenario N:` sub-bullet per scenario, most severe first, and each scenario gets
its own four sub-bullets. With one scenario, the four sub-bullets sit directly
under the check.

Here is a filled-in failure, for reference:

```markdown
- ❌ `tests` failed.
  - Symptom: The new tests do not exercise the retry path that this change adds.
  - Example: `tests/test_sync.py` calls `sync()` once and asserts only that it returns.
  - Root cause: Not known.
  - Fix: Add a test that delivers the same message twice and asserts that one row exists.
```

## Substitution rules

- `{outcome line}` is one of:
  - `**Every check passed.** No check objected. A person still decides whether this pull request merges.`
  - `**Not clear.** {one sentence that names every blocker, or every failed check, by its id}`
- The blockers section is omitted when there are none, and the checks section is
  omitted when the review did not get far enough to answer any.
- Every check that was asked appears, passed or not. A check omitted from the
  list reads as one that was not asked.
- `✅` and `❌` mark each check. A passed check stays on one line with its
  reason. A failed check uses the bullet list above.
- The `engineering` and `architecture` lines state the runtime assumed and the
  areas examined, whether the check passed or failed.
- The notes section is omitted when there are no notes, and always for a
  documentation-only review. Its heading says it is advisory, so a reader does
  not mistake a note for a failed check. Each note keeps its altitude tag.
- The two closing lines are fixed. Copy them as written.

Everything below the horizontal rule is the comment body.

---

<!-- automated-review: {sha} -->
## Automatic review

{outcome line}

### Before a review can run

- `{blocker id}` stops the review.
  - Symptom: {what is wrong}
  - Example: {the count, file or setting that shows it}
  - Root cause: {why it is wrong, or "Not known."}
  - Fix: {the change that clears it}

### Checks

- ✅ `{check id}` passed. {the reason, naming the file, criterion or line that decided it}
- ❌ `{check id}` failed.
  - Symptom: {what is wrong}
  - Example: {`file:line` and what the diff shows there}
  - Root cause: {why it is wrong, or "Not known."}
  - Fix: {the change that would clear this check}
- ❌ `{engineering or architecture}` failed. Runtime assumed: {how this code runs}. Areas examined: {the areas}.
  - Scenario 1: {a short name for the most severe scenario}
    - Symptom: {what goes wrong}
    - Example: {`file:line` and the condition that triggers it}
    - Root cause: {why it goes wrong, or "Not known."}
    - Fix: {the change that removes the scenario}
  - Scenario 2: {a short name for the next scenario}
    - Symptom: {what goes wrong}
    - Example: {`file:line` and the condition that triggers it}
    - Root cause: {why it goes wrong, or "Not known."}
    - Fix: {the change that removes the scenario}

### Engineering and architecture notes (advisory, not part of the outcome)

- `[{staff, principal or distinguished}]` {the observation, the file where there is one, and what it would take to address it}

---

_The automatic review read commit `{sha}`. It did not merge or approve this pull request._
_The review runs again only when someone runs `/pr-review-loop` on this pull request after a new push._
