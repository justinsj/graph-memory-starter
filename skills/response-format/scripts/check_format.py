"""Check a markdown response, report or decisions file against the response-format standard.

The standard lives in ../SKILL.md. This script checks the parts a machine can check:
the outcome line comes first, PR and ticket links sit in the Links block directly under
it, the top-level sections keep their fixed order, every D, F and Q block has an
`### <ID>. <Short name>` heading with its labels in the fixed order, and no ticket or PR
number appears without a link or a description.

Usage:
    python check_format.py FILE [FILE ...]
    python check_format.py --blocks-only FILE      # only the D, F and Q blocks
    some_command | python check_format.py          # read standard input

Exit 0 when there are no findings, 1 when there are findings, 2 on a usage error.
"""

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

# Known top-level sections, in their fixed order. Any other `## ` heading is a body section,
# which sits between Links and Tests.
SECTION_ORDER: list[str] = [
    "Links",
    "Tests",
    "Decisions",
    "Not done",
    "Files",
    "Next step",
    "Questions for you",
]
BODY_SECTION_RANK = 0.5

DECISION_LABELS: list[str] = [
    "Decision",
    "Question",
    "Reason",
    "Source",
    "Not chosen",
    "Affects",
    "Needs your yes",
]
DECISION_REQUIRED: set[str] = {"Decision", "Reason"}
PROBLEM_LABELS: list[str] = ["Symptom", "Example", "Root cause", "Fix"]
QUESTION_LABELS: list[str] = ["Context", "Example", "Options", "Reply with", "Recorded in"]
QUESTION_REQUIRED: set[str] = {"Context", "Example", "Options"}
LINK_LABELS: set[str] = {"PR", "Ticket", "Review comment", "CI run", "Deploy", "Page"}

MAX_SHORT_NAME_WORDS = 6
MAX_SHORT_NAME_CHARACTERS = 60

# A pull request URL, not a link to a comment, file or commit inside the pull request.
PR_URL = re.compile(r"https://github\.com/[\w.-]+/[\w.-]+/pull/\d+(?![\w/#])")
TICKET_URL = re.compile(r"https://[\w.-]+\.atlassian\.net/browse/[A-Z][A-Z0-9]+-\d+")
BLOCK_HEADING = re.compile(r"^### ([DFQ])(\d+)\. (.+?)\s*$")
ANY_BLOCK_HEADING = re.compile(r"^### [DFQ]\d+\b")
SECTION_HEADING = re.compile(r"^## (?!#)(.+?)\s*$")
TOP_LABEL = re.compile(r"^- ([A-Z][A-Za-z ]*?):(?:\s|$)")
BOLD_LABEL = re.compile(r"^- \*\*[^*]+\*\*:?")
OPTION_LINE = re.compile(r"^\s{2,}- ([A-Z])\. (.*)$")
LINKS_LINE = re.compile(r"^Links:\s")
LINK_BULLET = re.compile(r"^- ([A-Za-z ]+): \[.+\]\(https?://[^)]+\)")
FENCE = re.compile(r"^\s*(```|~~~)")
MARKDOWN_LINK = re.compile(r"\[[^\]]*\]\([^)]*\)")
INLINE_CODE = re.compile(r"`[^`]*`")
BARE_URL = re.compile(r"https?://\S+")
TICKET_KEY = re.compile(r"\b([A-Z]{2,10})-(\d{2,6})\b(?!\s*\()")
PR_NUMBER = re.compile(r"(?<![\w/#&])#(\d+)\b(?!\s*\()")
NOT_TICKET_PREFIXES: set[str] = {"UTF", "SHA", "ISO", "RFC", "TLS", "AES", "MD", "HTTP", "IPV"}


@dataclass(frozen=True)
class Finding:
    """One place where the text breaks the standard.

    Attributes:
        line: 1-based line number of the problem.
        rule: Short rule id, stable across runs.
        message: What is wrong and how to fix it.
    """

    line: int
    rule: str
    message: str


def strip_fenced_code(lines: list[str]) -> list[str]:
    """Blank out lines inside fenced code blocks, keeping line numbers.

    Args:
        lines: The document lines.

    Returns:
        A list of the same length where fenced lines (and the fences) are empty strings.
    """
    visible: list[str] = []
    in_fence = False
    for line in lines:
        if FENCE.match(line):
            in_fence = not in_fence
            visible.append("")
            continue
        visible.append("" if in_fence else line)
    return visible


def check_outcome(lines: list[str]) -> list[Finding]:
    """Check that the first non-empty line is a plain outcome sentence.

    Args:
        lines: Document lines with fenced code blanked out.

    Returns:
        A finding when the first line is a heading, list item, table row or quote.
    """
    for number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        if re.match(r"^\s*(#|- |\* |\d+\. |\||>)", line):
            return [Finding(number, "outcome-first", "Start with one or two plain sentences that state the outcome, before any heading, list or table.")]
        return []
    return [Finding(1, "outcome-first", "The response is empty.")]


def find_sections(lines: list[str]) -> list[tuple[int, str]]:
    """List the top-level `## ` sections.

    Args:
        lines: Document lines with fenced code blanked out.

    Returns:
        Pairs of (1-based line number, section name).
    """
    sections: list[tuple[int, str]] = []
    for number, line in enumerate(lines, start=1):
        match = SECTION_HEADING.match(line)
        if match:
            sections.append((number, match.group(1)))
    return sections


def section_rank(name: str) -> float:
    """Return the position of a section in the fixed order.

    Args:
        name: The text of a `## ` heading.

    Returns:
        The index in SECTION_ORDER, or BODY_SECTION_RANK for a body section.
    """
    if name in SECTION_ORDER:
        return float(SECTION_ORDER.index(name))
    return BODY_SECTION_RANK


def check_section_order(sections: list[tuple[int, str]]) -> list[Finding]:
    """Check that the top-level sections keep the fixed order.

    Args:
        sections: Pairs of (line number, section name) in document order.

    Returns:
        One finding per section that comes after a section it should precede.
    """
    findings: list[Finding] = []
    highest_rank = -1.0
    highest_name = ""
    for number, name in sections:
        rank = section_rank(name)
        if rank < highest_rank:
            label = "a body section" if rank == BODY_SECTION_RANK else f"'{name}'"
            findings.append(Finding(number, "section-order", f"{label} must come before '{highest_name}'. Order: outcome, Links, body, {', '.join(SECTION_ORDER[1:])}."))
        elif rank > highest_rank:
            highest_rank = rank
            highest_name = name
    return findings


def links_region(lines: list[str], sections: list[tuple[int, str]]) -> tuple[int, int] | None:
    """Find the lines that make up the Links block.

    Args:
        lines: Document lines with fenced code blanked out.
        sections: The top-level sections.

    Returns:
        A (start, end) pair of 1-based line numbers, end exclusive, or None when there is no Links block.
    """
    for index, (number, name) in enumerate(sections):
        if name == "Links":
            end = sections[index + 1][0] if index + 1 < len(sections) else len(lines) + 1
            return number, end
    non_empty = [number for number, line in enumerate(lines, start=1) if line.strip()]
    for number in non_empty[:3]:
        if LINKS_LINE.match(lines[number - 1]):
            return number, number + 1
    return None


def check_links(lines: list[str], sections: list[tuple[int, str]]) -> list[Finding]:
    """Check that every PR and ticket URL appears in a Links block under the outcome.

    Args:
        lines: Document lines with fenced code blanked out.
        sections: The top-level sections.

    Returns:
        Findings for a missing or misplaced Links block, URLs outside it, and badly shaped link bullets.
    """
    urls: dict[str, int] = {}
    for number, line in enumerate(lines, start=1):
        for match in list(PR_URL.finditer(line)) + list(TICKET_URL.finditer(line)):
            urls.setdefault(match.group(0), number)
    if not urls:
        return []
    region = links_region(lines, sections)
    if region is None:
        first_line = min(urls.values())
        return [Finding(first_line, "links-block", "PR or ticket links must sit in a '## Links' section (or a 'Links:' line) directly under the outcome.")]
    start, end = region
    findings: list[Finding] = []
    region_text = "\n".join(lines[start - 1:end - 1])
    for url, number in urls.items():
        if url not in region_text:
            findings.append(Finding(number, "links-block", f"{url} is not in the Links block. Put every PR and ticket link there."))
    if lines[start - 1].startswith("## "):
        pr_lines: list[int] = []
        for number in range(start + 1, end):
            line = lines[number - 1]
            if not line.startswith("- "):
                continue
            match = LINK_BULLET.match(line)
            if not match:
                findings.append(Finding(number, "link-bullet", "Write each link as '- <Label>: [<what it is in words>](<url>) (<state>)'."))
                continue
            label = match.group(1)
            if label not in LINK_LABELS:
                findings.append(Finding(number, "link-bullet", f"Unknown link label '{label}'. Use one of: {', '.join(sorted(LINK_LABELS))}."))
            if label == "PR":
                pr_lines.append(number)
            elif PR_URL.search(line):
                findings.append(Finding(number, "link-bullet", "A pull request link gets the 'PR' label."))
        bullet_lines = [number for number in range(start + 1, end) if lines[number - 1].startswith("- ")]
        if pr_lines and bullet_lines[:len(pr_lines)] != pr_lines:
            findings.append(Finding(pr_lines[0], "link-order", "PR lines come first in the Links block."))
    return findings


def split_blocks(lines: list[str]) -> list[tuple[int, str, str, list[tuple[int, str]]]]:
    """Split the document into D, F and Q blocks.

    Args:
        lines: Document lines with fenced code blanked out.

    Returns:
        Tuples of (heading line number, block kind letter, short name, body lines with their numbers).
    """
    blocks: list[tuple[int, str, str, list[tuple[int, str]]]] = []
    current: tuple[int, str, str, list[tuple[int, str]]] | None = None
    for number, line in enumerate(lines, start=1):
        match = BLOCK_HEADING.match(line)
        if match:
            current = (number, match.group(1), match.group(3), [])
            blocks.append(current)
            continue
        if line.startswith("#"):
            current = None
            continue
        if current is not None:
            current[3].append((number, line))
    return blocks


def check_heading_shape(lines: list[str]) -> list[Finding]:
    """Find block headings that do not follow `### <ID>. <Short name>`.

    Args:
        lines: Document lines with fenced code blanked out.

    Returns:
        One finding per malformed D, F or Q heading.
    """
    findings: list[Finding] = []
    for number, line in enumerate(lines, start=1):
        if ANY_BLOCK_HEADING.match(line) and not BLOCK_HEADING.match(line):
            findings.append(Finding(number, "block-heading", "Write the heading as '### <ID>. <Short name>', for example '### D1. Retry limit'."))
    return findings


def check_short_name(number: int, short_name: str) -> list[Finding]:
    """Check that a block's short name is a short noun phrase.

    Args:
        number: The heading's line number.
        short_name: The text after '<ID>. '.

    Returns:
        Findings for a short name that is a question or too long.
    """
    findings: list[Finding] = []
    if short_name.endswith("?"):
        findings.append(Finding(number, "short-name", "The short name is a noun phrase, not the question. Put the question on the next line."))
    word_count = len(short_name.split())
    if word_count > MAX_SHORT_NAME_WORDS or len(short_name) > MAX_SHORT_NAME_CHARACTERS:
        findings.append(Finding(number, "short-name", f"Short name has {word_count} words. Use two to five words."))
    return findings


def check_label_order(number: int, kind_name: str, labels: list[tuple[int, str]], allowed: list[str], required: set[str]) -> list[Finding]:
    """Check that a block's labels are known, required ones are present, and the order is fixed.

    Args:
        number: The heading's line number.
        kind_name: 'Decision', 'Problem' or 'Question', for messages.
        labels: Pairs of (line number, label) in document order.
        allowed: The labels this kind allows, in their fixed order.
        required: The labels this kind must have.

    Returns:
        Findings for unknown, duplicate, missing or out-of-order labels.
    """
    findings: list[Finding] = []
    seen: list[str] = []
    for line_number, label in labels:
        if label not in allowed:
            findings.append(Finding(line_number, "block-label", f"'{label}' is not a {kind_name.lower()} label. Use: {', '.join(allowed)}."))
            continue
        if label in seen:
            findings.append(Finding(line_number, "block-label", f"'{label}' appears twice in this block."))
            continue
        if seen and allowed.index(label) < allowed.index(seen[-1]):
            findings.append(Finding(line_number, "label-order", f"'{label}' must come before '{seen[-1]}'. Order: {', '.join(allowed)}."))
        seen.append(label)
    for label in allowed:
        if label in required and label not in seen:
            findings.append(Finding(number, "block-label", f"{kind_name} block is missing '{label}'."))
    return findings


def check_block(number: int, kind: str, short_name: str, body: list[tuple[int, str]]) -> list[Finding]:
    """Check one D, F or Q block.

    Args:
        number: The heading's line number.
        kind: 'D', 'F' or 'Q'.
        short_name: The text after '<ID>. '.
        body: The block's lines with their numbers.

    Returns:
        Every finding for this block.
    """
    findings = check_short_name(number, short_name)
    labels: list[tuple[int, str]] = []
    for line_number, line in body:
        if BOLD_LABEL.match(line):
            findings.append(Finding(line_number, "bold-label", "Labels are plain text: '- Decision: ...', not '- **Decision**: ...'."))
            continue
        match = TOP_LABEL.match(line)
        if match:
            labels.append((line_number, match.group(1)))
    if kind == "D":
        findings += check_label_order(number, "Decision", labels, DECISION_LABELS, DECISION_REQUIRED)
        if labels and labels[0][1] != "Decision":
            findings.append(Finding(labels[0][0], "label-order", "A decision block starts with '- Decision:'."))
    elif kind == "F":
        findings += check_label_order(number, "Problem", labels, PROBLEM_LABELS, set(PROBLEM_LABELS))
    else:
        findings += check_question(number, body, labels)
    return findings


def check_question(number: int, body: list[tuple[int, str]], labels: list[tuple[int, str]]) -> list[Finding]:
    """Check the question line, labels and options of a Q block.

    Args:
        number: The heading's line number.
        body: The block's lines with their numbers.
        labels: Pairs of (line number, label) in document order.

    Returns:
        Findings for the question line, the labels and the options.
    """
    findings = check_label_order(number, "Question", labels, QUESTION_LABELS, QUESTION_REQUIRED)
    first_text = next(((line_number, line) for line_number, line in body if line.strip()), None)
    if first_text is None or first_text[1].startswith("- ") or not first_text[1].rstrip().endswith("?"):
        line_number = first_text[0] if first_text else number
        findings.append(Finding(line_number, "question-line", "The line after the heading is the question itself, one sentence ending in '?'."))
    options = [(line_number, match.group(1), match.group(2)) for line_number, line in body if (match := OPTION_LINE.match(line))]
    if any(label == "Options" for _, label in labels):
        if len(options) < 2:
            findings.append(Finding(number, "options", "Give at least two lettered options under '- Options:', as '  - A. <choice>: <consequence>'."))
        else:
            if "(Recommended)" not in options[0][2]:
                findings.append(Finding(options[0][0], "options", "Put the recommended option first and mark it '(Recommended)'."))
            if not options[-1][2].startswith("Other"):
                findings.append(Finding(options[-1][0], "options", "End the options with 'Other'."))
    return findings


def check_bare_references(lines: list[str]) -> list[Finding]:
    """Find ticket keys and PR numbers that have neither a link nor a description.

    Args:
        lines: Document lines with fenced code blanked out.

    Returns:
        One finding per bare reference.
    """
    findings: list[Finding] = []
    for number, line in enumerate(lines, start=1):
        if line.startswith("#"):
            line = line.lstrip("#")
        visible = BARE_URL.sub(" ", INLINE_CODE.sub(" ", MARKDOWN_LINK.sub(" ", line)))
        for match in TICKET_KEY.finditer(visible):
            if match.group(1) not in NOT_TICKET_PREFIXES:
                findings.append(Finding(number, "bare-reference", f"{match.group(0)} needs a link or a description in brackets, for example '{match.group(0)} (what it is)'."))
        for match in PR_NUMBER.finditer(visible):
            findings.append(Finding(number, "bare-reference", f"{match.group(0)} needs a link or a description in brackets."))
    return findings


def check_text(text: str, blocks_only: bool) -> list[Finding]:
    """Run every check on one document.

    Args:
        text: The markdown text.
        blocks_only: When True, check only the D, F and Q blocks and bare references.

    Returns:
        All findings, sorted by line.
    """
    lines = strip_fenced_code(text.splitlines())
    findings: list[Finding] = []
    if not blocks_only:
        sections = find_sections(lines)
        findings += check_outcome(lines)
        findings += check_section_order(sections)
        findings += check_links(lines, sections)
    findings += check_heading_shape(lines)
    for number, kind, short_name, body in split_blocks(lines):
        findings += check_block(number, kind, short_name, body)
    findings += check_bare_references(lines)
    return sorted(findings, key=lambda finding: (finding.line, finding.rule))


def main() -> None:
    """Parse the command line, check each input, print findings, and set the exit code."""
    parser = argparse.ArgumentParser(description="Check markdown against the response-format standard.")
    parser.add_argument("files", nargs="*", type=Path, help="files to check; standard input when none")
    parser.add_argument("--blocks-only", action="store_true", help="check only the D, F and Q blocks")
    arguments = parser.parse_args()
    inputs: list[tuple[str, str]] = []
    if arguments.files:
        for path in arguments.files:
            inputs.append((str(path), path.read_text(encoding="utf-8")))
    else:
        inputs.append(("<stdin>", sys.stdin.read()))
    total = 0
    for name, text in inputs:
        for finding in check_text(text, arguments.blocks_only):
            print(f"{name}:{finding.line}: {finding.rule}: {finding.message}")
            total += 1
    print(f"{total} finding(s)")
    sys.exit(1 if total else 0)


if __name__ == "__main__":
    main()
