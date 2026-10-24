"""Replays: a past session up to the point where Claude was about to ask, for a sandboxed rerun.

A replay is the `/merge-session` digest of the session's transcript, cut after the user
message that started the asking turn. The asking turn itself (which shows the question and
its recommended option) and the user's answer are left out, so neither the executor nor the
editor can see what the user chose. A fixed closing instruction, outside the editable
harness, asks for the next response.
"""

import json
from pathlib import Path

from harness2cc.decision_points import DecisionPoint, is_human_entry, session_merge, strip_leading_tags

MAXIMUM_ASSISTANT_TEXT_CHARACTERS = 4_000
MAXIMUM_REPLAY_CHARACTERS = 80_000
KEPT_OPENING_CHARACTERS = 10_000
REPLAY_FILE_NAME = "replay.md"
REPLAY_SOURCE_FILE_NAME = "replay_source.jsonl"
CLOSING_INSTRUCTION = """--- End of the conversation so far. ---

You are the assistant in this session. Write the next response you would send to the user
after their last message above: your plan, the decisions you would settle yourself, and the
questions you would ask them, following the instructions in this folder. You cannot run
commands or reach any system; you can only read the files in this folder. Do not do the
work itself."""


class ReplayError(ValueError):
    """A replay cannot be built from the transcript as recorded."""


def cut_assistant_text(entry: dict) -> dict:
    """Return an assistant entry whose text blocks are cut to the replay's maximum length.

    Args:
        entry: A transcript entry whose type is "assistant".

    Returns:
        The entry, with long text blocks shortened by `session_merge.cut_text`.
    """
    content = (entry.get("message") or {}).get("content")
    if not isinstance(content, list):
        return entry
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str):
            block["text"] = session_merge.cut_text(block["text"], MAXIMUM_ASSISTANT_TEXT_CHARACTERS)
    return entry


def strip_prompt_context(entry: dict) -> dict:
    """Return a human user entry without the IDE or reminder blocks in front of its text.

    `/merge-session`'s digest leaves out any user text that starts with "<", so a prompt typed
    while a file was open in the IDE would otherwise vanish from the replay.

    Args:
        entry: A transcript entry whose type is "user".

    Returns:
        The entry, with leading context blocks removed from its text.
    """
    message = entry.get("message") or {}
    content = message.get("content")
    if isinstance(content, str):
        message["content"] = strip_leading_tags(content)
    elif isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str):
                block["text"] = strip_leading_tags(block["text"])
    return entry


def write_replay_source(decision_point: DecisionPoint, work_directory: Path) -> Path:
    """Copy the transcript up to and including the user message that started the asking turn.

    Args:
        decision_point: The decision point to replay.
        work_directory: Folder that receives the cut transcript.

    Returns:
        The cut transcript file.

    Raises:
        ReplayError: When the transcript no longer holds the entry that started the asking turn.
    """
    transcript_path = Path(decision_point.transcript)
    work_directory.mkdir(parents=True, exist_ok=True)
    replay_source_path = work_directory / REPLAY_SOURCE_FILE_NAME
    found = False
    with transcript_path.open(encoding="utf-8") as source, \
            replay_source_path.open("w", encoding="utf-8", newline="\n") as target:
        for line in source:
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                target.write(line if line.endswith("\n") else line + "\n")
                continue
            if isinstance(entry, dict) and entry.get("type") == "assistant":
                entry = cut_assistant_text(entry)
            elif isinstance(entry, dict) and entry.get("type") == "user" and is_human_entry(entry):
                entry = strip_prompt_context(entry)
            target.write(json.dumps(entry) + "\n")
            if isinstance(entry, dict) and entry.get("uuid") == decision_point.turn_start_uuid:
                found = True
                break
    if not found:
        raise ReplayError(
            f"{transcript_path} has no entry {decision_point.turn_start_uuid} (the prompt that started the turn "
            f"asking {decision_point.decision_point_id}); rescan with `harness2cc list-references`.")
    return replay_source_path


def shorten_replay(digest_text: str) -> str:
    """Keep the opening and the most recent part of a digest that is longer than the replay limit.

    Args:
        digest_text: The rendered digest.

    Returns:
        The digest unchanged when it fits, else its first part, a notice of what was left out, and its last part.
    """
    if len(digest_text) <= MAXIMUM_REPLAY_CHARACTERS:
        return digest_text
    kept_recent_characters = MAXIMUM_REPLAY_CHARACTERS - KEPT_OPENING_CHARACTERS
    left_out = len(digest_text) - MAXIMUM_REPLAY_CHARACTERS
    return (digest_text[:KEPT_OPENING_CHARACTERS].rstrip()
            + f"\n\n[... {left_out:,} characters of the middle of the conversation are left out ...]\n\n"
            + digest_text[-kept_recent_characters:].lstrip())


def build_replay_text(decision_point: DecisionPoint, work_directory: Path) -> str:
    """Build the replay text for a decision point.

    Args:
        decision_point: The decision point to replay.
        work_directory: Folder for the cut transcript the digest is built from.

    Returns:
        The digest of the session up to the user message that started the asking turn, then the closing instruction.
    """
    replay_source_path = write_replay_source(decision_point, work_directory)
    digest = session_merge.build_digest(replay_source_path)
    return shorten_replay(session_merge.render_digest(digest)) + "\n\n" + CLOSING_INSTRUCTION + "\n"


def write_replay(decision_point: DecisionPoint, work_directory: Path) -> Path:
    """Write `replay.md` for a decision point into a folder.

    Args:
        decision_point: The decision point to replay.
        work_directory: The folder; it also receives the cut transcript.

    Returns:
        The path of `replay.md`.
    """
    replay_path = work_directory / REPLAY_FILE_NAME
    replay_path.write_text(build_replay_text(decision_point, work_directory), encoding="utf-8", newline="\n")
    return replay_path
