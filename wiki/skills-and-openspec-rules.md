---
title: Skills and OpenSpec rules (pr-review-loop, response-format, question-format, openspec-rules)
id: skills-and-openspec-rules
type: topic
tags: [claude-code, skill, install-guide, openspec, formats]
related: [session-merge, index]
updated: 2026-10-29
---

# Skills and OpenSpec rules

Sources: `skills/pr-review-loop/`, `skills/response-format/` (with `scripts/check_format.py`), `skills/question-format/` and `openspec-rules/`. Tests: `tests/test_check_format.py`, `tests/test_apply_openspec_rules.py` and `tests/test_install_guide.py`, each run with `python -m unittest discover -s tests -p <file name>`. Install instructions: Parts B, H and I of `docs/claude-session-tools-and-review-install.md`.

## When you change one, also update

- The installed copy: `<SKILLS_DIR>/<skill>/` for a skill, `<RULES_DIR>/` for the OpenSpec rules. The sources here are the master copies.
- The verbatim copy in the install guide. `tests/test_install_guide.py` fails until the guide and the source match byte for byte. Regenerate the guide's copy from the source, never by hand.
- For `openspec-rules/apply_openspec_rules.py`: the "What the script adds" table at the end of `openspec-rules/rules.md`.
- For `preferences.md`, `rules.md` section 1 or the "Before you ask" step of `question-format`: the skill restates the order of authority and the Needs-your-yes list, and `rules.md` names P11 by its label. `tests/test_openspec_preferences.py` fails until all copies agree.
- For the "settle it yourself first" rule: Part F's `## Asking questions` section in the install guide restates the same order of authority and Needs-your-yes list as prose, not as an embedded file, so edit it by hand alongside `question-format`. `tests/test_openspec_preferences.py` checks that it keeps both lists in order.
- For a change to `pr-review-loop/reference/review-procedure.md` that adds or removes a line naming the 180,000-character budget: the expected count in the guide's Verify check 7. `tests/test_install_guide.py` checks it.

## Before regenerating the guide

Diff the installed copies against the sources first. Fixes are often made straight in `~/.claude/skills/<skill>/` while a review loop runs, and the sources then lag: on 2026-10-29 the installed `pr-review-loop` had `--allow-large`, the documentation-only exemption from `no-tests` and `tests-not-claimed`, and the test-snapshot size exclusion (owner decisions of 2026-10-23 and 2026-10-24), and neither `skills/pr-review-loop/` nor the guide did. The other direction happens too: the installed `archive` skill on that machine still lacked the guide's "type /clear" ending.

## Nuances not obvious from the code

- **Where `openspec init` writes (CLI 1.14.0).** For Claude Code it writes the skill and command copies into the target folder's own `.claude/` (`skillsDir: '.claude'`). The personal copies under `~/.claude` exist because it once ran in the home folder; run in a repository, it does not touch them, so `apply_openspec_rules.py` has nothing to restore there. In a shell with no terminal (any agent), pass `--tools claude`: without it, init stops when the folder has no tool folder yet.
- **A clean checkout of `main` has 7 test errors.** `tests/test_impact.py`, `test_projects.py`, `test_project_cases.py` and the `test_kl_` flow, ingest and review cases read `projects/cases/inputs/*.md`, which is not committed. Compare a branch's suite against a clean `main` worktree, not against a working tree that has those files.

- **Sources live outside `.claude/`.** `.gitignore` ignores `.claude/` and `CLAUDE.md`, so the skills sit under `skills/` and are copied into `.claude/skills/` or `~/.claude/skills/` to install.
- **Examples stay neutral.** This repository is public (see [[session-merge]]). Use TICKET-12, Acme Widgets, example-org and shop-api; never real ticket keys, clients, repositories, people or machine paths.
- **`apply_openspec_rules.py` finds `rules.md` next to itself**, and writes that absolute path into OpenSpec's files on the machine it runs on. Nothing in this repository holds a machine path.
- **The patch anchors match the files the OpenSpec CLI 1.14.0 generates.** A newer CLI may change that text. The script then stops, names the file and the step, and writes nothing. Update the anchor, and keep the old replacement in `previous_replacements` so files patched earlier are upgraded in place.
- **The test against the real installed OpenSpec files is skipped** on a machine where OpenSpec's skills are not installed under `~/.claude`.
- **Part F's question layout and `question-format` are the same block**: `### Q<n>. <Short name>`, then Context, Example, Options, Reply with and Recorded in. Change both together, and `QUESTION_LABELS` in `check_format.py`.
- **pr-review-loop downloads asd-ste100 pinned to one commit** (`STE_COMMIT` in its `SKILL.md`). Read the upstream diff before moving the pin.
