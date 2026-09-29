# Ingest eval: change sets proposed from the cases

Run 2026-09-28 01:09. Made by `python projects/eval_ingest.py --models sonnet,haiku --reps 3 --jobs 4`.

**39 of 42 runs passed**: a valid change set whose result meets the case's expectations. 2 needed the repair round (the checks' problems sent back once).

| Case | sonnet | haiku |
| --- | ---: | ---: |
| 01-new-project: A kickoff meeting creates a project | 3 of 3 | 2 of 3 |
| 02-progress-update: A later meeting moves the plan along | 3 of 3 | 2 of 3 |
| 03-nothing-new: A meeting with nothing new changes nothing | 3 of 3 | 3 of 3 |
| 04-second-project: A request creates a second project that waits on the first | 3 of 3 | 2 of 3 |
| 05-blocked-and-decided: A busy meeting: step done, project blocked, question settled | 3 of 3 | 3 of 3 |
| 06-two-projects: One meeting moves two projects | 3 of 3 | 3 of 3 |
| 07-session-entry: A session write-up moves a date and records decisions | 3 of 3 | 3 of 3 |

## Every run

| Case | Model | Rep | Changes (expected) | Repaired | Valid | Expectations | Needs you | Time | Result |
| --- | --- | ---: | ---: | --- | --- | --- | ---: | ---: | --- |
| 01-new-project | sonnet | 1 | 11 (11) | — | yes | all | 0 | 41.7 s | pass |
| 02-progress-update | sonnet | 1 | 3 (3) | — | yes | all | 0 | 8.0 s | pass |
| 03-nothing-new | sonnet | 1 | 0 (0) | — | yes | all | 0 | 5.2 s | pass |
| 04-second-project | sonnet | 1 | 7 (5) | 1 fixed | yes | all | 0 | 31.5 s | pass |
| 05-blocked-and-decided | sonnet | 1 | 4 (5) | — | yes | all | 0 | 15.2 s | pass |
| 06-two-projects | sonnet | 1 | 5 (5) | — | yes | all | 0 | 29.5 s | pass |
| 07-session-entry | sonnet | 1 | 5 (4) | — | yes | all | 0 | 33.3 s | pass |
| 01-new-project | haiku | 1 | 10 (11) | — | yes | 1 missed | 0 | 70.3 s | FAIL |
| 02-progress-update | haiku | 1 | 3 (3) | — | yes | all | 0 | 26.8 s | pass |
| 03-nothing-new | haiku | 1 | 0 (0) | — | yes | all | 0 | 5.9 s | pass |
| 04-second-project | haiku | 1 | 5 (5) | — | yes | all | 0 | 29.7 s | pass |
| 05-blocked-and-decided | haiku | 1 | 5 (5) | — | yes | all | 0 | 19.2 s | pass |
| 06-two-projects | haiku | 1 | 5 (5) | — | yes | all | 0 | 34.4 s | pass |
| 07-session-entry | haiku | 1 | 5 (4) | — | yes | all | 0 | 38.3 s | pass |
| 01-new-project | sonnet | 2 | 11 (11) | — | yes | all | 0 | 34.8 s | pass |
| 02-progress-update | sonnet | 2 | 3 (3) | — | yes | all | 0 | 10.1 s | pass |
| 03-nothing-new | sonnet | 2 | 0 (0) | — | yes | all | 0 | 2.2 s | pass |
| 04-second-project | sonnet | 2 | 7 (5) | — | yes | all | 0 | 19.8 s | pass |
| 05-blocked-and-decided | sonnet | 2 | 4 (5) | — | yes | all | 0 | 16.0 s | pass |
| 06-two-projects | sonnet | 2 | 5 (5) | — | yes | all | 0 | 4.8 s | pass |
| 07-session-entry | sonnet | 2 | 3 (4) | — | yes | all | 0 | 23.9 s | pass |
| 01-new-project | haiku | 2 | 10 (11) | — | yes | all | 0 | 65.1 s | pass |
| 02-progress-update | haiku | 2 | 3 (3) | — | yes | 1 missed | 0 | 7.9 s | FAIL |
| 03-nothing-new | haiku | 2 | 0 (0) | — | yes | all | 0 | 11.8 s | pass |
| 04-second-project | haiku | 2 | 4 (5) | — | yes | 1 missed | 0 | 36.8 s | FAIL |
| 05-blocked-and-decided | haiku | 2 | 5 (5) | — | yes | all | 0 | 14.6 s | pass |
| 06-two-projects | haiku | 2 | 5 (5) | — | yes | all | 0 | 31.3 s | pass |
| 07-session-entry | haiku | 2 | 5 (4) | — | yes | all | 0 | 19.1 s | pass |
| 01-new-project | sonnet | 3 | 12 (11) | — | yes | all | 0 | 58.2 s | pass |
| 02-progress-update | sonnet | 3 | 3 (3) | — | yes | all | 0 | 7.6 s | pass |
| 03-nothing-new | sonnet | 3 | 0 (0) | — | yes | all | 0 | 2.8 s | pass |
| 04-second-project | sonnet | 3 | 5 (5) | 1 fixed | yes | all | 0 | 22.0 s | pass |
| 05-blocked-and-decided | sonnet | 3 | 4 (5) | — | yes | all | 0 | 15.7 s | pass |
| 06-two-projects | sonnet | 3 | 5 (5) | — | yes | all | 0 | 4.4 s | pass |
| 07-session-entry | sonnet | 3 | 5 (4) | — | yes | all | 0 | 31.9 s | pass |
| 01-new-project | haiku | 3 | 10 (11) | — | yes | all | 0 | 59.0 s | pass |
| 02-progress-update | haiku | 3 | 3 (3) | — | yes | all | 0 | 10.7 s | pass |
| 03-nothing-new | haiku | 3 | 0 (0) | — | yes | all | 0 | 10.0 s | pass |
| 04-second-project | haiku | 3 | 5 (5) | — | yes | all | 0 | 22.5 s | pass |
| 05-blocked-and-decided | haiku | 3 | 5 (5) | — | yes | all | 0 | 35.7 s | pass |
| 06-two-projects | haiku | 3 | 4 (5) | — | yes | all | 0 | 19.7 s | pass |
| 07-session-entry | haiku | 3 | 5 (4) | — | yes | all | 0 | 62.2 s | pass |

## What each run proposed

### 01-new-project, sonnet, rep 1: pass

A kickoff meeting creates a project. Creating a project from a transcript: status, who asked, dependencies on things the graph knows, deliverables, and questions for what the meeting left open. No invented dates: 'before the January peak' is a due in words and a question, not a date.

Proposed:

```
+ project      New helpdesk migration (helpdesk-migration)
~ status       helpdesk-migration: planning
~ requested_by helpdesk-migration: Priya Patel
~ due          helpdesk-migration: before the January peak
? question     helpdesk-migration Q1: No specific date set for the January peak deadline
+ deliverable  helpdesk-migration D1 Shortlist of helpdesk options
+ deliverable  helpdesk-migration D2 Migration plan
+ deliverable  helpdesk-migration D3 New helpdesk live with ticket history imported
+ needs        helpdesk-migration → Tooling inventory
+ subject to   helpdesk-migration → Supplier payments
? question     helpdesk-migration Q2: Whether to keep the old helpdesk system read-only after migration
```

Expected:

```
+ project      Helpdesk migration (helpdesk-migration)
~ status       helpdesk-migration: planning, from 2026-09-14
~ requested_by helpdesk-migration: Priya Patel
~ due          helpdesk-migration: before the January peak
+ needs        helpdesk-migration → Tooling inventory
+ subject to   helpdesk-migration → Supplier payments
+ deliverable  helpdesk-migration D1 Shortlist of three helpdesks, Marcus Webb, due 2026-09-23
+ deliverable  helpdesk-migration D2 Migration plan
+ deliverable  helpdesk-migration D3 New helpdesk live with ticket history imported
? question     helpdesk-migration Q1: Does the old helpdesk stay read-only after the move?
? question     helpdesk-migration Q2: What date does the January peak start?
```

### 02-progress-update, sonnet, rep 1: pass

A later meeting moves the plan along. Updating an existing project by its id: a step done, a deliverable delivered, the next step started with the due date said in the meeting. Two lines of the meeting are not about the project (ticket volume, a macro task for this week) and must not become changes or a project.

Proposed:

```
~ deliverable  helpdesk-migration D1: delivered
~ step 1       helpdesk-migration: done
~ step 2       helpdesk-migration: doing, due 2026-10-02
```

Expected:

```
~ step 1       helpdesk-migration: done
~ deliverable  helpdesk-migration D1: delivered
~ step 2       helpdesk-migration: doing, due 2026-10-02
```

### 03-nothing-new, sonnet, rep 1: pass

A meeting with nothing new changes nothing. Restraint: the helpdesk move is mentioned ('on track, nothing new'), and the rest is about the newsletter and tone of voice. The right change set is empty.

Proposed:

```
(nothing to change)
```

Expected:

```
(nothing to change)
```

### 04-second-project, sonnet, rep 1: pass

A request creates a second project that waits on the first. Telling new work from existing work: a request that mentions the helpdesk creates its own project rather than updating the helpdesk one, starts as proposed, and depends on the helpdesk project by id. The helpdesk project must come out unchanged.

The first answer's problems, sent back once:

- change 7 (add_question): missing quote

Proposed:

```
+ project      Refunds dashboard (refunds-dashboard)
~ status       refunds-dashboard: proposed, from 2026-09-25
~ requested_by refunds-dashboard: Sarah Chen
+ deliverable  refunds-dashboard D1 Refunds dashboard with weekly refund totals and approval counts
+ needs        refunds-dashboard → project:helpdesk-migration
~ due          refunds-dashboard: until the new helpdesk is live
? question     refunds-dashboard Q1: No fixed date given for the refunds dashboard beyond waiting for the new helpdesk to go live - when is that expected?
```

Expected:

```
+ project      Refunds dashboard (refunds-dashboard)
~ status       refunds-dashboard: proposed, from 2026-09-25
~ requested_by refunds-dashboard: Sarah Chen
+ needs        refunds-dashboard → project:helpdesk-migration
+ deliverable  refunds-dashboard D1 Dashboard of weekly refund totals and approvals
```

### 05-blocked-and-decided, sonnet, rep 1: pass

A busy meeting: step done, project blocked, question settled. Several kinds of change from one meeting: a step done, the project moving active → blocked (an allowed move that needs no confirmation), and an open question answered, which closes it and records the decision.

Proposed:

```
~ step 2       helpdesk-migration: done
~ status       helpdesk-migration: blocked
✓ answered     helpdesk-migration Q1
+ decision     helpdesk-migration: Keep the old helpdesk read-only for 90 days after go-live, then close it.
```

Expected:

```
~ step 2       helpdesk-migration: done
~ step 3       helpdesk-migration: blocked
~ status       helpdesk-migration: blocked, from 2026-09-26
✓ answered     helpdesk-migration Q1
+ decision     helpdesk-migration: Keep the old helpdesk read-only for 90 days after go-live, then close it
```

### 06-two-projects, sonnet, rep 1: pass

One meeting moves two projects. Updating two projects from one meeting, each by its id: the helpdesk migration unblocked (blocked → active) with step 3 done and step 4 started, and an owner named for the refunds dashboard. Nothing new is created.

Proposed:

```
~ step 3       helpdesk-migration: done
~ status       helpdesk-migration: active
~ step 4       helpdesk-migration: doing
~ owner        refunds-dashboard: Marcus Webb
~ status       refunds-dashboard: planning
```

Expected:

```
~ step 3       helpdesk-migration: done
~ status       helpdesk-migration: active
~ step 4       helpdesk-migration: doing
~ owner        refunds-dashboard: Marcus Webb
~ status       refunds-dashboard: planning
```

### 07-session-entry, sonnet, rep 1: pass

A session write-up moves a date and records decisions. Reading the digest's write-up of a working session (kind session): the go-live date moves step 5's due date to 7 December and the decisions are recorded. A session is not a new project, and the plan's steps are not added to.

Proposed:

```
~ deliverable  helpdesk-migration D2: delivered
~ step 4       helpdesk-migration: done
+ decision     helpdesk-migration: The test import runs on the weekend of 21 November.
+ decision     helpdesk-migration: Go-live is 7 December, well before the January peak.
~ step 5       helpdesk-migration: due 2026-12-07
```

Expected:

```
~ step 5       helpdesk-migration: due 2026-12-07
~ deliverable  helpdesk-migration D2: in_progress
+ decision     helpdesk-migration: The test import runs on the weekend of 21 November
+ decision     helpdesk-migration: Go-live is 7 December
```

### 01-new-project, haiku, rep 1: FAIL

A kickoff meeting creates a project. Creating a project from a transcript: status, who asked, dependencies on things the graph knows, deliverables, and questions for what the meeting left open. No invented dates: 'before the January peak' is a due in words and a question, not a date.

Missed expectations:

- new#1: requested_by is None, expected 'Priya Patel'

Proposed:

```
+ project      Support tooling upgrade (helpdesk-migration)
~ status       helpdesk-migration: planning, from 2026-09-14
~ due          helpdesk-migration: before the January peak
+ subject to   helpdesk-migration → Supplier payments
+ needs        helpdesk-migration → Tooling inventory
+ deliverable  helpdesk-migration D1 Shortlist of three helpdesk options, Marcus Webb, due 2026-09-23
+ deliverable  helpdesk-migration D2 Migration plan
+ deliverable  helpdesk-migration D3 New helpdesk live with ticket history imported
? question     helpdesk-migration Q1: What is the exact date for the new helpdesk deployment before the January peak?
? question     helpdesk-migration Q2: Should the old helpdesk be kept read-only after migration?
```

Expected:

```
+ project      Helpdesk migration (helpdesk-migration)
~ status       helpdesk-migration: planning, from 2026-09-14
~ requested_by helpdesk-migration: Priya Patel
~ due          helpdesk-migration: before the January peak
+ needs        helpdesk-migration → Tooling inventory
+ subject to   helpdesk-migration → Supplier payments
+ deliverable  helpdesk-migration D1 Shortlist of three helpdesks, Marcus Webb, due 2026-09-23
+ deliverable  helpdesk-migration D2 Migration plan
+ deliverable  helpdesk-migration D3 New helpdesk live with ticket history imported
? question     helpdesk-migration Q1: Does the old helpdesk stay read-only after the move?
? question     helpdesk-migration Q2: What date does the January peak start?
```

### 02-progress-update, haiku, rep 1: pass

A later meeting moves the plan along. Updating an existing project by its id: a step done, a deliverable delivered, the next step started with the due date said in the meeting. Two lines of the meeting are not about the project (ticket volume, a macro task for this week) and must not become changes or a project.

Proposed:

```
~ deliverable  helpdesk-migration D1: delivered
~ step 1       helpdesk-migration: done
~ step 2       helpdesk-migration: doing, due 2026-10-02
```

Expected:

```
~ step 1       helpdesk-migration: done
~ deliverable  helpdesk-migration D1: delivered
~ step 2       helpdesk-migration: doing, due 2026-10-02
```

### 03-nothing-new, haiku, rep 1: pass

A meeting with nothing new changes nothing. Restraint: the helpdesk move is mentioned ('on track, nothing new'), and the rest is about the newsletter and tone of voice. The right change set is empty.

Proposed:

```
(nothing to change)
```

Expected:

```
(nothing to change)
```

### 04-second-project, haiku, rep 1: pass

A request creates a second project that waits on the first. Telling new work from existing work: a request that mentions the helpdesk creates its own project rather than updating the helpdesk one, starts as proposed, and depends on the helpdesk project by id. The helpdesk project must come out unchanged.

Proposed:

```
+ project      Refunds dashboard (refunds-dashboard)
~ status       refunds-dashboard: proposed, from 2026-09-25
~ requested_by refunds-dashboard: Sarah Chen
+ needs        refunds-dashboard → project:helpdesk-migration
+ deliverable  refunds-dashboard D1 Monthly refunds dashboard
```

Expected:

```
+ project      Refunds dashboard (refunds-dashboard)
~ status       refunds-dashboard: proposed, from 2026-09-25
~ requested_by refunds-dashboard: Sarah Chen
+ needs        refunds-dashboard → project:helpdesk-migration
+ deliverable  refunds-dashboard D1 Dashboard of weekly refund totals and approvals
```

### 05-blocked-and-decided, haiku, rep 1: pass

A busy meeting: step done, project blocked, question settled. Several kinds of change from one meeting: a step done, the project moving active → blocked (an allowed move that needs no confirmation), and an open question answered, which closes it and records the decision.

Proposed:

```
~ step 2       helpdesk-migration: done
~ status       helpdesk-migration: blocked, from 2026-09-26
~ step 3       helpdesk-migration: due 2026-10-12
✓ answered     helpdesk-migration Q1
+ decision     helpdesk-migration: Old helpdesk stays read-only for 90 days after go-live, then closes
```

Expected:

```
~ step 2       helpdesk-migration: done
~ step 3       helpdesk-migration: blocked
~ status       helpdesk-migration: blocked, from 2026-09-26
✓ answered     helpdesk-migration Q1
+ decision     helpdesk-migration: Keep the old helpdesk read-only for 90 days after go-live, then close it
```

### 06-two-projects, haiku, rep 1: pass

One meeting moves two projects. Updating two projects from one meeting, each by its id: the helpdesk migration unblocked (blocked → active) with step 3 done and step 4 started, and an owner named for the refunds dashboard. Nothing new is created.

Proposed:

```
~ step 3       helpdesk-migration: done
~ status       helpdesk-migration: active
~ step 4       helpdesk-migration: doing
~ owner        refunds-dashboard: Marcus Webb
~ status       refunds-dashboard: planning
```

Expected:

```
~ step 3       helpdesk-migration: done
~ status       helpdesk-migration: active
~ step 4       helpdesk-migration: doing
~ owner        refunds-dashboard: Marcus Webb
~ status       refunds-dashboard: planning
```

### 07-session-entry, haiku, rep 1: pass

A session write-up moves a date and records decisions. Reading the digest's write-up of a working session (kind session): the go-live date moves step 5's due date to 7 December and the decisions are recorded. A session is not a new project, and the plan's steps are not added to.

Proposed:

```
~ step 4       helpdesk-migration: done
~ deliverable  helpdesk-migration D2: delivered
~ step 5       helpdesk-migration: due 2026-12-07
+ decision     helpdesk-migration: The test import runs on the weekend of 21 November
+ decision     helpdesk-migration: Go-live is 7 December, well before the January peak
```

Expected:

```
~ step 5       helpdesk-migration: due 2026-12-07
~ deliverable  helpdesk-migration D2: in_progress
+ decision     helpdesk-migration: The test import runs on the weekend of 21 November
+ decision     helpdesk-migration: Go-live is 7 December
```

### 01-new-project, sonnet, rep 2: pass

A kickoff meeting creates a project. Creating a project from a transcript: status, who asked, dependencies on things the graph knows, deliverables, and questions for what the meeting left open. No invented dates: 'before the January peak' is a due in words and a question, not a date.

Proposed:

```
+ project      Helpdesk migration (helpdesk-migration)
~ status       helpdesk-migration: planning
~ requested_by helpdesk-migration: Priya Patel
~ due          helpdesk-migration: before the January peak
? question     helpdesk-migration Q1: Exact date for the January peak deadline is not specified.
+ deliverable  helpdesk-migration D1 Shortlist of three helpdesk options, Marcus Webb, due 2026-09-23
+ deliverable  helpdesk-migration D2 Migration plan
+ deliverable  helpdesk-migration D3 New helpdesk live with ticket history imported
+ needs        helpdesk-migration → Tooling inventory
+ subject to   helpdesk-migration → Supplier payments
? question     helpdesk-migration Q2: Whether to keep the old helpdesk read-only after migration.
```

Expected:

```
+ project      Helpdesk migration (helpdesk-migration)
~ status       helpdesk-migration: planning, from 2026-09-14
~ requested_by helpdesk-migration: Priya Patel
~ due          helpdesk-migration: before the January peak
+ needs        helpdesk-migration → Tooling inventory
+ subject to   helpdesk-migration → Supplier payments
+ deliverable  helpdesk-migration D1 Shortlist of three helpdesks, Marcus Webb, due 2026-09-23
+ deliverable  helpdesk-migration D2 Migration plan
+ deliverable  helpdesk-migration D3 New helpdesk live with ticket history imported
? question     helpdesk-migration Q1: Does the old helpdesk stay read-only after the move?
? question     helpdesk-migration Q2: What date does the January peak start?
```

### 02-progress-update, sonnet, rep 2: pass

A later meeting moves the plan along. Updating an existing project by its id: a step done, a deliverable delivered, the next step started with the due date said in the meeting. Two lines of the meeting are not about the project (ticket volume, a macro task for this week) and must not become changes or a project.

Proposed:

```
~ deliverable  helpdesk-migration D1: delivered
~ step 1       helpdesk-migration: done
~ step 2       helpdesk-migration: doing, due 2026-10-02
```

Expected:

```
~ step 1       helpdesk-migration: done
~ deliverable  helpdesk-migration D1: delivered
~ step 2       helpdesk-migration: doing, due 2026-10-02
```

### 03-nothing-new, sonnet, rep 2: pass

A meeting with nothing new changes nothing. Restraint: the helpdesk move is mentioned ('on track, nothing new'), and the rest is about the newsletter and tone of voice. The right change set is empty.

Proposed:

```
(nothing to change)
```

Expected:

```
(nothing to change)
```

### 04-second-project, sonnet, rep 2: pass

A request creates a second project that waits on the first. Telling new work from existing work: a request that mentions the helpdesk creates its own project rather than updating the helpdesk one, starts as proposed, and depends on the helpdesk project by id. The helpdesk project must come out unchanged.

Proposed:

```
+ project      Refunds dashboard (refunds-dashboard)
~ status       refunds-dashboard: proposed
~ requested_by refunds-dashboard: Sarah Chen
+ deliverable  refunds-dashboard D1 Refunds dashboard with weekly refund totals and count needing approval
~ due          refunds-dashboard: until the new helpdesk is live
+ needs        refunds-dashboard → project:helpdesk-migration
? question     refunds-dashboard Q1: it can wait until the new helpdesk is live
```

Expected:

```
+ project      Refunds dashboard (refunds-dashboard)
~ status       refunds-dashboard: proposed, from 2026-09-25
~ requested_by refunds-dashboard: Sarah Chen
+ needs        refunds-dashboard → project:helpdesk-migration
+ deliverable  refunds-dashboard D1 Dashboard of weekly refund totals and approvals
```

### 05-blocked-and-decided, sonnet, rep 2: pass

A busy meeting: step done, project blocked, question settled. Several kinds of change from one meeting: a step done, the project moving active → blocked (an allowed move that needs no confirmation), and an open question answered, which closes it and records the decision.

Proposed:

```
~ step 2       helpdesk-migration: done
~ status       helpdesk-migration: blocked, from 2026-09-26
✓ answered     helpdesk-migration Q1
+ decision     helpdesk-migration: Old helpdesk stays read-only for 90 days after go-live, then closed.
```

Expected:

```
~ step 2       helpdesk-migration: done
~ step 3       helpdesk-migration: blocked
~ status       helpdesk-migration: blocked, from 2026-09-26
✓ answered     helpdesk-migration Q1
+ decision     helpdesk-migration: Keep the old helpdesk read-only for 90 days after go-live, then close it
```

### 06-two-projects, sonnet, rep 2: pass

One meeting moves two projects. Updating two projects from one meeting, each by its id: the helpdesk migration unblocked (blocked → active) with step 3 done and step 4 started, and an owner named for the refunds dashboard. Nothing new is created.

Proposed:

```
~ step 3       helpdesk-migration: done
~ status       helpdesk-migration: active
~ step 4       helpdesk-migration: doing
~ owner        refunds-dashboard: Marcus Webb
~ status       refunds-dashboard: planning
```

Expected:

```
~ step 3       helpdesk-migration: done
~ status       helpdesk-migration: active
~ step 4       helpdesk-migration: doing
~ owner        refunds-dashboard: Marcus Webb
~ status       refunds-dashboard: planning
```

### 07-session-entry, sonnet, rep 2: pass

A session write-up moves a date and records decisions. Reading the digest's write-up of a working session (kind session): the go-live date moves step 5's due date to 7 December and the decisions are recorded. A session is not a new project, and the plan's steps are not added to.

Proposed:

```
+ decision     helpdesk-migration: The test import runs on the weekend of 21 November.
+ decision     helpdesk-migration: Go-live is 7 December, well before the January peak.
~ step 5       helpdesk-migration: due 2026-12-07
```

Expected:

```
~ step 5       helpdesk-migration: due 2026-12-07
~ deliverable  helpdesk-migration D2: in_progress
+ decision     helpdesk-migration: The test import runs on the weekend of 21 November
+ decision     helpdesk-migration: Go-live is 7 December
```

### 01-new-project, haiku, rep 2: pass

A kickoff meeting creates a project. Creating a project from a transcript: status, who asked, dependencies on things the graph knows, deliverables, and questions for what the meeting left open. No invented dates: 'before the January peak' is a due in words and a question, not a date.

Proposed:

```
+ project      Helpdesk migration (helpdesk-migration)
~ status       helpdesk-migration: planning
~ requested_by helpdesk-migration: Priya Patel
~ due          helpdesk-migration: before the January peak
+ deliverable  helpdesk-migration D1 Helpdesk shortlist, Marcus Webb, due 2026-09-23
+ deliverable  helpdesk-migration D2 Migration plan
+ deliverable  helpdesk-migration D3 New helpdesk live with ticket history imported
+ subject to   helpdesk-migration → Supplier payments
+ needs        helpdesk-migration → Tooling inventory
? question     helpdesk-migration Q1: Whether to keep the old system read-only afterwards
```

Expected:

```
+ project      Helpdesk migration (helpdesk-migration)
~ status       helpdesk-migration: planning, from 2026-09-14
~ requested_by helpdesk-migration: Priya Patel
~ due          helpdesk-migration: before the January peak
+ needs        helpdesk-migration → Tooling inventory
+ subject to   helpdesk-migration → Supplier payments
+ deliverable  helpdesk-migration D1 Shortlist of three helpdesks, Marcus Webb, due 2026-09-23
+ deliverable  helpdesk-migration D2 Migration plan
+ deliverable  helpdesk-migration D3 New helpdesk live with ticket history imported
? question     helpdesk-migration Q1: Does the old helpdesk stay read-only after the move?
? question     helpdesk-migration Q2: What date does the January peak start?
```

### 02-progress-update, haiku, rep 2: FAIL

A later meeting moves the plan along. Updating an existing project by its id: a step done, a deliverable delivered, the next step started with the due date said in the meeting. Two lines of the meeting are not about the project (ticket volume, a macro task for this week) and must not become changes or a project.

Missed expectations:

- helpdesk-migration: step 2 status is 'todo', expected 'doing'

Proposed:

```
~ deliverable  helpdesk-migration D1: delivered
~ step 1       helpdesk-migration: done
~ step 2       helpdesk-migration: due 2026-10-02
```

Expected:

```
~ step 1       helpdesk-migration: done
~ deliverable  helpdesk-migration D1: delivered
~ step 2       helpdesk-migration: doing, due 2026-10-02
```

### 03-nothing-new, haiku, rep 2: pass

A meeting with nothing new changes nothing. Restraint: the helpdesk move is mentioned ('on track, nothing new'), and the rest is about the newsletter and tone of voice. The right change set is empty.

Proposed:

```
(nothing to change)
```

Expected:

```
(nothing to change)
```

### 04-second-project, haiku, rep 2: FAIL

A request creates a second project that waits on the first. Telling new work from existing work: a request that mentions the helpdesk creates its own project rather than updating the helpdesk one, starts as proposed, and depends on the helpdesk project by id. The helpdesk project must come out unchanged.

Missed expectations:

- new#1: requested_by is None, expected 'Sarah Chen'

Proposed:

```
+ project      Refunds dashboard (refunds-dashboard)
~ status       refunds-dashboard: proposed
+ deliverable  refunds-dashboard D1 Refunds dashboard with weekly totals and approval counts
+ blocked by   refunds-dashboard → project:helpdesk-migration
```

Expected:

```
+ project      Refunds dashboard (refunds-dashboard)
~ status       refunds-dashboard: proposed, from 2026-09-25
~ requested_by refunds-dashboard: Sarah Chen
+ needs        refunds-dashboard → project:helpdesk-migration
+ deliverable  refunds-dashboard D1 Dashboard of weekly refund totals and approvals
```

### 05-blocked-and-decided, haiku, rep 2: pass

A busy meeting: step done, project blocked, question settled. Several kinds of change from one meeting: a step done, the project moving active → blocked (an allowed move that needs no confirmation), and an open question answered, which closes it and records the decision.

Proposed:

```
~ step 2       helpdesk-migration: done
~ status       helpdesk-migration: blocked
~ step 3       helpdesk-migration: due 2026-10-12
✓ answered     helpdesk-migration Q1
+ decision     helpdesk-migration: Keep the old helpdesk read-only for 90 days after go-live, then close it.
```

Expected:

```
~ step 2       helpdesk-migration: done
~ step 3       helpdesk-migration: blocked
~ status       helpdesk-migration: blocked, from 2026-09-26
✓ answered     helpdesk-migration Q1
+ decision     helpdesk-migration: Keep the old helpdesk read-only for 90 days after go-live, then close it
```

### 06-two-projects, haiku, rep 2: pass

One meeting moves two projects. Updating two projects from one meeting, each by its id: the helpdesk migration unblocked (blocked → active) with step 3 done and step 4 started, and an owner named for the refunds dashboard. Nothing new is created.

Proposed:

```
~ status       helpdesk-migration: active
~ step 3       helpdesk-migration: done
~ step 4       helpdesk-migration: doing
~ status       refunds-dashboard: planning
~ owner        refunds-dashboard: Marcus Webb
```

Expected:

```
~ step 3       helpdesk-migration: done
~ status       helpdesk-migration: active
~ step 4       helpdesk-migration: doing
~ owner        refunds-dashboard: Marcus Webb
~ status       refunds-dashboard: planning
```

### 07-session-entry, haiku, rep 2: pass

A session write-up moves a date and records decisions. Reading the digest's write-up of a working session (kind session): the go-live date moves step 5's due date to 7 December and the decisions are recorded. A session is not a new project, and the plan's steps are not added to.

Proposed:

```
~ step 4       helpdesk-migration: done
~ deliverable  helpdesk-migration D2: delivered
~ step 5       helpdesk-migration: due 2026-12-07
+ decision     helpdesk-migration: The test import runs on the weekend of 21 November.
+ decision     helpdesk-migration: Go-live is 7 December, well before the January peak.
```

Expected:

```
~ step 5       helpdesk-migration: due 2026-12-07
~ deliverable  helpdesk-migration D2: in_progress
+ decision     helpdesk-migration: The test import runs on the weekend of 21 November
+ decision     helpdesk-migration: Go-live is 7 December
```

### 01-new-project, sonnet, rep 3: pass

A kickoff meeting creates a project. Creating a project from a transcript: status, who asked, dependencies on things the graph knows, deliverables, and questions for what the meeting left open. No invented dates: 'before the January peak' is a due in words and a question, not a date.

Proposed:

```
+ project      Helpdesk migration (helpdesk-migration)
~ status       helpdesk-migration: planning
~ requested_by helpdesk-migration: Priya Patel
~ due          helpdesk-migration: before the January peak
+ needs        helpdesk-migration → Tooling inventory
+ subject to   helpdesk-migration → Supplier payments
+ deliverable  helpdesk-migration D1 Shortlist of three helpdesk options, Marcus Webb, due 2026-09-23
+ deliverable  helpdesk-migration D2 Migration plan
+ deliverable  helpdesk-migration D3 New helpdesk live with ticket history imported
? question     helpdesk-migration Q1: What is the exact date for the January peak deadline?
? question     helpdesk-migration Q2: Should the old helpdesk be kept read-only after migration?
+ decision     helpdesk-migration: Move to a new helpdesk before the January peak, with a shortlist due 23 September.
```

Expected:

```
+ project      Helpdesk migration (helpdesk-migration)
~ status       helpdesk-migration: planning, from 2026-09-14
~ requested_by helpdesk-migration: Priya Patel
~ due          helpdesk-migration: before the January peak
+ needs        helpdesk-migration → Tooling inventory
+ subject to   helpdesk-migration → Supplier payments
+ deliverable  helpdesk-migration D1 Shortlist of three helpdesks, Marcus Webb, due 2026-09-23
+ deliverable  helpdesk-migration D2 Migration plan
+ deliverable  helpdesk-migration D3 New helpdesk live with ticket history imported
? question     helpdesk-migration Q1: Does the old helpdesk stay read-only after the move?
? question     helpdesk-migration Q2: What date does the January peak start?
```

### 02-progress-update, sonnet, rep 3: pass

A later meeting moves the plan along. Updating an existing project by its id: a step done, a deliverable delivered, the next step started with the due date said in the meeting. Two lines of the meeting are not about the project (ticket volume, a macro task for this week) and must not become changes or a project.

Proposed:

```
~ deliverable  helpdesk-migration D1: delivered
~ step 1       helpdesk-migration: done
~ step 2       helpdesk-migration: doing, due 2026-10-02
```

Expected:

```
~ step 1       helpdesk-migration: done
~ deliverable  helpdesk-migration D1: delivered
~ step 2       helpdesk-migration: doing, due 2026-10-02
```

### 03-nothing-new, sonnet, rep 3: pass

A meeting with nothing new changes nothing. Restraint: the helpdesk move is mentioned ('on track, nothing new'), and the rest is about the newsletter and tone of voice. The right change set is empty.

Proposed:

```
(nothing to change)
```

Expected:

```
(nothing to change)
```

### 04-second-project, sonnet, rep 3: pass

A request creates a second project that waits on the first. Telling new work from existing work: a request that mentions the helpdesk creates its own project rather than updating the helpdesk one, starts as proposed, and depends on the helpdesk project by id. The helpdesk project must come out unchanged.

The first answer's problems, sent back once:

- change 4 (add_deliverable): missing quote

Proposed:

```
+ project      Refunds dashboard (refunds-dashboard)
~ status       refunds-dashboard: proposed
~ requested_by refunds-dashboard: Sarah Chen
+ deliverable  refunds-dashboard D1 Dashboard showing weekly refund totals and how many needed approval
+ needs        refunds-dashboard → project:helpdesk-migration
```

Expected:

```
+ project      Refunds dashboard (refunds-dashboard)
~ status       refunds-dashboard: proposed, from 2026-09-25
~ requested_by refunds-dashboard: Sarah Chen
+ needs        refunds-dashboard → project:helpdesk-migration
+ deliverable  refunds-dashboard D1 Dashboard of weekly refund totals and approvals
```

### 05-blocked-and-decided, sonnet, rep 3: pass

A busy meeting: step done, project blocked, question settled. Several kinds of change from one meeting: a step done, the project moving active → blocked (an allowed move that needs no confirmation), and an open question answered, which closes it and records the decision.

Proposed:

```
~ step 2       helpdesk-migration: done
~ status       helpdesk-migration: blocked
✓ answered     helpdesk-migration Q1
+ decision     helpdesk-migration: Keep the old helpdesk read-only for 90 days after go-live, then close it.
```

Expected:

```
~ step 2       helpdesk-migration: done
~ step 3       helpdesk-migration: blocked
~ status       helpdesk-migration: blocked, from 2026-09-26
✓ answered     helpdesk-migration Q1
+ decision     helpdesk-migration: Keep the old helpdesk read-only for 90 days after go-live, then close it
```

### 06-two-projects, sonnet, rep 3: pass

One meeting moves two projects. Updating two projects from one meeting, each by its id: the helpdesk migration unblocked (blocked → active) with step 3 done and step 4 started, and an owner named for the refunds dashboard. Nothing new is created.

Proposed:

```
~ step 3       helpdesk-migration: done
~ status       helpdesk-migration: active
~ step 4       helpdesk-migration: doing
~ owner        refunds-dashboard: Marcus Webb
~ status       refunds-dashboard: planning
```

Expected:

```
~ step 3       helpdesk-migration: done
~ status       helpdesk-migration: active
~ step 4       helpdesk-migration: doing
~ owner        refunds-dashboard: Marcus Webb
~ status       refunds-dashboard: planning
```

### 07-session-entry, sonnet, rep 3: pass

A session write-up moves a date and records decisions. Reading the digest's write-up of a working session (kind session): the go-live date moves step 5's due date to 7 December and the decisions are recorded. A session is not a new project, and the plan's steps are not added to.

Proposed:

```
~ deliverable  helpdesk-migration D2: delivered
~ step 4       helpdesk-migration: done
~ step 5       helpdesk-migration: due 2026-12-07
+ decision     helpdesk-migration: The test import runs on the weekend of 21 November.
+ decision     helpdesk-migration: Go-live is 7 December, well before the January peak.
```

Expected:

```
~ step 5       helpdesk-migration: due 2026-12-07
~ deliverable  helpdesk-migration D2: in_progress
+ decision     helpdesk-migration: The test import runs on the weekend of 21 November
+ decision     helpdesk-migration: Go-live is 7 December
```

### 01-new-project, haiku, rep 3: pass

A kickoff meeting creates a project. Creating a project from a transcript: status, who asked, dependencies on things the graph knows, deliverables, and questions for what the meeting left open. No invented dates: 'before the January peak' is a due in words and a question, not a date.

Proposed:

```
+ project      Helpdesk system migration (helpdesk-migration)
~ status       helpdesk-migration: planning
~ requested_by helpdesk-migration: Priya Patel
~ due          helpdesk-migration: before the January peak
+ deliverable  helpdesk-migration D1 Helpdesk options shortlist, Marcus Webb, due 2026-09-23
+ deliverable  helpdesk-migration D2 Migration plan
+ deliverable  helpdesk-migration D3 New helpdesk live with ticket history imported
+ subject to   helpdesk-migration → Supplier payments
+ needs        helpdesk-migration → Tooling inventory
? question     helpdesk-migration Q1: Whether to keep the old system read-only afterwards
```

Expected:

```
+ project      Helpdesk migration (helpdesk-migration)
~ status       helpdesk-migration: planning, from 2026-09-14
~ requested_by helpdesk-migration: Priya Patel
~ due          helpdesk-migration: before the January peak
+ needs        helpdesk-migration → Tooling inventory
+ subject to   helpdesk-migration → Supplier payments
+ deliverable  helpdesk-migration D1 Shortlist of three helpdesks, Marcus Webb, due 2026-09-23
+ deliverable  helpdesk-migration D2 Migration plan
+ deliverable  helpdesk-migration D3 New helpdesk live with ticket history imported
? question     helpdesk-migration Q1: Does the old helpdesk stay read-only after the move?
? question     helpdesk-migration Q2: What date does the January peak start?
```

### 02-progress-update, haiku, rep 3: pass

A later meeting moves the plan along. Updating an existing project by its id: a step done, a deliverable delivered, the next step started with the due date said in the meeting. Two lines of the meeting are not about the project (ticket volume, a macro task for this week) and must not become changes or a project.

Proposed:

```
~ deliverable  helpdesk-migration D1: delivered
~ step 1       helpdesk-migration: done
~ step 2       helpdesk-migration: doing, due 2026-10-02
```

Expected:

```
~ step 1       helpdesk-migration: done
~ deliverable  helpdesk-migration D1: delivered
~ step 2       helpdesk-migration: doing, due 2026-10-02
```

### 03-nothing-new, haiku, rep 3: pass

A meeting with nothing new changes nothing. Restraint: the helpdesk move is mentioned ('on track, nothing new'), and the rest is about the newsletter and tone of voice. The right change set is empty.

Proposed:

```
(nothing to change)
```

Expected:

```
(nothing to change)
```

### 04-second-project, haiku, rep 3: pass

A request creates a second project that waits on the first. Telling new work from existing work: a request that mentions the helpdesk creates its own project rather than updating the helpdesk one, starts as proposed, and depends on the helpdesk project by id. The helpdesk project must come out unchanged.

Proposed:

```
+ project      Refunds dashboard (refunds-dashboard)
~ status       refunds-dashboard: proposed
~ requested_by refunds-dashboard: Sarah Chen
+ blocked by   refunds-dashboard → project:helpdesk-migration
+ deliverable  refunds-dashboard D1 Refunds dashboard with weekly totals and approval counts
```

Expected:

```
+ project      Refunds dashboard (refunds-dashboard)
~ status       refunds-dashboard: proposed, from 2026-09-25
~ requested_by refunds-dashboard: Sarah Chen
+ needs        refunds-dashboard → project:helpdesk-migration
+ deliverable  refunds-dashboard D1 Dashboard of weekly refund totals and approvals
```

### 05-blocked-and-decided, haiku, rep 3: pass

A busy meeting: step done, project blocked, question settled. Several kinds of change from one meeting: a step done, the project moving active → blocked (an allowed move that needs no confirmation), and an open question answered, which closes it and records the decision.

Proposed:

```
~ step 2       helpdesk-migration: done
~ status       helpdesk-migration: blocked
~ step 3       helpdesk-migration: due 2026-10-12
✓ answered     helpdesk-migration Q1
+ decision     helpdesk-migration: Keep the old helpdesk read-only for 90 days after go-live, then close it.
```

Expected:

```
~ step 2       helpdesk-migration: done
~ step 3       helpdesk-migration: blocked
~ status       helpdesk-migration: blocked, from 2026-09-26
✓ answered     helpdesk-migration Q1
+ decision     helpdesk-migration: Keep the old helpdesk read-only for 90 days after go-live, then close it
```

### 06-two-projects, haiku, rep 3: pass

One meeting moves two projects. Updating two projects from one meeting, each by its id: the helpdesk migration unblocked (blocked → active) with step 3 done and step 4 started, and an owner named for the refunds dashboard. Nothing new is created.

Proposed:

```
~ step 3       helpdesk-migration: done
~ step 4       helpdesk-migration: doing
~ status       helpdesk-migration: active, from 2026-09-27
~ owner        refunds-dashboard: Marcus Webb (2026-09-27)
```

Expected:

```
~ step 3       helpdesk-migration: done
~ status       helpdesk-migration: active
~ step 4       helpdesk-migration: doing
~ owner        refunds-dashboard: Marcus Webb
~ status       refunds-dashboard: planning
```

### 07-session-entry, haiku, rep 3: pass

A session write-up moves a date and records decisions. Reading the digest's write-up of a working session (kind session): the go-live date moves step 5's due date to 7 December and the decisions are recorded. A session is not a new project, and the plan's steps are not added to.

Proposed:

```
~ step 4       helpdesk-migration: done
~ deliverable  helpdesk-migration D2: delivered
~ step 5       helpdesk-migration: due 2026-12-07
+ decision     helpdesk-migration: The test import runs on the weekend of 21 November
+ decision     helpdesk-migration: Go-live is 7 December, well before the January peak
```

Expected:

```
~ step 5       helpdesk-migration: due 2026-12-07
~ deliverable  helpdesk-migration D2: in_progress
+ decision     helpdesk-migration: The test import runs on the weekend of 21 November
+ decision     helpdesk-migration: Go-live is 7 December
```
