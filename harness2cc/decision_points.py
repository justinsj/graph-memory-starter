"""Decision points: past questions Claude asked with a recommended option, and the answers the user gave.

A decision point is one question from an assistant turn that asked the user to choose, either
through the AskUserQuestion tool (an option label holds "(Recommended)") or as a chat block
("### Q1. <Short name>" with lettered options, one marked "(Recommended)"), followed by the
user's answer. The answer is kept apart from the decision point: `decision_points.jsonl`
holds no answer, and `labels.jsonl` holds only the answers, for the grader.

Transcripts are read with the `/merge-session` helpers in `sessionmerge/session_merge.py`, so
both tools agree on what a typed prompt is.
"""

import hashlib
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

SESSIONMERGE_DIRECTORY = Path(__file__).resolve().parents[1] / "sessionmerge"
sys.path.insert(0, str(SESSIONMERGE_DIRECTORY))

import session_merge  # noqa: E402

from harness2cc.config import Harness2ccConfig  # noqa: E402

RECOMMENDED_MARKER = "(Recommended)"
ASK_USER_QUESTION_TOOL = "AskUserQuestion"
CHAT_QUESTION_HEADING = re.compile(r"^###\s+Q(\d+)\.\s+(.+?)\s*$", re.MULTILINE)
CHAT_OPTION_LINE = re.compile(r"^\s*-\s+([A-Z])\.\s+(.+?)\s*$", re.MULTILINE)
NUMBERED_ANSWER = re.compile(r"\b[Qq](\d+)\s*[:.)\-]?\s*(?:[Oo]ption\s+)?\(?([A-Ea-e])(?![A-Za-z])")
SINGLE_ANSWER = re.compile(r"^\s*(?:[Oo]ption\s+)?\(?([A-Ea-e])\)?(?:[\s.,:;!)]|$)")
# Context Claude Code puts in front of a typed prompt, such as the file open in the IDE.
LEADING_TAG_BLOCK = re.compile(r"\A\s*<(ide_[a-z_]+|system-reminder)\b[^>]*>.*?</\1>\s*", re.DOTALL)
TURN_STARTING_ORIGINS: tuple[str, ...] = ("peer", "task-notification")


@dataclass(frozen=True)
class DecisionPoint:
    """One question asked with a recommended option. It holds no answer."""

    decision_point_id: str
    session_id: str
    transcript: str
    timestamp: str
    project: str
    kind: str
    short_name: str
    question: str
    options: tuple[str, ...]
    recommended: str
    turn_start_uuid: str


@dataclass(frozen=True)
class Label:
    """The answer the user gave to one decision point."""

    decision_point_id: str
    chosen: str
    matches_recommended: bool


@dataclass
class ScanResult:
    """Everything one scan of the transcript folders found."""

    decision_points: list[DecisionPoint] = field(default_factory=list)
    labels: dict[str, Label] = field(default_factory=dict)
    transcripts_read: int = 0
    malformed_lines: int = 0
    skipped_without_turn_start: int = 0


@dataclass
class PendingQuestion:
    """A question seen in an assistant turn, waiting for the user's answer."""

    session_id: str
    transcript: str
    timestamp: str
    project: str
    turn_start_uuid: str | None
    payload: dict


def stable_identifier(session_id: str, key: str) -> str:
    """Return a decision point id that stays the same on every scan of the same question.

    Args:
        session_id: The session the question was asked in.
        key: What identifies the question inside the session (tool call id or turn, plus the question).

    Returns:
        "dp-" followed by the first 8 hex digits of a SHA-256 of both.
    """
    return "dp-" + hashlib.sha256(f"{session_id}|{key}".encode("utf-8")).hexdigest()[:8]


def project_name(working_directory: str) -> str:
    """Return the last folder name of a session's working directory, or "" when it is unknown.

    Args:
        working_directory: The `cwd` field of a transcript entry.

    Returns:
        The folder name, such as "billing-etl".
    """
    cleaned = working_directory.replace("\\", "/").rstrip("/")
    return cleaned.rsplit("/", 1)[-1] if cleaned else ""


def strip_leading_tags(text: str) -> str:
    """Remove the context blocks Claude Code puts in front of a typed prompt (IDE file, system reminder).

    Args:
        text: The text of a user entry.

    Returns:
        The text after any leading `<ide_...>...</ide_...>` or `<system-reminder>...</system-reminder>` blocks.
    """
    while True:
        leading_block = LEADING_TAG_BLOCK.match(text)
        if not leading_block:
            return text
        text = text[leading_block.end():]


def prompt_text(entry: dict) -> str:
    """Return the text of a user entry with its leading context blocks removed.

    Args:
        entry: A transcript entry whose type is "user".

    Returns:
        The text the user wrote, or "" when there is none.
    """
    content = (entry.get("message") or {}).get("content")
    return "\n".join(strip_leading_tags(text) for text in session_merge.text_blocks(content)).strip()


def is_human_entry(entry: dict) -> bool:
    """Say whether a user-role entry came from the user, not from a tool, a skill body, a reminder or a summary.

    Args:
        entry: A transcript entry whose type is "user".

    Returns:
        True when the entry is neither meta, nor a condensed summary, nor a tool result, and its origin is human.
    """
    if entry.get("isMeta") or entry.get("isCompactSummary"):
        return False
    if session_merge.origin_kind(entry) not in ("human", None):
        return False
    content = (entry.get("message") or {}).get("content")
    return not (isinstance(content, list) and any(
        isinstance(block, dict) and block.get("type") == "tool_result" for block in content))


def is_slash_command(entry: dict) -> bool:
    """Say whether a human user entry is a slash command such as `/opsx:apply`.

    Args:
        entry: A transcript entry whose type is "user".

    Returns:
        True for a slash command.
    """
    content = (entry.get("message") or {}).get("content")
    return session_merge.describe_command("\n".join(session_merge.text_blocks(content))) is not None


def is_typed_prompt(entry: dict) -> bool:
    """Say whether a user-role entry is a prompt the user typed, which can answer a question.

    Args:
        entry: A transcript entry whose type is "user".

    Returns:
        True for a typed prompt (leading IDE context allowed); False for slash commands, tool results,
        reminders, notifications, summaries and meta entries.
    """
    if not is_human_entry(entry) or is_slash_command(entry):
        return False
    text = prompt_text(entry)
    return bool(text) and not text.startswith("<") and not text.startswith("[Request interrupted by user")


def starts_turn(entry: dict) -> bool:
    """Say whether a user-role entry starts a new assistant turn: a typed prompt, a slash command,
    a message from another session, or a task notification.

    Args:
        entry: A transcript entry whose type is "user".

    Returns:
        True when the assistant's next reply answers this entry.
    """
    if session_merge.origin_kind(entry) in TURN_STARTING_ORIGINS and not entry.get("isCompactSummary"):
        return True
    return is_typed_prompt(entry) or (is_human_entry(entry) and is_slash_command(entry))


def parse_chat_questions(assistant_text: str) -> dict[str, dict]:
    """Find "### Q<n>. <Short name>" blocks that have a "(Recommended)" option in an assistant turn's text.

    Args:
        assistant_text: All text the assistant wrote in one turn.

    Returns:
        Question number -> {"short_name", "question", "options" (letter -> label), "recommended" (letter)}.
    """
    questions: dict[str, dict] = {}
    headings = list(CHAT_QUESTION_HEADING.finditer(assistant_text))
    for index, heading in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(assistant_text)
        body = assistant_text[heading.end():end]
        options = dict(CHAT_OPTION_LINE.findall(body))
        recommended = [letter for letter, label in options.items() if RECOMMENDED_MARKER in label]
        if not recommended:
            continue
        question_line = next((line.strip() for line in body.splitlines() if line.strip()), "")
        questions[heading.group(1)] = {
            "short_name": heading.group(2),
            "question": question_line,
            "options": options,
            "recommended": recommended[0],
        }
    return questions


def parse_chat_answers(reply_text: str, open_questions: dict[str, dict]) -> dict[str, str]:
    """Read which option letter the user picked for each open chat question.

    Replies such as "Q1: B", "Q2. A" or "Q3 option C" name the question. When exactly one
    question is open, a reply that starts with the letter ("B", "Option A", "A. and also ...")
    answers it.

    Args:
        reply_text: The user's typed reply.
        open_questions: The questions from `parse_chat_questions`, by number.

    Returns:
        Question number -> chosen letter, only for letters that are among that question's options.
    """
    answers = {number: letter.upper() for number, letter in NUMBERED_ANSWER.findall(reply_text)
               if number in open_questions}
    if not answers and len(open_questions) == 1:
        single = SINGLE_ANSWER.match(reply_text)
        if single:
            answers = {next(iter(open_questions)): single.group(1).upper()}
    return {number: letter for number, letter in answers.items() if letter in open_questions[number]["options"]}


def tool_answers(entry: dict) -> dict[str, str]:
    """Return the answers an AskUserQuestion result recorded, keyed by question text.

    Args:
        entry: The user-role entry that carries the tool result.

    Returns:
        Question text -> answer; empty when the call was interrupted or rejected.
    """
    result = entry.get("toolUseResult")
    answers = result.get("answers") if isinstance(result, dict) else None
    if not isinstance(answers, dict):
        return {}
    return {str(question): str(answer) for question, answer in answers.items() if str(answer).strip()}


def add_decision_point(scan: ScanResult, decision_point: DecisionPoint, chosen: str) -> None:
    """Record a decision point and its label, keeping the first copy when the id was already seen.

    Args:
        scan: The scan being built.
        decision_point: The decision point.
        chosen: The answer the user gave.
    """
    if decision_point.decision_point_id in scan.labels:
        return
    scan.decision_points.append(decision_point)
    scan.labels[decision_point.decision_point_id] = Label(
        decision_point_id=decision_point.decision_point_id,
        chosen=chosen,
        matches_recommended=chosen.strip() == decision_point.recommended.strip(),
    )


def scan_transcript(transcript_path: Path, scan: ScanResult) -> None:
    """Add every answered decision point in one transcript to the scan.

    Args:
        transcript_path: A session's .jsonl transcript.
        scan: The scan being built; malformed lines and skipped questions are counted in it.
    """
    malformed_line_numbers: list[int] = []
    pending_tool_questions: dict[str, PendingQuestion] = {}
    open_chat_questions: dict[str, dict] = {}
    open_chat_context: PendingQuestion | None = None
    turn_texts: list[str] = []
    turn_context: PendingQuestion | None = None
    last_prompt_uuid: str | None = None
    for entry in session_merge.read_entries(transcript_path, malformed_line_numbers):
        if entry.get("isSidechain") or entry.get("type") not in ("user", "assistant"):
            continue
        context = PendingQuestion(
            session_id=str(entry.get("sessionId") or transcript_path.stem),
            transcript=str(transcript_path),
            timestamp=str(entry.get("timestamp") or ""),
            project=project_name(str(entry.get("cwd") or "")),
            turn_start_uuid=last_prompt_uuid,
            payload={},
        )
        content = (entry.get("message") or {}).get("content")
        if entry.get("type") == "assistant":
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text" and str(block.get("text") or "").strip():
                    turn_texts.append(block["text"])
                    turn_context = context
                elif block.get("type") == "tool_use" and block.get("name") == ASK_USER_QUESTION_TOOL:
                    context.payload = {"tool_use_id": block.get("id"), "input": block.get("input") or {}}
                    pending_tool_questions[str(block.get("id"))] = context
            continue
        if isinstance(content, list) and any(
                isinstance(block, dict) and block.get("type") == "tool_result" for block in content):
            for block in content:
                if not isinstance(block, dict) or block.get("type") != "tool_result":
                    continue
                asked = pending_tool_questions.pop(str(block.get("tool_use_id")), None)
                if asked is not None:
                    add_tool_decision_points(scan, asked, tool_answers(entry))
            continue
        if not starts_turn(entry):
            continue
        if turn_texts:
            parsed = parse_chat_questions("\n".join(turn_texts))
            if parsed:
                open_chat_questions, open_chat_context = parsed, turn_context
            turn_texts = []
        if open_chat_questions and open_chat_context is not None and is_typed_prompt(entry):
            add_chat_decision_points(scan, open_chat_context, open_chat_questions,
                                     parse_chat_answers(prompt_text(entry), open_chat_questions))
            open_chat_questions, open_chat_context = {}, None
        last_prompt_uuid = str(entry.get("uuid") or "") or None
    scan.malformed_lines += len(malformed_line_numbers)


def add_tool_decision_points(scan: ScanResult, asked: PendingQuestion, answers: dict[str, str]) -> None:
    """Turn one answered AskUserQuestion call into decision points, one per question with a recommendation.

    Args:
        scan: The scan being built.
        asked: The call, with its context.
        answers: Question text -> answer, from `tool_answers`; empty when the call was not answered.
    """
    for question in asked.payload["input"].get("questions") or []:
        labels = tuple(str(option.get("label", "")) for option in question.get("options") or [])
        recommended = next((label for label in labels if RECOMMENDED_MARKER in label), "")
        question_text = str(question.get("question", ""))
        chosen = answers.get(question_text, "")
        if not recommended or not chosen:
            continue
        if asked.turn_start_uuid is None:
            scan.skipped_without_turn_start += 1
            continue
        add_decision_point(scan, DecisionPoint(
            decision_point_id=stable_identifier(asked.session_id, f"{asked.payload['tool_use_id']}|{question_text}"),
            session_id=asked.session_id,
            transcript=asked.transcript,
            timestamp=asked.timestamp,
            project=asked.project,
            kind=ASK_USER_QUESTION_TOOL,
            short_name=str(question.get("header", "")),
            question=question_text,
            options=labels,
            recommended=recommended,
            turn_start_uuid=asked.turn_start_uuid,
        ), chosen)


def add_chat_decision_points(scan: ScanResult, asked: PendingQuestion, questions: dict[str, dict],
                             answers: dict[str, str]) -> None:
    """Turn answered chat question blocks into decision points.

    Args:
        scan: The scan being built.
        asked: The context of the assistant turn that asked.
        questions: The open questions, by number.
        answers: Question number -> chosen letter, from `parse_chat_answers`.
    """
    for number, letter in answers.items():
        if asked.turn_start_uuid is None:
            scan.skipped_without_turn_start += 1
            continue
        question = questions[number]
        options = question["options"]
        add_decision_point(scan, DecisionPoint(
            decision_point_id=stable_identifier(
                asked.session_id, f"{asked.turn_start_uuid}|Q{number}|{question['question']}"),
            session_id=asked.session_id,
            transcript=asked.transcript,
            timestamp=asked.timestamp,
            project=asked.project,
            kind="chat",
            short_name=question["short_name"],
            question=question["question"],
            options=tuple(f"{option_letter}. {label}" for option_letter, label in options.items()),
            recommended=f"{question['recommended']}. {options[question['recommended']]}",
            turn_start_uuid=asked.turn_start_uuid,
        ), f"{letter}. {options[letter]}")


def scan_transcripts(transcript_roots: tuple[Path, ...]) -> ScanResult:
    """Scan every session transcript under the given folders. Subagent transcripts are skipped.

    Args:
        transcript_roots: Folders that hold Claude Code transcripts, such as `~/.claude/projects`.
            Earlier folders win when the same session is in two of them.

    Returns:
        The decision points, their labels and the counts of what was read and skipped.
    """
    scan = ScanResult()
    for root in transcript_roots:
        for transcript_path in sorted(root.rglob("*.jsonl")):
            if "subagents" in transcript_path.parts:
                continue
            scan.transcripts_read += 1
            scan_transcript(transcript_path, scan)
    return scan


def write_scan(scan: ScanResult, config: Harness2ccConfig) -> tuple[Path, Path]:
    """Write the decision points and, separately, the labels into the harness2cc home folder.

    Args:
        scan: The scan to write.
        config: The configuration, which names the home folder.

    Returns:
        The decision points file and the labels file.
    """
    config.home.mkdir(parents=True, exist_ok=True)
    with config.decision_points_file.open("w", encoding="utf-8", newline="\n") as handle:
        for decision_point in scan.decision_points:
            handle.write(json.dumps(asdict(decision_point)) + "\n")
    with config.labels_file.open("w", encoding="utf-8", newline="\n") as handle:
        for label in scan.labels.values():
            handle.write(json.dumps(asdict(label)) + "\n")
    return config.decision_points_file, config.labels_file


def read_decision_points(config: Harness2ccConfig) -> dict[str, DecisionPoint]:
    """Read the decision points the last scan wrote.

    Args:
        config: The configuration, which names the home folder.

    Returns:
        Decision point id -> decision point.

    Raises:
        FileNotFoundError: When no scan has been written yet; the message names `list-references`.
    """
    if not config.decision_points_file.is_file():
        raise FileNotFoundError(
            f"{config.decision_points_file} does not exist. Run `harness2cc list-references` first.")
    decision_points: dict[str, DecisionPoint] = {}
    for line in config.decision_points_file.read_text(encoding="utf-8").splitlines():
        if line.strip():
            raw = json.loads(line)
            raw["options"] = tuple(raw["options"])
            decision_point = DecisionPoint(**raw)
            decision_points[decision_point.decision_point_id] = decision_point
    return decision_points
