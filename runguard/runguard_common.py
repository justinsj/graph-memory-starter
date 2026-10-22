"""What the run guard's scripts share: the config, budgets, the ledger, the script a command runs."""

import hashlib
import json
import os
import re
import shlex
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONFIG = Path(os.environ.get("RUNGUARD_CONFIG") or HERE / "config.json")

# A command with nothing chained to it. Outside double quotes: no &&, lone &, ;, | or newline
# (the & of a 2>&1 or &> redirection is fine). Anywhere: no $( ) or backticks.
ALONE = r'(?:[^&|;\n$`"]|(?<=>)&|&(?=>)|"[^"\n$`]*")*$'


def build_exempt_pattern(required: str) -> str:
    """An exempt pattern: the command contains `required` and has nothing chained to it.

    Patterns are matched against the whole command line, so a bare "--help" would also exempt
    "python pull.py --help && python backtest.py". Anchoring to ALONE keeps that checked.
    """
    return f"^(?=.*{required}){ALONE}"


DEFAULTS: dict = {
    "mode": "warn",                # warn: allow and tell the model; block: deny the call
    "budgets": {"test": 300, "data": 600, "backtest": 1800},
    "max_budget_seconds": 1800,    # above this, run_bounded needs --approved
    "slow_fraction": 0.8,          # a run that used more than this share of its budget is "slow"
    "ledger": "ledger.jsonl",      # relative to this folder, or absolute
    "heavy_patterns": [
        r"\bpytest\b",
        r"\bpython[0-9.]*(?:\.exe)?\s+(?:-[A-Za-z]+\s+)*(?:-m\s+(?:unittest|pytest)\b|[^\s-][^\s]*\.py\b)",
        r"\bpy(?:\.exe)?\s+(?:-[0-9.]+\s+)?[^\s-][^\s]*\.py\b",
        r"\bjupyter\s+(?:nbconvert|execute)\b",
        r"\bpapermill\b",
        r"\bsqlcmd\b",
        r"\bmysql\s",
        r"\bpsql\b",
        r"\baws\s+redshift-data\s+execute-statement\b",
        r"\baws\s+athena\s+start-query-execution\b",
    ],
    "exempt_patterns": [
        build_exempt_pattern(r"--version\b"),
        build_exempt_pattern(r"--help\b"),
        build_exempt_pattern(r"\s-m\s+(?:pip|venv|json\.tool)\b"),
    ],
    "db_driver_modules": ["pyodbc", "pymssql", "pymysql", "mysql.connector", "MySQLdb",
                          "psycopg", "psycopg2", "redshift_connector", "sqlalchemy"],
    "safe_db_module": "safe_db",
}

SCRIPT_SUFFIXES = (".py", ".sql", ".ipynb")


def load_config(path: Path | None = None) -> dict:
    """config.json laid over DEFAULTS. A file that does not parse raises, it is never skipped."""
    path = path or CONFIG
    merged = json.loads(json.dumps(DEFAULTS))
    if path.is_file():
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError(f"{path} must hold a JSON object, found {type(loaded).__name__}")
        merged.update(loaded)
    if merged["mode"] not in ("warn", "block"):
        raise ValueError(f"{path}: mode must be 'warn' or 'block', found {merged['mode']!r}")
    return merged


def ledger_path(config: dict) -> Path:
    """Where the ledger lives. RUNGUARD_LEDGER wins over the config, so tests can point elsewhere."""
    override = os.environ.get("RUNGUARD_LEDGER")
    if override:
        return Path(override)
    path = Path(config["ledger"])
    return path if path.is_absolute() else HERE / path


def parse_budget(text: str) -> int:
    """'90', '90s', '10m' or '1h' as whole seconds. Anything else, or zero, raises ValueError."""
    match = re.fullmatch(r"\s*(\d+)\s*([smh]?)\s*", text.lower())
    if not match:
        raise ValueError(f"budget {text!r} is not a number of seconds, or a number followed by s, m or h")
    seconds = int(match.group(1)) * {"": 1, "s": 1, "m": 60, "h": 3600}[match.group(2)]
    if seconds <= 0:
        raise ValueError("budget must be more than zero seconds")
    return seconds


def split_command(command: str) -> list[str]:
    """Shell words of a command. POSIX rules first; a Windows path that breaks them falls back to whitespace."""
    try:
        return shlex.split(command, posix=False)
    except ValueError:
        return command.split()


def script_in(words: list[str], cwd: Path | None = None) -> Path | None:
    """The first word that names a .py, .sql or .ipynb file on disk, or None."""
    base = cwd or Path.cwd()
    for word in words:
        cleaned = word.strip("\"'")
        if not cleaned.lower().endswith(SCRIPT_SUFFIXES):
            continue
        candidate = Path(cleaned)
        if not candidate.is_absolute():
            candidate = base / candidate
        if candidate.is_file():
            return candidate.resolve()
    return None


def file_hash(path: Path) -> str:
    """sha256 of the file's bytes, so an edited script is told apart from the one that overran."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_ledger(path: Path) -> list[dict]:
    """Every entry in the ledger, oldest first. A line that is not JSON raises with its line number."""
    if not path.is_file():
        return []
    entries = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError as error:
            raise ValueError(f"{path}:{number} is not JSON: {error}") from error
    return entries


def append_ledger(path: Path, entry: dict) -> None:
    """Add one entry, stamped with the UTC time, as one JSON line."""
    path.parent.mkdir(parents=True, exist_ok=True)
    stamped = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), **entry}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(stamped, ensure_ascii=False) + "\n")


def last_entry_for(entries: list[dict], script: Path) -> dict | None:
    """The newest run or clear entry for this script, or None if it has never run under the guard."""
    key = str(script)
    for entry in reversed(entries):
        if entry.get("script") == key:
            return entry
    return None
