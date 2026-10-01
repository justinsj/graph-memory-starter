"""Questions about a company's own database whose answer depends on rules the schema does not
show: querygraph/cases/questions.json, against the databases querygraph/cases/build.py makes.

Each rule is already written into a query the company uses, in its code (a parameterized
query) or in its notes (a Metabase template, or a query with July's dates written in). For
each case:
- the indexed query, taken from its source and adjusted as the case records, gives the answer;
- so does a plain-Python reading of the source's rules over the raw rows, written apart from
  the SQL, so the query is not only checked against itself;
- the query written from the schema alone does not;
- nor does the indexed query with any one rule taken out: every rule changes the answer;
- every recorded edit finds its text, and every decoy is there and is another query.
"""
import importlib.util
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASES_DIR = ROOT / "querygraph" / "cases"
sys.path.insert(0, str(CASES_DIR))
import check  # noqa: E402

CASES = {c["id"]: c for c in check.load()["cases"]}


def london_month(year, month):
    """A London month as UTC timestamps in the ledger's format, worked out here, not read
    from the case."""
    from zoneinfo import ZoneInfo
    tz, fmt = ZoneInfo("Europe/London"), "%Y-%m-%d %H:%M:%S"
    start = datetime(year, month, 1, tzinfo=tz).astimezone(timezone.utc)
    end = datetime(year + month // 12, month % 12 + 1, 1, tzinfo=tz).astimezone(timezone.utc)
    return start.strftime(fmt), end.strftime(fmt)


def net_revenue(conn, start, end):
    """revenue.py's comment, read over the rows: captures less refunds, each in its own
    month; euros at the last published rate; staff and QA out; minor units."""
    email = dict(conn.execute("SELECT o.id, c.email FROM orders o JOIN customers c ON c.id = o.customer_id"))
    rates = sorted(conn.execute("SELECT rate_date, gbp_per_unit FROM fx_rates WHERE currency = 'EUR'"))
    pay = {r[0]: r[1:] for r in conn.execute("SELECT id, order_id, amount, currency, status, captured_at FROM payments")}

    def gbp(amount, currency, when):
        return amount if currency == "GBP" else amount * [r for d, r in rates if d <= when[:10]][-1]

    def counted(order_id):
        return not email[order_id].endswith(("@shop.example", "@mailinator.com"))

    total = sum(gbp(amount, cur, captured) for order_id, amount, cur, status, captured in pay.values()
                if status == "captured" and start <= captured < end and counted(order_id))
    for payment_id, amount, status, created in conn.execute("SELECT payment_id, amount, status, created_at FROM refunds"):
        order_id, _, cur, _, _ = pay[payment_id]
        if status == "succeeded" and start <= created < end and counted(order_id):
            total -= gbp(amount, cur, created)
    return round(total / 100, 2)


BUDGET_RATES = {"USD": 1.0, "EUR": 1.10, "GBP": 1.30}  # the handbook's 2026 rates


def paying(conn, instant):
    """(subscription, account, monthly minor units in dollars) for each subscription paying
    just before an instant."""
    account = dict(conn.execute("SELECT id, account_id FROM subscriptions"))
    plans = {p: rest for p, *rest in conn.execute("SELECT id, billing_interval, unit_amount, currency FROM plans")}
    out = []
    for sub, plan, qty, status, since, until in conn.execute(
            "SELECT subscription_id, plan_id, quantity, status, valid_from, valid_to FROM subscription_history"):
        if status in ("active", "past_due") and since < instant and (until is None or until >= instant):
            interval, amount, currency = plans[plan]
            out.append((sub, account[sub], qty * amount / (12 if interval == "year" else 1) * BUDGET_RATES[currency]))
    return out


def mrr(conn, day_after):
    """The handbook's MRR section: paying subscriptions as they stood, less the discounts
    running then, in dollars at the budget rates."""
    discounts = conn.execute("SELECT subscription_id, percent_off, starts_at, ends_at FROM discounts").fetchall()
    total = 0.0
    for sub, _, monthly in paying(conn, day_after):
        off = next((p for s, p, a, b in discounts if s == sub and a < day_after and (b is None or b >= day_after)), 0)
        total += monthly * (1 - off / 100)
    return round(total / 100, 2)


def logo_churn(conn, start, end):
    """Tom's reply in #data-help: accounts paying going into the month and not going out of it."""
    before = {acct for _, acct, _ in paying(conn, start)}
    after = {acct for _, acct, _ in paying(conn, end)}
    return round(100 * len(before - after) / len(before), 2)


def urgent_missed(conn, start, end):
    """The runbook's urgent first-reply rules, read over the rows."""
    role = dict(conn.execute("SELECT id, role FROM users"))
    urgent = {}
    for tid, when in conn.execute("SELECT ticket_id, changed_at FROM ticket_field_changes "
                                  "WHERE field = 'priority' AND new_value = 'urgent'"):
        urgent[tid] = min(when, urgent.get(tid, when))
    reply = {}
    for tid, author, public, via, when in conn.execute("SELECT ticket_id, author_id, public, via, created_at FROM ticket_comments"):
        if public and role[author] in ("agent", "admin") and via != "rule":
            reply[tid] = min(when, reply.get(tid, when))
    tickets = {t: (merged, status) for t, merged, status in conn.execute("SELECT id, merged_into, status FROM tickets")}
    missed = []
    for tid, since in urgent.items():
        merged, status = tickets[tid]
        answered = reply.get(tid)
        if merged or status == "deleted" or not start <= since < end or (answered and answered <= since):
            continue
        parse = lambda s: datetime.strptime(s, "%Y-%m-%d %H:%M:%S")  # noqa: E731
        missed.append(answered is None or parse(answered) - parse(since) > timedelta(hours=1))
    return round(100 * sum(missed) / len(missed), 1)


def available(conn, sku, warehouse, now, safety_cases):
    """atp.py, read over the rows: done moves to now, in units, in bulk and pick, less the
    storefront's live holds, less the cases held back for wholesale."""
    per_case = dict(conn.execute("SELECT sku, units_per_case FROM products"))[sku]
    shelf = {i for i, w, k in conn.execute("SELECT id, warehouse, kind FROM locations") if w == warehouse and k in ("bulk", "pick")}
    units = 0
    for src, dst, qty, uom, state, moved in conn.execute(
            "SELECT from_location, to_location, qty, uom, state, moved_at FROM stock_moves WHERE sku = ?", (sku,)):
        if state == "done" and moved <= now:
            n = qty * (per_case if uom == "case" else 1)
            units += n * (dst in shelf) - n * (src in shelf)
    held = sum(q for ref, w, q, expires, released in conn.execute(
        "SELECT order_ref, warehouse, qty_units, expires_at, released_at FROM reservations WHERE sku = ?", (sku,))
        if w == warehouse and released is None and expires > now and not ref.startswith("WS-"))
    return units - held - safety_cases * per_case


class QueryCases(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dbs = check.build_all(cls.tmp.name)
        cls.got = {}
        for cid, case in CASES.items():
            with closing(sqlite3.connect(cls.dbs[case["database"]])) as conn:
                cls.got[cid] = check.run(case, conn)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def db(self, name):
        conn = sqlite3.connect(self.dbs[name])
        self.addCleanup(conn.close)
        return conn

    def test_the_indexed_query_adjusted_gives_the_answer(self):
        for cid, case in CASES.items():
            with self.subTest(cid):
                self.assertTrue(check.right(case, self.got[cid]["indexed"]), (self.got[cid]["indexed"], case["answer"]))

    def test_the_query_from_the_schema_alone_does_not(self):
        for cid, case in CASES.items():
            with self.subTest(cid):
                self.assertFalse(check.right(case, self.got[cid]["naive"]), self.got[cid]["naive"])

    def test_every_rule_changes_the_answer(self):
        for cid, case in CASES.items():
            for rule in case["rules"]:
                with self.subTest(cid, rule=rule["id"]):
                    self.assertFalse(check.right(case, self.got[cid]["without"][rule["id"]]))

    def test_the_rules_read_in_plain_python_give_the_same_answers(self):
        try:
            aug = london_month(2026, 8)
        except Exception as e:  # no time zone data on this machine
            self.skipTest(f"zoneinfo: {e}")
        self.assertAlmostEqual(net_revenue(self.db("shop"), *aug), CASES["01-net-revenue"]["answer"], places=2)
        self.assertAlmostEqual(mrr(self.db("billing"), "2026-09-01 00:00:00"), CASES["02-mrr"]["answer"], places=2)
        self.assertAlmostEqual(logo_churn(self.db("billing"), "2026-08-01 00:00:00", "2026-09-01 00:00:00"),
                               CASES["03-logo-churn"]["answer"], places=2)
        self.assertAlmostEqual(urgent_missed(self.db("helpdesk"), "2026-08-01 00:00:00", "2026-09-01 00:00:00"),
                               CASES["04-urgent-first-reply"]["answer"], places=1)
        self.assertEqual(available(self.db("warehouse"), "MUG-BLU", "LDS", "2026-09-30 17:00:00", safety_cases=2),
                         CASES["05-available-to-promise"]["answer"])

    def test_the_bound_months_are_what_the_code_itself_works_out(self):
        spec = importlib.util.spec_from_file_location("revenue", CASES_DIR / "shop" / "repo" / "finance" / "revenue.py")
        revenue = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(revenue)
            bounds = revenue.month_bounds(2026, 8)
        except Exception as e:
            self.skipTest(f"zoneinfo: {e}")
        params = CASES["01-net-revenue"]["source"]["params"]
        self.assertEqual(bounds, (params["start"], params["end"]))
        self.assertEqual(bounds, ("2026-07-31 23:00:00", "2026-08-31 23:00:00"))

    def test_the_bound_safety_stock_is_the_constant_beside_the_query(self):
        spec = importlib.util.spec_from_file_location("atp", CASES_DIR / "warehouse" / "repo" / "inventory" / "atp.py")
        atp = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(atp)
        case = CASES["05-available-to-promise"]
        self.assertEqual(case["source"]["params"]["safety_cases"], atp.SAFETY_STOCK_CASES["LDS"])
        p = case["source"]["params"]
        self.assertEqual(atp.available_to_promise(self.db("warehouse"), p["sku"], p["warehouse"], p["now"]), case["answer"])

    def test_every_case_turns_on_a_convention_only_its_source_settles(self):
        for cid, case in CASES.items():
            with self.subTest(cid):
                self.assertTrue(any(r["visible"] == "convention" for r in case["rules"]))

    def test_the_named_ids_are_the_ones_the_question_means(self):
        name = self.db("warehouse").execute("SELECT name FROM products WHERE sku = 'MUG-BLU'").fetchone()[0]
        self.assertEqual(name.lower(), "blue enamel mug")
        codes = {c for (c,) in self.db("warehouse").execute("SELECT code FROM locations WHERE warehouse = 'LDS'")}
        self.assertTrue(codes and all(c.startswith("LDS/") for c in codes))

    def test_editing_hard_coded_dates_in_the_wrong_order_gives_zero_churn(self):
        case = CASES["03-logo-churn"]
        src = check.extract(case["source"]["path"], case["source"]["extract"])
        wrong = check.edit(src, list(reversed(case["source"]["adjust"])))
        self.assertEqual(check.value(self.db("billing"), wrong, column="logo_churn_pct"), 0.0)

    def test_the_sources_hold_what_the_notes_say(self):
        """The figures quoted in the Slack thread are what its queries give for July."""
        conn = self.db("billing")
        path = CASES["03-logo-churn"]["source"]["path"]
        text = (CASES_DIR / path).read_text(encoding="utf-8")
        first = check.value(conn, check.extract(path, {"sql_block": 1}))
        corrected = check.value(conn, check.extract(path, {"sql_block": 2}), column="logo_churn_pct")
        self.assertIn(f"It gives me {first}%", text)
        self.assertIn(f"{corrected:.1f}%. That's more like it", text)

    def test_every_edit_finds_its_text_and_every_decoy_is_another_query(self):
        for cid, case in CASES.items():
            with self.subTest(cid):
                indexed = check.indexed_query(case)  # raises if an adjustment finds nothing
                for rule in case["rules"]:
                    self.assertIn(rule["visible"], ("schema", "data", "question", "convention"))
                    check.ablation(case, rule)  # raises if an edit finds nothing
                self.assertTrue(case["decoys"])
                for decoy in case["decoys"]:
                    other = check.extract(decoy["path"], decoy["extract"])
                    self.assertNotEqual(other.strip(), indexed.strip())
                    self.assertIn("SELECT", other)

    def test_the_builds_are_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name, path in check.build_all(tmp).items():
                with self.subTest(name), closing(sqlite3.connect(path)) as a, closing(sqlite3.connect(self.dbs[name])) as b:
                    self.assertEqual(list(a.iterdump()), list(b.iterdump()))


if __name__ == "__main__":
    unittest.main()
