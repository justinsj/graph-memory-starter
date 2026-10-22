"""runguard: the budgeted run, the ledger, the PreToolUse hook as Claude Code runs it, and safe_db.

The hook and the wrapper run as fresh processes with JSON on stdin, as Claude
Code runs them. Each test points RUNGUARD_LEDGER and RUNGUARD_CONFIG at its own
temporary folder, so nothing touches runguard/ledger.jsonl.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNGUARD = ROOT / "runguard"
sys.path.insert(0, str(RUNGUARD))

import runguard_common as common  # noqa: E402
import ledger  # noqa: E402
import preflight_gate  # noqa: E402
import safe_db  # noqa: E402

GRANDCHILD = """
import subprocess, sys, time
grandchild = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
open(sys.argv[1], "w").write(str(grandchild.pid))
time.sleep(60)
"""


def alive(pid: int) -> bool:
    """True while a process with this pid exists."""
    if os.name == "nt":
        listed = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True)
        return str(pid) in listed.stdout
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


class Folder(unittest.TestCase):
    """A temporary folder with its own ledger and config, passed to every child process."""

    mode = "warn"

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.ledger = self.dir / "ledger.jsonl"
        self.config = self.dir / "config.json"
        self.config.write_text(json.dumps({"mode": self.mode, "max_budget_seconds": 60}), encoding="utf-8")
        self.env = {**{k: v for k, v in os.environ.items() if k not in ("PYTHONIOENCODING", "PYTHONUTF8")},
                    "RUNGUARD_LEDGER": str(self.ledger), "RUNGUARD_CONFIG": str(self.config)}
        self.saved = {key: os.environ.get(key) for key in ("RUNGUARD_LEDGER", "RUNGUARD_CONFIG")}
        os.environ["RUNGUARD_LEDGER"] = str(self.ledger)

    def tearDown(self) -> None:
        for key, value in self.saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp.cleanup()

    def bounded(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(RUNGUARD / "run_bounded.py"), *args], cwd=self.dir,
                              env=self.env, capture_output=True, text=True, timeout=60)

    def hook(self, command: str, tool: str = "Bash") -> dict | None:
        payload = {"tool_name": tool, "tool_input": {"command": command}, "cwd": str(self.dir)}
        out = subprocess.run([sys.executable, str(RUNGUARD / "preflight_gate.py")], cwd=self.dir, env=self.env,
                             input=json.dumps(payload).encode("utf-8"), capture_output=True, timeout=30)
        if out.returncode != 0:
            raise AssertionError(out.stderr.decode("utf-8", "replace"))
        text = out.stdout.decode("utf-8")
        return json.loads(text) if text else None

    def script(self, name: str, body: str) -> Path:
        path = self.dir / name
        path.write_text(body, encoding="utf-8")
        return path

    def entries(self) -> list[dict]:
        return common.read_ledger(self.ledger)


class Budgets(unittest.TestCase):

    def test_units(self) -> None:
        self.assertEqual(common.parse_budget("90"), 90)
        self.assertEqual(common.parse_budget("90s"), 90)
        self.assertEqual(common.parse_budget("10m"), 600)
        self.assertEqual(common.parse_budget(" 1H "), 3600)

    def test_bad_budgets_raise(self) -> None:
        for text in ("", "0", "0m", "ten minutes", "-5", "1.5m", "5d"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                common.parse_budget(text)

    def test_broken_config_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text("{not json", encoding="utf-8")
            with self.assertRaises(json.JSONDecodeError):
                common.load_config(path)
            path.write_text(json.dumps({"mode": "loud"}), encoding="utf-8")
            with self.assertRaises(ValueError):
                common.load_config(path)

    def test_broken_ledger_line_raises_with_its_number(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ledger.jsonl"
            path.write_text('{"outcome": "ok"}\nnot json\n', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, r"ledger.jsonl:2"):
                common.read_ledger(path)


class RunBounded(Folder):

    def test_quick_run_is_logged(self) -> None:
        script = self.script("quick.py", "print('hello')")
        out = self.bounded("--budget", "30s", "--label", "quick", "--", sys.executable, str(script))
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("hello", out.stdout)
        self.assertIn("runguard: quick took", out.stderr)
        [entry] = self.entries()
        self.assertEqual(entry["outcome"], "ok")
        self.assertEqual(entry["script"], str(script.resolve()))
        self.assertEqual(entry["script_hash"], common.file_hash(script))
        self.assertEqual(entry["budget_seconds"], 30)

    def test_exit_code_passes_through(self) -> None:
        script = self.script("fails.py", "import sys; sys.exit(3)")
        out = self.bounded("--budget", "30s", "--", sys.executable, str(script))
        self.assertEqual(out.returncode, 3)
        self.assertEqual(self.entries()[0]["outcome"], "failed")

    def test_one_word_runs_through_the_shell(self) -> None:
        out = self.bounded("--budget", "30s", "--", f'"{sys.executable}" -c "print(41 + 1)"')
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("42", out.stdout)

    def test_overrun_kills_the_whole_tree(self) -> None:
        script = self.script("slow.py", GRANDCHILD)
        pid_file = self.dir / "grandchild.pid"
        started = time.monotonic()
        out = self.bounded("--budget", "3s", "--label", "slow", "--", sys.executable, str(script), str(pid_file))
        self.assertLess(time.monotonic() - started, 30)
        self.assertEqual(out.returncode, 124)
        self.assertIn("BUDGET EXCEEDED", out.stderr)
        grandchild = int(pid_file.read_text())
        for _ in range(20):
            if not alive(grandchild):
                break
            time.sleep(0.25)
        self.assertFalse(alive(grandchild), "the grandchild outlived the budget")
        self.assertEqual(self.entries()[0]["outcome"], "budget_exceeded")

    def test_slow_run_is_called_out(self) -> None:
        script = self.script("nearly.py", "import time; time.sleep(2.5)")
        out = self.bounded("--budget", "3s", "--", sys.executable, str(script))
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("SLOW", out.stderr)

    def test_long_budget_needs_approval(self) -> None:
        script = self.script("quick.py", "print('hello')")
        refused = self.bounded("--budget", "2m", "--", sys.executable, str(script))
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("--approved", refused.stderr)
        self.assertEqual(self.entries(), [])
        approved = self.bounded("--budget", "2m", "--approved", "--", sys.executable, str(script))
        self.assertEqual(approved.returncode, 0, approved.stderr)

    def test_no_command_is_an_error(self) -> None:
        out = self.bounded("--budget", "30s", "--")
        self.assertNotEqual(out.returncode, 0)
        self.assertIn("no command", out.stderr)


class Gate(Folder):

    def test_light_commands_pass_silently(self) -> None:
        for command in ("git status", "ls -la", "python --version", "python -m pip install fastembed",
                        "python -c \"print(1)\"", "dir"):
            with self.subTest(command=command):
                self.assertIsNone(self.hook(command))

    def test_other_tools_are_ignored(self) -> None:
        self.assertIsNone(self.hook("pytest", tool="Read"))

    def test_exempt_commands_pass_when_nothing_is_chained(self) -> None:
        self.script("pull.py", "print(1)")
        for command in ("python pull.py --help", "pytest --version", "python pull.py --help 2>&1",
                        "python pull.py --version > out.txt", "python pull.py --help &> out.txt",
                        'python pull.py --help --name "P&L; a|b"'):
            with self.subTest(command=command):
                self.assertIsNone(self.hook(command))

    def test_exempt_flag_does_not_cover_a_chained_command(self) -> None:
        self.script("pull.py", "print(1)")
        for command in ("python pull.py --help && python pull.py", "python pull.py; pytest --version",
                        "python pull.py & python pull.py --help", "python pull.py --help | python pull.py",
                        "python -m venv .venv && python pull.py", 'pytest --version "$(python pull.py)"',
                        "pytest --version `python pull.py`", "pytest --version\npython pull.py"):
            with self.subTest(command=command):
                reply = self.hook(command)
                self.assertIsNotNone(reply)
                self.assertIn("without a time budget", reply["hookSpecificOutput"]["additionalContext"])

    def test_unwrapped_heavy_commands_are_flagged(self) -> None:
        self.script("pull.py", "print(1)")
        for command in ("pytest -x tests", "python pull.py", "python3 -u pull.py --since 2026-01-01",
                        "python -m unittest discover tests", "sqlcmd -S host -Q \"select 1\"",
                        "aws redshift-data execute-statement --sql \"select 1\"",
                        "jupyter nbconvert --execute report.ipynb", "py pull.py"):
            with self.subTest(command=command):
                reply = self.hook(command)
                self.assertIsNotNone(reply)
                self.assertIn("without a time budget", reply["hookSpecificOutput"]["additionalContext"])

    def test_warn_mode_allows_and_tells_the_model(self) -> None:
        reply = self.hook("pytest -x tests")
        self.assertNotIn("permissionDecision", reply["hookSpecificOutput"])
        self.assertEqual(reply["hookSpecificOutput"]["hookEventName"], "PreToolUse")
        self.assertTrue(reply["systemMessage"].startswith("runguard: "))

    def test_wrapped_clean_script_passes(self) -> None:
        self.script("pull.py", "import pandas\nprint(1)\n")
        self.assertIsNone(self.hook("python run_bounded.py --budget 10m -- python pull.py"))

    def test_powershell_is_guarded_too(self) -> None:
        self.assertIsNotNone(self.hook("python .\\missing.py", tool="PowerShell"))

    def test_overran_unchanged_script_is_refused_until_changed(self) -> None:
        script = self.script("slow.py", "import time; time.sleep(60)")
        out = self.bounded("--budget", "2s", "--", sys.executable, str(script))
        self.assertEqual(out.returncode, 124)
        command = f"python run_bounded.py --budget 10m -- python {script.name}"
        reply = self.hook(command)
        self.assertIn("overran its 2s budget", reply["hookSpecificOutput"]["additionalContext"])
        script.write_text("import time; time.sleep(0.1)", encoding="utf-8")
        self.assertIsNone(self.hook(command))

    def test_clear_lets_an_unchanged_script_run_once_more(self) -> None:
        script = self.script("slow.py", "import time; time.sleep(60)")
        self.bounded("--budget", "2s", "--", sys.executable, str(script))
        command = f"python run_bounded.py --budget 10m -- \"python {script.name}\""
        self.assertIsNotNone(self.hook(command))
        cleared = subprocess.run([sys.executable, str(RUNGUARD / "ledger.py"), "clear", str(script),
                                  "--reason", "user approved"], cwd=self.dir, env=self.env,
                                 capture_output=True, text=True, timeout=30)
        self.assertEqual(cleared.returncode, 0, cleared.stderr)
        self.assertIsNone(self.hook(command))
        self.assertEqual(self.entries()[-1]["reason"], "user approved")

    def test_raw_driver_is_flagged_and_safe_db_is_not(self) -> None:
        self.script("raw.py", "import os\nimport pyodbc\n")
        self.script("viasafe.py", "import pyodbc\nimport safe_db\n")
        self.script("sub.py", "from mysql.connector import connect\n")
        reply = self.hook("python run_bounded.py --budget 5m -- python raw.py")
        self.assertIn("imports pyodbc but not safe_db", reply["hookSpecificOutput"]["additionalContext"])
        self.assertIsNone(self.hook("python run_bounded.py --budget 5m -- python viasafe.py"))
        reply = self.hook("python run_bounded.py --budget 5m -- python sub.py")
        self.assertIn("mysql.connector", reply["hookSpecificOutput"]["additionalContext"])

    def test_broken_config_fails_the_hook_loudly(self) -> None:
        self.config.write_text("{broken", encoding="utf-8")
        with self.assertRaises(AssertionError):
            self.hook("pytest")


class GateBlocking(Folder):

    mode = "block"

    def test_block_mode_denies_with_the_reason(self) -> None:
        reply = self.hook("pytest -x tests")
        decision = reply["hookSpecificOutput"]
        self.assertEqual(decision["permissionDecision"], "deny")
        self.assertIn("without a time budget", decision["permissionDecisionReason"])

    def test_block_mode_still_passes_clean_calls(self) -> None:
        self.assertIsNone(self.hook("git status"))
        self.script("ok.py", "print(1)")
        self.assertIsNone(self.hook("python run_bounded.py --budget 1m -- python ok.py"))


class ShippedConfig(unittest.TestCase):

    def setUp(self) -> None:
        self.shipped = json.loads((RUNGUARD / "config.json").read_text(encoding="utf-8"))

    def test_shipped_config_repeats_the_default_exemptions(self) -> None:
        """A list in config.json replaces the default list, so it must start with the defaults, unchanged."""
        defaults = common.DEFAULTS["exempt_patterns"]
        self.assertEqual(self.shipped["exempt_patterns"][:len(defaults)], defaults)

    def test_session_merge_is_exempt_only_when_it_runs_alone(self) -> None:
        pattern = common.build_exempt_pattern(r"session_merge\.py")
        self.assertIn(pattern, self.shipped["exempt_patterns"])
        script = '"C:/Users/someone/.claude/skills/merge-session/session_merge.py"'
        self.assertTrue(re.search(pattern, f'python {script} path --source "TICKET-12 P&L" --target "fees"'))
        self.assertTrue(re.search(pattern, f"python {script} digest --output C:/tmp/digest.md 2>&1"))
        self.assertFalse(re.search(pattern, f"python {script} find x && python backtest.py"))
        self.assertFalse(re.search(pattern, f"python backtest.py; python {script} find x"))


class LedgerReport(unittest.TestCase):

    def test_only_overruns_and_slow_runs_worst_first(self) -> None:
        entries = [
            {"at": "t1", "outcome": "ok", "seconds": 10.0, "budget_seconds": 100, "label": "fast"},
            {"at": "t2", "outcome": "ok", "seconds": 85.0, "budget_seconds": 100, "label": "slow"},
            {"at": "t3", "outcome": "budget_exceeded", "seconds": 100.4, "budget_seconds": 100, "label": "over"},
        ]
        flagged = ledger.runs_to_revisit(entries, 0.8)
        self.assertEqual([entry["label"] for entry in flagged], ["over", "slow"])
        self.assertIn("budget_exceeded", ledger.format_row(flagged[0]))


class Fake:
    """A DB-API connection and cursor that records statements and returns set rows."""

    def __init__(self, rows: list[tuple] | None = None, pages: list[list[tuple]] | None = None) -> None:
        self.executed: list[tuple[str, object]] = []
        self.rows = rows or []
        self.pages = pages
        self.closed_cursors = 0
        self.autocommit = None
        self.timeout = None

    def cursor(self) -> "Fake":
        return self

    def execute(self, sql: str, parameters: object = ()) -> None:
        self.executed.append((sql, parameters))

    def fetchall(self) -> list[tuple]:
        return self.pages.pop(0) if self.pages is not None else self.rows

    def fetchone(self) -> tuple:
        return self.rows[0]

    def close(self) -> None:
        self.closed_cursors += 1


class SafeDbStatements(unittest.TestCase):

    def test_each_engine_gets_its_guards(self) -> None:
        self.assertEqual(safe_db.guard_statements("sqlserver", 600, 5),
                         ["SET LOCK_TIMEOUT 5000", "SET DEADLOCK_PRIORITY LOW"])
        mysql = safe_db.guard_statements("mysql", 600, 5)
        self.assertIn("SET SESSION TRANSACTION READ ONLY", mysql)
        self.assertIn("SET SESSION MAX_EXECUTION_TIME = 600000", mysql)
        self.assertIn("SET SESSION lock_wait_timeout = 5", mysql)
        postgres = safe_db.guard_statements("postgres", 60, 2)
        self.assertIn("SET statement_timeout = 60000", postgres)
        self.assertIn("SET lock_timeout = 2000", postgres)
        self.assertEqual(safe_db.guard_statements("redshift", 60, 2), ["SET statement_timeout TO 60000"])
        with self.assertRaises(ValueError):
            safe_db.guard_statements("oracle", 60, 2)

    def test_reads_pass(self) -> None:
        for sql in ("SELECT id FROM orders", "  select * from t where note = 'please update me';",
                    "WITH recent AS (SELECT id FROM t) SELECT id FROM recent",
                    "-- the daily pull\nSELECT REPLACE(name, 'a', 'b') FROM t", "EXPLAIN SELECT 1",
                    "SELECT updated_at, data_set FROM t"):
            with self.subTest(sql=sql):
                self.assertEqual(safe_db.require_read(sql), sql)

    def test_writes_and_locks_are_refused(self) -> None:
        for sql in ("", "UPDATE t SET a = 1", "DELETE FROM t", "SELECT 1; DROP TABLE t",
                    "SELECT * INTO backup FROM t", "SELECT * FROM t FOR UPDATE", "SELECT * FROM t FOR SHARE",
                    "WITH gone AS (DELETE FROM t RETURNING *) SELECT * FROM gone", "EXEC dbo.purge",
                    "TRUNCATE t", "SET LOCK_TIMEOUT -1", "REPLACE INTO t VALUES (1)",
                    "/* SELECT */ INSERT INTO t VALUES (1)", "REFRESH MATERIALIZED VIEW mv"):
            with self.subTest(sql=sql), self.assertRaises(safe_db.UnsafeQueryError):
                safe_db.require_read(sql)

    def test_markers(self) -> None:
        safe_db.require_marker("db-prod-READONLY02.example.com", "readonly", "host")
        safe_db.require_marker("anything", None, "host")
        with self.assertRaises(safe_db.UnsafeConnectionError):
            safe_db.require_marker("db-prod-primary.example.com", "readonly", "host")
        with self.assertRaises(safe_db.UnsafeConnectionError):
            safe_db.require_marker("", "read-only", "login")


class SafeDbConnections(unittest.TestCase):

    DRIVERS = ("pyodbc", "pymysql", "psycopg2")

    def setUp(self) -> None:
        self.saved = {name: sys.modules[name] for name in self.DRIVERS if name in sys.modules}

    def tearDown(self) -> None:
        for name in self.DRIVERS:
            sys.modules.pop(name, None)
        sys.modules.update(self.saved)

    def fake_driver(self, name: str, connection: Fake) -> list[tuple]:
        calls: list[tuple] = []

        def connect(*args: object, **kwargs: object) -> Fake:
            calls.append((args, kwargs))
            return connection

        sys.modules[name] = type(sys)(name)
        sys.modules[name].connect = connect
        return calls

    def test_sqlserver_refuses_a_primary_before_loading_the_driver(self) -> None:
        sys.modules["pyodbc"] = None  # importing it would raise
        with self.assertRaises(safe_db.UnsafeConnectionError):
            safe_db.connect_sqlserver("db-primary.example.com", "Sales", "u", "p")

    def test_sqlserver_sets_intent_timeout_and_guards(self) -> None:
        connection = Fake()
        calls = self.fake_driver("pyodbc", connection)
        result = safe_db.connect_sqlserver(" db-readonly02.example.com", "Sales", "u", "p",
                                           statement_timeout_seconds=120)
        self.assertIs(result, connection)
        (args, kwargs), = calls
        self.assertIn("ApplicationIntent=ReadOnly", args[0])
        self.assertIn("SERVER=db-readonly02.example.com,1433", args[0])
        self.assertTrue(kwargs["autocommit"])
        self.assertEqual(connection.timeout, 120)
        self.assertEqual([sql for sql, _ in connection.executed],
                         ["SET LOCK_TIMEOUT 5000", "SET DEADLOCK_PRIORITY LOW"])

    def test_mysql_checks_the_login_before_guarding(self) -> None:
        writer = Fake(rows=[("app-writer@%",)])
        self.fake_driver("pymysql", writer)
        with self.assertRaises(safe_db.UnsafeConnectionError):
            safe_db.connect_mysql("cluster.example.com", "li", "app-writer", "p")
        self.assertEqual([sql for sql, _ in writer.executed], ["SELECT CURRENT_USER()"])
        reader = Fake(rows=[("li-risk-read-only-prod@%",)])
        calls = self.fake_driver("pymysql", reader)
        safe_db.connect_mysql("cluster.example.com", "li", "li-risk-read-only-prod", "p")
        self.assertTrue(calls[0][1]["autocommit"])
        self.assertIn("SET SESSION TRANSACTION READ ONLY", [sql for sql, _ in reader.executed])

    def test_postgres_and_redshift(self) -> None:
        connection = Fake()
        self.fake_driver("psycopg2", connection)
        safe_db.connect_postgres("warehouse.example.com", "dev", "u", "p", engine="redshift", port=5439)
        self.assertTrue(connection.autocommit)
        self.assertEqual(connection.executed[-1][0], "SET statement_timeout TO 600000")
        with self.assertRaises(ValueError):
            safe_db.connect_postgres("h", "d", "u", "p", engine="mysql")

    def test_missing_driver_names_the_package(self) -> None:
        sys.modules["psycopg2"] = None
        with self.assertRaisesRegex(ImportError, "pip install psycopg2"):
            safe_db.connect_postgres("h", "d", "u", "p")


class SafeDbReads(unittest.TestCase):

    def test_read_query_refuses_before_running(self) -> None:
        connection = Fake(rows=[(1,)])
        self.assertEqual(safe_db.read_query(connection, "SELECT 1"), [(1,)])
        with self.assertRaises(safe_db.UnsafeQueryError):
            safe_db.read_query(connection, "DELETE FROM t")
        self.assertEqual(len(connection.executed), 1)
        self.assertEqual(connection.closed_cursors, 2)

    def test_chunks_use_keyset_pagination(self) -> None:
        connection = Fake(pages=[[(1, "a"), (2, "b")], [(3, "c"), (4, "d")], [(5, "e")]])
        chunks = list(safe_db.read_in_chunks(connection, "SELECT id, name FROM t", "id", 2))
        self.assertEqual([len(chunk) for chunk in chunks], [2, 2, 1])
        sqls = [(sql, parameters) for sql, parameters in connection.executed]
        self.assertNotIn("WHERE", sqls[0][0])
        self.assertIn("WHERE id > %s ORDER BY id LIMIT 2", sqls[1][0])
        self.assertEqual(sqls[1][1], [2])
        self.assertEqual(sqls[2][1], [4])

    def test_chunks_refuse_an_odd_key_column(self) -> None:
        with self.assertRaises(safe_db.UnsafeQueryError):
            list(safe_db.read_in_chunks(Fake(), "SELECT id FROM t", "id; drop table t", 10))


class FakeDataApi:
    """A redshift-data client whose statement finishes after a set number of polls, or never."""

    def __init__(self, finish_after: int | None, status: str = "FINISHED") -> None:
        self.finish_after = finish_after
        self.status = status
        self.polls = 0
        self.cancelled: list[str] = []
        self.sql = ""

    def execute_statement(self, Sql: str, **location: str) -> dict:
        self.sql = Sql
        self.location = location
        return {"Id": "stmt-1"}

    def describe_statement(self, Id: str) -> dict:
        self.polls += 1
        if self.finish_after is not None and self.polls > self.finish_after:
            return {"Id": Id, "Status": self.status, "Error": "boom"}
        return {"Id": Id, "Status": "STARTED"}

    def cancel_statement(self, Id: str) -> dict:
        self.cancelled.append(Id)
        return {"Status": True}


class RedshiftDataApi(unittest.TestCase):

    def test_finishes(self) -> None:
        client = FakeDataApi(finish_after=2)
        result = safe_db.redshift_data_query(client, "SELECT 1", deadline_seconds=10, poll_seconds=0.01,
                                             WorkgroupName="wg", Database="dev")
        self.assertEqual(result["Status"], "FINISHED")
        self.assertEqual(client.location, {"WorkgroupName": "wg", "Database": "dev"})
        self.assertEqual(client.cancelled, [])

    def test_deadline_cancels(self) -> None:
        client = FakeDataApi(finish_after=None)
        with self.assertRaises(safe_db.QueryDeadlineError):
            safe_db.redshift_data_query(client, "SELECT 1", deadline_seconds=0, poll_seconds=0.01)
        self.assertEqual(client.cancelled, ["stmt-1"])

    def test_failure_raises_with_the_error(self) -> None:
        client = FakeDataApi(finish_after=0, status="FAILED")
        with self.assertRaisesRegex(RuntimeError, "boom"):
            safe_db.redshift_data_query(client, "SELECT 1", deadline_seconds=10, poll_seconds=0.01)

    def test_write_never_reaches_the_api(self) -> None:
        client = FakeDataApi(finish_after=0)
        with self.assertRaises(safe_db.UnsafeQueryError):
            safe_db.redshift_data_query(client, "TRUNCATE sales", deadline_seconds=10)
        self.assertEqual(client.sql, "")


if __name__ == "__main__":
    unittest.main()
