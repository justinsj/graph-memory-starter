"""When the graph knows no name in the prompt: passages from the RAG index, labelled.

The hook runs as Claude Code runs it, against a temp graph and a temp RAG index
built from corpus-before/. Without fastembed the index is keyword only, which
is enough for these questions.
"""
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from graphs import REFUND, ROOT, build

sys.path.insert(0, str(ROOT / "rag"))
import build_index  # noqa: E402

BOSS = "Who is in charge when the boss is away?"


class Fallback(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.db = str(build(cls.tmp.name))
        cls.rag = Path(cls.tmp.name) / "rag.db"
        saved, build_index.DB = build_index.DB, cls.rag
        argv, sys.argv = sys.argv, ["build_index.py"]  # the default corpus: corpus-before
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                build_index.main()
        finally:
            sys.argv, build_index.DB = argv, saved

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def hook(self, prompt, rag=None):
        env = {**os.environ, "GRAPH_MEMORY_DB": self.db,
               "GRAPH_MEMORY_RAG_DB": str(rag or self.rag),
               "GRAPH_MEMORY_STATE": str(Path(self.tmp.name) / "state")}
        out = subprocess.run([sys.executable, "src/recall_hook.py"],
                             input=json.dumps({"prompt": prompt}, ensure_ascii=False).encode("utf-8"),
                             capture_output=True, cwd=ROOT, env=env, timeout=120)
        self.assertEqual(out.returncode, 0, out.stderr.decode("utf-8", "replace"))
        reply = json.loads(out.stdout.decode("utf-8"))
        return reply["systemMessage"], reply["hookSpecificOutput"]["additionalContext"]

    def test_no_names_brings_labelled_passages(self):
        status, context = self.hook(BOSS)
        self.assertIn("(no memory matches for this prompt)", context)  # still said out loud
        self.assertIn("These are search results, not checked facts", context)
        self.assertIn("[ooo-march-sarah.md", context)  # the out-of-office note
        self.assertIn("passages from your notes", status)

    def test_passages_stay_within_the_budget(self):
        _, context = self.hook(BOSS)
        passages = context.split("not checked facts:\n", 1)[1].splitlines()
        self.assertLessEqual(len(passages), 3)
        self.assertLessEqual(sum(len(p) for p in passages), 1500)

    def test_a_graph_answer_brings_no_passages(self):
        _, context = self.hook(REFUND)
        self.assertNotIn("search results", context)

    def test_without_an_index_the_loud_line_stays_alone(self):
        status, context = self.hook(BOSS, rag=Path(self.tmp.name) / "none.db")
        self.assertTrue(context.endswith("(no memory matches for this prompt)"))
        self.assertNotIn("passages", status)


if __name__ == "__main__":
    unittest.main()
