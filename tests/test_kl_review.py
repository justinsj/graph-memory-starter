"""People approve every edit: change requests, over HTTP, as a task app would use them.

Nothing applies without a person's approval. One approval is enough, and a
proposer may approve their own request (the defaults; a workspace can turn
that off). Service accounts and runs never approve. Approval can be of all the
operations, some, or an edited version. A request that another approved one
made stale is caught at approval, and every decision records who, when and what.
"""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kl_support as ks  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from kl.api import create_app  # noqa: E402
from kl import db as t  # noqa: E402
from kl.client import Client, KLError  # noqa: E402

ROOT = ks.ROOT
DASH = {"id": "refunds-dashboard", "title": "Refunds dashboard", "description": "A weekly view of refunds.",
        "owner": "Priya Patel", "deliverables": [{"key": "D1", "title": "Weekly refunds view"}]}


class Review(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.svc = ks.make_service(cls.tmp)
        cls.http = TestClient(create_app(cls.svc, mcp=False))
        cls.boot, cls.admin_p = ks.workspace(cls.svc)
        ks.ingest_corpus(cls.svc, cls.admin_p)
        cls.admin = Client("http://testserver", cls.boot["key"], http=cls.http)
        _, key = ks.person(cls.svc, cls.admin_p, "ed@acme.example", "Ed Editor", "editor")
        cls.editor = Client("http://testserver", key, http=cls.http)
        _, key = ks.person(cls.svc, cls.admin_p, "ann@acme.example", "Ann Approver", "approver")
        cls.approver = Client("http://testserver", key, http=cls.http)
        _, key = ks.service_account(cls.svc, cls.admin_p, "task-app", ("read", "projects:propose", "context:read"))
        cls.app = Client("http://testserver", key, http=cls.http)

    @classmethod
    def tearDownClass(cls):
        cls.svc.close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def fresh(self, pid):
        body = {**DASH, "id": pid, "title": f"Dashboard {pid}"}
        return self.admin.approve(self.editor.create_project(**body)["id"])

    def test_nothing_applies_until_a_person_approves(self):
        cr = self.app.create_project(**{**DASH, "id": "wait-for-me", "title": "Wait for me"})
        self.assertEqual(cr["state"], "open")
        self.assertNotIn("wait-for-me", [p["id"] for p in self.admin.projects()["items"]])
        with self.assertRaises(KLError) as e:
            self.admin.project("wait-for-me")
        self.assertEqual(e.exception.status, 404)
        pending = self.admin.projects(include="pending")
        self.assertNotIn("wait-for-me", [p["id"] for p in pending["items"]])
        self.approver.approve(cr["id"])
        self.assertIn("wait-for-me", [p["id"] for p in self.admin.projects()["items"]])

    def test_a_proposer_may_approve_their_own_request_and_one_approval_is_enough(self):
        cr = self.approver.create_project(**{**DASH, "id": "self-approved", "title": "Self approved"})
        done = self.approver.approve(cr["id"])
        self.assertEqual(done["state"], "applied")
        self.assertEqual([(d["decision"], d["user_id"]) for d in done["decisions"]],
                         [("approve", self.approver.whoami()["id"])])

    def test_approve_true_proposes_and_approves_in_one_call_and_records_both(self):
        r = self.http.post("/v1/projects?approve=true", json={**DASH, "id": "one-call", "title": "One call"},
                           headers=self.approver.headers)
        self.assertEqual(r.status_code, 200)
        cr = r.json()
        self.assertEqual(cr["state"], "applied")
        self.assertEqual(cr["proposer"]["id"], cr["decisions"][0]["user_id"])

    def test_the_workspace_can_turn_self_approval_off(self):
        self.admin._req("PATCH", "/v1/workspace/settings", {"self_approval": False})
        try:
            cr = self.approver.create_project(**{**DASH, "id": "no-self", "title": "No self"})
            with self.assertRaises(KLError) as e:
                self.approver.approve(cr["id"])
            self.assertEqual(e.exception.status, 403)
            self.admin.approve(cr["id"])  # someone else may
        finally:
            self.admin._req("PATCH", "/v1/workspace/settings", {"self_approval": True})

    def test_service_accounts_editors_and_runs_never_approve(self):
        cr = self.editor.create_project(**{**DASH, "id": "not-yours", "title": "Not yours"})
        for who in (self.app, self.editor):
            with self.assertRaises(KLError) as e:
                who.approve(cr["id"])
            self.assertEqual(e.exception.status, 403)
        with self.assertRaises(KLError) as e:
            self.admin.create_service_account("sneaky", ["review:approve"])
        self.assertIn("only people approve", str(e.exception))
        with self.assertRaises(KLError) as e:
            self.app.create_project(approve=True, **{**DASH, "id": "not-yours-2", "title": "Nope"})
        self.assertEqual(e.exception.status, 403)

    def test_a_move_the_rules_forbid_is_refused_before_anyone_is_asked(self):
        self.fresh("forbidden-move")
        with self.assertRaises(KLError) as e:
            self.editor.patch_project("forbidden-move", status="active")
        self.assertEqual(e.exception.status, 422)
        self.assertIn("proposed → active is not allowed", str(e.exception))
        self.assertEqual(e.exception.problem["type"], "https://kl.dev/problems/invalid")

    def test_a_dry_run_shows_the_diff_and_opens_nothing(self):
        before = len(self.admin.change_requests()["items"])
        out = self.editor.changes([{"op": "create_project", "project": "dry", "title": "Dry", "description": "d"},
                                   {"op": "set_status", "project": "dry", "value": "done"}], dry_run=True)
        self.assertTrue(out["dry_run"])
        self.assertIn("+ project      Dry (dry)", out["diff"])
        self.assertTrue(out["problems"])  # proposed -> done is not a move
        self.assertEqual(len(self.admin.change_requests()["items"]), before)

    def test_approving_some_operations(self):
        self.fresh("pick-some")
        cr = self.editor.changes([{"op": "add_decision", "project": "pick-some", "text": "Weekly, not daily."},
                                  {"op": "add_question", "project": "pick-some", "key": "Q1", "text": "Which currency?"},
                                  {"op": "set_status", "project": "pick-some", "value": "planning"}])
        done = self.approver.approve(cr["id"], ops=[1, 3], note="the question is answered already")
        self.assertEqual(done["decisions"][0]["ops"], [1, 3])
        rec = self.admin.project("pick-some")["record"]
        self.assertEqual([d["text"] for d in rec["decisions"]], ["Weekly, not daily."])
        self.assertEqual(rec["questions"], [])
        self.assertEqual(rec["status"][-1]["value"], "planning")
        self.assertTrue(done["ops"][-1].get("skipped"))

    def test_approving_an_edited_version_records_the_edit(self):
        self.fresh("edit-me")
        cr = self.editor.changes([{"op": "set_field", "project": "edit-me", "field": "title", "value": "Refund dash"}])
        done = self.approver.approve(cr["id"], edits={"1": {"value": "Refunds dashboard v2"}})
        self.assertIn("'Refund dash' → 'Refunds dashboard v2'", done["decisions"][0]["edits"]["1"])
        pr = self.admin.project("edit-me", include=("events",))
        self.assertEqual(pr["record"]["title"], "Refunds dashboard v2")
        src = pr["record"]["aliases"]
        self.assertIn("Dashboard edit-me", src)  # the old title still finds it
        doc = next(d for d in self.admin.sources(collection="requests", limit=500)["items"]
                   if d["name"] == f"cr-{cr['number']}.md")
        text = self.http.get(f"/v1/sources/{doc['id']}/content", headers=self.admin.headers).text
        self.assertIn("Edited when approved:", text)
        self.assertIn("Approved by Ann Approver", text)

    def test_a_request_another_approval_made_stale_is_caught(self):
        self.fresh("stale-one")
        first = self.editor.add_deliverable("stale-one", "D2", "Monthly view")
        second = self.editor.add_deliverable("stale-one", "D2", "Monthly view, again")
        self.approver.approve(first["id"])
        with self.assertRaises(KLError) as e:
            self.approver.approve(second["id"])
        self.assertEqual(e.exception.status, 409)
        self.assertEqual(self.admin.change_request(second["id"])["state"], "stale")
        fixed = self.editor.update_change_request(second["id"], ops=[
            {"op": "add_deliverable", "project": "stale-one", "key": "D3", "title": "Monthly view, again"}])
        self.assertEqual(fixed["state"], "open")
        self.assertEqual(self.approver.approve(second["id"])["state"], "applied")

    def test_if_match_refuses_an_edit_based_on_an_old_version(self):
        self.fresh("versioned")
        v = self.admin.project("versioned")["version"]
        with self.assertRaises(KLError) as e:
            self.editor.patch_project("versioned", if_match=v + 5, title="Nope")
        self.assertEqual(e.exception.status, 409)
        self.assertEqual(e.exception.problem["current_version"], v)
        self.assertEqual(self.editor.patch_project("versioned", if_match=v, title="Yes")["state"], "open")

    def test_a_rejection_keeps_its_reason(self):
        cr = self.editor.create_project(**{**DASH, "id": "rejected", "title": "Rejected"})
        out = self.approver.reject(cr["id"], note="we have one already")
        self.assertEqual(out["state"], "rejected")
        self.assertEqual(out["decisions"][0]["note"], "we have one already")
        with self.assertRaises(KLError):
            self.approver.approve(cr["id"])

    def test_soft_delete_leaves_recall_and_the_list_and_restore_brings_it_back(self):
        self.fresh("soft")
        q = "Who owns Dashboard soft?"
        self.assertIn("Dashboard soft", self.admin.context(q)["text"])
        self.approver.approve(self.editor.delete_project("soft")["id"])
        self.assertNotIn("soft", [p["id"] for p in self.admin.projects()["items"]])
        self.assertIn("soft", [p["id"] for p in self.admin.projects(include_deleted="true")["items"]])
        self.assertNotIn("Dashboard soft", self.admin.context(q)["text"])
        self.approver.approve(self.editor.restore_project("soft")["id"])
        self.assertIn("Dashboard soft", self.admin.context(q)["text"])

    def test_every_decision_is_in_the_projects_history(self):
        self.fresh("history")
        self.approver.approve(self.editor.patch_project("history", status="planning")["id"])
        events = self.admin.project("history", include=("events",))["events"]
        last = events[-1]
        self.assertEqual((last["op"], last["new"]), ("set_status", "planning"))
        self.assertIn("approved by Ann Approver", last["actor"])
        self.assertTrue(last["change_request"])
        self.assertTrue(last["source"].startswith("inputs/requests/cr-"))


class Cases(unittest.TestCase):
    """projects/cases, each applied as a change request, gives the record the case expects."""

    def test_each_case_as_a_change_request(self):
        import cases
        import model
        for case in cases.all_cases():
            with self.subTest(case=case["name"]):
                tmp = Path(tempfile.mkdtemp())
                svc = ks.make_service(tmp)
                try:
                    _, p = ks.workspace(svc)
                    ks.ingest_corpus(svc, p)
                    with svc.db.tx(p.workspace_id) as c:  # the case's starting records, as the log would hold them
                        for pid, rec in case["before"].items():
                            c.execute(t.project_records.insert().values(workspace_id=p.workspace_id, project_id=pid, version=1, record=rec,
                                              updated="2026-09-01T00:00:00.000000Z"))
                        svc.bump(c, p.workspace_id)
                    for rel in {s["doc"] for r in case["before"].values() for s in r["sources"]}:
                        path = ROOT / "projects" / "cases" / rel
                        if path.is_file():
                            svc.ingest(p, name=Path(rel).name, collection=str(Path(rel).parent.relative_to("inputs"))
                                       if Path(rel).parent.name != "inputs" else "", kind="transcript",
                                       text=path.read_text(encoding="utf-8"), changes=[])
                    if not case["diff"]["changes"]:
                        continue
                    r = svc.ingest(p, name=Path(case["input"]).name, kind=case.get("kind", "transcript"),
                                   collection="" if Path(case["input"]).parent.name == "inputs"
                                   else Path(case["input"]).parent.name, text=case["text"],
                                   changes=case["diff"]["changes"], on=case["diff"]["on"])
                    cr = svc.get_change_request(p, r["job"]["result"]["change_request"])
                    self.assertEqual(cr["problems"], [], cr["problems"])
                    svc.approve_change_request(p, cr["id"])
                    after = svc._records(p.workspace_id)
                    self.assertEqual(cases.check(case["expect"], case["before"], case["diff"], after), [])
                    _, _, snapshot = svc.projector.ensure(p.workspace_id)  # every quote is in the file it cites
                    for rec in after.values():
                        self.assertEqual(model.check_record(rec, snapshot), [], rec["id"])
                finally:
                    svc.close()
                    shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
