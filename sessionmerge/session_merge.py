#!/usr/bin/env python3
"""Mechanical steps for /merge-session: pass what one Claude Code session learned into another.

The model writes the handoff itself. This script does the parts that should not
depend on the model's memory or judgment:

  digest  turns a session transcript into plain text (what the user typed, what
          Claude replied, one line per tool call, tool errors, condensed
          summaries), so a session that Claude Code condensed can be read back
          in full
  find    lists sessions, open or closed, whose name matches some words, with
          the command that reopens a closed one
  path    names the handoff file for a source and a target session
  save    checks a draft handoff for secrets, saves it under <claude dir>/handoffs/,
          and prints the command the receiving session types to read it. The
          session writes the draft where it needs no approval (its scratchpad),
          so creating the handoff file never stops for a permission prompt
  check   scans a handoff file for secrets and database hostnames, and exits 1
          when it finds any

usage:
  session_merge.py digest [--session-id ID | --transcript PATH] [--output PATH]
  session_merge.py find WORDS...
  session_merge.py path --source NAME --target NAME [--date YYYY-MM-DD]
  session_merge.py save --draft PATH (--source NAME --target NAME [--date YYYY-MM-DD] | --replace PATH)
  session_merge.py check FILE
"""

import argparse
import json
import os
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Iterator

# Title entries in a transcript, in the order /resume prefers them.
TITLE_FIELDS: dict[str, str] = {
    "agent-name": "agentName",
    "custom-title": "customTitle",
    "ai-title": "aiTitle",
    "summary": "summary",
}
# These entries lead with their type, so a look at the start of a line is enough.
TITLE_ENTRY_PATTERN = re.compile(rb'^\{\s*"type"\s*:\s*"(%s)"' % b"|".join(key.encode() for key in TITLE_FIELDS))

# Tool input fields that say what a call did, most telling first.
TOOL_DETAIL_FIELDS: tuple[str, ...] = (
    "description", "file_path", "notebook_path", "skill", "to", "url", "pattern", "query", "command", "prompt",
)
MAXIMUM_TOOL_DETAIL_CHARACTERS = 160
MAXIMUM_TOOL_ERROR_CHARACTERS = 600
MAXIMUM_NOTIFICATION_CHARACTERS = 1500
MAXIMUM_SLUG_CHARACTERS = 60
SESSION_ID_PATTERN = re.compile(r"[0-9a-f][0-9a-f-]{7,}")

CONDENSED_MARKER = "--- Claude Code condensed the conversation here. Claude's working memory kept only the summary below. ---"

SENSITIVE_PATTERNS: dict[str, re.Pattern[str]] = {
    "AWS access key id": re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    "private key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "GitHub token": re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{22,})\b"),
    "Slack token": re.compile(r"\bxox[abposr]-[A-Za-z0-9-]{10,}"),
    "API key": re.compile(r"\bsk-(?:ant-)?[A-Za-z0-9_-]{20,}"),
    "JSON web token": re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
    "credentials in a URL": re.compile(r"\b[a-z][a-z0-9+.-]*://[^\s:/@]+:[^\s@/]+@", re.IGNORECASE),
    "secret value": re.compile(
        r"\b(?:password|passwd|pwd|secret|api[_-]?key|access[_-]?key|auth[_-]?token|token)\b[\"']?\s*[:=]\s*[\"']?"
        r"(?P<value>[^\s\"',;]{8,})",
        re.IGNORECASE,
    ),
    "database hostname": re.compile(
        r"\b[a-z0-9][a-z0-9.-]*\.(?:rds|redshift|redshift-serverless)\.amazonaws\.com\b"
        r"|\b[a-z0-9][a-z0-9-]*\.database\.windows\.net\b",
        re.IGNORECASE,
    ),
}


@dataclass
class TranscriptDigest:
    """A session transcript reduced to what was said and done, ready to render as text."""

    session_id: str
    transcript_path: Path
    title: str | None = None
    lines: list[str] = field(default_factory=list)
    counts: Counter[str] = field(default_factory=Counter)
    malformed_line_numbers: list[int] = field(default_factory=list)
    first_timestamp: str | None = None
    last_timestamp: str | None = None


@dataclass
class SessionMatch:
    """One session found by `find`, open or closed."""

    session_id: str
    title: str
    live_name: str | None
    working_directory: str | None
    last_active: datetime
    is_live: bool
    is_archived: bool
    transcript_path: Path


@dataclass
class SensitiveFinding:
    """One line of a handoff that looks like it holds a secret or a hostname."""

    line_number: int
    kind: str
    masked_excerpt: str


def resolve_claude_directory() -> Path:
    """Return the Claude Code config directory: $CLAUDE_CONFIG_DIR, or ~/.claude when it is not set.

    Returns:
        Path of the config directory (it is not checked for existence here).
    """
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")


# --- reading transcripts -----------------------------------------------------

def find_transcript(session_id: str, claude_directory: Path) -> Path:
    """Find the transcript of a session in projects/ or session-archive/.

    Args:
        session_id: Full session id, or a prefix of at least 8 characters that matches one session.
        claude_directory: Claude Code config directory.

    Returns:
        Path of the session's .jsonl transcript.

    Raises:
        ValueError: The id is not shaped like a session id, or the prefix matches more than one session.
        FileNotFoundError: No transcript has this id.
    """
    session_id = session_id.strip().lower()
    if not SESSION_ID_PATTERN.fullmatch(session_id):
        raise ValueError(f"not a session id: {session_id!r}")
    candidates = [
        path
        for folder in ("projects", "session-archive")
        for path in (claude_directory / folder).glob("*/*.jsonl")
        if path.stem.startswith(session_id)
    ]
    session_ids = {path.stem for path in candidates}
    if not candidates:
        raise FileNotFoundError(f"no transcript for session {session_id} under {claude_directory}/projects or session-archive")
    if len(session_ids) > 1:
        raise ValueError(f"{session_id!r} matches {len(session_ids)} sessions ({', '.join(sorted(session_ids))}); give more of the id")
    return max(candidates, key=lambda path: path.stat().st_mtime)


def read_entries(transcript_path: Path, malformed_line_numbers: list[int]) -> Iterator[dict]:
    """Yield each JSON entry of a transcript, recording the lines that are not valid JSON.

    Args:
        transcript_path: The .jsonl transcript.
        malformed_line_numbers: List that receives the 1-based number of every line that could not be parsed.

    Yields:
        One parsed entry per valid line.
    """
    with open(transcript_path, encoding="utf-8") as transcript_file:
        for line_number, line in enumerate(transcript_file, 1):
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except ValueError:
                malformed_line_numbers.append(line_number)
                continue
            if isinstance(entry, dict):
                yield entry
            else:
                malformed_line_numbers.append(line_number)


def text_blocks(content: object) -> list[str]:
    """Return the text parts of a message's content, which is either a string or a list of blocks.

    Args:
        content: The `message.content` value of a transcript entry.

    Returns:
        The non-empty text strings, in order.
    """
    if isinstance(content, str):
        return [content] if content.strip() else []
    if isinstance(content, list):
        return [block["text"] for block in content
                if isinstance(block, dict) and block.get("type") == "text" and str(block.get("text") or "").strip()]
    return []


def origin_kind(entry: dict) -> str | None:
    """Return where a user-role entry came from ("human", "peer", "task-notification"), when the transcript says.

    Args:
        entry: A transcript entry.

    Returns:
        The origin kind, or None when the entry carries no origin.
    """
    origin = entry.get("origin")
    if isinstance(origin, dict):
        return origin.get("kind")
    return origin if isinstance(origin, str) else None


def cut_text(text: str, maximum_characters: int) -> str:
    """Shorten text to a maximum length, saying how much was cut.

    Args:
        text: Text to shorten.
        maximum_characters: Longest text kept before the cut notice.

    Returns:
        The text unchanged when it fits, or its start followed by a notice of how many characters were cut.
    """
    text = text.strip()
    if len(text) <= maximum_characters:
        return text
    return f"{text[:maximum_characters].rstrip()} … [cut: {len(text) - maximum_characters:,} more characters]"


def describe_tool_use(block: dict) -> str:
    """Describe one tool call in a single line: the tool name and what it was asked to do.

    Args:
        block: A `tool_use` content block from an assistant entry.

    Returns:
        A line such as "Bash: List files in current directory".
    """
    tool_input = block.get("input") if isinstance(block.get("input"), dict) else {}
    detail = next((str(tool_input[key]) for key in TOOL_DETAIL_FIELDS if tool_input.get(key)), "")
    detail = " ".join(detail.split())
    name = block.get("name") or "unknown tool"
    return f"{name}: {cut_text(detail, MAXIMUM_TOOL_DETAIL_CHARACTERS)}" if detail else name


def tool_result_text(block: dict) -> str:
    """Return the text of a tool_result block, whose content is a string or a list of text blocks.

    Args:
        block: A `tool_result` content block from a user entry.

    Returns:
        The result text, joined with newlines.
    """
    return "\n".join(text_blocks(block.get("content")))


def format_timestamp(timestamp: object) -> str:
    """Turn an ISO timestamp from a transcript into "YYYY-MM-DD HH:MM" (UTC, as the transcript records it).

    Args:
        timestamp: The entry's `timestamp` value.

    Returns:
        The short form, or "unknown time" when the entry has none.
    """
    if not isinstance(timestamp, str) or len(timestamp) < 16:
        return "unknown time"
    return timestamp[:16].replace("T", " ")


def describe_command(text: str) -> str | None:
    """Turn a slash-command entry ("<command-name>/x</command-name> <command-args>y</command-args>") into "/x y".

    Args:
        text: The text of a user entry.

    Returns:
        The command and its arguments, or None when the text is not a slash command.
    """
    command = re.search(r"<command-name>(.*?)</command-name>", text, re.S)
    if not command:
        return None
    arguments = re.search(r"<command-args>(.*?)</command-args>", text, re.S)
    name = command.group(1).strip()
    return f"{name if name.startswith('/') else '/' + name} {arguments.group(1).strip() if arguments else ''}".strip()


def add_line(digest: TranscriptDigest, timestamp: object, speaker: str, text: str) -> None:
    """Append one speaker block to the digest.

    Args:
        digest: Digest being built.
        timestamp: The entry's `timestamp` value.
        speaker: Label such as "USER" or "CLAUDE".
        text: The block's text.
    """
    digest.lines.append(f"[{format_timestamp(timestamp)}] {speaker}\n{text.strip()}\n")


def add_user_entry(digest: TranscriptDigest, entry: dict) -> None:
    """Add a user-role entry to the digest: a typed prompt, a slash command, a message from another session,
    a task notification, a condensed summary or a tool error. Skill bodies, reminders and successful tool
    results are left out.

    Args:
        digest: Digest being built.
        entry: A transcript entry whose type is "user".
    """
    timestamp = entry.get("timestamp")
    content = (entry.get("message") or {}).get("content")
    kind = origin_kind(entry)
    if entry.get("isCompactSummary"):
        digest.counts["condensed summaries"] += 1
        digest.lines.append(CONDENSED_MARKER + "\n")
        add_line(digest, timestamp, "CONDENSED SUMMARY", "\n".join(text_blocks(content)))
        return
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_result" and block.get("is_error"):
                digest.counts["tool errors"] += 1
                add_line(digest, timestamp, "TOOL ERROR", cut_text(tool_result_text(block), MAXIMUM_TOOL_ERROR_CHARACTERS))
    texts = text_blocks(content)
    if not texts:
        return
    text = "\n".join(texts)
    if kind == "peer":
        digest.counts["messages from other sessions or subagents"] += 1
        add_line(digest, timestamp, "MESSAGE FROM ANOTHER SESSION OR SUBAGENT", text)
        return
    if kind == "task-notification" or text.lstrip().startswith("<task-notification>"):
        digest.counts["task notifications"] += 1
        add_line(digest, timestamp, "TASK NOTIFICATION", cut_text(text, MAXIMUM_NOTIFICATION_CHARACTERS))
        return
    if entry.get("isMeta"):
        return
    command = describe_command(text)
    if command:
        digest.counts["user prompts"] += 1
        add_line(digest, timestamp, "USER RAN", command)
        return
    if text.lstrip().startswith("<"):
        return
    if text.strip().startswith("[Request interrupted by user"):
        add_line(digest, timestamp, "USER INTERRUPTED", "The user stopped Claude's turn here.")
        return
    digest.counts["user prompts"] += 1
    add_line(digest, timestamp, "USER", text)


def add_assistant_entry(digest: TranscriptDigest, entry: dict) -> None:
    """Add an assistant entry to the digest: its reply text and one line per tool call. Thinking is left out.

    Args:
        digest: Digest being built.
        entry: A transcript entry whose type is "assistant".
    """
    content = (entry.get("message") or {}).get("content")
    if isinstance(content, str):
        content = [{"type": "text", "text": content}]
    if not isinstance(content, list):
        return
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text" and str(block.get("text") or "").strip():
            digest.counts["Claude replies"] += 1
            add_line(digest, entry.get("timestamp"), "CLAUDE", block["text"])
        elif block.get("type") == "tool_use":
            digest.counts["tool calls"] += 1
            digest.lines.append(f"[{format_timestamp(entry.get('timestamp'))}] TOOL {describe_tool_use(block)}\n")


def build_digest(transcript_path: Path) -> TranscriptDigest:
    """Read a transcript and reduce it to what was said and done.

    Args:
        transcript_path: The session's .jsonl transcript.

    Returns:
        The digest, with counts and the numbers of any lines that could not be parsed.
    """
    digest = TranscriptDigest(session_id=transcript_path.stem, transcript_path=transcript_path)
    titles: dict[str, str] = {}
    for entry in read_entries(transcript_path, digest.malformed_line_numbers):
        entry_type = entry.get("type")
        if entry_type in TITLE_FIELDS:
            titles[entry_type] = entry.get(TITLE_FIELDS[entry_type]) or titles.get(entry_type, "")
            continue
        if entry.get("isSidechain") or entry_type not in ("user", "assistant", "system"):
            continue
        if isinstance(entry.get("timestamp"), str):
            digest.first_timestamp = digest.first_timestamp or entry["timestamp"]
            digest.last_timestamp = entry["timestamp"]
        if entry_type == "user":
            add_user_entry(digest, entry)
        elif entry_type == "assistant":
            add_assistant_entry(digest, entry)
    digest.title = next((titles[key] for key in TITLE_FIELDS if titles.get(key)), None)
    return digest


def render_digest(digest: TranscriptDigest) -> str:
    """Render a digest as plain text: a header with counts, then every block in order.

    Args:
        digest: The digest to render.

    Returns:
        The digest text.
    """
    counts = ", ".join(f"{digest.counts[label]} {label}" for label in (
        "user prompts", "Claude replies", "tool calls", "tool errors", "condensed summaries",
        "messages from other sessions or subagents", "task notifications"))
    if digest.malformed_line_numbers:
        shown = ", ".join(str(number) for number in digest.malformed_line_numbers[:20])
        more = f" and {len(digest.malformed_line_numbers) - 20} more" if len(digest.malformed_line_numbers) > 20 else ""
        malformed = f"{len(digest.malformed_line_numbers)} line(s) of the transcript were not valid JSON and are missing here: line {shown}{more}"
    else:
        malformed = "every line of the transcript was read"
    header = [
        f"# Transcript digest: {digest.title or digest.session_id}",
        "",
        f"Session {digest.session_id}, transcript {digest.transcript_path}",
        f"From {format_timestamp(digest.first_timestamp)} to {format_timestamp(digest.last_timestamp)} (UTC)",
        counts,
        malformed,
    ]
    body = "\n".join(digest.lines)
    if digest.counts["condensed summaries"]:
        last_marker_offset = body[:body.rindex(CONDENSED_MARKER)].count("\n")
        # The header lines so far, this line, and one blank line come before the body's first line.
        last_marker_line = len(header) + 3 + last_marker_offset
        header.append(f"The last condensed summary starts at line {last_marker_line:,}. Claude's working memory starts there; "
                      "everything before it is known to Claude only through that summary.")
    else:
        header.append("No condensed summaries: the whole conversation is still in Claude's working memory.")
    if not digest.lines:
        header.append("")
        header.append("The transcript holds no prompts, replies or tool calls.")
    return "\n".join(header) + "\n\n" + body


# --- finding sessions --------------------------------------------------------

def read_live_sessions(claude_directory: Path, unreadable_paths: list[Path]) -> dict[str, dict]:
    """Read the records Claude Code keeps for each open session (sessions/<pid>.json).

    Args:
        claude_directory: Claude Code config directory.
        unreadable_paths: List that receives every record that could not be read.

    Returns:
        Each open session's record, keyed by session id.
    """
    live_sessions: dict[str, dict] = {}
    for path in sorted((claude_directory / "sessions").glob("*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            unreadable_paths.append(path)
            continue
        if isinstance(record, dict) and record.get("sessionId"):
            live_sessions[str(record["sessionId"]).lower()] = record
    return live_sessions


def read_title_and_directory(transcript_path: Path) -> tuple[str | None, str | None]:
    """Return a transcript's title (picked the way /resume picks it) and its working directory.

    Title entries are rewritten every turn, so one that does not parse is passed over and a later one is used.

    Args:
        transcript_path: The .jsonl transcript.

    Returns:
        The title (None when the session has none yet) and the working directory (None when not recorded).
    """
    titles: dict[str, str] = {}
    working_directory: str | None = None
    first_prompt: str | None = None
    with open(transcript_path, "rb") as transcript_file:
        for line_number, raw_line in enumerate(transcript_file):
            title_match = TITLE_ENTRY_PATTERN.match(raw_line)
            if not title_match and ((working_directory and first_prompt) or line_number > 2000):
                continue
            try:
                entry = json.loads(raw_line)
            except ValueError:
                continue
            if title_match:
                kind = title_match.group(1).decode()
                titles[kind] = entry.get(TITLE_FIELDS[kind]) or titles.get(kind, "")
                continue
            working_directory = working_directory or entry.get("cwd")
            if first_prompt is None and entry.get("type") == "user" and origin_kind(entry) in ("human", None) \
                    and not entry.get("isMeta"):
                texts = text_blocks((entry.get("message") or {}).get("content"))
                if texts and not texts[0].lstrip().startswith("<"):
                    first_prompt = " ".join(texts[0].split())[:90]
    title = next((titles[key] for key in TITLE_FIELDS if titles.get(key)), None) or first_prompt
    return (" ".join(str(title).split()) if title else None), working_directory


def find_sessions(words: list[str], claude_directory: Path, unreadable_paths: list[Path]) -> list[SessionMatch]:
    """List sessions, open or closed, whose title, open-session name or id contains every word.

    Args:
        words: Words to match, case-insensitive. Each must appear somewhere in the title, the name or the id.
        claude_directory: Claude Code config directory.
        unreadable_paths: List that receives open-session records that could not be read.

    Returns:
        The matching sessions, most recently active first.

    Raises:
        ValueError: No words were given.
    """
    lowered_words = [word.lower() for word in words if word.strip()]
    if not lowered_words:
        raise ValueError("give at least one word to match against session names")
    live_sessions = read_live_sessions(claude_directory, unreadable_paths)
    matches: list[SessionMatch] = []
    for folder, is_archived in (("projects", False), ("session-archive", True)):
        for transcript_path in (claude_directory / folder).glob("*/*.jsonl"):
            session_id = transcript_path.stem.lower()
            live_record = live_sessions.get(session_id)
            live_name = live_record.get("name") if live_record else None
            title, working_directory = read_title_and_directory(transcript_path)
            haystack = " ".join(filter(None, (title, live_name, session_id))).lower()
            if not all(word in haystack for word in lowered_words):
                continue
            matches.append(SessionMatch(
                session_id=transcript_path.stem,
                title=title or live_name or transcript_path.stem[:8],
                live_name=live_name,
                working_directory=working_directory or (live_record or {}).get("cwd"),
                last_active=datetime.fromtimestamp(transcript_path.stat().st_mtime),
                is_live=live_record is not None,
                is_archived=is_archived,
                transcript_path=transcript_path,
            ))
    return sorted(matches, key=lambda match: match.last_active, reverse=True)


def render_matches(words: list[str], matches: list[SessionMatch], unreadable_paths: list[Path]) -> str:
    """Render `find` results, with the reopen command for each closed session.

    Args:
        words: The words that were matched.
        matches: Sessions found, most recently active first.
        unreadable_paths: Open-session records that could not be read.

    Returns:
        The text to print.
    """
    searched = " ".join(words)
    lines = [f'No session matches "{searched}".'] if not matches else \
        [f'{len(matches)} session(s) match "{searched}", most recently active first:', ""]
    for number, match in enumerate(matches, 1):
        if match.is_live:
            state = f'open now as "{match.live_name}", reachable with SendMessage'
        elif match.is_archived:
            state = f"closed and archived (run /restore first), then: claude --resume {match.session_id}"
        else:
            state = f"closed, reopen with: claude --resume {match.session_id}"
        lines.append(f"{number:>3}. {match.title}")
        lines.append(f"     {state}")
        lines.append(f"     last active {match.last_active:%Y-%m-%d %H:%M} · {match.session_id}")
        lines.append(f"     {match.working_directory or 'working directory not recorded'}")
    if unreadable_paths:
        lines.append("")
        lines.append(f"{len(unreadable_paths)} open-session record(s) could not be read, so those sessions show as closed: "
                     + ", ".join(str(path) for path in unreadable_paths))
    return "\n".join(lines)


# --- naming the handoff file -------------------------------------------------

def build_slug(name: str, maximum_characters: int = MAXIMUM_SLUG_CHARACTERS) -> str:
    """Turn a session name into a file-name part: lowercase letters and digits joined by underscores.

    Args:
        name: Session name, for example "TICKET-12 P&L, Acme Widgets".
        maximum_characters: Longest slug kept.

    Returns:
        The slug, for example "ticket_12_p_l_acme_widgets".

    Raises:
        ValueError: The name has no letters or digits.
    """
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:maximum_characters].rstrip("_")
    if not slug:
        raise ValueError(f"session name {name!r} has no letters or digits to name a file with")
    return slug


def build_handoff_path(source_name: str, target_name: str, handoff_date: date, handoff_directory: Path) -> Path:
    """Name a new handoff file, <date>_<source>_to_<target>.md, adding _2, _3... when the name is taken.

    Creates the handoff directory when it does not exist.

    Args:
        source_name: Name of the session the handoff comes from.
        target_name: Name of the session it goes to.
        handoff_date: Date put at the start of the file name.
        handoff_directory: Folder that holds handoff files.

    Returns:
        A path that no file uses yet.
    """
    handoff_directory.mkdir(parents=True, exist_ok=True)
    base_name = f"{handoff_date.isoformat()}_{build_slug(source_name)}_to_{build_slug(target_name)}"
    candidate = handoff_directory / f"{base_name}.md"
    suffix = 2
    while candidate.exists():
        candidate = handoff_directory / f"{base_name}_{suffix}.md"
        suffix += 1
    return candidate


# --- checking for secrets ----------------------------------------------------

def mask_value(value: str) -> str:
    """Hide all but the first four characters of a value.

    Args:
        value: The text to hide.

    Returns:
        For example "AKIA… (20 characters)".
    """
    return f"{value[:4]}… ({len(value)} characters)"


def find_sensitive_text(text: str) -> list[SensitiveFinding]:
    """Find lines that look like they hold a secret, a credential or a database hostname.

    A "secret value" only counts when the value contains a digit, so prose such as
    "the token budget" or "password: required" is not flagged.

    Args:
        text: The handoff text.

    Returns:
        One finding per match, in line order. The matched text is masked.
    """
    findings: list[SensitiveFinding] = []
    for line_number, line in enumerate(text.splitlines(), 1):
        for kind, pattern in SENSITIVE_PATTERNS.items():
            for match in pattern.finditer(line):
                if kind == "secret value" and not any(character.isdigit() for character in match.group("value")):
                    continue
                findings.append(SensitiveFinding(line_number=line_number, kind=kind, masked_excerpt=mask_value(match.group(0))))
    return findings


# --- commands ----------------------------------------------------------------

def run_digest(arguments: argparse.Namespace, claude_directory: Path) -> int:
    """Run `digest`: print the transcript digest, or write it to --output and print a one-line summary.

    Args:
        arguments: Parsed command-line arguments.
        claude_directory: Claude Code config directory.

    Returns:
        Exit code 0.

    Raises:
        SystemExit: No session id was given and none is set in CLAUDE_CODE_SESSION_ID.
    """
    if arguments.transcript:
        transcript_path = Path(arguments.transcript)
        if not transcript_path.is_file():
            raise FileNotFoundError(f"no transcript at {transcript_path}")
    else:
        session_id = arguments.session_id or os.environ.get("CLAUDE_CODE_SESSION_ID")
        if not session_id:
            raise SystemExit("session_merge: no session id; run this inside Claude Code or pass --session-id or --transcript")
        transcript_path = find_transcript(session_id, claude_directory)
    digest = build_digest(transcript_path)
    text = render_digest(digest)
    if not arguments.output:
        print(text)
        return 0
    output_path = Path(arguments.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text, encoding="utf-8")
    print(f"Wrote {output_path} ({len(text.splitlines()):,} lines, {len(text):,} characters) "
          f"from {transcript_path}: {digest.counts['user prompts']} user prompts, "
          f"{digest.counts['condensed summaries']} condensed summaries, "
          f"{len(digest.malformed_line_numbers)} unreadable lines.")
    return 0


def run_find(arguments: argparse.Namespace, claude_directory: Path) -> int:
    """Run `find`: print the sessions whose name matches the words.

    Args:
        arguments: Parsed command-line arguments.
        claude_directory: Claude Code config directory.

    Returns:
        Exit code 0 when at least one session matches, 1 when none does.
    """
    unreadable_paths: list[Path] = []
    matches = find_sessions(arguments.words, claude_directory, unreadable_paths)
    print(render_matches(arguments.words, matches, unreadable_paths))
    return 0 if matches else 1


def parse_handoff_date(value: str | None) -> date:
    """Read a --date argument, defaulting to today.

    Args:
        value: The argument as typed, or None when it was left out.

    Returns:
        The date.

    Raises:
        SystemExit: The value is not a YYYY-MM-DD date.
    """
    try:
        return date.fromisoformat(value) if value else date.today()
    except ValueError:
        raise SystemExit(f"session_merge: --date must be YYYY-MM-DD, got {value!r}")


def build_receive_command(handoff_path: Path) -> str:
    """Return the command the receiving session types to read a handoff.

    Args:
        handoff_path: The saved handoff file.

    Returns:
        For example "/merge-session --receive C:/Users/me/.claude/handoffs/2026-10-22_a_to_b.md".
    """
    return f"/merge-session --receive {handoff_path.resolve().as_posix()}"


def print_findings(findings: list[SensitiveFinding]) -> None:
    """Print one indented line per finding: its line number, kind and masked text.

    Args:
        findings: What find_sensitive_text found.
    """
    for finding in findings:
        print(f"  line {finding.line_number}: {finding.kind}: {finding.masked_excerpt}")


def choose_save_path(arguments: argparse.Namespace, handoff_directory: Path) -> Path:
    """Pick where `save` writes: a new free name, or the saved handoff that --replace names.

    Args:
        arguments: Parsed command-line arguments.
        handoff_directory: Folder that holds handoff files.

    Returns:
        The path to write.

    Raises:
        SystemExit: --replace is mixed with --source, --target or --date; a new handoff lacks
            --source or --target; --date is not a YYYY-MM-DD date; or --replace names a file that
            does not exist or is not in the handoff folder.
    """
    if arguments.replace:
        if arguments.source or arguments.target or arguments.date:
            raise SystemExit("session_merge: use --replace on its own, or --source and --target for a new handoff, not both")
        replace_path = Path(arguments.replace).resolve()
        if not replace_path.is_file():
            raise SystemExit(f"session_merge: --replace names no saved handoff: {replace_path}")
        if handoff_directory.resolve() not in replace_path.parents:
            raise SystemExit(f"session_merge: --replace must name a file in {handoff_directory}, got {replace_path}")
        return replace_path
    if not (arguments.source and arguments.target):
        raise SystemExit("session_merge: a new handoff needs --source and --target (or --replace PATH to update a saved one)")
    return build_handoff_path(arguments.source, arguments.target, parse_handoff_date(arguments.date), handoff_directory)


def run_path(arguments: argparse.Namespace, claude_directory: Path) -> int:
    """Run `path`: print a free handoff file path under <claude dir>/handoffs/.

    Args:
        arguments: Parsed command-line arguments.
        claude_directory: Claude Code config directory.

    Returns:
        Exit code 0.

    Raises:
        SystemExit: --date is not a YYYY-MM-DD date.
    """
    print(build_handoff_path(arguments.source, arguments.target, parse_handoff_date(arguments.date), claude_directory / "handoffs"))
    return 0


def run_save(arguments: argparse.Namespace, claude_directory: Path) -> int:
    """Run `save`: check a draft handoff for secrets, copy it into <claude dir>/handoffs/, and print the receive command.

    The session writes the draft where it can write without asking (its scratchpad). This
    command, which the skill pre-approves, does the write into the handoff folder, so creating
    the handoff never stops for a permission prompt.

    Args:
        arguments: Parsed command-line arguments.
        claude_directory: Claude Code config directory.

    Returns:
        Exit code 0 when saved. Exit code 1 when the draft holds something that looks like a
        secret or a database hostname; nothing is saved then.

    Raises:
        FileNotFoundError: The draft does not exist.
        SystemExit: The arguments that say where to save are wrong (see choose_save_path).
    """
    draft_path = Path(arguments.draft)
    if not draft_path.is_file():
        raise FileNotFoundError(f"no draft handoff at {draft_path}")
    handoff_path = choose_save_path(arguments, claude_directory / "handoffs")
    content = draft_path.read_bytes()
    findings = find_sensitive_text(content.decode("utf-8"))
    if findings:
        print(f"Not saved: {len(findings)} line(s) in {draft_path} look like secrets or database hostnames. "
              "Rewrite each one in the draft, then run save again:")
        print_findings(findings)
        return 1
    handoff_path.write_bytes(content)
    print(f"Saved the handoff to {handoff_path.resolve().as_posix()}")
    print("To receive it, type this in the target session:")
    print(build_receive_command(handoff_path))
    return 0


def run_check(arguments: argparse.Namespace) -> int:
    """Run `check`: list lines of a handoff file that look like secrets or hostnames.

    Args:
        arguments: Parsed command-line arguments.

    Returns:
        Exit code 0 when the file is clean, 1 when anything was found.
    """
    handoff_path = Path(arguments.file)
    findings = find_sensitive_text(handoff_path.read_text(encoding="utf-8"))
    if not findings:
        print(f"clean: no secrets or database hostnames found in {handoff_path}")
        return 0
    print(f"{len(findings)} line(s) in {handoff_path} look like secrets or database hostnames. "
          "Rewrite each one, then run check again:")
    print_findings(findings)
    return 1


def build_argument_parser() -> argparse.ArgumentParser:
    """Build the command-line parser for the five commands.

    Returns:
        The parser.
    """
    parser = argparse.ArgumentParser(prog="session_merge.py", description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    digest_parser = commands.add_parser("digest", help="turn a session transcript into plain text")
    source = digest_parser.add_mutually_exclusive_group()
    source.add_argument("--session-id", help="session id or a unique prefix; defaults to $CLAUDE_CODE_SESSION_ID")
    source.add_argument("--transcript", help="path of a .jsonl transcript")
    digest_parser.add_argument("--output", help="write the digest here instead of printing it")
    find_parser = commands.add_parser("find", help="list sessions, open or closed, whose name matches")
    find_parser.add_argument("words", nargs="+")
    path_parser = commands.add_parser("path", help="name a new handoff file")
    path_parser.add_argument("--source", required=True, help="name of this session")
    path_parser.add_argument("--target", required=True, help="name of the session the handoff goes to")
    path_parser.add_argument("--date", help="YYYY-MM-DD; defaults to today")
    save_parser = commands.add_parser("save", help="check a draft handoff, save it under handoffs/ and print the receive command")
    save_parser.add_argument("--draft", required=True, help="the handoff as written in the session's scratchpad")
    save_parser.add_argument("--source", help="name of this session, for a new handoff")
    save_parser.add_argument("--target", help="name of the session the handoff goes to, for a new handoff")
    save_parser.add_argument("--date", help="YYYY-MM-DD; defaults to today, for a new handoff")
    save_parser.add_argument("--replace", help="a saved handoff to overwrite with the draft")
    check_parser = commands.add_parser("check", help="scan a handoff file for secrets and hostnames")
    check_parser.add_argument("file")
    return parser


def main(argv: list[str]) -> int:
    """Parse the arguments and run one command.

    Args:
        argv: Command-line arguments after the script name.

    Returns:
        The command's exit code.
    """
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    arguments = build_argument_parser().parse_args(argv)
    claude_directory = resolve_claude_directory()
    if arguments.command == "digest":
        return run_digest(arguments, claude_directory)
    if arguments.command == "find":
        return run_find(arguments, claude_directory)
    if arguments.command == "path":
        return run_path(arguments, claude_directory)
    if arguments.command == "save":
        return run_save(arguments, claude_directory)
    return run_check(arguments)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
