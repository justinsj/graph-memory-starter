"""Source quotes in the injection: why the model need not go and read the files.

Each claim carries the source's own words. The build checks them; recall
quotes them within a budget, checked against the files as they are now; the
hook does not repeat them within a conversation. Also: the provenance line,
unknowns stated as claims, and the build's coverage warnings.
"""
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from graphs import REFUND, ROOT, build, build_graph, claims, recall

JUNE = "Who approves a £300 refund in June 2025?"
REFUND_DOC = {"name": "Refund approvals", "type": "POLICY"}


def doc(*nodes, source="refund-policy.md"):
    return {"source_doc": source, "nodes": list(nodes), "edges": []}


class QuotesAtBuild(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def refused(self, *extra) -> str:
        with self.assertRaises(SystemExit) as stop:
            build(Path(self.tmp.name), *extra)
        return str(stop.exception)

    def test_a_paraphrase_is_refused(self):
        message = self.refused(doc({**REFUND_DOC, "claims": [
            {"kind": "rule", "text": "x", "quote": "Refunds above £500 need the Ops Manager."}]}))
        self.assertIn("does not contain the quote", message)

    def test_markdown_and_spacing_do_not_count(self):
        # the source says "**Ops Manager**" across one line; the quote is plain text
        build(Path(self.tmp.name), doc({**REFUND_DOC, "claims": [{
            "kind": "rule", "text": "x",
            "quote": "Refunds over £500 require approval by the  Ops Manager before payment"}]}))

    def test_a_quote_too_long_is_refused(self):
        message = self.refused(doc({**REFUND_DOC, "claims": [
            {"kind": "rule", "text": "x", "quote": "a" * (build_graph.MAX_QUOTE + 1)}]}))
        self.assertIn("quote at most 300", message)

    def test_a_quote_from_a_missing_document_is_refused(self):
        message = self.refused(doc({**REFUND_DOC, "claims": [
            {"kind": "rule", "text": "x", "quote": "anything"}]}, source="nowhere.md"))
        self.assertIn("nowhere.md is not in", message)


class Coverage(unittest.TestCase):

    def test_the_repo_graph_has_no_gaps(self):
        with tempfile.TemporaryDirectory() as tmp:
            ext = Path(tmp) / "extraction"
            shutil.copytree(ROOT / "extraction", ext)
            result = build_graph.build(extraction=ext, db_path=Path(tmp) / "g.db", records=Path(tmp) / "records")
        self.assertEqual(result["warnings"], [])

    def test_a_role_nobody_holds_is_a_gap(self):
        with tempfile.TemporaryDirectory() as tmp:
            ext = Path(tmp) / "extraction"
            shutil.copytree(ROOT / "extraction", ext)
            (ext / "zz.json").write_text(json.dumps(doc(
                {"name": "Auditor", "type": "ROLE", "claims": [{"kind": "note", "text": "Audits"}]},
                source="x.md")), encoding="utf-8")
            result = build_graph.build(extraction=ext, db_path=Path(tmp) / "g.db", records=Path(tmp) / "records")
        self.assertEqual(result["warnings"], [
            "Auditor: a role nobody holds - add a held_by link, or an unknown claim "
            "saying the documents name nobody"])


class QuotesAtRecall(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.saved, recall.DB = recall.DB, build(cls.tmp.name)

    @classmethod
    def tearDownClass(cls):
        recall.DB = cls.saved
        cls.tmp.cleanup()

    def test_provenance_line_tells_the_model_how_to_use_the_facts(self):
        second = recall.recall(REFUND).as_text().splitlines()[1]
        self.assertTrue(second.startswith("These facts come from your documents (9, extracted "))
        self.assertIn("open a file only if its line says it changed or is missing", second)
        # no folder named: a folder the model cannot find sent it looking
        self.assertNotIn("corpus", second)

    def test_the_model_is_not_told_the_timing(self):
        facts = recall.recall(REFUND)
        self.assertEqual(facts.as_text().splitlines()[0], "memory: 8 facts, for March 2026")
        self.assertIn("recalled in", facts.header())  # the user's status line keeps it

    def test_the_answer_comes_with_its_sources(self):
        facts = recall.recall(REFUND)
        quoted = {(d, q) for d, q, _ in facts.excerpts}
        self.assertIn(("delegation-memo.md",
                       "During this period all of her sign-offs and approvals are delegated to "
                       "Marcus Webb."), quoted)
        self.assertIn(("refund-policy.md", "Refunds over £500 require approval by the Ops Manager "
                       "before payment is released."), quoted)
        self.assertTrue(all(status == "ok" for _, _, status in facts.excerpts))
        # the quote stands in for the claim's paraphrase, with its source and dates
        self.assertIn('\nRefund approvals: "Refunds over £500 require approval by the Ops Manager '
                      'before payment is released." [refund-policy.md] (from 2026-01-01)',
                      facts.as_text())

    def test_an_unknown_keeps_its_own_words(self):
        text = recall.recall(JUNE).as_text()
        self.assertIn("\nDirector: The 2024 refund policy names no person for the Director role "
                      "(until 2025-12-31)", text)

    def test_quotes_stay_within_the_budget(self):
        for q in (REFUND, JUNE, "How has the refund approval threshold changed?",
                  "Who approves supplier payments over £2,000?"):
            facts = recall.recall(q)
            self.assertLessEqual(len(facts.excerpts), recall.MAX_EXCERPTS)
            self.assertLessEqual(sum(len(d) + len(t) + 6 for d, t, _ in facts.excerpts),
                                 recall.EXCERPT_BUDGET)
            self.assertEqual(len(facts.excerpts), len({t for _, t, _ in facts.excerpts}))

    def test_what_the_documents_leave_open_is_said(self):
        facts = recall.recall(JUNE)
        self.assertIn(("Director", "The 2024 refund policy names no person for the Director role"),
                      claims(facts))

    def test_quotes_already_sent_are_not_repeated(self):
        first = recall.recall(REFUND)
        again = recall.recall(REFUND, sent=frozenset(first.excerpt_keys))
        # none of the first quotes again; the budget they freed may carry the next ones
        self.assertFalse(set(first.excerpt_keys) & set(again.excerpt_keys))
        self.assertEqual(again.repeats, len(first.excerpts))
        self.assertEqual(again.as_text().count(", quoted earlier]"), len(first.excerpts))
        # once everything has been sent, only the note remains
        third = recall.recall(REFUND, sent=frozenset(first.excerpt_keys + again.excerpt_keys))
        self.assertEqual(third.excerpts, [])


class ChangedDocuments(unittest.TestCase):
    """A file edited or removed after the build is said out loud, not left to find."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.docs = Path(self.tmp.name) / "docs"
        shutil.copytree(ROOT / "corpus", self.docs)
        self.saved, recall.DB = recall.DB, build(Path(self.tmp.name) / "g", docs=self.docs)

    def tearDown(self):
        recall.DB = self.saved
        self.tmp.cleanup()

    def status(self, doc, quote_part=""):
        return {s for d, q, s in recall.recall(REFUND).excerpts if d == doc and quote_part in q}

    def test_unchanged(self):
        self.assertEqual(self.status("refund-policy.md"), {"ok"})

    def test_changed_file(self):
        path = self.docs / "refund-policy.md"
        path.write_text(path.read_text(encoding="utf-8").replace("£500", "£600"), encoding="utf-8")
        self.assertEqual(self.status("refund-policy.md", "£500"), {"changed"})
        self.assertEqual(self.status("refund-policy.md", "original payment method"), {"ok"})
        self.assertIn("[refund-policy.md changed since extraction: check it]",
                      recall.recall(REFUND).as_text())

    def test_missing_file(self):
        (self.docs / "delegation-memo.md").unlink()
        self.assertEqual(self.status("delegation-memo.md"), {"missing"})
        self.assertIn("[delegation-memo.md is no longer in the documents folder]",
                      recall.recall(REFUND).as_text())


class HookSessions(unittest.TestCase):
    """The hook as Claude Code runs it: one process per prompt, the same session id."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.db = str(build(cls.tmp.name))
        cls.state = str(Path(cls.tmp.name) / "state")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def hook(self, payload, *args):
        env = {**os.environ, "GRAPH_MEMORY_DB": self.db, "GRAPH_MEMORY_STATE": self.state}
        out = subprocess.run([sys.executable, "src/recall_hook.py", *args],
                             input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                             capture_output=True, cwd=ROOT, env=env, timeout=60)
        self.assertEqual(out.returncode, 0, out.stderr.decode("utf-8", "replace"))
        text = out.stdout.decode("utf-8")
        return json.loads(text)["hookSpecificOutput"]["additionalContext"] if text else ""

    def quotes(self, context):
        return [ln for ln in context.splitlines() if '" [' in ln]

    def test_a_conversation_sees_each_quote_once_until_it_is_compacted(self):
        ask = {"session_id": "s-1", "prompt": REFUND}
        first = self.quotes(self.hook(ask))
        self.assertTrue(first)
        second = self.hook(ask)
        self.assertFalse(set(first) & set(self.quotes(second)))  # nothing twice
        self.assertIn(", quoted earlier]", second)
        self.hook(ask)  # by now every quote for this question has been sent
        self.hook({"session_id": "s-1", "source": "resume"}, "--forget")  # resuming keeps them
        self.assertEqual(self.quotes(self.hook(ask)), [])
        self.hook({"session_id": "s-1", "trigger": "auto"}, "--forget")  # compaction drops them
        self.assertEqual(self.quotes(self.hook(ask)), first)

    def test_sessions_do_not_share(self):
        self.hook({"session_id": "s-2", "prompt": REFUND})
        self.assertTrue(self.quotes(self.hook({"session_id": "s-3", "prompt": REFUND})))


if __name__ == "__main__":
    unittest.main()
