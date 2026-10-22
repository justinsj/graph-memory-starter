---
name: response-format
description: Standard layout for every report, status update, review summary, plan or decision list sent to the user. The outcome comes first, links (PRs first, then tickets, review comments, CI runs) sit directly under it, then the body, tests, decisions, what was not done, files, next step, and questions last. Decisions, problems and questions share one block shape (an ID and a short name as the heading, then plain labeled bullets in a fixed order), so the reader finds the same field in the same place every time. Use before writing any response that reports finished or partial work, lists decisions, describes problems, includes a PR or ticket link, or asks the user something, and before writing a decisions file or report file. Questions also follow the question-format skill. Not for a one-line casual answer.
---

# Response format

The reader switches between many projects and scans a response for three
things: did it work, where is the PR, and what do I need to decide. Every
response puts those in the same place, so the reader never has to search.

## 1. The skeleton

Fixed order. Leave out a part that would be empty. Never reorder the parts.

| # | Part | Heading | What goes there |
| --- | --- | --- | --- |
| 1 | Outcome | none | One or two sentences: what was done or found, and whether it worked. Never a heading, a list or a table. |
| 2 | Links | `## Links` | PRs first, then tickets, review comments, CI runs, deploys and published pages. See section 2. |
| 3 | Body | as the task needs | For example `## What changed`, `## Findings`, `## Results`. Problems go here as F blocks. |
| 4 | Tests | `## Tests` | What ran and the result, failures included. |
| 5 | Decisions | `## Decisions` | D blocks, with `Needs your yes: yes` blocks first. |
| 6 | Not done | `## Not done` | Bullets: what was skipped, not checked or deferred, and why. |
| 7 | Files | `## Files` | One clickable link per line, with the full path. |
| 8 | Next step | `## Next step` | One or two lines: the command to run or the thing that happens next. |
| 9 | Questions | `## Questions for you` | Q blocks (question-format skill). Always last, because the end of the message is what the terminal shows. |

A short response with no headings keeps the same order without the headings:
the outcome sentence, then a `Links:` line, then the rest as prose. A casual
one-line answer with no links needs no skeleton.

HTML reports and other report files use the same order, with the same section
names.

## 2. Links

Links sit directly under the outcome, every time, so a PR is always the second
thing in the response. One link per bullet, in this shape:

```markdown
## Links

- PR: [shop-api#132 Keep first-day invoice lines](https://github.com/example-org/shop-api/pull/132) (open, fix/first-day-lines → main)
- Ticket: [TICKET-12 Invoice completeness](https://example.atlassian.net/browse/TICKET-12) (In Progress)
- Review comment: [Automatic review of 3f9c2a1](https://github.com/example-org/shop-api/pull/132#issuecomment-123)
- CI run: [deploy.yml on 3f9c2a1](https://github.com/example-org/shop-api/actions/runs/456) (passed)
```

- The PR lines come first. A PR you mention but did not open still goes here.
- Each label is one of `PR`, `Ticket`, `Review comment`, `CI run`, `Deploy`,
  `Page`. Add a new label only when none of these fits.
- The link text names the thing in words. A PR shows `<repo>#<n>` and its
  title, and a ticket shows its key and summary.
- The bracket after the link gives the state you checked, not the state you
  expect: `open`, `draft`, `merged` or `closed` with `head → base` for a PR, and
  the workflow status for a ticket.
- Never write a bare `#132` or `TICKET-12` anywhere in the response. Use the link,
  or the key followed by its description in brackets: `TICKET-12 (invoice
  completeness)`.

In a short response, the same links go on one line directly after the outcome:
`Links: PR [shop-api#132 Keep first-day invoice lines](https://...) (open)`.

## 3. Blocks: decisions, problems and questions

All three use one shape:

```markdown
### <ID>. <Short name>

- <Label>: <text>
- <Label>: <text>
```

The ID is `D1`, `D2` for decisions, `F1`, `F2` for problems and findings, and
`Q1`, `Q2` for questions. Numbering restarts in each response. A decisions file
keeps its own numbers, and a response that cites them uses those numbers.

The short name has two to five words. It is a noun phrase that names the
subject, not a sentence: write `Retry limit`, `Backfill scope` or
`Unknown CLI arguments`, not `Should we retry?`. Use the same short name every
time the item is mentioned, as in `D2 (Unknown CLI arguments)`.

Labels are plain text, not bold, one per bullet, in the order given below.
Leave out an optional label instead of writing "N/A", and do not invent labels.
A label's text may continue in indented sub-bullets.

### Decision block (D)

| Order | Label | Required | What it holds |
| --- | --- | --- | --- |
| 1 | Decision | yes | What was decided, as one sentence. |
| 2 | Question | no | The question it answers, naming the exact repo, file, table or endpoint. |
| 3 | Reason | yes | Why this answer. |
| 4 | Source | no | What settled it: `request`, `project: <path>`, `CLAUDE.md`, a preference such as `P1 Workaround instead of full refactor`, `your answer to Q1 (Backfill scope) on <date>`, or `cheapest to reverse`. |
| 5 | Not chosen | no | The main alternative and what it would have changed. |
| 6 | Affects | no | Files, tables, tasks (with their descriptions) that change because of it. |
| 7 | Needs your yes | no | `yes` with the reason, or `no`. Omit it when nothing needs approval. |

```markdown
### D1. Unknown CLI arguments

- Decision: `scripts/export.py` rejects an argument it does not recognize, with a usage error and exit code 2.
- Question: What should `scripts/export.py` do with an argument it does not recognize, such as `--dryrun`?
- Reason: A mistyped `--dryrun` would otherwise run a real export and replace today's file.
- Source: P4 Fail loudly
- Not chosen: Keep ignoring unknown arguments, which keeps old command lines working but lets a typo write.
- Affects: `scripts/export.py`, task 1.1 (replace the `sys.argv[1]` read with `argparse`)
- Needs your yes: yes, because jobs outside the repo may pass extra arguments today.
```

### Problem block (F)

All four labels, in this order. This is the workspace rule for describing a
problem (symptom, example, root cause, solution) in a fixed shape.

| Order | Label | What it holds |
| --- | --- | --- |
| 1 | Symptom | What is wrong, as the user would see it. |
| 2 | Example | One concrete case: a file and line, a row, a count, a command and its output. |
| 3 | Root cause | Why it happens. Write `Not known.` when it is not established. |
| 4 | Fix | The change that would remove it. |

```markdown
### F1. Invoice lines dropped

- Symptom: The invoice total for Acme Widgets is lower than the supplier's statement.
- Example: Batch 1234 has 412 lines in `invoice_lines`, and the statement lists 419.
- Root cause: The date filter in `invoice_loader.py:88` drops lines posted on the first day of the period.
- Fix: Make the start of the date range inclusive, and add a test with a first-day line.
```

### Question block (Q)

The heading is `### Q<n>. <Short name>`, the next line is the question itself,
and the labels are `Context`, `Example`, `Options`, `Reply with` and, when the
question is recorded in a file, `Recorded in`. The question-format skill has
the full rules and an example.

### Answers become decisions

When the user answers a question, record the answer as a decision block that
keeps the question's short name, with
`Source: your answer to Q1 (Backfill scope) on <date>`. In the next response, it
appears under `## Decisions`. In a file that holds decisions, such as an OpenSpec
`decisions.md`, it is added as a new block with the next free D number.

```markdown
### D4. Backfill scope

- Decision: The backfill leaves out the 37 customers who closed their accounts before 2026-09-01.
- Reason: Their partial months pulled the August median down.
- Source: your answer to Q1 (Backfill scope) on 2026-10-22
```

## 4. Order inside a section

- Decisions: `Needs your yes: yes` first, then in the order the work depends on
  them.
- Problems: the most severe first.
- Questions: the ones that block work first.

## 5. Check before sending

For any file that holds blocks or a report (a decisions file, a report, a plan),
run the checker and fix every finding:

```bash
python "<this skill folder>/scripts/check_format.py" <file>
python "<this skill folder>/scripts/check_format.py" --blocks-only <decisions file>
```

`--blocks-only` checks only the D, F and Q blocks, for files that have their own
section layout, such as an OpenSpec `decisions.md`. The checker also reads
standard input. For a long chat response with blocks or links, save the draft to
the scratchpad and check it the same way.

Then confirm by reading:

- The first line says what happened, and a PR link (if any) is the second thing.
- Every block heading is `### <ID>. <Short name>`, and every label is in its
  fixed place.
- Nothing refers to `#132`, `TICKET-12`, `D2` or `Q1` without its description or
  short name.
- The writing follows the writing rules in your `CLAUDE.md`, if it has any.
