"""Evidence for a thesis, gathered from a database and stored for later: evidence/cases/evidence.json,
over the sales ledger evidence/cases/build.py makes, and the archived OpenSpec evidence changes in
evidence/openspec that hold it.

- every recorded number is what its SQL gives on a fresh build;
- the headline numbers come out the same from a plain-Python reading of the raw rows, written apart from
  the SQL, so the SQL is not only checked against itself;
- every slip a number records (UTC days, the order headers, staff left in) gives another value;
- the gold archives state every number, as recorded, and the figures in their notes are the data's;
- every question's answer is worked out from the numbers it names, and its slips are other answers;
- the indexer turns both archives into facts the graph accepts, ending the first half's sets when the
  later change repeats them, in both layouts; bare keeps the numbers and nothing else;
- the knowledge layer, holding the gold archives, finds this period's numbers for the thesis and for an
  undated question, not the superseded ones.
"""
import json
import re
import sqlite3
import sys
import tempfile
import unittest
from collections import defaultdict
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "evidence"
sys.path[:0] = [str(ROOT / "src"), str(HERE)]
import build_graph  # noqa: E402
import evidence_index as index  # noqa: E402
import score  # noqa: E402  evidence/score.py: the knowledge layer holding a store

check = score.check  # evidence/cases/check.py, loaded under its own name (querygraph has a check.py too)
build = check.build

SPEC = check.load()
QUESTIONS = check.load_questions()["questions"]
LONDON = ZoneInfo("Europe/London")
NEW, OLD = "2026-09-15", "2026-07-01"


def value(date, set_id, key):
    return check.number(SPEC, date, set_id, key)["value"]


def london_day(utc_text):
    t = datetime.strptime(utc_text, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    return t.astimezone(LONDON).date().isoformat()


class Ledger:
    """The raw rows, read without SQL: counted orders and their lines, by the brief's definitions."""

    def __init__(self):
        rows = build.seed_module("sales").rows()
        self.customers = {c[0]: c for c in rows["customers"]}
        self.orders = rows["orders"]
        self.lines = defaultdict(list)
        for item in rows["order_items"]:
            self.lines[item[1]].append(item)
        self.amended = {a[1] for a in rows["order_amendments"]}
        self.amendments = rows["order_amendments"]

    def counted(self, first, last):
        out = []
        for o in self.orders:
            email, kind = self.customers[o[1]][2], self.customers[o[1]][3]
            day = london_day(o[3])
            if o[4] == "completed" and not email.endswith("@kettleandkiln.example") \
                    and email != "training@till.local" and first <= day <= last:
                ls = self.lines[o[0]]
                out.append({"id": o[0], "day": day, "channel": o[2], "kind": kind, "item_count": o[5],
                            "total_quantity": o[6], "total_amount": o[7], "n": len(ls),
                            "units": sum(x[3] for x in ls), "amount": sum(x[5] for x in ls), "lines": ls})
        return out


class TestEvidenceNumbers(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.conn = check.connect(build.build("sales", cls.tmp.name))
        cls.got = check.computed(cls.conn, SPEC)
        cls.traps = check.traps(cls.conn, SPEC)
        cls.ledger = Ledger()
        cls.jul_aug = cls.ledger.counted("2026-07-01", "2026-08-31")
        cls.h1 = cls.ledger.counted("2026-01-01", "2026-06-30")

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()
        cls.tmp.cleanup()

    def test_every_recorded_number_is_what_its_sql_gives(self):
        for a in SPEC["archives"]:
            for s in a["sets"]:
                for n in s["numbers"]:
                    with self.subTest(archive=a["date"], set=s["id"], key=n["key"]):
                        self.assertTrue(check.same(n["value"], self.got[(a["date"], s["id"], n["key"])]))

    def test_daily_sales_from_the_raw_rows(self):
        orders = self.jul_aug
        days = defaultdict(int)
        for o in orders:
            days[o["day"]] += o["amount"]
        self.assertEqual(len(days), value(NEW, "daily-sales", "days"))
        self.assertEqual(len(orders), value(NEW, "daily-sales", "counted_orders"))
        self.assertAlmostEqual(sum(days.values()) / 100, value(NEW, "daily-sales", "sales"), places=2)
        self.assertAlmostEqual(round(len(orders) / 62, 1), value(NEW, "daily-sales", "orders_a_day"))
        self.assertAlmostEqual(round(median(days.values()) / 100, 2), value(NEW, "daily-sales", "median_daily_sales"))
        h1_sales = sum(o["amount"] for o in self.h1) / 100
        self.assertAlmostEqual(h1_sales, value(OLD, "daily-sales", "sales"), places=2)
        self.assertEqual(len(self.h1), value(OLD, "daily-sales", "counted_orders"))

    def test_days_ranked_from_the_raw_rows(self):
        days, retail, biggest = defaultdict(int), defaultdict(int), defaultdict(int)
        for o in self.jul_aug:
            days[o["day"]] += o["amount"]
            biggest[o["day"]] = max(biggest[o["day"]], o["amount"])
            if o["kind"] == "retail":
                retail[o["day"]] += o["amount"]
        best = max(days, key=days.get)
        self.assertEqual(best, value(NEW, "days-ranked", "best_day"))
        self.assertAlmostEqual(biggest[best] / 100, value(NEW, "days-ranked", "best_day_largest_order"))
        self.assertEqual(max(retail, key=retail.get), value(NEW, "days-ranked", "best_retail_day"))
        self.assertNotEqual(best, max(retail, key=retail.get), "one trade order makes the best day")
        self.assertEqual(min(days, key=days.get), value(NEW, "days-ranked", "lowest_day"))
        by_weekday = defaultdict(list)
        for d, s in days.items():
            by_weekday[datetime.fromisoformat(d).strftime("%A")].append(s)
        means = {w: sum(v) / len(v) for w, v in by_weekday.items()}
        self.assertEqual(max(means, key=means.get), value(NEW, "days-ranked", "best_weekday"))

    def test_lines_per_order_from_the_raw_rows(self):
        orders = self.jul_aug
        single = [o for o in orders if o["n"] == 1]
        self.assertEqual(len(single), value(NEW, "lines-per-order", "single_line_orders"))
        self.assertAlmostEqual(round(100 * len(single) / len(orders), 1), value(NEW, "lines-per-order", "single_line_share"))
        for channel in ("web", "shop", "phone"):
            mine = [o for o in orders if o["channel"] == channel]
            self.assertAlmostEqual(round(100 * sum(o["n"] == 1 for o in mine) / len(mine), 1),
                                   value(NEW, "lines-per-order", f"single_line_share_{channel}"))
        self.assertTrue(all(o["n"] >= 1 for o in orders), "every completed order has a line")
        self.assertGreater(value(NEW, "lines-per-order", "cancelled_without_lines"), 0)
        h1 = self.h1
        self.assertAlmostEqual(round(100 * sum(o["n"] == 1 for o in h1) / len(h1), 1), value(OLD, "lines-per-order", "single_line_share"))

    def test_header_totals_from_the_raw_rows(self):
        orders = self.jul_aug
        off = [o for o in orders if (o["units"], o["amount"], o["n"]) != (o["total_quantity"], o["total_amount"], o["item_count"])]
        self.assertEqual(len([o for o in orders if o["units"] != o["total_quantity"]]), value(NEW, "header-totals", "quantity_mismatches"))
        self.assertEqual(sum(o["units"] - o["total_quantity"] for o in orders), value(NEW, "header-totals", "units_missing"))
        self.assertAlmostEqual(sum(o["amount"] - o["total_amount"] for o in orders) / 100, value(NEW, "header-totals", "amount_missing"))
        self.assertTrue(all(o["id"] in self.ledger.amended for o in off), "every mismatch is an amended order")
        self.assertTrue(all(o["channel"] == "phone" for o in off), "the phone desk amends")
        self.assertEqual(min(london_day(a[3]) for a in self.ledger.amendments), value(NEW, "header-totals", "first_amendment"))
        self.assertFalse([x for o in orders for x in o["lines"] if x[5] != x[3] * x[4]], "line arithmetic holds")
        self.assertFalse([o for o in self.h1 if o["units"] != o["total_quantity"] or o["amount"] != o["total_amount"]],
                         "no header was out of step before July")

    def test_order_value_from_the_raw_rows(self):
        orders = self.jul_aug
        amounts = sorted(o["amount"] for o in orders)
        self.assertAlmostEqual(round(sum(amounts) / 100 / len(orders), 2), value(NEW, "order-value", "aov"))
        self.assertAlmostEqual(round(median(amounts) / 100, 2), value(NEW, "order-value", "median_order_value"))
        self.assertAlmostEqual(round(100 * sum(a >= 10000 for a in amounts) / len(amounts), 1), value(NEW, "order-value", "over_100_share"))
        self.assertAlmostEqual(round(sum(amounts) / 100 / sum(o["n"] for o in orders), 2), value(NEW, "order-value", "average_line_amount"))

    def test_every_slip_gives_another_value(self):
        self.assertTrue(self.traps)
        for k, slips in self.traps.items():
            for got, why in slips:
                with self.subTest(number="/".join(k), slip=why):
                    self.assertFalse(check.same(self.got[k], got))

    def test_the_gold_notes_figures_are_the_datas(self):
        staff = [o for o in self.ledger.orders if o[4] == "completed" and "2026-07-01" <= london_day(o[3]) <= "2026-08-31"
                 and self.ledger.customers[o[1]][2].endswith("@kettleandkiln.example")]
        training = [o for o in self.ledger.orders if o[4] == "completed" and "2026-07-01" <= london_day(o[3]) <= "2026-08-31"
                    and self.ledger.customers[o[1]][2] == "training@till.local"]
        amount = lambda os: sum(x[5] for o in os for x in self.ledger.lines[o[0]]) / 100  # noqa: E731
        trade = [o for o in self.jul_aug if o["kind"] == "trade"]
        best = value(NEW, "days-ranked", "best_day")
        top = max((o for o in self.jul_aug if o["day"] == best), key=lambda o: o["amount"])
        text = (HERE / "openspec/changes/archive/2026-09-15-bundle-evidence/evidence.md").read_text(encoding="utf-8")
        for said in (f"staff purchases ({len(staff)} orders, £{amount(staff):,.2f})",
                     f"training transactions ({len(training)} orders, £{amount(training):,.2f})",
                     f"Trade orders ({len(trade)} in the period, £{sum(o['amount'] for o in trade) / 100:,.2f}",
                     f"£{top['amount'] / 100:,.2f} from {self.ledger.customers[self.ledger.orders[top['id'] - 1][1]][1]}, "
                     f"{round(100 * top['amount'] / sum(o['amount'] for o in self.jul_aug if o['day'] == best))}% of the day"):
            with self.subTest(note=said):
                self.assertIn(said, text)


class TestStoredEvidence(unittest.TestCase):

    def test_the_gold_archives_state_every_number_as_recorded(self):
        files = index.read_root(HERE / "openspec")
        for date, change, path, text in index.archives(files):
            a = next(a for a in SPEC["archives"] if a["date"] == date)
            self.assertEqual(change, a["change"])
            parsed = {s["id"]: s for s in index.parse(text)["sets"]}
            self.assertEqual(sorted(parsed), sorted(s["id"] for s in a["sets"]))
            for s in a["sets"]:
                rows = {n["key"]: n for n in parsed[s["id"]]["numbers"]}
                self.assertEqual(sorted(rows), sorted(n["key"] for n in s["numbers"]), s["id"])
                for n in s["numbers"]:
                    cell = rows[n["key"]]["value"]
                    with self.subTest(archive=date, set=s["id"], key=n["key"]):
                        got = index.figure(cell)
                        self.assertTrue(check.same(n["value"], cell if got is None else got))

    def test_the_index_is_facts_the_graph_accepts_in_both_layouts(self):
        files = index.read_root(HERE / "openspec")
        texts = {f"evidence/{d}-{c}/evidence.md": t for d, c, _, t in index.archives(files)}
        for layout in index.LAYOUTS:
            docs, problems = index.index(files, layout=layout)
            self.assertEqual(problems, [], layout)
            with tempfile.TemporaryDirectory() as tmp:
                for path, text in texts.items():
                    (Path(tmp) / path).parent.mkdir(parents=True, exist_ok=True)
                    (Path(tmp) / path).write_text(text, encoding="utf-8")
                self.assertEqual(build_graph.problems(list(docs.values()), Path(tmp)), [], layout)
            old = docs[f"evidence/{OLD}-h1-sales-evidence/evidence.md"]
            new = docs[f"evidence/{NEW}-bundle-evidence/evidence.md"]
            self.assertEqual({c.get("valid_to") for n in old["nodes"] for c in n["claims"]}, {NEW},
                             "the later change repeats every first-half set, so each ends on its date")
            self.assertFalse([c for n in new["nodes"] for c in n["claims"] if "valid_to" in c or "valid_from" in c])
            findings = [n for n in new["nodes"] if n["type"] == "FINDING"]
            rows = sum(1 for s in SPEC["archives"][1]["sets"] for n in s["numbers"] if n["key"] != "verdict")
            self.assertEqual(len(findings), rows if layout == "number" else 0)

    def test_bare_keeps_the_numbers_and_nothing_else(self):
        text = (HERE / "openspec/changes/archive/2026-09-15-bundle-evidence/evidence.md").read_text(encoding="utf-8")
        full, thin = index.parse(text), index.parse(index.bare(text))
        self.assertEqual([[n["line"] for n in s["numbers"]] for s in full["sets"]],
                         [[n["line"] for n in s["numbers"]] for s in thin["sets"]])
        self.assertFalse([s for s in thin["sets"] if s["notes"] or s["keywords"] or s["claim"] or s["sql"]])
        self.assertTrue(all(s["notes"] for s in full["sets"]))

    def test_the_brief_asks_for_every_number_by_key_not_by_label(self):
        brief = check.brief_text(SPEC)
        new = next(a for a in SPEC["archives"] if a["date"] == NEW)
        for s in new["sets"]:
            for n in s["numbers"]:
                self.assertIn(f"`{n['key']}`", brief)
                if n["key"] != "verdict" and len(n["label"].split()) >= 3:  # "counted orders" is a term the brief defines
                    self.assertNotIn(n["label"].lower(), n["ask"].lower())
        for d in SPEC["brief"]["definitions"]:
            self.assertIn(d, brief)


class TestQuestions(unittest.TestCase):

    def test_every_answer_comes_from_the_numbers_it_names(self):
        for q in QUESTIONS:
            with self.subTest(q=q["id"]):
                if q["grade"] == "none":
                    self.assertIsNone(q["answer"])
                    continue
                for ref in q["from"].values():
                    check.number(SPEC, *ref.split("/"))
                ans = check.answer_of(q, SPEC)
                self.assertIsNotNone(ans)
                for slip in q.get("slips", {}):
                    self.assertFalse(check.same(ans, float(slip) if re.fullmatch(r"[\d.]+", slip) else slip,
                                                q.get("tolerance", 0)))

    def test_the_kinds_cover_what_a_store_must_do(self):
        kinds = {q["kind"] for q in QUESTIONS}
        self.assertEqual(kinds, {"headline", "derived", "caveat", "by-number", "period", "out-of-scope"})
        self.assertTrue(all(q.get("support") for q in QUESTIONS if q["kind"] == "caveat" and q["grade"] != "date"))


class TestKnowledgeLayer(unittest.TestCase):
    """The gold archives in a workspace: the scorecard's measures that already hold, kept from regressing."""

    @classmethod
    def setUpClass(cls):
        cls.score = score
        cls.svc, cls.p, cls.by_doc, cls.problems = score.workspace(score.store_files("gold"), "number")

    @classmethod
    def tearDownClass(cls):
        cls.svc.close()

    def test_the_gold_evidence_goes_in_whole(self):
        self.assertEqual(self.problems, [])

    def test_the_thesis_finds_this_periods_orders_a_day_not_the_first_halfs(self):
        rows = {r["key"]: r for r in self.score.thesis_rows(self.svc, self.p, SPEC)}
        self.assertTrue(rows["orders_a_day"]["right"], rows["orders_a_day"])
        self.assertIn(NEW, rows["orders_a_day"]["source"])
        self.assertTrue(rows["average_line_amount"]["right"])
        self.assertTrue(rows["bundle_take_up"]["right"], "no data holds the take-up: it is asked")

    def test_an_undated_question_is_shown_no_superseded_figure(self):
        q = next(q for q in QUESTIONS if q["id"] == "q04-orders-a-day")
        row = self.score.recall_rows(self.svc, self.p, SPEC, [q], self.by_doc)[0]
        self.assertTrue(row["complete"], row)
        self.assertFalse(row["stale"])


if __name__ == "__main__":
    unittest.main()
