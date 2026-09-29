# projects

Projects and their statuses, read from requests, meeting transcripts and
session write-ups, planned with you, and answered from the graph like
everything else. The design is `docs/projects-proposal.html`; what it measured
is `docs/projects-results.html`.

    model.py            the record, the change-set vocabulary, validate(), apply(), health()
    ingest.py           an input in, a proposed change set out (one claude -p call)
    ingest-prompt.md    what that call is told
    review.py           what is waiting: show, apply, reject; the session-start notice
    plan.py             records a plan agreed with you, from the discussion
    status.py           a status or step change in your own words
    board.py            BOARD.md, or one project's card
    cases.py, cases/    seven worked cases and the inputs they quote
    eval_ingest.py      re-tests ingest against the cases with the real model
    ../commands/        /project-new, /project-plan, /project-review for Claude Code

## How it goes

1. **An input arrives.** It can be a request (`/project-new`), a transcript
   (`python projects/ingest.py meeting.md`), or a session write-up, which the
   digest sends on its own. The input is kept under `inputs/`. One Claude call
   proposes a change set: every change quotes the input. Code checks it, and
   it waits in `projects/pending/`.
2. **You review it** (`/project-review`, or `python projects/review.py`).
   Applying writes `projects/records/<id>.json` and appends to its
   `.log.jsonl` history, then rebuilds `graph.db` and `projects/BOARD.md`. The
   next session start says when updates are waiting.
3. **You agree a plan** (`/project-plan <id>`). Claude researches first:
   - memory, then documents and code, read only, at most 20 tool calls;
   - then it asks what it could not find, drafts the steps, and waits for your
     explicit agreement.

   `plan.py` then saves the discussion under `inputs/discussions/` and records
   the plan, so every step quotes a line you agreed.
4. **Status moves** through later inputs, the same way, or at once through
   `python projects/status.py <id> "why" --status blocked`. Your words are
   saved and quoted.
5. **Questions are answered from the graph.** A project is an entity, so the
   hook finds it by its title, an alias, or a word of its title. The answer
   includes:
   - its status with the quote behind it;
   - its plan in a line: progress, what is being done, what is next;
   - the whole plan, the deliverables or the history, when the question asks;
   - for a question naming no project ("what's blocked?", "what is Marcus
     working on?"), the projects table instead.

   Everything carries the date it was learnt, so "the status on 14 September"
   gets that day's answer and nothing learnt later.

## A change set

Claude never edits a record. It answers with changes, each quoting the input
word for word:

    {"input": "inputs/2026-09-24-support-sync.md", "kind": "transcript", "on": "2026-09-24",
     "changes": [
      {"op": "set_step", "project": "helpdesk-migration", "n": 1, "status": "done",
       "quote": "Shortlist's done, three options in the shared drive."}]}

    create_project   project, title, description, aliases?
    set_status       project, value, from?
    set_field        project, field (title|description|owner|requested_by|due), value, date?
    add_dependency   project, on (an entity, or project:<id>), kind (needs|subject_to|blocked_by)
    add_deliverable  project, key (D1...), title, owner?, due?
    set_deliverable  project, key, status, on?
    set_step         project, n, status and/or due, on?
    add_question     project, key (Q1...), text
    close_question   project, key
    add_decision     project, text
    agree_plan       project, steps              (a discussion's only: plan.py)

`model.validate(records, diff, input_text, names)` returns the problems and
the changes that need your confirmation. It refuses:

- a quote the input does not contain, or one over 300 characters
- a date the input does not state
- a status move outside the table
- a name the graph does not know, or a short one ("Marcus" for Marcus Webb)
- a step, deliverable, question or project that does not exist
- a dependency cycle
- a plan from anything but a discussion

Moving to or from done or cancelled, changing an owner or due date already set,
and replacing an agreed plan all need your confirmation. `model.apply(records,
diff, input_text)` is pure: it returns the new records and the history lines,
and leaves the records it was given alone.

## In the graph

`src/build_graph.py` loads `projects/records/` beside the documents:

- A project and its deliverables are entities.
- Its status history, due date, dependencies, decisions and open questions are
  dated claims.
- Its owner, requester and dependencies are links.
- Its steps, sources and history have tables of their own (`src/schema.sql`).

A record whose quotes are not in its inputs stops the build, as a bad
extraction does. The build reports what needs a look, and so does `BOARD.md`:

- an active project with no update for 14 days
- an overdue step or deliverable
- an input edited since it was read
- a question open for 7 days
- a dependency on a finished project
- a name the graph no longer knows

## The cases

Each is an input, the projects before it, the change set a careful reader
would propose, and the projects after it. They tell one story, in order:

| Case | Input | What should happen |
|---|---|---|
| 01 new project | kickoff meeting, no projects yet | a project created: planning, who asked, two dependencies, three deliverables, questions, no invented date |
| (plan) | the plan discussion, through plan.py | a 5-step plan agreed, an owner, the due date, the move to active |
| 02 progress update | later meeting | step 1 done, D1 delivered, step 2 doing with its due date; off-topic lines change nothing |
| 03 nothing new | brand voice review | nothing |
| 04 second project | typed request | a new project that needs the first, which stays untouched |
| 05 blocked and decided | busy meeting | step done, project blocked, an open question closed with a decision |
| 06 two projects | catch-up meeting | the first project unblocked, steps moved; the second given an owner |
| 07 session entry | the digest's write-up | a step's due date moved, decisions recorded, nothing created |

    python -m unittest tests.test_project_cases tests.test_projects   # no model
    python projects/eval_ingest.py --models sonnet,haiku --reps 3      # the model proposes each case's set
    python bench/project_eval.py --models haiku,sonnet                 # the model answers project questions

`tests/test_project_cases.py` holds each expected set to exactly its stored
result. The ingest eval scores facts, not wording: each case's `expect` names
what must be true afterwards. So a different id, title or quote is not a
failure, but a missed step, a wrong status or an invented project is.

### Adding a case

1. Put the input in `cases/inputs/`.
2. Write `case.json` (what it tests, the input, its kind and date, `expect`).
3. Write `before.json` (often another case's `after.json`).
4. Write `diff.json` (the change set you would propose).
5. Generate `after.json` with `model.apply`, and read it before you commit it.
