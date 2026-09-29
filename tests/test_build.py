"""build_graph.py: deterministic, fills the access layer, refuses what it would guess."""
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from graphs import build, build_graph

REFUND = {"name": "Refund approvals", "type": "POLICY"}


def dump(db_path: Path) -> dict:
    with closing(sqlite3.connect(db_path)) as db:
        return {t: sorted(db.execute(f"SELECT * FROM {t}"))  # noqa: S608
                for t in ("entities", "claims", "relations", "names", "meta")}


def doc(*nodes, edges=()):
    return {"source_doc": "extra.md", "nodes": list(nodes), "edges": list(edges)}


class Build(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def refused(self, *extra) -> str:
        with self.assertRaises(SystemExit) as stop:
            build(self.dir / "a", *extra)
        return str(stop.exception)

    def test_same_input_same_db(self):
        first = dump(build(self.dir / "a"))
        self.assertEqual(first, dump(build(self.dir / "b")))

    def test_counts(self):
        with closing(sqlite3.connect(build(self.dir / "a"))) as db:
            count = lambda t: db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]  # noqa: E731,S608
            aliases = db.execute("SELECT COUNT(*) FROM names WHERE kind = 'alias'").fetchone()[0]
            self.assertEqual((count("entities"), count("claims"), count("relations"), aliases),
                             (14, 35, 14, 10))
            # every name and every alias is findable, and every entity text-indexed
            self.assertEqual(count("names"), 14 + 10)
            self.assertEqual(count("entity_fts"), 14)
            meta = dict(db.execute("SELECT key, value FROM meta"))
        self.assertEqual({k: meta[k] for k in ("entities", "longest_name", "docs_root", "docs")},
                         {"entities": "14", "longest_name": "3", "docs_root": "corpus", "docs": "9"})
        self.assertRegex(meta["extracted"], r"^\d{4}-\d{2}-\d{2}$")

    def test_names_are_split_like_questions(self):
        with closing(sqlite3.connect(build(self.dir / "a"))) as db:
            rows = set(db.execute("SELECT norm, kind, text FROM names"))
        self.assertIn(("customer support sop", "name", "Customer support SOP"), rows)
        # an alias keeps the extraction's spelling beside its search key
        self.assertIn(("priya", "alias", "Priya"), rows)

    def test_every_docs_claims_are_kept(self):
        # the Ops Manager is described in two docs; the old build kept only the first
        with closing(sqlite3.connect(build(self.dir / "a"))) as db:
            got = {(t, d) for t, d in db.execute(
                "SELECT c.text, c.source_doc FROM claims c JOIN entities e ON e.id = c.entity_id"
                " WHERE e.name = 'Ops Manager'")}
        self.assertEqual(got, {("Owns day-to-day operations, budgets and sign-offs", "org-chart.md"),
                               ("Approves refunds over £500", "refund-policy.md")})

    def test_dated_versions_of_a_policy_coexist(self):
        with closing(sqlite3.connect(build(self.dir / "a"))) as db:
            got = list(db.execute(
                "SELECT c.amount, c.valid_from, c.valid_to FROM claims c"
                " JOIN entities e ON e.id = c.entity_id"
                " WHERE e.name = 'Refund approvals' AND c.kind = 'threshold'"
                " ORDER BY COALESCE(c.valid_from, '')"))
        self.assertEqual(got, [(250.0, None, "2026-01-01"), (500.0, "2026-01-01", None)])

    def test_links_carry_their_dates(self):
        with closing(sqlite3.connect(build(self.dir / "a"))) as db:
            got = db.execute("SELECT valid_from, valid_to FROM relations"
                             " WHERE predicate = 'delegates_to'").fetchone()
        self.assertEqual(got, ("2026-03-01", "2026-04-01"))

    def test_foreign_keys_hold(self):
        with closing(sqlite3.connect(build(self.dir / "a"))) as db:
            db.execute("PRAGMA foreign_keys = ON")
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("INSERT INTO claims (entity_id, kind, text, source_doc)"
                           " VALUES ('no-such-entity', 'note', 'x', 'x.md')")
            self.assertEqual(list(db.execute("PRAGMA foreign_key_check")), [])

    def test_an_older_extraction_description_becomes_a_note(self):
        old = doc({"name": "Legacy policy", "type": "POLICY", "description": "Written the old way"})
        with closing(sqlite3.connect(build(self.dir / "a", old))) as db:
            got = db.execute("SELECT c.kind, c.text FROM claims c JOIN entities e"
                             " ON e.id = c.entity_id WHERE e.name = 'Legacy policy'").fetchone()
        self.assertEqual(got, ("note", "Written the old way"))

    def test_name_with_two_types_stops_the_build(self):
        message = self.refused(doc({"name": "Ops Manager", "type": "PERSON"}))
        self.assertIn("ops_manager", message)
        self.assertIn("ROLE", message)
        self.assertIn("PERSON in extra.md", message)

    def test_unknown_claim_kind_stops_the_build(self):
        message = self.refused(doc({**REFUND, "claims": [{"kind": "vibe", "text": "Friendly"}]}))
        self.assertIn("kind 'vibe'", message)

    def test_a_date_that_is_not_a_date_stops_the_build(self):
        message = self.refused(doc({**REFUND, "claims": [
            {"kind": "note", "text": "x", "valid_from": "March 2026"}]}))
        self.assertIn("'March 2026' is not a YYYY-MM-DD date", message)

    def test_dates_the_wrong_way_round_stop_the_build(self):
        message = self.refused(doc(edges=[{"source": "Sarah Chen", "predicate": "delegates_to",
                                          "target": "Marcus Webb", "valid_from": "2026-04-01",
                                          "valid_to": "2026-03-01"}]))
        self.assertIn("is not before valid_to", message)

    def test_two_thresholds_in_force_at_once_stop_the_build(self):
        # an undated £300 rule would hold alongside both dated versions
        message = self.refused(doc({**REFUND, "claims": [
            {"kind": "threshold", "text": "Refunds over £300 need Director approval", "amount": 300}]}))
        self.assertIn("two threshold claims hold at once", message)
        self.assertIn("Refunds over £300 need Director approval", message)

    def test_the_repo_extraction_is_consistent(self):
        docs = [json.loads(f.read_text(encoding="utf-8"))
                for f in sorted(build_graph.EXTRACTION.glob("*.json"))]
        self.assertEqual(build_graph.clashes(docs), {})
        self.assertEqual(build_graph.problems(docs), [])
        # every claim carries the source's own words
        self.assertEqual([c["text"] for d in docs for n in d["nodes"] for c in n["claims"]
                          if not c.get("quote")], [])


if __name__ == "__main__":
    unittest.main()
