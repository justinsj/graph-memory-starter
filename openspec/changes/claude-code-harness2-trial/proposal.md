# Proposal

## Why

The agent asks many questions that end in its recommended answer, and its recommendation is often not the answer the user wants. In one user's transcripts from 2026-08-28 to 2026-10-23, the user answered 92 questions that had a recommended option, across 38 sessions: 56 times with the recommended option and 36 times with a different one. A harness change can make the agent settle questions from a preferences file (a `CLAUDE.md` rule, the `question-format` skill and a new preference), but nothing measures whether such a change helps, or improves it with evidence.

Harness² (Xu et al., "Harness²: Recursive Agent Harnessing for an Open World", arXiv 2610.14224, code at `github.com/google-research/harness2`) improves an agent's harness from contrastive runs of one task (Propose, Probe, Compose) and keeps reusable lessons in a library. A review of the paper (2026-10-21) recommends it only offline, at k=1, on a chosen sample, in a sandbox, with a person approving each new harness and each new lesson. Question handling is a good first trial because, unlike the paper's benchmarks, the right answer is known: it is the option the user actually chose.

## What Changes

- Install upstream Harness² at a pinned commit in its own Python 3.12 environment, and run its core loop on Windows: task-level Propose, Probe, Compose and selection, and harness-level reflection and library.
- Add `harness2cc/`, a plug-in that makes Claude Code the agent being improved: a Claude Code executor (headless `claude -p` in a sandbox), and a task source that replays past decision points from Claude Code transcripts.
- Add a command line, `harness2cc`, where the user picks everything: which past decision points to use as reference runs, the k value, the mode (parallel or sequential), the models and a cost cap. There is no option to run over every task.
- Add two human approval gates. Gate 1 (task level): a composed harness changes the live harness files only after `approve-harness`. Gate 2 (harness level): a lesson enters the library only after `approve-lesson`.
- Apply the review's recommendations: sandboxed runs with frozen inputs and no live tools; guardrail files read-only; the user's real answers hidden from the editor and used only for grading (a fast set at every gate, the full held-out set on request); a cap on library size and on `CLAUDE.md` growth; scans for client names, hostnames, secrets and injected instructions; a record of every run, its cost and every approval.
- Keep every user-specific file outside this public repository: the configuration (workspace path, editable files, protected sections, client names), the transcripts, the runs, the library and the ledger live under `~/.claude/harness2cc/`.
- First trial: compare the harness before the question-handling edits with the current one on the fast set, then run one k=1 loop on decision points the user picks, and report its cost in dollars.

## Deliverable and mockup

The user gets the `harness2cc` command: it lists past decision points, runs one Harness² loop on the ones the user picks, grades the result against the user's real answers, and waits for the user's approval before any harness file or library entry changes.

Where to see it: the source is `harness2cc/` in this repository, installed to `~/.claude/harness2cc/` (Windows, Python 3.12 environment). Each run writes its records to `~/.claude/harness2cc/runs/<run-id>/`.

Mockup (Example values):

```text
> harness2cc list-references --mismatch-only --since 2026-10-01
ID       DATE        PROJECT        SHORT NAME      RECOMMENDED           YOU CHOSE
dp-0433  2026-10-13  billing-etl    Cache lifetime  1 hour                Keep 1 day
dp-0412  2026-10-15  billing-etl    Retry limit     Raise it to 5         Keep 3
dp-0417  2026-10-15  shop-api       Backfill scope  Exclude closed        Include them as-is
3 of 12 decision points shown

> harness2cc run --reference dp-0433 --k 1 --mode parallel --budget-usd 25 --dry-run
Plan for run h2-20261024-0930 (dry run, no model calls)
  references  dp-0433 (Cache lifetime)
  k / mode    1 / parallel
  executor    opus, claude -p in a sandbox (Read, Glob, Grep only; no MCP servers; no user hooks)
  editor      opus, effort high
  fast set    dp-0388, dp-0391, dp-0402, dp-0405, dp-0420 (5 most recent not used as references)
  calls       4 executor runs, 4 editor sessions, 10 fast-set runs, 10 grader calls
  estimate    $6 to $14 (the run stops with status BUDGET_REACHED at $25)

> harness2cc run --reference dp-0433 --k 1 --mode parallel --budget-usd 25
[1/4] reference run ........... done  $0.41
[2/4] propose general + domain  done  $2.10
[3/4] probe 2 candidates ...... done  $0.88
[4/4] compose and run ......... done  $1.62
Fast set (5 decision points, 6 questions; your answers were hidden from the editor)
                               current harness   composed harness
  asked you                    4 of 6            2 of 6
  matched your answer          3 of 6            5 of 6
  settled a Needs-your-yes     0                 0
Diff: runs/h2-20261024-0930/pending/harness.diff (+14 / -2 lines; CLAUDE.md grows 610 characters)
Gate 1 waiting: harness2cc approve-harness h2-20261024-0930   or   harness2cc reject-harness h2-20261024-0930
Lesson staged: library/pending/questions/dp-0433/EXPERIENCE.md
Gate 2 waiting: harness2cc approve-lesson questions/dp-0433   or   harness2cc reject-lesson questions/dp-0433
Cost: $5.01 of $25
```

Failure output (Example values):

```text
> harness2cc run --k 1
error: no --reference given. Pick decision points with `harness2cc list-references`; a run never covers every task.
(exit code 2)

> harness2cc approve-lesson questions/dp-0433
error: approval blocked by 1 scan finding in library/pending/questions/dp-0433/EXPERIENCE.md
  line 12: client name "Acme Widgets" (from client_terms.txt). Remove it or state the lesson without it, then approve again.
(exit code 3)
```

## Capabilities

### New Capabilities

- `harness-improvement`: offline trials that improve the Claude Code harness: replaying decision points the user picks, proposing and probing harness edits in a sandbox, grading them against the user's real answers, and changing harness files or the lesson library only after the user approves.

### Modified Capabilities

None.

## Impact

- New in this repository: `harness2cc/` (Python package, `README.md`, an example configuration with placeholder values), `tests/test_harness2cc.py` with a fake `claude` executable, so the tests make no model calls.
- Changed: `tests/test_kl_specs.py` also reads `tests/test_harness2cc.py`, so the new capability's scenarios are checked against their tests after archive.
- Installed outside the repository: `uv` (user-level), Python 3.12 (through `uv`), upstream `harness2` at commit `1cfe254e` (Apache-2.0, no runtime dependencies), and `~/.claude/harness2cc/` with its configuration, runs, library and ledger.
- Live files the approval gates can change: the files the configuration lists as editable (in the first trial: the workspace `CLAUDE.md`, `preferences.md`, the `question-format` and `response-format` skills, and new skills), plus their source copies in this repository and the install guide.
- Cost: model calls through the user's Claude Code login, only on runs the user starts, each capped by `--budget-usd`.

## Follow-ups

- Consolidating near-duplicate library entries, and retrieval by meaning instead of reading the index.
- One library per client, if lessons ever need client-specific content (this change blocks client names instead).
- Replays that include a frozen snapshot of the repository the session was working in, for decisions that depend on reading code.
- An install guide part for `harness2cc`, once the trial shows it is worth installing elsewhere.
