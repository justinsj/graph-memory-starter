"""session_merge: the transcript digest, finding sessions, naming handoff files, and the secrets check.

Every test builds its own Claude config folder in a temporary directory, with
transcripts shaped like the ones Claude Code writes, and points
CLAUDE_CONFIG_DIR at it, so nothing reads or writes the real ~/.claude.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "sessionmerge" / "session_merge.py"
sys.path.insert(0, str(SCRIPT.parent))

import session_merge  # noqa: E402

SOURCE_SESSION_ID = "11111111-aaaa-bbbb-cccc-000000000001"
CLOSED_SESSION_ID = "22222222-aaaa-bbbb-cccc-000000000002"
ARCHIVED_SESSION_ID = "33333333-aaaa-bbbb-cccc-000000000003"
PROJECT_FOLDER = "C--work-repo"

# Built at runtime so secret scanners do not flag this file.
FAKE_AWS_KEY = "AKIA" + "IOSFODNN7EXAMPLE"
FAKE_GITHUB_TOKEN = "ghp_" + "a1" * 18
FAKE_SLACK_TOKEN = "xoxb-" + "1234567890-abcdef"
FAKE_API_KEY = "sk-ant-" + "api03-" + "b2" * 12
FAKE_JWT = "eyJ" + "hbGciOiJIUzI1NiJ9" + ".eyJzdWIiOiIxMjM0NTY3ODkwIn0" + ".dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
FAKE_PRIVATE_KEY = "-----BEGIN RSA " + "PRIVATE KEY-----"


def user_entry(text: object, timestamp: str, **fields: object) -> dict:
    """Build a user-role transcript entry."""
    return {"type": "user", "timestamp": timestamp, "message": {"role": "user", "content": text}, **fields}


def assistant_entry(blocks: list[dict], timestamp: str, **fields: object) -> dict:
    """Build an assistant transcript entry."""
    return {"type": "assistant", "timestamp": timestamp, "message": {"role": "assistant", "content": blocks}, **fields}


def full_conversation() -> list[object]:
    """A transcript with every kind of entry the digest handles, including one that is not JSON."""
    return [
        {"type": "custom-title", "customTitle": "Fix invoice loader", "sessionId": SOURCE_SESSION_ID},
        {"type": "agent-name", "agentName": "TICKET-12 invoice HOLD", "sessionId": SOURCE_SESSION_ID},
        user_entry("Keep first-day lines; do not drop them.", "2026-10-20T14:03:11.000Z",
                   origin={"kind": "human"}, cwd="C:/work/repo"),
        user_entry([{"type": "text", "text": "Base directory for this skill: SKILL BODY TEXT"}],
                   "2026-10-20T14:03:12.000Z", isMeta=True),
        user_entry("<command-message>rename</command-message>\n<command-name>/rename</command-name>\n"
                   "<command-args>TICKET-12 HOLD</command-args>", "2026-10-20T14:04:00.000Z", origin={"kind": "human"}),
        assistant_entry([
            {"type": "thinking", "thinking": "PRIVATE THINKING TEXT"},
            {"type": "text", "text": "Plan: rerun the loader tests first."},
            {"type": "tool_use", "name": "Bash", "input": {"command": "pytest -x", "description": "Run loader tests"}},
            {"type": "tool_use", "name": "Edit", "input": {"file_path": "C:/work/repo/loader.py", "old_string": "a"}},
        ], "2026-10-20T14:05:00.000Z"),
        user_entry([{"type": "tool_result", "tool_use_id": "t1", "is_error": True,
                     "content": "Exit code 1\nAssertionError: 3 != 4"}], "2026-10-20T14:05:30.000Z",
                   toolUseResult={"stderr": "x"}),
        user_entry([{"type": "tool_result", "tool_use_id": "t2", "content": "SUCCESSFUL TOOL OUTPUT"}],
                   "2026-10-20T14:05:40.000Z", toolUseResult={"stdout": "x"}),
        assistant_entry([{"type": "text", "text": "SIDECHAIN TEXT"}], "2026-10-20T14:06:00.000Z", isSidechain=True),
        "{this line is not json",
        {"type": "system", "subtype": "compact_boundary", "timestamp": "2026-10-20T15:00:00.000Z"},
        user_entry("This session is being continued from a previous conversation. Summary: kept first-day lines.",
                   "2026-10-20T15:00:01.000Z", isCompactSummary=True),
        user_entry([{"type": "text", "text": "Another Claude session sent a message: PR #145 merged."}],
                   "2026-10-20T15:10:00.000Z", isMeta=True, origin={"kind": "peer"}),
        user_entry("<task-notification>Background tests finished: 52 passed</task-notification>",
                   "2026-10-20T15:20:00.000Z", origin={"kind": "task-notification"}),
        user_entry([{"type": "text", "text": "[Request interrupted by user]"}], "2026-10-20T15:21:00.000Z"),
        user_entry([{"type": "text", "text": "<system-reminder>REMINDER TEXT</system-reminder>"}],
                   "2026-10-20T15:22:00.000Z", isMeta=True),
        assistant_entry([{"type": "text", "text": "Done after the summary."}], "2026-10-20T15:30:00.000Z"),
        {"type": "file-history-snapshot", "snapshot": {"FILE HISTORY": "x"}},
    ]


def write_transcript(path: Path, entries: list[object]) -> Path:
    """Write entries as a .jsonl transcript; a string entry is written as a raw line."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as transcript_file:
        for entry in entries:
            transcript_file.write((entry if isinstance(entry, str) else json.dumps(entry)) + "\n")
    return path


class ClaudeFolder(unittest.TestCase):
    """A temporary Claude config folder with projects/, session-archive/ and sessions/."""

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.claude_directory = Path(self.temporary_directory.name)
        self.projects = self.claude_directory / "projects" / PROJECT_FOLDER
        self.archive = self.claude_directory / "session-archive" / PROJECT_FOLDER
        self.sessions = self.claude_directory / "sessions"
        self.sessions.mkdir(parents=True)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def add_live_session(self, session_id: str, name: str, process_id: int = 4242) -> None:
        """Write the record Claude Code keeps for an open session."""
        record = {"pid": process_id, "sessionId": session_id, "cwd": "C:\\work\\repo", "name": name, "status": "idle"}
        (self.sessions / f"{process_id}.json").write_text(json.dumps(record), encoding="utf-8")

    def run_script(self, *arguments: str, session_id: str | None = None) -> subprocess.CompletedProcess:
        """Run the script as a fresh process, the way the skill runs it."""
        environment = {key: value for key, value in os.environ.items() if key != "CLAUDE_CODE_SESSION_ID"}
        environment["CLAUDE_CONFIG_DIR"] = str(self.claude_directory)
        environment["PYTHONIOENCODING"] = "utf-8"
        if session_id:
            environment["CLAUDE_CODE_SESSION_ID"] = session_id
        return subprocess.run([sys.executable, str(SCRIPT), *arguments], capture_output=True, text=True,
                              encoding="utf-8", env=environment, timeout=60)


class DigestTests(ClaudeFolder):
    def setUp(self) -> None:
        super().setUp()
        self.transcript = write_transcript(self.projects / f"{SOURCE_SESSION_ID}.jsonl", full_conversation())
        self.digest = session_merge.build_digest(self.transcript)
        self.text = session_merge.render_digest(self.digest)

    def test_keeps_prompts_commands_replies_and_tool_lines(self) -> None:
        self.assertIn("[2026-10-20 14:03] USER\nKeep first-day lines; do not drop them.", self.text)
        self.assertIn("USER RAN\n/rename TICKET-12 HOLD", self.text)
        self.assertIn("CLAUDE\nPlan: rerun the loader tests first.", self.text)
        self.assertIn("TOOL Bash: Run loader tests", self.text)
        self.assertIn("TOOL Edit: C:/work/repo/loader.py", self.text)
        self.assertIn("TOOL ERROR\nExit code 1\nAssertionError: 3 != 4", self.text)
        self.assertIn("MESSAGE FROM ANOTHER SESSION OR SUBAGENT\nAnother Claude session sent a message: PR #145 merged.", self.text)
        self.assertIn("TASK NOTIFICATION\n<task-notification>Background tests finished: 52 passed", self.text)
        self.assertIn("USER INTERRUPTED", self.text)
        self.assertIn("CLAUDE\nDone after the summary.", self.text)

    def test_leaves_out_thinking_skill_bodies_reminders_sidechains_and_successful_results(self) -> None:
        for hidden in ("PRIVATE THINKING TEXT", "SKILL BODY TEXT", "REMINDER TEXT", "SIDECHAIN TEXT",
                       "SUCCESSFUL TOOL OUTPUT", "FILE HISTORY"):
            self.assertNotIn(hidden, self.text, hidden)

    def test_counts_each_kind_of_entry(self) -> None:
        counts = self.digest.counts
        self.assertEqual(counts["user prompts"], 2)
        self.assertEqual(counts["Claude replies"], 2)
        self.assertEqual(counts["tool calls"], 2)
        self.assertEqual(counts["tool errors"], 1)
        self.assertEqual(counts["condensed summaries"], 1)
        self.assertEqual(counts["messages from other sessions or subagents"], 1)
        self.assertEqual(counts["task notifications"], 1)

    def test_reports_the_line_that_is_not_json_by_number(self) -> None:
        self.assertEqual(self.digest.malformed_line_numbers, [10])
        self.assertIn("1 line(s) of the transcript were not valid JSON and are missing here: line 10", self.text)

    def test_header_points_at_the_line_where_the_last_condensed_summary_starts(self) -> None:
        line_number = int(re.search(r"starts at line ([\d,]+)", self.text).group(1).replace(",", ""))
        self.assertEqual(self.text.splitlines()[line_number - 1], session_merge.CONDENSED_MARKER)
        self.assertIn("CONDENSED SUMMARY\nThis session is being continued", self.text)

    def test_header_points_at_the_last_of_several_condensed_summaries(self) -> None:
        entries = full_conversation()
        entries += [user_entry("Second summary: moved to PR #132.", "2026-10-21T09:00:00.000Z", isCompactSummary=True),
                    assistant_entry([{"type": "text", "text": "After the second summary."}], "2026-10-21T09:01:00.000Z")]
        text = session_merge.render_digest(session_merge.build_digest(write_transcript(self.transcript, entries)))
        line_number = int(re.search(r"starts at line ([\d,]+)", text).group(1).replace(",", ""))
        lines = text.splitlines()
        self.assertEqual(lines[line_number - 1], session_merge.CONDENSED_MARKER)
        # The marker, a blank line, the summary's heading, then its text.
        self.assertIn("CONDENSED SUMMARY", lines[line_number + 1])
        self.assertIn("Second summary: moved to PR #132.", lines[line_number + 2])

    def test_title_prefers_the_agent_name_over_the_custom_title(self) -> None:
        self.assertEqual(self.digest.title, "TICKET-12 invoice HOLD")
        self.assertTrue(self.text.startswith("# Transcript digest: TICKET-12 invoice HOLD"))

    def test_says_the_whole_conversation_is_in_memory_when_nothing_was_condensed(self) -> None:
        entries = [entry for entry in full_conversation()
                   if not (isinstance(entry, dict) and entry.get("isCompactSummary"))]
        text = session_merge.render_digest(session_merge.build_digest(write_transcript(self.transcript, entries)))
        self.assertIn("No condensed summaries: the whole conversation is still in Claude's working memory.", text)
        self.assertNotIn(session_merge.CONDENSED_MARKER, text)

    def test_empty_transcript_renders_a_header_and_says_it_is_empty(self) -> None:
        empty = write_transcript(self.projects / f"{CLOSED_SESSION_ID}.jsonl", [])
        text = session_merge.render_digest(session_merge.build_digest(empty))
        self.assertIn(f"# Transcript digest: {CLOSED_SESSION_ID}", text)
        self.assertIn("The transcript holds no prompts, replies or tool calls.", text)
        self.assertIn("From unknown time to unknown time", text)

    def test_long_tool_error_is_cut_with_a_notice_of_how_much(self) -> None:
        long_error = "E" * (session_merge.MAXIMUM_TOOL_ERROR_CHARACTERS + 250)
        entries = [user_entry([{"type": "tool_result", "is_error": True, "content": long_error}], "2026-10-20T14:05:30.000Z")]
        text = session_merge.render_digest(session_merge.build_digest(write_transcript(self.transcript, entries)))
        self.assertIn("[cut: 250 more characters]", text)
        self.assertNotIn(long_error, text)

    def test_user_prompts_are_never_cut(self) -> None:
        long_prompt = "keep this word " * 2000
        entries = [user_entry(long_prompt, "2026-10-20T14:05:30.000Z", origin={"kind": "human"})]
        text = session_merge.render_digest(session_merge.build_digest(write_transcript(self.transcript, entries)))
        self.assertIn(long_prompt.strip(), text)


class FindTranscriptTests(ClaudeFolder):
    def setUp(self) -> None:
        super().setUp()
        write_transcript(self.projects / f"{SOURCE_SESSION_ID}.jsonl", full_conversation())
        write_transcript(self.archive / f"{ARCHIVED_SESSION_ID}.jsonl", full_conversation())

    def test_finds_by_full_id_and_by_unique_prefix(self) -> None:
        expected = self.projects / f"{SOURCE_SESSION_ID}.jsonl"
        self.assertEqual(session_merge.find_transcript(SOURCE_SESSION_ID, self.claude_directory), expected)
        self.assertEqual(session_merge.find_transcript(SOURCE_SESSION_ID[:8].upper(), self.claude_directory), expected)

    def test_finds_an_archived_session(self) -> None:
        self.assertEqual(session_merge.find_transcript(ARCHIVED_SESSION_ID, self.claude_directory),
                         self.archive / f"{ARCHIVED_SESSION_ID}.jsonl")

    def test_refuses_text_that_is_not_a_session_id(self) -> None:
        with self.assertRaises(ValueError):
            session_merge.find_transcript("../../etc", self.claude_directory)
        with self.assertRaises(ValueError):
            session_merge.find_transcript("1111", self.claude_directory)

    def test_missing_session_raises(self) -> None:
        with self.assertRaises(FileNotFoundError):
            session_merge.find_transcript("99999999-0000-0000-0000-000000000009", self.claude_directory)

    def test_prefix_matching_two_sessions_raises(self) -> None:
        write_transcript(self.projects / "11111111-ffff-0000-0000-000000000004.jsonl", [])
        with self.assertRaisesRegex(ValueError, "matches 2 sessions"):
            session_merge.find_transcript("11111111", self.claude_directory)


class FindSessionsTests(ClaudeFolder):
    def setUp(self) -> None:
        super().setUp()
        self.live = write_transcript(self.projects / f"{SOURCE_SESSION_ID}.jsonl", full_conversation())
        self.closed = write_transcript(self.projects / f"{CLOSED_SESSION_ID}.jsonl", [
            {"type": "ai-title", "aiTitle": "Invoice reserves investigation"},
            user_entry("Why are reserves negative?", "2026-10-18T10:00:00.000Z", origin={"kind": "human"}, cwd="C:/work/other"),
        ])
        self.archived = write_transcript(self.archive / f"{ARCHIVED_SESSION_ID}.jsonl", [
            user_entry("Look at invoice fee breakdown", "2026-10-17T10:00:00.000Z", origin={"kind": "human"}),
        ])
        now = time.time()
        os.utime(self.archived, (now - 300, now - 300))
        os.utime(self.closed, (now - 200, now - 200))
        os.utime(self.live, (now - 100, now - 100))
        self.add_live_session(SOURCE_SESSION_ID, "TICKET-12 invoice HOLD")

    def test_matches_every_word_against_titles_names_and_ids_newest_first(self) -> None:
        unreadable: list[Path] = []
        matches = session_merge.find_sessions(["invoice"], self.claude_directory, unreadable)
        self.assertEqual([match.session_id for match in matches], [SOURCE_SESSION_ID, CLOSED_SESSION_ID, ARCHIVED_SESSION_ID])
        self.assertEqual(unreadable, [])

    def test_marks_open_closed_and_archived_sessions(self) -> None:
        matches = {match.session_id: match for match in session_merge.find_sessions(["invoice"], self.claude_directory, [])}
        self.assertTrue(matches[SOURCE_SESSION_ID].is_live)
        self.assertEqual(matches[SOURCE_SESSION_ID].live_name, "TICKET-12 invoice HOLD")
        self.assertFalse(matches[CLOSED_SESSION_ID].is_live)
        self.assertEqual(matches[CLOSED_SESSION_ID].title, "Invoice reserves investigation")
        self.assertEqual(matches[CLOSED_SESSION_ID].working_directory, "C:/work/other")
        self.assertTrue(matches[ARCHIVED_SESSION_ID].is_archived)
        self.assertEqual(matches[ARCHIVED_SESSION_ID].title, "Look at invoice fee breakdown")

    def test_all_words_must_match(self) -> None:
        matches = session_merge.find_sessions(["invoice", "reserves"], self.claude_directory, [])
        self.assertEqual([match.session_id for match in matches], [CLOSED_SESSION_ID])

    def test_no_match_gives_an_empty_list(self) -> None:
        self.assertEqual(session_merge.find_sessions(["inventory"], self.claude_directory, []), [])

    def test_no_words_raises(self) -> None:
        with self.assertRaises(ValueError):
            session_merge.find_sessions([" "], self.claude_directory, [])

    def test_unreadable_live_record_is_reported_not_skipped_silently(self) -> None:
        broken = self.sessions / "999.json"
        broken.write_text("{half a record", encoding="utf-8")
        unreadable: list[Path] = []
        matches = session_merge.find_sessions(["invoice"], self.claude_directory, unreadable)
        self.assertEqual(unreadable, [broken])
        self.assertIn("1 open-session record(s) could not be read", session_merge.render_matches(["invoice"], matches, unreadable))

    def test_render_gives_send_target_for_open_and_resume_command_for_closed(self) -> None:
        matches = session_merge.find_sessions(["invoice"], self.claude_directory, [])
        text = session_merge.render_matches(["invoice"], matches, [])
        self.assertIn('open now as "TICKET-12 invoice HOLD", reachable with SendMessage', text)
        self.assertIn(f"closed, reopen with: claude --resume {CLOSED_SESSION_ID}", text)
        self.assertIn(f"closed and archived (run /restore first), then: claude --resume {ARCHIVED_SESSION_ID}", text)


class HandoffPathTests(ClaudeFolder):
    def test_slug_keeps_letters_and_digits_joined_by_underscores(self) -> None:
        self.assertEqual(session_merge.build_slug("TICKET-12 P&L, Acme Widgets"), "ticket_12_p_l_acme_widgets")
        self.assertEqual(session_merge.build_slug("tool: Conversation merge skill design"), "tool_conversation_merge_skill_design")
        self.assertEqual(session_merge.build_slug("TICKET-34 partial loading analysis ⑂"), "ticket_34_partial_loading_analysis")

    def test_slug_is_cut_without_a_trailing_underscore(self) -> None:
        slug = session_merge.build_slug("word " * 40)
        self.assertLessEqual(len(slug), session_merge.MAXIMUM_SLUG_CHARACTERS)
        self.assertFalse(slug.endswith("_"))

    def test_name_without_letters_or_digits_raises(self) -> None:
        with self.assertRaises(ValueError):
            session_merge.build_slug("⑂ — !!")

    def test_path_has_no_spaces_and_takes_the_next_free_name(self) -> None:
        handoff_directory = self.claude_directory / "handoffs"
        first = session_merge.build_handoff_path("TICKET-12 invoice HOLD", "TICKET-12 P&L fees", date(2026, 10, 22), handoff_directory)
        self.assertEqual(first.name, "2026-10-22_ticket_12_invoice_hold_to_ticket_12_p_l_fees.md")
        self.assertTrue(handoff_directory.is_dir())
        first.write_text("taken", encoding="utf-8")
        second = session_merge.build_handoff_path("TICKET-12 invoice HOLD", "TICKET-12 P&L fees", date(2026, 10, 22), handoff_directory)
        self.assertEqual(second.name, "2026-10-22_ticket_12_invoice_hold_to_ticket_12_p_l_fees_2.md")
        second.write_text("taken", encoding="utf-8")
        third = session_merge.build_handoff_path("TICKET-12 invoice HOLD", "TICKET-12 P&L fees", date(2026, 10, 22), handoff_directory)
        self.assertTrue(third.name.endswith("_3.md"))


class SensitiveTextTests(unittest.TestCase):
    def test_flags_each_kind_of_secret_and_hostname(self) -> None:
        samples = {
            "AWS access key id": f"key {FAKE_AWS_KEY} here",
            "private key": FAKE_PRIVATE_KEY,
            "GitHub token": f"token {FAKE_GITHUB_TOKEN}",
            "Slack token": FAKE_SLACK_TOKEN,
            "API key": FAKE_API_KEY,
            "JSON web token": FAKE_JWT,
            "credentials in a URL": "postgres://reader:hunter22@db.example.com/app",
            "secret value": "password=Winter2026!",
            "database hostname": "connect to mydb.abc123xyz.us-east-1.rds.amazonaws.com:1433",
        }
        for kind, sample in samples.items():
            kinds = {finding.kind for finding in session_merge.find_sensitive_text(sample)}
            self.assertIn(kind, kinds, f"{kind} not flagged in {sample!r}")

    def test_flags_azure_sql_and_redshift_hostnames(self) -> None:
        text = "a: myserver.database.windows.net\nb: cluster1.abc.us-east-1.redshift.amazonaws.com"
        findings = session_merge.find_sensitive_text(text)
        self.assertEqual([(finding.line_number, finding.kind) for finding in findings],
                         [(1, "database hostname"), (2, "database hostname")])

    def test_masks_what_it_found(self) -> None:
        finding = session_merge.find_sensitive_text(f"key {FAKE_AWS_KEY}")[0]
        self.assertEqual(finding.masked_excerpt, "AKIA… (20 characters)")
        self.assertNotIn(FAKE_AWS_KEY, finding.masked_excerpt)

    def test_leaves_ordinary_prose_alone(self) -> None:
        prose = "\n".join([
            "The token budget is 12000 tokens per run.",
            "password: required for the read-only login",
            "Read the host from the read_only_host field of the app-prod secret.",
            "See https://github.com/org/repo/pull/145 (partial-load views).",
            "secret: the name of the Secrets Manager entry",
        ])
        self.assertEqual(session_merge.find_sensitive_text(prose), [])


class CommandLineTests(ClaudeFolder):
    def setUp(self) -> None:
        super().setUp()
        write_transcript(self.projects / f"{SOURCE_SESSION_ID}.jsonl", full_conversation())

    def test_digest_reads_the_session_id_claude_code_sets(self) -> None:
        result = self.run_script("digest", session_id=SOURCE_SESSION_ID)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("# Transcript digest: TICKET-12 invoice HOLD", result.stdout)

    def test_digest_writes_the_output_file_and_prints_a_summary(self) -> None:
        output = self.claude_directory / "scratch" / "digest.md"
        result = self.run_script("digest", "--session-id", SOURCE_SESSION_ID[:8], "--output", str(output))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("2 user prompts, 1 condensed summaries, 1 unreadable lines.", result.stdout)
        self.assertIn("Keep first-day lines", output.read_text(encoding="utf-8"))

    def test_digest_without_any_session_id_fails_loudly(self) -> None:
        result = self.run_script("digest")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no session id", result.stderr)

    def test_digest_of_a_missing_session_fails_loudly(self) -> None:
        result = self.run_script("digest", "--session-id", "99999999-0000-0000-0000-000000000009")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("FileNotFoundError", result.stderr)

    def test_find_exits_one_when_nothing_matches(self) -> None:
        result = self.run_script("find", "inventory")
        self.assertEqual(result.returncode, 1)
        self.assertIn('No session matches "inventory".', result.stdout)

    def test_path_prints_a_path_under_handoffs(self) -> None:
        result = self.run_script("path", "--source", "TICKET-12 invoice HOLD", "--target", "P&L fees", "--date", "2026-10-22")
        self.assertEqual(result.returncode, 0, result.stderr)
        printed = Path(result.stdout.strip())
        self.assertEqual(printed.parent, self.claude_directory / "handoffs")
        self.assertEqual(printed.name, "2026-10-22_ticket_12_invoice_hold_to_p_l_fees.md")

    def test_path_with_a_bad_date_fails(self) -> None:
        result = self.run_script("path", "--source", "a", "--target", "b", "--date", "22/10/2026")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--date must be YYYY-MM-DD", result.stderr)

    def test_check_exits_zero_when_clean_and_one_when_not(self) -> None:
        clean = self.claude_directory / "clean.md"
        clean.write_text("# Handoff\nDecision: keep first-day lines.\n", encoding="utf-8")
        dirty = self.claude_directory / "dirty.md"
        dirty.write_text(f"# Handoff\nUse key {FAKE_AWS_KEY}\n", encoding="utf-8")
        clean_result = self.run_script("check", str(clean))
        dirty_result = self.run_script("check", str(dirty))
        self.assertEqual(clean_result.returncode, 0, clean_result.stdout)
        self.assertIn("clean:", clean_result.stdout)
        self.assertEqual(dirty_result.returncode, 1)
        self.assertIn("line 2: AWS access key id: AKIA… (20 characters)", dirty_result.stdout)
        self.assertNotIn(FAKE_AWS_KEY, dirty_result.stdout)

    def test_no_command_is_a_usage_error(self) -> None:
        result = self.run_script()
        self.assertEqual(result.returncode, 2)


if __name__ == "__main__":
    unittest.main()
