"""harness2cc: configuration, decision points, replays, the upstream Windows patch and `list-references`.

Every test builds its own transcripts (shaped like the ones Claude Code writes) and its own
harness2cc home folder in a temporary directory, and points HARNESS2CC_HOME at it, so nothing
reads or writes the real ~/.claude. Tests named after a scenario of
openspec/changes/claude-code-harness2-trial/specs/harness-improvement/spec.md verify that scenario.

Run with the harness2cc environment, which has upstream harness2 installed:
  ~/.claude/harness2cc/.venv/Scripts/python.exe -m unittest tests.test_harness2cc
The tests that need upstream harness2 are skipped, with that reason, in other environments.
"""
import contextlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from harness2cc import cli, config, decision_points, patch_upstream, replay  # noqa: E402

HARNESS2_AVAILABLE = importlib.util.find_spec("harness2") is not None
if HARNESS2_AVAILABLE:
    from harness2.core import tree as upstream_tree  # noqa: E402
    from harness2.substrate.opencode import OpencodeSubstrate  # noqa: E402

NEEDS_HARNESS2 = "needs upstream harness2: run with ~/.claude/harness2cc/.venv/Scripts/python.exe"
SESSION_ID = "11111111-aaaa-bbbb-cccc-000000000001"
OTHER_SESSION_ID = "22222222-aaaa-bbbb-cccc-000000000002"
PROJECT_FOLDER = "C--work-billing-etl"
WORKING_DIRECTORY = "C:\\work\\billing-etl"
TREE_FIXTURE_LINES = (
    '"""A stand-in for upstream core/tree.py: only the two lines the patch changes matter."""',
    "def read_tree(d):",
    "    for p in d.rglob('*'):",
    "        rel = str(p.relative_to(d))",
    "",
    "def write_tree(dest):",
    "    for p in dest.rglob('*'):",
    "        rel = str(p.relative_to(dest))",
)


class TranscriptBuilder:
    """Builds one transcript as Claude Code writes it: one JSON entry per line."""

    def __init__(self, session_id: str = SESSION_ID, working_directory: str = WORKING_DIRECTORY):
        self.session_id = session_id
        self.working_directory = working_directory
        self.entries: list[dict] = []

    def base(self, entry_type: str, uuid: str, timestamp: str) -> dict:
        return {"type": entry_type, "uuid": uuid, "sessionId": self.session_id, "timestamp": timestamp,
                "cwd": self.working_directory, "isSidechain": False}

    def prompt(self, uuid: str, timestamp: str, text: str) -> "TranscriptBuilder":
        entry = self.base("user", uuid, timestamp)
        entry["origin"] = {"kind": "human"}
        entry["message"] = {"role": "user", "content": text}
        self.entries.append(entry)
        return self

    def reply(self, uuid: str, timestamp: str, text: str) -> "TranscriptBuilder":
        entry = self.base("assistant", uuid, timestamp)
        entry["message"] = {"role": "assistant", "content": [{"type": "text", "text": text}]}
        self.entries.append(entry)
        return self

    def ask(self, uuid: str, timestamp: str, tool_use_id: str, question: str, header: str,
            labels: list[str]) -> "TranscriptBuilder":
        entry = self.base("assistant", uuid, timestamp)
        entry["message"] = {"role": "assistant", "content": [{
            "type": "tool_use", "id": tool_use_id, "name": "AskUserQuestion",
            "input": {"questions": [{"question": question, "header": header, "multiSelect": False,
                                     "options": [{"label": label, "description": ""} for label in labels]}]}}]}
        self.entries.append(entry)
        return self

    def answer(self, uuid: str, timestamp: str, tool_use_id: str, answers: dict[str, str] | None,
               is_error: bool = False) -> "TranscriptBuilder":
        entry = self.base("user", uuid, timestamp)
        entry["message"] = {"role": "user", "content": [{
            "type": "tool_result", "tool_use_id": tool_use_id, "is_error": is_error,
            "content": "User has answered your questions." if answers else "Tool call interrupted."}]}
        if answers is not None:
            entry["toolUseResult"] = {"answers": answers}
        self.entries.append(entry)
        return self

    def write(self, folder: Path, session_id: str | None = None) -> Path:
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{session_id or self.session_id}.jsonl"
        path.write_text("".join(json.dumps(entry) + "\n" for entry in self.entries), encoding="utf-8")
        return path


CHAT_QUESTIONS = """Here is the plan.

### Q1. Backfill scope

Should the revenue backfill include customers who closed their accounts before September?

- Context: 37 of 178 rows belong to closed accounts.
- Example: Acme Widgets closed on 2026-08-02.
- Options:
  - A. Exclude closed accounts (Recommended): cleaner averages.
  - B. Include them as-is: full sample.
  - D. Other: describe it in your reply.
- Reply with: `Q1: A`, or the letter you choose.
"""

SINGLE_CHAT_QUESTION = """### Q1. Retry limit

Should the nightly import retry 5 times instead of 3?

- Options:
  - A. Raise it to 5 (Recommended): fewer dead letters.
  - B. Keep 3: no change.
"""


def answered_session() -> TranscriptBuilder:
    """A session with one answered AskUserQuestion call and two answered chat questions."""
    return (TranscriptBuilder()
            .prompt("u1", "2026-10-01T09:00:00Z", "Plan the revenue backfill for billing-etl.")
            .ask("a1", "2026-10-01T09:01:00Z", "toolu_1", "Which table should the backfill write to?", "Target",
                 ["New table (Recommended)", "Existing table"])
            .answer("r1", "2026-10-01T09:02:00Z", "toolu_1",
                    {"Which table should the backfill write to?": "Existing table"})
            .reply("a2", "2026-10-01T09:03:00Z", CHAT_QUESTIONS)
            .prompt("u2", "2026-10-01T09:05:00Z", "Q1: B")
            .reply("a3", "2026-10-15T10:00:00Z", SINGLE_CHAT_QUESTION)
            .prompt("u3", "2026-10-15T10:01:00Z", "Option A, and keep going."))


def write_home(home: Path, transcript_roots: list[Path], drop_key: str | None = None) -> Path:
    """Write a complete harness2cc config.json into `home`, optionally without one key."""
    workspace = home / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    raw = json.loads((ROOT / "harness2cc" / "config.example.json").read_text(encoding="utf-8"))
    raw["workspace_root"] = str(workspace)
    raw["transcript_roots"] = [str(root) for root in transcript_roots]
    if drop_key:
        raw.pop(drop_key)
    (home / "config.json").write_text(json.dumps(raw), encoding="utf-8")
    return home


def run_cli(arguments: list[str]) -> tuple[int, str, str]:
    """Run `harness2cc` in-process and return its exit code, standard output and standard error."""
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        exit_code = cli.main(arguments)
    return exit_code, stdout.getvalue(), stderr.getvalue()


class TemporaryHome(unittest.TestCase):
    """A temporary harness2cc home and transcript folders, with HARNESS2CC_HOME pointing at the home."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.home = self.root / "harness2cc"
        self.home.mkdir()
        self.projects = self.root / "claude" / "projects"
        self.archive = self.root / "claude" / "session-archive"
        self.projects.mkdir(parents=True)
        self.archive.mkdir(parents=True)
        environment = mock.patch.dict(os.environ, {config.HOME_ENVIRONMENT_VARIABLE: str(self.home)})
        environment.start()
        self.addCleanup(environment.stop)


class ConfigurationTests(TemporaryHome):

    def test_a_missing_configuration_key_is_named(self):
        write_home(self.home, [self.projects], drop_key="models")
        with self.assertRaisesRegex(config.ConfigurationError, r"missing key 'models'"):
            config.load_config()
        exit_code, _, stderr = run_cli(["list-references"])
        self.assertEqual(exit_code, cli.EXIT_REFUSED)
        self.assertIn("missing key 'models'", stderr)

    def test_a_missing_transcript_folder_is_named(self):
        write_home(self.home, [self.root / "no-such-folder"])
        with self.assertRaisesRegex(config.ConfigurationError, r"transcript_roots.*no-such-folder"):
            config.load_config()

    def test_a_complete_configuration_loads(self):
        write_home(self.home, [self.projects, self.archive])
        loaded = config.load_config()
        self.assertEqual(loaded.home, self.home.resolve())
        self.assertEqual(loaded.models["grader"], "sonnet")
        self.assertEqual(loaded.caps["max_k"], 5)
        self.assertEqual(loaded.client_terms_file, self.home.resolve() / "client_terms.txt")


class DecisionPointTests(TemporaryHome):

    def test_an_answered_question_becomes_a_decision_point(self):
        answered_session().write(self.projects / PROJECT_FOLDER)
        scan = decision_points.scan_transcripts((self.projects,))
        by_question = {point.question: point for point in scan.decision_points}
        self.assertEqual(len(scan.decision_points), 3)

        tool_point = by_question["Which table should the backfill write to?"]
        self.assertEqual(tool_point.kind, "AskUserQuestion")
        self.assertEqual(tool_point.recommended, "New table (Recommended)")
        self.assertEqual(tool_point.turn_start_uuid, "u1")
        self.assertEqual(tool_point.project, "billing-etl")
        self.assertEqual(scan.labels[tool_point.decision_point_id].chosen, "Existing table")
        self.assertFalse(scan.labels[tool_point.decision_point_id].matches_recommended)

        chat_point = by_question[
            "Should the revenue backfill include customers who closed their accounts before September?"]
        self.assertEqual(chat_point.kind, "chat")
        self.assertEqual(chat_point.short_name, "Backfill scope")
        self.assertEqual(chat_point.turn_start_uuid, "u1")
        self.assertEqual(scan.labels[chat_point.decision_point_id].chosen, "B. Include them as-is: full sample.")

        single_point = by_question["Should the nightly import retry 5 times instead of 3?"]
        self.assertEqual(single_point.turn_start_uuid, "u2")
        self.assertTrue(scan.labels[single_point.decision_point_id].matches_recommended)

    def test_an_unanswered_question_is_not_a_decision_point(self):
        (TranscriptBuilder()
         .prompt("u1", "2026-10-01T09:00:00Z", "Plan it.")
         .ask("a1", "2026-10-01T09:01:00Z", "toolu_1", "Interrupted question?", "Cut", ["Yes (Recommended)", "No"])
         .answer("r1", "2026-10-01T09:02:00Z", "toolu_1", None)
         .ask("a2", "2026-10-01T09:03:00Z", "toolu_2", "Rejected question?", "Rejected", ["Yes (Recommended)", "No"])
         .answer("r2", "2026-10-01T09:04:00Z", "toolu_2", None, is_error=True)
         .reply("a3", "2026-10-01T09:05:00Z", CHAT_QUESTIONS)
         .prompt("u2", "2026-10-01T09:06:00Z", "Let me think about the backfill first.")
         .write(self.projects / PROJECT_FOLDER))
        scan = decision_points.scan_transcripts((self.projects,))
        self.assertEqual(scan.decision_points, [])

    def test_a_prompt_after_ide_context_and_a_slash_command_start_turns(self):
        (TranscriptBuilder()
         .prompt("u1", "2026-10-01T09:00:00Z",
                 "<ide_opened_file>The user opened the file C:\\work\\cache.py in the IDE.</ide_opened_file>"
                 "Plan the cache change.")
         .ask("a1", "2026-10-01T09:01:00Z", "toolu_1", "Cache lifetime?", "Cache", ["1 hour (Recommended)", "1 day"])
         .answer("r1", "2026-10-01T09:02:00Z", "toolu_1", {"Cache lifetime?": "1 day"})
         .prompt("u2", "2026-10-01T09:10:00Z",
                 "<command-message>opsx:apply</command-message>\n<command-name>/opsx:apply</command-name>\n"
                 "<command-args>cache-change</command-args>")
         .reply("a2", "2026-10-01T09:11:00Z", SINGLE_CHAT_QUESTION)
         .prompt("u3", "2026-10-01T09:12:00Z",
                 "<ide_opened_file>The user opened the file C:\\work\\retry.py in the IDE.</ide_opened_file>B")
         .write(self.projects / PROJECT_FOLDER))
        scan = decision_points.scan_transcripts((self.projects,))
        self.assertEqual(scan.skipped_without_turn_start, 0)
        by_short_name = {point.short_name: point for point in scan.decision_points}
        self.assertEqual(by_short_name["Cache"].turn_start_uuid, "u1")
        self.assertEqual(by_short_name["Retry limit"].turn_start_uuid, "u2")
        self.assertEqual(scan.labels[by_short_name["Retry limit"].decision_point_id].chosen, "B. Keep 3: no change.")

    def test_a_reply_that_starts_with_the_word_a_names_no_option(self):
        for reply in ("a mix of both: retry 4 times", "A better plan: retry 4 times on the first night"):
            with self.subTest(reply=reply):
                folder = self.projects / f"C--work-{len(reply)}"
                (TranscriptBuilder(session_id=f"{len(reply):08d}-aaaa-bbbb-cccc-000000000003")
                 .prompt("u1", "2026-10-15T10:00:00Z", "Plan the nightly import retries.")
                 .reply("a1", "2026-10-15T10:01:00Z", SINGLE_CHAT_QUESTION)
                 .prompt("u2", "2026-10-15T10:02:00Z", reply)
                 .write(folder))
                scan = decision_points.scan_transcripts((folder,))
                self.assertEqual(scan.decision_points, [])

    def test_a_single_answer_needs_option_or_the_letter_alone_or_before_punctuation(self):
        open_questions = decision_points.parse_chat_questions(SINGLE_CHAT_QUESTION)
        expected_answers = {
            "B": {"1": "B"},
            "b.": {"1": "B"},
            "(A)": {"1": "A"},
            "A. and also keep the alert": {"1": "A"},
            "B, but log each retry": {"1": "B"},
            "B) keep 3": {"1": "B"},
            "Option A, and keep going.": {"1": "A"},
            "option b": {"1": "B"},
            "a mix of both": {},
            "A better plan: retry 4 times": {},
            "Also check the alert first": {},
            "C": {},
        }
        for reply, expected in expected_answers.items():
            with self.subTest(reply=reply):
                self.assertEqual(decision_points.parse_chat_answers(reply, open_questions), expected)

    def test_archived_copies_of_a_session_are_counted_once(self):
        session = answered_session()
        session.write(self.projects / PROJECT_FOLDER)
        session.write(self.archive / PROJECT_FOLDER)
        scan = decision_points.scan_transcripts((self.projects, self.archive))
        self.assertEqual(scan.transcripts_read, 2)
        self.assertEqual(len(scan.decision_points), 3)
        self.assertEqual(len({point.decision_point_id for point in scan.decision_points}), 3)
        self.assertTrue(all(point.transcript.startswith(str(self.projects)) for point in scan.decision_points))

    def test_list_references_filters_by_date_project_and_mismatch(self):
        answered_session().write(self.projects / PROJECT_FOLDER)
        (TranscriptBuilder(session_id=OTHER_SESSION_ID, working_directory="C:\\work\\shop-api")
         .prompt("v1", "2026-10-20T08:00:00Z", "Plan the cache change.")
         .ask("b1", "2026-10-20T08:01:00Z", "toolu_9", "Cache lifetime?", "Cache", ["1 hour (Recommended)", "1 day"])
         .answer("s1", "2026-10-20T08:02:00Z", "toolu_9", {"Cache lifetime?": "1 day"})
         .write(self.projects / "C--work-shop-api"))
        write_home(self.home, [self.projects])

        exit_code, everything, _ = run_cli(["list-references"])
        self.assertEqual(exit_code, cli.EXIT_DONE)
        self.assertIn("4 of 4 decision points shown", everything)

        _, mismatches, _ = run_cli(["list-references", "--mismatch-only"])
        self.assertIn("3 of 4 decision points shown", mismatches)
        self.assertNotIn("Retry limit", mismatches)

        _, recent, _ = run_cli(["list-references", "--since", "2026-10-10"])
        self.assertIn("2 of 4 decision points shown", recent)
        self.assertNotIn("Backfill scope", recent)

        _, shop, _ = run_cli(["list-references", "--project", "shop"])
        self.assertIn("1 of 4 decision points shown", shop)
        self.assertIn("Cache", shop)
        self.assertLess(shop.index("Cache"), shop.index("1 of 4"))

        exit_code, _, stderr = run_cli(["list-references", "--since", "last week"])
        self.assertEqual(exit_code, cli.EXIT_USAGE)
        self.assertIn("YYYY-MM-DD", stderr)

    def test_data_files_are_written_under_the_harness2cc_home(self):
        answered_session().write(self.projects / PROJECT_FOLDER)
        write_home(self.home, [self.projects])
        exit_code, output, _ = run_cli(["list-references"])
        self.assertEqual(exit_code, cli.EXIT_DONE)
        decision_points_file = self.home / "decision_points.jsonl"
        labels_file = self.home / "labels.jsonl"
        self.assertIn(str(decision_points_file.resolve()), output)
        rows = [json.loads(line) for line in decision_points_file.read_text(encoding="utf-8").splitlines()]
        labels = [json.loads(line) for line in labels_file.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(rows), 3)
        self.assertTrue(all("chosen" not in row for row in rows))
        self.assertEqual({label["decision_point_id"] for label in labels}, {row["decision_point_id"] for row in rows})
        for folder in (ROOT, ROOT / "harness2cc", ROOT / "tests"):
            self.assertEqual(sorted(folder.glob("decision_points.jsonl")) + sorted(folder.glob("labels.jsonl")), [])


class ReplayTests(TemporaryHome):

    def test_the_replay_holds_no_answer(self):
        long_reply = "Findings: " + "the August totals tie out. " * 300
        transcript = (TranscriptBuilder()
                      .prompt("u1", "2026-10-01T09:00:00Z", "Look at the August totals.")
                      .reply("a1", "2026-10-01T09:02:00Z", long_reply)
                      .prompt("u2", "2026-10-01T09:10:00Z", "Now plan the revenue backfill.")
                      .reply("a2", "2026-10-01T09:11:00Z", CHAT_QUESTIONS)
                      .prompt("u3", "2026-10-01T09:12:00Z", "Q1: B")
                      .reply("a3", "2026-10-01T09:13:00Z", "Including closed accounts as you chose.")
                      .write(self.projects / PROJECT_FOLDER))
        scan = decision_points.scan_transcripts((self.projects,))
        point = scan.decision_points[0]
        self.assertEqual(point.turn_start_uuid, "u2")
        replay_path = replay.write_replay(point, self.root / "run" / point.decision_point_id)
        text = replay_path.read_text(encoding="utf-8")
        self.assertIn("Now plan the revenue backfill.", text)
        self.assertIn("Look at the August totals.", text)
        self.assertIn("[cut:", text)
        for leaked in ("(Recommended)", "Backfill scope", "Q1: B", "Including closed accounts", str(transcript)):
            self.assertNotIn(leaked, text.replace(str(self.root / "run"), ""))
        self.assertTrue(text.rstrip().endswith(replay.CLOSING_INSTRUCTION.rstrip()))

    def test_a_prompt_after_ide_context_stays_in_the_replay(self):
        (TranscriptBuilder()
         .prompt("u1", "2026-10-01T09:00:00Z",
                 "<ide_opened_file>The user opened the file C:\\work\\cache.py in the IDE.</ide_opened_file>"
                 "Plan the cache change for the nightly import.")
         .ask("a1", "2026-10-01T09:01:00Z", "toolu_1", "Cache lifetime?", "Cache", ["1 hour (Recommended)", "1 day"])
         .answer("r1", "2026-10-01T09:02:00Z", "toolu_1", {"Cache lifetime?": "1 day"})
         .write(self.projects / PROJECT_FOLDER))
        point = decision_points.scan_transcripts((self.projects,)).decision_points[0]
        text = replay.write_replay(point, self.root / "run").read_text(encoding="utf-8")
        self.assertIn("Plan the cache change for the nightly import.", text)
        self.assertNotIn("ide_opened_file", text)
        self.assertNotIn("Cache lifetime?", text)

    def test_a_replay_of_a_missing_turn_is_refused(self):
        answered_session().write(self.projects / PROJECT_FOLDER)
        point = decision_points.scan_transcripts((self.projects,)).decision_points[0]
        moved = decision_points.DecisionPoint(**{**point.__dict__, "turn_start_uuid": "gone"})
        with self.assertRaisesRegex(replay.ReplayError, "has no entry gone"):
            replay.write_replay(moved, self.root / "run")

    def test_a_long_replay_keeps_its_opening_and_its_end(self):
        digest = "OPENING " + "x" * (replay.MAXIMUM_REPLAY_CHARACTERS * 2) + " LAST PROMPT"
        shortened = replay.shorten_replay(digest)
        self.assertLess(len(shortened), replay.MAXIMUM_REPLAY_CHARACTERS + 200)
        self.assertTrue(shortened.startswith("OPENING"))
        self.assertTrue(shortened.endswith("LAST PROMPT"))
        self.assertIn("characters of the middle of the conversation are left out", shortened)


class UpstreamPatchTests(unittest.TestCase):

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.tree_path = Path(temporary.name) / "tree.py"
        self.tree_path.write_bytes("\r\n".join(TREE_FIXTURE_LINES).encode("utf-8") + b"\r\n")

    def test_the_upstream_patch_is_safe_to_rerun(self):
        first = patch_upstream.patch_tree_file(self.tree_path)
        self.assertEqual([message.split(":")[0] for message in first], ["line 4 patched", "line 8 patched"])
        patched_bytes = self.tree_path.read_bytes()
        self.assertIn(b"        rel = p.relative_to(d).as_posix()\r\n", patched_bytes)
        self.assertIn(b"        rel = p.relative_to(dest).as_posix()\r\n", patched_bytes)
        self.assertNotIn(b"str(p.relative_to", patched_bytes)
        self.assertEqual(patched_bytes.count(b"\r\n"), len(TREE_FIXTURE_LINES))
        second = patch_upstream.patch_tree_file(self.tree_path)
        self.assertTrue(all("already patched" in message for message in second))
        self.assertEqual(self.tree_path.read_bytes(), patched_bytes)
        self.assertTrue(patch_upstream.is_tree_file_patched(self.tree_path))

    def test_the_upstream_patch_leaves_hard_linked_copies_alone(self):
        cached_copy = self.tree_path.with_name("cached_tree.py")
        os.link(self.tree_path, cached_copy)
        original_bytes = cached_copy.read_bytes()
        patch_upstream.patch_tree_file(self.tree_path)
        self.assertTrue(patch_upstream.is_tree_file_patched(self.tree_path))
        self.assertEqual(cached_copy.read_bytes(), original_bytes)
        self.assertFalse(self.tree_path.with_name("tree.py.harness2cc-new").exists())

    def test_the_upstream_patch_stops_on_unexpected_lines(self):
        self.tree_path.write_text("def read_tree(d):\n    rel = d.name\n", encoding="utf-8")
        before = self.tree_path.read_bytes()
        with self.assertRaisesRegex(patch_upstream.UpstreamPatchError, r"tree\.py: expected exactly one line"):
            patch_upstream.patch_tree_file(self.tree_path)
        self.assertEqual(self.tree_path.read_bytes(), before)
        self.assertFalse(patch_upstream.is_tree_file_patched(self.tree_path))

    @unittest.skipUnless(HARNESS2_AVAILABLE, NEEDS_HARNESS2)
    def test_the_upstream_patch_fixes_windows_paths(self):
        self.assertEqual(patch_upstream.installed_upstream_commit(), patch_upstream.PINNED_UPSTREAM_COMMIT)
        self.assertTrue(patch_upstream.is_tree_file_patched(patch_upstream.installed_tree_file()),
                        "run `harness2cc patch-upstream` first")
        harness_folder = Path(self.tree_path.parent) / "harness"
        (harness_folder / "scripts").mkdir(parents=True)
        (harness_folder / "scripts" / "check_totals.py").write_text("print('ok')\n", encoding="utf-8")
        surface = OpencodeSubstrate().surface()
        tree = upstream_tree.read_tree(surface, harness_folder)
        self.assertIn("scripts/check_totals.py", tree)
        self.assertFalse(any("\\" in key for key in tree))


if __name__ == "__main__":
    unittest.main()
