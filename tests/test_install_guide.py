"""The install guide: every file it embeds matches its source here, and its parts, steps and checks run in order.

Run from the repository root: python -m unittest discover -s tests -p test_install_guide.py
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUIDE = ROOT / "docs" / "claude-session-tools-and-review-install.md"

# Install path named in the guide -> the source file in this repository.
EMBEDDED_SOURCES: dict[str, str] = {
    "<SKILLS_DIR>/pr-review-loop/SKILL.md": "skills/pr-review-loop/SKILL.md",
    "<SKILLS_DIR>/pr-review-loop/reference/review-procedure.md": "skills/pr-review-loop/reference/review-procedure.md",
    "<SKILLS_DIR>/pr-review-loop/reference/review-checks.md": "skills/pr-review-loop/reference/review-checks.md",
    "<SKILLS_DIR>/pr-review-loop/reference/review-comment.md": "skills/pr-review-loop/reference/review-comment.md",
    "<SKILLS_DIR>/pr-review-loop/reference/fix-playbook.md": "skills/pr-review-loop/reference/fix-playbook.md",
    "<CLAUDE_DIR>/skills/merge-session/session_merge.py": "sessionmerge/session_merge.py",
    "<CLAUDE_DIR>/skills/merge-session/SKILL.md": "sessionmerge/skill/merge-session/SKILL.md",
    "<SKILLS_DIR>/response-format/SKILL.md": "skills/response-format/SKILL.md",
    "<SKILLS_DIR>/response-format/scripts/check_format.py": "skills/response-format/scripts/check_format.py",
    "<SKILLS_DIR>/question-format/SKILL.md": "skills/question-format/SKILL.md",
    "<RULES_DIR>/rules.md": "openspec-rules/rules.md",
    "<RULES_DIR>/preferences.md": "openspec-rules/preferences.md",
    "<RULES_DIR>/apply_openspec_rules.py": "openspec-rules/apply_openspec_rules.py",
    "<CLAUDE_DIR>/runguard/runguard_common.py": "runguard/runguard_common.py",
    "<CLAUDE_DIR>/runguard/run_bounded.py": "runguard/run_bounded.py",
    "<CLAUDE_DIR>/runguard/ledger.py": "runguard/ledger.py",
    "<CLAUDE_DIR>/runguard/preflight_gate.py": "runguard/preflight_gate.py",
    "<CLAUDE_DIR>/runguard/safe_db.py": "runguard/safe_db.py",
    "<CLAUDE_DIR>/runguard/config.json": "runguard/config.json",
    "<SKILLS_DIR>/script-preflight/SKILL.md": "runguard/skill/script-preflight/SKILL.md",
}
# Install paths under these prefixes must have a source listed above.
SOURCED_PREFIXES: tuple[str, ...] = (
    "<SKILLS_DIR>/pr-review-loop/", "<CLAUDE_DIR>/skills/merge-session/", "<SKILLS_DIR>/response-format/",
    "<SKILLS_DIR>/question-format/", "<RULES_DIR>/", "<CLAUDE_DIR>/runguard/", "<SKILLS_DIR>/script-preflight/",
)
EXPECTED_PARTS: list[str] = list("ABCDEFGHI")
# Two ways the guide introduces an embedded file: "Create `<path>` with exactly this content:" for a single
# file, and a line holding only "`<path>`:" for each file of a set, as in the run guard's step.
EMBED_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"`(?P<target>[^`]+)` with exactly this content[^\n]*:\n\n(?P<fence>````+)[a-z]*\n"),
    re.compile(r"^`(?P<target>[^`]+)`:\n\n(?P<fence>````+)[a-z]*\n", re.M),
)


def read_text(path: Path) -> str:
    """Read a UTF-8 file with line endings normalized to LF, as git stores these files.

    Args:
        path: The file to read.

    Returns:
        The text.
    """
    return path.read_bytes().decode("utf-8").replace("\r\n", "\n")


def embedded_files(guide: str) -> dict[str, str]:
    """Return every file the guide embeds, keyed by the install path it names.

    Args:
        guide: The guide text.

    Returns:
        A mapping from install path to the embedded file text.
    """
    files: dict[str, str] = {}
    for pattern in EMBED_PATTERNS:
        for match in pattern.finditer(guide):
            closing = "\n" + match.group("fence") + "\n"
            end = guide.index(closing, match.end() - 1)
            files[match.group("target")] = guide[match.end():end + 1]
    return files


def numbers(pattern: str, text: str) -> list[int]:
    """Return every number a multiline pattern captures, in document order.

    Args:
        pattern: A regex whose group 1 is a number.
        text: The text to search.

    Returns:
        The numbers.
    """
    return [int(found) for found in re.findall(pattern, text, re.M)]


class EmbeddedFilesTests(unittest.TestCase):
    """The guide promises byte-for-byte copies of the files it installs."""

    @classmethod
    def setUpClass(cls) -> None:
        """Read the guide once."""
        cls.guide = read_text(GUIDE)
        cls.embedded = embedded_files(cls.guide)

    def test_every_source_is_embedded_verbatim(self) -> None:
        """Happy path: each listed source matches its embedded copy exactly."""
        for target, source in EMBEDDED_SOURCES.items():
            with self.subTest(target=target):
                self.assertIn(target, self.embedded, f"the guide does not embed {target}")
                self.assertEqual(self.embedded[target], read_text(ROOT / source), f"{target} differs from {source}")

    def test_every_sourced_install_path_is_listed(self) -> None:
        """Edge case: a new embedded file under a sourced folder must get a source entry here."""
        unlisted = [target for target in self.embedded
                    if target.startswith(SOURCED_PREFIXES) and target not in EMBEDDED_SOURCES]
        self.assertEqual(unlisted, [])

    def test_embedded_files_extraction_finds_files(self) -> None:
        """Error guard: the extraction pattern still matches the guide's install lines."""
        self.assertGreaterEqual(len(self.embedded), len(EMBEDDED_SOURCES))


class StructureTests(unittest.TestCase):
    """Parts, steps and checks are numbered in order, so cross-references stay right."""

    @classmethod
    def setUpClass(cls) -> None:
        """Split the guide into its Verify and Uninstall sections."""
        cls.guide = read_text(GUIDE)
        cls.verify = cls.guide[cls.guide.index("## Verify"):cls.guide.index("## Uninstall")]
        cls.uninstall = cls.guide[cls.guide.index("## Uninstall"):]

    def test_parts_are_in_order(self) -> None:
        """Parts run A to I with no gap."""
        self.assertEqual(re.findall(r"^# Part ([A-Z]) — ", self.guide, re.M), EXPECTED_PARTS)

    def test_steps_are_numbered_in_order(self) -> None:
        """Steps run 1, 2, 3 and so on with no gap."""
        steps = numbers(r"^## Step (\d+):", self.guide)
        self.assertEqual(steps, list(range(1, len(steps) + 1)))

    def test_terminal_checks_are_numbered_in_order(self) -> None:
        """The terminal checks in Verify run 1, 2, 3 and so on, grouped by part in order."""
        checks = numbers(r"^# (\d+)\. ", self.verify)
        self.assertEqual(checks, list(range(1, len(checks) + 1)))
        self.assertEqual(re.findall(r"^# --- Part ([A-Z]) ---", self.verify, re.M), EXPECTED_PARTS)

    def test_in_session_checks_are_numbered_in_order(self) -> None:
        """The in-session checks run 1, 2, 3 and so on."""
        session = self.verify[self.verify.index("Then in a **new** Claude Code session"):]
        checks = numbers(r"^(\d+)\. ", session)
        self.assertEqual(checks, list(range(1, len(checks) + 1)))

    def test_uninstall_covers_every_part_in_order(self) -> None:
        """Uninstall has one entry per part, A to I."""
        self.assertEqual(re.findall(r"^\*\*Part ([A-Z])\.\*\*", self.uninstall, re.M), EXPECTED_PARTS)

    def test_no_reference_to_a_missing_part(self) -> None:
        """Error case: text never names a part the guide does not have."""
        named = set(re.findall(r"\bPart ([A-Z])\b", self.guide))
        self.assertEqual(named - set(EXPECTED_PARTS), set())


if __name__ == "__main__":
    unittest.main()
