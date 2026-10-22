"""PreToolUse hook for Bash and PowerShell: data and test commands go through run_bounded, and safe_db.

Claude Code sends the tool call as JSON on stdin. Three checks, on commands that
match a heavy pattern in config.json (pytest, python some_script.py, sqlcmd, ...):

    unwrapped    the command is not run through run_bounded.py
    overran      its script overran its budget last time and has not changed since
    raw driver   its script imports a database driver but not safe_db

In "warn" mode the call goes ahead and the model is told what was wrong. In
"block" mode the call is denied with the same text. Anything else passes silently.
A config or ledger that cannot be read fails the hook loudly rather than passing.
"""

import json
import re
import sys
from pathlib import Path

from runguard_common import file_hash, last_entry_for, ledger_path, load_config, read_ledger, script_in, split_command

GUARDED_TOOLS = ("Bash", "PowerShell")
RUNGUARD_DIR = Path(__file__).resolve().parent


def is_heavy(command: str, config: dict) -> bool:
    """True when the command runs a script, tests or a query, and is not a quick exempt call."""
    if any(re.search(pattern, command) for pattern in config["exempt_patterns"]):
        return False
    return any(re.search(pattern, command) for pattern in config["heavy_patterns"])


def is_wrapped(command: str) -> bool:
    """True when the command runs through run_bounded.py."""
    return "run_bounded.py" in command


def command_words(command: str) -> list[str]:
    """The words of the command that is actually run: after run_bounded's --, or all of them."""
    words = split_command(command)
    if is_wrapped(command) and "--" in words:
        inner = words[words.index("--") + 1:]
        return split_command(inner[0].strip("\"'")) if len(inner) == 1 else inner
    return words


def imports_raw_driver(script: Path, config: dict) -> list[str]:
    """Database drivers a .py script imports when it does not also import safe_db. Empty when it is fine."""
    if script.suffix.lower() != ".py":
        return []
    source = script.read_text(encoding="utf-8", errors="replace")
    imported = set(re.findall(r"^\s*(?:from|import)\s+([A-Za-z_][\w.]*)", source, flags=re.MULTILINE))
    if any(name.split(".")[0] == config["safe_db_module"] for name in imported):
        return []
    drivers = config["db_driver_modules"]
    return sorted({driver for driver in drivers
                   for name in imported if name == driver or name.startswith(driver + ".")})


def problems_with(command: str, config: dict, cwd: Path) -> list[str]:
    """What is wrong with this command, one sentence each. Empty when it may run."""
    if not is_heavy(command, config):
        return []
    problems = []
    if not is_wrapped(command):
        budgets = ", ".join(f"{kind} {seconds}s" for kind, seconds in config["budgets"].items())
        problems.append("This command runs a script, tests or a query without a time budget. Run the "
                        "script-preflight checklist, then wrap it: python "
                        f"\"{RUNGUARD_DIR / 'run_bounded.py'}\" --budget <time> --label <name> -- <command>. "
                        f"Default budgets: {budgets}.")
    script = script_in(command_words(command), cwd)
    if script is None:
        return problems
    last = last_entry_for(read_ledger(ledger_path(config)), script)
    if last and last.get("outcome") == "budget_exceeded" and last.get("script_hash") == file_hash(script):
        problems.append(f"{script.name} overran its {last['budget_seconds']}s budget on {last['at']} and has "
                        "not changed since. Optimize it first (script-preflight skill), or ask the user to "
                        f"run: python \"{RUNGUARD_DIR / 'ledger.py'}\" clear <script> --reason \"...\".")
    drivers = imports_raw_driver(script, config)
    if drivers:
        problems.append(f"{script.name} imports {', '.join(drivers)} but not safe_db. Open database "
                        "connections through safe_db, which sets lock and statement timeouts and refuses "
                        "anything but a read.")
    return problems


def decide(payload: dict, config: dict) -> dict | None:
    """The hook's JSON reply for one tool call, or None to let it pass with nothing said."""
    if payload.get("tool_name") not in GUARDED_TOOLS:
        return None
    command = (payload.get("tool_input") or {}).get("command") or ""
    problems = problems_with(command, config, Path(payload.get("cwd") or Path.cwd()))
    if not problems:
        return None
    text = "runguard: " + " ".join(problems)
    if config["mode"] == "block":
        return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                       "permissionDecisionReason": text}}
    return {"systemMessage": text,
            "hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": text}}


def main() -> int:
    """Read the tool call from stdin, print the reply if there is one."""
    payload = json.loads(sys.stdin.buffer.read().decode("utf-8") or "{}")
    reply = decide(payload, load_config())
    if reply is not None:
        sys.stdout.write(json.dumps(reply, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
