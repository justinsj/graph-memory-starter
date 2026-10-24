# harness2cc

Harness² ("Harness²: Recursive Agent Harnessing for an Open World", arXiv 2610.14224, code at
github.com/google-research/harness2) improves an agent's harness by running a task with the
current harness and with candidate edits, and keeping the edits the comparison supports.
harness2cc points it at the Claude Code harness (`CLAUDE.md`, skills, a preferences file) and
uses past sessions as the tasks. A past session where Claude asked you to choose, and you
answered, is a **decision point**; your answer is the label the result is graded against.

What this release does (PR 1 of 3): it installs upstream Harness² on Windows, patches it, scans
your transcripts for decision points and lists them. It makes no model calls. Running the loop
(PR 2) and approving its results (PR 3) come next. A run only ever covers decision points you
name; there is no option that covers every session.

Nothing user-specific is stored in this repository. The configuration, the decision points,
your answers and every later run live in the harness2cc home folder, `~/.claude/harness2cc/`
(or the folder `HARNESS2CC_HOME` names).

## Install (Windows)

From the repository root, in Git Bash:

```bash
py -3.11 -m pip install --user uv
UV="$(py -3.11 -c 'import sysconfig; print(sysconfig.get_path("scripts", "nt_user"))')/uv.exe"
"$UV" python install 3.12
"$UV" venv "$HOME/.claude/harness2cc/.venv" --python 3.12
"$UV" pip install --python "$HOME/.claude/harness2cc/.venv/Scripts/python.exe" -e harness2cc
"$HOME/.claude/harness2cc/.venv/Scripts/harness2cc.exe" patch-upstream
```

The fourth line also installs upstream `harness2` from git at commit
`1cfe254e8d25b15f37048c3730134686abe60335` (pinned in `pyproject.toml`). `harness2cc` is
installed in editable mode, because it reads transcripts with `../sessionmerge/session_merge.py`.

To call it as `harness2cc` from any folder, put two shims in a folder that is on both the
Windows and the Git Bash `PATH`, such as `~/.local/bin`:

```bash
mkdir -p "$HOME/.local/bin"
printf '@echo off\r\n"%%USERPROFILE%%\\.claude\\harness2cc\\.venv\\Scripts\\harness2cc.exe" %%*\r\n' > "$HOME/.local/bin/harness2cc.cmd"
printf '#!/bin/sh\nexec "$HOME/.claude/harness2cc/.venv/Scripts/harness2cc.exe" "$@"\n' > "$HOME/.local/bin/harness2cc"
chmod +x "$HOME/.local/bin/harness2cc"
```

## Configure

Copy `config.example.json` to `~/.claude/harness2cc/config.json` and fill in your values. Every
key is required; a missing or invalid key stops every command with the key's name.

| Key | What it holds |
| --- | --- |
| `workspace_root` | The folder whose `CLAUDE.md` and `.claude/` make up the harness being improved |
| `transcript_roots` | Folders of Claude Code transcripts, earlier ones first (a session in two of them counts once) |
| `editable_files` | Harness files a run may change, relative to `workspace_root` |
| `protected_sections` | Per file, the headings of sections no run may change |
| `protected_files` | Files no run may change |
| `source_map` | Live files that have a source copy in this repository, and their install guide step |
| `client_terms_file` | Client names that must never reach a lesson or a public source copy (relative to the home folder) |
| `models` | The `executor`, `editor` and `grader` models |
| `caps` | `max_references`, `max_k`, `library_entries_per_domain`, `claude_md_growth_characters` |

## Commands

### `harness2cc list-references`

Scans the transcript folders, writes `decision_points.jsonl` (the questions, without answers)
and `labels.jsonl` (your answers, read only by the grader) to the home folder, and lists them,
newest first.

```bash
harness2cc list-references
harness2cc list-references --since 2026-10-01 --mismatch-only
harness2cc list-references --project billing
```

`--mismatch-only` keeps the decision points where you chose something other than the
recommended option. A decision point is:

- an AskUserQuestion call with a "(Recommended)" option, and its answer (your own text counts);
- a chat question block (`### Q1. <Short name>`, lettered options, one "(Recommended)") answered
  by a reply such as `Q1: B`. When one question was asked, a reply can also start with
  `Option A`, or give the letter alone or before `.`, `,`, `:` or `)` (`B`, `A. and also`).

An interrupted or rejected question, or a reply that names no option, is not a decision point.
A reply that starts with a word, such as `a mix of both`, names no option.

### `harness2cc patch-upstream`

Applies the Windows path fix to the installed upstream package (see Windows notes). It checks
that the installed `harness2` is the pinned commit, is safe to re-run, and stops with the file
and the text it expected when that text is not there.

## Replays

A replay is what a sandboxed run sees of a decision point: the `/merge-session` digest of the
session up to the user message that started the asking turn, then a fixed instruction to write
the next response. The asking turn (which shows the recommended option) and your answer are left
out. Assistant replies are cut to 4,000 characters each, and a replay longer than 80,000
characters keeps its first 10,000 and its last 70,000. A prompt typed while a file was open in
the IDE starts with an `<ide_opened_file>` block; the replay removes that block so the prompt
itself stays in.

## Windows notes

Checked on Windows 11 with Python 3.12.15 from `uv`, upstream at commit `1cfe254e`:

- The core modules import: `harness2.core.recursion`, `selection`, `library`, `proposer`, `context`.
- Upstream's own `tests/test_workflow.py`, as published: 5 tests, 4 failures and 3 errors.
  - `core/tree.py` lines 140 and 167 build harness file keys with `str(p.relative_to(...))`, which
    gives backslash paths (`scripts\summarize.py`). They then fail to match the stubs upstream
    expects (`scripts/README.md`), and every valid edit is rejected as "off the editable surface".
    `harness2cc patch-upstream` changes both lines to `.as_posix()`.
  - `core/schedule.py` imports `fcntl`, which Windows does not have. Only the sweep driver
    (`schedule.run_domain`) uses it, and harness2cc does not call it.
- After `patch-upstream`, and with a no-op `fcntl` stand-in on `PYTHONPATH` only for upstream's
  own tests, all 5 upstream tests pass.
- uv installs package files as hard links to its cache on Windows. Writing the patch through
  such a link would also change the cached copy, so the next environment would start out
  patched without anyone running `patch-upstream`. `patch-upstream` therefore writes a new file
  and moves it into place, which leaves the cache with upstream's original. If an older
  harness2cc patched in place, run `uv cache clean harness2`, reinstall, and patch again.
- `core/proposer.py` line 525 and `core/runmark.py` line 54 hash `str(p.relative_to(root))`, so
  fingerprints differ from Linux but stay stable on one machine.

## Tests

```bash
"$HOME/.claude/harness2cc/.venv/Scripts/python.exe" -m unittest tests.test_harness2cc
```

The tests build their own transcripts and home folder in a temporary directory and make no
model calls. The test that needs upstream `harness2` is skipped, with that reason, when the tests
run in another Python environment.
