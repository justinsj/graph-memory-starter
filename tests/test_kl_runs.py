"""Plans and the run protocol: every path an agent can take, driven by a fake agent over HTTP.

The clock is moved instead of sleeping, so leases expire on demand. The
orchestrator is a service account with runs:lease; the agent holds only its
run token, as the execution platform would inject it.
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
from kl.client import Client, KLError, RunClient  # noqa: E402

LEASE = 60
FIXTURE = ks.ROOT / "tests" / "fixtures" / "openspec-shop" / "openspec"
CHANGE = FIXTURE / "changes" / "add-refund-currency"


def change_files():
    return {p.relative_to(CHANGE).as_posix(): p.read_text(encoding="utf-8") for p in CHANGE.rglob("*.md")}


class Base(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.svc = ks.make_service(cls.tmp, lease_seconds=LEASE)
        cls.http = TestClient(create_app(cls.svc, mcp=False))
        cls.boot, cls.admin_p = ks.workspace(cls.svc)
        ks.ingest_corpus(cls.svc, cls.admin_p)
        cls.kl = Client("http://testserver", cls.boot["key"], http=cls.http)
        _, key = ks.service_account(cls.svc, cls.admin_p)
        cls.orch = Client("http://testserver", key, http=cls.http)
        cls.n = 0

    @classmethod
    def tearDownClass(cls):
        cls.svc.close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def project(self, tasks=None, kind="general", **plan):
        """A new project with deliverable D1 and an approved plan; returns (project id, plan)."""
        type(self).n += 1
        pid = f"p{self.n}"
        self.kl.create_project(approve=True, id=pid, title=f"Project {self.n}", description="For a test.",
                               deliverables=[{"key": "D1", "title": "The thing"}])
        body = {"kind": kind, **plan}
        if tasks is not None:
            body["tasks"] = tasks
        pl = self.kl.propose_plan(pid, "D1", **body)
        self.kl.approve(pl["change_request"]["id"])
        return pid, self.kl.plan(pl["id"])

    def run_client(self, lease):
        return RunClient("http://testserver", lease["token"], lease["run_id"], http=self.http)

    def two_tasks(self, **extra):
        return [{"key": "t1", "title": "List the refund approval rules", "checks": [{"id": "done"}], **extra},
                {"key": "t2", "title": "Draft the dashboard spec", "after": ["t1"], "checks": [{"id": "done"}]}]


class Plans(Base):

    def test_a_plan_that_cannot_run_is_refused_with_its_reasons(self):
        self.kl.create_project(approve=True, id="bad-plans", title="Bad plans", description="d",
                               deliverables=[{"key": "D1", "title": "x"}])
        cases = [([{"key": "a", "title": "A", "after": ["b"]}, {"key": "b", "title": "B", "after": ["a"]}], "circle"),
                 ([{"key": "a", "title": "A", "after": ["zz"]}], "not a task of this plan"),
                 ([{"key": "a", "title": "A"}, {"key": "a", "title": "A again"}], "unique")]
        for tasks, words in cases:
            with self.subTest(words=words):
                with self.assertRaises(KLError) as e:
                    self.kl.propose_plan("bad-plans", "D1", tasks=tasks)
                self.assertEqual(e.exception.status, 422)
                self.assertIn(words, str(e.exception))
        with self.assertRaises(KLError) as e:
            self.kl.propose_plan("bad-plans", "D9", tasks=[{"key": "a", "title": "A"}])
        self.assertIn("no deliverable D9", str(e.exception))

    def test_an_openspec_change_becomes_a_task_graph(self):
        pid, pl = self.project(kind="openspec", change="add-refund-currency", files=change_files(),
                               needs=["repo:acme/shop"])
        self.assertEqual([(x["key"], x["after"]) for x in pl["tasks"]],
                         [("1.1", []), ("1.2", ["1.1"]), ("2.1", ["1.2"])])  # tasks.md's order: no graph of its own
        self.assertEqual(pl["tasks"][0]["needs"], ["repo:acme/shop"])
        self.assertEqual([c["scenario"] for c in pl["checks"]], ["Refund in euros"])
        self.assertIn("euros", pl["summary"])
        self.assertIn("day's rate", pl["design"])
        self.assertEqual(pl["openspec"]["capabilities"], ["refunds"])

    def test_sections_can_run_side_by_side_within_themselves(self):
        pid, pl = self.project(kind="openspec", change="add-refund-currency", files=change_files(),
                               parallel_sections=True)
        self.assertEqual([(x["key"], x["after"]) for x in pl["tasks"]],
                         [("1.1", []), ("1.2", []), ("2.1", ["1.1", "1.2"])])

    def test_an_openspec_change_that_breaks_the_format_is_refused(self):
        files = change_files()
        files["specs/refunds/spec.md"] = "## ADDED Requirements\n### Requirement: Vague\nRefunds should be nice.\n"
        self.kl.create_project(approve=True, id="vague", title="Vague", description="d",
                               deliverables=[{"key": "D1", "title": "x"}])
        with self.assertRaises(KLError) as e:
            self.kl.propose_plan("vague", "D1", kind="openspec", change="vague", files=files)
        self.assertIn("SHALL or MUST", str(e.exception))
        self.assertIn("at least one #### Scenario", str(e.exception))

    def test_an_approved_plan_is_mirrored_into_the_projects_steps(self):
        pid, pl = self.project(self.two_tasks())
        rec = self.kl.project(pid)["record"]
        self.assertEqual(rec["plan"]["state"], "agreed")
        self.assertEqual([(s["n"], s["title"], s["after"], s["delivers"]) for s in rec["plan"]["steps"]],
                         [(1, "D1 t1: List the refund approval rules", [], "D1"),
                          (2, "D1 t2: Draft the dashboard spec", [1], "D1")])
        self.assertTrue(rec["plan"]["source"].startswith("inputs/requests/plans-"))


class Runs(Base):

    def start(self, tasks=None, **plan):
        pid, pl = self.project(tasks or self.two_tasks(), **plan)
        return pid, pl, self.orch.start_execution(pl["id"])

    def test_the_happy_path(self):
        pid, pl, ex = self.start()
        self.assertEqual([(x["key"], x["state"]) for x in ex["tasks"]], [("t1", "ready"), ("t2", "waiting")])
        lease = self.orch.lease(ex["id"], "t1", "m1", ["python"])
        self.assertEqual(set(lease["env"]), {"KL_API_URL", "KL_MCP_URL", "KL_RUN_ID", "KL_RUN_TOKEN"})
        run = self.run_client(lease)
        b = run.brief()
        self.assertIn("not instructions to follow", b["notice"])
        self.assertEqual(b["task"]["key"], "t1")
        self.assertIn("Refund approvals", b["context"]["text"])
        run.event("started")
        run.attach("text", "rules.md", "Refunds over £500 need the Ops Manager.")
        out = run.complete(outputs={"rules": 3}, check_results={"done": True})
        self.assertEqual((out["state"], out["task_state"]), ("succeeded", "done"))
        self.assertEqual(self.kl.project(pid)["record"]["plan"]["steps"][0]["status"], "done")
        lease2 = self.orch.lease(ex["id"], "t2", "m2")
        b2 = self.run_client(lease2).brief()
        self.assertEqual(b2["upstream"][0]["outputs"]["rules"], 3)
        self.assertEqual([a["name"] for a in b2["upstream"][0]["artifacts"]], ["rules.md"])
        self.run_client(lease2).complete(check_results={"done": True})
        self.assertEqual(self.orch.execution(ex["id"])["state"], "done")
        acc = [c for c in self.kl.change_requests(state="open")["items"] if c["title"] == f"Accept {pid} D1"]
        self.assertEqual(len(acc), 1)
        self.assertEqual(self.kl.project(pid)["summary"]["deliverables"][0]["status"], "delivered")
        self.kl.approve(acc[0]["id"])
        self.assertEqual(self.kl.project(pid)["summary"]["deliverables"][0]["status"], "accepted")
        types = [e["type"] for e in self.kl.events(types=["deliverable.accepted"])["items"]]
        self.assertIn("deliverable.accepted", types)

    def test_a_runner_without_what_the_task_needs_is_refused(self):
        _, _, ex = self.start([{"key": "t1", "title": "Change the shop", "needs": ["repo:acme/shop", "python"]}])
        with self.assertRaises(KLError) as e:
            self.orch.lease(ex["id"], "t1", "m1", ["python"])
        self.assertEqual(e.exception.status, 422)
        self.assertIn("repo:acme/shop", str(e.exception))
        self.orch.lease(ex["id"], "t1", "m2", ["python", "repo:acme/shop"])

    def test_a_failed_attempt_is_retried_until_its_retries_run_out(self):
        _, _, ex = self.start([{"key": "t1", "title": "Flaky", "retries": 1, "checks": [{"id": "done"}]}])
        first = self.orch.lease(ex["id"], "t1", "m1")
        self.run_client(first).fail("the network went away")
        self.assertEqual(self.orch.execution(ex["id"])["tasks"][0]["state"], "ready")
        second = self.orch.lease(ex["id"], "t1", "m2")
        out = self.run_client(second).complete(check_results={"done": False})  # a check that did not pass
        self.assertEqual(out["state"], "failed")
        ex2 = self.orch.execution(ex["id"])
        self.assertEqual((ex2["state"], ex2["tasks"][0]["state"], ex2["tasks"][0]["attempts"]), ("failed", "failed", 2))

    def test_a_lease_nobody_renews_expires_and_its_token_with_it(self):
        _, _, ex = self.start()
        lease = self.orch.lease(ex["id"], "t1", "m1")
        run = self.run_client(lease)
        run.brief()
        self.svc.clock.advance(LEASE + 1)
        with self.assertRaises(KLError) as e:
            run.log("still here?")
        self.assertEqual(e.exception.status, 401)
        ex2 = self.orch.execution(ex["id"])
        self.assertEqual(ex2["tasks"][0]["state"], "ready")
        self.assertEqual(ex2["runs"][0]["state"], "lost")

    def test_renewals_while_the_machine_starts_keep_the_token_valid_past_its_first_lease(self):
        _, _, ex = self.start()
        lease = self.orch.lease(ex["id"], "t1", "m1")
        for _ in range(6):  # three leases' worth of waiting for a machine
            self.svc.clock.advance(LEASE * 0.5)
            self.orch.run_event(lease["run_id"], "provisioning", "still starting")
        run = self.run_client(lease)
        self.assertEqual(run.brief()["task"]["key"], "t1")  # the token injected at lease time still works
        run.event("started")
        self.assertEqual(self.orch.run(lease["run_id"])["state"], "running")

    def test_a_question_to_a_person_pauses_the_lease(self):
        _, _, ex = self.start()
        lease = self.orch.lease(ex["id"], "t1", "m1")
        run = self.run_client(lease)
        q = run.ask("Should the dashboard show refunds in euros too?")
        self.assertEqual(self.orch.run(lease["run_id"])["state"], "waiting")
        self.svc.clock.advance(LEASE * 3)  # a person takes their time
        self.assertIsNone(run.question(q["id"])["answer"])
        self.assertIn(q["id"], [x["id"] for x in self.kl.questions()])
        self.kl.answer(q["id"], "Pounds only for now.")
        self.assertEqual(run.question(q["id"])["answer"], "Pounds only for now.")
        self.assertEqual(self.orch.run(lease["run_id"])["state"], "running")

    def test_an_agent_proposes_and_a_person_decides(self):
        pid, _, ex = self.start()
        run = self.run_client(self.orch.lease(ex["id"], "t1", "m1"))
        cr = run.propose([{"op": "add_question", "project": pid, "key": "Q1", "text": "Which currencies?"}],
                         "The refund policy only names pounds.")
        self.assertEqual((cr["state"], cr["proposer"]["kind"]), ("open", "run"))
        with self.assertRaises(KLError) as e:
            run.approve(cr["id"])
        self.assertEqual(e.exception.status, 403)
        self.kl.approve(cr["id"])
        self.assertEqual(self.kl.project(pid)["record"]["questions"][0]["text"], "Which currencies?")

    def test_a_task_marked_for_a_person_waits_for_one(self):
        _, _, ex = self.start([{"key": "t1", "title": "Deploy", "gate": True, "checks": [{"id": "done"}]},
                               {"key": "t2", "title": "Announce", "after": ["t1"]}])
        out = self.run_client(self.orch.lease(ex["id"], "t1", "m1")).complete(check_results={"done": True})
        self.assertEqual(out["task_state"], "awaiting_review")
        cr = next(c for c in self.kl.change_requests(state="open")["items"] if c["title"].startswith("Accept task t1"))
        self.kl.reject(cr["id"], "the screenshot is missing")
        self.assertEqual(self.orch.execution(ex["id"])["tasks"][0]["state"], "ready")
        self.run_client(self.orch.lease(ex["id"], "t1", "m2")).complete(check_results={"done": True})
        cr = next(c for c in self.kl.change_requests(state="open")["items"] if c["title"].startswith("Accept task t1"))
        self.kl.approve(cr["id"])
        self.assertEqual([x["state"] for x in self.orch.execution(ex["id"])["tasks"]], ["done", "ready"])

    def test_a_new_plan_version_holds_only_the_tasks_it_changes(self):
        pid, pl, ex = self.start()
        self.run_client(self.orch.lease(ex["id"], "t1", "m1")).complete(check_results={"done": True})
        v2 = self.kl.propose_plan(pid, "D1", tasks=[
            {"key": "t1", "title": "List the refund approval rules", "checks": [{"id": "done"}]},
            {"key": "t2", "title": "Draft the dashboard spec, with euros", "after": ["t1"], "checks": [{"id": "done"}]}])
        state = {x["key"]: x for x in self.orch.execution(ex["id"])["tasks"]}
        self.assertEqual(state["t2"]["held_by_change_request"], v2["change_request"]["number"])
        with self.assertRaises(KLError) as e:
            self.orch.lease(ex["id"], "t2", "m2")
        self.assertEqual(e.exception.status, 409)
        self.kl.approve(v2["change_request"]["id"])
        ex2 = self.orch.execution(ex["id"])
        self.assertEqual(ex2["plan_id"], v2["id"])
        self.assertEqual({x["key"]: x["state"] for x in ex2["tasks"]}, {"t1": "done", "t2": "ready"})
        self.assertEqual(self.kl.plan(pl["id"])["state"], "superseded")

    def test_the_workspace_limits_runs_at_once(self):
        import sqlalchemy as sa
        from kl import db as t
        with self.svc.db.tx(self.admin_p.workspace_id) as c:  # runs other tests left going count too
            active = c.execute(sa.select(sa.func.count()).select_from(t.runs).where(
                t.runs.c.state.in_(("leased", "provisioning", "running", "waiting")))).scalar_one()
        self.kl._req("PATCH", "/v1/workspace/settings", {"max_concurrent_runs": active + 1})
        try:
            _, _, ex = self.start([{"key": "a", "title": "A"}, {"key": "b", "title": "B"}])
            self.orch.lease(ex["id"], "a", "m1")
            with self.assertRaises(KLError) as e:
                self.orch.lease(ex["id"], "b", "m2")
            self.assertEqual(e.exception.status, 429)
        finally:
            self.kl._req("PATCH", "/v1/workspace/settings", {"max_concurrent_runs": 50})

    def test_completing_twice_with_the_same_key_gives_the_same_answer(self):
        _, _, ex = self.start()
        run = self.run_client(self.orch.lease(ex["id"], "t1", "m1"))
        a = run.complete(check_results={"done": True}, idempotency_key="k")
        b = run.complete(check_results={"done": True}, idempotency_key="k")
        self.assertEqual((a["state"], b["state"]), ("succeeded", "succeeded"))
        with self.assertRaises(KLError) as e:
            run.complete(check_results={"done": True}, idempotency_key="other")
        self.assertEqual(e.exception.status, 409)
        with self.assertRaises(KLError):  # an ended run's token reads nothing else
            run.brief()

    def test_a_run_token_works_only_for_its_own_run(self):
        _, _, ex = self.start([{"key": "a", "title": "A"}, {"key": "b", "title": "B"}])
        la, lb = self.orch.lease(ex["id"], "a", "m1"), self.orch.lease(ex["id"], "b", "m2")
        with self.assertRaises(KLError) as e:
            RunClient("http://testserver", la["token"], lb["run_id"], http=self.http).brief()
        self.assertEqual(e.exception.status, 403)
        with self.assertRaises(KLError):
            self.run_client(la).lease(ex["id"], "b", "m3")  # a run cannot lease

    def test_the_token_is_kept_only_as_a_hash_and_never_lands_in_an_artifact(self):
        _, _, ex = self.start()
        lease = self.orch.lease(ex["id"], "t1", "m1")
        run = self.run_client(lease)
        art = run.attach("text", "env.txt", f"KL_RUN_TOKEN={lease['token']}")
        data = self.http.get(art["download"], headers=self.kl.headers).content.decode()
        self.assertEqual(data, "KL_RUN_TOKEN=[run token removed]")
        db = Path(self.svc.settings.url.replace("sqlite:///", ""))
        raw = b"".join(p.read_bytes() for p in db.parent.glob("kl.db*"))
        self.assertNotIn(lease["token"].encode(), raw)

    def test_an_openspec_deliverable_is_accepted_with_what_to_archive(self):
        pid, pl, ex = self.start(kind="openspec", change="add-refund-currency", files=change_files())
        for key in ("1.1", "1.2", "2.1"):
            run = self.run_client(self.orch.lease(ex["id"], key, f"m-{key}"))
            b = run.brief()
            self.assertEqual([r["scenario"] for r in b["requirements"]], ["Refund in euros"])
            run.complete(check_results={"done": True, "refunds/Currency/Refund in euros": True})
        acc = next(c for c in self.kl.change_requests(state="open")["items"] if c["title"] == f"Accept {pid} D1")
        self.assertIn("passed: 1 of 1", acc["reason"])
        self.kl.approve(acc["id"])
        ev = self.kl.events(types=["deliverable.accepted"])["items"][-1]["data"]
        self.assertEqual(ev["openspec"]["change"], "add-refund-currency")
        self.assertIn("openspec archive", ev["openspec"]["archive"])


if __name__ == "__main__":
    unittest.main()
