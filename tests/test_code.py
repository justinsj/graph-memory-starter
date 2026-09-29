"""Code in the graph: identifiers in any style, the index of a small shop, and the questions
in codegraph/cases/questions.json answered from it.

The shop (codegraph/cases/shop) is a Python API and a TypeScript frontend, built to hold
each case: a constant read through a chain of calls, an explicit route, a URL built from
constants, one endpoint that runs a different function for each value in the body, another
that picks one from a lookup table, two functions with one name, an unused one, a function
re-exported by its package, passed as a callback and called from tests, and a threshold the
backend, the frontend and the refund policy do not agree on.

Dependents checks the promise a change request relies on: whatever the wording, the code
block names everything that depends on the symbol and everything it depends on, worked out
here from the index's links on their own, with the line of each direct use.
"""
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
import graphs  # noqa: E402  pins GRAPH_MEMORY_TODAY, puts src/ on the path
import recall  # noqa: E402
import tokens  # noqa: E402

sys.path.insert(0, str(ROOT / "codegraph"))
import index  # noqa: E402

SHOP = ROOT / "codegraph" / "cases" / "shop"
CASES = json.loads((ROOT / "codegraph" / "cases" / "questions.json").read_text(encoding="utf-8"))


class Tokens(unittest.TestCase):

    def test_every_naming_style_comes_apart_at_the_same_seams(self):
        for name, want in [
                ("needs_approval", ["needs", "approval"]), ("needsApproval", ["needs", "approval"]),
                ("NeedsApproval", ["needs", "approval"]), ("NEEDS_APPROVAL", ["needs", "approval"]),
                ("needs-approval", ["needs", "approval"]), ("needs approval", ["needs", "approval"]),
                ("APPROVAL_THRESHOLD_GBP", ["approval", "threshold", "gbp"]),
                ("orders.service.cancel_order", ["orders", "service", "cancel", "order"]),
                ("__init__", ["init"])]:
            self.assertEqual(tokens.words(name), want, name)

    def test_a_run_of_capitals_is_one_word(self):
        for name, want in [("parseHTTPResponse", ["parse", "http", "response"]), ("HTTPServer", ["http", "server"]),
                           ("XMLHttpRequest", ["xml", "http", "request"]), ("getOrderByID", ["get", "order", "by", "id"]),
                           ("IOError", ["io", "error"])]:
            self.assertEqual(tokens.words(name), want, name)

    def test_digits_stay_with_the_letters_before_them(self):
        self.assertEqual(tokens.words("sha256Hash"), ["sha256", "hash"])
        self.assertEqual(tokens.words("v2Handler"), ["v2", "handler"])

    def test_any_alphabet(self):
        self.assertEqual(tokens.words("créerRemboursement"), ["créer", "remboursement"])
        self.assertEqual(tokens.words("Straße"), ["straße"])

    def test_prose_is_unchanged(self):
        import re
        for q in (graphs.REFUND, "Who approves supplier payments over £2,000?", "What's the status on 2026-09-23?"):
            self.assertEqual(tokens.words(q), re.findall(r"\w+", q.lower()))


class Index(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.result = index.index(SHOP)
        cls.edges = {(e["source"], e["predicate"], e["target"]) for d in cls.result["docs"] for e in d["edges"]}
        cls.syms = cls.result["symbols"]

    def has(self, *edge):
        self.assertIn(edge, self.edges)

    def test_what_it_finds(self):
        kinds = {}
        for s in self.syms.values():
            kinds[s["type"]] = kinds.get(s["type"], 0) + 1
        self.assertEqual(kinds, {"FUNCTION": 20, "COMPONENT": 2, "TEST": 2, "VARIABLE": 7, "MODULE": 10,
                                 "ROUTE": 4, "ROUTE_CASE": 4, "UI_ACTION": 3})
        self.assertEqual(self.result["files"], 17)

    def test_a_chain_of_calls_to_a_constant(self):
        self.has("backend.refunds.views.create_refund", "calls", "backend.refunds.rules.needs_approval")
        self.has("backend.refunds.rules.needs_approval", "reads", "backend.config.APPROVAL_THRESHOLD_GBP")
        self.assertEqual(self.syms["backend.config.APPROVAL_THRESHOLD_GBP"]["value"], "250")

    def test_an_explicit_route_matched_across_parameter_syntaxes(self):
        self.has("frontend.api.getOrder", "requests", "GET /api/orders/{order_id}")
        self.has("GET /api/orders/{order_id}", "handled_by", "backend.orders.views.get_order")

    def test_a_url_built_from_constants_in_two_files(self):
        self.assertEqual(self.syms["frontend.api.REFUNDS_URL"]["resolved"], "/api/refunds")
        self.has("frontend.api.REFUNDS_URL", "reads", "frontend.config.API_BASE")
        self.has("frontend.api.submitRefund", "requests", "POST /api/refunds")
        self.has("frontend.api.postAction", "requests", "POST /api/actions")

    def test_a_value_in_the_body_picks_the_branch(self):
        self.has("frontend.api.cancelOrder", "requests", "POST /api/actions when action = cancel")
        self.has("frontend.api.refundViaActions", "requests", "POST /api/actions when action = refund")
        self.has("POST /api/actions when action = cancel", "dispatches_to", "backend.orders.service.cancel_order")
        self.has("POST /api/actions when action = refund", "dispatches_to", "backend.orders.service.process_refund")
        handler_calls = {t for s, p, t in self.edges if s == "backend.orders.views.handle_action" and p == "calls"}
        self.assertEqual(handler_calls, set())  # branch calls belong to their case, not to the handler

    def test_buttons_own_what_their_onclick_runs(self):
        self.has("'Request refund' button in RefundForm", "triggers", "frontend.api.submitRefund")
        self.has("'Cancel order' button in OrderPage", "triggers", "frontend.api.cancelOrder")
        component_calls = {t for s, p, t in self.edges if s == "frontend.components.OrderPage" and p == "calls"}
        self.assertEqual(component_calls, {"frontend.api.getOrder"})

    def test_the_import_decides_which_validate(self):
        self.has("backend.refunds.views.create_refund", "calls", "backend.refunds.rules.validate")
        self.assertNotIn(("backend.refunds.views.create_refund", "calls", "backend.orders.service.validate"), self.edges)

    def test_nothing_reaches_the_legacy_refund(self):
        self.assertFalse([e for e in self.edges if "backend.refunds.legacy.legacy_refund" in (e[0], e[2])])

    def test_an_import_through_a_package_is_followed_to_the_definition(self):
        self.has("backend/reports.py", "imports", "backend.refunds.rules.needs_approval")  # from refunds import ...
        self.has("backend/refunds/__init__.py", "imports", "backend.refunds.rules.needs_approval")  # the re-export

    def test_a_function_passed_and_not_called_is_referenced(self):
        self.has("backend.reports.count_large", "references", "backend.refunds.rules.needs_approval")  # filter(f, xs)
        self.assertNotIn(("backend.reports.count_large", "calls", "backend.refunds.rules.needs_approval"), self.edges)

    def test_tests_are_their_own_kind_and_call_what_they_test(self):
        for name in ("backend.tests.test_rules.test_small_refund_needs_no_approval",
                     "backend.tests.test_rules.test_large_refund_needs_approval"):
            self.assertEqual(self.syms[name]["type"], "TEST")
            self.has(name, "calls", "backend.refunds.rules.needs_approval")

    def test_a_lookup_table_gives_one_case_per_entry(self):
        self.has("POST /api/bulk when action = cancel", "dispatches_to", "backend.orders.service.cancel_order")
        self.has("POST /api/bulk when action = hold", "dispatches_to", "backend.orders.service.hold_order")
        self.has("backend.orders.views.BULK_ACTIONS", "references", "backend.orders.service.cancel_order")
        self.has("backend.orders.views.handle_bulk", "looks_up", "backend.orders.views.BULK_ACTIONS")
        self.assertFalse({t for s, p, t in self.edges if s == "backend.orders.views.handle_bulk" and p != "looks_up"})

    def test_a_literal_body_in_the_fetch_picks_the_case(self):
        self.has("frontend.api.bulkCancel", "requests", "POST /api/bulk when action = cancel")
        self.assertNotIn(("frontend.api.bulkCancel", "requests", "POST /api/bulk"), self.edges)

    def test_the_body_fields_sent_and_read(self):
        sites = {(x["source"], x["predicate"], x["target"], x["line"], x.get("detail"))
                 for d in self.result["docs"] for x in d.get("sites", [])}
        for site in [("frontend.api.submitRefund", "requests", "POST /api/refunds", 8, "order_id, amount"),
                     ("frontend.api.bulkCancel", "requests", "POST /api/bulk when action = cancel", 32,
                      "action, order_ids"),
                     ("frontend.api.refundViaActions", "requests", "POST /api/actions when action = refund", 26,
                      "action, order_id, amount"),
                     ("backend.refunds.views.create_refund", "reads_body", "POST /api/refunds", 14, "amount"),
                     ("backend.orders.views.handle_bulk", "reads_body", "POST /api/bulk", 33, "order_ids")]:
            self.assertIn(site, sites)

    def test_every_site_quotes_its_line(self):
        for doc in self.result["docs"]:
            lines = (SHOP / doc["source_doc"]).read_text(encoding="utf-8").splitlines()
            for x in doc.get("sites", []):
                self.assertEqual(recall.plain(lines[x["line"] - 1].strip()), recall.plain(x["quote"]), x)

    def test_every_claim_quotes_a_line_of_its_file(self):
        for doc in self.result["docs"]:
            text = (SHOP / doc["source_doc"]).read_text(encoding="utf-8")
            for node in doc["nodes"]:
                for c in node["claims"]:
                    self.assertIn(recall.plain(c["quote"]), recall.plain(text), (doc["source_doc"], c["quote"]))


def names_only(facts) -> str:
    """The trace's own lines: the quoted lines of code under them are indented, and may name anything."""
    return "\n".join(line for line in facts.code if not line.startswith("  "))


class Answers(unittest.TestCase):
    """Each case in questions.json, asked of a graph of the documents and the shop."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.db = graphs.build(cls.tmp / "g", code=SHOP)
        cls.saved, recall.DB = recall.DB, cls.db

    @classmethod
    def tearDownClass(cls):
        recall.DB = cls.saved
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def check(self, case):
        facts = recall.recall(case["question"])
        text, code = facts.as_text(), names_only(facts)
        for want in case["must_include"]:
            self.assertIn(want, text, f"{case['id']}: missing {want!r}\n\n{text}")
        for bad in case.get("must_not_include", []):
            self.assertNotIn(bad, text, f"{case['id']}: should not say {bad!r}\n\n{text}")
        for bad in case.get("must_not_include_in_code", []):
            self.assertNotIn(bad, code, f"{case['id']}: the trace should not reach {bad!r}\n\n{code}")
        return facts

    def test_every_case(self):
        for case in CASES:
            with self.subTest(case=case["id"]):
                self.check(case)

    def test_one_name_in_any_style_names_one_symbol(self):
        case = next(c for c in CASES if c["id"] == "10-identifier-styles")
        with closing(sqlite3.connect(self.db)) as db:
            ids = {name: eid for eid, name in db.execute("SELECT id, name FROM entities")}
            for group in case["seeds"]:
                for q in group["questions"]:
                    with self.subTest(question=q):
                        self.assertIn(ids[group["entity"]], recall._seeds(db, q))

    def test_the_trace_follows_past_three_hops(self):
        facts = recall.recall("What runs on the server when someone clicks 'Request refund'?")
        self.assertIn("backend.refunds.rules.needs_approval reads backend.config.APPROVAL_THRESHOLD_GBP (= 250)",
                      "\n".join(facts.code))  # five links from the button

    def test_the_provenance_counts_the_code(self):
        text = recall.recall("What calls submitRefund?").as_text()
        self.assertIn("and your code (17 files, indexed", text)

    def test_a_document_graph_without_code_has_no_code_in_its_answers(self):
        recall.DB = graphs.build(self.tmp / "plain")
        try:
            text = recall.recall("What calls submitRefund?").as_text()  # "refund" still names the policy
        finally:
            recall.DB = self.db
        self.assertNotIn("code:", text)
        self.assertNotIn("frontend.", text)
        self.assertNotIn("your code", text)

    def test_the_hook_sends_the_trace(self):
        env = {**os.environ, "GRAPH_MEMORY_DB": str(self.db), "GRAPH_MEMORY_STATE": str(self.tmp / "state"),
               "PYTHONIOENCODING": "utf-8"}
        out = subprocess.run([sys.executable, str(ROOT / "src" / "recall_hook.py")], env=env, capture_output=True,
                             input=json.dumps({"prompt": "Is legacy_refund still used anywhere?",
                                               "session_id": "t"}).encode())
        context = json.loads(out.stdout.decode("utf-8"))["hookSpecificOutput"]["additionalContext"]
        self.assertIn("code:\nbackend.refunds.legacy.legacy_refund: nothing in the code calls", context)
        self.assertNotIn("Passages from your notes", context)


DEPENDS = {"triggers", "calls", "requests", "handled_by", "dispatches_to", "reads", "references", "imports"}
BACK_ONLY = {"looks_up"}  # a handler depends on its lookup table, but runs one entry, not all of them


def closure(edges: set, start: str, forward: bool) -> set:
    """Everything start depends on (forward) or that depends on it, to the end: no depth limit."""
    found, frontier = set(), {start}
    while frontier:
        nxt = set()
        for s, p, t in edges:
            if forward and p in DEPENDS and s in frontier:
                other = t
            elif not forward and p in DEPENDS | BACK_ONLY and t in frontier:
                other = s
            else:
                continue
            if other != start and other not in found:
                found.add(other)
                nxt.add(other)
        frontier = nxt
    return found


def named(name: str, text: str) -> bool:
    """name appears as a whole name: not the start of a longer one (POST /api/actions when action = ...)."""
    return re.search(rf"(?:^|[ ,]){re.escape(name)}(?=$|,| \(| (?!when )[a-z])", text, re.M) is not None


def site_line(file, x) -> str:
    return f"  {file}:{x['line']}, {x['source']} {x['predicate']} it: {x['quote']}"


def contract_lines(result, handler, edges) -> set:
    """The body each client sends to the routes handler handles, and each field it reads."""
    routes = {s for s, p, t in edges if p == "handled_by" and t == handler}
    out = set()
    for d in result["docs"]:
        for x in d.get("sites", []):
            if x["target"] in routes and x["predicate"] == "requests":
                what = f"sends {x['detail']}" if x.get("detail") else "requests it"
                out.add(f"  {d['source_doc']}:{x['line']}, {x['source']} {what}: {x['quote']}")
            elif x["target"] in routes and x["predicate"] == "reads_body":
                out.add(f"  {d['source_doc']}:{x['line']}, {x['source']} reads {x['detail']}: {x['quote']}")
    return out


class Dependents(unittest.TestCase):
    """A change request's code block against the index's own links, followed to the end.

    The expected dependents are worked out here from index() alone, not by recall, so a
    link the trace fails to follow, a depth that stops short, a group cut for space or a
    wording that turns one direction off all show up as a name missing.
    """

    TYPES = ("FUNCTION", "COMPONENT", "TEST", "VARIABLE", "ROUTE")

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.db = graphs.build(cls.tmp / "g", code=SHOP)
        cls.saved, recall.DB = recall.DB, cls.db
        cls.result = index.index(SHOP)
        cls.edges = {(e["source"], e["predicate"], e["target"]) for d in cls.result["docs"] for e in d["edges"]}
        cls.sites = [(d["source_doc"], x) for d in cls.result["docs"] for x in d.get("sites", [])]

    @classmethod
    def tearDownClass(cls):
        recall.DB = cls.saved
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def spoken(self, name):
        """What someone would call it: the last part of the name, or the last two when that is not enough."""
        if self.result["symbols"][name]["type"] == "ROUTE":
            return name
        parts = name.split(".")
        for n in range(1, len(parts) + 1):
            short = ".".join(parts[-n:])
            if sum(1 for other in self.result["symbols"] if other.endswith("." + short) or other == short) == 1:
                return short
        return name

    def complete(self, name, question):
        """Every dependent and dependency of name is in the trace, each direct use has its line, and
        a handler's clients' bodies and its reads are shown."""
        facts = recall.recall(question)
        names, lines = names_only(facts), set(facts.code)
        where = f"{question}\n\n" + "\n".join(facts.code)
        if closure(self.edges, name, False):
            self.assertIn(f"{name}, what depends on it:", names, where)
        if closure(self.edges, name, True):
            self.assertIn(f"{name}, what it depends on:", names, where)
        for forward in (False, True):
            for other in sorted(closure(self.edges, name, forward)):
                self.assertTrue(named(other, names), f"{'depends on' if forward else 'dependent'} {other} "
                                                     f"missing for: {where}")
        for file, x in self.sites:
            if x["target"] == name and x["predicate"] != "reads_body":
                self.assertIn(site_line(file, x), lines, where)
        for line in contract_lines(self.result, name, self.edges):
            self.assertIn(line, lines, where)
        return facts

    def test_every_predicate_the_index_writes_is_followed(self):
        written = {p for _, p, _ in self.edges}
        self.assertLessEqual(written, DEPENDS | BACK_ONLY | {"part_of"})
        self.assertEqual(set(recall.LEADS), DEPENDS)
        self.assertEqual(set(recall.BACK_ONLY), BACK_ONLY)

    def test_every_symbol_asked_about_a_change_brings_every_dependent(self):
        for name, sym in sorted(self.result["symbols"].items()):
            if sym["type"] in self.TYPES:
                q = f"If I change {self.spoken(name)}, what else has to change?"
                with self.subTest(symbol=name):
                    self.complete(name, q)

    def test_every_wording_of_a_change_brings_both_directions(self):
        name = "backend.refunds.rules.needs_approval"
        for q in ["Add a required currency argument to needs_approval. What else has to change?",
                  "Rename needsApproval to requiresApproval.",
                  "Remove the amount parameter from needs_approval",
                  "Change NEEDS_APPROVAL so it returns a reason as well as yes or no",
                  "What breaks if I change the signature of needsApproval?",
                  "Make needs-approval take the customer's tier",
                  "What calls needs_approval?",
                  "What does needs_approval call?",
                  "Tell me about NeedsApproval"]:
            with self.subTest(question=q):
                self.complete(name, q)

    def test_the_trace_is_the_same_whatever_the_wording(self):
        def block(q):  # the needs_approval lines, as a set: the order follows the wording, the content must not
            return {line for line in names_only(recall.recall(q)).splitlines() if "needs_approval" in line}
        base = block("If I change needs_approval, what else is affected?")
        for q in ("What does needs_approval call?", "Rename needsApproval", "What calls NEEDS_APPROVAL?"):
            with self.subTest(question=q):
                self.assertEqual(block(q), base)

    def test_a_handler_change_shows_the_bodies_its_clients_send(self):
        facts = self.complete("backend.orders.views.handle_action", "Make handle_action require a reason field")
        code = "\n".join(facts.code)
        self.assertIn('frontend.api.cancelOrder sends action, order_id: return postAction({ action: "cancel", '
                      'order_id: orderId });', code)
        self.assertIn('backend.orders.views.handle_action reads action: action = payload["action"]', code)

    def test_space_runs_out_on_call_sites_and_never_on_dependents(self):
        name, q = "backend.refunds.rules.needs_approval", "Add a required currency argument to needs_approval."
        saved, recall.CODE_BUDGET = recall.CODE_BUDGET, 600
        try:
            facts = recall.recall(q)
        finally:
            recall.CODE_BUDGET = saved
        names = names_only(facts)
        for forward in (False, True):
            for other in closure(self.edges, name, forward):
                self.assertTrue(named(other, names), other)
        note = [line for line in facts.code if "call-site lines left out for space" in line]
        self.assertEqual(len(note), 1, "\n".join(facts.code))
        shown = sum(1 for line in facts.code if line.startswith("  "))
        full = sum(1 for line in recall.recall(q).code if line.startswith("  "))
        self.assertGreater(full, shown)
        self.assertIn(f"({full - shown} call-site lines left out", note[0])


class FanIn(unittest.TestCase):
    """Thirty callers of one function in three files: every one named, every call's line shown."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        code = cls.tmp / "code" / "app"
        for pkg in ("pricing", "checkout"):
            (code / pkg).mkdir(parents=True)
            (code / pkg / "__init__.py").write_text("", encoding="utf-8")
        (code / "pricing" / "discount.py").write_text(
            "def apply_discount(total):\n    return total * 0.9\n", encoding="utf-8")
        cls.callers = []
        for f in ("web", "batch", "admin"):
            body = ["from pricing.discount import apply_discount", ""]
            for i in range(10):
                fn = f"{f}_checkout_{i:02d}"
                cls.callers.append((f"app.checkout.{f}.{fn}", f"app/checkout/{f}.py", len(body) + 3))
                body += ["", f"def {fn}(total):", f"    return apply_discount(total + {i})"]
            (code / "checkout" / f"{f}.py").write_text("\n".join(body) + "\n", encoding="utf-8")
        cls.db = graphs.build(cls.tmp / "g", code=cls.tmp / "code")
        cls.saved, recall.DB = recall.DB, cls.db

    @classmethod
    def tearDownClass(cls):
        recall.DB = cls.saved
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_every_caller_and_every_call_is_there(self):
        facts = recall.recall("Add a rate argument to apply_discount. What has to change?")
        names, code = names_only(facts), "\n".join(facts.code)
        self.assertIn("app.pricing.discount.apply_discount is called by", names)
        for caller, file, line in self.callers:
            self.assertTrue(named(caller, names), caller)
            self.assertIn(f"  {file}:{line}, {caller} calls it: return apply_discount(", code)
        for f in ("web", "batch", "admin"):
            self.assertIn(f"  app/checkout/{f}.py:1, app/checkout/{f}.py imports it: "
                          "from pricing.discount import apply_discount", code)
        self.assertNotIn("left out for space", code)


class Freshness(unittest.TestCase):

    def test_a_code_line_changed_after_indexing_is_said_to_have_changed(self):
        tmp = Path(tempfile.mkdtemp())
        shop = tmp / "shop"
        shutil.copytree(SHOP, shop)
        db = graphs.build(tmp / "g", code=shop)
        config = shop / "backend" / "config.py"
        config.write_text(config.read_text(encoding="utf-8").replace("= 250", "= 500"), encoding="utf-8")
        saved, recall.DB = recall.DB, db
        try:
            text = recall.recall("What value does APPROVAL_THRESHOLD_GBP hold?").as_text()
        finally:
            recall.DB = saved
            shutil.rmtree(tmp, ignore_errors=True)
        self.assertIn("[backend/config.py changed since extraction: check it]", text)

    def test_a_call_site_changed_after_indexing_is_said_to_have_changed(self):
        tmp = Path(tempfile.mkdtemp())
        shop = tmp / "shop"
        shutil.copytree(SHOP, shop)
        db = graphs.build(tmp / "g", code=shop)
        views = shop / "backend" / "refunds" / "views.py"
        views.write_text(views.read_text(encoding="utf-8").replace('needs_approval(refund["amount"])',
                                                                    'needs_approval(refund["amount"], "GBP")'),
                         encoding="utf-8")
        saved, recall.DB = recall.DB, db
        try:
            code = recall.recall("Add a currency argument to needs_approval").code
        finally:
            recall.DB = saved
            shutil.rmtree(tmp, ignore_errors=True)
        self.assertIn('  backend/refunds/views.py:14, backend.refunds.views.create_refund calls it: '
                      'if needs_approval(refund["amount"]): [this line has changed since indexing: check it]', code)
        self.assertIn('  backend/orders/service.py:18, backend.orders.service.process_refund calls it: '
                      'if needs_approval(payload["amount"]):', code)  # untouched, so unmarked

    def test_the_build_refuses_a_call_site_the_code_lacks(self):
        from build_graph import problems

        doc = {"source_doc": "backend/refunds/views.py", "edges": [], "nodes": [],
               "sites": [{"source": "backend.refunds.views.create_refund", "predicate": "calls",
                          "target": "backend.refunds.rules.needs_approval", "line": 14,
                          "quote": 'if needs_approval(refund["amount"], "GBP"):'}]}
        self.assertTrue(any("does not contain the line" in p for p in problems([doc], SHOP)))

    def test_the_build_refuses_an_index_whose_quotes_the_code_lacks(self):
        from build_graph import problems

        doc = {"source_doc": "backend/config.py", "edges": [],
               "nodes": [{"name": "x", "type": "VARIABLE",
                          "claims": [{"kind": "value", "text": "X = 1", "quote": "X = 1"}]}]}
        self.assertTrue(any("does not contain the quote" in p for p in problems([doc], SHOP)))


if __name__ == "__main__":
    unittest.main()
