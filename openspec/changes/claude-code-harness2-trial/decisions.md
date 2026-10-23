# Decisions: claude-code-harness2-trial

Status: accepted on 2026-10-23, when apply started
Written by the propose workflow on 2026-10-23. Each decision answers a question the workflow would otherwise have asked.

## Preferences used

- P1 Workaround instead of full refactor: settled D4 (Windows core only) and D7 (Decision-point replay).
- P3 Reuse what exists: settled D1 (Change home), D3 (Upstream install) and D17 (Test approach).
- P4 Fail loudly: settled D15 (Approval scans).
- P5 Read-only data access: settled D6 (Session sandbox).
- P6 Tests for happy, edge and error paths: settled D17 (Test approach).
- P7 Defer extras to follow-ups: settled D18 (Documentation home).
- P10 One shippable change per PR: settled D18 (Documentation home) and D20 (Delivery in three PRs).

## Decisions

### D1. Change home

- Decision: The change lives in this repository as a new `harness2cc/` folder, installed to `~/.claude/harness2cc/`, the same way the run guard is shipped from `runguard/` and installed to `~/.claude/runguard/`.
- Question: Where should the Harness² plug-in for Claude Code and its OpenSpec change live: in this repository (graph-memory-starter, which already ships the run guard, the session merge tool, the review loop and the OpenSpec rules as sources), or in a new repository?
- Reason: This repository already holds the user's Claude Code harness tooling and has an OpenSpec root; a new repository would need `openspec init`, which the workspace rules leave to the user.
- Source: project: `runguard/`, `sessionmerge/`, `openspec-rules/` and `openspec/` in this repository
- Not chosen: A new repository, which would need its own OpenSpec setup and would split the harness tooling across two places.
- Affects: proposal.md (What Changes, Impact), design.md (Decision 9), tasks 1.2 (create the environment) and 2.1 (create the package)
- Needs your yes: no

### D2. Public repository data

- Decision: Every user-specific file (configuration, client names, labels, runs, library, backups, ledger) lives under `~/.claude/harness2cc/`; the repository gets code, tests and an example configuration with placeholder values only, and the change's own documents use example values.
- Question: This repository is public on GitHub; what may the Harness² plug-in and its OpenSpec documents hold?
- Reason: The repository has no company data today, and transcripts, client names and database hostnames must not reach a public repository.
- Source: project: `gh repo view` reports the repository as PUBLIC, and a search of tracked files finds no company names
- Not chosen: Keeping the configuration and client list in the repository, which would publish client names and workspace paths.
- Affects: proposal.md (What Changes, Impact), spec requirement "User-specific data stays outside the repository", design.md (Decision 8), tasks 2.1 (package and configuration) and 11.1 (real configuration)
- Needs your yes: no

### D3. Upstream install

- Decision: Upstream `harness2` is installed from git at commit `1cfe254e` into its own Python 3.12 environment made with `uv`, and `harness2cc patch-upstream` then changes two lines of the installed `core/tree.py` (lines 140 and 167, `str(p.relative_to(...))` to `p.relative_to(...).as_posix()`); the plug-in imports the patched package.
- Question: Should the plug-in install upstream Harness² as a pinned package, or copy (fork) its code into this repository; and, once upstream turned out to build backslash paths on Windows, how should that be fixed?
- Reason: The plug-in needs only upstream's core loop through its published protocols, and a pinned commit keeps the paper's code exact. On Windows those two lines make every valid edit look off the editable surface, so the loop never changes a harness; with the two-line change all 5 upstream tests pass on Windows.
- Source: your answer on 2026-10-23
- Not chosen: Running everything in WSL Ubuntu, which needs a second Claude Code install and login there; or a fork on GitHub, which drifts from upstream.
- Affects: design.md (Context, Decision 9), tasks 1.2 (install upstream) and 2.3 (the patch step)
- Needs your yes: no

### D4. Windows core only

- Decision: Upstream runs on Windows, using only its core modules (`recursion`, `selection`, `library`, `proposer`, `context`) and never `core/schedule.py`.
- Question: Upstream declares POSIX only; should the plug-in run it on Windows or inside WSL (Ubuntu 22.04, currently stopped)?
- Reason: The only POSIX-only call in the core is `fcntl` in `schedule.py`, which drives the sweep over a whole benchmark that this change does not want; Claude Code is logged in on Windows, not in WSL.
- Source: P1 Workaround instead of full refactor
- Not chosen: WSL, which needs a second Claude Code install and login inside Ubuntu, and copying files across the two file systems.
- Affects: design.md (Context, Decision 1), task 1.3 (check upstream on Windows)
- Needs your yes: no

### D5. Claude Code as executor

- Decision: The plug-in adds a Claude Code substrate (headless `claude -p`) as the executor, and replaces the command builder of upstream's `claude_cli` editor channel.
- Question: Upstream's executors are OpenCode and Codex; which agent should the trial run as the executor?
- Reason: The harness being improved is Claude Code's (`CLAUDE.md`, skills, preferences), so it has to run inside Claude Code to be measured.
- Source: request
- Not chosen: Upstream's OpenCode executor, which would measure a different agent with a different harness.
- Affects: design.md (Decisions 2 and 3), tasks 4.2 (substrate and adapter) and 4.3 (editor command)
- Needs your yes: no

### D6. Session sandbox

- Decision: Every executor, editor and grader session runs in a fresh folder with an empty MCP configuration in strict mode, project settings only, read-only file tools (the editor may also write inside its own folder), and no cloud, database or source-control variables in its environment; upstream's `--dangerously-skip-permissions` is never used.
- Question: How should model sessions that read past transcripts and rerun a task 4 to 20 times be isolated from live systems?
- Reason: The review of the paper found that probing repeats every side effect and that injected text in inputs can be saved; the workspace allows only read-only data access.
- Source: P5 Read-only data access
- Not chosen: Upstream's editor command as it is, which gives an agent that reads untrusted transcript text full permissions and the user's cloud credentials.
- Affects: spec requirement "Runs execute in a sandbox without live tools", design.md (Decision 3), tasks 4.1 (sandbox builder), 4.3 (editor command) and 4.4 (live sandbox check)
- Needs your yes: no

### D7. Decision-point replay

- Decision: A task is a replay of one past decision point: the user's messages up to that turn, the assistant's text replies (each cut to 4,000 characters) and the tool calls by name and path, ending with a fixed instruction to write the next response without doing the work.
- Question: How should a past session be rerun under a candidate harness: resume the real session, or replay a digest of it?
- Reason: A resumed session keeps the old `CLAUDE.md` text already in its transcript, so a candidate harness would not take effect; the digest needs no repository or live tools.
- Source: P1 Workaround instead of full refactor
- Not chosen: `claude --resume --fork-session`, which would grade the old harness under a new label.
- Affects: spec requirement "Decision points come from the user's transcripts", design.md (Decision 4), tasks 3.1 (scan) and 3.2 (replay)
- Needs your yes: no

### D8. Editable surface

- Decision: Only files the configuration lists can change (first trial: the workspace `CLAUDE.md`, `preferences.md`, the `question-format` and `response-format` skills, and new skills); the configuration's protected `CLAUDE.md` sections (first trial: the database access rules and the review loop rule), the OpenSpec `rules.md`, settings, hooks, scripts, plugins, subagents and memory files are read-only.
- Question: Which parts of the Claude Code harness may Harness² edit, given that the paper edits all eight components, guardrails included?
- Reason: The review of the paper recommends read-only guardrails, with policy changes going to a person.
- Source: request (the review's recommendations)
- Not chosen: All eight components editable as in the paper, which would let a composed harness rewrite its own guardrails.
- Affects: spec requirement "Guardrail files stay read-only", design.md (Decisions 2 and 8), task 5.1 (`validate_tree`)
- Needs your yes: no

### D9. Labels hidden from the editor

- Decision: The user's real answers are read only by the grader; a replay ends with the user message that started the asking turn, so neither the turn that asked (with its recommended option) nor the user's reply is in it, and grades are written outside every editor workspace.
- Question: Should the editor see the answer the user gave at a reference decision point?
- Reason: An editor that sees the answer writes a rule for exactly that answer, and the held-out grade would no longer measure anything; upstream already refuses grader verdicts in harness trees and library entries.
- Source: project: upstream `core/context.py` (`assert_tree_has_no_grader_verdicts`) and `core/spec.py` (`BenchPrompts` checks)
- Not chosen: Showing the answer to the editor, which would make the run fit its own references.
- Affects: spec requirement "The user's answers are hidden from the editor", design.md (Decisions 4 and 5), tasks 3.2 (replay) and 6.2 (orchestration)
- Needs your yes: no

### D10. Approval gates

- Decision: Two gates: `approve-harness` before a composed harness changes any live file (task level), and `approve-lesson` before a lesson enters the library (harness level); candidate runs inside the sandbox need no approval.
- Question: Where should a person approve: before each probe run, before a harness is adopted, before a lesson is saved, or at all three?
- Reason: The request names approval at the task level and the harness level; probe runs have no live side effects inside the sandbox, so a third gate would only add interruptions.
- Source: request
- Not chosen: A third gate before each probe, which would stop the loop four times per reference at k=1.
- Affects: spec requirements "A new harness changes live files only after approval" and "A lesson enters the library only after approval", design.md (Decision 6), tasks 8.1 to 9.1
- Needs your yes: no

### D11. Manual run selection

- Decision: `run` requires one to five `--reference` decision points, takes `--k` from 1 to 5 (default 1) and `--mode parallel` or `sequential` (default parallel), and has no option that covers every task.
- Question: How does the user choose what a run covers, and what are the defaults and limits?
- Reason: The request asks for manual choice of the reference run and the k value, and the review recommends k=1 on a chosen sample, not every task.
- Source: request
- Not chosen: Upstream's sweep command, which runs every task of a benchmark.
- Affects: spec requirement "Runs start only from decision points the user names", task 6.1 (argument checks)
- Needs your yes: no

### D12. Grading sets

- Decision: Gate 1 grades the current and the composed harness on a fast set (default: the 5 most recent decision points not used as references, overridable with `--fast-set`); the full held-out set runs only on `test --full`; `test --harness <folder>` grades a saved snapshot.
- Question: How many labelled decision points should each run grade, given that each graded point costs two executor runs and two grader calls?
- Reason: The review recommends a small fast set on every change and the full held-out set once per batch.
- Source: request (the review's recommendations)
- Not chosen: Grading all 92 points on every run, which would cost about 180 executor runs per gate.
- Affects: spec requirement "Each candidate is graded against the user's real answers", design.md (Decision 5), tasks 7.1 and 7.2 (grader and test command)
- Needs your yes: no

### D13. Models

- Decision: The executor and the editor default to `opus` (the editor at high effort) and the grader to `sonnet`; each is a flag.
- Question: Which models should the executor, the editor and the grader use?
- Reason: The live harness runs on `opus` (`"model": "opus"` in the user settings), so probes measure the same model; the paper's editor is an Opus model at high effort; grading is a short mapping task.
- Source: project: `~/.claude/settings.json`
- Not chosen: `sonnet` as executor, which costs less but would measure another model's question behavior.
- Affects: design.md (Decisions 2 and 5), task 6.1 (model flags)
- Needs your yes: no

### D14. Library and growth caps

- Decision: A library domain holds at most 20 approved lessons (`library prune <entry>` frees space), and one approved harness may add at most 2,000 characters to `CLAUDE.md`.
- Question: How should the library and the always-loaded files be kept from growing without limit?
- Reason: The review of the paper found no size limit across tasks; `CLAUDE.md` is loaded into every session, so its growth costs every future session.
- Source: request (the review's recommendations)
- Not chosen: No caps, as in the paper, where libraries held 25 to 100 tasks per domain.
- Affects: spec scenarios "A full library refuses a new lesson" and "An approved harness that grows CLAUDE.md past the cap is refused", tasks 8.3 and 9.1
- Needs your yes: no

### D15. Approval scans

- Decision: Every approval scans added lines for secrets and injected instructions; files with a source copy in this public repository, and every lesson, are also scanned for client names from `client_terms.txt` and for database hostnames; a finding blocks the approval and names the file, line and finding.
- Question: What should block an approval, and should a finding warn or block?
- Reason: The review of the paper names injected instructions and client data in lessons as risks, and the workspace rules require errors to stop the work rather than show as warnings.
- Source: P4 Fail loudly
- Not chosen: Warnings that let the approval go ahead.
- Affects: spec scenarios "A harness diff with a scan finding is refused" and "A lesson with a scan finding cannot be approved", design.md (Decision 7), task 8.2 (scans)
- Needs your yes: no

### D16. Source sync on approval

- Decision: `approve-harness` also writes each changed file's source copy in this repository and its embedded copy in the install guide, then runs `tests/test_install_guide.py`.
- Question: When an approved harness changes a live file that has a source copy here (`preferences.md`, the `question-format` skill), should the source copy change too?
- Reason: `test_every_source_is_embedded_verbatim` requires the source copies and the install guide to match, and the 2026-10-23 question-handling edits were synced the same way.
- Source: project: `tests/test_install_guide.py`
- Not chosen: Changing only the live files, which leaves the sources stale and fails that test.
- Affects: spec scenario "An approved harness updates the live files and their sources", design.md (Decision 6), task 8.3 (`approve-harness`)
- Needs your yes: no

### D17. Test approach

- Decision: Tests use `unittest` in `tests/test_harness2cc.py`, run in the Python 3.12 environment, with a fake `claude` executable for executor and grader calls and a deterministic editor modelled on upstream's `demo.py`; each test is named after its spec scenario, and `tests/test_kl_specs.py` also reads this file.
- Question: How should the plug-in be tested without spending on model calls, and how do its tests meet the repository's rule that every scenario has a test of the same name?
- Reason: The repository's tests use `unittest` and name tests after scenarios; upstream's demo already has a deterministic editor; mocks are allowed where the real dependency cannot be reached.
- Source: P6 Tests for happy, edge and error paths
- Not chosen: Tests against the real `claude` command, which would spend money on every test run.
- Affects: design.md (Decision 10), every task's named tests, task 3.5 (spec test glob)
- Needs your yes: no

### D18. Documentation home

- Decision: The plug-in is documented in `harness2cc/README.md`, one section per PR; an install guide part for it is a follow-up.
- Question: Should the plug-in get a part in `docs/claude-session-tools-and-review-install.md`, which embeds every installed file verbatim, or only a README?
- Reason: Each PR carries the documentation for what it ships; a guide part is worth writing once the trial shows the tool is worth installing elsewhere.
- Source: P10 One shippable change per PR
- Not chosen: A new install guide part now, which would embed the whole package in the guide before the trial says whether to keep it.
- Affects: proposal.md (Follow-ups), tasks 3.4, 7.3 and 9.2 (README sections)
- Needs your yes: no

### D19. First trial baseline

- Decision: The first trial grades the harness from before the 2026-10-23 question-handling edits (saved outside the repository at `~/.claude/backups/harness-h0-2026-10-23/`) against the current one on the fast set, before the first Harness² loop.
- Question: What should the first trial compare, given that the question-handling edits were made on 2026-10-23 before this change?
- Reason: The request asks to test Harness² on this harness improvement, and that comparison measures the edits already made before Harness² proposes more.
- Source: request
- Not chosen: Starting with a Harness² loop on the current harness, which would leave the effect of the 2026-10-23 edits unmeasured.
- Affects: tasks 11.2 (baseline comparison) and 11.3 (first loop)
- Needs your yes: no

### D20. Delivery in three PRs

- Decision: The change ships as three PRs in order: PR 1 installs upstream and scans decision points (task groups 1 to 3, no model calls), PR 2 runs the sandboxed loop and grades it (groups 4 to 7, results are staged and nothing can be approved), PR 3 adds the two approval gates and the integration checks (groups 8 to 10); the first trial's results go in with the archive.
- Question: Should the plug-in ship as one PR or as several, and where are the cuts?
- Reason: Each of the three PRs does something useful once merged (listing decision points; measuring a loop's cost and showing its diffs; approving changes), and PR 2 cannot change a live file before the gate code in PR 3 exists. A fourth PR holding only the trial results would pay a full test run and review for a documentation change.
- Source: P10 One shippable change per PR
- Not chosen: One PR with all ten build groups, which mixes the install, the sandboxed loop and the live-writing gates in one review.
- Affects: tasks.md (delivery line, group headings, tasks 3.4, 3.5, 7.3, 9.2 and group 10), design.md (Migration Plan)
- Needs your yes: no

### D21. Replay length cap

- Decision: A replay longer than 80,000 characters keeps its first 10,000 and its last 70,000 characters, with a line saying how many were left out; assistant replies inside it stay cut to 4,000 characters each.
- Question: How long may a replay be, given that every probe run and every fast-set run reads the whole replay?
- Reason: The replay for one real decision point was longer than 80,000 characters before the cut, and each run pays for every character it reads; the opening holds the session's first request and the end holds what came just before the question.
- Source: cheapest to reverse (two constants in `harness2cc/replay.py`)
- Not chosen: No cap, which makes the cost of a run grow with the length of the session; or keeping only the end, which loses the session's first request.
- Affects: design.md (Decision 4), `harness2cc/replay.py`, `harness2cc/README.md` (Replays)
- Needs your yes: no

## Changes to decisions

- D3 (Upstream install) changed on 2026-10-23 by the user: upstream installed unchanged → upstream at the pinned commit plus a two-line Windows path patch applied by `harness2cc patch-upstream`, after task 1.3 found that upstream's `core/tree.py` builds backslash paths on Windows.
- D21 (Replay length cap) added on 2026-10-23 during apply, task 3.2: no limit on replay length → first 10,000 and last 70,000 characters of a replay longer than 80,000.
- D9 (Labels hidden from the editor) clarified on 2026-10-23 during apply: replays end before the user's reply → replays end with the user message that started the asking turn, because the asking turn itself shows the recommended option.
- D18 (Documentation home) changed on 2026-10-23 by the user: one README task at the end of the plan → a README section in each PR (tasks 3.4, 7.3 and 9.2), after P10 became "One shippable change per PR".
- D20 (Delivery in three PRs) changed on 2026-10-23 by the user: no PR plan → three PRs in order, after P10 became "One shippable change per PR".
