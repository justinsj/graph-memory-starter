# Design

## Context

See proposal.md (Why) for the motivation. What shapes the approach:

- Upstream Harness² (commit `1cfe254e`, 2026-10-13) supports two executors, OpenCode and Codex, and two editor channels, `opencode` and `claude_cli`. Its `claude_cli` channel runs `claude --dangerously-skip-permissions -p` and forces Vertex AI settings into the environment.
- Upstream declares POSIX and Python 3.12 or later. Reading the code, the only POSIX-only call in the core is `fcntl` in `core/schedule.py` (`_write_summary`), the module that drives a sweep over a whole benchmark. The core loop is reachable without it: `core.recursion.run_mode`, `core.selection.run_selection` and `reflect_adoption`, and `core.library.Library`. Running upstream's tests on Windows (task 1.3) also found that `core/tree.py` lines 140 and 167 build backslash paths, which makes every valid edit look off the editable surface; changing them to `.as_posix()` makes all 5 upstream tests pass (decision D3).
- The plug-in points are two protocols in upstream: `Substrate` (`surface`, `materialise`, `execute`, `read_trajectory`, `preflight`) and `BenchmarkAdapter` (`tasks`, `domain_of`, `task_prompt`, `task_files`, `execute`, `delivered`, `trajectory`, `deliverable_files`, `deliverable_text`, `base_harness`, `validate_tree`, `score`). Upstream's `demo.py` shows a deterministic editor that tests can reuse.
- Upstream already keeps grades away from the editor: `context.assert_tree_has_no_grader_verdicts` runs before a library write, and `BenchPrompts` refuses the words "score", "rubric" and "evaluation".
- The machine is Windows with Python 3.11, Git Bash, Docker and a stopped WSL Ubuntu 22.04. Claude Code is logged in on Windows. `uv` is not installed.
- This repository is public. It holds the source copies of the `question-format` skill and `preferences.md`, embedded verbatim in `docs/claude-session-tools-and-review-install.md` (checked by `tests/test_install_guide.py`).
- Labels exist: the scan of one user's transcripts found 92 answered questions with a recommended option (56 matched, 36 did not).

## Goals / Non-Goals

**Goals:**

- One Harness² loop at a time, on decision points the user names, with k and mode from the command line.
- A sandbox for every model session (executor, editor, grader) with no live tools and no credentials.
- Two approval gates, and a grade against the user's real answers at gate 1.
- A dollar figure for one k=1 loop.

**Non-Goals:**

- Running on every task, or on every new session as it happens (the paper's online mode).
- Editing hooks, settings, scripts, plugins, subagents or memory files. Only the files the configuration lists as editable can change.
- Replaying sessions with the repository they worked in. Replays hold the conversation digest only (follow-up).
- Library consolidation or retrieval by meaning (follow-up).

## Decisions

### 1. Call upstream's core loop directly, not its sweep CLI

`harness2cc run` builds the base runs, then calls `run_mode("agg" | "seq", ...)`, `run_selection` (only when k > 1; k=1 uses `trivial_selection`) and `reflect_adoption`. It never imports `core.schedule`, which holds the sweep and the POSIX lock. Alternatives: a fork of upstream (drifts from the paper's code), or WSL (needs a second Claude Code install and login inside Ubuntu).

### 2. A Claude Code substrate and a replay adapter, in `harness2cc/`

The substrate's editable surface is relative to the workspace root and comes from the configuration: always-loaded files (in the first trial `CLAUDE.md` and `.claude/openspec-rules/preferences.md`) and skills under `.claude/skills/<name>/SKILL.md`. `hooks_file` and `plugin_dir` are `None`, so upstream itself rejects hook and plugin edits. `materialise` writes the tree into a new folder; `execute` copies that folder per run, adds `replay.md`, and runs:

```text
claude -p --output-format stream-json --verbose --model <executor>
       --strict-mcp-config --mcp-config <empty.json> --setting-sources project
       --allowedTools Read,Glob,Grep --max-turns 30
```

with the replay prompt on standard input. `read_trajectory` renders the stream (assistant text, tool calls with truncated arguments, truncated tool results) into upstream's trajectory grammar, following `substrate/opencode.py`. The adapter's `score` returns `None`, so upstream never sees a grade.

### 3. One sandbox for every model session

Executor, editor and grader sessions all run with an empty MCP configuration in strict mode and project settings only (no user hooks, plugins or MCP servers), in a fresh folder, with an environment that drops every variable named `AWS_*`, `GH_TOKEN`, `GITHUB_TOKEN`, `GOOGLE_*`, `CLOUD_ML_*`, `CLAUDE_CODE_USE_VERTEX`, `ANTHROPIC_VERTEX_*`, and any name ending in `PASSWORD`, `SECRET` or `TOKEN` (the Claude Code login is stored in the user profile, not in these variables). The executor and grader get Read, Glob and Grep. The editor gets Read, Glob, Grep, Write and Edit with `--permission-mode acceptEdits`, which accepts edits inside its working folder only; harness2cc replaces upstream's `claude_cli` command builder so `--dangerously-skip-permissions` and the Vertex settings are never used. Alternative: upstream's editor command as is, which would give an agent that reads untrusted transcript text full permissions and the user's cloud credentials.

### 4. Decision points and replays

The transcript scan finds AskUserQuestion calls whose options include "(Recommended)" and their answers, and "### Q<n>." chat blocks with a "(Recommended)" option followed by a reply such as "Q1: B". Interrupted or rejected calls are skipped, and archived copies are deduplicated by session and question. Each decision point gets a stable id (`dp-` and the first 8 hex digits of a hash of the session id and the question). The answer goes to `labels.jsonl` only. The replay (`replay.md`) holds the user's messages up to that turn word for word, the assistant's text replies (each cut to 4,000 characters), and the tool calls by name and file path only. It ends with a fixed instruction that is outside the editable surface: write the next response to the user (plan, decisions settled, questions asked) without doing the work. A replay longer than 80,000 characters keeps its first 10,000 and its last 70,000, with a line saying how much was left out (decision D21). The replay is built from the `/merge-session` digest (`session_merge.build_digest`) of a copy of the transcript cut at the turn's first message, so both tools read transcripts the same way; leading `<ide_…>` blocks are removed from typed prompts first, because the digest skips user text that starts with `<`. Alternative: `claude --resume --fork-session` on the real session, which keeps the old `CLAUDE.md` text already present in the transcript, so a candidate harness would not take effect.

### 5. Grading against the user's answers

The grader is a sandboxed `claude -p` session (default model sonnet) that gets the executor's response, the question with its options, the user's answer and the Needs-your-yes list from the OpenSpec `rules.md`. It returns JSON: whether the response asked the question, which option it chose or recommended, and whether the question is a Needs-your-yes kind. "Matched" means the chosen or recommended option equals the user's. "Settled a Needs-your-yes" means a Needs-your-yes question that the response settled without asking, and it counts as a failure whatever option was chosen. Grades are written to `runs/<run-id>/grades/`, outside every editor workspace. The fast set defaults to the 5 most recent decision points not used as references (`--fast-set` overrides it); `test --full` grades every decision point not used as a reference; `test --harness <folder>` grades a saved snapshot against the current harness.

### 6. The two gates

Gate 1: after the loop, the adopted harness is staged under `runs/<run-id>/pending/harness/` with `harness.diff`, an evidence summary from upstream's step record, and the fast-set grades. `approve-harness` first checks that each live file still matches the fingerprint the run read (otherwise it refuses and says to run again), runs the scans, checks the `CLAUDE.md` growth cap (2,000 characters), backs up each file to `~/.claude/harness2cc/backups/<run-id>/`, writes the live files, updates each file's source copy and the install guide through the configured source map, and runs `tests/test_install_guide.py`. Gate 2: reflection writes the lesson into a `Library` rooted at `library/pending/`; `run_mode` reads only the approved `library/`, so a pending lesson is never used. `approve-lesson` runs the scans and the cap (20 entries per domain), moves the entry, and rebuilds the index. Both gates append to `ledger.jsonl`. Alternative: a third gate before each probe, which would add interruptions while the sandbox already prevents live side effects.

### 7. Scans

Every approval scans the added lines for secrets (AWS key patterns, tokens, private keys) and injected instructions ("ignore previous instructions", `curl ... | sh`, `Invoke-Expression`, long base64 blocks). Files that have a source copy in this public repository, and every library entry, are also scanned for client names from `client_terms.txt` and for database hostnames (`*.rds.amazonaws.com`, `cluster-`). A finding blocks the approval and names the file, the line and the finding.

### 8. User-specific data outside the repository

`~/.claude/harness2cc/config.json` holds the workspace root, the editable files, the protected `CLAUDE.md` sections and files, the source map, the transcript roots, the models and the caps. `client_terms.txt`, `labels.jsonl`, runs, the library, backups and `ledger.jsonl` live in the same folder. The repository ships `harness2cc/config.example.json` with placeholder values only. A missing or invalid configuration key stops the command with the key's name.

### 9. Install

`uv` is installed for the user with `py -3.11 -m pip install --user uv`, then `uv python install 3.12` and `uv venv ~/.claude/harness2cc/.venv --python 3.12`. Upstream is installed from git at the pinned commit, and `harness2cc` from this repository in editable mode. `harness2cc patch-upstream` then applies the two-line Windows path fix to the installed `core/tree.py`; it checks the installed commit first, is safe to re-run, stops with the file and line when the text it expects is not there, and writes a new file that it moves into place, because uv installs files as hard links to its cache and writing through the link would patch the cached copy too. Every command that runs upstream's loop checks that the patch is in place before it starts. Two shims in `~/.local/bin`, which is on both the Windows and the Git Bash `PATH`, call the environment's entry point: `harness2cc.cmd` for PowerShell and cmd, and a `harness2cc` shell script for Git Bash.

### 10. Tests

`tests/test_harness2cc.py` uses `unittest`, like the rest of the repository, and runs in the Python 3.12 environment. Executor and grader calls go to a fake `claude` executable placed first on `PATH`, which prints canned stream-json and records its arguments and environment. Editor calls use a deterministic proposer, following upstream's `demo.py`. Every test is named after its spec scenario. `tests/test_kl_specs.py` reads test names from `tests/test_kl_*.py` only; it will also read `tests/test_harness2cc.py`.

```text
+----------------------------------------------------------+
|  Claude Code transcripts (projects and session archive)  |
+----------------------------------------------------------+
                             |
                             | list-references (scan only)
                             v
+----------------------------------------------------------+
|  decision points: replay.md per point                    |
|  answers kept apart in labels.jsonl (grader only)        |
+----------------------------------------------------------+
                             |
                             | run --reference --k --mode
                             v
+----------------------------------------------------------+
|  upstream Harness2 core (pinned commit)                  |
|  reference run, propose, probe, compose, select, reflect |
|  executor and grader: claude -p in the sandbox           |
|  editor: claude -p in the sandbox, edits own folder only |
+----------------------------------------------------------+
              |                               |
              | composed harness              | lesson
              v                               v
+-----------------------------+ +-----------------------------+
|  fast-set grades, diff,     | |  library/pending/<domain>/  |
|  staged under pending/      | |  scans and library cap      |
+-----------------------------+ +-----------------------------+
              |                               |
              | Gate 1: approve-harness       | Gate 2: approve-lesson
              v                               v
+-----------------------------+ +-----------------------------+
|  live files, source copies, | |  library/<domain>/ and      |
|  install guide, backups     | |  its index                  |
+-----------------------------+ +-----------------------------+
```

Text alternative: transcripts are scanned into decision points; a run on the named points calls the upstream loop with Claude Code as executor, editor and grader, all sandboxed; the composed harness waits at gate 1 and the lesson at gate 2; each gate writes only after the user approves.

## Risks / Trade-offs

- [The replay has no repository and no tool output, so the executor may decide differently from the real session] → Grades compare two harnesses on the same replays, so the difference is what matters; repository snapshots are a follow-up.
- [The grader maps a free-text response to an option and can be wrong] → Grades keep the grader's quoted evidence per question, and gate 1 shows the per-question table for a spot check.
- [Five fast-set points are a small sample] → Gate 1 shows counts, not percentages; `test --full` runs the held-out set when the user wants a firmer number.
- [Upstream may not run on Windows beyond the core] → Only the core modules are used; task 1.3 imports them and runs upstream's own test file on Windows before any adapter code is written.
- [Cost and plan limits: Opus as executor and editor] → `--budget-usd` stops the run; `--dry-run` prints an estimate first; the models are flags.
- [Transcripts contain pasted text that could carry instructions] → Every session is sandboxed with read-only tools and no credentials (the editor writes only inside its folder), and approvals scan for injected instructions.
- [Company data reaching the public repository through a source copy] → Client-name and hostname scans on every file with a source copy; all user data lives under `~/.claude/harness2cc/`; the example configuration holds placeholders only.
- [A live file edited between the run and the approval] → Approval compares fingerprints and refuses on a mismatch.

## Migration Plan

0. Delivery: three PRs in the order of `tasks.md` (decision D20). PR 1 installs and scans, PR 2 runs and stages, PR 3 adds the gates.
1. Install `uv`, Python 3.12, upstream at the pinned commit and `harness2cc` (Decision 9).
2. Write `~/.claude/harness2cc/config.json` and `client_terms.txt` from the example.
3. Rollback: each approved harness has its backups under `~/.claude/harness2cc/backups/<run-id>/`, and the README gives the copy commands to restore them. Removing `~/.claude/harness2cc/` and the shim uninstalls the tool; the repository change is reverted by reverting its commit.
