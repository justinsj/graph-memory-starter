"""Read-only database connections that cannot hold locks for long or queue other work behind them.

    import safe_db
    connection = safe_db.connect_sqlserver(host, "SalesDB", user, password, host_marker="readonly")
    rows = safe_db.read_query(connection, "SELECT id, total FROM orders WHERE placed_on >= ?", ["2026-09-01"])

A long read does its harm by what waits behind it, and each engine differs:

    SQL Server   a long read on a readable secondary holds a schema lock that stalls
                 redo of DDL, and grows the version store and the replica lag
    MySQL        a SELECT takes no row locks, but holds a metadata lock: an ALTER waits
                 on it, and every later query on the table queues behind the ALTER
    Postgres /   a SELECT holds an AccessShareLock, which blocks materialized view
    Redshift     refreshes, TRUNCATE, VACUUM and DDL until it finishes

So every connection here is autocommit (no transaction left open), has a statement
timeout and a lock timeout, is read-only where the engine allows it, and runs only
statements that read. A host or login that does not look read-only is refused
before the first query. The driver is loaded by name when a connect_* function is
called, so this module imports without any driver installed.
"""

import importlib
import re
import time
from typing import Any, Iterable, Sequence

ENGINES = ("sqlserver", "mysql", "postgres", "redshift")
READ_KEYWORDS = ("select", "with", "show", "explain", "describe", "desc")
WRITE_WORDS = re.compile(
    r"\b(insert|update|delete|merge|upsert|drop|alter|create|truncate|grant|revoke|exec|execute|"
    r"call|rename|vacuum|analyze|refresh|copy|unload|lock|set)\b", re.IGNORECASE)
COMMENTS = re.compile(r"--[^\n]*|/\*.*?\*/", re.DOTALL)
STRINGS = re.compile(r"'(?:[^']|'')*'")


class UnsafeQueryError(ValueError):
    """A statement that would write, lock or change a session was refused before it ran."""


class UnsafeConnectionError(RuntimeError):
    """The host or login does not look read-only, so no query was run."""


class QueryDeadlineError(TimeoutError):
    """A statement ran past its deadline and was cancelled."""


def guard_statements(engine: str, statement_timeout_seconds: int, lock_timeout_seconds: int) -> list[str]:
    """The SET statements run on a new connection, for one engine. Raises on an engine not in ENGINES."""
    statement_ms = statement_timeout_seconds * 1000
    lock_ms = lock_timeout_seconds * 1000
    if engine == "sqlserver":
        return [f"SET LOCK_TIMEOUT {lock_ms}", "SET DEADLOCK_PRIORITY LOW"]
    if engine == "mysql":
        return ["SET SESSION TRANSACTION READ ONLY",
                f"SET SESSION MAX_EXECUTION_TIME = {statement_ms}",
                f"SET SESSION lock_wait_timeout = {lock_timeout_seconds}",
                f"SET SESSION innodb_lock_wait_timeout = {lock_timeout_seconds}"]
    if engine == "postgres":
        return ["SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY",
                f"SET statement_timeout = {statement_ms}",
                f"SET lock_timeout = {lock_ms}",
                f"SET idle_in_transaction_session_timeout = {statement_ms}"]
    if engine == "redshift":
        return [f"SET statement_timeout TO {statement_ms}"]
    raise ValueError(f"engine must be one of {', '.join(ENGINES)}, found {engine!r}")


def require_read(sql: str) -> str:
    """The statement unchanged if it only reads. Raises UnsafeQueryError on a write, a lock or a second statement."""
    bare = STRINGS.sub("''", COMMENTS.sub(" ", sql)).strip().rstrip(";").strip()
    if not bare:
        raise UnsafeQueryError("empty statement")
    if ";" in bare:
        raise UnsafeQueryError("more than one statement; run them one at a time")
    first = bare.split(None, 1)[0].lower()
    if first not in READ_KEYWORDS:
        raise UnsafeQueryError(f"statement starts with {first.upper()}; only reads are allowed")
    found = WRITE_WORDS.search(bare)
    if found:
        raise UnsafeQueryError(f"statement contains {found.group(0).upper()}; only reads are allowed")
    if re.search(r"\binto\b", bare, re.IGNORECASE):
        raise UnsafeQueryError("SELECT ... INTO writes a table; only reads are allowed")
    if re.search(r"\bfor\s+(update|share|no\s+key\s+update|key\s+share)\b", bare, re.IGNORECASE):
        raise UnsafeQueryError("FOR UPDATE / FOR SHARE takes row locks; only plain reads are allowed")
    return sql


def require_marker(value: str, marker: str | None, what: str) -> None:
    """Raise UnsafeConnectionError unless value contains marker (case-insensitive). marker None skips the check."""
    if marker is None:
        return
    if marker.lower() not in (value or "").lower():
        raise UnsafeConnectionError(f"the {what} does not contain {marker!r}; refusing to connect. "
                                    "Point at the read-only replica or login.")


def apply_guards(connection: Any, engine: str, statement_timeout_seconds: int,
                 lock_timeout_seconds: int) -> None:
    """Run guard_statements on a DB-API connection, one cursor, closed afterwards."""
    cursor = connection.cursor()
    try:
        for statement in guard_statements(engine, statement_timeout_seconds, lock_timeout_seconds):
            cursor.execute(statement)
    finally:
        cursor.close()


def load_driver(name: str) -> Any:
    """Import a driver module by name. Raises ImportError naming the package to install."""
    try:
        return importlib.import_module(name)
    except ImportError as error:
        raise ImportError(f"safe_db needs the {name} package for this engine: pip install {name}") from error


def connect_sqlserver(host: str, database: str, user: str, password: str, *,
                      host_marker: str | None = "readonly", statement_timeout_seconds: int = 600,
                      lock_timeout_seconds: int = 5, driver: str = "ODBC Driver 17 for SQL Server",
                      port: int = 1433) -> Any:
    """A pyodbc connection to a SQL Server read replica: ApplicationIntent=ReadOnly, autocommit,
    a per-statement timeout, LOCK_TIMEOUT and low deadlock priority. The host must contain host_marker."""
    host = host.strip()
    require_marker(host, host_marker, "SQL Server host")
    pyodbc = load_driver("pyodbc")
    connection = pyodbc.connect(
        f"DRIVER={{{driver}}};SERVER={host},{port};DATABASE={database};UID={user};PWD={password};"
        "ApplicationIntent=ReadOnly;Encrypt=yes;TrustServerCertificate=yes", autocommit=True)
    connection.timeout = statement_timeout_seconds
    apply_guards(connection, "sqlserver", statement_timeout_seconds, lock_timeout_seconds)
    print(f"safe_db: sqlserver connected, host check {'passed' if host_marker else 'skipped'}, "
          f"statement timeout {statement_timeout_seconds}s, lock timeout {lock_timeout_seconds}s")
    return connection


def connect_mysql(host: str, database: str, user: str, password: str, *,
                  host_marker: str | None = None, user_marker: str | None = "read-only",
                  statement_timeout_seconds: int = 600, lock_timeout_seconds: int = 5,
                  port: int = 3306) -> Any:
    """A pymysql connection: autocommit, a read-only session, MAX_EXECUTION_TIME and short lock waits.
    CURRENT_USER() must contain user_marker, and the host host_marker when one is given."""
    require_marker(host, host_marker, "MySQL host")
    pymysql = load_driver("pymysql")
    connection = pymysql.connect(host=host.strip(), port=port, user=user, password=password,
                                 database=database, autocommit=True,
                                 read_timeout=statement_timeout_seconds + 30)
    cursor = connection.cursor()
    try:
        cursor.execute("SELECT CURRENT_USER()")
        current_user = cursor.fetchone()[0]
    finally:
        cursor.close()
    require_marker(current_user, user_marker, "MySQL login (CURRENT_USER())")
    apply_guards(connection, "mysql", statement_timeout_seconds, lock_timeout_seconds)
    print(f"safe_db: mysql connected, login check {'passed' if user_marker else 'skipped'}, "
          f"statement timeout {statement_timeout_seconds}s, lock timeout {lock_timeout_seconds}s")
    return connection


def connect_postgres(host: str, database: str, user: str, password: str, *, engine: str = "postgres",
                     host_marker: str | None = None, statement_timeout_seconds: int = 600,
                     lock_timeout_seconds: int = 5, port: int = 5432) -> Any:
    """A psycopg2 connection to Postgres or Redshift (engine='redshift', port 5439): autocommit,
    statement_timeout, and on Postgres a read-only session and a lock_timeout."""
    if engine not in ("postgres", "redshift"):
        raise ValueError(f"engine must be 'postgres' or 'redshift', found {engine!r}")
    require_marker(host, host_marker, f"{engine} host")
    psycopg2 = load_driver("psycopg2")
    connection = psycopg2.connect(host=host.strip(), port=port, dbname=database, user=user,
                                  password=password, connect_timeout=30)
    connection.autocommit = True
    apply_guards(connection, engine, statement_timeout_seconds, lock_timeout_seconds)
    print(f"safe_db: {engine} connected, statement timeout {statement_timeout_seconds}s")
    return connection


def read_query(connection: Any, sql: str, parameters: Sequence[Any] | None = None) -> list[tuple]:
    """Run one read on a safe_db connection and return every row. Raises UnsafeQueryError before running a write."""
    cursor = connection.cursor()
    try:
        cursor.execute(require_read(sql), parameters or ())
        return list(cursor.fetchall())
    finally:
        cursor.close()


def read_in_chunks(connection: Any, sql: str, key_column: str, chunk_size: int,
                   start_after: Any = None) -> Iterable[list[tuple]]:
    """Yield rows chunk by chunk with keyset pagination, so no single statement runs long.
    key_column must be the first column sql selects, and unique. sql is wrapped as
    SELECT * FROM (sql) AS page WHERE key_column > %s ORDER BY key_column, limited to chunk_size rows.
    The LIMIT form suits MySQL, Postgres and Redshift; for SQL Server use read_query with TOP."""
    require_read(sql)
    if not re.fullmatch(r"[A-Za-z_][\w]*", key_column):
        raise UnsafeQueryError(f"key column {key_column!r} is not a plain column name")
    last = start_after
    while True:
        where = f"WHERE {key_column} > %s " if last is not None else ""
        page_sql = f"SELECT * FROM ({sql}) AS page {where}ORDER BY {key_column} LIMIT {int(chunk_size)}"
        rows = read_query(connection, page_sql, [last] if last is not None else None)
        if not rows:
            return
        yield rows
        if len(rows) < chunk_size:
            return
        last = rows[-1][0]


def redshift_data_query(client: Any, sql: str, *, deadline_seconds: int, poll_seconds: float = 2.0,
                        **location: str) -> dict:
    """Run one read through the Redshift Data API (a boto3 'redshift-data' client) and return the
    describe_statement result. Cancels the statement and raises QueryDeadlineError past deadline_seconds.
    location is ClusterIdentifier or WorkgroupName, Database, and SecretArn or DbUser."""
    started = client.execute_statement(Sql=require_read(sql), **location)
    statement_id = started["Id"]
    deadline = time.monotonic() + deadline_seconds
    while True:
        described = client.describe_statement(Id=statement_id)
        status = described["Status"]
        if status == "FINISHED":
            return described
        if status in ("FAILED", "ABORTED"):
            raise RuntimeError(f"redshift-data statement {statement_id} {status}: {described.get('Error')}")
        if time.monotonic() >= deadline:
            client.cancel_statement(Id=statement_id)
            raise QueryDeadlineError(f"redshift-data statement {statement_id} passed its "
                                     f"{deadline_seconds}s deadline and was cancelled")
        time.sleep(poll_seconds)
