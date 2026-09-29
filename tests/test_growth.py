"""Recall as the graph grows: the answer must stay in the 8 facts, and fast.

Two ways to grow, as measured in docs/improvement-proposals.html:
  around a busy node   policies all approved by the Ops Manager, one hop from
                       the question, which used to push the answer out
  elsewhere            separate clusters, which used to slow name matching

Time limits are loose on purpose (5x or more what was measured) so a slow
machine does not fail them; they catch the old code, which took seconds.
"""
import tempfile
import unittest

from graphs import REFUND, build, clusters, edges, policies, recall

ANSWER = ("Sarah Chen", "delegates_to", "Marcus Webb")


class GrowthCase(unittest.TestCase):
    extra = None

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.saved, recall.DB = recall.DB, build(cls.tmp.name, cls.extra)

    @classmethod
    def tearDownClass(cls):
        recall.DB = cls.saved
        cls.tmp.cleanup()

    def recall_timed(self, runs=5):
        results = [recall.recall(REFUND) for _ in range(runs)]
        return results[-1], sorted(r.ms for r in results)[runs // 2]


class Busy100(GrowthCase):
    extra = policies(100)

    def test_answer_survives(self):
        facts, _ = self.recall_timed(1)
        self.assertIn(ANSWER, edges(facts))
        self.assertEqual(len(facts.triples), 8)


class Busy1000(GrowthCase):
    extra = policies(1000)

    def test_answer_survives(self):
        self.assertIn(ANSWER, edges(recall.recall(REFUND)))


class Busy10000(GrowthCase):
    extra = policies(10000)

    def test_answer_survives_within_budget(self):
        facts, ms = self.recall_timed()
        self.assertIn(ANSWER, edges(facts))
        self.assertFalse(facts.stopped)
        self.assertLess(ms, 250)  # measured about 43 ms; the old query took 12 s


class BusyBare10000(GrowthCase):
    extra = policies(10000, text="")  # nothing in the policies' text to rank them by

    def test_answer_survives(self):
        self.assertIn(ANSWER, edges(recall.recall(REFUND)))


class Elsewhere10000(GrowthCase):
    extra = clusters(10000)  # 30,013 entities

    def test_answer_survives_and_names_are_fast(self):
        facts, ms = self.recall_timed()
        self.assertIn(ANSWER, edges(facts))
        self.assertLess(ms, 50)  # measured about 1 ms; the old regex took 0.9 s


class TimeBudget(GrowthCase):
    extra = policies(1000)

    def test_out_of_time_says_so(self):
        facts = recall.recall(REFUND, budget_ms=0)
        self.assertTrue(facts.stopped)
        self.assertIn("stopped at the time budget", facts.header())

    def test_in_time_says_nothing(self):
        self.assertFalse(recall.recall(REFUND).stopped)


if __name__ == "__main__":
    unittest.main()
