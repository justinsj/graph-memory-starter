---
title: /merge-session (passing one Claude Code session's details into another)
id: session-merge
type: topic
tags: [claude-code, skill, install-guide, runguard, transcripts]
related: [index, scale-benchmarks]
updated: 2026-10-22
---

# /merge-session

Source: `sessionmerge/session_merge.py` and `sessionmerge/skill/merge-session/SKILL.md`. Tests: `tests/test_session_merge.py` (run with `python -m unittest discover -s tests -p test_session_merge.py`; this repo's `.venv` has no pytest). Installed copy: `~/.claude/skills/merge-session/`. Install instructions: Part G of `docs/claude-session-tools-and-review-install.md`.

## When you change it, also update

- The installed copy in `~/.claude/skills/merge-session/`. Copy both files; the skill runs the script from its own folder.
- The two verbatim copies in Part G of the install guide (steps 21 and 22). The guide promises byte-for-byte copies. Regenerate them from the source files, never by hand, and compare afterwards.
- The Part G verify list, when a command's output changes.

## Nuances not obvious from the code

- **This repository is public** (github.com/justinsj/graph-memory-starter). Test data, docstring examples and wiki notes must use neutral names (TICKET-12, Acme Widgets, app-prod), never real session names, ticket keys, client names or internal secret names. Check `git grep` for them before every push.
- **Transcript shape (Claude Code 2.1.308).** User prompts carry `origin.kind` = `human`. Messages from other sessions and subagent hand-backs are `isMeta: true` with `origin.kind` = `peer`; that is the one `isMeta` entry worth keeping. Condensed summaries are user entries with `isCompactSummary: true`, after a `system` entry with subtype `compact_boundary`. A forked session (title ends in ⑂) starts with a condensed summary.
- **Title entries are rewritten every turn.** One session had 251 `ai-title` entries. Take the last non-empty value, and prefer `agent-name`, then `custom-title`, then `ai-title`, the order `/resume` uses.
- **The live session name lives in `~/.claude/sessions/<pid>.json`** (`name`, `sessionId`). `ListAgents` shows the same names. `CLAUDE_CODE_SESSION_ID` is set in every tool shell.
- **runguard exempts `session_merge.py` through `exempt_patterns`** (added 2026-10-22 to `~/.claude/runguard/config.json`, `runguard/config.json` and the guide's step 12; all three must stay identical). Without the exemption, block mode would refuse every skill call. A list in config.json replaces the default list (`merged.update(loaded)` in `runguard_common.load_config`), so it repeats the three defaults.
- **Exempt patterns are matched against the whole command line.** A bare `session_merge\.py` pattern, and the old defaults `--help\b` and `--version\b`, also exempted chains such as `python pull.py --help && python backtest.py`. Since 2026-10-22 every exempt pattern comes from `build_exempt_pattern` in `runguard_common.py`, which anchors it to the `ALONE` rule: nothing chained outside double quotes (`&&`, a lone `&`, `;`, `|`, newline), and no `$(...)` or backticks anywhere. `2>&1` and `&>` redirections are fine. A `&` inside double quotes is fine too, because session names such as "TICKET-12 P&L Acme Widgets" contain one. `tests/test_runguard.py` (`ShippedConfig`) fails if `runguard/config.json` stops repeating the defaults exactly.
- **Cross-session messages are plain text.** `@path` attaches nothing on the receiving side, so a handoff always goes as a file plus a pointer message.
- **Writing into `~/.claude/handoffs/` with the Write tool stops for approval.** The folder is outside the project, so Claude Code asks before creating the file. Since 2026-10-22 the skill writes a draft in the session's scratchpad (no prompt) and the pre-approved script copies it in with `save`, which also runs the secrets check and prints the `/merge-session --receive <file>` command at once. Later edits and the Delivery note go through `save --replace` for the same reason. The only approval left is the one before sending the message.
