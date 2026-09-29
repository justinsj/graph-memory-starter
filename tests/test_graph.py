"""The README's graph test cases, as code, plus the injection's two formats.

    python -m unittest discover tests

Every graph is built into a temp folder, so the repo's graph.db is left alone.
"""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from graphs import REFUND, build, claims, edges, recall


class GraphTestCases(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.saved, recall.DB = recall.DB, build(cls.tmp.name)

    @classmethod
    def tearDownClass(cls):
        recall.DB = cls.saved
        cls.tmp.cleanup()  # fails on Windows if recall left a connection open

    def test_refund_in_march_walks_three_hops_to_marcus(self):
        got = edges(recall.recall(REFUND))
        self.assertIn(("Refund approvals", "approved_by", "Ops Manager"), got)
        self.assertIn(("Ops Manager", "held_by", "Sarah Chen"), got)
        self.assertIn(("Sarah Chen", "delegates_to", "Marcus Webb"), got)

    def test_supplier_payments_walk_two_hops_to_alex(self):
        got = edges(recall.recall("Who approves supplier payments over £2,000?"))
        self.assertIn(("Supplier payments", "approved_by", "Founder"), got)
        self.assertIn(("Founder", "held_by", "Alex Doyle"), got)

    def test_onboarding_is_one_hop_several_edges(self):
        got = edges(recall.recall("What is the onboarding process?"))
        self.assertIn(("Onboarding process", "references", "Ops Manager"), got)
        self.assertIn(("Onboarding process", "references", "Tooling inventory"), got)

    def test_priya_is_seeded_by_alias(self):
        facts = recall.recall("What does Priya do?")
        self.assertIn(("Support Lead", "held_by", "Priya Patel"), edges(facts))
        # what the role involves, one link from the person asked about
        self.assertIn(("Support Lead", "Runs the support rota and handles escalations"),
                      claims(facts))

    def test_outside_the_vocabulary_fails_loudly(self):
        facts = recall.recall("Who is in charge when the boss is away?")
        self.assertEqual(facts.triples, [])
        self.assertIn("(no memory matches for this prompt)", facts.as_text())

    def test_injection_is_capped_at_eight_facts(self):
        self.assertLessEqual(len(recall.recall(REFUND).triples), 8)

    def test_conditions_travel_with_the_facts_as_claims(self):
        got = claims(recall.recall(REFUND))
        self.assertIn(("Sarah Chen", "On leave 1-31 March 2026"), got)
        self.assertIn(("Refund approvals",
                       "Refunds over £500 need Ops Manager approval before payment is released"), got)

    def test_claims_stay_on_topic(self):
        # the walk passes through the onboarding process; nothing about it was asked
        names = {name for name, _ in claims(recall.recall(REFUND))}
        self.assertNotIn("Onboarding process", names)

    def test_compact_format_for_the_model(self):
        text = recall.recall(REFUND).as_text()
        self.assertTrue(text.startswith("memory: "))
        self.assertIn(", for March 2026", text.splitlines()[0])
        self.assertIn("Refund approvals approved_by Ops Manager [refund-policy.md] (from 2026-01-01)",
                      text)
        self.assertIn("Sarah Chen delegates_to Marcus Webb [delegation-memo.md] "
                      "(2026-03-01 to 2026-03-31)", text)
        self.assertNotIn("  ", text.split("where:")[0])  # no padding to pay tokens for

    def test_pretty_format_for_people(self):
        text = recall.recall(REFUND).as_text(pretty=True)
        self.assertIn("Refund approvals --[approved_by]--> Ops Manager", text)
        self.assertIn("(refund-policy.md) (from 2026-01-01)", text)

    def test_same_question_same_facts(self):
        self.assertEqual(recall.recall(REFUND).triples, recall.recall(REFUND).triples)


class NoUsableGraph(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.saved = recall.DB

    def tearDown(self):
        recall.DB = self.saved
        self.tmp.cleanup()

    def test_missing_graph_says_how_to_build_it(self):
        recall.DB = Path(self.tmp.name) / "graph.db"
        facts = recall.recall(REFUND)
        self.assertEqual(facts.as_text(), "memory: " + recall.NO_GRAPH)
        self.assertFalse(recall.DB.exists())  # asking must not create an empty file

    def test_graph_from_an_older_version_says_rebuild(self):
        recall.DB = Path(self.tmp.name) / "graph.db"
        with sqlite3.connect(recall.DB) as db:  # the first schema: no access layer, no claims
            db.executescript("CREATE TABLE entities (id TEXT PRIMARY KEY, name TEXT, type TEXT,"
                             " description TEXT, source_doc TEXT);"
                             "CREATE TABLE relations (source_id TEXT, target_id TEXT,"
                             " predicate TEXT, source_doc TEXT);"
                             "CREATE TABLE aliases (entity_id TEXT, alias TEXT);")
        db.close()
        self.assertEqual(recall.recall(REFUND).as_text(), "memory: " + recall.OLD_GRAPH)


if __name__ == "__main__":
    unittest.main()
