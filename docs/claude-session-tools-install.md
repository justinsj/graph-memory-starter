# Claude Code session tools: `/archive`, `/restore`, and the background-task spinner hook

These are installation instructions for an LLM coding agent (or a person) setting up these Claude Code add-ons in a new environment. Everything needed is in this file: four files to create, one settings change, and checks to run afterwards. Every file is reproduced in full and verbatim. Copy them byte for byte; don't paraphrase or "improve" them while installing.

Tested on Claude Code 2.1.286 with Python 3.12.7 on Windows 11. The scripts are plain Python 3 standard library and run on macOS and Linux too.

## What gets installed

| # | Item | Path (relative to the Claude config dir) | Kind | What it does |
|---|------|------------------------------------------|------|--------------|
| 1 | `session_archive.py` | `skills/archive/session_archive.py` | Python script | Does the work for `/archive` and `/restore`: moves a session's transcript out of `/resume` and back, lists archived sessions, and runs as a hook to keep archived sessions archived. |
| 2 | `/archive` | `skills/archive/SKILL.md` | User skill (slash command) | Archives the current session so it stops showing in `/resume`. |
| 3 | `/restore` | `skills/restore/SKILL.md` | User skill (slash command) | Lists archived sessions and puts the ones you pick back into `/resume`. |
| 4 | `wait_for_background.py` | `hooks/wait_for_background.py` | Stop hook script | Keeps the spinner (with the status text "Waiting for background tasks…") showing while background shells, subagents, monitors or workflows are still running, so the session doesn't look idle when it isn't. |
| 5 | Hook registrations | `settings.json` → `"hooks"` | Settings | Wire item 1 into the `Stop`, `SessionEnd` and `SessionStart` events, and item 4 into `Stop`. |

Items 1–3 depend on each other: `/restore` calls the script inside the `archive` skill folder, so both skill folders must sit side by side in the same `skills/` directory. Item 4 is independent and can be installed without the others.

## Before you start

1. **Find the Claude config directory.** It is `$CLAUDE_CONFIG_DIR` if that variable is set, otherwise `~/.claude` (on Windows, `C:\Users\<user>\.claude`). Everything below is relative to it, and this document calls it `<CLAUDE_DIR>`. Both scripts work out the same directory the same way at runtime.
2. **Find the Python command.** Run `python --version` and `python3 --version`. You need Python 3.8 or newer. Use whichever command works and call it `<PYTHON>` below. On Windows it is usually `python`; on macOS and Linux it is usually `python3`.
3. **If `<PYTHON>` is not `python`**, make two small changes while installing:
   - In both `SKILL.md` files, replace `python` with `python3` in the command inside the bash block **and** in the `allowed-tools` line (`Bash(python3 *session_archive.py*)`). The `allowed-tools` pattern has to match the command exactly or every run will trigger a permission prompt.
   - Use `python3` in the hook commands in step 5.

   Don't change anything else in the files.
4. **Back up `settings.json`** (for example to `settings.json.bak`) before editing it in step 5.

## Step 1: the archive script

**Explanation.** Claude Code stores each session's transcript at `<CLAUDE_DIR>/projects/<project-folder>/<session-id>.jsonl`, sometimes with a `<session-id>/` folder beside it for subagent transcripts and large tool results. `/resume` lists whatever transcripts are in `projects/`. Claude Code has no built-in "hide this session", so the script moves both items into `<CLAUDE_DIR>/session-archive/<project-folder>/`, where `/resume` doesn't look. Restoring moves them back. Nothing is deleted.

One complication: archiving usually happens from inside the session being archived. Claude Code keeps appending to the transcript, and once the file has been moved it starts a fresh file at the old path. Left alone, that fresh file (the "tail") would bring the session back into `/resume`. The script's `hook` command takes care of this:

- On **Stop** (end of every turn) and **SessionEnd**, if the current session is archived, it moves any tail out of `projects/` and appends it to the archived transcript.
- On **SessionStart**, it sweeps every archived session that isn't currently open and folds in any tail it left behind (for example after a crash).

Other details worth knowing:

- **Safety:** inside Claude Code, `archive` only acts on the session it's running in. It reads `CLAUDE_CODE_SESSION_ID`, which Claude Code sets in every tool shell, and refuses to archive any other id. This stops a confused model from archiving the wrong session.
- **Moves are crash-safe:** the file is renamed to `<name>.moving-<timestamp>` first, then merged into the destination. If a run stops part way, the next run picks up the leftovers.
- **Titles:** `list` shows the same title `/resume` would (agent name, custom title, AI title or summary, or failing those the first prompt). Sessions are listed most recently active first.
- **Restored sessions are touched** (their mtime set to now), so they show at the top of `/resume` and don't get removed early by Claude Code's `cleanupPeriodDays` cleanup.
- **Hooks never fail the session:** any error in `hook` mode is printed to stderr and swallowed.

CLI (the skills call it for you):

```
session_archive.py archive [SESSION_ID]   inside Claude Code, only the session running it
session_archive.py list
session_archive.py restore SELECTOR...    list number, session id or id prefix
session_archive.py hook                   reads the hook's JSON on stdin
```

**Install.** Create `<CLAUDE_DIR>/skills/archive/session_archive.py` with exactly this content:

````python
#!/usr/bin/env python3
"""Archive Claude Code sessions out of /resume, and restore them.

A session's transcript is ~/.claude/projects/<project>/<id>.jsonl, sometimes with
an <id>/ folder beside it for subagent and tool-result files. /resume lists those
transcripts. Archiving moves both into ~/.claude/session-archive/<project>/, where
/resume does not look; restoring moves them back.

Claude Code appends to a transcript and starts a fresh file if the old one has
been moved, so a session archived while it is still open leaves a tail behind in
projects/. The `hook` command, run from the Stop, SessionEnd and SessionStart
hooks, appends that tail onto the archived copy so the session stays out of
/resume.

usage:
  session_archive.py archive [SESSION_ID]   inside Claude Code, only the session running it
  session_archive.py list
  session_archive.py restore SELECTOR...    list number, session id or id prefix
  session_archive.py hook                   reads the hook's JSON on stdin
"""

import json
import os
import re
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

CLAUDE_DIR = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
PROJECTS = CLAUDE_DIR / "projects"
ARCHIVE = CLAUDE_DIR / "session-archive"
RUNNING = CLAUDE_DIR / "sessions"  # one <pid>.json per open session

# Time for a write already under way on a file we just renamed to land in it.
SETTLE_SECONDS = 0.2

# Title entries in a transcript, in the order /resume prefers them.
TITLE_FIELDS = {
    "agent-name": "agentName",
    "custom-title": "customTitle",
    "ai-title": "aiTitle",
    "summary": "summary",
}
# These entries lead with their type, so a look at the start of a line is enough.
TITLE_ENTRY = re.compile(rb'^\{\s*"type"\s*:\s*"(%s)"' % b"|".join(k.encode() for k in TITLE_FIELDS))


def warn(message):
    print(f"session_archive: {message}", file=sys.stderr)


def fail(message):
    warn(message)
    sys.exit(1)


# --- moving sessions ---------------------------------------------------------

def transfer(sid, src_dir, dst_dir):
    """Move a session's transcript and side folder from src_dir into dst_dir.

    Whatever dst_dir already holds for the session stays first and the moved
    content is appended after it. Returns True if anything moved.
    """
    grabbed = []
    for name in (f"{sid}.jsonl", sid):
        # Leftovers from a run that stopped part way are older than whatever is
        # at the plain name now, so they go across first.
        held = sorted(src_dir.glob(f"{name}.moving-*"))
        src = src_dir / name
        if src.exists():
            fresh = src_dir / f"{name}.moving-{time.time_ns()}"
            try:
                os.replace(src, fresh)  # Claude Code's next write starts a new file at src
                held.append(fresh)
            except OSError as err:
                warn(f"could not move {src} yet: {err}")
        grabbed += [(h, dst_dir / name) for h in held]
    if not grabbed:
        return False
    time.sleep(SETTLE_SECONDS)
    dst_dir.mkdir(parents=True, exist_ok=True)
    for held, dst in grabbed:
        merge(held, dst)
    return True


def merge(src, dst):
    """Move src to dst. Where both exist, transcripts append and folders merge."""
    if not dst.exists():
        shutil.move(src, dst)
    elif src.is_dir():
        for child in list(src.iterdir()):
            merge(child, dst / child.name)
        src.rmdir()
    elif dst.suffix == ".jsonl":
        append(src, dst)
        src.unlink()
    else:
        os.replace(src, dst)


def append(src, dst):
    data = src.read_bytes()
    if not data:
        return
    with open(dst, "ab+") as out:
        if out.tell():
            out.seek(-1, os.SEEK_END)
            if out.read(1) != b"\n":
                data = b"\n" + data
        out.write(data)


def running_session_ids():
    ids = set()
    for path in RUNNING.glob("*.json"):
        try:
            ids.add(json.loads(path.read_bytes()).get("sessionId"))
        except (OSError, ValueError, AttributeError):
            pass
    return ids


def sweep():
    """Fold in tails archived sessions wrote after their last Stop or SessionEnd.

    Sessions still open are left to their own Stop hook.
    """
    open_ids = running_session_ids()
    for path in ARCHIVE.glob("*/*.jsonl"):
        if path.stem not in open_ids:
            transfer(path.stem, PROJECTS / path.parent.name, path.parent)


# --- describing sessions -----------------------------------------------------

def prompt_text(entry):
    """The text of a typed prompt, or None for tool results and system entries."""
    if entry.get("isMeta") or entry.get("isSidechain") or "toolUseResult" in entry:
        return None
    content = (entry.get("message") or {}).get("content")
    if isinstance(content, list):
        content = next((b.get("text") for b in content
                        if isinstance(b, dict) and b.get("type") == "text"), None)
    if not isinstance(content, str):
        return None
    command = re.search(r"<command-name>(.*?)</command-name>", content)
    if command:
        args = re.search(r"<command-args>(.*?)</command-args>", content, re.S)
        content = f"{command.group(1)} {args.group(1) if args else ''}"
    elif content.lstrip().startswith("<"):
        return None
    return " ".join(content.split()) or None


def describe(path):
    """Title and project folder of a transcript, picked the way /resume picks them."""
    titles, cwd, first = {}, None, None
    with open(path, "rb") as fh:
        for n, raw in enumerate(fh):
            match = TITLE_ENTRY.match(raw)
            kind = match and match.group(1).decode()
            if not kind and ((cwd and first) or n > 2000):
                continue
            try:
                entry = json.loads(raw)
            except ValueError:
                continue
            if kind:
                titles[kind] = entry.get(TITLE_FIELDS[kind]) or titles.get(kind)
                continue
            cwd = cwd or entry.get("cwd")
            if first is None and entry.get("type") == "user":
                first = prompt_text(entry)
    title = next((titles[k] for k in TITLE_FIELDS if titles.get(k)), None) or first or path.stem[:8]
    title = " ".join(str(title).split())
    return {
        "title": title if len(title) <= 90 else title[:89] + "…",
        "cwd": cwd or path.parent.name,
    }


def archived_sessions():
    """Archived transcripts, most recently active first."""
    return sorted(ARCHIVE.glob("*/*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)


def size_label(n):
    return f"{n / 1e6:.1f} MB" if n >= 1e6 else f"{max(1, round(n / 1e3))} KB"


# --- commands ----------------------------------------------------------------

def cmd_archive(sid):
    # Claude Code sets this in every tool shell, so inside a session it is the
    # ground truth; an id typed out by the model is not.
    current = (os.environ.get("CLAUDE_CODE_SESSION_ID") or "").strip().lower()
    sid = (sid or current).strip().lower()
    if current and sid != current:
        fail(f"refusing to archive {sid}: this is running in session {current}, "
             "and only that session can be archived from inside it")
    if not re.fullmatch(r"[0-9a-f][0-9a-f-]{7,}", sid):
        fail(f"not a session id: {sid!r}")
    transcripts = list(PROJECTS.glob(f"*/{sid}.jsonl"))
    if not transcripts:
        if list(ARCHIVE.glob(f"*/{sid}.jsonl")):
            print(f"Session {sid} is already archived. /restore brings it back.")
            return
        fail(f"no transcript for session {sid} under {PROJECTS}")
    for transcript in transcripts:  # normally just one
        project = transcript.parent.name
        if not transfer(sid, PROJECTS / project, ARCHIVE / project):
            fail(f"could not move {transcript}")
    info = describe(ARCHIVE / project / f"{sid}.jsonl")
    print(f'Archived "{info["title"]}" ({sid}).')
    print("It no longer shows in /resume; /restore brings it back.")
    if sid == current:
        print("This session is still open: anything more said in it is archived along with it.")


def cmd_list():
    sessions = archived_sessions()
    if not sessions:
        print("No archived sessions.")
        return
    print(f"{len(sessions)} archived session(s), most recently active first:\n")
    for n, path in enumerate(sessions, 1):
        info = describe(path)
        stat = path.stat()
        when = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
        print(f"{n:>3}. {info['title']}")
        print(f"     {info['cwd']}")
        print(f"     last active {when} · {size_label(stat.st_size)} · {path.stem}")


def cmd_restore(selectors):
    sessions = archived_sessions()
    chosen = []
    for sel in " ".join(selectors).replace(",", " ").lower().split():
        if sel.isdigit() and len(sel) <= 3:
            matches = sessions[int(sel) - 1:int(sel)] if int(sel) >= 1 else []
        else:
            matches = [p for p in sessions if p.stem.startswith(sel)]
        if len(matches) != 1:
            fail(f"{sel!r} matches {len(matches)} archived sessions; run `list` and use a number or more of the id")
        if matches[0] not in chosen:
            chosen.append(matches[0])
    for path in chosen:
        sid, project = path.stem, path.parent.name
        info = describe(path)
        # Anything the session wrote since it was archived joins the archived copy first.
        transfer(sid, PROJECTS / project, ARCHIVE / project)
        if not transfer(sid, ARCHIVE / project, PROJECTS / project):
            fail(f"could not move {path}")
        # Counts as fresh activity: top of /resume, and clear of the cleanupPeriodDays sweep.
        os.utime(PROJECTS / project / f"{sid}.jsonl")
        try:
            (ARCHIVE / project).rmdir()
        except OSError:
            pass
        print(f'Restored "{info["title"]}" ({sid}).')
        print(f"  It shows in /resume for {info['cwd']}")


def cmd_hook():
    try:
        event = json.loads(sys.stdin.buffer.read() or b"{}")
    except ValueError:
        return
    if event.get("hook_event_name") == "SessionStart":
        sweep()
    elif event.get("session_id"):
        sid = event["session_id"]
        for path in ARCHIVE.glob(f"*/{sid}.jsonl"):
            transfer(sid, PROJECTS / path.parent.name, path.parent)


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    cmd, args = (argv[0], argv[1:]) if argv else ("", [])
    if cmd == "archive" and len(args) <= 1:
        cmd_archive(args[0] if args else None)
    elif cmd == "list" and not args:
        sweep()
        cmd_list()
    elif cmd == "restore" and args:
        sweep()
        cmd_restore(args)
    elif cmd == "hook":
        try:
            cmd_hook()
        except Exception as err:  # a hook must never get in the way of the session
            warn(f"hook: {err!r}")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
````

## Step 2: the `/archive` skill

**Explanation.** A user skill is a folder under `<CLAUDE_DIR>/skills/` holding a `SKILL.md`. The folder name becomes the slash command, so this one is `/archive`. Frontmatter fields:

- `disable-model-invocation: true` means only you can run it by typing `/archive`. Claude never archives a session on its own initiative.
- `allowed-tools: Bash(python *session_archive.py*)` pre-approves that one command so it runs without a permission prompt. Nothing else is pre-approved.
- `${CLAUDE_SKILL_DIR}` is replaced by Claude Code with this skill's folder, so the skill finds its script wherever the config dir is.

The body tells Claude to run the script with no session id, because the script reads the id from the environment, and to relay the result in a line or two.

**Install.** Create `<CLAUDE_DIR>/skills/archive/SKILL.md` with exactly this content:

````markdown
---
name: archive
description: Archive the current Claude Code session so it no longer shows in /resume. /restore brings it back.
disable-model-invocation: true
allowed-tools: Bash(python *session_archive.py*)
---

Archive this session by running exactly this with the Bash tool:

```bash
python "${CLAUDE_SKILL_DIR}/session_archive.py" archive
```

Don't add a session id: the script reads it from the environment Claude Code sets.

Then reply with what it printed, in a line or two, and nothing else. If it failed, show the error.
````

## Step 3: the `/restore` skill

**Explanation.** `/restore` takes an optional argument (`argument-hint`), which is passed in as `$ARGUMENTS`:

- **No argument:** Claude runs `list`. With 4 or fewer archived sessions it shows a multi-select picker (AskUserQuestion). With more, it prints the numbered list and waits for you to reply with numbers.
- **Numbers or session ids** (e.g. `/restore 2`, `/restore 3f9a1c2b`): Claude restores them directly.
- **Words** (e.g. `/restore pricing page`): Claude lists the sessions and restores the one whose title matches, asking first if more than one could match.

When it restores after showing a picker, Claude passes full session ids rather than list numbers, because the numbering can shift between listing and restoring. The skill reaches the shared script at `${CLAUDE_SKILL_DIR}/../archive/session_archive.py`, so it depends on step 1 being installed in the sibling `archive` folder. It has the same `disable-model-invocation` and `allowed-tools` settings as `/archive`.

**Install.** Create `<CLAUDE_DIR>/skills/restore/SKILL.md` with exactly this content:

````markdown
---
name: restore
description: List Claude Code sessions archived with /archive and restore the ones you pick so they show in /resume again.
argument-hint: "[list number | session id]"
disable-model-invocation: true
allowed-tools: Bash(python *session_archive.py*)
---

Restore sessions that /archive put away, so they show in /resume again. Run the script with the Bash tool, exactly as written here:

```bash
python "${CLAUDE_SKILL_DIR}/../archive/session_archive.py" <command>
```

Arguments: $ARGUMENTS

If the arguments are list numbers or session ids, run the `restore $ARGUMENTS` command, relay what it prints, and stop. If they are words, run `list`, pick the session whose title matches (ask if more than one could), and restore it by id as in step 3.

With no arguments:

1. Run the `list` command. If there are no archived sessions, say so and stop.
2. Ask which to restore.
   - 4 sessions or fewer: use AskUserQuestion with multiSelect on and one option per session. Label: the title cut to a few words. Description: the project folder, when it was last active, and the first 8 characters of the id.
   - More than 4: show the list as printed and ask the user to reply with the number(s) to restore, then wait for the reply.
3. Run `restore <id> [<id> ...]` with the full session ids of the chosen sessions. Use ids rather than list numbers, since the order can shift between listing and restoring.
4. Relay what it printed, a line or two per session.
````

## Step 4: the background-task wait hook (spinner / status)

**Explanation.** When Claude starts background work (a `run_in_background` shell, a subagent, a Monitor, a workflow), Claude Code ends the turn and shows the idle prompt even though work is still running. The task's completion wakes Claude later, but in the meantime the session looks finished. This Stop hook holds the turn open instead, so the spinner and the hook's status text, "Waiting for background tasks…", stay up until there is something for Claude to act on.

How it works:

1. Claude Code passes the Stop hook a JSON payload on stdin. If its `background_tasks` list is empty or missing, the hook exits at once and the turn ends as normal, so ordinary turns cost nothing.
2. Otherwise it watches the session transcript. When a task notification or a message you typed while waiting is queued, Claude Code writes a `"queue-operation"` line with `"operation": "enqueue"`. On the first one the hook exits, the turn ends, and the queued item wakes Claude straight away. It checks twice a second.
3. If something was already queued before the hook started (a task that finished just then), it doesn't wait at all. Only entries written by this Claude Code process count, which it checks against the session's `startedAt`, so leftovers from an earlier run of a resumed session are ignored.
4. It stops waiting when Claude Code or its parent process exits, or after `MAX_WAIT_SECONDS`: 7200 s (2 h) by default, overridable with the `CLAUDE_BG_WAIT_MAX_SECONDS` environment variable. On that timeout it prints a `systemMessage` saying so.
5. It never waits in sessions with no spinner to keep. It reads `<CLAUDE_DIR>/sessions/<CLAUDE_PID>.json` and skips any session whose `kind` isn't `interactive` (for example `-p`, SDK or background sessions).

It relies on these Claude Code internals: `background_tasks` and `transcript_path` in the Stop hook input, the `CLAUDE_PID` environment variable, the per-session `sessions/<pid>.json` file, and `queue-operation` transcript entries. If a future Claude Code version renames any of them, the hook simply exits early and the old idle behaviour comes back; nothing breaks.

**Install.** Create `<CLAUDE_DIR>/hooks/wait_for_background.py` with exactly this content:

````python
#!/usr/bin/env python3
"""Stop hook: keep the spinner up while background tasks are still running.

Claude Code ends a turn and shows the idle prompt even when a background shell,
subagent, monitor or workflow it started is still running; the task's
completion wakes it later. This hook holds the turn open instead, so the
spinner (with the hook's statusMessage) stays up until there is something for
Claude to act on.

The Stop hook input lists in-flight work in `background_tasks`. When that list
is empty the hook exits at once. Otherwise it watches the session transcript:
Claude Code logs a queue-operation "enqueue" line the moment a task
notification, or a message typed while waiting, is queued. On the first one the
hook exits, the turn ends, and the queued item wakes Claude straight away.

It also stops waiting after MAX_WAIT_SECONDS, when Claude Code exits, and never
waits in sessions without a spinner to keep (-p, SDK, background sessions).
"""

import ctypes
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

CLAUDE_DIR = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
RUNNING = CLAUDE_DIR / "sessions"  # one <pid>.json per open session

# Keep under the hook's "timeout" in settings.json, so the hook ends itself.
MAX_WAIT_SECONDS = float(os.environ.get("CLAUDE_BG_WAIT_MAX_SECONDS", 7200))
POLL_SECONDS = 0.5

# Queue operations that take an item off the queue again.
TAKEN = {"dequeue", "remove"}


def queue_ops(path, offset):
    """Queue-operation entries logged in the transcript after offset, and the new offset.

    Only whole lines are read, so a line still being written is picked up on the
    next call. A file shorter than offset has been replaced by a fresh one, so it
    is read from the start.
    """
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            if f.tell() < offset:
                offset = 0
            f.seek(offset)
            data = f.read()
    except OSError:
        return [], offset
    end = data.rfind(b"\n") + 1
    ops = []
    for line in data[:end].splitlines():
        if b'"queue-operation"' not in line:
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if entry.get("type") == "queue-operation":
            ops.append(entry)
    return ops, offset + end


def alive(pid):
    if not pid:
        return True
    if sys.platform != "win32":
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except OSError:
            pass
        return True
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return False
    code = ctypes.c_ulong()
    kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
    kernel32.CloseHandle(handle)
    return code.value == 259  # STILL_ACTIVE


def session_info(claude_pid):
    """What Claude Code records about its running session, or {} if unknown."""
    try:
        return json.loads((RUNNING / f"{claude_pid}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def since(entry, started_ms):
    """Whether the entry was logged by this Claude Code process, not an earlier run."""
    try:
        stamp = datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00"))
    except (KeyError, AttributeError, ValueError):
        return True
    return stamp.timestamp() * 1000 >= started_ms


def main():
    try:
        event = json.load(sys.stdin)
    except ValueError:
        return
    if event.get("hook_event_name") != "Stop" or not event.get("background_tasks"):
        return
    claude_pid = int(os.environ.get("CLAUDE_PID") or 0)
    parent_pid = os.getppid()
    transcript = event.get("transcript_path")
    info = session_info(claude_pid)
    if not transcript or info.get("kind", "interactive") != "interactive":
        return

    # Something may already be queued: a task that finished while this hook
    # started up. Then there is nothing to wait for. The queue lives in memory,
    # so only this process's entries count, not ones a resumed session left.
    ops, offset = queue_ops(transcript, 0)
    depth = 0
    for entry in ops:
        if since(entry, info.get("startedAt", 0)):
            op = entry.get("operation")
            depth = depth + 1 if op == "enqueue" else max(0, depth - (op in TAKEN))
    if depth:
        return

    deadline = time.monotonic() + MAX_WAIT_SECONDS
    while alive(claude_pid) and alive(parent_pid):
        if time.monotonic() > deadline:
            minutes = round(MAX_WAIT_SECONDS / 60)
            print(json.dumps({"systemMessage": f"Stopped waiting for background tasks after {minutes} min."}))
            return
        time.sleep(POLL_SECONDS)
        ops, offset = queue_ops(transcript, offset)
        if any(entry.get("operation") == "enqueue" for entry in ops):
            return


if __name__ == "__main__":
    main()
````

## Step 5: register the hooks in `settings.json`

**Explanation.** Hooks are shell commands Claude Code runs on lifecycle events, configured in `<CLAUDE_DIR>/settings.json` (user-level, so they apply in every project). Each command gets the event as JSON on stdin. The four registrations:

| Event | Command | Why |
|-------|---------|-----|
| `Stop` | `session_archive.py hook` | After every turn, moves the tail an archived-but-still-open session just wrote back into the archive. Without it, a session you archived reappears in `/resume` as soon as you say anything more in it. |
| `Stop` | `wait_for_background.py` | Holds the spinner while background tasks run (step 4). `timeout: 7260` is the hook's limit in seconds, kept just above the script's own 7200 s cap so the script always ends itself first. `statusMessage` is the text shown beside the spinner. |
| `SessionEnd` | `session_archive.py hook` | Last sweep for the closing session, catching anything written after its final Stop. |
| `SessionStart` | `session_archive.py hook` | Sweeps all archived sessions that aren't open and folds in any stray tails (from a crash, or a session closed without a clean SessionEnd). |

Claude Code runs all hooks for an event in parallel, so the two `Stop` hooks don't hold each other up: the archive hook finishes in milliseconds while the wait hook may block for a long time.

**Install.** Merge the block below into `<CLAUDE_DIR>/settings.json`. Replace `<PYTHON>` with the command from "Before you start", and `<CLAUDE_DIR>` with the **absolute** path to the config directory. Use forward slashes on Windows too (e.g. `C:/Users/alice/.claude`). Don't use `~` or `$HOME`, because how they expand depends on which shell runs the hook.

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "<PYTHON> \"<CLAUDE_DIR>/skills/archive/session_archive.py\" hook"
          }
        ]
      },
      {
        "hooks": [
          {
            "type": "command",
            "command": "<PYTHON> \"<CLAUDE_DIR>/hooks/wait_for_background.py\"",
            "timeout": 7260,
            "statusMessage": "Waiting for background tasks…"
          }
        ]
      }
    ],
    "SessionEnd": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "<PYTHON> \"<CLAUDE_DIR>/skills/archive/session_archive.py\" hook"
          }
        ]
      }
    ],
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "<PYTHON> \"<CLAUDE_DIR>/skills/archive/session_archive.py\" hook"
          }
        ]
      }
    ]
  }
}
```

Merging rules:

- If `settings.json` doesn't exist, create it with just this block.
- If it exists, keep every other key exactly as it is (`statusLine`, `permissions`, `enabledPlugins` and so on).
- If it already has a `"hooks"` object, **append** these groups to the existing `Stop`, `SessionEnd` and `SessionStart` arrays. Don't replace them, or you'll remove hooks someone else set up.
- Don't add a group twice if one with the same command is already there.
- Check the result is valid JSON (for example `<PYTHON> -m json.tool <CLAUDE_DIR>/settings.json`).

Changes to skills and hooks take effect in **new** Claude Code sessions. Restart any session that is open.

## Step 6: verify

Run these from a terminal. Each should succeed quietly or print what's shown:

```bash
# 1. The script runs and the archive is empty (or lists what's there).
<PYTHON> "<CLAUDE_DIR>/skills/archive/session_archive.py" list
#    -> No archived sessions.

# 2. Hook mode tolerates any input and prints nothing.
echo '{"hook_event_name":"SessionStart"}' | <PYTHON> "<CLAUDE_DIR>/skills/archive/session_archive.py" hook

# 3. The wait hook returns immediately when there are no background tasks.
echo '{"hook_event_name":"Stop","background_tasks":[]}' | <PYTHON> "<CLAUDE_DIR>/hooks/wait_for_background.py"

# 4. settings.json is valid JSON.
<PYTHON> -m json.tool "<CLAUDE_DIR>/settings.json" > /dev/null && echo ok
```

Then in a **new** Claude Code session:

1. Type `/` and confirm `archive` and `restore` both appear in the command list.
2. Say something, then run `/archive`. It should reply `Archived "<title>" (<id>).` Open `/resume` from another session (or after exiting) and confirm the session isn't listed.
3. Run `/restore`. Pick the session, and confirm it's back at the top of `/resume`.
4. Ask Claude to run `sleep 30` as a background command and finish its turn. The spinner should stay up with "Waiting for background tasks…" until the command completes, and then Claude should report the result.

## Uninstall

1. Run `/restore` (or `session_archive.py restore <id> ...`) for any sessions you want back in `/resume`. Sessions left in `<CLAUDE_DIR>/session-archive/` stay there untouched; they're just files.
2. Remove the four hook groups from `settings.json`.
3. Delete `<CLAUDE_DIR>/skills/archive/`, `<CLAUDE_DIR>/skills/restore/` and `<CLAUDE_DIR>/hooks/wait_for_background.py`.

## Not included: the status line

The source environment also shows a custom status line (model, context use and so on) at the bottom of Claude Code. That comes from the third-party **claude-hud** plugin (`jarrodwatts/claude-hud` on GitHub), not from these hooks, so it isn't reproduced here. To get it, run `/plugin marketplace add jarrodwatts/claude-hud`, then `/plugin install claude-hud@claude-hud`, then `/claude-hud:setup`, which writes the `statusLine` entry for the local platform.
