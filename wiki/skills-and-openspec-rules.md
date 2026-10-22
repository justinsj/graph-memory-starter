---
title: Skills and OpenSpec rules (pr-review-loop, response-format, question-format, openspec-rules)
id: skills-and-openspec-rules
type: topic
tags: [claude-code, skill, install-guide, openspec, formats]
related: [session-merge, index]
updated: 2026-10-22
---

# Skills and OpenSpec rules

Sources: `skills/pr-review-loop/`, `skills/response-format/` (with `scripts/check_format.py`), `skills/question-format/` and `openspec-rules/`. Tests: `tests/test_check_format.py`, `tests/test_apply_openspec_rules.py` and `tests/test_install_guide.py`, each run with `python -m unittest discover -s tests -p <file name>`. Install instructions: Parts B, H and I of `docs/claude-session-tools-and-review-install.md`.

## When you change one, also update

- The installed copy: `<SKILLS_DIR>/<skill>/` for a skill, `<RULES_DIR>/` for the OpenSpec rules. The sources here are the master copies.
- The verbatim copy in the install guide. `tests/test_install_guide.py` fails until the guide and the source match byte for byte. Regenerate the guide's copy from the source, never by hand.
- For `openspec-rules/apply_openspec_rules.py`: the "What the script adds" table at the end of `openspec-rules/rules.md`.

## Nuances not obvious from the code

- **Sources live outside `.claude/`.** `.gitignore` ignores `.claude/` and `CLAUDE.md`, so the skills sit under `skills/` and are copied into `.claude/skills/` or `~/.claude/skills/` to install.
- **Examples stay neutral.** This repository is public (see [[session-merge]]). Use TICKET-12, Acme Widgets, example-org and shop-api; never real ticket keys, clients, repositories, people or machine paths.
- **`apply_openspec_rules.py` finds `rules.md` next to itself**, and writes that absolute path into OpenSpec's files on the machine it runs on. Nothing in this repository holds a machine path.
- **The patch anchors match the files the OpenSpec CLI 1.14.0 generates.** A newer CLI may change that text. The script then stops, names the file and the step, and writes nothing. Update the anchor, and keep the old replacement in `previous_replacements` so files patched earlier are upgraded in place.
- **The test against the real installed OpenSpec files is skipped** on a machine where OpenSpec's skills are not installed under `~/.claude`.
- **Part F's question layout and `question-format` are the same block**: `### Q<n>. <Short name>`, then Context, Example, Options, Reply with and Recorded in. Change both together, and `QUESTION_LABELS` in `check_format.py`.
- **pr-review-loop downloads asd-ste100 pinned to one commit** (`STE_COMMIT` in its `SKILL.md`). Read the upstream diff before moving the pin.
