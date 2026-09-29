"""The project cases replayed without a model, and the rules a change set must keep.

Each case in projects/cases/ is an input, the projects before it, the change set
a careful reader would propose and the projects after it. Here the expected set
must pass validate and apply to exactly the stored result; projects/eval_ingest.py
asks the real model the same questions.
"""
import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "projects"))
import cases  # noqa: E402
import ingest  # noqa: E402
import model  # noqa: E402

ENTITIES = model.entities_from_extraction(ROOT / "extraction")
NAMES = model.name_map(ENTITIES)
CASES = {c["name"][:2]: c for c in cases.all_cases()}
HD = "helpdesk-migration"


def changed(case, *changes, on=None):
    """A case's change set with its changes replaced."""
    return {**case["diff"], "on": on or case["diff"]["on"], "changes": list(changes)}


def problems_of(case, *changes, before=None):
    return model.validate(case["before"] if before is None else before,
                          changed(case, *changes), case["text"], NAMES)[0]


class Cases(unittest.TestCase):

    def test_there_are_seven(self):
        self.assertEqual(sorted(CASES), ["01", "02", "03", "04", "05", "06", "07"])

    def test_each_expected_change_set_is_valid(self):
        for key, case in CASES.items():
            with self.subTest(case=case["name"]):
                problems, confirm = model.validate(case["before"], case["diff"], case["text"], NAMES)
                self.assertEqual(problems, [])
                self.assertEqual(confirm, [])

    def test_applying_it_gives_the_stored_result(self):
        for case in CASES.values():
            with self.subTest(case=case["name"]):
                after, events = model.apply(case["before"], case["diff"], case["text"])
                self.assertEqual(model.as_state(after)["projects"], case["after"]["projects"])
                self.assertEqual(events, case["after"]["events"])

    def test_the_result_meets_the_case_expectations(self):
        for case in CASES.values():
            with self.subTest(case=case["name"]):
                after = model.from_state(case["after"])
                self.assertEqual(cases.check(case["expect"], case["before"], case["diff"], after), [])

    def test_every_quote_in_every_record_is_in_its_input(self):
        for case in CASES.values():
            for state in (case["before"].values(), case["after"]["projects"]):
                for rec in state:
                    with self.subTest(case=case["name"], project=rec["id"]):
                        self.assertEqual(model.check_record(rec, cases.CASES), [])

    def test_the_cases_follow_on_from_each_other(self):
        after_02 = model.from_state(CASES["02"]["after"])
        for key in ("03", "04", "05"):
            self.assertEqual(CASES[key]["before"], after_02, key)
        self.assertEqual(model.from_state(CASES["03"]["after"]), after_02)  # nothing new
        self.assertEqual(CASES["06"]["before"], cases.story()[0])  # 04 and 05 both applied
        self.assertEqual(CASES["07"]["before"], model.from_state(CASES["06"]["after"]))

    def test_apply_leaves_the_records_it_was_given_alone(self):
        case = CASES["05"]
        before = copy.deepcopy(case["before"])
        model.apply(case["before"], case["diff"], case["text"])
        self.assertEqual(case["before"], before)

    def test_a_new_project_is_found_short_of_owner_date_and_plan(self):
        after = model.from_state(CASES["01"]["after"])
        self.assertEqual(model.gaps(after[HD]), ["no owner", "no due date", "no agreed plan"])
        self.assertEqual(model.gaps(model.from_state(CASES["02"]["after"])[HD]), [])

    def test_each_input_is_recorded_once_per_project_with_what_it_was_used_for(self):
        rec = model.from_state(CASES["05"]["after"])[HD]
        self.assertEqual([s["doc"].split("/")[-1][:10] for s in rec["sources"]],
                         ["2026-09-14", "2026-09-15", "2026-09-24", "2026-09-26"])
        self.assertEqual(rec["sources"][-1]["used_for"],
                         ["step 2 done", "step 3 blocked", "status blocked", "Q1 answered", "decisions"])

    def test_the_hash_ignores_line_endings(self):
        text = CASES["02"]["text"]
        self.assertEqual(model.digest(text), model.digest(text.replace("\n", "\r\n")))


class Refused(unittest.TestCase):
    """Each rule, broken once. The case's other changes are left out, so the problem is alone."""

    def assertRefused(self, case, change, words, before=None):
        found = problems_of(CASES[case], change, before=before)
        self.assertTrue(any(words in p for p in found), f"{words!r} not in {found}")

    def test_a_paraphrased_quote(self):
        self.assertRefused("02", {"op": "set_step", "project": HD, "n": 1, "status": "done",
                                  "quote": "Marcus finished the shortlist."}, "quote not in the input")

    def test_a_quote_over_300_characters(self):
        self.assertRefused("02", {"op": "set_step", "project": HD, "n": 1, "status": "done",
                                  "quote": "x" * 301}, "over 300")

    def test_a_date_the_input_does_not_state(self):
        self.assertRefused("02", {"op": "set_step", "project": HD, "n": 2, "status": "doing",
                                  "due": "2026-10-09",
                                  "quote": "I'm checking integrations against the inventory next"},
                           "2026-10-09 is not stated")

    def test_a_deadline_in_words_is_not_a_date(self):
        self.assertRefused("01", {"op": "set_field", "project": HD, "field": "due",
                                  "value": "before the January peak", "date": "2027-01-01",
                                  "quote": "before the January peak"},
                           "is not stated", before=model.from_state(CASES["01"]["after"]))

    def test_a_status_move_the_table_does_not_allow(self):
        self.assertRefused("02", {"op": "set_status", "project": HD, "value": "proposed",
                                  "from": "2026-09-24", "quote": "Shortlist's done"}, "active → proposed")

    def test_going_active_without_an_agreed_plan(self):
        self.assertRefused("01", {"op": "set_status", "project": HD, "value": "active",
                                  "from": "2026-09-14", "quote": "Agreed."},
                           "needs an agreed plan", before=model.from_state(CASES["01"]["after"]))

    def test_a_new_project_starting_active(self):
        case = CASES["04"]
        found = problems_of(case, case["diff"]["changes"][0],
                            {**case["diff"]["changes"][1], "value": "active"})
        self.assertTrue(any("starts as proposed or planning" in p for p in found), found)

    def test_a_project_that_does_not_exist(self):
        self.assertRefused("02", {"op": "set_step", "project": "helpdesk", "n": 1, "status": "done",
                                  "quote": "Shortlist's done"}, "no project helpdesk")

    def test_a_person_the_graph_does_not_know(self):
        self.assertRefused("02", {"op": "set_field", "project": HD, "field": "owner",
                                  "value": "Bob Smith", "quote": "Shortlist's done"}, "not in the graph")

    def test_a_short_name_where_the_full_one_is_needed(self):
        self.assertRefused("02", {"op": "set_field", "project": HD, "field": "owner",
                                  "value": "Marcus", "quote": "Shortlist's done"}, "write Marcus Webb")

    def test_creating_a_project_twice(self):
        self.assertRefused("02", {"op": "create_project", "project": HD, "title": "Helpdesk",
                                  "description": "x", "quote": "Shortlist's done"}, "already exists")

    def test_a_step_the_plan_does_not_have(self):
        self.assertRefused("02", {"op": "set_step", "project": HD, "n": 9, "status": "done",
                                  "quote": "Shortlist's done"}, "no step 9")

    def test_moving_a_step_with_no_agreed_plan(self):
        self.assertRefused("01", {"op": "set_step", "project": HD, "n": 1, "status": "done",
                                  "quote": "Agreed."}, "no agreed plan",
                           before=model.from_state(CASES["01"]["after"]))

    def test_a_dependency_cycle(self):
        before = model.from_state(CASES["04"]["after"])  # the dashboard needs the helpdesk
        self.assertRefused("04", {"op": "add_dependency", "project": HD, "on": "project:refunds-dashboard",
                                  "kind": "needs", "quote": "No rush"}, "a cycle", before=before)

    def test_writing_a_plan_from_a_meeting(self):
        self.assertRefused("02", {"op": "agree_plan", "project": HD, "quote": "Shortlist's done",
                                  "steps": [{"n": 1, "title": "Shortlist", "quote": "Shortlist's done"}]},
                           "agreed in a discussion with you")

    def test_a_step_change_with_neither_status_nor_due(self):
        self.assertRefused("02", {"op": "set_step", "project": HD, "n": 2, "quote": "Shortlist's done"},
                           "needs a status, a due date or both")

    def test_restating_a_recorded_due_date_is_not_refused(self):
        found = problems_of(CASES["05"], {"op": "set_step", "project": HD, "n": 2, "status": "done",
                                          "due": "2026-10-02", "quote": "Integration check is done."})
        self.assertEqual(found, [])

    def test_answering_a_question_twice(self):
        self.assertRefused("05", {"op": "close_question", "project": HD, "key": "Q2",
                                  "quote": "keep it read-only"}, "already answered")

    def test_a_later_change_is_still_checked_after_a_bad_one(self):
        found = problems_of(CASES["02"],
                            {"op": "set_step", "project": HD, "n": 9, "status": "done", "quote": "Shortlist's done"},
                            {"op": "set_step", "project": HD, "n": 1, "status": "done", "quote": "not said"})
        self.assertEqual([p[:8] for p in found], ["change 1", "change 2"])

    def test_done_is_not_refused_but_needs_you(self):
        case = CASES["02"]
        diff = changed(case, {"op": "set_status", "project": HD, "value": "done", "from": "2026-09-24",
                              "quote": "Shortlist's done"})
        problems, confirm = model.validate(case["before"], diff, case["text"], NAMES)
        self.assertEqual(problems, [])
        self.assertEqual(len(confirm), 1)

    def test_changing_an_owner_already_set_needs_you(self):
        case = CASES["02"]
        diff = changed(case, {"op": "set_field", "project": HD, "field": "owner", "value": "Marcus Webb",
                              "quote": "Marcus: Shortlist's done"})
        self.assertEqual(len(model.validate(case["before"], diff, case["text"], NAMES)[1]), 1)


class Defaults(unittest.TestCase):

    def test_a_status_without_from_holds_from_the_inputs_date(self):
        case = CASES["05"]
        diff = changed(case, {"op": "set_status", "project": HD, "value": "blocked",
                              "quote": "Then the helpdesk migration is blocked until he's back."})
        self.assertEqual(model.validate(case["before"], diff, case["text"], NAMES), ([], []))
        after = model.apply(case["before"], diff, case["text"])[0]
        self.assertEqual(after[HD]["status"][-1]["from"], "2026-09-26")

    def test_a_step_can_move_its_due_date_alone(self):
        case = CASES["02"]
        diff = changed(case, {"op": "set_step", "project": HD, "n": 2, "due": "2026-10-02",
                              "quote": "done by 2 October"})
        self.assertEqual(model.validate(case["before"], diff, case["text"], NAMES), ([], []))
        step = model.apply(case["before"], diff, case["text"])[0][HD]["plan"]["steps"][1]
        self.assertEqual((step["status"], step["due"]), ("todo", "2026-10-02"))


class Dates(unittest.TestCase):

    def test_the_forms_a_date_is_said_in(self):
        text = "Shortlist by 23 September. Live by Jan 4th. Review on 2026-11-02. Call on October 3."
        for iso in ("2026-09-23", "2027-01-04", "2026-11-02", "2026-10-03"):
            self.assertTrue(model.stated(iso, text, "2026-09-14"), iso)

    def test_near_misses_are_not_dates(self):
        text = "Shortlist by 23 September, and 12 October."
        self.assertFalse(model.stated("2026-09-03", text, "2026-09-14"))  # 23 is not 3
        self.assertFalse(model.stated("2026-10-02", text, "2026-09-14"))  # 12 is not 2
        self.assertFalse(model.stated("2029-09-23", text, "2026-09-14"))  # no year said: this year or next

    def test_a_day_said_relative_to_the_input(self):
        self.assertTrue(model.stated("2026-09-26", "I signed it last night.", "2026-09-27"))
        self.assertTrue(model.stated("2026-09-28", "We go live tomorrow.", "2026-09-27"))
        self.assertFalse(model.stated("2026-09-25", "I signed it last night.", "2026-09-27"))

    def test_the_inputs_own_date_needs_no_saying(self):
        self.assertTrue(model.stated("2026-09-14", "", "2026-09-14"))


class Ingest(unittest.TestCase):
    """The model's side, with its reply recorded: parsing, names, the wrapper."""

    def test_a_fenced_reply_parses(self):
        reply = 'Here you go:\n```json\n{"changes": [{"op": "add_decision"}]}\n```'
        self.assertEqual(ingest.parse(reply), [{"op": "add_decision"}])

    def test_a_reply_without_changes_is_an_error(self):
        with self.assertRaises(ValueError):
            ingest.parse("I could not find any changes.")

    def test_short_names_are_written_out(self):
        out = ingest.tidy([{"op": "set_field", "field": "owner", "value": "Priya"},
                           {"op": "add_dependency", "on": "tooling"},
                           {"op": "add_dependency", "on": "project:x"},
                           {"op": "add_deliverable", "owner": "Marcus"},
                           {"op": "set_step", "project": "project:helpdesk-migration"}], NAMES)
        self.assertEqual([out[0]["value"], out[1]["on"], out[2]["on"], out[3]["owner"], out[4]["project"]],
                         ["Priya Patel", "Tooling inventory", "project:x", "Marcus Webb", HD])

    def test_propose_wraps_the_reply_with_the_input(self):
        case = CASES["02"]
        seen = {}

        def llm(prompt, body):
            seen["prompt"], seen["body"] = prompt, body
            return json.dumps({"changes": case["diff"]["changes"]})

        diff = ingest.propose(case["input"], case["text"], case["before"], ENTITIES,
                              case["kind"], case["on"], llm=llm)
        self.assertEqual(diff, case["diff"])
        self.assertIn("helpdesk-migration", seen["body"])
        self.assertIn('"next_deliverable_key": "D4"', seen["body"])
        self.assertIn("- Priya Patel (PERSON), also: Priya: The Support Lead", seen["body"])
        self.assertIn("- Supplier payments (POLICY): Payments over £2,000 need Founder sign-off", seen["body"])
        self.assertIn("set_step", seen["prompt"])

    def test_a_new_projects_id_may_be_written_id(self):
        self.assertEqual(ingest.tidy([{"op": "create_project", "id": "x"}], NAMES), [{"op": "create_project", "project": "x"}])

    def test_a_refused_answer_is_sent_back_once_with_the_problems(self):
        case = CASES["02"]
        good = case["diff"]["changes"]
        bad = [dict(good[0], quote="Marcus finished the shortlist.")] + good[1:]
        asked = []

        def llm(prompt, body):
            asked.append(body)
            return json.dumps({"changes": bad if len(asked) == 1 else good})

        diff = ingest.propose(case["input"], case["text"], case["before"], ENTITIES, case["kind"], case["on"], llm=llm)
        self.assertEqual(diff["changes"], good)
        self.assertEqual(len(asked), 2)
        self.assertIn("The checks refused it:\n- change 1 (set_step): quote not in the input", asked[1])
        self.assertEqual(len(diff["repaired"]), 1)

    def test_a_good_answer_is_not_sent_back(self):
        case, asked = CASES["02"], []
        ingest.propose(case["input"], case["text"], case["before"], ENTITIES, case["kind"], case["on"],
                       llm=lambda p, b: asked.append(b) or json.dumps({"changes": case["diff"]["changes"]}))
        self.assertEqual(len(asked), 1)

    def test_the_date_comes_from_the_file_name(self):
        self.assertEqual(ingest.input_date("inputs/2026-09-24-support-sync.md"), "2026-09-24")


if __name__ == "__main__":
    unittest.main()
