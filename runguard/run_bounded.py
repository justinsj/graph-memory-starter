"""Run a command inside a time budget, kill its whole process tree when the budget runs out, and log the run.

    python runguard/run_bounded.py --budget 10m --label pull-orders -- python scripts/pull_orders.py
    python runguard/run_bounded.py --budget 5m -- "pytest -x tests/test_rules.py"

One word after -- runs through the shell (pipes, &&); several run as they are.
Exit code: the command's own, or 124 when the budget ran out (as GNU timeout does).
Every run adds one line to the ledger: the command, the script and its sha256,
the budget, how long it took and how it ended. preflight_gate.py reads it to
refuse a re-run of a script that overran and has not changed since.
"""

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from runguard_common import append_ledger, file_hash, ledger_path, load_config, parse_budget, script_in

BUDGET_EXCEEDED = 124
GRACE_SECONDS = 5


def build_parser() -> argparse.ArgumentParser:
    """The command line: the budget, a label, approval for a long budget, and the command after --."""
    parser = argparse.ArgumentParser(description="Run a command inside a time budget.")
    parser.add_argument("--budget", required=True, help="90, 90s, 10m or 1h")
    parser.add_argument("--label", default="", help="a name for the ledger, e.g. backtest-q3")
    parser.add_argument("--approved", action="store_true",
                        help="the user approved a budget above max_budget_seconds")
    parser.add_argument("command", nargs=argparse.REMAINDER, help="-- then the command")
    return parser


def start(command: list[str]) -> subprocess.Popen:
    """Start the command in its own process group, so the tree can be killed as one."""
    shell = len(command) == 1
    target = command[0] if shell else command
    if os.name == "nt":
        return subprocess.Popen(target, shell=shell, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
    return subprocess.Popen(target, shell=shell, start_new_session=True)


def kill_tree(process: subprocess.Popen) -> None:
    """Kill the process and every child it started. Raises if the tree is still alive afterwards."""
    if os.name == "nt":
        result = subprocess.run(["taskkill", "/T", "/F", "/PID", str(process.pid)],
                                capture_output=True, text=True)
        if result.returncode != 0 and process.poll() is None:
            raise RuntimeError(f"taskkill could not stop pid {process.pid}: {result.stderr.strip()}")
    else:
        group = os.getpgid(process.pid)
        os.killpg(group, signal.SIGTERM)
        try:
            process.wait(timeout=GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            os.killpg(group, signal.SIGKILL)
    process.wait(timeout=GRACE_SECONDS)


def run(command: list[str], budget_seconds: int) -> tuple[int, float, str]:
    """Run the command. Returns (exit code, seconds taken, outcome: ok, failed, budget_exceeded or interrupted)."""
    started = time.monotonic()
    process = start(command)
    try:
        exit_code = process.wait(timeout=budget_seconds)
    except subprocess.TimeoutExpired:
        kill_tree(process)
        return BUDGET_EXCEEDED, time.monotonic() - started, "budget_exceeded"
    except KeyboardInterrupt:
        kill_tree(process)
        return 130, time.monotonic() - started, "interrupted"
    return exit_code, time.monotonic() - started, "ok" if exit_code == 0 else "failed"


def main(argv: list[str] | None = None) -> int:
    """Check the budget, run the command, log it, and say how much of the budget it used."""
    arguments = build_parser().parse_args(argv)
    command = arguments.command[1:] if arguments.command[:1] == ["--"] else arguments.command
    if not command:
        raise SystemExit("run_bounded: no command after --")
    config = load_config()
    budget_seconds = parse_budget(arguments.budget)
    if budget_seconds > config["max_budget_seconds"] and not arguments.approved:
        raise SystemExit(f"run_bounded: a {budget_seconds}s budget is over the {config['max_budget_seconds']}s "
                         "limit. Ask the user, then pass --approved.")

    script = script_in(command if len(command) > 1 else command[0].split())
    entry = {"label": arguments.label, "command": " ".join(command), "cwd": str(Path.cwd()),
             "script": str(script) if script else None,
             "script_hash": file_hash(script) if script else None,
             "budget_seconds": budget_seconds}

    exit_code, seconds, outcome = run(command, budget_seconds)
    append_ledger(ledger_path(config), {**entry, "seconds": round(seconds, 1),
                                        "exit_code": exit_code, "outcome": outcome})

    share = seconds / budget_seconds
    name = arguments.label or entry["command"]
    if outcome == "budget_exceeded":
        print(f"runguard: BUDGET EXCEEDED: {name} was stopped after {budget_seconds}s. "
              "Run the script-preflight checklist and change the script before running it again.",
              file=sys.stderr)
    elif share >= config["slow_fraction"]:
        print(f"runguard: SLOW: {name} took {seconds:.1f}s, {share:.0%} of its {budget_seconds}s budget. "
              "Optimize it before the next run.", file=sys.stderr)
    else:
        print(f"runguard: {name} took {seconds:.1f}s, {share:.0%} of its {budget_seconds}s budget.",
              file=sys.stderr)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
