# OpenSpec workspace rules: pre-answered questions, decisions and mockups

These rules add to the OpenSpec workflows used in this workspace:

- propose and fast-forward (the `openspec-propose` and `openspec-ff-change`
  skills, and the `/opsx:propose` and `/opsx:ff` commands),
- apply (`openspec-apply-change`, `/opsx:apply`),
- update (`openspec-update-change`, `/opsx:update`).

They apply to every copy of those workflows: the personal copies in
`~/.claude/skills` and `~/.claude/commands/opsx`, and the team copies inside a
repo. They do not relax any guardrail of the workflows, with one exception:
under P11, propose may run `openspec init` (section 1). Propose still writes
planning artifacts only, and apply still pauses on errors and on added scope.

Preferences live in `preferences.md` in this folder.

---

## 1. Propose: pre-answer every question

Do not stop to ask the user during propose. Each time the workflow would ask,
answer the question yourself and record the answer as a decision. This covers
material ambiguity in the request, an artifact that needs user input, an unclear
target project, and a change name that already exists.

To answer one question:

1. Write the question as the user would have seen it. Name the exact repo, file,
   table and schema, environment or endpoint.
2. Look for the answer in the order `preferences.md` gives ("Order of
   authority"), and stop at the first source that settles it.
3. Note the answer, the source that settled it, and the main alternative you did
   not choose.
4. Write the artifacts as if the user had given that answer.

Never invent a fact to settle a question. If the code or data that would settle
it cannot be read, the decision says so and picks the option that is cheapest to
reverse.

A change name that already exists is a question about the change. Do not touch
the existing change. Use the next free name (`<name>-2`, `<name>-3`) and record
the choice as a decision.

Two situations are not questions about the change. Handle them this way:

- The request has no description at all. There is nothing to decide from, so
  ask what to build.
- There is no OpenSpec root and the user asked for OpenSpec explicitly. When
  `preferences.md` has P11 (Plan in the repo that owns the code) and one
  repository owns the code the change edits, P11 is the user's standing request
  to set OpenSpec up there. Run `openspec init --tools claude` in that
  repository: an agent's shell has no terminal, and without `--tools` the
  command stops when the repository has no tool folder yet. The command writes
  OpenSpec's skill and command copies into that repository's `.claude/` folder,
  not into `~/.claude`, so `apply_openspec_rules.py` does not patch them. The
  OpenSpec rule in `CLAUDE.md` keeps these rules in force there. Record the
  setup as a decision, and continue. Otherwise do not initialize anything. Stop
  and say so, because setting up OpenSpec in a repo is the user's call.

### Decisions that need the user's yes

Pre-answer these with the safe option and mark them `Needs your yes: yes`:

- a write to a production database, a backfill, a migration or a DDL change,
- deleting or overwriting data, files, branches or another person's work
  (the one exception is the `openspec init` that P11 allows in section 1),
- anything that notifies people or publishes: Slack, Jira, GitHub comments,
  email, a deploy to prod,
- a new recurring cost: a paid service, a larger instance, a more expensive
  model,
- a breaking change to an API, table, event or file another team consumes,
- a change to permissions, grants, IAM roles or secrets.

---

## 2. Propose: write decisions.md

Write `decisions.md` in the change folder (the `changeRoot` that
`openspec status --change "<name>" --json` returns), next to `proposal.md`.
Write it after the last artifact, so it matches the final plan.

`decisions.md` is not a schema artifact. `openspec status` does not list it,
`openspec validate` ignores it, and `openspec archive` moves it with the change.

Use this template:

```markdown
# Decisions: <change-name>

Status: pending review
Written by the propose workflow on <YYYY-MM-DD>. Each decision answers a question the workflow would otherwise have asked.

## Preferences used

- P1 Workaround instead of full refactor: settled D1 (<short name>) and D3 (<short name>).
- P6 Tests for happy, edge and error paths: settled D4 (<short name>).

## Decisions

### D1. <Short name>

- Decision: <what the plan does, in one sentence>
- Question: <the question the workflow would have asked, naming the exact repo, file, table or endpoint>
- Reason: <why this answer>
- Source: <request | project: <path> | CLAUDE.md | P<n> <preference label> | cheapest to reverse>
- Not chosen: <the main alternative>, which would have <its consequence>
- Affects: <artifact and section>, task <id> (<what the task does>)
- Needs your yes: no

## Changes to decisions

None yet.
```

Rules for the file:

- Each decision is a decision block from the `response-format` skill: a
  `### D<n>. <Short name>` heading, then the labels in the fixed order shown
  above. The short name has two to five words and names the subject
  (`Unknown CLI arguments`, `Retry limit`), not the question.
- One decision per question. Number them D1, D2 and so on, with the decisions
  marked `Needs your yes: yes` first, then in the order the plan depends on
  them.
- List a preference under "Preferences used" only if it settled at least one
  decision, and name each decision with its short name.
- Each decision stands alone. A reader who sees only that block knows what was
  decided, about which thing, and why.
- If no question came up, write "No open questions came up." under Decisions and
  keep the file. Apply looks for it.
- Check the file before showing it:
  `python <response-format skill folder>/scripts/check_format.py --blocks-only <decisions.md>`,
  when the response-format skill is installed.
  Fix every finding.

---

## 3. Propose: require a deliverable and a mockup

`proposal.md` gets a `## Deliverable and mockup` section directly after
`## What Changes`. A proposal without this section is not complete. The section
has three parts:

1. What the user gets, in one or two sentences, naming the concrete thing: a
   page, an endpoint, a table or view, a report, a script, a job, a document.
2. Where to see it: the URL path, file path, command or table name, and the
   environment.
3. A mockup of the finished deliverable. Choose the form by type:

| Deliverable | Mockup |
| --- | --- |
| UI page or component | ASCII wireframe in a `text` block, plus `mockup.html` in the change folder: a static page styled per the repo's `DESIGN.md` when it has one. Link to it from the section. |
| API endpoint | Example request and response with realistic values, plus one error response |
| Table, view or ETL output | Column list with types, the grain (one row per what), and 3 to 5 sample rows |
| Report, spreadsheet or HTML report | Section outline, plus one sample table with representative rows |
| Script, CLI or scheduled job | Example command and its console output, plus one failure output |
| Event, message or webhook | Sample payload |
| Infrastructure or configuration | Config snippet before and after, or a Mermaid diagram |
| Documentation only | Heading outline with one line per section |
| Internal change with no visible output | The interface before and after (function signature, config key), and the test output that proves the change |

Mockup rules:

- The values are examples. Label them "Example values". Never paste real
  customer data, personal data, secrets or database hostnames.
- Check Mermaid and ASCII diagrams before writing them (the project's
  content-validation rules, when it has them).
- The mockup is what the reviewer signs off on. `tasks.md` includes one task
  that builds the deliverable to match the mockup, and one task that checks the
  result against it.

---

## 4. Propose: what to show at the end

Lay out the end-of-propose message as the `response-format` skill says, with
these parts in this order:

1. The outcome: one or two sentences naming the change and saying that
   `openspec validate --strict` passed (or what failed).
2. `## Links`, only when a PR or ticket is involved.
3. `## Artifacts`: each artifact with a one-line description, plus any
   conditional artifact you skipped and why.
4. `## Deliverable`: the first sentence of the deliverable section, then the
   mockup or the link to `mockup.html`.
5. `## Decisions`: first the "Preferences used" list from `decisions.md`, then
   every decision block, with the decisions marked `Needs your yes: yes` first.
   In chat, each block shows `Decision`, `Reason`, `Source` and, when it is yes,
   `Needs your yes`. The full blocks stay in `decisions.md`.
6. `## Files`: clickable links to `proposal.md`, `design.md`, `tasks.md`, the
   spec files, `decisions.md` and `mockup.html` when it exists.
7. `## Next step`, with this text. Fill in the example from one of this
   change's own decisions, using its real number and a real alternative from
   its `Not chosen` line, so the example matches the list above it:

> To change a decision, reply with its number and the new answer (for example
> `D<n>: <the alternative from that decision's Not chosen line>`), and I will
> update the plan. Run `/opsx:apply` when the decisions look right.

---

## 5. Apply: show the decisions before any code

When the apply instructions return a state that proceeds to implementation, and
before the first task:

1. Read `decisions.md` from the change folder. If it is missing (an older change,
   or a change written by a teammate), say "This change has no decisions.md" and
   continue the workflow as written.
2. Show the preferences used and the decision blocks under a `## Decisions`
   heading, in the format of section 4, part 5.
3. Running apply accepts the decisions shown, except the ones marked
   `Needs your yes`. If any of those has no yes from the user, either in this
   conversation or under "Changes to decisions", ask about all of them in one
   message (question-format skill) and start no task until the user answers.
   Each question keeps the decision's short name, so `D2 (Unknown CLI
   arguments)` is asked as `### Q1. Unknown CLI arguments`.
   Record each answer under "Changes to decisions". If the user says no, that
   is a change to the decision: update the plan as section 6 says before any
   task starts.
4. Only when no decision is still waiting for a yes, change the status line to
   `Status: accepted on <YYYY-MM-DD>, when apply started`. While one is waiting,
   leave the status as `pending review`.

If a decision proves wrong during implementation, it is a design issue. Pause as
the apply workflow says, and when the user decides, record the change under
"Changes to decisions".

---

## 6. Update: keep decisions.md in step

When the update workflow revises a change that has a `decisions.md`:

- Reconcile `decisions.md` together with the schema artifacts. A revision that
  changes an answer updates that decision block's `Decision`, `Reason`,
  `Source` and `Affects` lines, and keeps its number and short name. The new
  `Source` is `your answer on <YYYY-MM-DD>`.
- Add one bullet per changed decision under "Changes to decisions":
  `- D<n> (<Short name>) changed on <YYYY-MM-DD> by the user: <old decision> → <new decision>`.
  Remove the "None yet." line the first time.
- A reply such as `D2: keep ignoring unknown arguments` is a request to change
  D2. Draft the revision of every artifact the decision affects, as the update
  workflow says.
- If apply has not started, set the status back to `Status: pending review`.
- After writing, run the checker on `decisions.md` (section 2), then show the
  decision blocks again, in the format of section 4, part 5.

---

## 7. After OpenSpec regenerates its files

`openspec update` and `openspec init` rewrite the personal copies in
`~/.claude/skills/openspec-*` and `~/.claude/commands/opsx/`, which removes the
short blocks that point here. The OpenSpec section in `CLAUDE.md` keeps these
rules in force anyway. To restore the blocks, run this from the folder that holds this file:

```bash
python apply_openspec_rules.py
```

The script is safe to re-run: it skips blocks that are already there. If OpenSpec
changed the text a block anchors to, the script stops with an error that names
the file and the block, and writes nothing. Update that anchor in the script and
run it again. Its tests live with its source, in
`tests/test_apply_openspec_rules.py`.

What the script adds:

| File | Where | Block |
| --- | --- | --- |
| `skills/openspec-propose/SKILL.md` and `commands/opsx/propose.md` | after the "Planning boundary" paragraph | "Workspace rules" paragraph pointing to sections 1 to 4 |
| same two files | step 1 ambiguity line, step 6c, the two "ask" guardrails | "pre-answer and record" in place of "ask" |
| same two files | before "Show final status" | step "Write decisions.md" (section 2) |
| same two files | Output | the three parts of section 4 |
| `skills/openspec-apply-change/SKILL.md` and `commands/opsx/apply.md` | between step 4 and step 5 | step "4b. Show the decisions" (section 5) |
| `skills/openspec-update-change/SKILL.md` and `commands/opsx/update.md` | after step 4 | step "4b. Reconcile decisions.md" (section 6) |
