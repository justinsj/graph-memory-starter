"""The RAG layer: rank fusion, and the test cases in rag/README.md.

The README cases need fastembed (the meaning leg) and are skipped without it.
The index is built into a temp folder, so rag/rag.db is left alone.
"""
import contextlib
import io
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "rag"))
import build_index  # noqa: E402
import search  # noqa: E402

try:
    import fastembed  # noqa: F401
    HAVE_FASTEMBED = True
except ImportError:
    HAVE_FASTEMBED = False


class Fusion(unittest.TestCase):

    def test_scores_add_across_legs(self):
        ranked, found_by = search.fuse({"keyword": [1, 2], "meaning": [2, 3]})
        self.assertEqual(ranked[0], 2)
        self.assertEqual(found_by[2], ["keyword", "meaning"])

    def test_meaning_leg_breaks_a_tie(self):
        # 1 and 3 both top a leg: equal scores, and the meaning leg decides
        ranked, _ = search.fuse({"keyword": [1, 2], "meaning": [3, 4]})
        self.assertEqual(ranked[:2], [3, 1])

    def test_keyword_only_keeps_its_order(self):
        self.assertEqual(search.fuse({"keyword": [5, 6, 7]})[0], [5, 6, 7])


@unittest.skipUnless(HAVE_FASTEMBED, "needs fastembed: python -m pip install fastembed")
class ReadmeCases(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.saved, build_index.DB = build_index.DB, Path(cls.tmp.name) / "rag.db"
        argv, sys.argv = sys.argv, ["build_index.py"]  # the default corpus: corpus-before
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                build_index.main()
        finally:
            sys.argv = argv
        cls.db = sqlite3.connect(build_index.DB)

    @classmethod
    def tearDownClass(cls):
        cls.db.close()
        build_index.DB = cls.saved
        cls.tmp.cleanup()

    def top(self, query, n=3):
        legs = {"keyword": search.keyword_leg(self.db, query),
                "meaning": search.meaning_leg(self.db, query)}
        ranked, found_by = search.fuse(legs)
        out = []
        for rowid in ranked[:n]:
            file, section, text = self.db.execute(
                "SELECT file, section, text FROM chunks WHERE id = ?", (rowid,)).fetchone()
            out.append((f"{file} § {section}", found_by[rowid], text))
        return out

    def test_mileage_rate_both_legs_agree(self):
        label, legs, _ = self.top("what is the mileage rate")[0]
        self.assertTrue(label.startswith("expenses.md"))
        self.assertEqual(legs, ["keyword", "meaning"])

    def test_talk_to_customers_meaning_finds_the_right_docs(self):
        labels = [label for label, _, _ in self.top("how do we talk to customers in writing")]
        self.assertEqual(labels[0], "customer-ops-handbook.md § Tone of voice")
        self.assertTrue(any(label.startswith("brand-voice.md") for label in labels))

    def test_sign_off_while_sarah_is_away_distilled_entry_first(self):
        labels = [label for label, _, _ in self.top("who has sign-off while Sarah is away")]
        self.assertEqual(labels[:2], ["ooo-march-sarah.md § distilled",
                                      "ooo-march-sarah.md § ooo-march-sarah"])

    def test_refund_in_march_the_500_rule_first(self):
        _, _, text = self.top("A customer wants an £800 refund in March. Who signs it off?")[0]
        self.assertIn("£500", text)


if __name__ == "__main__":
    unittest.main()
