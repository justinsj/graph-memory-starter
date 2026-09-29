"""The three hooks as Claude Code runs them: a fresh process, JSON on stdin.

Claude Code sends UTF-8. These tests send UTF-8 bytes and clear the Python
encoding overrides, so on Windows they fail if a hook reads with the code page.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

from graphs import ROOT, build

FINANCE = {  # a name only UTF-8 can carry
    "source_doc": "finance.md",
    "nodes": [{"name": "Finance Lead", "type": "ROLE", "description": "Signs off expenses"},
              {"name": "José García", "type": "PERSON", "description": "Finance Lead"}],
    "edges": [{"source": "Finance Lead", "predicate": "held_by", "target": "José García"}],
    "aliases": [{"entity": "José García", "alias": "José"}],
}


def run(argv, payload, **env):
    child_env = {k: v for k, v in os.environ.items()
                 if k not in ("PYTHONIOENCODING", "PYTHONUTF8")}
    child_env.update(env)
    out = subprocess.run(argv, input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                         capture_output=True, cwd=ROOT, env=child_env, timeout=60)
    if out.returncode != 0:
        raise AssertionError(out.stderr.decode("utf-8", "replace"))
    return out.stdout.decode("utf-8")


class GraphHook(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.db = str(build(cls.tmp.name, FINANCE))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def hook(self, prompt):
        out = run([sys.executable, "src/recall_hook.py"], {"prompt": prompt},
                  GRAPH_MEMORY_DB=self.db)
        return json.loads(out)

    def test_output_is_what_claude_code_reads(self):
        out = self.hook("What does Priya do?")
        self.assertTrue(out["systemMessage"].startswith("memory: "))
        self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "UserPromptSubmit")
        self.assertIn("Support Lead held_by Priya Patel", out["hookSpecificOutput"]["additionalContext"])

    def test_non_ascii_name_is_found(self):
        context = self.hook("What does José do?")["hookSpecificOutput"]["additionalContext"]
        self.assertIn("Finance Lead held_by José García", context)

    def test_no_match_still_answers(self):
        context = self.hook("Who is in charge when the boss is away?")["hookSpecificOutput"]
        self.assertIn("(no memory matches for this prompt)", context["additionalContext"])


class RagHook(unittest.TestCase):

    def test_prompt_arrives_intact(self):
        # the search itself is stubbed: this is about reading the prompt
        code = ("import sys; sys.path.insert(0, 'rag'); import recall_hook as h; "
                "h.DB = type('P', (), {'is_file': lambda self: True})(); "
                "h.hits = lambda q: [('[echo]', q)]; h.main()")
        out = json.loads(run([sys.executable, "-c", code], {"prompt": "What does José do?"}))
        self.assertIn("What does José do?", out["hookSpecificOutput"]["additionalContext"])


class DigestHook(unittest.TestCase):

    def test_transcript_path_arrives_intact(self):
        path = r"C:\Users\José\.claude\projects\t.jsonl"
        code = ("import json, sys; sys.path.insert(0, 'digest'); import session_end; "
                "print(json.dumps(session_end.read_stdin()))")
        out = json.loads(run([sys.executable, "-c", code], {"transcript_path": path}))
        self.assertEqual(out["transcript_path"], path)


if __name__ == "__main__":
    unittest.main()
