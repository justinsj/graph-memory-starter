"""The store, on both backends: the same answers from SQLite and Postgres, and workspaces kept apart.

On Postgres, row-level security is checked directly: a transaction for one
workspace sees none of another's rows even when its query forgets to filter,
and cannot write rows for another workspace.
"""
import shutil
import tempfile
import unittest
from pathlib import Path

import sqlalchemy as sa

import sys  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parent))
import kl_support as ks  # noqa: E402
from kl import db as t
from kl import errors


class Backends(unittest.TestCase):
    backend = "sqlite"

    @classmethod
    def setUpClass(cls):
        if cls.backend == "postgres" and not ks.postgres_available():
            raise unittest.SkipTest("pgserver and psycopg are not installed")
        cls.tmp = Path(tempfile.mkdtemp())
        cls.svc = ks.make_service(cls.tmp, cls.backend)
        cls.boot_a, cls.a = ks.workspace(cls.svc, "acme")
        cls.boot_b, cls.b = ks.workspace(cls.svc, "globex")
        ks.ingest_corpus(cls.svc, cls.a)
        ks.ingest_corpus(cls.svc, cls.b, names={"org-chart.md"})
        cr = cls.svc.create_project(cls.a, {"id": "refunds-dashboard", "title": "Refunds dashboard",
                                            "description": "A weekly view of refunds.", "owner": "Priya Patel"})
        cls.svc.approve_change_request(cls.a, cr["id"])

    @classmethod
    def tearDownClass(cls):
        cls.svc.close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_the_answer_is_the_one_recall_gives_in_process(self):
        import recall
        q = "A customer wants an £800 refund in March. Who signs it off?"
        ref = recall.recall(q, db=ks.graphs.build(self.tmp / "ref")).as_text()
        self.assertEqual(ks.without_extracted(self.svc.context(self.a, q)["text"]), ks.without_extracted(ref))

    def test_one_workspace_never_sees_another(self):
        a_doc = self.svc.list_sources(self.a)["items"][0]["id"]
        with self.assertRaises(errors.NotFound):
            self.svc.get_source(self.b, a_doc)
        self.assertEqual(len(self.svc.list_sources(self.b)["items"]), 1)
        self.assertEqual(self.svc.list_projects(self.b)["items"], [])
        with self.assertRaises(errors.NotFound):
            self.svc.get_project(self.b, "refunds-dashboard")
        self.assertEqual(self.svc.list_change_requests(self.b)["items"], [])
        ctx = self.svc.context(self.b, "A customer wants an £800 refund in March. Who signs it off?")
        self.assertNotIn("Refund approvals", ctx["text"])  # globex has only the org chart

    def test_every_table_but_two_carries_its_workspace(self):
        for table in t.md.sorted_tables:
            if table.name in t.GLOBAL:
                continue
            self.assertIn("workspace_id", table.c, table.name)


class Postgres(Backends):
    backend = "postgres"

    def _conn(self, ws, system=False):
        return self.svc.db.tx(ws, system=system)

    def test_row_security_hides_other_workspaces_even_without_a_filter(self):
        with self._conn(self.a.workspace_id) as c:
            ws = {r[0] for r in c.execute(sa.text("SELECT DISTINCT workspace_id FROM documents"))}
        self.assertEqual(ws, {self.a.workspace_id})
        with self._conn(self.b.workspace_id) as c:
            n = c.execute(sa.text("SELECT count(*) FROM documents")).scalar()
        self.assertEqual(n, 1)
        with self._conn(None) as c:  # a transaction that says no workspace sees nothing
            self.assertEqual(c.execute(sa.text("SELECT count(*) FROM documents")).scalar(), 0)

    def test_row_security_refuses_writes_for_another_workspace(self):
        import sqlalchemy.exc
        with self.assertRaises(sqlalchemy.exc.DBAPIError):
            with self._conn(self.a.workspace_id) as c:
                c.execute(t.jobs.insert().values(id="job_x", workspace_id=self.b.workspace_id, kind="x", status="x",
                                                 stage="x", subject={}, result={}, problems=[], created="x", updated="x"))

    def test_the_app_role_is_not_a_superuser(self):
        with self._conn(self.a.workspace_id) as c:
            self.assertFalse(c.execute(sa.text("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")).scalar())
            self.assertEqual(c.execute(sa.text("SELECT current_user")).scalar(), "kl_app")

    def test_postgres_and_sqlite_give_the_same_context(self):
        tmp = Path(tempfile.mkdtemp())
        lite = ks.make_service(tmp, "sqlite")
        _, p = ks.workspace(lite, "acme")
        ks.ingest_corpus(lite, p)
        try:
            for q in ("Who approves supplier payments over £2,000?", "Who covers Sarah Chen's sign-offs in March?"):
                self.assertEqual(ks.without_extracted(lite.context(p, q)["text"]),
                                 ks.without_extracted(self.svc.context(self.a, q)["text"]), q)
        finally:
            lite.close()
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
