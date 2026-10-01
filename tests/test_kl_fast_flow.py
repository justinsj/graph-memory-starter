"""Turning an input into a project, fast: research before review, one model call or two at once, no graph rebuilds.

Research before review: the thesis and its numbers are opened as a change request beside the input's own, checked
against the records as the input's would leave them, so the reviewer weighs the impact with the changes.
The thesis comes from the extractor's one call (thesis_call merged), a second call at the same time (parallel),
or is drafted from the proposed project (separate, and whenever the extractor can do neither).
Preloaded: each call is told that what it is given is all there is, so it answers at once; only when nothing was
left out (every project among the candidates, every figure under FACTS_SHOWN), and not when preload_note is off.
Deferred graph updates: the process reads the graph as last built and never rebuilds it; each change it makes is a
line of the pending diff, taken in by the next read that needs a current graph, or by apply_pending.
"""
import json
import shutil
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kl_support as ks  # noqa: E402
from kl import errors  # noqa: E402
from kl.extractors import FixtureExtractor  # noqa: E402

sys.path.insert(0, str(ks.ROOT / "projects"))
import cases  # noqa: E402
import ingest  # noqa: E402

FIX = ks.ROOT / "tests" / "fixtures" / "impact"
HD = "helpdesk-migration"
CASE = cases.load(ks.ROOT / "projects" / "cases" / "01-new-project")
THESES = json.loads((FIX / "theses.json").read_text(encoding="utf-8"))
NAME = "2026-09-14-support-tooling-review.md"


class Fake(FixtureExtractor):
    """The case's change set and thesis, from whichever call the service makes; each call counted."""

    def __init__(self, merged=False, parallel=False):
        super().__init__(theses=THESES)
        self.by_name.update(FixtureExtractor(FIX / "extraction").by_name)
        self.calls, self.threads, self.preloaded = [], set(), {}
        self.together = threading.Barrier(2, timeout=10) if parallel else None  # passes only if both run at once
        if merged:
            self.propose_with_thesis = self._both
        if parallel:
            self.draft_thesis_from_input = self._from_input

    def propose_changes(self, text, path, kind, on, records, entities, preloaded=False):
        self.calls.append("changes")
        self.preloaded["changes"] = preloaded
        self.threads.add(threading.get_ident())
        if self.together and "draft_thesis_from_input" in vars(self):
            self.together.wait()
        return CASE["diff"]["changes"]

    def _both(self, text, path, kind, on, records, entities, figures, preloaded=False):
        self.calls.append("both")
        self.preloaded["both"] = preloaded
        assert "Support serves 1,240 active clients." in figures  # the graph's figures reach the call
        return CASE["diff"]["changes"], THESES[HD]

    def _from_input(self, text, path, figures, preloaded=False):
        self.calls.append("thesis from input")
        self.preloaded["thesis"] = preloaded
        self.threads.add(threading.get_ident())
        self.together.wait()
        return THESES[HD]

    def draft_thesis(self, record, sources, facts):
        self.calls.append("thesis from project")
        return super().draft_thesis(record, sources, facts)


def workspace(tmp, extractor, **settings):
    svc, _, admin = ks.seeded(tmp, **settings)
    svc.extractor = extractor
    svc.ingest(admin, name="support-metrics.md", data=(FIX / "support-metrics.md").read_bytes())
    svc.projector.apply_pending(admin.workspace_id)  # the document is in the graph before the meeting arrives
    return svc, admin


class ResearchBeforeReview(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        self.svc.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def ingest(self, extractor, **settings):
        self.svc, self.admin = workspace(self.tmp, extractor, **settings)
        return self.svc.ingest(self.admin, name=NAME, kind="transcript", text=CASE["text"], on="2026-09-14")

    def test_the_thesis_waits_for_review_beside_the_changes(self):
        r = self.ingest(Fake())
        opened = {c["id"]: c for c in self.svc.list_change_requests(self.admin, state="open")["items"]}
        self.assertEqual(len(opened), 2)
        research = opened[r["job"]["result"]["research"]]
        self.assertEqual(research["title"], f"Thesis and impact research for {HD}")
        ops = [o["op"] for o in research["ops"]]
        self.assertEqual(ops, ["set_thesis"] + ["set_number"] * 4)
        found = [o for o in research["ops"] if o.get("status") == "found"]
        self.assertEqual(sorted(o["value"] for o in found), [4, 11, 1240])
        self.assertEqual([o["ask"] for o in research["ops"] if o.get("status") == "asked"], ["Priya Patel"])
        self.assertEqual(research["problems"], [])

    def test_the_research_applies_after_the_project(self):
        r = self.ingest(Fake())
        research = r["job"]["result"]["research"]
        with self.assertRaises(errors.Problem):  # before its project exists, it cannot apply
            self.svc.approve_change_request(self.admin, research)
        self.svc.approve_change_request(self.admin, r["job"]["result"]["change_request"])
        self.assertEqual(len(self.svc.list_change_requests(self.admin, state="open")["items"]), 1)  # no second draft
        self.svc.approve_change_request(self.admin, research)
        rec = self.svc._records(self.admin.workspace_id)[HD]
        self.assertEqual(rec["thesis"]["because"]["source"], f"inputs/{NAME}")
        self.assertEqual(sorted(n["status"] for n in rec["numbers"]), ["asked", "found", "found", "found"])

    def test_one_call_writes_both_when_merged(self):
        ex = Fake(merged=True)
        self.ingest(ex, thesis_call="merged")
        self.assertEqual(ex.calls, ["both"])

    def test_two_calls_run_at_once_when_parallel(self):
        ex = Fake(parallel=True)
        self.ingest(ex, thesis_call="parallel")
        self.assertEqual(sorted(ex.calls), ["changes", "thesis from input"])
        self.assertEqual(len(ex.threads), 2)

    def test_separate_drafts_from_the_proposed_project(self):
        ex = Fake(merged=True, parallel=True)
        ex.together = None  # no second call to wait for
        self.ingest(ex, thesis_call="separate")
        self.assertEqual(ex.calls, ["changes", "thesis from project"])

    def test_each_call_is_told_it_has_everything(self):
        ex = Fake(parallel=True)
        self.ingest(ex, thesis_call="parallel")
        self.assertEqual(ex.preloaded, {"changes": True, "thesis": True})

    def test_not_the_thesis_when_a_figure_was_left_out(self):
        ex = Fake(parallel=True)
        with mock.patch("kl.impact.FACTS_SHOWN", 1):  # the workspace's figures are more than one
            self.ingest(ex, thesis_call="parallel")
        self.assertEqual(ex.preloaded, {"changes": True, "thesis": False})

    def test_nor_when_the_note_is_off(self):
        ex = Fake(merged=True)
        self.ingest(ex, thesis_call="merged", preload_note=False)
        self.assertEqual(ex.preloaded, {"both": False})

    def test_after_approval_as_before_when_asked(self):
        ex = Fake(merged=True)
        r = self.ingest(ex, research_before_review=False)
        self.assertNotIn("research", r["job"]["result"])
        self.assertEqual(ex.calls, ["changes"])
        self.svc.approve_change_request(self.admin, r["job"]["result"]["change_request"])
        titles = [c["title"] for c in self.svc.list_change_requests(self.admin, state="open")["items"]]
        self.assertEqual(titles, [f"Thesis and impact research for {HD}"])


class DeferredGraphUpdates(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.svc, cls.admin = workspace(cls.tmp, Fake())
        ws = cls.admin.workspace_id
        cls.built = json.loads((cls.svc.projector.folder(ws) / "current.json").read_text(encoding="utf-8"))
        builds = []
        real = cls.svc.projector.build
        cls.svc.projector.build = lambda *a, **k: builds.append(a) or real(*a, **k)
        r = cls.svc.ingest(cls.admin, name=NAME, kind="transcript", text=CASE["text"], on="2026-09-14")
        cls.svc.approve_change_request(cls.admin, r["job"]["result"]["change_request"])
        cls.svc.approve_change_request(cls.admin, r["job"]["result"]["research"])
        cls.builds = list(builds)
        cls.after = json.loads((cls.svc.projector.folder(ws) / "current.json").read_text(encoding="utf-8"))
        cls.pending = cls.svc.projector.pending(ws)
        cls.applied = cls.svc.projector.apply_pending(ws)
        cls.left = cls.svc.projector.pending(ws)
        cls.answer = cls.svc.context(cls.admin, "Who asked for the helpdesk migration?")["text"]

    @classmethod
    def tearDownClass(cls):
        cls.svc.close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_the_process_never_rebuilds_the_graph(self):
        self.assertEqual(self.builds, [])
        self.assertEqual(self.after, self.built)

    def test_what_it_changed_is_saved_for_later(self):
        kinds = [(e["change"], e.get("kind") or e.get("change_request")) for e in self.pending]
        self.assertIn(("source", "transcript"), kinds)
        applied = [e for e in self.pending if e["change"] == "records"]
        self.assertEqual(len(applied), 2)  # the project, then its research
        self.assertTrue(all(e["projects"] == [HD] for e in applied))

    def test_applied_later_the_graph_knows_the_project(self):
        self.assertEqual(self.applied["applied"], len(self.pending))
        self.assertEqual(self.left, [])
        self.assertIn("Helpdesk migration requested_by Priya Patel", self.answer)

    def test_a_document_is_never_left_out(self):
        pj, ws = self.svc.projector, self.admin.workspace_id
        with self.svc.db.tx(ws) as c:
            self.svc.bump(c, ws)  # as a document's activation does
        pj.defer(ws, {"change": "source", "kind": "document", "path": "new-policy.md"})
        _, version, _ = pj.current(ws)  # the project process's read takes the document in
        self.assertEqual(pj.pending(ws), [])
        self.assertEqual(version, json.loads((pj.folder(ws) / "current.json").read_text(encoding="utf-8"))["version"])


class Envelope(unittest.TestCase):

    def test_the_project_given_once_belongs_to_each_change(self):
        changes, thesis = ingest.parse_all('{"project": "p", "changes": [{"op": "set_status", "value": "planning", '
                                           '"quote": "q"}, {"op": "add_question", "project": "other", "key": "Q1", '
                                           '"text": "t", "quote": "q"}], "thesis": {"change": "c"}}')
        self.assertEqual([c["project"] for c in changes], ["p", "other"])
        self.assertEqual(thesis, {"change": "c"})

    def test_the_payload_says_it_is_everything_only_when_nothing_was_cut(self):
        rec = next(iter(cases.load(ks.ROOT / "projects" / "cases" / "02-progress-update")["before"].values()))

        def opening(records, preloaded=True):
            sent = []
            ingest.propose("inputs/note.md", "Nothing new.", records, [], on="2026-09-14", repair=False,
                           preloaded=preloaded, llm=lambda prompt, body: sent.append(body) or '{"changes": []}')
            return sent[0].split("\n", 1)[0]

        self.assertTrue(opening({}).startswith("Preloaded: "))
        self.assertTrue(opening({rec["id"]: rec}).startswith("Preloaded: "))
        many = {f"p{i}": {**rec, "id": f"p{i}"} for i in range(ingest.CANDIDATES + 1)}
        self.assertTrue(opening(many).startswith("Input: "))  # a project was left out of the candidates
        self.assertTrue(opening({}, preloaded=False).startswith("Input: "))

    def test_the_merged_instructions_hold_both(self):
        both = ingest.with_thesis(ingest.PROMPT.read_text(encoding="utf-8"))
        self.assertIn("How to read an input into project changes", both)
        self.assertIn("You draft the thesis for one project", both)


if __name__ == "__main__":
    unittest.main()
