"""Projects end to end, without a model: records into the graph, questions answered
from them, and the scripts that change them (plan, status, review, ingest, the digest).

The records are the cases replayed in order (projects/cases.py story()): as they
stand on 26 September 2026, asked about on 28 September.
"""
import contextlib
import io
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
import graphs  # noqa: E402,F401  pins GRAPH_MEMORY_TODAY, puts src/ on the path
import build_graph  # noqa: E402
import recall  # noqa: E402

sys.path.insert(0, str(ROOT / "projects"))
import board  # noqa: E402
import cases  # noqa: E402
import ingest  # noqa: E402
import model  # noqa: E402
import plan  # noqa: E402
import review  # noqa: E402
import status  # noqa: E402

sys.path.insert(0, str(ROOT / "digest"))
import common  # noqa: E402

NOW = date(2026, 9, 28)
HD, RD = "helpdesk-migration", "refunds-dashboard"
ENTITIES = model.entities_from_extraction(ROOT / "extraction")
NAMES = model.name_map(ENTITIES)
DISCUSSION = json.loads((cases.CASES / "inputs/discussions/2026-09-15-helpdesk-migration.json")
                        .read_text(encoding="utf-8"))


def story_graph(folder: Path) -> Path:
    """The story's records and history, built into folder/g.db beside the repo's documents."""
    records, events = cases.story()
    model.save_records(folder / "records", records, events)
    db = folder / "g.db"
    build_graph.build(db_path=db, records=folder / "records", records_root=cases.CASES, now=NOW)
    return db


class Build(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.db = story_graph(cls.tmp)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def rows(self, sql, *args):
        with closing(sqlite3.connect(self.db)) as db:
            return db.execute(sql, args).fetchall()

    def pid(self, slug):
        return self.rows("SELECT entity_id FROM projects WHERE slug = ?", slug)[0][0]

    def test_projects_and_deliverables_are_entities(self):
        self.assertEqual(self.rows("SELECT type, COUNT(*) FROM entities WHERE type IN ('PROJECT', 'DELIVERABLE') "
                                   "GROUP BY type ORDER BY type"), [("DELIVERABLE", 4), ("PROJECT", 2)])

    def test_a_project_is_found_by_its_title_and_its_alias(self):
        norms = {n for (n,) in self.rows("SELECT norm FROM names WHERE entity_id = ?", self.pid(HD))}
        self.assertEqual(norms, {"helpdesk migration", "new helpdesk"})

    def test_the_status_history_is_dated_claims(self):
        self.assertEqual(self.rows("SELECT text, valid_from, valid_to FROM claims WHERE entity_id = ? "
                                   "AND kind = 'status' ORDER BY valid_from", self.pid(HD)),
                         [("Status: planning", "2026-09-14", "2026-09-15"),
                          ("Status: active", "2026-09-15", "2026-09-26"),
                          ("Status: blocked", "2026-09-26", None)])

    def test_links_join_the_projects_to_the_graph(self):
        links = set(self.rows("SELECT s.name, r.predicate, t.name, r.valid_from FROM relations r "
                              "JOIN entities s ON s.id = r.source_id JOIN entities t ON t.id = r.target_id "
                              "WHERE s.type = 'PROJECT'"))
        for want in [("Helpdesk migration", "subject_to", "Supplier payments", "2026-09-14"),
                     ("Helpdesk migration", "depends_on", "Tooling inventory", "2026-09-14"),
                     ("Helpdesk migration", "owned_by", "Priya Patel", "2026-09-15"),
                     ("Refunds dashboard", "depends_on", "Helpdesk migration", "2026-09-25"),
                     ("Refunds dashboard", "requested_by", "Sarah Chen", "2026-09-25")]:
            self.assertIn(want, links)

    def test_the_plan_its_order_the_sources_and_the_history_have_tables(self):
        self.assertEqual(self.rows("SELECT n, status FROM steps WHERE project_id = ? ORDER BY n", self.pid(HD)),
                         [(1, "done"), (2, "done"), (3, "blocked"), (4, "todo"), (5, "todo")])
        self.assertEqual(self.rows("SELECT COUNT(*) FROM step_after")[0][0], 4)
        self.assertEqual(len(self.rows("SELECT doc FROM sources WHERE project_id = ?", self.pid(HD))), 4)
        self.assertEqual(self.rows("SELECT on_date, op, subject, old, new FROM events WHERE project_id = ? "
                                   "ORDER BY id DESC LIMIT 1", self.pid(HD))[0],
                         ("2026-09-26", "add_decision", None, None,
                          "Keep the old helpdesk read-only for 90 days after go-live, then close it"))
        self.assertEqual(self.rows("SELECT status, status_from, plan_version FROM projects WHERE slug = ?", HD),
                         [("blocked", "2026-09-26", 1)])

    def test_the_build_line_counts_projects(self):
        records = self.tmp / "records"
        result = build_graph.build(db_path=self.tmp / "again.db", records=records, records_root=cases.CASES, now=NOW)
        self.assertTrue(build_graph.summary(result).startswith(
            "built again.db: 20 entities, 54 claims, 25 relations, 11 aliases from 9 docs and 2 projects"))
        self.assertEqual(result["checks"], [])

    def test_a_record_whose_quote_is_not_in_its_input_stops_the_build(self):
        folder = self.tmp / "bad"
        shutil.copytree(self.tmp / "records", folder)
        rec = json.loads((folder / f"{HD}.json").read_text(encoding="utf-8"))
        rec["description"]["quote"] = "We must move helpdesks at once."
        (folder / f"{HD}.json").write_text(json.dumps(rec), encoding="utf-8")
        with self.assertRaises(SystemExit) as stop:
            build_graph.build(db_path=self.tmp / "bad.db", records=folder, records_root=cases.CASES, now=NOW)
        self.assertIn("the project records need fixing first", str(stop.exception))

    def test_no_records_builds_the_graph_as_before(self):
        result = build_graph.build(db_path=self.tmp / "plain.db", records=self.tmp / "none", now=NOW)
        self.assertEqual((result["entities"], result["projects"]), (14, 0))


class Answers(unittest.TestCase):
    """What the hook tells the model, asked on 28 September."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.db = story_graph(cls.tmp)
        cls.saved, recall.DB = recall.DB, cls.db

    @classmethod
    def tearDownClass(cls):
        recall.DB = cls.saved
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def ask(self, question):
        return recall.recall(question, now=NOW).as_text()

    def test_the_status_comes_first_with_why_and_the_plan_in_a_line(self):
        text = self.ask("What's the status of the helpdesk migration?")
        self.assertIn('Helpdesk migration: Status: blocked (from 2026-09-26), on the words "Then the helpdesk '
                      'migration is blocked until he\'s back." [inputs/2026-09-26-ops-sync.md]', text)
        self.assertIn("Helpdesk migration: plan v1 agreed 2026-09-15; 2 of 5 steps done; due 2027-01-04", text)
        self.assertIn("Helpdesk migration: blocked: step 3, Founder signs the contract (Alex Doyle)", text)
        self.assertTrue(text.startswith("memory: 8 facts, as of 2026-09-28; 1 project\nThese facts come from "
                                        "your documents (9, extracted"))
        self.assertIn("and project records (2, updated 2026-09-26)", text)

    def test_the_sign_off_is_walked_from_the_project_to_the_person(self):
        text = self.ask("Who has to sign off the helpdesk contract?")
        for line in ("Helpdesk migration subject_to Supplier payments", "Supplier payments approved_by Founder",
                     "Founder held_by Alex Doyle"):
            self.assertIn(line, text)

    def test_deliverables_are_left_out_unless_asked_for(self):
        self.assertNotIn(" delivers ", self.ask("What's the status of the helpdesk migration?"))
        text = self.ask("What are the deliverables of the helpdesk migration?")
        self.assertIn("Helpdesk migration: D1 Shortlist of three helpdesks: delivered (Marcus Webb, due 2026-09-23)",
                      text)

    def test_the_whole_plan_when_asked_for(self):
        text = self.ask("What is the plan for the helpdesk migration?")
        self.assertIn("Helpdesk migration: done: step 1, Shortlist three helpdesks (Marcus Webb, due 2026-09-23)", text)
        self.assertIn("Helpdesk migration: todo: step 5, Import ticket history and go live "
                      "(Priya Patel, due 2027-01-04)", text)

    def test_a_past_date_gets_that_days_status_and_nothing_learnt_later(self):
        text = self.ask("What was the status of the helpdesk migration on 14 September?")
        self.assertIn("Status: planning", text)
        for later in ("Status: active", "Owned by", "Refunds dashboard", "plan v1"):
            self.assertNotIn(later, text)

    def test_what_changed_is_the_history_newest_first(self):
        text = self.ask("What changed on the helpdesk migration?")
        self.assertIn("Helpdesk migration: 2026-09-26 status active → blocked", text)
        self.assertLess(text.index("2026-09-26 status active → blocked"), text.index("2026-09-24 step 1 todo → done"))

    def test_a_question_about_projects_that_names_none(self):
        text = self.ask("Is anything blocked right now?")
        self.assertIn("1 blocked project, as of 2026-09-28:", text)
        self.assertIn("Helpdesk migration: blocked since 2026-09-26; owner Priya Patel; 2 of 5 steps done", text)
        self.assertIn("no overdue projects, as of 2026-09-28", self.ask("Is any project overdue?"))

    def test_what_a_person_is_working_on(self):
        text = self.ask("Which projects is Marcus working on?")
        self.assertIn("1 project involving Marcus Webb", text)
        self.assertIn("Helpdesk migration: Marcus Webb: step 1 done, step 2 done", text)

    def test_a_project_name_wins_over_an_alias_inside_it(self):
        text = self.ask("What does the refunds dashboard depend on?")
        self.assertIn("Refunds dashboard depends_on Helpdesk migration", text)
        self.assertNotIn("Refund approvals:", text)  # "refunds" is the policy's alias

    def test_document_questions_are_answered_as_before(self):
        text = self.ask(graphs.REFUND)
        self.assertNotIn("projects:", text)
        self.assertIn("Marcus Webb", text)

    def test_quick_enough_for_the_hook(self):
        facts = recall.recall("What's the status of the helpdesk migration?", now=NOW)
        self.assertLess(facts.ms, 100)

    def test_the_hook_answers_a_projects_question_without_falling_back_to_notes(self):
        env = {**os.environ, "GRAPH_MEMORY_DB": str(self.db), "GRAPH_MEMORY_TODAY": NOW.isoformat(),
               "GRAPH_MEMORY_STATE": str(self.tmp / "state"), "PYTHONIOENCODING": "utf-8"}
        out = subprocess.run([sys.executable, str(ROOT / "src" / "recall_hook.py")], env=env, capture_output=True,
                             input=json.dumps({"prompt": "Is anything blocked right now?", "session_id": "t"}).encode())
        reply = json.loads(out.stdout.decode("utf-8"))
        self.assertIn("1 blocked project", reply["hookSpecificOutput"]["additionalContext"])
        self.assertNotIn("Passages from your notes", reply["hookSpecificOutput"]["additionalContext"])
        self.assertIn("; 1 project", reply["systemMessage"])


class Plans(unittest.TestCase):

    def test_the_discussion_renders_to_the_file_the_quotes_are_checked_against(self):
        text = plan.render("Helpdesk migration", "2026-09-15", DISCUSSION)
        self.assertEqual(text, (cases.CASES / "inputs/discussions/2026-09-15-helpdesk-migration.md")
                         .read_text(encoding="utf-8"))

    def test_recording_it_gives_the_projects_case_02_starts_from(self):
        after_01 = model.from_state(cases.load(cases.CASES / "01-new-project")["after"])
        done = plan.record_plan(after_01, HD, DISCUSSION, ENTITIES, cases.CASES)
        self.assertEqual(done["problems"], [])
        self.assertEqual(done["records"], cases.load(cases.CASES / "02-progress-update")["before"])
        self.assertEqual([e["op"] for e in done["events"]],
                         ["agree_plan", "set_field", "set_field", "close_question", "set_status"])

    def refused(self, data, words, records=None):
        records = records or model.from_state(cases.load(cases.CASES / "01-new-project")["after"])
        found = plan.record_plan(records, HD, data, ENTITIES, cases.CASES)["problems"]
        self.assertTrue(any(words in p for p in found), f"{words!r} not in {found}")

    def test_a_step_owner_the_graph_does_not_know(self):
        steps = [dict(DISCUSSION["steps"][0], owner="Bob Smith")] + DISCUSSION["steps"][1:]
        self.refused({**DISCUSSION, "steps": steps}, "Bob Smith is not in the graph")

    def test_a_step_waiting_on_a_later_one(self):
        steps = [dict(DISCUSSION["steps"][0], after=[2])] + DISCUSSION["steps"][1:]
        self.refused({**DISCUSSION, "steps": steps}, "can wait only on an earlier step")

    def test_a_deliverable_the_project_does_not_have(self):
        steps = [dict(DISCUSSION["steps"][0], delivers="D9")] + DISCUSSION["steps"][1:]
        self.refused({**DISCUSSION, "steps": steps}, "no deliverable D9")

    def test_research_the_file_does_not_say(self):
        found = [{"doc": "../../corpus/tooling-inventory.md", "quote": "The helpdesk is due for renewal."}]
        self.refused({**DISCUSSION, "found": found}, "does not contain")

    def test_research_that_checks_out_is_kept_as_a_source(self):
        found = [{"doc": "../../corpus/tooling-inventory.md",
                  "quote": "The onboarding process uses this document as its day-one checklist."}]
        after_01 = model.from_state(cases.load(cases.CASES / "01-new-project")["after"])
        done = plan.record_plan(after_01, HD, {**DISCUSSION, "found": found}, ENTITIES, cases.CASES)
        self.assertEqual(done["problems"], [])
        self.assertIn('Claude found:\n- ../../corpus/tooling-inventory.md: "The onboarding process', done["text"])
        self.assertEqual(done["records"][HD]["sources"][-1]["kind"], "research")

    def test_a_new_plan_replaces_the_agreed_one_as_version_two(self):
        before = cases.load(cases.CASES / "02-progress-update")["after"]
        data = {"asked": [], "approved": "Yes, replace it.", "on": "2026-09-25",
                "steps": [{"title": "Sign the contract", "owner": "Alex Doyle"}, {"title": "Go live", "after": [1]}]}
        done = plan.record_plan(model.from_state(before), HD, data, ENTITIES, cases.CASES)
        self.assertEqual(done["problems"], [])
        self.assertEqual(len(done["confirm"]), 1)  # the agreed plan is being replaced
        self.assertEqual(done["records"][HD]["plan"]["version"], 2)
        self.assertEqual((done["events"][0]["old"], done["events"][0]["new"]), ("v1, 5 steps", "v2, 2 steps"))


class Status(unittest.TestCase):

    def setUp(self):
        self.records = model.from_state(cases.load(cases.CASES / "02-progress-update")["after"])

    def check(self, **kw):
        change = status.status_change(self.records, HD, on="2026-09-27", doc="inputs/notes/x.md", **kw)
        return model.validate(self.records, change["diff"], change["text"], NAMES), change

    def test_your_words_are_the_quote(self):
        (problems, confirm), change = self.check(words="Waiting on the supplier's quote.", status="blocked")
        self.assertEqual((problems, confirm), ([], []))
        self.assertEqual(change["text"], "# Note on Helpdesk migration, 2026-09-27\n\nWaiting on the supplier's quote.\n")
        after = model.apply(self.records, change["diff"], change["text"])[0]
        self.assertEqual(after[HD]["status"][-1]["quote"], "Waiting on the supplier's quote.")

    def test_a_step_can_be_moved_too(self):
        (problems, _), _ = self.check(words="Alex signed today.", step=("3", "done"))
        self.assertEqual(problems, [])

    def test_done_needs_your_confirmation(self):
        (problems, confirm), _ = self.check(words="Live.", status="done")
        self.assertEqual((problems, len(confirm)), ([], 1))


class Review(unittest.TestCase):
    """ingest.stage, review.py and the ledger, in a folder of their own: nothing touches the repo."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.patches = [(review, "ROOT"), (review, "PENDING"), (review, "LEDGER"), (ingest, "ROOT"),
                        (ingest, "INPUTS"), (ingest, "PENDING"), (board, "BOARD")]
        self.saved = [getattr(m, a) for m, a in self.patches]
        review.ROOT = ingest.ROOT = self.tmp
        review.PENDING = ingest.PENDING = self.tmp / "pending"
        review.LEDGER = self.tmp / "ingested.json"
        ingest.INPUTS = self.tmp / "inputs"
        board.BOARD = self.tmp / "BOARD.md"
        self.case = cases.load(cases.CASES / "02-progress-update")
        self.records = self.tmp / "records"
        model.save_records(self.records, self.case["before"], [])
        self.input = self.tmp / self.case["input"]
        self.input.parent.mkdir(parents=True)
        self.input.write_text(self.case["text"], encoding="utf-8")
        self.db = self.tmp / "g.db"
        build_graph.build(db_path=self.db, records=self.tmp / "none", now=NOW)
        self.llm = lambda prompt, body: json.dumps({"changes": self.case["diff"]["changes"]})

    def tearDown(self):
        for (m, a), v in zip(self.patches, self.saved):
            setattr(m, a, v)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def stage(self):
        return ingest.stage(self.input, "transcript", records_dir=self.records, db=self.db, llm=self.llm)

    def quietly(self, fn, *args, **kw):
        with contextlib.redirect_stdout(io.StringIO()):
            return fn(*args, **kw)

    def test_a_proposal_waits_until_you_apply_it(self):
        result = self.stage()
        self.assertEqual(result["problems"], [])
        self.assertEqual(model.load_records(self.records)[HD], self.case["before"][HD])  # nothing applied yet
        self.assertIn("~ step 1       helpdesk-migration: done", review.show(result["pending"].stem, self.records, self.db))
        self.quietly(review.apply_pending, result["pending"].stem, self.records, self.db, build=False)
        self.assertEqual(model.load_records(self.records), model.from_state(self.case["after"]))
        log = (self.records / f"{HD}.log.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual([json.loads(line) for line in log], self.case["after"]["events"])
        self.assertFalse(result["pending"].exists())
        self.assertIn("Helpdesk migration", board.BOARD.read_text(encoding="utf-8"))

    def test_an_input_dealt_with_is_not_read_again(self):
        self.quietly(review.apply_pending, self.stage()["pending"].stem, self.records, self.db, build=False)
        self.assertEqual(self.stage()["skipped"], "applied")
        self.input.write_text(self.case["text"] + "\nMarcus: One more thing.\n", encoding="utf-8")
        self.assertIn("diff", self.stage())  # changed: read again

    def test_a_rejected_proposal_changes_nothing(self):
        name = self.stage()["pending"].stem
        self.assertEqual(review.reject(name), f"rejected {name}")
        self.assertEqual(model.load_records(self.records)[HD], self.case["before"][HD])
        self.assertEqual(self.stage()["skipped"], "rejected")

    def test_an_input_edited_after_the_proposal_is_refused(self):
        name = self.stage()["pending"].stem
        self.input.write_text(self.case["text"].replace("2 October", "9 October"), encoding="utf-8")
        with self.assertRaises(ValueError) as refused:
            review.apply_pending(name, self.records, self.db, build=False)
        self.assertIn("changed since this was proposed", str(refused.exception))

    def test_changes_that_need_you_wait_for_yes(self):
        self.llm = lambda prompt, body: json.dumps({"changes": [
            {"op": "set_status", "project": HD, "value": "done", "quote": "Shortlist's done"}]})
        name = self.stage()["pending"].stem
        with self.assertRaises(ValueError):
            review.apply_pending(name, self.records, self.db, build=False)
        self.quietly(review.apply_pending, name, self.records, self.db, yes=True, build=False)
        self.assertEqual(model.status_of(model.load_records(self.records)[HD]), "done")

    def test_an_input_from_elsewhere_is_kept_under_inputs(self):
        outside = Path(tempfile.mkdtemp()) / "2026-09-24-sync.md"
        outside.write_text(self.case["text"], encoding="utf-8")
        result = ingest.stage(outside, "transcript", records_dir=self.records, db=self.db, llm=self.llm)
        self.assertEqual(result["diff"]["input"], "inputs/2026-09-24-sync.md")
        self.assertTrue((self.tmp / "inputs" / "2026-09-24-sync.md").is_file())
        shutil.rmtree(outside.parent)

    def test_session_start_says_when_updates_wait(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            review.notice()
        self.assertEqual(out.getvalue(), "")  # nothing waiting, nothing said
        self.stage()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            review.notice()
        self.assertEqual(json.loads(out.getvalue())["systemMessage"], "projects: 1 update to review (/project-review)")


class Health(unittest.TestCase):

    def setUp(self):
        self.records = model.from_state(cases.load(cases.CASES / "05-blocked-and-decided")["after"])
        self.rec = self.records[HD]

    def test_the_story_needs_no_look_on_the_28th(self):
        self.assertEqual(model.health(self.rec, self.records, cases.CASES, NOW, NAMES), [])

    def test_overdue_stale_and_old_questions(self):
        self.rec["status"][-1]["value"] = "active"
        self.rec["plan"]["steps"][3]["due"] = "2026-10-01"
        self.rec["questions"].append({"key": "Q3", "text": "Which option?", "source": self.rec["sources"][0]["doc"],
                                      "quote": "x", "answered": None})
        found = model.health(self.rec, self.records, cases.CASES, date(2026, 10, 20), NAMES)
        self.assertIn("step 4 overdue since 2026-10-01", found)
        self.assertIn("no update since 2026-09-26", found)
        self.assertIn("Q3 open since 2026-09-14: Which option?", found)

    def test_a_source_changed_since_it_was_read(self):
        root = Path(tempfile.mkdtemp())
        shutil.copytree(cases.CASES / "inputs", root / "inputs")
        doc = root / "inputs" / "2026-09-24-support-sync.md"
        doc.write_text(doc.read_text(encoding="utf-8") + "\nMarcus: Actually, four options.\n", encoding="utf-8")
        found = model.health(self.rec, self.records, root, NOW, NAMES)
        self.assertEqual(found, ["inputs/2026-09-24-support-sync.md changed since it was read on 2026-09-24: "
                                 "ingest it again"])
        shutil.rmtree(root)

    def test_the_board_shows_each_project_and_what_needs_a_look(self):
        records, _ = cases.story()
        text = board.render(records, cases.CASES, NOW)
        self.assertIn("| Helpdesk migration (`helpdesk-migration`) | blocked since 2026-09-26 | Priya Patel "
                      "| v1: 2 of 5 done | 3 blocked | 2027-01-04 |", text)  # step 4 waits on the blocked 3
        self.assertIn("- Refunds dashboard: no owner", text)


class Digest(unittest.TestCase):

    def test_a_session_entry_is_kept_on_its_own_for_ingest(self):
        saved = common.SESSIONS
        common.SESSIONS = Path(tempfile.mkdtemp())
        try:
            from datetime import datetime
            path = common.session_input("### What happened\nMarcus finished step 2.", datetime(2026, 9, 26, 16, 5))
            self.assertEqual(path.name, "2026-09-26-1605.md")
            self.assertIn("Marcus finished step 2.", path.read_text(encoding="utf-8"))
        finally:
            shutil.rmtree(common.SESSIONS, ignore_errors=True)
            common.SESSIONS = saved

    def test_projects_are_on_by_default(self):
        self.assertTrue(common.DEFAULTS["projects"])
        self.assertTrue(json.loads((ROOT / "digest" / "config.json").read_text(encoding="utf-8"))["projects"])


if __name__ == "__main__":
    unittest.main()
