"""Tests that the preferences, the OpenSpec rules and the question-format skill agree with each other.

The question-format skill restates two lists that live elsewhere: the order of authority
(openspec-rules/preferences.md) and the kinds of decision that need the user's yes
(openspec-rules/rules.md, section 1). The rules name preference P11 by its label. These tests
fail when one copy changes and the other does not, or when a file names a preference that
does not exist.

Run from the repository root: python -m unittest discover -s tests -p test_openspec_preferences.py
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREFERENCES_FILE = ROOT / "openspec-rules" / "preferences.md"
RULES_FILE = ROOT / "openspec-rules" / "rules.md"
QUESTION_FORMAT_FILE = ROOT / "skills" / "question-format" / "SKILL.md"

PREFERENCE_HEADING = re.compile(r"^### P(\d+)\. (.+)$", re.MULTILINE)
PREFERENCE_MENTION = re.compile(r"\bP(\d+)\b")
NUMBERED_ITEM = re.compile(r"^(\d+)\. ", re.MULTILINE)
UNUSED_PREFERENCE_IDS = frozenset({12})
# One phrase per position that both copies of each list must hold at that position.
ORDER_OF_AUTHORITY_PHRASES: tuple[str, ...] = (
    "what the user said", "the project", "claude.md", "the preferences", "cheapest to reverse",
)
NEEDS_YOUR_YES_PHRASES: tuple[str, ...] = (
    "ddl", "deleting or overwriting", "publish", "new recurring cost", "breaking change", "permissions",
)


def read_text(path: Path) -> str:
    """Read a repository file as UTF-8 text.

    Args:
        path: The file to read.

    Returns:
        Its text.
    """
    return path.read_text(encoding="utf-8")


def section(text: str, heading: str) -> str:
    """Return the body of a markdown section, from its heading to the next heading of the same or a higher level.

    Args:
        text: The markdown text.
        heading: The full heading line, such as "## Order of authority".

    Returns:
        The section body, without its heading.

    Raises:
        AssertionError: When the heading is not in the text.
    """
    start = text.find(heading + "\n")
    assert start >= 0, f"heading {heading!r} not found"
    level = heading.split(" ", 1)[0]
    body_start = start + len(heading) + 1
    next_heading = re.search(rf"^#{{1,{len(level)}}} ", text[body_start:], re.MULTILINE)
    return text[body_start:body_start + next_heading.start()] if next_heading else text[body_start:]


def numbered_items(text: str) -> list[str]:
    """Split a markdown numbered list into its items, joining wrapped lines.

    Args:
        text: Text that holds a list whose items start with "1. ", "2. " and so on.

    Returns:
        The item texts, in order, lowercased and with whitespace collapsed.
    """
    starts = [match.start() for match in NUMBERED_ITEM.finditer(text)]
    items = []
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(text)
        item = text[start:end].split("\n\n", 1)[0]
        items.append(" ".join(NUMBERED_ITEM.sub("", item, count=1).split()).lower())
    return items


def defined_preferences() -> dict[int, str]:
    """Return every preference heading in preferences.md.

    Returns:
        Preference number -> label, such as 11 -> "Plan in the repo that owns the code".
    """
    return {int(number): label for number, label in PREFERENCE_HEADING.findall(read_text(PREFERENCES_FILE))}


class PreferenceIdentifiers(unittest.TestCase):

    def test_preference_numbers_are_unique_and_in_order(self):
        numbers = [int(number) for number, _ in PREFERENCE_HEADING.findall(read_text(PREFERENCES_FILE))]
        self.assertEqual(len(numbers), len(set(numbers)))
        self.assertEqual(numbers, sorted(numbers))
        self.assertEqual(set(range(1, max(numbers) + 1)) - set(numbers), set(UNUSED_PREFERENCE_IDS))

    def test_the_unused_number_is_never_defined_and_says_so(self):
        preferences_text = read_text(PREFERENCES_FILE)
        for number in UNUSED_PREFERENCE_IDS:
            self.assertNotIn(number, defined_preferences())
            self.assertIn(f"P{number} is not used.", preferences_text)

    def test_every_mentioned_preference_is_defined(self):
        defined = set(defined_preferences())
        for path in (PREFERENCES_FILE, RULES_FILE, QUESTION_FORMAT_FILE):
            mentioned = {int(number) for number in PREFERENCE_MENTION.findall(read_text(path))}
            self.assertEqual(sorted(mentioned - defined - UNUSED_PREFERENCE_IDS), [], f"{path.name} names an undefined preference")

    def test_the_rules_name_p11_by_its_label(self):
        label = defined_preferences()[11]
        self.assertEqual(label, "Plan in the repo that owns the code")
        self.assertIn(f"P11 ({label})", read_text(RULES_FILE))

    def test_the_skill_names_a_preference_by_its_label(self):
        skill_text = read_text(QUESTION_FORMAT_FILE)
        for number, label in re.findall(r"`P(\d+) ([^`]+)`", skill_text):
            self.assertEqual(defined_preferences()[int(number)], label)


class RestatedLists(unittest.TestCase):

    def test_the_skill_restates_the_order_of_authority(self):
        source = numbered_items(section(read_text(PREFERENCES_FILE), "## Order of authority"))
        copy = numbered_items(section(read_text(QUESTION_FORMAT_FILE), "## Before you ask: settle it yourself when you can"))
        self.assertEqual(len(source), len(ORDER_OF_AUTHORITY_PHRASES))
        self.assertEqual(len(copy), len(ORDER_OF_AUTHORITY_PHRASES))
        for position, phrase in enumerate(ORDER_OF_AUTHORITY_PHRASES):
            self.assertIn(phrase, source[position])
            self.assertIn(phrase, copy[position])

    def test_the_skill_restates_the_needs_your_yes_list(self):
        rules_section = section(read_text(RULES_FILE), "### Decisions that need the user's yes")
        source = [" ".join(item.split()).lower()
                  for item in re.findall(r"^- (.+?)(?=^- |\Z)", rules_section, re.MULTILINE | re.DOTALL)]
        skill_section = section(read_text(QUESTION_FORMAT_FILE), "## Before you ask: settle it yourself when you can")
        restated = re.search(r'"Needs your yes" kinds in the OpenSpec `rules.md`: (.+?)\.\n', skill_section)
        self.assertIsNotNone(restated, "the skill no longer restates the Needs-your-yes kinds")
        copy = [item.strip().lower() for item in restated.group(1).split(";")]
        self.assertEqual(len(source), len(NEEDS_YOUR_YES_PHRASES))
        self.assertEqual(len(copy), len(NEEDS_YOUR_YES_PHRASES))
        for position, phrase in enumerate(NEEDS_YOUR_YES_PHRASES):
            self.assertIn(phrase, source[position])
            self.assertIn(phrase, copy[position])


if __name__ == "__main__":
    unittest.main()
