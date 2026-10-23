# Tasks

Delivery: three PRs, in order (decision D20). Each PR runs the whole test suite before it opens and carries its own README section. PR 1 makes no model calls; PR 2 can run a loop and stage its results but cannot change a live file; PR 3 adds the approval gates.

## 1. Install upstream Harness² (PR 1)

- [x] 1.1 Install `uv` for the user (`py -3.11 -m pip install --user uv`), then `uv python install 3.12`. Verify that `uv run --python 3.12 python --version` prints 3.12.
- [x] 1.2 Create `~/.claude/harness2cc/.venv` with Python 3.12 and install upstream `harness2` from git at commit `1cfe254e8d25b15f37048c3730134686abe60335`. Verify that `pip show harness2` names that commit in its direct URL record.
- [x] 1.3 Check upstream on Windows before writing adapter code: import `harness2.core.recursion`, `harness2.core.selection`, `harness2.core.library` and `harness2.core.proposer`, and run upstream's `tests/test_workflow.py` from the pinned checkout. Verify that the imports succeed, and record which upstream tests pass and which fail on Windows (with the error) for the README's "Windows notes" (task 3.4).

## 2. Package and configuration (PR 1)

- [x] 2.1 Create `harness2cc/` with `pyproject.toml` (entry point `harness2cc`), `config.example.json` (placeholder values only) and the configuration loader that stops on a missing or invalid key with the key's name. Install it in editable mode into the environment from 1.2. Verify with `test_a_missing_configuration_key_is_named` and `test_data_files_are_written_under_the_harness2cc_home`.
- [x] 2.2 Add the shims in `~/.local/bin`, which is on both the Windows and the Git Bash `PATH` (`~/bin` is not on the Windows `PATH`): `harness2cc.cmd` for PowerShell and cmd, and a `harness2cc` shell script for Git Bash. Verify that `harness2cc --help` runs from a new Git Bash and a new PowerShell window.
- [x] 2.3 Add `harness2cc patch-upstream` (decision D3): it checks that the installed `harness2` is the pinned commit, changes `core/tree.py` lines 140 and 167 to `.as_posix()`, does nothing when they are already changed, and stops with the file and line when neither form is there. Run it on the installed package. Verify with `test_the_upstream_patch_fixes_windows_paths`, `test_the_upstream_patch_is_safe_to_rerun` and `test_the_upstream_patch_stops_on_unexpected_lines`, and that upstream's `tests/test_workflow.py` passes against the patched install with a no-op `fcntl` stand-in.

## 3. Decision points and replays (PR 1)

- [x] 3.1 Move the transcript scan into `harness2cc/decision_points.py`: AskUserQuestion calls and "### Q<n>." chat blocks with a "(Recommended)" option, stable `dp-` ids, answers written to `labels.jsonl` only. Verify with `test_an_answered_question_becomes_a_decision_point`, `test_an_unanswered_question_is_not_a_decision_point` and `test_archived_copies_of_a_session_are_counted_once`.
- [x] 3.2 Build `replay.md` for a decision point (user messages word for word, assistant text cut to 4,000 characters, tool calls by name and path, the fixed closing instruction). Verify with `test_the_replay_holds_no_answer`.
- [x] 3.3 Add `harness2cc list-references` with `--since`, `--project` and `--mismatch-only`. Verify with `test_list_references_filters_by_date_project_and_mismatch` and by running it on the real transcripts: it lists every answered question the earlier scan found (92 on 2026-10-23, more if new ones were answered since).
- [x] 3.4 Write `harness2cc/README.md` with install, configuration, `list-references` and the Windows notes from 1.3. Verify that each command in it runs as written.
- [x] 3.5 Add `tests/test_harness2cc.py` to the test-name glob in `tests/test_kl_specs.py`. Verify that `python -m unittest tests.test_kl_specs` passes, that the whole suite passes in the repository's environment, and that `tests.test_harness2cc` passes in the Python 3.12 one (which holds harness2cc and upstream only, not the repository's service dependencies).

## 4. Sandbox and the Claude Code substrate (PR 2)

- [ ] 4.1 Write the sandbox command builder and environment scrub shared by executor, editor and grader sessions (Design, Decision 3). Verify with `test_a_sandbox_run_has_no_live_tools`, `test_cloud_and_database_credentials_are_removed_from_a_sandbox_run` and `test_an_editor_session_has_no_live_tools`.
- [ ] 4.2 Write `ClaudeCodeSubstrate` (surface from the configuration, `materialise`, `execute`, `read_trajectory`, `preflight`) and the replay adapter (`BenchmarkAdapter` with `score` returning `None`). Verify with `test_a_sandbox_run_sees_only_the_harness_and_the_replay` and `test_a_trajectory_renders_text_tool_calls_and_results`.
- [ ] 4.3 Replace upstream's `claude_cli` editor command with the sandboxed one (no `--dangerously-skip-permissions`, no Vertex settings). Verify with `test_an_editor_session_has_no_live_tools` against the patched proposer.
- [ ] 4.4 Run one real sandboxed `claude -p` call on a one-line replay (cost under $0.10). Verify from the stream's init event that it lists no MCP servers and no plugins and offers only Read, Glob and Grep, and that a request to read a file outside the folder fails.

## 5. Guardrails (PR 2)

- [ ] 5.1 Write `validate_tree`: refuse a protected `CLAUDE.md` section or file from the configuration, and any path off the editable surface. Verify with `test_a_candidate_that_edits_a_guardrail_is_rejected` and `test_a_candidate_outside_the_editable_surface_is_rejected`.

## 6. The run command (PR 2)

- [ ] 6.1 Write argument checks: at least one `--reference` (at most 5), `--k` 1 to 5 (default 1), `--mode parallel|sequential` (default parallel), `--budget-usd`, model flags, `--fast-set`, `--dry-run`. Verify with `test_a_run_without_a_reference_is_refused`, `test_the_k_value_and_mode_come_from_the_command` and `test_a_dry_run_makes_no_model_calls`.
- [ ] 6.2 Orchestrate the loop through upstream's `run_mode`, `run_selection` or `trivial_selection`, and `reflect_adoption` (Design, Decision 1), with the deterministic editor in tests. Verify with `test_a_run_takes_only_the_decision_points_it_names` and `test_grades_are_not_written_into_the_editors_workspace`.
- [ ] 6.3 Record `run.json` (references, k, mode, models, fingerprints, upstream commit, cost per call and total) and stop at the cost cap with status BUDGET_REACHED, staging nothing. Verify with `test_a_run_records_its_inputs_outputs_and_cost` and `test_a_run_stops_at_its_cost_cap`.

## 7. Grading (PR 2)

- [ ] 7.1 Write the grader session and the fast-set report (asked, matched, Needs-your-yes settled, per harness). Verify with `test_the_fast_set_grades_both_harnesses` and `test_settling_a_needs_your_yes_question_counts_as_a_failure`.
- [ ] 7.2 Add `harness2cc test` with `--full`, `--fast-set` and `--harness <folder>`. Verify with `test_the_full_held_out_set_runs_only_on_request` and `test_a_saved_harness_snapshot_can_be_graded`.
- [ ] 7.3 Add the sandbox limits, `run` and `test` to the README, and say that this release stages results without any approve command. Verify that each command in the new sections runs as written in its dry-run form, that the whole suite passes in the repository's environment, and that `tests.test_harness2cc` passes in the Python 3.12 one.

## 8. Gate 1: harness approval (PR 3)

- [ ] 8.1 Stage the composed harness, diff and evidence under `pending/`, and print the gate commands. Verify with `test_a_composed_harness_waits_for_approval`.
- [ ] 8.2 Write the scans (Design, Decision 7). Verify with `test_a_harness_diff_with_a_scan_finding_is_refused`.
- [ ] 8.3 Write `approve-harness` (fingerprint check, scans, growth cap, backups, live write, source copies and install guide, `tests/test_install_guide.py`, ledger) and `reject-harness`. Verify with `test_an_approved_harness_updates_the_live_files_and_their_sources`, `test_a_rejected_harness_leaves_every_file_unchanged`, `test_an_approved_harness_that_grows_claude_md_past_the_cap_is_refused`, `test_an_approval_after_the_live_file_changed_is_refused` and `test_every_approval_is_written_to_the_ledger`.

## 9. Gate 2: lesson approval (PR 3)

- [ ] 9.1 Root reflection's library at `library/pending/`, pass only the approved library to `run_mode`, and write `approve-lesson`, `reject-lesson` and `library prune <entry>`. Verify with `test_a_lesson_waits_in_pending_until_approved`, `test_a_lesson_with_a_scan_finding_cannot_be_approved`, `test_a_full_library_refuses_a_new_lesson` and `test_runs_and_the_library_are_written_outside_the_repository`.
- [ ] 9.2 Add the two gates, the scans and rollback from backups to the README. Verify that the rollback commands restore a backed-up file in a scratch folder.

## 10. Integration checks (PR 3)

- [ ] 10.1 Run the whole test suite in the repository's environment and `tests.test_harness2cc` in the Python 3.12 one. Verify that every existing test passes unchanged and every `test_harness2cc.py` test passes, and that every scenario in `specs/harness-improvement/spec.md` has a test of the same name.
- [ ] 10.2 Check the deliverable against the mockup in `proposal.md` (section "Deliverable and mockup"): run `list-references`, `run --dry-run`, `run` with no reference, and `approve-lesson` on a pending lesson that holds a client term. Verify that each mockup line has its counterpart in the real output (the values differ), and list any difference in the README.

## 11. First trial (after PR 3 merges; the results go in with the archive)

- [ ] 11.1 Write the real `~/.claude/harness2cc/config.json` and `client_terms.txt` (client names from the transcripts and the workspace notes). Verify that `harness2cc list-references` runs on it and that the repository has no new file.
- [ ] 11.2 Grade the harness from before the question-handling edits (saved at `~/.claude/backups/harness-h0-2026-10-23/`) against the current one with `harness2cc test --harness <that folder>` on the fast set. Verify that the report shows asked, matched and Needs-your-yes counts for both, with the cost.
- [ ] 11.3 Stop and ask the user which decision points to use as references, the k value, the mode and the cost cap; run `--dry-run` with their choice first, then the run. Verify that the run output has the mockup's progress, fast-set and gate lines, that gate 1 and gate 2 print their commands, and that nothing live changed before the user's approval.
- [ ] 11.4 Report the dollar cost of the k=1 loop, the fast-set grades, and the user's gate decisions, and add a "Results" section to `design.md` with aggregate numbers only (no client names, no transcript text). Verify that the scans find nothing in `design.md`.
