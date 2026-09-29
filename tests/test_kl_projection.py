"""The graph as a projection of the log.

- It answers exactly as in-process recall does over the same files (the recall
  questions and all sixteen code questions).
- Any sequence of adding, changing, retracting and restoring files gives the
  graph a full build of the surviving files gives.
- A new version of one file rewrites that file's snapshot entries and no others.
- A claim's id is the same in every build.
- A graph file is never replaced under a reader.
"""
import json
import random
import shutil
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kl_support as ks  # noqa: E402
import build_graph  # noqa: E402
import recall  # noqa: E402
from kl.projection import safe_name  # noqa: E402

ROOT = ks.ROOT
SHOP = ROOT / "codegraph" / "cases" / "shop"
EXTRACTION = {json.loads(p.read_text(encoding="utf-8"))["source_doc"]: json.loads(p.read_text(encoding="utf-8"))
              for p in (ROOT / "extraction").glob("*.json")}
QUESTIONS = [
    "A customer wants an £800 refund in March. Who signs it off?",
    "Who approves supplier payments over £2,000?",
    "Who covers Sarah Chen's sign-offs in March?",
    "Who approves a £300 refund in June 2025?",
    "What happens when a severity-1 incident is raised?",
    "Who owns onboarding for new starters?",
    "What does the tooling inventory list?",
    "Who is Priya?",
]


def tables(db_path) -> dict:
    """Everything a build writes that answers depend on, as sorted rows (row numbers left out)."""
    with closing(sqlite3.connect(db_path)) as db:
        return {
            "entities": sorted(db.execute("SELECT id, name, type, source_doc FROM entities")),
            "claims": sorted(db.execute("SELECT entity_id, kind, text, quote, amount, unit, valid_from, valid_to, "
                                        "source_doc FROM claims")),
            "relations": sorted(db.execute("SELECT source_id, target_id, predicate, source_doc, valid_from, valid_to "
                                           "FROM relations")),
            "names": sorted(db.execute("SELECT norm, entity_id, kind, text FROM names")),
            "fts": sorted(db.execute("SELECT entity_id, name, claims FROM entity_fts")),
        }


class SameAnswers(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.svc = ks.make_service(cls.tmp)
        _, cls.p = ks.workspace(cls.svc)
        ks.ingest_corpus(cls.svc, cls.p)
        code = cls.tmp / "code"
        shutil.copytree(SHOP, code / "shop")
        cls.svc.ingest(cls.p, name="shop", kind="code", data=ks.zip_dir(SHOP))
        cls.ref = ks.graphs.build(cls.tmp / "ref", code=code)

    @classmethod
    def tearDownClass(cls):
        cls.svc.close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_document_questions(self):
        for q in QUESTIONS:
            with self.subTest(q=q):
                self.assertEqual(ks.without_extracted(self.svc.context(self.p, q)["text"]),
                                 ks.without_extracted(recall.recall(q, db=self.ref).as_text()))

    def test_code_questions(self):
        cases = json.loads((ROOT / "codegraph" / "cases" / "questions.json").read_text(encoding="utf-8"))
        for case in cases:
            with self.subTest(case=case["id"]):
                got = self.svc.context(self.p, case["question"])["text"]
                want = recall.recall(case["question"], db=self.ref).as_text()
                self.assertEqual(ks.without_extracted(got), ks.without_extracted(want))

    def test_each_fact_names_its_claim_by_content(self):
        ctx = self.svc.context(self.p, QUESTIONS[0])
        self.assertTrue(ctx["claims"])
        for c in ctx["claims"]:
            self.assertTrue(c["id"].startswith("clm_"), c)
            self.assertEqual(self.svc.get_claim(self.p, c["id"])["text"], c["text"])


class Projection(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.svc = ks.make_service(self.tmp)
        _, self.p = ks.workspace(self.svc)

    def tearDown(self):
        self.svc.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def graph(self):
        return self.svc.projector.ensure(self.p.workspace_id)[0]

    @staticmethod
    def variants():
        """For each file, the contents it may have: the original, and for two of them a changed fact."""
        out = {}
        for f in sorted(ks.CORPUS.glob("*.md")):
            text = f.read_text(encoding="utf-8")
            out[f.name] = [(text, EXTRACTION[f.name])]
        sp = out["supplier-payments.md"][0][0]
        out["supplier-payments.md"].append((sp.replace("£2,000", "£3,000"),
                                            json.loads(json.dumps(EXTRACTION["supplier-payments.md"], ensure_ascii=False)
                                                       .replace("£2,000", "£3,000").replace("2000", "3000"))))
        oc = out["org-chart.md"][0][0]
        out["org-chart.md"].append((oc + "\nThe org chart was reviewed in September.\n", EXTRACTION["org-chart.md"]))
        return out

    def reference(self, active: dict):
        """A full build of exactly these files, laid out as the projection lays them out."""
        folder = Path(tempfile.mkdtemp(dir=self.tmp))
        (folder / "docs").mkdir()
        (folder / "extraction").mkdir()
        for name, (text, x) in active.items():
            (folder / "docs" / name).write_text(text, encoding="utf-8")
            (folder / "extraction" / f"{safe_name(name)}.json").write_text(
                json.dumps({**x, "source_doc": name}), encoding="utf-8")
        db = folder / "g.db"
        build_graph.build(extraction=folder / "extraction", db_path=db, docs_root=folder / "docs",
                          records=folder / "none", records_root=folder, now=self.svc.clock.today())
        return db

    def test_any_sequence_of_changes_gives_the_graph_a_full_build_gives(self):
        rng = random.Random(20260928)
        variants = self.variants()
        active, retracted, ids = {}, {}, {}
        for step in range(24):
            name = rng.choice(sorted(variants))
            move = rng.choice(["add", "add", "retract", "restore"])
            if move == "add" or (move == "restore" and name not in retracted) or (move == "retract" and name not in active):
                text, x = rng.choice(variants[name])
                r = self.svc.ingest(self.p, name=name, text=text, extraction=x)
                ids[name] = r["document_id"]
                self.assertIn(r["status"], ("active",), r)
                active[name] = (text, x)
                retracted.pop(name, None)
            elif move == "retract":
                self.svc.retract_source(self.p, ids[name])
                retracted[name] = active.pop(name)
            else:
                self.svc.restore_source(self.p, ids[name])
                active[name] = retracted.pop(name)
            with self.subTest(step=step, move=move, name=name):
                self.assertEqual(tables(self.graph()), tables(self.reference(active)))

    def test_a_new_version_rewrites_only_its_own_files(self):
        ks.ingest_corpus(self.svc, self.p)
        _, _, snap = self.svc.projector.ensure(self.p.workspace_id)
        before = {p: p.stat().st_mtime_ns for p in snap.rglob("*") if p.is_file() and p.name != ".manifest.json"}
        import time
        time.sleep(0.05)
        text = (ks.CORPUS / "org-chart.md").read_text(encoding="utf-8") + "\nReviewed in September.\n"
        self.svc.ingest(self.p, name="org-chart.md", text=text, extraction=EXTRACTION["org-chart.md"])
        self.svc.projector.ensure(self.p.workspace_id)
        changed = sorted(p.relative_to(snap).as_posix() for p, m in before.items() if p.stat().st_mtime_ns != m)
        self.assertEqual(changed, ["docs/org-chart.md", "extraction/org-chart.md.json"])

    def test_a_claims_id_is_the_same_in_every_build(self):
        ks.ingest_corpus(self.svc, self.p, names={"refund-policy.md"})
        first = {c["id"] for c in self.svc.context(self.p, QUESTIONS[0])["claims"]}
        ks.ingest_corpus(self.svc, self.p, names={"org-chart.md", "tooling-inventory.md"})
        self.svc.projector.drop(self.p.workspace_id)  # no cache: rebuilt from the log
        again = {c["id"] for c in self.svc.context(self.p, QUESTIONS[0])["claims"]}
        self.assertTrue(first)
        self.assertLessEqual(first, again)

    def test_a_graph_file_is_never_replaced_under_a_reader(self):
        ks.ingest_corpus(self.svc, self.p, names={"refund-policy.md"})
        old = self.graph()
        reader = sqlite3.connect(old)
        try:
            ks.ingest_corpus(self.svc, self.p, names={"org-chart.md"})
            new = self.graph()
            self.assertNotEqual(old, new)
            self.assertTrue(reader.execute("SELECT count(*) FROM entities").fetchone()[0] > 0)
        finally:
            reader.close()


if __name__ == "__main__":
    unittest.main()
