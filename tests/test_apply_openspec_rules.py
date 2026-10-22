"""Tests for openspec-rules/apply_openspec_rules.py.

Run from the repository root: python -m unittest discover -s tests -p test_apply_openspec_rules.py
"""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "openspec-rules"))

import apply_openspec_rules as patcher  # noqa: E402

INSTALLED_FILES_PRESENT = all(path.is_file() for path in patcher.build_targets(Path.home()))


def build_fixture_text(edits: list[patcher.TextEdit]) -> str:
    """Build a file body that contains every anchor of the given edits once.

    Args:
        edits: The edits whose anchors the body must contain.

    Returns:
        A markdown-like body with front matter and each anchor on its own block.
    """
    body = "---\nname: fixture\n---\n\n"
    for edit in edits:
        body += edit.anchor + "\n\nfiller text\n\n"
    return body


def write_fixture_home(home: Path) -> None:
    """Create the six OpenSpec target files under a temporary home folder.

    Args:
        home: The temporary folder that stands in for the user's home folder.
    """
    for path, edits in patcher.build_targets(home).items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(build_fixture_text(edits), encoding="utf-8", newline="")


def read_all(home: Path) -> dict[Path, str]:
    """Read every target file under a home folder.

    Args:
        home: The folder that holds `.claude`.

    Returns:
        A mapping from file path to its text.
    """
    return {path: path.read_text(encoding="utf-8") for path in patcher.build_targets(home)}


class RulesPathTests(unittest.TestCase):
    """The steps the script adds point at the rules.md next to it, wherever it is installed."""

    def test_rules_path_is_next_to_the_script(self) -> None:
        """RULES_PATH is resolved from the script's own folder, not written into it."""
        self.assertEqual(Path(patcher.RULES_PATH), (ROOT / "openspec-rules" / "rules.md").resolve())


class PlanEditsTests(unittest.TestCase):
    """Unit tests for plan_edits on in-memory text."""

    def test_applies_every_edit_once(self) -> None:
        """Happy path: every anchor is replaced and every replacement is present."""
        text = build_fixture_text(patcher.PROPOSE_EDITS)
        result = patcher.plan_edits(Path("propose.md"), text, patcher.PROPOSE_EDITS)
        self.assertEqual(len(result.applied), len(patcher.PROPOSE_EDITS))
        self.assertEqual(result.skipped, [])
        for edit in patcher.PROPOSE_EDITS:
            self.assertEqual(result.new_text.count(edit.replacement), 1, edit.name)
        self.assertIn(patcher.RULES_PATH, result.new_text)

    def test_second_run_changes_nothing(self) -> None:
        """Edge case: a patched file is skipped edit by edit and its text stays the same."""
        text = build_fixture_text(patcher.APPLY_EDITS)
        first = patcher.plan_edits(Path("apply.md"), text, patcher.APPLY_EDITS)
        second = patcher.plan_edits(Path("apply.md"), first.new_text, patcher.APPLY_EDITS)
        self.assertEqual(second.applied, [])
        self.assertEqual(len(second.skipped), len(patcher.APPLY_EDITS))
        self.assertEqual(second.new_text, first.new_text)

    def test_previous_replacement_is_upgraded(self) -> None:
        """Edge case: a file patched with an older block text is upgraded to the current text."""
        upgradable = [edit for edit in patcher.PROPOSE_EDITS if edit.previous_replacements]
        self.assertTrue(upgradable, "expected at least one edit with an older replacement")
        edit = upgradable[0]
        text = "---\nname: fixture\n---\n\n" + edit.previous_replacements[0] + "\nfiller\n"
        result = patcher.plan_edits(Path("propose.md"), text, [edit])
        self.assertEqual(result.applied, [edit.name])
        self.assertIn(edit.replacement, result.new_text)
        self.assertNotIn(edit.previous_replacements[0], result.new_text)

    def test_missing_anchor_raises(self) -> None:
        """Error case: an anchor that is not in the file raises AnchorError with the edit name."""
        text = build_fixture_text(patcher.UPDATE_EDITS).replace(patcher.UPDATE_EDITS[0].anchor, "")
        with self.assertRaises(patcher.AnchorError) as raised:
            patcher.plan_edits(Path("update.md"), text, patcher.UPDATE_EDITS)
        self.assertIn(patcher.UPDATE_EDITS[0].name, str(raised.exception))
        self.assertIn("found 0", str(raised.exception))

    def test_duplicate_anchor_raises(self) -> None:
        """Error case: an anchor that appears twice raises instead of patching both places."""
        text = build_fixture_text(patcher.APPLY_EDITS) + patcher.APPLY_EDITS[0].anchor
        with self.assertRaises(patcher.AnchorError) as raised:
            patcher.plan_edits(Path("apply.md"), text, patcher.APPLY_EDITS)
        self.assertIn("found 2", str(raised.exception))

    def test_windows_line_endings_raise(self) -> None:
        """Edge case: a file saved with CRLF does not match the LF anchors and fails loudly."""
        text = build_fixture_text(patcher.UPDATE_EDITS).replace("\n", "\r\n")
        with self.assertRaises(patcher.AnchorError):
            patcher.plan_edits(Path("update.md"), text, patcher.UPDATE_EDITS)


class ApplyRulesTests(unittest.TestCase):
    """Tests for apply_rules against files on disk under a temporary home folder."""

    def setUp(self) -> None:
        """Create an empty temporary home folder."""
        self.home = Path(tempfile.mkdtemp(prefix="openspec_rules_test_"))

    def tearDown(self) -> None:
        """Delete the temporary home folder."""
        shutil.rmtree(self.home)

    def test_patches_all_six_files(self) -> None:
        """Happy path: all six files are patched and each points at rules.md."""
        write_fixture_home(self.home)
        results = patcher.apply_rules(self.home, dry_run=False)
        self.assertEqual(len(results), 6)
        for path, text in read_all(self.home).items():
            self.assertIn(patcher.RULES_PATH, text, str(path))
            self.assertTrue(text.startswith("---\n"), str(path))

    def test_dry_run_writes_nothing(self) -> None:
        """Edge case: a dry run reports the edits but leaves every file unchanged."""
        write_fixture_home(self.home)
        before = read_all(self.home)
        results = patcher.apply_rules(self.home, dry_run=True)
        self.assertTrue(all(result.applied for result in results))
        self.assertEqual(read_all(self.home), before)

    def test_one_bad_file_blocks_every_write(self) -> None:
        """Error case: when one file lacks an anchor, no file is written."""
        write_fixture_home(self.home)
        broken = self.home / ".claude" / "commands" / "opsx" / "update.md"
        broken.write_text("---\nname: broken\n---\n", encoding="utf-8", newline="")
        before = read_all(self.home)
        with self.assertRaises(patcher.AnchorError):
            patcher.apply_rules(self.home, dry_run=False)
        self.assertEqual(read_all(self.home), before)

    def test_missing_file_raises(self) -> None:
        """Error case: a target file that does not exist raises FileNotFoundError."""
        write_fixture_home(self.home)
        (self.home / ".claude" / "skills" / "openspec-apply-change" / "SKILL.md").unlink()
        with self.assertRaises(FileNotFoundError):
            patcher.apply_rules(self.home, dry_run=False)

    @unittest.skipUnless(INSTALLED_FILES_PRESENT, "OpenSpec's skills and /opsx commands are not installed under ~/.claude")
    def test_installed_files_patch_cleanly_and_idempotently(self) -> None:
        """Copies of the real installed files patch without error, and a rerun changes nothing."""
        for real_path in patcher.build_targets(Path.home()):
            copy_path = self.home / real_path.relative_to(Path.home())
            copy_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(real_path, copy_path)
        patcher.apply_rules(self.home, dry_run=False)
        rerun = patcher.apply_rules(self.home, dry_run=False)
        self.assertTrue(all(result.applied == [] for result in rerun))
        for path, text in read_all(self.home).items():
            self.assertIn(patcher.RULES_PATH, text, str(path))
            self.assertTrue(text.startswith("---"), str(path))


if __name__ == "__main__":
    unittest.main()
