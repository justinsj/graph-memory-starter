"""The `harness2cc` command line.

Commands in this release:

  list-references  scan the transcript folders for answered decision points, write them
                   (and, separately, the answers) to the harness2cc home folder, and list them
  patch-upstream   apply the two-line Windows path fix to the installed upstream harness2

Exit codes: 0 done, 2 the command line was wrong, 3 the command refused (a configuration
problem, an upstream patch problem).
"""

import argparse
import sys
from datetime import date
from typing import Sequence

from harness2cc import decision_points as decision_points_module
from harness2cc.config import ConfigurationError, load_config
from harness2cc.decision_points import RECOMMENDED_MARKER, DecisionPoint, Label
from harness2cc.patch_upstream import UpstreamPatchError, patch_installed_upstream

EXIT_DONE = 0
EXIT_USAGE = 2
EXIT_REFUSED = 3
LIST_COLUMNS: tuple[tuple[str, int], ...] = (
    ("ID", 11), ("DATE", 10), ("PROJECT", 22), ("SHORT NAME", 18), ("RECOMMENDED", 34), ("YOU CHOSE", 34),
)


def parse_date(text: str) -> date:
    """Parse a YYYY-MM-DD date for `--since`.

    Args:
        text: The date as typed.

    Returns:
        The date.

    Raises:
        argparse.ArgumentTypeError: When the text is not a YYYY-MM-DD date.
    """
    try:
        return date.fromisoformat(text)
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"expected a date as YYYY-MM-DD, got {text!r}") from error


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for every command.

    Returns:
        The parser.
    """
    parser = argparse.ArgumentParser(
        prog="harness2cc",
        description="Harness2 (arXiv 2610.14224) for the Claude Code harness. "
                    "A run only ever covers decision points you name.")
    commands = parser.add_subparsers(dest="command", required=True, metavar="command")
    list_references = commands.add_parser(
        "list-references", help="scan transcripts and list answered decision points (no model calls)")
    list_references.add_argument("--since", type=parse_date, help="only decision points on or after this date")
    list_references.add_argument("--project", help="only decision points whose project folder name holds this text")
    list_references.add_argument("--mismatch-only", action="store_true",
                                 help="only decision points where you chose something other than the recommendation")
    commands.add_parser("patch-upstream", help="apply the Windows path fix to the installed upstream harness2")
    return parser


def fit(text: str, width: int) -> str:
    """Fit text into a fixed-width column, cutting it with "..." when it is too long.

    Args:
        text: The text.
        width: The column width.

    Returns:
        The text padded or cut to exactly `width` characters.
    """
    text = " ".join(text.replace(RECOMMENDED_MARKER, "").split())
    return text.ljust(width) if len(text) <= width else text[:width - 3] + "..."


def format_row(values: Sequence[str]) -> str:
    """Format one row of the `list-references` table.

    Args:
        values: One value per column, in `LIST_COLUMNS` order.

    Returns:
        The row, columns separated by two spaces.
    """
    return "  ".join(fit(value, width) for value, (_, width) in zip(values, LIST_COLUMNS)).rstrip()


def select_decision_points(decision_points: list[DecisionPoint], labels: dict[str, Label],
                           arguments: argparse.Namespace) -> list[DecisionPoint]:
    """Apply the `--since`, `--project` and `--mismatch-only` filters and sort newest first.

    Args:
        decision_points: Every decision point found.
        labels: The answers, by decision point id.
        arguments: The parsed command line.

    Returns:
        The decision points to show.
    """
    selected = []
    for decision_point in decision_points:
        if arguments.since and decision_point.timestamp[:10] < arguments.since.isoformat():
            continue
        if arguments.project and arguments.project.lower() not in decision_point.project.lower():
            continue
        if arguments.mismatch_only and labels[decision_point.decision_point_id].matches_recommended:
            continue
        selected.append(decision_point)
    return sorted(selected, key=lambda decision_point: decision_point.timestamp, reverse=True)


def run_list_references(arguments: argparse.Namespace) -> int:
    """Scan the transcripts, write the decision points and labels, and print the table.

    Args:
        arguments: The parsed command line.

    Returns:
        The exit code.
    """
    config = load_config()
    scan = decision_points_module.scan_transcripts(config.transcript_roots)
    decision_points_file, labels_file = decision_points_module.write_scan(scan, config)
    selected = select_decision_points(scan.decision_points, scan.labels, arguments)
    print(format_row([name for name, _ in LIST_COLUMNS]))
    for decision_point in selected:
        print(format_row([
            decision_point.decision_point_id,
            decision_point.timestamp[:10],
            decision_point.project,
            decision_point.short_name,
            decision_point.recommended,
            scan.labels[decision_point.decision_point_id].chosen,
        ]))
    print(f"{len(selected)} of {len(scan.decision_points)} decision points shown "
          f"({scan.transcripts_read} transcripts read)")
    if scan.malformed_lines:
        print(f"{scan.malformed_lines} transcript lines were not valid JSON and were not read")
    if scan.skipped_without_turn_start:
        print(f"{scan.skipped_without_turn_start} answered questions were left out because no typed prompt "
              "started their turn, so they cannot be replayed")
    print(f"Wrote {decision_points_file} and {labels_file}")
    return EXIT_DONE


def run_patch_upstream() -> int:
    """Apply the Windows path fix to the installed upstream package and print what changed.

    Returns:
        The exit code.
    """
    for message in patch_installed_upstream():
        print(message)
    return EXIT_DONE


def main(argv: Sequence[str] | None = None) -> int:
    """Run one `harness2cc` command.

    Args:
        argv: The arguments after the program name; `sys.argv[1:]` when omitted.

    Returns:
        The exit code: 0 done, 2 usage error, 3 refused.
    """
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = build_parser()
    try:
        arguments = parser.parse_args(argv)
    except SystemExit as exit_request:
        return int(exit_request.code or 0)
    try:
        if arguments.command == "list-references":
            return run_list_references(arguments)
        if arguments.command == "patch-upstream":
            return run_patch_upstream()
    except (ConfigurationError, UpstreamPatchError) as error:
        print(f"error: {error}", file=sys.stderr)
        return EXIT_REFUSED
    parser.error(f"unknown command {arguments.command!r}")
    return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
