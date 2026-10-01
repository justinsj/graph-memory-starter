"""A project's thesis, the research behind its numbers, and the priorities they give (openspec/specs/impact).

Flow: the corpus, a support-metrics document, and case 01's kickoff meeting. When the meeting arrives, impact
research runs beside its change set, before review (research_before_review, the default): it opens a second change
request with the thesis, three numbers found in the metrics, and the fourth asked of Priya Patel, who asked for the
project. It applies only after the project's own; then she answers, Marcus Webb estimates the effort, and the thesis
is complete.

Portfolio: projects made through the API, to rank, to price, and to change.
"""
import copy
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kl_support as ks  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from kl import errors  # noqa: E402
from kl.api import create_app  # noqa: E402
from kl.client import Client  # noqa: E402
from kl.extractors import FixtureExtractor  # noqa: E402

sys.path.insert(0, str(ks.ROOT / "projects"))
import cases  # noqa: E402
import model  # noqa: E402

FIX = ks.ROOT / "tests" / "fixtures" / "impact"
HD = "helpdesk-migration"
THESIS = ("If support moves to a new helpdesk, the support hours lost to broken tagging reports will fall by "
          "potentially 264 hours a year, across 1,240 active clients.")


def impact_extractor() -> FixtureExtractor:
    ex = FixtureExtractor(theses=json.loads((FIX / "theses.json").read_text(encoding="utf-8")))
    ex.by_name.update(FixtureExtractor(FIX / "extraction").by_name)
    return ex


class Flow(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        svc, _, admin = cls.svc, _, cls.admin = ks.seeded(cls.tmp)
        svc.extractor = impact_extractor()
        svc.ingest(admin, name="support-metrics.md", data=(FIX / "support-metrics.md").read_bytes())
        cls.priya, _ = ks.person(svc, admin, "priya@acme.example", "Priya Patel", "approver")
        cls.marcus, _ = ks.person(svc, admin, "marcus@acme.example", "Marcus Webb", "editor")
        case = cases.load(ks.ROOT / "projects" / "cases" / "01-new-project")
        r = svc.ingest(admin, name="2026-09-14-support-tooling-review.md", kind="transcript", text=case["text"],
                       changes=case["diff"]["changes"], on="2026-09-14")
        cls.job_result = r["job"]["result"]
        cls.open_before_review = svc.list_change_requests(admin, state="open")["items"]
        cls.research_cr = copy.deepcopy(svc.get_change_request(admin, cls.job_result["research"]))
        try:  # before the project exists
            svc.approve_change_request(admin, cls.research_cr["id"])
            cls.too_early = None
        except errors.Conflict as e:
            cls.too_early = e
        svc.approve_change_request(admin, cls.job_result["change_request"])
        svc.approve_change_request(admin, cls.research_cr["id"], note="the numbers check out")
        cls.after_research = svc.project_impact(admin, HD)
        cls.asked_events = [e["data"] for e in svc.list_events(admin, types=["number.asked"])["items"]]
        cls.answer = svc.answer_number(cls.priya, HD, "hours_per_failure",
                                       {"value": 6, "answer": "About 6 hours per agent, rebuilding the queues by hand."},
                                       approve=True)
        effort = svc.estimate_effort(cls.marcus, HD, {"days": 15, "basis": "the shortlist, a migration plan, and "
                                                                           "importing the ticket history"})
        svc.approve_change_request(admin, effort["id"])
        cls.final = svc.project_impact(admin, HD)
        cls.record = svc._records(admin.workspace_id)[HD]
        _, _, cls.snap = svc.projector.ensure(admin.workspace_id)
        cls.context = svc.context(admin, "What is the projected impact of the helpdesk migration?")["text"]

    @classmethod
    def tearDownClass(cls):
        cls.svc.close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_a_new_project_gets_a_draft_thesis_and_its_numbers_researched(self):
        self.assertEqual(sorted(c["id"] for c in self.open_before_review),  # both open before anyone reviews
                         sorted([self.job_result["change_request"], self.job_result["research"]]))
        self.assertIsNotNone(self.too_early)  # it adds to the project change request 1 creates: 409 until then
        self.assertIn("approve the change request that creates it first", self.too_early.detail)
        cr = self.research_cr
        self.assertEqual((cr["title"], cr["proposer"]["name"]), (f"Thesis and impact research for {HD}",
                                                                 "impact research"))
        self.assertEqual([o["op"] for o in cr["ops"]], ["set_thesis"] + ["set_number"] * 4)
        self.assertEqual({o["key"]: o["status"] for o in cr["ops"][1:]},
                         {"failures_a_year": "found", "support_agents": "found", "hours_per_failure": "asked",
                          "active_clients": "found"})
        self.assertEqual(self.record["thesis"]["because"],  # the meeting line, traced to its input
                         {"source": "inputs/2026-09-14-support-tooling-review.md",
                          "quote": "Tagging reports broke again this week."})

    def test_a_number_found_in_a_document_is_recorded_with_its_sentence(self):
        n = next(x for x in self.record["numbers"] if x["key"] == "failures_a_year")
        self.assertEqual((n["status"], n["value"], n["found_in"]),
                         ("found", 11, {"source": "docs/support-metrics.md",
                                        "quote": "Tagging reports failed 11 times over the past year."}))
        self.assertEqual(model.check_record(self.record, self.snap), [])
        bad = copy.deepcopy(self.record)
        next(x for x in bad["numbers"] if x["key"] == "failures_a_year")["found_in"]["quote"] = \
            "Tagging reports failed 3 times over the past year."
        self.assertTrue(any("quote not in docs/support-metrics.md" in p for p in model.check_record(bad, self.snap)))

    def test_a_number_no_document_holds_is_asked_of_the_person_the_project_names(self):
        self.assertEqual(self.asked_events, [{
            "project": HD, "key": "hours_per_failure", "label": "hours each agent loses per failure",
            "unit": "hours per agent", "ask": "Priya Patel", "change_request": self.research_cr["id"],
            "question": "When the tagging reports fail, about how many hours does each agent lose?"}])
        self.assertFalse(self.after_research["complete"])
        self.assertEqual(self.after_research["missing"], ["hours_per_failure"])
        self.assertIn("still being researched (2 of 3 numbers in)", self.after_research["thesis"])
        self.assertEqual(self.after_research["priority"]["unranked"],
                         "numbers still being researched: hours_per_failure")
        hook = self.svc.create_webhook(self.admin, "https://questions.example.com/kl", ["number.asked"])
        self.assertEqual(hook["types"], ["number.asked"])  # whatever routes questions to people can subscribe

    def test_the_answer_fills_the_number_in_and_completes_the_thesis(self):
        self.assertEqual(self.answer["state"], "applied")  # Priya approved her own answer: one approval is enough
        f = self.final
        self.assertEqual(f["thesis"], THESIS)
        self.assertEqual(f["working"], "11 failures a year × 4 agents × 6 hours per agent = 264 hours a year")
        self.assertEqual((f["value"], f["effort_days"], f["per_day"], f["estimated"]), (264, 15, 17.6, []))
        self.assertEqual(f["priority"]["place"], 1)
        n = next(x for x in self.record["numbers"] if x["key"] == "hours_per_failure")
        self.assertEqual((n["status"], n["value"], n["by"]), ("answered", 6, "Priya Patel"))
        self.assertIn("Projected impact: 264 hours a year", self.context)


def build_project(svc, p, pid, unit, numbers, days=None, owner="Sarah Chen", status="planning"):
    """One project, its thesis, numbers and effort, in one change request a person approves at once.
    numbers: [(key, label, unit, value or None, "answered" | "estimated")]"""
    ops = [{"op": "create_project", "project": pid, "title": pid.replace("-", " ").capitalize(),
            "description": f"The {pid} project"},
           {"op": "set_status", "project": pid, "value": status},
           {"op": "set_field", "project": pid, "field": "owner", "value": owner},
           {"op": "set_thesis", "project": pid, "change": f"{pid} is done", "outcome": f"the {unit} lost",
            "direction": "reduce", "unit": unit, "formula": [n[0] for n in numbers]}]
    for key, label, u, value, how in numbers:
        if value is None:
            ops.append({"op": "set_number", "project": pid, "key": key, "label": label, "unit": u,
                        "status": "asked", "ask": owner, "question": f"How many {label}?"})
        else:
            ops.append({"op": "set_number", "project": pid, "key": key, "label": label, "unit": u, "status": how,
                        "value": value, "by": owner, **({"basis": "a rough count"} if how == "estimated" else {})})
    if days:
        ops.append({"op": "set_effort", "project": pid, "days": days, "by": owner})
    cr = svc.propose_changes(p, ops, "portfolio", approve=True)
    assert cr["state"] == "applied", cr
    return cr


class Portfolio(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.svc = ks.make_service(cls.tmp)
        cls.boot, cls.admin = ks.workspace(cls.svc)
        ks.ingest_corpus(cls.svc, cls.admin, names=["org-chart.md"])
        s, p = cls.svc, cls.admin
        build_project(s, p, "alpha", "hours a year", [("fails", "failures", "failures a year", 11, "answered"),
                                                      ("agents", "agents", "agents", 4, "answered"),
                                                      ("hours", "hours per failure", "hours", 6, "answered")], 15)
        build_project(s, p, "bravo", "hours a year", [("hours", "hours saved", "hours a year", 100, "answered")], 2)
        build_project(s, p, "charlie", "refunds a month", [("refunds", "refunds", "refunds a month", 30, "answered")],
                      3)
        build_project(s, p, "delta", "hours a year", [("hours", "hours saved", "hours a year", None, "answered")], 5)
        build_project(s, p, "foxtrot", "tickets a month", [("tickets", "tickets", "tickets a month", 40, "answered")],
                      4)
        build_project(s, p, "golf", "tickets a month", [("tickets", "tickets", "tickets a month", 30, "estimated")],
                      2)
        cls.http = TestClient(create_app(cls.svc, mcp=False))
        cls.client = Client("http://testserver", cls.boot["key"], http=cls.http)

    @classmethod
    def tearDownClass(cls):
        cls.svc.close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def order(self, unit):
        return [x["project"] for x in self.svc.priorities(self.admin)["by_unit"].get(unit, [])]

    def test_a_project_missing_numbers_is_not_ranked(self):
        prio = self.svc.priorities(self.admin)
        unranked = {x["project"]: (x["reason"], x["missing"]) for x in prio["unranked"]}
        self.assertEqual(unranked["delta"], ("numbers still being researched: hours", ["hours"]))
        self.assertNotIn("delta", self.order("hours a year"))

    def test_projects_are_ranked_by_projected_impact_per_person_day(self):
        prio = self.svc.priorities(self.admin)
        self.assertEqual(prio["basis"], "impact per person-day, within each unit")
        self.assertEqual(self.order("hours a year"), ["bravo", "alpha"])  # 50 a person-day, then 17.6
        self.assertEqual(self.order("refunds a month"), ["charlie"])
        listed = [x["id"] for x in self.svc.list_projects(self.admin, sort="priority")["items"]]
        self.assertLess(listed.index("bravo"), listed.index("alpha"))
        self.assertGreater(listed.index("delta"), max(listed.index(x) for x in ("alpha", "bravo", "charlie")))
        alpha = next(x for x in self.svc.list_projects(self.admin, sort="priority")["items"] if x["id"] == "alpha")
        self.assertEqual((alpha["impact"]["projected_impact"], alpha["impact"]["impact_per_day"]), (264, 17.6))

    def test_a_value_per_unit_ranks_across_units_in_money(self):
        self.svc.update_settings(self.admin, {"unit_values": {"hours a year": 45, "refunds a month": 20,
                                                              "tickets a month": 5}})
        try:
            prio = self.svc.priorities(self.admin)
        finally:
            self.svc.update_settings(self.admin, {"unit_values": {}})
        self.assertEqual(prio["basis"], "money per person-day")
        ranked = [x["project"] for x in prio["ranked"]]
        self.assertEqual(ranked[:3], ["bravo", "alpha", "charlie"])  # 2,250, 792 and 200 a person-day
        self.assertEqual(sorted(ranked[3:]), ["foxtrot", "golf"])
        money = [x["money_per_day"] for x in prio["ranked"]]
        self.assertEqual(money, sorted(money, reverse=True))
        self.assertEqual(prio["ranked"][1]["money"], 11880)

    def test_an_approved_number_change_updates_the_priority(self):
        self.assertEqual(self.order("tickets a month"), ["golf", "foxtrot"])  # 15 a person-day, then 10
        cr = self.svc.answer_number(self.admin, "foxtrot", "tickets", {"value": 100, "answer": "100 tickets a month."})
        self.assertIn("needs a careful look: # number       foxtrot tickets: 100 tickets a month (answered, by Acme "
                      "Admin)", cr["notes"])  # a known number changed: flagged for the reviewer
        self.assertEqual(self.order("tickets a month"), ["golf", "foxtrot"])  # nothing changes until approved
        self.svc.approve_change_request(self.admin, cr["id"])
        self.assertEqual(self.order("tickets a month"), ["foxtrot", "golf"])  # 25 a person-day now
        self.assertEqual(self.svc.project_impact(self.admin, "foxtrot")["value"], 100)

    def test_an_estimate_stays_marked_as_one(self):
        golf = self.svc.project_impact(self.admin, "golf")
        self.assertEqual(golf["estimated"], ["tickets"])
        self.assertEqual(golf["working"], "30 tickets a month (estimated) = 30 tickets a month")
        n = golf["numbers"][0]
        self.assertEqual((n["status"], n["by"], n["basis"]), ("estimated", "Sarah Chen", "a rough count"))
        self.assertEqual(next(x for x in self.svc.priorities(self.admin)["by_unit"]["tickets a month"]
                              if x["project"] == "golf")["estimated"], ["tickets"])

    def test_documents_that_disagree_are_not_guessed_between(self):
        s, p = self.svc, self.admin
        for name, title, lines, value in (
                ("refund-report-june.md", "Refund report, June",
                 ["The June refund report covers card and bank refunds.",
                  "Refunds were issued 120 times last month.", "Most were for late deliveries."], 120),
                ("refund-dashboard-notes.md", "Refund dashboard notes",
                 ["Notes from the refund dashboard, taken by the finance team in July.",
                  "The dashboard says refunds were issued 150 times last month.", "None were disputed."], 150)):
            quote = lines[1]
            s.ingest(p, name=name, text=f"---\ntitle: {title}\n---\n" + "\n".join(lines) + "\n", extraction={
                "source_doc": name, "nodes": [{"name": title, "type": "DOCUMENT", "claims": [
                    {"kind": "note", "text": quote.rstrip("."), "quote": quote, "amount": value,
                     "unit": "refunds a month"}]}], "edges": [], "aliases": []})
        s.create_project(p, {"id": "refund-speed", "title": "Refund speed", "description": "Faster refunds",
                             "owner": "Sarah Chen", "status": "planning"}, approve=True)
        cr = s.propose_thesis(p, "refund-speed", {
            "change": "refunds are issued automatically", "outcome": "the refunds handled by hand",
            "direction": "reduce", "unit": "refunds a month", "formula": ["refunds"],
            "numbers": [{"key": "refunds", "label": "refunds issued", "unit": "refunds a month"}]})
        number = next(o for o in cr["ops"] if o["op"] == "set_number")
        self.assertEqual((number["status"], number["ask"]), ("asked", "Sarah Chen"))
        self.assertIn("the documents disagree (150 in docs/refund-dashboard-notes.md; 120 in "
                      "docs/refund-report-june.md), so asked Sarah Chen", cr["reason"])

    def test_a_number_not_in_its_quote_is_refused(self):
        s, p = self.svc, self.admin
        text = "# Refunds call, 20 September 2026\nSarah: Refunds are slow. We issued 120 last month.\n"
        r = s.ingest(p, name="2026-09-20-refunds-call.md", kind="transcript", text=text, on="2026-09-20", changes=[
            {"op": "set_number", "project": "alpha", "key": "fails", "status": "found", "value": 12,
             "quote": "We issued 120 last month."}])
        cr = s.get_change_request(p, r["job"]["result"]["change_request"])
        self.assertTrue(any("12 is not in the quote" in x for x in cr["problems"]), cr["problems"])
        with self.assertRaises(errors.Invalid) as e:  # found elsewhere: the sentence must be in that document
            s.propose_changes(p, [{"op": "set_number", "project": "alpha", "key": "agents", "status": "found",
                                   "value": 5, "found_in": {"source": "docs/org-chart.md",
                                                            "quote": "Support has 5 agents."}}])
        self.assertTrue(any("found_in: quote not in docs/org-chart.md" in x for x in e.exception.problems),
                        e.exception.problems)

    def test_the_impact_calls_work_over_http(self):
        c = self.client
        c.create_project(id="helpdesk-http", title="Helpdesk over HTTP", description="Over HTTP",
                         owner="Priya Patel", status="planning", approve=True)
        cr = c.propose_thesis("helpdesk-http", approve=True, change="support moves to a new helpdesk",
                              outcome="the support hours lost to broken tagging reports", direction="reduce",
                              unit="hours a year", formula=["hours"],
                              numbers=[{"key": "hours", "label": "hours lost to tagging", "unit": "hours a year"}])
        self.assertEqual(cr["state"], "applied")
        again = c.research("helpdesk-http")
        self.assertEqual((again["change_request"], again["notes"]),
                         (None, ["hours: not in the graph, still waiting on Priya Patel"]))
        self.assertEqual(c.answer_number("helpdesk-http", "hours", 60, answer="About 60 hours a year.",
                                         approve=True)["state"], "applied")
        self.assertEqual(c.estimate_effort("helpdesk-http", 3, basis="a week of setup", approve=True)["state"],
                         "applied")
        imp = c.impact("helpdesk-http")
        self.assertEqual(imp["thesis"], "If support moves to a new helpdesk, the support hours lost to broken tagging "
                                        "reports will fall by potentially 60 hours a year.")
        self.assertEqual(imp["per_day"], 20)
        self.assertIn("helpdesk-http", [x["project"] for x in c.priorities()["by_unit"]["hours a year"]])
        listed = c.projects(sort="priority", include="impact")["items"]
        self.assertEqual(next(x for x in listed if x["id"] == "helpdesk-http")["impact"]["projected_impact"], 60)


if __name__ == "__main__":
    unittest.main()
