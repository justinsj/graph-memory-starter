"""Dates: which facts hold when the question is asked about.

The example questions here are the ones in the README's "Dates and
amendments" table. Each test checks the facts that decide the answer.
The tests run as of 23 September 2026 (see graphs.py).
"""
import tempfile
import unittest
from datetime import date

from graphs import build, claims, edges, recall

NOW = date(2026, 9, 23)
DIRECTOR = ("Refund approvals", "approved_by", "Director")
OPS_MANAGER = ("Refund approvals", "approved_by", "Ops Manager")
DELEGATION = ("Sarah Chen", "delegates_to", "Marcus Webb")
OLD_RULE = ("Refund approvals", "Refunds over £250 need Director approval")
NEW_RULE = ("Refund approvals", "Refunds over £500 need Ops Manager approval before payment is released")
AGENT_RULE = ("Refund approvals", "Refunds under £500 are processed by any support agent within 48 hours")
LEAVE = ("Sarah Chen", "On leave 1-31 March 2026")


class Period(unittest.TestCase):
    """Reading the dates out of a question."""

    def check(self, question, start, end, label):
        p = recall.period(question, NOW)
        self.assertEqual((p.start, p.end, p.label), (start, end, label))

    def test_no_date_means_today(self):
        self.check("Who approves a £300 refund?", "2026-09-23", "2026-09-24", "as of 2026-09-23")

    def test_a_month_without_a_year_is_this_year(self):
        self.check("An £800 refund in March?", "2026-03-01", "2026-04-01", "for March 2026")

    def test_month_and_year(self):
        self.check("a refund in June 2025", "2025-06-01", "2025-07-01", "for June 2025")

    def test_days(self):
        for q in ("on 15 March 2026", "on March 15, 2026", "on 2026-03-15", "on 15th March"):
            self.check(q, "2026-03-15", "2026-03-16", "for 2026-03-15")

    def test_a_year(self):
        self.check("the threshold in 2025", "2025-01-01", "2026-01-01", "for 2025")
        self.check("the threshold last year", "2025-01-01", "2026-01-01", "for 2025")

    def test_open_ended(self):
        self.check("since January 2026", "2026-01-01", "9999-12-31", "since January 2026")
        self.check("after March 2026", "2026-04-01", "9999-12-31", "after March 2026")
        self.check("before 2026", "0000-01-01", "2026-01-01", "before 2026")
        self.check("until March 2026", "0000-01-01", "2026-04-01", "until March 2026")

    def test_a_history_question_spans_all_dates(self):
        for q in ("How has the refund threshold changed?", "What was the previous threshold?"):
            self.assertEqual(recall.period(q, NOW), recall.EVER)

    def test_words_that_only_look_like_dates(self):
        for q in ("Who may approve refunds?", "Payments over £2,000", "Who signs off 31 February?"):
            self.assertEqual(recall.period(q, NOW).label, "as of 2026-09-23")


class ExampleQuestions(unittest.TestCase):
    """The README's examples: the facts each answer rests on, and the ones it must not see."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.saved, recall.DB = recall.DB, build(cls.tmp.name)

    @classmethod
    def tearDownClass(cls):
        recall.DB = cls.saved
        cls.tmp.cleanup()

    def ask(self, question):
        facts = recall.recall(question)
        return facts, edges(facts), claims(facts)

    def test_800_refund_in_march_goes_to_marcus(self):
        facts, links, notes = self.ask("A customer wants an £800 refund in March. Who signs it off?")
        self.assertIn(", for March 2026", facts.header())
        self.assertIn(OPS_MANAGER, links)
        self.assertIn(DELEGATION, links)
        self.assertIn(LEAVE, notes)

    def test_800_refund_in_april_goes_to_sarah(self):
        facts, links, notes = self.ask("A customer wants an £800 refund in April 2026. Who signs it off?")
        self.assertIn(("Ops Manager", "held_by", "Sarah Chen"), links)
        self.assertNotIn(DELEGATION, links)  # the cover ended on 31 March
        self.assertNotIn(LEAVE, notes)

    def test_300_refund_in_june_2025_needed_a_director(self):
        _, links, notes = self.ask("Who approves a £300 refund in June 2025?")
        self.assertIn(DIRECTOR, links)
        self.assertNotIn(OPS_MANAGER, links)  # that policy started in January 2026
        self.assertIn(OLD_RULE, notes)
        self.assertNotIn(NEW_RULE, notes)

    def test_300_refund_today_any_agent(self):
        _, links, notes = self.ask("Who approves a £300 refund?")
        self.assertIn(AGENT_RULE, notes)
        self.assertNotIn(OLD_RULE, notes)
        self.assertNotIn(DIRECTOR, links)

    def test_threshold_history_shows_both_versions_with_dates(self):
        facts, links, notes = self.ask("How has the refund approval threshold changed?")
        self.assertIn(", for all dates", facts.header())
        self.assertIn(OLD_RULE, notes)
        self.assertIn(NEW_RULE, notes)
        self.assertIn(DIRECTOR, links)
        self.assertIn(OPS_MANAGER, links)
        text = facts.as_text()
        self.assertIn('Refund approvals: "Refunds over £250 require approval by a Director." '
                      "[refund-policy-2024.md] (until 2025-12-31)", text)
        self.assertIn("(from 2026-01-01)", text)

    def test_threshold_in_2025(self):
        _, _, notes = self.ask("What was the refund approval threshold in 2025?")
        self.assertIn(OLD_RULE, notes)
        self.assertNotIn(NEW_RULE, notes)

    def test_undated_facts_hold_at_any_date(self):
        _, links, _ = self.ask("Who approves supplier payments over £2,000 in 2025?")
        self.assertIn(("Supplier payments", "approved_by", "Founder"), links)
        self.assertIn(("Founder", "held_by", "Alex Doyle"), links)

    def test_cover_on_a_given_day(self):
        _, during, _ = self.ask("Who covers Sarah's sign-offs on 15 March 2026?")
        _, after, _ = self.ask("Who covers Sarah's sign-offs on 15 April 2026?")
        self.assertIn(DELEGATION, during)
        self.assertNotIn(DELEGATION, after)


if __name__ == "__main__":
    unittest.main()
