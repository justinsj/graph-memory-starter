"""Insert the workspace OpenSpec rules into the personal OpenSpec skill and command files.

The OpenSpec CLI generates ~/.claude/skills/openspec-* and ~/.claude/commands/opsx/*.md,
and `openspec update` or `openspec init` rewrites them. This script adds the short blocks
that point those workflows at rules.md in this folder. It is idempotent: a block that is
already present is skipped. If an anchor it needs is missing or appears more than once, it
raises and writes nothing, because a silent partial patch would leave the workflows half
changed.

Usage:
    python apply_openspec_rules.py            # patch the files under ~/.claude
    python apply_openspec_rules.py --dry-run  # report what would change, write nothing
    python apply_openspec_rules.py --home <dir>
"""

import argparse
from dataclasses import dataclass
from pathlib import Path

# rules.md sits next to this script, so the steps it adds point at whichever folder the rules are installed in.
RULES_PATH = (Path(__file__).resolve().parent / "rules.md").as_posix()


@dataclass(frozen=True)
class TextEdit:
    """One replacement of an anchor string that must appear exactly once.

    Attributes:
        name: Short label used in reports and errors.
        anchor: Text that must appear exactly once in the target file before patching.
        replacement: Text that replaces the anchor. Its presence marks the edit as done.
        previous_replacements: Older versions of the replacement. One found in the file is
            upgraded to the current replacement instead of looking for the anchor.
    """

    name: str
    anchor: str
    replacement: str
    previous_replacements: tuple[str, ...] = ()


@dataclass(frozen=True)
class EditResult:
    """Outcome of planning the edits for one file.

    Attributes:
        path: The file the edits target.
        applied: Names of the edits that change the file.
        skipped: Names of the edits already present in the file.
        new_text: The full file text after the edits.
    """

    path: Path
    applied: list[str]
    skipped: list[str]
    new_text: str


class AnchorError(ValueError):
    """Raised when an anchor is missing or is not unique in a target file."""


WORKSPACE_RULES_PARAGRAPH = (
    f"**Workspace rules**: Before step 1, read `{RULES_PATH}` and `preferences.md` in the same "
    "folder, and follow sections 1 to 4. They change this workflow in three ways. Every question "
    "is pre-answered and recorded as a decision instead of asked. The change gets a `decisions.md`. "
    "And `proposal.md` needs a `## Deliverable and mockup` section. Where a step below says to ask "
    "the user, pre-answer instead, except in the two situations the rules file names."
)

PLANNING_BOUNDARY = (
    "**Planning boundary**: This workflow creates planning artifacts only. The user request that "
    "selected or triggered this workflow authorizes planning only, even if it asks to build or fix "
    "something. Do not edit project code. After the planning artifacts are complete, stop. Do not "
    "start implementation in the same response, even if the initial request asks for it. Wait for "
    "a new user request after the artifacts are presented; then start the apply workflow."
)

PROPOSE_EDITS = [
    TextEdit(
        name="propose: workspace rules paragraph",
        anchor=PLANNING_BOUNDARY,
        replacement=PLANNING_BOUNDARY + "\n\n" + WORKSPACE_RULES_PARAGRAPH,
    ),
    TextEdit(
        name="propose: step 1 pre-answers ambiguity",
        anchor=(
            "acceptance criteria, ask the user before creating the change. For minor details, "
            "make a reasonable assumption and record it in the planning artifacts."
        ),
        replacement=(
            "acceptance criteria, do not ask: pre-answer it and record it as a decision "
            "(workspace rules, section 1). For minor details, make a reasonable assumption and "
            "record it in the planning artifacts."
        ),
    ),
    TextEdit(
        name="propose: step 6c pre-answers artifact input",
        anchor=(
            "   c. **If an artifact requires user input** (unclear context):\n"
            "      - Ask the user to clarify\n"
        ),
        replacement=(
            "   c. **If an artifact requires user input** (unclear context):\n"
            "      - Do not ask: pre-answer it and record it as a decision (workspace rules, section 1)\n"
        ),
    ),
    TextEdit(
        name="propose: step 7 writes decisions.md",
        anchor="7. **Show final status**\n",
        replacement=(
            "7. **Write decisions.md** (workspace rules, section 2)\n\n"
            "   Write `decisions.md` in the change folder with every pre-answered question and the "
            "preferences that settled them. Check that `proposal.md` has its "
            "`## Deliverable and mockup` section (section 3) before you continue.\n\n"
            "8. **Show final status**\n"
        ),
    ),
    TextEdit(
        name="propose: output shows deliverable, preferences and decisions",
        anchor="- What's ready: \"All artifacts needed for implementation are ready.\"\n",
        replacement=(
            "- What's ready: \"All artifacts needed for implementation are ready.\"\n"
            "- Lay out the whole message as workspace rules section 4 says (outcome, Artifacts, "
            "Deliverable, Decisions as decision blocks with short names, Files, Next step). It "
            "covers the items above and replaces the prompt below.\n"
        ),
        previous_replacements=(
            "- What's ready: \"All artifacts needed for implementation are ready.\"\n"
            "- Then the three parts of workspace rules section 4, each under its own heading: "
            "Deliverable (with the mockup), Preferences used, and Decisions, followed by a link to "
            "`decisions.md`. End with the closing lines of section 4 instead of the prompt below.\n",
        ),
    ),
    TextEdit(
        name="propose: guideline requires the deliverable section",
        anchor="- Use `template` as the structure for your output file - fill in its sections\n",
        replacement=(
            "- Use `template` as the structure for your output file - fill in its sections\n"
            "- `proposal.md` also gets a `## Deliverable and mockup` section directly after "
            "`## What Changes` (workspace rules, section 3)\n"
        ),
    ),
    TextEdit(
        name="propose: guardrail pre-answers ambiguity",
        anchor=(
            "- Ask about ambiguities that would materially change scope, externally observable "
            "behavior, compatibility, or acceptance criteria; for minor details, make reasonable "
            "assumptions and record them"
        ),
        replacement=(
            "- Pre-answer ambiguities that would materially change scope, externally observable "
            "behavior, compatibility, or acceptance criteria, and record each one in `decisions.md` "
            "(workspace rules, section 1); for minor details, make reasonable assumptions and "
            "record them"
        ),
    ),
    TextEdit(
        name="propose: guardrail for an existing change name",
        anchor="- If a change with that name already exists, ask if user wants to continue it or create a new one",
        replacement=(
            "- If a change with that name already exists, do not touch it: use the next free name "
            "(`<name>-2`) and record that as a decision"
        ),
    ),
]

APPLY_EDITS = [
    TextEdit(
        name="apply: step 4b shows the decisions",
        anchor="5. **Show current progress**\n",
        replacement=(
            "4b. **Show the decisions** (workspace rules)\n\n"
            f"   If the state proceeds to implementation, read `{RULES_PATH}` and follow section 5 "
            "before the first task: show the preferences used and the decisions from the change's "
            "`decisions.md`, get a yes for any decision marked `Needs your yes`, then mark the "
            "file accepted.\n\n"
            "5. **Show current progress**\n"
        ),
    ),
    TextEdit(
        name="apply: guardrail shows the decisions first",
        anchor="- Always read context files before starting (from the apply instructions output)\n",
        replacement=(
            "- Always read context files before starting (from the apply instructions output)\n"
            "- Show the change's decisions before the first task (workspace rules, section 5)\n"
        ),
    ),
]

UPDATE_EDITS = [
    TextEdit(
        name="update: step 4b reconciles decisions.md",
        anchor="5. **Confirm and apply, one artifact at a time**\n",
        replacement=(
            "4b. **Reconcile decisions.md** (workspace rules)\n\n"
            f"   If the change folder has a `decisions.md`, read `{RULES_PATH}` and follow "
            "section 6: reconcile it with the drafted revisions and include its edits in step 5. "
            "A reply such as `D2: full refactor` is a request to change that decision.\n\n"
            "5. **Confirm and apply, one artifact at a time**\n"
        ),
    ),
    TextEdit(
        name="update: output shows the decision list",
        anchor="- Where the change stands and the recommended next command\n",
        replacement=(
            "- Where the change stands and the recommended next command\n"
            "- The decision list again, if `decisions.md` changed (workspace rules, section 4 format)\n"
        ),
    ),
]


def build_targets(home: Path) -> dict[Path, list[TextEdit]]:
    """Map each OpenSpec file under a home folder to the edits it needs.

    Args:
        home: The folder that holds `.claude` (normally the user's home folder).

    Returns:
        A mapping from file path to the ordered list of edits for that file.
    """
    claude_dir = home / ".claude"
    return {
        claude_dir / "skills" / "openspec-propose" / "SKILL.md": PROPOSE_EDITS,
        claude_dir / "commands" / "opsx" / "propose.md": PROPOSE_EDITS,
        claude_dir / "skills" / "openspec-apply-change" / "SKILL.md": APPLY_EDITS,
        claude_dir / "commands" / "opsx" / "apply.md": APPLY_EDITS,
        claude_dir / "skills" / "openspec-update-change" / "SKILL.md": UPDATE_EDITS,
        claude_dir / "commands" / "opsx" / "update.md": UPDATE_EDITS,
    }


def plan_edits(path: Path, text: str, edits: list[TextEdit]) -> EditResult:
    """Apply edits to a file's text in memory.

    An edit whose replacement is already present is skipped. An edit whose older
    replacement is present is upgraded in place. Every other edit needs its anchor exactly
    once.

    Args:
        path: The file the text came from, used in errors and the result.
        text: The current file text.
        edits: The edits to apply, in order.

    Returns:
        The edit result with the new text and the names of applied and skipped edits.

    Raises:
        AnchorError: An anchor is missing, or appears more than once.
    """
    applied: list[str] = []
    skipped: list[str] = []
    new_text = text
    for edit in edits:
        if edit.replacement in new_text:
            skipped.append(edit.name)
            continue
        previous = next((text for text in edit.previous_replacements if new_text.count(text) == 1), None)
        if previous is not None:
            new_text = new_text.replace(previous, edit.replacement)
            applied.append(edit.name)
            continue
        anchor_count = new_text.count(edit.anchor)
        if anchor_count != 1:
            raise AnchorError(
                f"{path}: edit '{edit.name}' needs its anchor exactly once, found {anchor_count}. "
                "OpenSpec may have changed this file; update the anchor in apply_openspec_rules.py."
            )
        new_text = new_text.replace(edit.anchor, edit.replacement)
        applied.append(edit.name)
    return EditResult(path=path, applied=applied, skipped=skipped, new_text=new_text)


def apply_rules(home: Path, dry_run: bool) -> list[EditResult]:
    """Plan the edits for every target file, then write them all.

    Nothing is written unless every file plans cleanly.

    Args:
        home: The folder that holds `.claude`.
        dry_run: When True, plan and report but write nothing.

    Returns:
        One edit result per target file.

    Raises:
        FileNotFoundError: A target file does not exist.
        AnchorError: An anchor is missing or not unique in a target file.
    """
    results: list[EditResult] = []
    for path, edits in build_targets(home).items():
        with path.open("r", encoding="utf-8", newline="") as handle:
            text = handle.read()
        results.append(plan_edits(path, text, edits))
    if not dry_run:
        for result in results:
            if result.applied:
                with result.path.open("w", encoding="utf-8", newline="") as handle:
                    handle.write(result.new_text)
    return results


def main() -> None:
    """Parse the command line, patch the files, and print what changed."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--home", type=Path, default=Path.home(), help="folder that holds .claude")
    parser.add_argument("--dry-run", action="store_true", help="report what would change, write nothing")
    arguments = parser.parse_args()
    results = apply_rules(arguments.home, arguments.dry_run)
    verb = "would apply" if arguments.dry_run else "applied"
    for result in results:
        print(f"{result.path}: {verb} {len(result.applied)}, already present {len(result.skipped)}")
        for name in result.applied:
            print(f"  + {name}")


if __name__ == "__main__":
    main()
