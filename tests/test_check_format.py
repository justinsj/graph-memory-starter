"""Tests for skills/response-format/scripts/check_format.py.

Run from the repository root: python -m unittest discover -s tests -p test_check_format.py
"""

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "response-format" / "scripts" / "check_format.py"
sys.path.insert(0, str(SCRIPT.parent))

import check_format  # noqa: E402

GOOD_RESPONSE = """The export now has a `--dry-run` flag, and all 12 tests pass.

## Links

- PR: [toy-export#7 Add export dry run](https://github.com/example-org/toy-export/pull/7) (open, feat/dry-run → main)
- Ticket: [TICKET-34 Export preview](https://example.atlassian.net/browse/TICKET-34) (In Progress)

## What changed

The script prints the rows it would write.

### F1. Mistyped flag writes

- Symptom: A mistyped `--dryrun` ran a real export.
- Example: `python scripts/export.py --dryrun` wrote `exports/2026-10-22.csv`.
- Root cause: The script ignored unknown arguments.
- Fix: Parse arguments with `argparse` and reject unknown ones.

## Tests

- `pytest tests` ran 12 tests, all passed.

## Decisions

### D1. Unknown CLI arguments

- Decision: The script rejects an unknown argument with exit code 2.
- Reason: A typo must not write a file.
- Source: P4 Fail loudly
- Needs your yes: yes, because outside jobs may pass extra arguments.

### D2. Retry limit

- Decision: The upload retries 3 times, then fails the run.
- Reason: The partner API recovers within a minute in the logs.

## Not done

- No test on Windows paths.

## Files

- [export.py](C:/repo/scripts/export.py)

## Next step

Merge after review.

## Questions for you

### Q1. Backfill scope

Should the backfill include customers who closed their accounts before September?

- Context: 37 of 178 customers closed their accounts before 2026-09-01.
- Example: Acme Widgets has 2 days of August revenue.
- Options:
  - A. Exclude them (Recommended): cleaner averages.
  - B. Include them: partial months distort the median.
  - C. Other: describe it in your reply.
- Reply with: `Q1: A`
"""


def rules_for(text: str, blocks_only: bool = False) -> list[str]:
    """Return the rule ids of every finding for a text.

    Args:
        text: The markdown to check.
        blocks_only: Passed through to check_text.

    Returns:
        The rule ids, in line order.
    """
    return [finding.rule for finding in check_format.check_text(text, blocks_only)]


class GoodInputTests(unittest.TestCase):
    """Happy path: compliant documents produce no findings."""

    def test_full_response_is_clean(self) -> None:
        """A response with every part in order has no findings."""
        self.assertEqual(rules_for(GOOD_RESPONSE), [])

    def test_short_response_with_links_line(self) -> None:
        """A short response may put its links on a 'Links:' line under the outcome."""
        text = "The fix is merged.\nLinks: PR [toy-export#7 Add export dry run](https://github.com/example-org/toy-export/pull/7) (merged)\n"
        self.assertEqual(rules_for(text), [])

    def test_response_without_links_needs_no_links_block(self) -> None:
        """Edge case: a response with no PR or ticket URL needs no Links block."""
        self.assertEqual(rules_for("Done. Nothing else changed.\n"), [])

    def test_blocks_only_ignores_layout(self) -> None:
        """Edge case: --blocks-only skips the outcome and section rules for files with their own layout."""
        text = "# Decisions: add-export-dry-run\n\n## Decisions\n\n### D1. Retry limit\n\n- Decision: Retry 3 times.\n- Reason: The API recovers.\n"
        self.assertEqual(rules_for(text, blocks_only=True), [])

    def test_code_fences_are_ignored(self) -> None:
        """Edge case: blocks and references inside fenced code are examples, not content."""
        text = "Example below.\n\n```markdown\n### D1. Should we retry?\n- **Decision**: yes\nSee #12 and TICKET-99\n```\n"
        self.assertEqual(rules_for(text), [])


class LayoutRuleTests(unittest.TestCase):
    """Error cases for the outcome, section order and links rules."""

    def test_heading_first_fails(self) -> None:
        """The outcome must come before any heading."""
        self.assertIn("outcome-first", rules_for("## Summary\n\nDone.\n"))

    def test_sections_out_of_order_fail(self) -> None:
        """'Files' before 'Decisions' breaks the fixed order."""
        text = "Done.\n\n## Files\n\n- [a](C:/a.md)\n\n## Decisions\n\n### D1. Retry limit\n\n- Decision: 3.\n- Reason: logs.\n"
        self.assertIn("section-order", rules_for(text))

    def test_links_after_body_fail(self) -> None:
        """A Links section after a body section breaks the order."""
        text = "Done.\n\n## What changed\n\nStuff.\n\n## Links\n\n- PR: [r#1 T](https://github.com/o/r/pull/1) (open)\n"
        self.assertIn("section-order", rules_for(text))

    def test_pr_url_without_links_block_fails(self) -> None:
        """A PR URL anywhere needs a Links block."""
        text = "Opened [the PR](https://github.com/o/r/pull/1) for the fix.\n"
        self.assertIn("links-block", rules_for(text))

    def test_pr_url_outside_links_block_fails(self) -> None:
        """A second PR mentioned only in the body must also be in the Links block."""
        text = (
            "Done.\n\n## Links\n\n- PR: [r#1 T](https://github.com/o/r/pull/1) (open)\n\n"
            "## Findings\n\nSee [r#2 Other](https://github.com/o/r/pull/2) too.\n"
        )
        self.assertIn("links-block", rules_for(text))

    def test_pr_not_first_in_links_fails(self) -> None:
        """PR lines come before ticket lines."""
        text = (
            "Done.\n\n## Links\n\n- Ticket: [TICKET-1 T](https://e.atlassian.net/browse/TICKET-1) (Done)\n"
            "- PR: [r#1 T](https://github.com/o/r/pull/1) (open)\n"
        )
        self.assertIn("link-order", rules_for(text))

    def test_review_comment_link_is_not_a_pr(self) -> None:
        """Edge case: a link to a comment inside a PR keeps its own label."""
        text = (
            "Done.\n\n## Links\n\n- PR: [r#1 T](https://github.com/o/r/pull/1) (open)\n"
            "- Review comment: [Review of abc123](https://github.com/o/r/pull/1#issuecomment-9)\n"
        )
        self.assertEqual(rules_for(text), [])

    def test_link_bullet_shape_fails(self) -> None:
        """A link bullet without a label fails."""
        text = "Done.\n\n## Links\n\n- https://github.com/o/r/pull/1\n"
        self.assertIn("link-bullet", rules_for(text))


class BlockRuleTests(unittest.TestCase):
    """Error cases for D, F and Q blocks."""

    def test_short_name_as_question_fails(self) -> None:
        """A short name ending in '?' is the question, not a name."""
        text = "### D1. Should we retry?\n\n- Decision: yes.\n- Reason: logs.\n"
        self.assertIn("short-name", rules_for(text, blocks_only=True))

    def test_long_short_name_fails(self) -> None:
        """A short name of more than six words fails."""
        text = "### D1. What the export script does with an unknown argument\n\n- Decision: reject.\n- Reason: typos.\n"
        self.assertIn("short-name", rules_for(text, blocks_only=True))

    def test_heading_without_short_name_shape_fails(self) -> None:
        """A heading like '### D1 Retry' (no period) is malformed."""
        self.assertIn("block-heading", rules_for("### D1 Retry limit\n", blocks_only=True))

    def test_decision_label_order_fails(self) -> None:
        """'Reason' before 'Decision' breaks the order and the first-label rule."""
        text = "### D1. Retry limit\n\n- Reason: logs.\n- Decision: 3 retries.\n"
        rules = rules_for(text, blocks_only=True)
        self.assertIn("label-order", rules)

    def test_decision_missing_reason_fails(self) -> None:
        """A decision block needs a Reason."""
        text = "### D1. Retry limit\n\n- Decision: 3 retries.\n"
        self.assertIn("block-label", rules_for(text, blocks_only=True))

    def test_unknown_label_fails(self) -> None:
        """A label outside the list, such as the old 'Answer', fails."""
        text = "### D1. Retry limit\n\n- Decision: 3.\n- Answer: 3.\n- Reason: logs.\n"
        self.assertIn("block-label", rules_for(text, blocks_only=True))

    def test_bold_label_fails(self) -> None:
        """Labels are plain text."""
        text = "### D1. Retry limit\n\n- **Decision**: 3.\n- Reason: logs.\n"
        self.assertIn("bold-label", rules_for(text, blocks_only=True))

    def test_problem_missing_root_cause_fails(self) -> None:
        """A problem block needs all four labels."""
        text = "### F1. Lines dropped\n\n- Symptom: low total.\n- Example: 412 vs 419.\n- Fix: inclusive range.\n"
        self.assertIn("block-label", rules_for(text, blocks_only=True))

    def test_question_without_question_line_fails(self) -> None:
        """The line after a Q heading must be the question."""
        text = "### Q1. Backfill scope\n\n- Context: c.\n- Example: e.\n- Options:\n  - A. X (Recommended): x.\n  - B. Other: y.\n"
        self.assertIn("question-line", rules_for(text, blocks_only=True))

    def test_question_without_recommended_first_fails(self) -> None:
        """The first option carries '(Recommended)'."""
        text = "### Q1. Backfill scope\n\nInclude them?\n\n- Context: c.\n- Example: e.\n- Options:\n  - A. X: x.\n  - B. Other: y.\n"
        self.assertIn("options", rules_for(text, blocks_only=True))

    def test_question_without_other_last_fails(self) -> None:
        """The last option is 'Other'."""
        text = "### Q1. Backfill scope\n\nInclude them?\n\n- Context: c.\n- Example: e.\n- Options:\n  - A. X (Recommended): x.\n  - B. Y: y.\n"
        self.assertIn("options", rules_for(text, blocks_only=True))


    def test_question_with_recorded_in_label_passes(self) -> None:
        """Edge case: a question kept in a decisions file ends with a Recorded in label."""
        text = ("### Q1. Backfill scope\n\nInclude them?\n\n- Context: c.\n- Example: e.\n- Options:\n"
                "  - A. X (Recommended): x.\n  - B. Other: y.\n- Reply with: `Q1: A`\n"
                "- Recorded in: `docs/decisions/2026-10-22-backfill-scope.md`\n")
        self.assertEqual(rules_for(text, blocks_only=True), [])

    def test_recorded_in_before_options_fails(self) -> None:
        """Error case: Recorded in is the last label."""
        text = ("### Q1. Backfill scope\n\nInclude them?\n\n- Context: c.\n- Example: e.\n- Recorded in: `a.md`\n"
                "- Options:\n  - A. X (Recommended): x.\n  - B. Other: y.\n")
        self.assertIn("label-order", rules_for(text, blocks_only=True))


class ReferenceRuleTests(unittest.TestCase):
    """Bare ticket and PR references."""

    def test_bare_ticket_fails(self) -> None:
        """'TICKET-12' alone fails."""
        self.assertIn("bare-reference", rules_for("Done for TICKET-12.\n"))

    def test_bare_pr_number_fails(self) -> None:
        """'#132' alone fails."""
        self.assertIn("bare-reference", rules_for("Merged #132 today.\n"))

    def test_described_reference_passes(self) -> None:
        """A key followed by a description in brackets passes."""
        self.assertEqual(rules_for("Done for TICKET-12 (invoice completeness).\n"), [])

    def test_reference_in_link_or_code_passes(self) -> None:
        """References inside link text or inline code pass."""
        text = "Done.\n\n## Links\n\n- Ticket: [TICKET-12 Invoice completeness](https://e.atlassian.net/browse/TICKET-12) (Done)\n\nRan `git log #12`.\n"
        self.assertEqual(rules_for(text), [])

    def test_non_ticket_prefixes_pass(self) -> None:
        """UTF-8 and SHA-256 are not tickets."""
        self.assertEqual(rules_for("Files are UTF-8 and hashed with SHA-256.\n"), [])


class CommandLineTests(unittest.TestCase):
    """The script as a command."""

    def test_stdin_clean_exits_zero(self) -> None:
        """A clean document on standard input exits 0."""
        result = subprocess.run([sys.executable, str(SCRIPT)], input=GOOD_RESPONSE, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("0 finding(s)", result.stdout)

    def test_findings_exit_one(self) -> None:
        """A document with findings exits 1 and names the rule."""
        result = subprocess.run([sys.executable, str(SCRIPT)], input="## Heading first\n", capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 1)
        self.assertIn("outcome-first", result.stdout)

    def test_missing_file_errors(self) -> None:
        """Error case: a missing file raises instead of passing silently."""
        result = subprocess.run([sys.executable, str(SCRIPT), "no_such_file.md"], capture_output=True, text=True, encoding="utf-8")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("FileNotFoundError", result.stderr)


if __name__ == "__main__":
    unittest.main()
