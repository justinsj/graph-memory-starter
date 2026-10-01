"""The thesis engine without the service: projects/impact.py's figures, and the set_thesis, set_number and
set_effort operations of projects/model.py, on case 01's project."""
import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "projects"))
import cases  # noqa: E402
import impact  # noqa: E402
import model  # noqa: E402

NAMES = model.name_map(model.entities_from_extraction(ROOT / "extraction"))
HD = "helpdesk-migration"
RECORDS = model.from_state(cases.load(cases.CASES / "01-new-project")["after"])
TEXT = ("# Helpdesk numbers, 29 September 2026\n"
        "Priya: Every time the tagging reports fail, each agent loses about 6 hours.\n"
        "Marcus: I'd put the migration at 15 person-days.\n"
        "Sarah: How often do they fail? Priya, can you find out?\n")
METRICS = "Support serves 1,240 active clients.\nTagging reports failed 11 times over the past year.\n"
THESIS = {"op": "set_thesis", "project": HD, "change": "support moves to a new helpdesk",
          "outcome": "the support hours lost to broken tagging reports", "direction": "reduce",
          "unit": "hours a year", "formula": ["failures_a_year", "hours_per_failure"], "reach": "active_clients",
          "quote": "Every time the tagging reports fail, each agent loses about 6 hours."}
HOURS = {"op": "set_number", "project": HD, "key": "hours_per_failure", "label": "hours lost per failure",
         "unit": "hours", "status": "estimated", "value": 6, "by": "Priya Patel",
         "quote": "Every time the tagging reports fail, each agent loses about 6 hours."}
ASKED = {"op": "set_number", "project": HD, "key": "failures_a_year", "label": "tagging report failures",
         "unit": "failures a year", "status": "asked", "ask": "Priya Patel",
         "quote": "How often do they fail? Priya, can you find out?"}
EFFORT = {"op": "set_effort", "project": HD, "days": 15, "by": "Marcus Webb",
          "quote": "I'd put the migration at 15 person-days."}


def diff(*changes):
    return {"input": "inputs/2026-09-29-helpdesk-numbers.md", "kind": "transcript", "on": "2026-09-29",
            "changes": list(changes)}


def docs(path):
    return {"docs/support-metrics.md": METRICS}.get(path)


def check(*changes, records=None):
    return model.validate(RECORDS if records is None else records, diff(*changes), TEXT, NAMES, docs=docs)


class Figures(unittest.TestCase):

    def test_a_sentence_states_its_figures(self):
        self.assertEqual(impact.figures("1,240 clients, 6.5 hours, 30%, four times, twice"),
                         {1240.0, 6.5, 30.0, 4.0, 2.0})
        self.assertTrue(impact.mentions(1240, "Support serves 1,240 active clients."))
        self.assertFalse(impact.mentions(12, "We issued 120 last month."))

    def test_a_thesis_reads_as_a_sentence_once_its_numbers_are_in(self):
        rec = {"thesis": {**THESIS, "formula": ["n", {"value": 52, "label": "weeks a year", "unit": "weeks"},
                                                "share"]},
               "numbers": [{"key": "n", "label": "hours a week", "unit": "hours", "status": "found", "value": 10},
                           {"key": "share", "label": "share saved", "unit": "%", "status": "estimated",
                            "value": 50}],
               "effort": {"days": 4}}
        e = impact.evaluate(rec, {"hours a year": 45})
        self.assertEqual(e["thesis"], "If support moves to a new helpdesk, the support hours lost to broken tagging "
                                      "reports will fall by potentially 260 hours a year.")
        self.assertEqual(e["working"], "10 hours × 52 weeks × 50% (estimated) = 260 hours a year")
        self.assertEqual((e["per_day"], e["money"], e["money_per_day"], e["estimated"]), (65, 11700, 2925, ["share"]))
        rec["numbers"][0] = {**rec["numbers"][0], "status": "asked", "value": None}
        self.assertIn("by an amount still being researched (2 of 3 numbers in)", impact.evaluate(rec)["thesis"])

    def test_ranking_leaves_out_what_is_incomplete_and_says_why(self):
        def ev(value, days, unit="hours a year"):
            return {"thesis": "t", "complete": value is not None, "value": value, "unit": unit, "effort_days": days,
                    "per_day": value / days if value is not None and days else None, "money_per_day": None,
                    "missing": [] if value is not None else ["x"]}
        r = impact.rank([("a", ev(100, 10)), ("b", ev(90, 3)), ("c", ev(None, 2)), ("d", ev(50, None)),
                         ("e", ev(5, 1, "refunds a month"))])
        self.assertEqual({u: [pid for pid, _ in xs] for u, xs in r["by_unit"].items()},
                         {"hours a year": ["b", "a"], "refunds a month": ["e"]})
        self.assertEqual([(pid, why) for pid, _, why in r["unranked"]],
                         [("c", "numbers still being researched: x"), ("d", "no estimated effort yet")])


class Operations(unittest.TestCase):

    def test_a_thesis_its_numbers_and_the_effort_apply_with_their_quotes(self):
        self.assertEqual(check(THESIS, HOURS, ASKED, EFFORT), ([], []))
        after, events = model.apply(RECORDS, diff(THESIS, HOURS, ASKED, EFFORT), TEXT)
        rec = after[HD]
        self.assertEqual(rec["thesis"]["formula"], ["failures_a_year", "hours_per_failure"])
        self.assertEqual({n["key"]: (n["status"], n["value"]) for n in rec["numbers"]},
                         {"hours_per_failure": ("estimated", 6), "failures_a_year": ("asked", None)})
        self.assertEqual(rec["effort"]["days"], 15)
        self.assertEqual([e.get("new") for e in events][1:], ["6 hours (estimated)", "tagging report failures (asked)",
                                                             "15 person-days"])
        self.assertEqual(rec["sources"][-1]["used_for"], ["thesis", "number hours_per_failure estimated",
                                                          "number failures_a_year asked", "effort"])
        e = impact.evaluate(rec)
        self.assertEqual((e["complete"], e["missing"]), (False, ["failures_a_year"]))

    def test_a_number_must_be_in_its_quote_and_a_person_must_be_named(self):
        problems, _ = check(THESIS, {**HOURS, "value": 8}, {**ASKED, "ask": "Priya"}, {**HOURS, "key": "x",
                                                                                          "by": None})
        self.assertEqual(problems, [
            "change 2 (set_number): 8 is not in the quote: a number must be pointed at where it was said",
            "change 3 (set_number): write Priya Patel, not Priya",
            "change 4 (set_number): an estimated number names who made it (by)"])
        self.assertEqual(check({**EFFORT, "days": 20})[0],
                         ["change 1 (set_effort): 20 is not in the quote: an estimate must be pointed at where it "
                          "was made"])

    def test_a_number_found_elsewhere_is_checked_against_that_document(self):
        found = {**ASKED, "status": "found", "value": 11, "ask": None,
                 "found_in": {"source": "docs/support-metrics.md",
                              "quote": "Tagging reports failed 11 times over the past year."},
                 "quote": "How often do they fail? Priya, can you find out?"}
        problems, _ = check(found)
        self.assertEqual(problems, ["change 1 (set_number): 11 is not in the quote: a number must be pointed at "
                                    "where it was said"])  # the transcript line must hold it too
        bad = {**found, "found_in": {"source": "docs/support-metrics.md", "quote": "Tagging failed 11 times."}}
        self.assertIn("change 1 (set_number): found_in: quote not in docs/support-metrics.md: "
                      "'Tagging failed 11 times.'", check(bad)[0])

    def test_changing_a_known_number_needs_a_careful_look(self):
        after, _ = model.apply(RECORDS, diff(THESIS, HOURS), TEXT)
        text = TEXT + "Priya: Actually it is closer to 9 hours.\n"
        changed = {**HOURS, "status": "answered", "value": 9, "quote": "Actually it is closer to 9 hours."}
        problems, confirm = model.validate(after, diff(changed), text, NAMES)
        self.assertEqual(problems, [])
        self.assertEqual(len(confirm), 1)
        self.assertIn("hours_per_failure: 9 hours (answered, by Priya Patel)", confirm[0])

    def test_the_build_reads_the_thesis_and_its_numbers_as_claims(self):
        sys.path.insert(0, str(ROOT / "src"))
        import build_graph
        after, _ = model.apply(RECORDS, diff(THESIS, HOURS, ASKED, EFFORT), TEXT)
        texts = [c[1] for c in build_graph.project_claims(copy.deepcopy(after[HD]), after)]
        self.assertIn("Thesis: If support moves to a new helpdesk, the support hours lost to broken tagging reports "
                      "will fall by an amount still being researched (1 of 2 numbers in).", texts)
        self.assertIn("hours lost per failure: 6 hours (estimated by Priya Patel)", texts)
        self.assertIn("Number still needed: tagging report failures (failures a year), asked Priya Patel", texts)
        self.assertIn("Estimated effort: 15 person-days, estimated by Marcus Webb", texts)


if __name__ == "__main__":
    unittest.main()
