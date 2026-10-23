"""harness2cc: Harness² (arXiv 2610.14224) for the Claude Code harness.

Replays past decision points from Claude Code transcripts, runs upstream Harness²'s
Propose, Probe and Compose loop on the ones the user names, and changes no live file
or library entry without the user's approval. User data lives under the harness2cc
home folder (`~/.claude/harness2cc/`), never in this repository.
"""

PINNED_UPSTREAM_COMMIT = "1cfe254e8d25b15f37048c3730134686abe60335"
