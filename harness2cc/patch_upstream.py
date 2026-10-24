"""The two-line Windows fix for upstream Harness² (decision D3 of the claude-code-harness2-trial change).

Upstream's `core/tree.py` builds harness file keys with `str(p.relative_to(...))`. On Windows
that gives `scripts\\summarize.py`, which never matches the README stubs it expects
(`scripts/README.md`), so every valid edit is rejected as "off the editable surface". The fix
changes those two lines to `p.relative_to(...).as_posix()`. It is applied to the installed copy
only after checking that the installed package is the pinned commit, it is safe to re-run,
and it stops with the file and the text it looked for when that text is not there.
"""

import importlib.metadata
import importlib.util
import json
import os
from dataclasses import dataclass
from pathlib import Path

from harness2cc import PINNED_UPSTREAM_COMMIT

UPSTREAM_DISTRIBUTION = "harness2"
TREE_MODULE = "harness2.core.tree"


@dataclass(frozen=True)
class LinePatch:
    """One line of upstream code and the line that replaces it."""

    original: str
    patched: str


TREE_LINE_PATCHES: tuple[LinePatch, ...] = (
    LinePatch("        rel = str(p.relative_to(d))", "        rel = p.relative_to(d).as_posix()"),
    LinePatch("        rel = str(p.relative_to(dest))", "        rel = p.relative_to(dest).as_posix()"),
)


class UpstreamPatchError(RuntimeError):
    """The installed upstream package is not the pinned commit, or its code is not what the patch expects."""


def installed_upstream_commit() -> str:
    """Return the git commit the installed `harness2` package was built from.

    Returns:
        The commit id recorded in the package's `direct_url.json`.

    Raises:
        UpstreamPatchError: When `harness2` is not installed or was not installed from git.
    """
    try:
        distribution = importlib.metadata.distribution(UPSTREAM_DISTRIBUTION)
    except importlib.metadata.PackageNotFoundError as error:
        raise UpstreamPatchError(
            "upstream harness2 is not installed in this Python environment; install it at commit "
            f"{PINNED_UPSTREAM_COMMIT} (see harness2cc/README.md)") from error
    direct_url_text = distribution.read_text("direct_url.json")
    if not direct_url_text:
        raise UpstreamPatchError("the installed harness2 has no direct_url.json, so its commit is unknown")
    commit = (json.loads(direct_url_text).get("vcs_info") or {}).get("commit_id", "")
    if not commit:
        raise UpstreamPatchError("the installed harness2 was not installed from git, so its commit is unknown")
    return commit


def installed_tree_file() -> Path:
    """Return the path of the installed `harness2/core/tree.py`.

    Raises:
        UpstreamPatchError: When the module cannot be found.
    """
    spec = importlib.util.find_spec(TREE_MODULE)
    if spec is None or not spec.origin:
        raise UpstreamPatchError(f"cannot find {TREE_MODULE} in this Python environment")
    return Path(spec.origin)


def split_line_ending(line: str) -> tuple[str, str]:
    """Split a line read with `newline=""` into its text and its line ending.

    Args:
        line: One line, with "\\r\\n", "\\n" or no ending.

    Returns:
        The text and the ending.
    """
    for ending in ("\r\n", "\n"):
        if line.endswith(ending):
            return line[:-len(ending)], ending
    return line, ""


def patch_tree_file(tree_path: Path) -> list[str]:
    """Apply the two-line fix to a `tree.py` file, keeping its line endings.

    Args:
        tree_path: The file to patch.

    Returns:
        One message per line: patched, or already patched.

    Raises:
        UpstreamPatchError: When a line is found neither in its original nor its patched form, or more than once.
    """
    with tree_path.open(encoding="utf-8", newline="") as handle:
        lines = handle.readlines()
    texts = [split_line_ending(line)[0] for line in lines]
    messages: list[str] = []
    changed = False
    for line_patch in TREE_LINE_PATCHES:
        original_rows = [index for index, text in enumerate(texts) if text == line_patch.original]
        patched_rows = [index for index, text in enumerate(texts) if text == line_patch.patched]
        if len(original_rows) + len(patched_rows) != 1:
            raise UpstreamPatchError(
                f"{tree_path}: expected exactly one line '{line_patch.original.strip()}' or "
                f"'{line_patch.patched.strip()}', found {len(original_rows)} and {len(patched_rows)}. "
                f"Is this upstream commit {PINNED_UPSTREAM_COMMIT}?")
        if patched_rows:
            messages.append(f"line {patched_rows[0] + 1} already patched: {line_patch.patched.strip()}")
            continue
        row = original_rows[0]
        lines[row] = line_patch.patched + split_line_ending(lines[row])[1]
        texts[row] = line_patch.patched
        changed = True
        messages.append(f"line {row + 1} patched: {line_patch.patched.strip()}")
    if changed:
        # Write a new file and move it into place: uv installs files as hard links to its cache,
        # and writing through the link would change the cached copy every later install uses.
        replacement_path = tree_path.with_name(tree_path.name + ".harness2cc-new")
        with replacement_path.open("w", encoding="utf-8", newline="") as handle:
            handle.writelines(lines)
        os.replace(replacement_path, tree_path)
    return messages


def is_tree_file_patched(tree_path: Path) -> bool:
    """Say whether both lines of the fix are in place in a `tree.py` file.

    Args:
        tree_path: The file to check.

    Returns:
        True when every patched line is present.
    """
    with tree_path.open(encoding="utf-8", newline="") as handle:
        texts = {split_line_ending(line)[0] for line in handle}
    return all(line_patch.patched in texts for line_patch in TREE_LINE_PATCHES)


def patch_installed_upstream() -> list[str]:
    """Check the installed upstream commit, then apply the fix to its `core/tree.py`.

    Returns:
        The messages from `patch_tree_file`, after one naming the file.

    Raises:
        UpstreamPatchError: When the installed commit is not the pinned one, or the file is not as expected.
    """
    commit = installed_upstream_commit()
    if commit != PINNED_UPSTREAM_COMMIT:
        raise UpstreamPatchError(
            f"installed harness2 is commit {commit}, but harness2cc is pinned to {PINNED_UPSTREAM_COMMIT}")
    tree_path = installed_tree_file()
    return [f"patching {tree_path} (commit {commit})"] + patch_tree_file(tree_path)


def assert_upstream_patched() -> None:
    """Stop when the installed upstream lacks the Windows fix. Commands that run upstream's loop call this first.

    Raises:
        UpstreamPatchError: When the fix is missing; the message names `harness2cc patch-upstream`.
    """
    tree_path = installed_tree_file()
    if not is_tree_file_patched(tree_path):
        raise UpstreamPatchError(f"{tree_path} lacks the Windows path fix; run `harness2cc patch-upstream` first")
