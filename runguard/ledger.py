"""Read the run ledger: which scripts overran or ran slow, and clear one for a re-run.

    python runguard/ledger.py report            the runs to revisit, slowest share of budget first
    python runguard/ledger.py report --all      every run
    python runguard/ledger.py clear path/to/script.py --reason "user approved a re-run as is"

clear is for the user. It lets an unchanged script that overran run once more,
and the reason is kept in the ledger beside it.
"""

import argparse
import sys
from pathlib import Path

from runguard_common import append_ledger, file_hash, ledger_path, load_config, read_ledger


def runs_to_revisit(entries: list[dict], slow_fraction: float) -> list[dict]:
    """Runs that overran or used at least slow_fraction of their budget, worst first."""
    flagged = [entry for entry in entries
               if entry.get("outcome") == "budget_exceeded"
               or (entry.get("budget_seconds") and entry.get("seconds") is not None
                   and entry["seconds"] / entry["budget_seconds"] >= slow_fraction)]
    return sorted(flagged, key=lambda entry: entry["seconds"] / entry["budget_seconds"], reverse=True)


def format_row(entry: dict) -> str:
    """One run as one line: when, outcome, seconds of budget, label or command."""
    share = entry["seconds"] / entry["budget_seconds"]
    name = entry.get("label") or entry.get("command", "")
    return (f"{entry['at']}  {entry['outcome']:<16} {entry['seconds']:>8.1f}s of "
            f"{entry['budget_seconds']:>5}s ({share:>4.0%})  {name}")


def main(argv: list[str] | None = None) -> int:
    """report or clear, as the module docstring says."""
    parser = argparse.ArgumentParser(description="Read or clear the run ledger.")
    commands = parser.add_subparsers(dest="action", required=True)
    report = commands.add_parser("report")
    report.add_argument("--all", action="store_true")
    clear = commands.add_parser("clear")
    clear.add_argument("script")
    clear.add_argument("--reason", required=True)
    arguments = parser.parse_args(argv)

    config = load_config()
    path = ledger_path(config)
    entries = read_ledger(path)

    if arguments.action == "clear":
        script = Path(arguments.script).resolve()
        if not script.is_file():
            raise SystemExit(f"ledger: {script} is not a file")
        append_ledger(path, {"script": str(script), "script_hash": file_hash(script),
                             "outcome": "cleared", "reason": arguments.reason})
        print(f"ledger: {script.name} may run once more as it is.")
        return 0

    runs = [entry for entry in entries if entry.get("outcome") != "cleared"]
    shown = runs if arguments.all else runs_to_revisit(runs, config["slow_fraction"])
    if not shown:
        print("ledger: nothing to revisit." if not arguments.all else "ledger: no runs yet.")
        return 0
    for entry in shown:
        print(format_row(entry))
    return 0


if __name__ == "__main__":
    sys.exit(main())
