# graph-memory-starter test report

Run 2026-09-28 22:02:33 on Windows 11 (10.0.26200), Python 3.12.7, SQLite 3.45.3, fastembed 0.8.1.
Code at commit `496a6e9`, plus uncommitted changes: `.gitignore`, `README.md`, `corpus/customer-support-sop.md`, `corpus/delegation-memo.md`, `corpus/refund-policy.md`, `digest/common.py`, `digest/config.json`, `digest/headless_run.py`, `digest/session_end.py`, `digest/session_start.py`, `extract-prompt.md`, `extraction/customer-support-sop.json`, `extraction/delegation-memo.json`, `extraction/incident-response.json`, `extraction/onboarding-process.json`, `extraction/org-chart.json`, `extraction/refund-policy.json`, `extraction/supplier-payments.json`, `extraction/tooling-inventory.json`, `hooks.json`, `rag/README.md`, `rag/hooks.json`, `rag/recall_hook.py`, `rag/search.py`, `src/build_graph.py`, `src/recall.py`, `src/recall_hook.py`, `src/schema.sql`, `Dockerfile`, `bench/`, `claude-md-snippet.md`, `codegraph/`, `commands/`, `corpus/refund-policy-2024.md`, `docker-compose.yml`, `docs/`, `extraction/refund-policy-2024.json`, `kl/`, `openspec/`, `projects/`, `rag/embedder.py`, `requirements-dev.txt`, `requirements-service.txt`, `src/tokens.py`, `tests/`.
Fresh start: `graph.db` and `rag/rag.db` were deleted before the run, and the run rebuilt them.

**23 passed · 0 warning · 0 failed · 1 not run · 137.7 s in total**

## Results

| # | Area | Check | Expected | Actual | Memory hits | Time in code | Wall time | Result | Log |
|---:|---|---|---|---|---|---:|---:|:---:|---|
| 1 | Install | Python version | 3.10 or newer | Python 3.12.7 | — | — | 13 ms | ✅ | L1 |
| 2 | Install | SQLite with full-text search | built into Python, FTS5 available | SQLite 3.45.3 with FTS5 | — | — | 45 ms | ✅ | L2 |
| 3 | Install | `pip install fastembed` | installs | already installed (0.8.1) | — | — | 1,799 ms | ✅ | L3 |
| 4 | Build | `python src/build_graph.py` | builds `graph.db`, no skipped links | 14 entities, 35 claims, 14 relations, 10 aliases from 9 docs | — | — | 340 ms | ✅ | L4 |
| 5 | Build | `python rag/build_index.py` | builds `rag.db` with the meaning search on | 12 files, 17 chunks, 3 distilled entries, 0 dropped; meaning search on (bge-small-en-v1.5, 384d) | — | — | 2,362 ms | ✅ | L5 |
| 6 | Unit test | Suite: `python -m unittest discover tests` | all pass | 307 run, OK | — | 118,588 ms | 123,560 ms | ✅ | L6 |
| 7 | Unit test | Refund in March, 3 steps | reaches Marcus Webb | ok | — | 4 ms | — | ✅ | L6 |
| 8 | Unit test | Supplier payments, 2 steps | reaches Alex Doyle | ok | — | 4 ms | — | ✅ | L6 |
| 9 | Unit test | Onboarding, 1 step | Ops Manager + Tooling inventory | ok | — | 3 ms | — | ✅ | L6 |
| 10 | Unit test | Priya, by short name | Support Lead | ok | — | 3 ms | — | ✅ | L6 |
| 11 | Unit test | Question outside the vocabulary | no matches | ok | — | 1 ms | — | ✅ | L6 |
| 12 | Graph | £800 refund in March | Marcus Webb, 3 steps | Refund approvals → Ops Manager → Sarah Chen → Marcus Webb | 8 facts | 8 ms | 101 ms | ✅ | L7 |
| 13 | Graph | Supplier payments over £2,000 | Alex Doyle, 2 steps | Supplier payments → Founder → Alex Doyle | 7 facts | 7 ms | 96 ms | ✅ | L8 |
| 14 | Graph | Onboarding process | Ops Manager, day-one checklist | Onboarding process → Ops Manager; Onboarding process → Tooling inventory | 7 facts | 7 ms | 115 ms | ✅ | L9 |
| 15 | Graph | What does Priya do? | Support Lead, found by short name | Support Lead → Priya Patel | 5 facts | 6 ms | 102 ms | ✅ | L10 |
| 16 | Graph | Boss is away | no memory matches, no guess | `(no memory matches for this prompt)` | 0 facts | 4 ms | 94 ms | ✅ | L11 |
| 17 | RAG | Mileage rate | `expenses.md` first, both searches | #1 expenses.md § Expenses (keyword+meaning)<br>#2 supplier-notes.md § Suppliers — working notes (meaning)<br>#3 brand-voice.md § Brand voice, one page (meaning) | 3 hits | — | 1,603 ms | ✅ | L12 |
| 18 | RAG | Talk to customers in writing | handbook § Tone of voice + `brand-voice.md`, via meaning | #1 customer-ops-handbook.md § Tone of voice (meaning)<br>#2 it-setup.md § New starter IT setup (keyword)<br>#3 brand-voice.md § Brand voice, one page (meaning) | 3 hits | — | 1,501 ms | ✅ | L13 |
| 19 | RAG | Sign-off while Sarah is away | distilled entry, then the memo | #1 ooo-march-sarah.md § distilled (keyword+meaning)<br>#2 ooo-march-sarah.md § ooo-march-sarah (keyword+meaning)<br>#3 team.md § Who's who (keyword+meaning) | 3 hits | — | 1,543 ms | ✅ | L14 |
| 20 | RAG | £800 refund in March | the £500 rule first | #1 customer-ops-handbook.md § distilled (keyword+meaning)<br>#2 newsletter-march-draft.md § March newsletter — draft 2 (keyword+meaning)<br>#3 customer-ops-handbook.md § Refunds and credits (keyword+meaning) | 3 hits | — | 1,476 ms | ✅ | L15 |
| 21 | Hook | Graph hook, refund prompt | facts sent to Claude, incl. Marcus Webb | shows `memory: 8 facts recalled in 7.2 ms, for March 2026`; sends 1,990 chars | 8 facts | 7 ms | 103 ms | ✅ | L16 |
| 22 | Hook | RAG hook, refund prompt | hits sent to Claude, incl. the £500 rule | shows `memory: 4 hits`; sends 1,306 chars | 4 hits | — | 1,444 ms | ✅ | L17 |
| 23 | Hook | Graph hook, question outside the graph | says no match, then labelled passages from the notes | shows `memory: 0 facts recalled in 3.6 ms, as of 2026-09-28; 3 passages from your notes` | — | — | 1,417 ms | ✅ | L18 |
| 24 | Digest | Session write-up | no test cases | not run: only runs when a real Claude Code session ends | — | — | — | — | — |

**Time in code** is what the code measured itself: the graph lookup's own timer, and unittest's timer for each test. **Wall time** is the whole process from start to exit, including Python starting up and, for RAG, loading the embedding model. It is what you would actually wait for.

## Summary

- Graph lookups took 3.6–8.0 ms inside the code and returned 0–8 facts each.
- RAG searches took 1.5–1.6 s of wall time each, most of it loading the embedding model; each returned its top 3 hits. They ran without the warm model (`python rag/embedder.py --start`, which the hooks start with a session), which brings a RAG hook to 0.1-0.2 s.
- The unit test suite ran in 118,588 ms inside unittest.

## How to re-run

```
python -m pip install fastembed
python src/build_graph.py
python rag/build_index.py
python -m unittest discover tests -v --durations 0
python src/recall.py "<question>"
python rag/search.py "<question>"
```

## Logs

### L1 · Python version

`python --version` · started 22:02:33.909 · exit 0 · 13 ms

stdout:

````text
Python 3.12.7
````

### L2 · SQLite with full-text search

`python -c "import sqlite3; db = sqlite3.connect(':memory:'); db.execute('CREATE VIRTUAL TABLE t USING fts5(x)'); print('SQLite', sqlite3.sqlite_version, 'with FTS5')"` · started 22:02:33.922 · exit 0 · 45 ms

stdout:

````text
SQLite 3.45.3 with FTS5
````

### L3 · Install fastembed

`python -m pip install fastembed` · started 22:02:33.966 · exit 0 · 1,799 ms

stdout:

````text
Requirement already satisfied: fastembed in c:\users\jdqsj\miniconda3\lib\site-packages (0.8.1)
Requirement already satisfied: huggingface-hub<2.0,>=0.20 in c:\users\jdqsj\miniconda3\lib\site-packages (from fastembed) (1.32.0)
Requirement already satisfied: loguru<0.8.0,>=0.7.2 in c:\users\jdqsj\miniconda3\lib\site-packages (from fastembed) (0.7.3)
Requirement already satisfied: mmh3<6.0.0,>=4.1.0 in c:\users\jdqsj\miniconda3\lib\site-packages (from fastembed) (5.3.0)
Requirement already satisfied: numpy>=1.26 in c:\users\jdqsj\miniconda3\lib\site-packages (from fastembed) (1.26.4)
Requirement already satisfied: onnxruntime!=1.20.0,!=1.24.0,!=1.24.1,>=1.17.0 in c:\users\jdqsj\miniconda3\lib\site-packages (from fastembed) (1.30.0)
Requirement already satisfied: pillow<13.0,>=10.3.0 in c:\users\jdqsj\miniconda3\lib\site-packages (from fastembed) (12.3.0)
Requirement already satisfied: py-rust-stemmers<0.2.0,>=0.1.0 in c:\users\jdqsj\miniconda3\lib\site-packages (from fastembed) (0.1.8)
Requirement already satisfied: requests<3.0,>=2.31 in c:\users\jdqsj\miniconda3\lib\site-packages (from fastembed) (2.32.4)
Requirement already satisfied: tokenizers<1.0,>=0.15 in c:\users\jdqsj\miniconda3\lib\site-packages (from fastembed) (0.23.2)
Requirement already satisfied: tqdm<5.0,>=4.66 in c:\users\jdqsj\miniconda3\lib\site-packages (from fastembed) (4.66.2)
Requirement already satisfied: click<9.0.0,>=8.4.2 in c:\users\jdqsj\miniconda3\lib\site-packages (from huggingface-hub<2.0,>=0.20->fastembed) (8.5.0)
Requirement already satisfied: filelock>=3.10.0 in c:\users\jdqsj\miniconda3\lib\site-packages (from huggingface-hub<2.0,>=0.20->fastembed) (3.16.1)
Requirement already satisfied: fsspec>=2023.5.0 in c:\users\jdqsj\miniconda3\lib\site-packages (from huggingface-hub<2.0,>=0.20->fastembed) (2024.12.0)
Requirement already satisfied: hf-xet<2.0.0,>=1.5.2 in c:\users\jdqsj\miniconda3\lib\site-packages (from huggingface-hub<2.0,>=0.20->fastembed) (1.6.0)
Requirement already satisfied: httpx<1,>=0.23.0 in c:\users\jdqsj\miniconda3\lib\site-packages (from huggingface-hub<2.0,>=0.20->fastembed) (0.28.1)
Requirement already satisfied: packaging>=20.9 in c:\users\jdqsj\miniconda3\lib\site-packages (from huggingface-hub<2.0,>=0.20->fastembed) (24.1)
Requirement already satisfied: pyyaml>=5.1 in c:\users\jdqsj\miniconda3\lib\site-packages (from huggingface-hub<2.0,>=0.20->fastembed) (6.0.3)
Requirement already satisfied: typing-extensions>=4.1.0 in c:\users\jdqsj\miniconda3\lib\site-packages (from huggingface-hub<2.0,>=0.20->fastembed) (4.12.2)
Requirement already satisfied: colorama>=0.3.4 in c:\users\jdqsj\miniconda3\lib\site-packages (from loguru<0.8.0,>=0.7.2->fastembed) (0.4.6)
Requirement already satisfied: win32-setctime>=1.0.0 in c:\users\jdqsj\miniconda3\lib\site-packages (from loguru<0.8.0,>=0.7.2->fastembed) (1.2.0)
Requirement already satisfied: flatbuffers in c:\users\jdqsj\miniconda3\lib\site-packages (from onnxruntime!=1.20.0,!=1.24.0,!=1.24.1,>=1.17.0->fastembed) (25.12.19)
Requirement already satisfied: protobuf>=4.25.8 in c:\users\jdqsj\miniconda3\lib\site-packages (from onnxruntime!=1.20.0,!=1.24.0,!=1.24.1,>=1.17.0->fastembed) (7.36.2)
Requirement already satisfied: charset_normalizer<4,>=2 in c:\users\jdqsj\miniconda3\lib\site-packages (from requests<3.0,>=2.31->fastembed) (3.3.2)
Requirement already satisfied: idna<4,>=2.5 in c:\users\jdqsj\miniconda3\lib\site-packages (from requests<3.0,>=2.31->fastembed) (3.7)
Requirement already satisfied: urllib3<3,>=1.21.1 in c:\users\jdqsj\miniconda3\lib\site-packages (from requests<3.0,>=2.31->fastembed) (2.2.3)
Requirement already satisfied: certifi>=2017.4.17 in c:\users\jdqsj\miniconda3\lib\site-packages (from requests<3.0,>=2.31->fastembed) (2024.8.30)
Requirement already satisfied: anyio in c:\users\jdqsj\miniconda3\lib\site-packages (from httpx<1,>=0.23.0->huggingface-hub<2.0,>=0.20->fastembed) (4.9.0)
Requirement already satisfied: httpcore==1.* in c:\users\jdqsj\miniconda3\lib\site-packages (from httpx<1,>=0.23.0->huggingface-hub<2.0,>=0.20->fastembed) (1.0.7)
Requirement already satisfied: h11<0.15,>=0.13 in c:\users\jdqsj\miniconda3\lib\site-packages (from httpcore==1.*->httpx<1,>=0.23.0->huggingface-hub<2.0,>=0.20->fastembed) (0.14.0)
Requirement already satisfied: sniffio>=1.1 in c:\users\jdqsj\miniconda3\lib\site-packages (from anyio->httpx<1,>=0.23.0->huggingface-hub<2.0,>=0.20->fastembed) (1.3.1)
````

### L4 · Build the graph

`python src/build_graph.py` · started 22:02:35.766 · exit 0 · 340 ms

stdout:

````text
built graph.db: 14 entities, 35 claims, 14 relations, 10 aliases from 9 docs
````

### L5 · Build the RAG index

`python rag/build_index.py` · started 22:02:36.106 · exit 0 · 2,362 ms

stdout:

````text
indexed 12 files, 17 chunks, 3 distilled entries, 0 dropped
model BAAI/bge-small-en-v1.5 (384d) + keyword sqlite fts5
````

### L6 · Unit tests

`python -m unittest discover tests -v --durations 0` · started 22:02:38.468 · exit 0 · 123,560 ms

stderr:

````text
test_a_date_that_is_not_a_date_stops_the_build (test_build.Build.test_a_date_that_is_not_a_date_stops_the_build) ... ok
test_an_older_extraction_description_becomes_a_note (test_build.Build.test_an_older_extraction_description_becomes_a_note) ... ok
test_counts (test_build.Build.test_counts) ... ok
test_dated_versions_of_a_policy_coexist (test_build.Build.test_dated_versions_of_a_policy_coexist) ... ok
test_dates_the_wrong_way_round_stop_the_build (test_build.Build.test_dates_the_wrong_way_round_stop_the_build) ... ok
test_every_docs_claims_are_kept (test_build.Build.test_every_docs_claims_are_kept) ... ok
test_foreign_keys_hold (test_build.Build.test_foreign_keys_hold) ... ok
test_links_carry_their_dates (test_build.Build.test_links_carry_their_dates) ... ok
test_name_with_two_types_stops_the_build (test_build.Build.test_name_with_two_types_stops_the_build) ... ok
test_names_are_split_like_questions (test_build.Build.test_names_are_split_like_questions) ... ok
test_same_input_same_db (test_build.Build.test_same_input_same_db) ... ok
test_the_repo_extraction_is_consistent (test_build.Build.test_the_repo_extraction_is_consistent) ... ok
test_two_thresholds_in_force_at_once_stop_the_build (test_build.Build.test_two_thresholds_in_force_at_once_stop_the_build) ... ok
test_unknown_claim_kind_stops_the_build (test_build.Build.test_unknown_claim_kind_stops_the_build) ... ok
test_a_document_graph_without_code_has_no_code_in_its_answers (test_code.Answers.test_a_document_graph_without_code_has_no_code_in_its_answers) ... ok
test_every_case (test_code.Answers.test_every_case) ... ok
test_one_name_in_any_style_names_one_symbol (test_code.Answers.test_one_name_in_any_style_names_one_symbol) ... ok
test_the_hook_sends_the_trace (test_code.Answers.test_the_hook_sends_the_trace) ... ok
test_the_provenance_counts_the_code (test_code.Answers.test_the_provenance_counts_the_code) ... ok
test_the_trace_follows_past_three_hops (test_code.Answers.test_the_trace_follows_past_three_hops) ... ok
test_a_handler_change_shows_the_bodies_its_clients_send (test_code.Dependents.test_a_handler_change_shows_the_bodies_its_clients_send) ... ok
test_every_predicate_the_index_writes_is_followed (test_code.Dependents.test_every_predicate_the_index_writes_is_followed) ... ok
test_every_symbol_asked_about_a_change_brings_every_dependent (test_code.Dependents.test_every_symbol_asked_about_a_change_brings_every_dependent) ... ok
test_every_wording_of_a_change_brings_both_directions (test_code.Dependents.test_every_wording_of_a_change_brings_both_directions) ... ok
test_space_runs_out_on_call_sites_and_never_on_dependents (test_code.Dependents.test_space_runs_out_on_call_sites_and_never_on_dependents) ... ok
test_the_trace_is_the_same_whatever_the_wording (test_code.Dependents.test_the_trace_is_the_same_whatever_the_wording) ... ok
test_every_caller_and_every_call_is_there (test_code.FanIn.test_every_caller_and_every_call_is_there) ... ok
test_a_call_site_changed_after_indexing_is_said_to_have_changed (test_code.Freshness.test_a_call_site_changed_after_indexing_is_said_to_have_changed) ... ok
test_a_code_line_changed_after_indexing_is_said_to_have_changed (test_code.Freshness.test_a_code_line_changed_after_indexing_is_said_to_have_changed) ... ok
test_the_build_refuses_a_call_site_the_code_lacks (test_code.Freshness.test_the_build_refuses_a_call_site_the_code_lacks) ... ok
test_the_build_refuses_an_index_whose_quotes_the_code_lacks (test_code.Freshness.test_the_build_refuses_an_index_whose_quotes_the_code_lacks) ... ok
test_a_chain_of_calls_to_a_constant (test_code.Index.test_a_chain_of_calls_to_a_constant) ... ok
test_a_function_passed_and_not_called_is_referenced (test_code.Index.test_a_function_passed_and_not_called_is_referenced) ... ok
test_a_literal_body_in_the_fetch_picks_the_case (test_code.Index.test_a_literal_body_in_the_fetch_picks_the_case) ... ok
test_a_lookup_table_gives_one_case_per_entry (test_code.Index.test_a_lookup_table_gives_one_case_per_entry) ... ok
test_a_url_built_from_constants_in_two_files (test_code.Index.test_a_url_built_from_constants_in_two_files) ... ok
test_a_value_in_the_body_picks_the_branch (test_code.Index.test_a_value_in_the_body_picks_the_branch) ... ok
test_an_explicit_route_matched_across_parameter_syntaxes (test_code.Index.test_an_explicit_route_matched_across_parameter_syntaxes) ... ok
test_an_import_through_a_package_is_followed_to_the_definition (test_code.Index.test_an_import_through_a_package_is_followed_to_the_definition) ... ok
test_buttons_own_what_their_onclick_runs (test_code.Index.test_buttons_own_what_their_onclick_runs) ... ok
test_every_claim_quotes_a_line_of_its_file (test_code.Index.test_every_claim_quotes_a_line_of_its_file) ... ok
test_every_site_quotes_its_line (test_code.Index.test_every_site_quotes_its_line) ... ok
test_nothing_reaches_the_legacy_refund (test_code.Index.test_nothing_reaches_the_legacy_refund) ... ok
test_tests_are_their_own_kind_and_call_what_they_test (test_code.Index.test_tests_are_their_own_kind_and_call_what_they_test) ... ok
test_the_body_fields_sent_and_read (test_code.Index.test_the_body_fields_sent_and_read) ... ok
test_the_import_decides_which_validate (test_code.Index.test_the_import_decides_which_validate) ... ok
test_what_it_finds (test_code.Index.test_what_it_finds) ... ok
test_a_run_of_capitals_is_one_word (test_code.Tokens.test_a_run_of_capitals_is_one_word) ... ok
test_any_alphabet (test_code.Tokens.test_any_alphabet) ... ok
test_digits_stay_with_the_letters_before_them (test_code.Tokens.test_digits_stay_with_the_letters_before_them) ... ok
test_every_naming_style_comes_apart_at_the_same_seams (test_code.Tokens.test_every_naming_style_comes_apart_at_the_same_seams) ... ok
test_prose_is_unchanged (test_code.Tokens.test_prose_is_unchanged) ... ok
test_300_refund_in_june_2025_needed_a_director (test_dates.ExampleQuestions.test_300_refund_in_june_2025_needed_a_director) ... ok
test_300_refund_today_any_agent (test_dates.ExampleQuestions.test_300_refund_today_any_agent) ... ok
test_800_refund_in_april_goes_to_sarah (test_dates.ExampleQuestions.test_800_refund_in_april_goes_to_sarah) ... ok
test_800_refund_in_march_goes_to_marcus (test_dates.ExampleQuestions.test_800_refund_in_march_goes_to_marcus) ... ok
test_cover_on_a_given_day (test_dates.ExampleQuestions.test_cover_on_a_given_day) ... ok
test_threshold_history_shows_both_versions_with_dates (test_dates.ExampleQuestions.test_threshold_history_shows_both_versions_with_dates) ... ok
test_threshold_in_2025 (test_dates.ExampleQuestions.test_threshold_in_2025) ... ok
test_undated_facts_hold_at_any_date (test_dates.ExampleQuestions.test_undated_facts_hold_at_any_date) ... ok
test_a_history_question_spans_all_dates (test_dates.Period.test_a_history_question_spans_all_dates) ... ok
test_a_month_without_a_year_is_this_year (test_dates.Period.test_a_month_without_a_year_is_this_year) ... ok
test_a_year (test_dates.Period.test_a_year) ... ok
test_days (test_dates.Period.test_days) ... ok
test_month_and_year (test_dates.Period.test_month_and_year) ... ok
test_no_date_means_today (test_dates.Period.test_no_date_means_today) ... ok
test_open_ended (test_dates.Period.test_open_ended) ... ok
test_words_that_only_look_like_dates (test_dates.Period.test_words_that_only_look_like_dates) ... ok
test_no_embedder_means_no_vectors (test_embedder.NotRunning.test_no_embedder_means_no_vectors) ... ok
test_no_index_means_no_start (test_embedder.NotRunning.test_no_index_means_no_start) ... ok
test_a_request_without_the_key_gets_nothing (test_embedder.Warm.test_a_request_without_the_key_gets_nothing) ... ok
test_same_vectors_as_loading_the_model (test_embedder.Warm.test_same_vectors_as_loading_the_model) ... ok
test_changed_file (test_excerpts.ChangedDocuments.test_changed_file) ... ok
test_missing_file (test_excerpts.ChangedDocuments.test_missing_file) ... ok
test_unchanged (test_excerpts.ChangedDocuments.test_unchanged) ... ok
test_a_role_nobody_holds_is_a_gap (test_excerpts.Coverage.test_a_role_nobody_holds_is_a_gap) ... ok
test_the_repo_graph_has_no_gaps (test_excerpts.Coverage.test_the_repo_graph_has_no_gaps) ... ok
test_a_conversation_sees_each_quote_once_until_it_is_compacted (test_excerpts.HookSessions.test_a_conversation_sees_each_quote_once_until_it_is_compacted) ... ok
test_sessions_do_not_share (test_excerpts.HookSessions.test_sessions_do_not_share) ... ok
test_a_paraphrase_is_refused (test_excerpts.QuotesAtBuild.test_a_paraphrase_is_refused) ... ok
test_a_quote_from_a_missing_document_is_refused (test_excerpts.QuotesAtBuild.test_a_quote_from_a_missing_document_is_refused) ... ok
test_a_quote_too_long_is_refused (test_excerpts.QuotesAtBuild.test_a_quote_too_long_is_refused) ... ok
test_markdown_and_spacing_do_not_count (test_excerpts.QuotesAtBuild.test_markdown_and_spacing_do_not_count) ... ok
test_an_unknown_keeps_its_own_words (test_excerpts.QuotesAtRecall.test_an_unknown_keeps_its_own_words) ... ok
test_provenance_line_tells_the_model_how_to_use_the_facts (test_excerpts.QuotesAtRecall.test_provenance_line_tells_the_model_how_to_use_the_facts) ... ok
test_quotes_already_sent_are_not_repeated (test_excerpts.QuotesAtRecall.test_quotes_already_sent_are_not_repeated) ... ok
test_quotes_stay_within_the_budget (test_excerpts.QuotesAtRecall.test_quotes_stay_within_the_budget) ... ok
test_the_answer_comes_with_its_sources (test_excerpts.QuotesAtRecall.test_the_answer_comes_with_its_sources) ... ok
test_the_model_is_not_told_the_timing (test_excerpts.QuotesAtRecall.test_the_model_is_not_told_the_timing) ... ok
test_what_the_documents_leave_open_is_said (test_excerpts.QuotesAtRecall.test_what_the_documents_leave_open_is_said) ... ok
test_a_graph_answer_brings_no_passages (test_fallback.Fallback.test_a_graph_answer_brings_no_passages) ... ok
test_no_names_brings_labelled_passages (test_fallback.Fallback.test_no_names_brings_labelled_passages) ... ok
test_passages_stay_within_the_budget (test_fallback.Fallback.test_passages_stay_within_the_budget) ... ok
test_without_an_index_the_loud_line_stays_alone (test_fallback.Fallback.test_without_an_index_the_loud_line_stays_alone) ... ok
test_claims_stay_on_topic (test_graph.GraphTestCases.test_claims_stay_on_topic) ... ok
test_compact_format_for_the_model (test_graph.GraphTestCases.test_compact_format_for_the_model) ... ok
test_conditions_travel_with_the_facts_as_claims (test_graph.GraphTestCases.test_conditions_travel_with_the_facts_as_claims) ... ok
test_injection_is_capped_at_eight_facts (test_graph.GraphTestCases.test_injection_is_capped_at_eight_facts) ... ok
test_onboarding_is_one_hop_several_edges (test_graph.GraphTestCases.test_onboarding_is_one_hop_several_edges) ... ok
test_outside_the_vocabulary_fails_loudly (test_graph.GraphTestCases.test_outside_the_vocabulary_fails_loudly) ... ok
test_pretty_format_for_people (test_graph.GraphTestCases.test_pretty_format_for_people) ... ok
test_priya_is_seeded_by_alias (test_graph.GraphTestCases.test_priya_is_seeded_by_alias) ... ok
test_refund_in_march_walks_three_hops_to_marcus (test_graph.GraphTestCases.test_refund_in_march_walks_three_hops_to_marcus) ... ok
test_same_question_same_facts (test_graph.GraphTestCases.test_same_question_same_facts) ... ok
test_supplier_payments_walk_two_hops_to_alex (test_graph.GraphTestCases.test_supplier_payments_walk_two_hops_to_alex) ... ok
test_graph_from_an_older_version_says_rebuild (test_graph.NoUsableGraph.test_graph_from_an_older_version_says_rebuild) ... ok
test_missing_graph_says_how_to_build_it (test_graph.NoUsableGraph.test_missing_graph_says_how_to_build_it) ... ok
test_answer_survives (test_growth.Busy100.test_answer_survives) ... ok
test_answer_survives (test_growth.Busy1000.test_answer_survives) ... ok
test_answer_survives_within_budget (test_growth.Busy10000.test_answer_survives_within_budget) ... ok
test_answer_survives (test_growth.BusyBare10000.test_answer_survives) ... ok
test_answer_survives_and_names_are_fast (test_growth.Elsewhere10000.test_answer_survives_and_names_are_fast) ... ok
test_in_time_says_nothing (test_growth.TimeBudget.test_in_time_says_nothing) ... ok
test_out_of_time_says_so (test_growth.TimeBudget.test_out_of_time_says_so) ... ok
test_transcript_path_arrives_intact (test_hooks.DigestHook.test_transcript_path_arrives_intact) ... ok
test_no_match_still_answers (test_hooks.GraphHook.test_no_match_still_answers) ... ok
test_non_ascii_name_is_found (test_hooks.GraphHook.test_non_ascii_name_is_found) ... ok
test_output_is_what_claude_code_reads (test_hooks.GraphHook.test_output_is_what_claude_code_reads) ... ok
test_prompt_arrives_intact (test_hooks.RagHook.test_prompt_arrives_intact) ... ok
test_a_person_says_which_workspace (test_kl_auth_events.Auth.test_a_person_says_which_workspace) ... ok
test_a_person_signs_in_with_the_issuers_token_once_an_admin_has_added_them (test_kl_auth_events.Auth.test_a_person_signs_in_with_the_issuers_token_once_an_admin_has_added_them) ... ok
test_a_revoked_key_stops_working (test_kl_auth_events.Auth.test_a_revoked_key_stops_working) ... ok
test_a_token_for_another_audience_or_expired_or_forged_is_refused (test_kl_auth_events.Auth.test_a_token_for_another_audience_or_expired_or_forged_is_refused) ... ok
test_errors_are_problems (test_kl_auth_events.Auth.test_errors_are_problems) ... ok
test_only_the_root_key_creates_workspaces (test_kl_auth_events.Auth.test_only_the_root_key_creates_workspaces) ... ok
test_roles_decide_what_a_person_may_do (test_kl_auth_events.Auth.test_roles_decide_what_a_person_may_do) ... ok
test_a_long_poll_returns_as_soon_as_something_happens (test_kl_auth_events.Events.test_a_long_poll_returns_as_soon_as_something_happens) ... ok
test_events_come_in_order_by_cursor_and_type (test_kl_auth_events.Events.test_events_come_in_order_by_cursor_and_type) ... ok
test_the_stream_sends_server_sent_events (test_kl_auth_events.Events.test_the_stream_sends_server_sent_events) ... ok
test_webhooks_are_signed_and_retried_in_order_until_delivered (test_kl_auth_events.Events.test_webhooks_are_signed_and_retried_in_order_until_delivered) ... ok
test_a_manifest_says_what_to_upload_and_what_to_retract (test_kl_ingest.Dedup.test_a_manifest_says_what_to_upload_and_what_to_retract) ... ok
test_a_near_copy_can_be_sent_to_a_person (test_kl_ingest.Dedup.test_a_near_copy_can_be_sent_to_a_person) ... ok
test_a_near_copy_is_linked_and_left_out (test_kl_ingest.Dedup.test_a_near_copy_is_linked_and_left_out) ... ok
test_a_new_version_replaces_the_old_ones_facts (test_kl_ingest.Dedup.test_a_new_version_replaces_the_old_ones_facts) ... ok
test_a_pdf_needs_its_text (test_kl_ingest.Dedup.test_a_pdf_needs_its_text) ... ok
test_a_renamed_copy_is_another_location_of_the_same_version (test_kl_ingest.Dedup.test_a_renamed_copy_is_another_location_of_the_same_version) ... ok
test_a_short_file_with_a_word_changed_is_not_a_near_copy (test_kl_ingest.Dedup.test_a_short_file_with_a_word_changed_is_not_a_near_copy) ... ok
test_a_transcript_becomes_a_change_request_quoting_it (test_kl_ingest.Dedup.test_a_transcript_becomes_a_change_request_quoting_it) ... ok
test_an_extraction_that_misquotes_is_refused (test_kl_ingest.Dedup.test_an_extraction_that_misquotes_is_refused) ... ok
test_retracting_a_source_takes_its_facts_out_and_restoring_brings_them_back (test_kl_ingest.Dedup.test_retracting_a_source_takes_its_facts_out_and_restoring_brings_them_back) ... ok
test_the_same_fact_from_two_files_is_one_claim_with_two_sources (test_kl_ingest.Dedup.test_the_same_fact_from_two_files_is_one_claim_with_two_sources) ... ok
test_the_same_file_twice_is_unchanged (test_kl_ingest.Dedup.test_the_same_file_twice_is_unchanged) ... ok
test_the_same_text_with_other_line_endings_is_the_same_text (test_kl_ingest.Dedup.test_the_same_text_with_other_line_endings_is_the_same_text) ... ok
test_the_storage_limit_holds (test_kl_ingest.Dedup.test_the_storage_limit_holds) ... ok
test_two_files_that_disagree_go_to_a_person (test_kl_ingest.Dedup.test_two_files_that_disagree_go_to_a_person) ... ok
test_without_an_extractor_a_document_waits_for_its_extraction (test_kl_ingest.Dedup.test_without_an_extractor_a_document_waits_for_its_extraction) ... ok
test_an_mcp_agent_works_a_task_through_the_tools (test_kl_live_server.LiveServer.test_an_mcp_agent_works_a_task_through_the_tools) ... ok
test_mcp_with_an_api_key_reads_and_proposes (test_kl_live_server.LiveServer.test_mcp_with_an_api_key_reads_and_proposes) ... ok
test_the_hook_asks_the_service_and_falls_back_when_it_is_down (test_kl_live_server.LiveServer.test_the_hook_asks_the_service_and_falls_back_when_it_is_down) ... ok
test_the_orchestrator_runs_a_plan_on_machines_that_start_slower_than_a_lease (test_kl_live_server.LiveServer.test_the_orchestrator_runs_a_plan_on_machines_that_start_slower_than_a_lease) ... ok
test_a_code_change_says_which_requirements_are_at_stake (test_kl_openspec.OpenSpecInTheGraph.test_a_code_change_says_which_requirements_are_at_stake) ... ok
test_a_modified_requirement_ends_the_old_claim_the_day_its_change_was_archived (test_kl_openspec.OpenSpecInTheGraph.test_a_modified_requirement_ends_the_old_claim_the_day_its_change_was_archived) ... ok
test_a_removed_requirement_ends_that_day (test_kl_openspec.OpenSpecInTheGraph.test_a_removed_requirement_ends_that_day) ... ok
test_a_test_that_names_a_scenario_verifies_it (test_kl_openspec.OpenSpecInTheGraph.test_a_test_that_names_a_scenario_verifies_it) ... ok
test_an_open_change_is_not_a_fact (test_kl_openspec.OpenSpecInTheGraph.test_an_open_change_is_not_a_fact) ... ok
test_context_answers_as_of_a_date (test_kl_openspec.OpenSpecInTheGraph.test_context_answers_as_of_a_date) ... ok
test_the_code_zip_is_indexed_and_its_specs_read (test_kl_openspec.OpenSpecInTheGraph.test_the_code_zip_is_indexed_and_its_specs_read) ... ok
test_the_parser_checks_the_format (test_kl_openspec.OpenSpecInTheGraph.test_the_parser_checks_the_format) ... ok
test_a_claims_id_is_the_same_in_every_build (test_kl_projection.Projection.test_a_claims_id_is_the_same_in_every_build) ... ok
test_a_graph_file_is_never_replaced_under_a_reader (test_kl_projection.Projection.test_a_graph_file_is_never_replaced_under_a_reader) ... ok
test_a_new_version_rewrites_only_its_own_files (test_kl_projection.Projection.test_a_new_version_rewrites_only_its_own_files) ... ok
test_any_sequence_of_changes_gives_the_graph_a_full_build_gives (test_kl_projection.Projection.test_any_sequence_of_changes_gives_the_graph_a_full_build_gives) ... ok
test_code_questions (test_kl_projection.SameAnswers.test_code_questions) ... ok
test_document_questions (test_kl_projection.SameAnswers.test_document_questions) ... ok
test_each_fact_names_its_claim_by_content (test_kl_projection.SameAnswers.test_each_fact_names_its_claim_by_content) ... ok
test_each_case_as_a_change_request (test_kl_review.Cases.test_each_case_as_a_change_request) ... ok
test_a_dry_run_shows_the_diff_and_opens_nothing (test_kl_review.Review.test_a_dry_run_shows_the_diff_and_opens_nothing) ... ok
test_a_move_the_rules_forbid_is_refused_before_anyone_is_asked (test_kl_review.Review.test_a_move_the_rules_forbid_is_refused_before_anyone_is_asked) ... ok
test_a_proposer_may_approve_their_own_request_and_one_approval_is_enough (test_kl_review.Review.test_a_proposer_may_approve_their_own_request_and_one_approval_is_enough) ... ok
test_a_rejection_keeps_its_reason (test_kl_review.Review.test_a_rejection_keeps_its_reason) ... ok
test_a_request_another_approval_made_stale_is_caught (test_kl_review.Review.test_a_request_another_approval_made_stale_is_caught) ... ok
test_approve_true_proposes_and_approves_in_one_call_and_records_both (test_kl_review.Review.test_approve_true_proposes_and_approves_in_one_call_and_records_both) ... ok
test_approving_an_edited_version_records_the_edit (test_kl_review.Review.test_approving_an_edited_version_records_the_edit) ... ok
test_approving_some_operations (test_kl_review.Review.test_approving_some_operations) ... ok
test_every_decision_is_in_the_projects_history (test_kl_review.Review.test_every_decision_is_in_the_projects_history) ... ok
test_if_match_refuses_an_edit_based_on_an_old_version (test_kl_review.Review.test_if_match_refuses_an_edit_based_on_an_old_version) ... ok
test_nothing_applies_until_a_person_approves (test_kl_review.Review.test_nothing_applies_until_a_person_approves) ... ok
test_service_accounts_editors_and_runs_never_approve (test_kl_review.Review.test_service_accounts_editors_and_runs_never_approve) ... ok
test_soft_delete_leaves_recall_and_the_list_and_restore_brings_it_back (test_kl_review.Review.test_soft_delete_leaves_recall_and_the_list_and_restore_brings_it_back) ... ok
test_the_workspace_can_turn_self_approval_off (test_kl_review.Review.test_the_workspace_can_turn_self_approval_off) ... ok
test_a_plan_that_cannot_run_is_refused_with_its_reasons (test_kl_runs.Plans.test_a_plan_that_cannot_run_is_refused_with_its_reasons) ... ok
test_an_approved_plan_is_mirrored_into_the_projects_steps (test_kl_runs.Plans.test_an_approved_plan_is_mirrored_into_the_projects_steps) ... ok
test_an_openspec_change_becomes_a_task_graph (test_kl_runs.Plans.test_an_openspec_change_becomes_a_task_graph) ... ok
test_an_openspec_change_that_breaks_the_format_is_refused (test_kl_runs.Plans.test_an_openspec_change_that_breaks_the_format_is_refused) ... ok
test_sections_can_run_side_by_side_within_themselves (test_kl_runs.Plans.test_sections_can_run_side_by_side_within_themselves) ... ok
test_a_failed_attempt_is_retried_until_its_retries_run_out (test_kl_runs.Runs.test_a_failed_attempt_is_retried_until_its_retries_run_out) ... ok
test_a_lease_nobody_renews_expires_and_its_token_with_it (test_kl_runs.Runs.test_a_lease_nobody_renews_expires_and_its_token_with_it) ... ok
test_a_new_plan_version_holds_only_the_tasks_it_changes (test_kl_runs.Runs.test_a_new_plan_version_holds_only_the_tasks_it_changes) ... ok
test_a_question_to_a_person_pauses_the_lease (test_kl_runs.Runs.test_a_question_to_a_person_pauses_the_lease) ... ok
test_a_run_token_works_only_for_its_own_run (test_kl_runs.Runs.test_a_run_token_works_only_for_its_own_run) ... ok
test_a_runner_without_what_the_task_needs_is_refused (test_kl_runs.Runs.test_a_runner_without_what_the_task_needs_is_refused) ... ok
test_a_task_marked_for_a_person_waits_for_one (test_kl_runs.Runs.test_a_task_marked_for_a_person_waits_for_one) ... ok
test_an_agent_proposes_and_a_person_decides (test_kl_runs.Runs.test_an_agent_proposes_and_a_person_decides) ... ok
test_an_openspec_deliverable_is_accepted_with_what_to_archive (test_kl_runs.Runs.test_an_openspec_deliverable_is_accepted_with_what_to_archive) ... ok
test_completing_twice_with_the_same_key_gives_the_same_answer (test_kl_runs.Runs.test_completing_twice_with_the_same_key_gives_the_same_answer) ... ok
test_renewals_while_the_machine_starts_keep_the_token_valid_past_its_first_lease (test_kl_runs.Runs.test_renewals_while_the_machine_starts_keep_the_token_valid_past_its_first_lease) ... ok
test_the_happy_path (test_kl_runs.Runs.test_the_happy_path) ... ok
test_the_token_is_kept_only_as_a_hash_and_never_lands_in_an_artifact (test_kl_runs.Runs.test_the_token_is_kept_only_as_a_hash_and_never_lands_in_an_artifact) ... ok
test_the_workspace_limits_runs_at_once (test_kl_runs.Runs.test_the_workspace_limits_runs_at_once) ... ok
test_every_scenario_is_verified_by_its_test (test_kl_specs.ServiceSpecs.test_every_scenario_is_verified_by_its_test) ... ok
test_the_specs_are_in_the_format (test_kl_specs.ServiceSpecs.test_the_specs_are_in_the_format) ... ok
test_every_table_but_two_carries_its_workspace (test_kl_store.Backends.test_every_table_but_two_carries_its_workspace) ... ok
test_one_workspace_never_sees_another (test_kl_store.Backends.test_one_workspace_never_sees_another) ... ok
test_the_answer_is_the_one_recall_gives_in_process (test_kl_store.Backends.test_the_answer_is_the_one_recall_gives_in_process) ... ok
test_every_table_but_two_carries_its_workspace (test_kl_store.Postgres.test_every_table_but_two_carries_its_workspace) ... ok
test_one_workspace_never_sees_another (test_kl_store.Postgres.test_one_workspace_never_sees_another) ... ok
test_postgres_and_sqlite_give_the_same_context (test_kl_store.Postgres.test_postgres_and_sqlite_give_the_same_context) ... ok
test_row_security_hides_other_workspaces_even_without_a_filter (test_kl_store.Postgres.test_row_security_hides_other_workspaces_even_without_a_filter) ... ok
test_row_security_refuses_writes_for_another_workspace (test_kl_store.Postgres.test_row_security_refuses_writes_for_another_workspace) ... ok
test_the_answer_is_the_one_recall_gives_in_process (test_kl_store.Postgres.test_the_answer_is_the_one_recall_gives_in_process) ... ok
test_the_app_role_is_not_a_superuser (test_kl_store.Postgres.test_the_app_role_is_not_a_superuser) ... ok
test_a_new_project_is_found_short_of_owner_date_and_plan (test_project_cases.Cases.test_a_new_project_is_found_short_of_owner_date_and_plan) ... ok
test_apply_leaves_the_records_it_was_given_alone (test_project_cases.Cases.test_apply_leaves_the_records_it_was_given_alone) ... ok
test_applying_it_gives_the_stored_result (test_project_cases.Cases.test_applying_it_gives_the_stored_result) ... ok
test_each_expected_change_set_is_valid (test_project_cases.Cases.test_each_expected_change_set_is_valid) ... ok
test_each_input_is_recorded_once_per_project_with_what_it_was_used_for (test_project_cases.Cases.test_each_input_is_recorded_once_per_project_with_what_it_was_used_for) ... ok
test_every_quote_in_every_record_is_in_its_input (test_project_cases.Cases.test_every_quote_in_every_record_is_in_its_input) ... ok
test_the_cases_follow_on_from_each_other (test_project_cases.Cases.test_the_cases_follow_on_from_each_other) ... ok
test_the_hash_ignores_line_endings (test_project_cases.Cases.test_the_hash_ignores_line_endings) ... ok
test_the_result_meets_the_case_expectations (test_project_cases.Cases.test_the_result_meets_the_case_expectations) ... ok
test_there_are_seven (test_project_cases.Cases.test_there_are_seven) ... ok
test_a_day_said_relative_to_the_input (test_project_cases.Dates.test_a_day_said_relative_to_the_input) ... ok
test_near_misses_are_not_dates (test_project_cases.Dates.test_near_misses_are_not_dates) ... ok
test_the_forms_a_date_is_said_in (test_project_cases.Dates.test_the_forms_a_date_is_said_in) ... ok
test_the_inputs_own_date_needs_no_saying (test_project_cases.Dates.test_the_inputs_own_date_needs_no_saying) ... ok
test_a_status_without_from_holds_from_the_inputs_date (test_project_cases.Defaults.test_a_status_without_from_holds_from_the_inputs_date) ... ok
test_a_step_can_move_its_due_date_alone (test_project_cases.Defaults.test_a_step_can_move_its_due_date_alone) ... ok
test_a_fenced_reply_parses (test_project_cases.Ingest.test_a_fenced_reply_parses) ... ok
test_a_good_answer_is_not_sent_back (test_project_cases.Ingest.test_a_good_answer_is_not_sent_back) ... ok
test_a_new_projects_id_may_be_written_id (test_project_cases.Ingest.test_a_new_projects_id_may_be_written_id) ... ok
test_a_refused_answer_is_sent_back_once_with_the_problems (test_project_cases.Ingest.test_a_refused_answer_is_sent_back_once_with_the_problems) ... ok
test_a_reply_without_changes_is_an_error (test_project_cases.Ingest.test_a_reply_without_changes_is_an_error) ... ok
test_propose_wraps_the_reply_with_the_input (test_project_cases.Ingest.test_propose_wraps_the_reply_with_the_input) ... ok
test_short_names_are_written_out (test_project_cases.Ingest.test_short_names_are_written_out) ... ok
test_the_date_comes_from_the_file_name (test_project_cases.Ingest.test_the_date_comes_from_the_file_name) ... ok
test_a_date_the_input_does_not_state (test_project_cases.Refused.test_a_date_the_input_does_not_state) ... ok
test_a_deadline_in_words_is_not_a_date (test_project_cases.Refused.test_a_deadline_in_words_is_not_a_date) ... ok
test_a_dependency_cycle (test_project_cases.Refused.test_a_dependency_cycle) ... ok
test_a_later_change_is_still_checked_after_a_bad_one (test_project_cases.Refused.test_a_later_change_is_still_checked_after_a_bad_one) ... ok
test_a_new_project_starting_active (test_project_cases.Refused.test_a_new_project_starting_active) ... ok
test_a_paraphrased_quote (test_project_cases.Refused.test_a_paraphrased_quote) ... ok
test_a_person_the_graph_does_not_know (test_project_cases.Refused.test_a_person_the_graph_does_not_know) ... ok
test_a_project_that_does_not_exist (test_project_cases.Refused.test_a_project_that_does_not_exist) ... ok
test_a_quote_over_300_characters (test_project_cases.Refused.test_a_quote_over_300_characters) ... ok
test_a_short_name_where_the_full_one_is_needed (test_project_cases.Refused.test_a_short_name_where_the_full_one_is_needed) ... ok
test_a_status_move_the_table_does_not_allow (test_project_cases.Refused.test_a_status_move_the_table_does_not_allow) ... ok
test_a_step_change_with_neither_status_nor_due (test_project_cases.Refused.test_a_step_change_with_neither_status_nor_due) ... ok
test_a_step_the_plan_does_not_have (test_project_cases.Refused.test_a_step_the_plan_does_not_have) ... ok
test_answering_a_question_twice (test_project_cases.Refused.test_answering_a_question_twice) ... ok
test_changing_an_owner_already_set_needs_you (test_project_cases.Refused.test_changing_an_owner_already_set_needs_you) ... ok
test_creating_a_project_twice (test_project_cases.Refused.test_creating_a_project_twice) ... ok
test_done_is_not_refused_but_needs_you (test_project_cases.Refused.test_done_is_not_refused_but_needs_you) ... ok
test_going_active_without_an_agreed_plan (test_project_cases.Refused.test_going_active_without_an_agreed_plan) ... ok
test_moving_a_step_with_no_agreed_plan (test_project_cases.Refused.test_moving_a_step_with_no_agreed_plan) ... ok
test_restating_a_recorded_due_date_is_not_refused (test_project_cases.Refused.test_restating_a_recorded_due_date_is_not_refused) ... ok
test_writing_a_plan_from_a_meeting (test_project_cases.Refused.test_writing_a_plan_from_a_meeting) ... ok
test_a_past_date_gets_that_days_status_and_nothing_learnt_later (test_projects.Answers.test_a_past_date_gets_that_days_status_and_nothing_learnt_later) ... ok
test_a_project_name_wins_over_an_alias_inside_it (test_projects.Answers.test_a_project_name_wins_over_an_alias_inside_it) ... ok
test_a_question_about_projects_that_names_none (test_projects.Answers.test_a_question_about_projects_that_names_none) ... ok
test_deliverables_are_left_out_unless_asked_for (test_projects.Answers.test_deliverables_are_left_out_unless_asked_for) ... ok
test_document_questions_are_answered_as_before (test_projects.Answers.test_document_questions_are_answered_as_before) ... ok
test_quick_enough_for_the_hook (test_projects.Answers.test_quick_enough_for_the_hook) ... ok
test_the_hook_answers_a_projects_question_without_falling_back_to_notes (test_projects.Answers.test_the_hook_answers_a_projects_question_without_falling_back_to_notes) ... ok
test_the_sign_off_is_walked_from_the_project_to_the_person (test_projects.Answers.test_the_sign_off_is_walked_from_the_project_to_the_person) ... ok
test_the_status_comes_first_with_why_and_the_plan_in_a_line (test_projects.Answers.test_the_status_comes_first_with_why_and_the_plan_in_a_line) ... ok
test_the_whole_plan_when_asked_for (test_projects.Answers.test_the_whole_plan_when_asked_for) ... ok
test_what_a_person_is_working_on (test_projects.Answers.test_what_a_person_is_working_on) ... ok
test_what_changed_is_the_history_newest_first (test_projects.Answers.test_what_changed_is_the_history_newest_first) ... ok
test_a_project_is_found_by_its_title_and_its_alias (test_projects.Build.test_a_project_is_found_by_its_title_and_its_alias) ... ok
test_a_record_whose_quote_is_not_in_its_input_stops_the_build (test_projects.Build.test_a_record_whose_quote_is_not_in_its_input_stops_the_build) ... ok
test_links_join_the_projects_to_the_graph (test_projects.Build.test_links_join_the_projects_to_the_graph) ... ok
test_no_records_builds_the_graph_as_before (test_projects.Build.test_no_records_builds_the_graph_as_before) ... ok
test_projects_and_deliverables_are_entities (test_projects.Build.test_projects_and_deliverables_are_entities) ... ok
test_the_build_line_counts_projects (test_projects.Build.test_the_build_line_counts_projects) ... ok
test_the_plan_its_order_the_sources_and_the_history_have_tables (test_projects.Build.test_the_plan_its_order_the_sources_and_the_history_have_tables) ... ok
test_the_status_history_is_dated_claims (test_projects.Build.test_the_status_history_is_dated_claims) ... ok
test_a_session_entry_is_kept_on_its_own_for_ingest (test_projects.Digest.test_a_session_entry_is_kept_on_its_own_for_ingest) ... ok
test_projects_are_on_by_default (test_projects.Digest.test_projects_are_on_by_default) ... ok
test_a_source_changed_since_it_was_read (test_projects.Health.test_a_source_changed_since_it_was_read) ... ok
test_overdue_stale_and_old_questions (test_projects.Health.test_overdue_stale_and_old_questions) ... ok
test_the_board_shows_each_project_and_what_needs_a_look (test_projects.Health.test_the_board_shows_each_project_and_what_needs_a_look) ... ok
test_the_story_needs_no_look_on_the_28th (test_projects.Health.test_the_story_needs_no_look_on_the_28th) ... ok
test_a_deliverable_the_project_does_not_have (test_projects.Plans.test_a_deliverable_the_project_does_not_have) ... ok
test_a_new_plan_replaces_the_agreed_one_as_version_two (test_projects.Plans.test_a_new_plan_replaces_the_agreed_one_as_version_two) ... ok
test_a_step_owner_the_graph_does_not_know (test_projects.Plans.test_a_step_owner_the_graph_does_not_know) ... ok
test_a_step_waiting_on_a_later_one (test_projects.Plans.test_a_step_waiting_on_a_later_one) ... ok
test_recording_it_gives_the_projects_case_02_starts_from (test_projects.Plans.test_recording_it_gives_the_projects_case_02_starts_from) ... ok
test_research_that_checks_out_is_kept_as_a_source (test_projects.Plans.test_research_that_checks_out_is_kept_as_a_source) ... ok
test_research_the_file_does_not_say (test_projects.Plans.test_research_the_file_does_not_say) ... ok
test_the_discussion_renders_to_the_file_the_quotes_are_checked_against (test_projects.Plans.test_the_discussion_renders_to_the_file_the_quotes_are_checked_against) ... ok
test_a_proposal_waits_until_you_apply_it (test_projects.Review.test_a_proposal_waits_until_you_apply_it) ... ok
test_a_rejected_proposal_changes_nothing (test_projects.Review.test_a_rejected_proposal_changes_nothing) ... ok
test_an_input_dealt_with_is_not_read_again (test_projects.Review.test_an_input_dealt_with_is_not_read_again) ... ok
test_an_input_edited_after_the_proposal_is_refused (test_projects.Review.test_an_input_edited_after_the_proposal_is_refused) ... ok
test_an_input_from_elsewhere_is_kept_under_inputs (test_projects.Review.test_an_input_from_elsewhere_is_kept_under_inputs) ... ok
test_changes_that_need_you_wait_for_yes (test_projects.Review.test_changes_that_need_you_wait_for_yes) ... ok
test_session_start_says_when_updates_wait (test_projects.Review.test_session_start_says_when_updates_wait) ... ok
test_a_step_can_be_moved_too (test_projects.Status.test_a_step_can_be_moved_too) ... ok
test_done_needs_your_confirmation (test_projects.Status.test_done_needs_your_confirmation) ... ok
test_your_words_are_the_quote (test_projects.Status.test_your_words_are_the_quote) ... ok
test_keyword_only_keeps_its_order (test_rag.Fusion.test_keyword_only_keeps_its_order) ... ok
test_meaning_leg_breaks_a_tie (test_rag.Fusion.test_meaning_leg_breaks_a_tie) ... ok
test_scores_add_across_legs (test_rag.Fusion.test_scores_add_across_legs) ... ok
test_mileage_rate_both_legs_agree (test_rag.ReadmeCases.test_mileage_rate_both_legs_agree) ... ok
test_refund_in_march_the_500_rule_first (test_rag.ReadmeCases.test_refund_in_march_the_500_rule_first) ... ok
test_sign_off_while_sarah_is_away_distilled_entry_first (test_rag.ReadmeCases.test_sign_off_while_sarah_is_away_distilled_entry_first) ... ok
test_talk_to_customers_meaning_finds_the_right_docs (test_rag.ReadmeCases.test_talk_to_customers_meaning_finds_the_right_docs) ... ok

Slowest test durations
----------------------------------------------------------------------
21.050s    test_the_orchestrator_runs_a_plan_on_machines_that_start_slower_than_a_lease (test_kl_live_server.LiveServer.test_the_orchestrator_runs_a_plan_on_machines_that_start_slower_than_a_lease)
9.436s     test_any_sequence_of_changes_gives_the_graph_a_full_build_gives (test_kl_projection.Projection.test_any_sequence_of_changes_gives_the_graph_a_full_build_gives)
8.697s     test_each_case_as_a_change_request (test_kl_review.Cases.test_each_case_as_a_change_request)
1.892s     test_an_openspec_deliverable_is_accepted_with_what_to_archive (test_kl_runs.Runs.test_an_openspec_deliverable_is_accepted_with_what_to_archive)
1.603s     test_the_hook_asks_the_service_and_falls_back_when_it_is_down (test_kl_live_server.LiveServer.test_the_hook_asks_the_service_and_falls_back_when_it_is_down)
1.474s     test_passages_stay_within_the_budget (test_fallback.Fallback.test_passages_stay_within_the_budget)
1.417s     test_no_names_brings_labelled_passages (test_fallback.Fallback.test_no_names_brings_labelled_passages)
1.405s     test_no_match_still_answers (test_hooks.GraphHook.test_no_match_still_answers)
1.399s     test_postgres_and_sqlite_give_the_same_context (test_kl_store.Postgres.test_postgres_and_sqlite_give_the_same_context)
1.254s     test_a_long_poll_returns_as_soon_as_something_happens (test_kl_auth_events.Events.test_a_long_poll_returns_as_soon_as_something_happens)
1.220s     test_a_new_version_rewrites_only_its_own_files (test_kl_projection.Projection.test_a_new_version_rewrites_only_its_own_files)
1.086s     test_a_manifest_says_what_to_upload_and_what_to_retract (test_kl_ingest.Dedup.test_a_manifest_says_what_to_upload_and_what_to_retract)
1.016s     test_soft_delete_leaves_recall_and_the_list_and_restore_brings_it_back (test_kl_review.Review.test_soft_delete_leaves_recall_and_the_list_and_restore_brings_it_back)
0.904s     test_an_mcp_agent_works_a_task_through_the_tools (test_kl_live_server.LiveServer.test_an_mcp_agent_works_a_task_through_the_tools)
0.893s     test_the_happy_path (test_kl_runs.Runs.test_the_happy_path)
0.888s     test_if_match_refuses_an_edit_based_on_an_old_version (test_kl_review.Review.test_if_match_refuses_an_edit_based_on_an_old_version)
0.818s     test_webhooks_are_signed_and_retried_in_order_until_delivered (test_kl_auth_events.Events.test_webhooks_are_signed_and_retried_in_order_until_delivered)
0.801s     test_a_claims_id_is_the_same_in_every_build (test_kl_projection.Projection.test_a_claims_id_is_the_same_in_every_build)
0.793s     test_renewals_while_the_machine_starts_keep_the_token_valid_past_its_first_lease (test_kl_runs.Runs.test_renewals_while_the_machine_starts_keep_the_token_valid_past_its_first_lease)
0.782s     test_completing_twice_with_the_same_key_gives_the_same_answer (test_kl_runs.Runs.test_completing_twice_with_the_same_key_gives_the_same_answer)
0.733s     test_a_new_plan_version_holds_only_the_tasks_it_changes (test_kl_runs.Runs.test_a_new_plan_version_holds_only_the_tasks_it_changes)
0.733s     test_an_agent_proposes_and_a_person_decides (test_kl_runs.Runs.test_an_agent_proposes_and_a_person_decides)
0.722s     test_the_token_is_kept_only_as_a_hash_and_never_lands_in_an_artifact (test_kl_runs.Runs.test_the_token_is_kept_only_as_a_hash_and_never_lands_in_an_artifact)
0.714s     test_a_graph_file_is_never_replaced_under_a_reader (test_kl_projection.Projection.test_a_graph_file_is_never_replaced_under_a_reader)
0.691s     test_the_workspace_limits_runs_at_once (test_kl_runs.Runs.test_the_workspace_limits_runs_at_once)
0.648s     test_a_conversation_sees_each_quote_once_until_it_is_compacted (test_excerpts.HookSessions.test_a_conversation_sees_each_quote_once_until_it_is_compacted)
0.640s     test_a_request_another_approval_made_stale_is_caught (test_kl_review.Review.test_a_request_another_approval_made_stale_is_caught)
0.615s     test_a_failed_attempt_is_retried_until_its_retries_run_out (test_kl_runs.Runs.test_a_failed_attempt_is_retried_until_its_retries_run_out)
0.612s     test_approving_an_edited_version_records_the_edit (test_kl_review.Review.test_approving_an_edited_version_records_the_edit)
0.610s     test_without_an_extractor_a_document_waits_for_its_extraction (test_kl_ingest.Dedup.test_without_an_extractor_a_document_waits_for_its_extraction)
0.607s     test_mcp_with_an_api_key_reads_and_proposes (test_kl_live_server.LiveServer.test_mcp_with_an_api_key_reads_and_proposes)
0.597s     test_every_decision_is_in_the_projects_history (test_kl_review.Review.test_every_decision_is_in_the_projects_history)
0.591s     test_sections_can_run_side_by_side_within_themselves (test_kl_runs.Plans.test_sections_can_run_side_by_side_within_themselves)
0.583s     test_approving_some_operations (test_kl_review.Review.test_approving_some_operations)
0.582s     test_retracting_a_source_takes_its_facts_out_and_restoring_brings_them_back (test_kl_ingest.Dedup.test_retracting_a_source_takes_its_facts_out_and_restoring_brings_them_back)
0.572s     test_the_answer_is_the_one_recall_gives_in_process (test_kl_store.Backends.test_the_answer_is_the_one_recall_gives_in_process)
0.565s     test_an_approved_plan_is_mirrored_into_the_projects_steps (test_kl_runs.Plans.test_an_approved_plan_is_mirrored_into_the_projects_steps)
0.513s     test_code_questions (test_kl_projection.SameAnswers.test_code_questions)
0.510s     test_a_task_marked_for_a_person_waits_for_one (test_kl_runs.Runs.test_a_task_marked_for_a_person_waits_for_one)
0.461s     test_two_files_that_disagree_go_to_a_person (test_kl_ingest.Dedup.test_two_files_that_disagree_go_to_a_person)
0.455s     test_same_input_same_db (test_build.Build.test_same_input_same_db)
0.429s     test_a_question_to_a_person_pauses_the_lease (test_kl_runs.Runs.test_a_question_to_a_person_pauses_the_lease)
0.411s     test_a_run_token_works_only_for_its_own_run (test_kl_runs.Runs.test_a_run_token_works_only_for_its_own_run)
0.411s     test_a_lease_nobody_renews_expires_and_its_token_with_it (test_kl_runs.Runs.test_a_lease_nobody_renews_expires_and_its_token_with_it)
0.385s     test_a_new_version_replaces_the_old_ones_facts (test_kl_ingest.Dedup.test_a_new_version_replaces_the_old_ones_facts)
0.381s     test_a_runner_without_what_the_task_needs_is_refused (test_kl_runs.Runs.test_a_runner_without_what_the_task_needs_is_refused)
0.375s     test_prompt_arrives_intact (test_hooks.RagHook.test_prompt_arrives_intact)
0.365s     test_the_same_fact_from_two_files_is_one_claim_with_two_sources (test_kl_ingest.Dedup.test_the_same_fact_from_two_files_is_one_claim_with_two_sources)
0.353s     test_a_transcript_becomes_a_change_request_quoting_it (test_kl_ingest.Dedup.test_a_transcript_becomes_a_change_request_quoting_it)
0.341s     test_an_openspec_change_becomes_a_task_graph (test_kl_runs.Plans.test_an_openspec_change_becomes_a_task_graph)
0.340s     test_a_code_change_says_which_requirements_are_at_stake (test_kl_openspec.OpenSpecInTheGraph.test_a_code_change_says_which_requirements_are_at_stake)
0.328s     test_talk_to_customers_meaning_finds_the_right_docs (test_rag.ReadmeCases.test_talk_to_customers_meaning_finds_the_right_docs)
0.304s     test_service_accounts_editors_and_runs_never_approve (test_kl_review.Review.test_service_accounts_editors_and_runs_never_approve)
0.300s     test_sign_off_while_sarah_is_away_distilled_entry_first (test_rag.ReadmeCases.test_sign_off_while_sarah_is_away_distilled_entry_first)
0.294s     test_a_move_the_rules_forbid_is_refused_before_anyone_is_asked (test_kl_review.Review.test_a_move_the_rules_forbid_is_refused_before_anyone_is_asked)
0.290s     test_a_plan_that_cannot_run_is_refused_with_its_reasons (test_kl_runs.Plans.test_a_plan_that_cannot_run_is_refused_with_its_reasons)
0.287s     test_refund_in_march_the_500_rule_first (test_rag.ReadmeCases.test_refund_in_march_the_500_rule_first)
0.286s     test_a_call_site_changed_after_indexing_is_said_to_have_changed (test_code.Freshness.test_a_call_site_changed_after_indexing_is_said_to_have_changed)
0.284s     test_a_proposal_waits_until_you_apply_it (test_projects.Review.test_a_proposal_waits_until_you_apply_it)
0.283s     test_approve_true_proposes_and_approves_in_one_call_and_records_both (test_kl_review.Review.test_approve_true_proposes_and_approves_in_one_call_and_records_both)
0.282s     test_a_code_line_changed_after_indexing_is_said_to_have_changed (test_code.Freshness.test_a_code_line_changed_after_indexing_is_said_to_have_changed)
0.281s     test_a_rejection_keeps_its_reason (test_kl_review.Review.test_a_rejection_keeps_its_reason)
0.270s     test_an_input_dealt_with_is_not_read_again (test_projects.Review.test_an_input_dealt_with_is_not_read_again)
0.261s     test_mileage_rate_both_legs_agree (test_rag.ReadmeCases.test_mileage_rate_both_legs_agree)
0.260s     test_one_workspace_never_sees_another (test_kl_store.Postgres.test_one_workspace_never_sees_another)
0.257s     test_a_dry_run_shows_the_diff_and_opens_nothing (test_kl_review.Review.test_a_dry_run_shows_the_diff_and_opens_nothing)
0.255s     test_the_answer_is_the_one_recall_gives_in_process (test_kl_store.Postgres.test_the_answer_is_the_one_recall_gives_in_process)
0.253s     test_changes_that_need_you_wait_for_yes (test_projects.Review.test_changes_that_need_you_wait_for_yes)
0.252s     test_changed_file (test_excerpts.ChangedDocuments.test_changed_file)
0.251s     test_answer_survives_within_budget (test_growth.Busy10000.test_answer_survives_within_budget)
0.251s     test_a_rejected_proposal_changes_nothing (test_projects.Review.test_a_rejected_proposal_changes_nothing)
0.248s     test_an_input_edited_after_the_proposal_is_refused (test_projects.Review.test_an_input_edited_after_the_proposal_is_refused)
0.248s     test_missing_file (test_excerpts.ChangedDocuments.test_missing_file)
0.246s     test_one_workspace_never_sees_another (test_kl_store.Backends.test_one_workspace_never_sees_another)
0.244s     test_an_input_from_elsewhere_is_kept_under_inputs (test_projects.Review.test_an_input_from_elsewhere_is_kept_under_inputs)
0.244s     test_unchanged (test_excerpts.ChangedDocuments.test_unchanged)
0.235s     test_session_start_says_when_updates_wait (test_projects.Review.test_session_start_says_when_updates_wait)
0.234s     test_the_stream_sends_server_sent_events (test_kl_auth_events.Events.test_the_stream_sends_server_sent_events)
0.232s     test_same_vectors_as_loading_the_model (test_embedder.Warm.test_same_vectors_as_loading_the_model)
0.231s     test_an_older_extraction_description_becomes_a_note (test_build.Build.test_an_older_extraction_description_becomes_a_note)
0.231s     test_the_build_line_counts_projects (test_projects.Build.test_the_build_line_counts_projects)
0.230s     test_every_symbol_asked_about_a_change_brings_every_dependent (test_code.Dependents.test_every_symbol_asked_about_a_change_brings_every_dependent)
0.230s     test_links_carry_their_dates (test_build.Build.test_links_carry_their_dates)
0.226s     test_no_records_builds_the_graph_as_before (test_projects.Build.test_no_records_builds_the_graph_as_before)
0.225s     test_counts (test_build.Build.test_counts)
0.224s     test_markdown_and_spacing_do_not_count (test_excerpts.QuotesAtBuild.test_markdown_and_spacing_do_not_count)
0.224s     test_names_are_split_like_questions (test_build.Build.test_names_are_split_like_questions)
0.223s     test_a_document_graph_without_code_has_no_code_in_its_answers (test_code.Answers.test_a_document_graph_without_code_has_no_code_in_its_answers)
0.223s     test_foreign_keys_hold (test_build.Build.test_foreign_keys_hold)
0.222s     test_every_docs_claims_are_kept (test_build.Build.test_every_docs_claims_are_kept)
0.221s     test_a_role_nobody_holds_is_a_gap (test_excerpts.Coverage.test_a_role_nobody_holds_is_a_gap)
0.219s     test_dated_versions_of_a_policy_coexist (test_build.Build.test_dated_versions_of_a_policy_coexist)
0.216s     test_the_repo_graph_has_no_gaps (test_excerpts.Coverage.test_the_repo_graph_has_no_gaps)
0.188s     test_sessions_do_not_share (test_excerpts.HookSessions.test_sessions_do_not_share)
0.166s     test_a_near_copy_is_linked_and_left_out (test_kl_ingest.Dedup.test_a_near_copy_is_linked_and_left_out)
0.164s     test_a_near_copy_can_be_sent_to_a_person (test_kl_ingest.Dedup.test_a_near_copy_can_be_sent_to_a_person)
0.132s     test_a_token_for_another_audience_or_expired_or_forged_is_refused (test_kl_auth_events.Auth.test_a_token_for_another_audience_or_expired_or_forged_is_refused)
0.104s     test_every_case (test_code.Answers.test_every_case)
0.097s     test_the_hook_answers_a_projects_question_without_falling_back_to_notes (test_projects.Answers.test_the_hook_answers_a_projects_question_without_falling_back_to_notes)
0.096s     test_the_hook_sends_the_trace (test_code.Answers.test_the_hook_sends_the_trace)
0.093s     test_a_graph_answer_brings_no_passages (test_fallback.Fallback.test_a_graph_answer_brings_no_passages)
0.091s     test_non_ascii_name_is_found (test_hooks.GraphHook.test_non_ascii_name_is_found)
0.091s     test_output_is_what_claude_code_reads (test_hooks.GraphHook.test_output_is_what_claude_code_reads)
0.087s     test_without_an_index_the_loud_line_stays_alone (test_fallback.Fallback.test_without_an_index_the_loud_line_stays_alone)
0.086s     test_the_workspace_can_turn_self_approval_off (test_kl_review.Review.test_the_workspace_can_turn_self_approval_off)
0.082s     test_document_questions (test_kl_projection.SameAnswers.test_document_questions)
0.076s     test_an_extraction_that_misquotes_is_refused (test_kl_ingest.Dedup.test_an_extraction_that_misquotes_is_refused)
0.073s     test_a_renamed_copy_is_another_location_of_the_same_version (test_kl_ingest.Dedup.test_a_renamed_copy_is_another_location_of_the_same_version)
0.071s     test_a_short_file_with_a_word_changed_is_not_a_near_copy (test_kl_ingest.Dedup.test_a_short_file_with_a_word_changed_is_not_a_near_copy)
0.071s     test_events_come_in_order_by_cursor_and_type (test_kl_auth_events.Events.test_events_come_in_order_by_cursor_and_type)
0.067s     test_transcript_path_arrives_intact (test_hooks.DigestHook.test_transcript_path_arrives_intact)
0.065s     test_every_wording_of_a_change_brings_both_directions (test_code.Dependents.test_every_wording_of_a_change_brings_both_directions)
0.065s     test_the_same_file_twice_is_unchanged (test_kl_ingest.Dedup.test_the_same_file_twice_is_unchanged)
0.064s     test_every_scenario_is_verified_by_its_test (test_kl_specs.ServiceSpecs.test_every_scenario_is_verified_by_its_test)
0.061s     test_the_same_text_with_other_line_endings_is_the_same_text (test_kl_ingest.Dedup.test_the_same_text_with_other_line_endings_is_the_same_text)
0.061s     test_nothing_applies_until_a_person_approves (test_kl_review.Review.test_nothing_applies_until_a_person_approves)
0.058s     test_the_storage_limit_holds (test_kl_ingest.Dedup.test_the_storage_limit_holds)
0.052s     test_answer_survives (test_growth.BusyBare10000.test_answer_survives)
0.045s     test_a_pdf_needs_its_text (test_kl_ingest.Dedup.test_a_pdf_needs_its_text)
0.037s     test_a_proposer_may_approve_their_own_request_and_one_approval_is_enough (test_kl_review.Review.test_a_proposer_may_approve_their_own_request_and_one_approval_is_enough)
0.035s     test_an_openspec_change_that_breaks_the_format_is_refused (test_kl_runs.Plans.test_an_openspec_change_that_breaks_the_format_is_refused)
0.033s     test_graph_from_an_older_version_says_rebuild (test_graph.NoUsableGraph.test_graph_from_an_older_version_says_rebuild)
0.032s     test_each_fact_names_its_claim_by_content (test_kl_projection.SameAnswers.test_each_fact_names_its_claim_by_content)
0.030s     test_a_source_changed_since_it_was_read (test_projects.Health.test_a_source_changed_since_it_was_read)
0.028s     test_roles_decide_what_a_person_may_do (test_kl_auth_events.Auth.test_roles_decide_what_a_person_may_do)
0.026s     test_answer_survives_and_names_are_fast (test_growth.Elsewhere10000.test_answer_survives_and_names_are_fast)
0.025s     test_the_trace_is_the_same_whatever_the_wording (test_code.Dependents.test_the_trace_is_the_same_whatever_the_wording)
0.024s     test_a_date_that_is_not_a_date_stops_the_build (test_build.Build.test_a_date_that_is_not_a_date_stops_the_build)
0.022s     test_a_person_signs_in_with_the_issuers_token_once_an_admin_has_added_them (test_kl_auth_events.Auth.test_a_person_signs_in_with_the_issuers_token_once_an_admin_has_added_them)
0.020s     test_a_revoked_key_stops_working (test_kl_auth_events.Auth.test_a_revoked_key_stops_working)
0.019s     test_the_board_shows_each_project_and_what_needs_a_look (test_projects.Health.test_the_board_shows_each_project_and_what_needs_a_look)
0.018s     test_a_paraphrase_is_refused (test_excerpts.QuotesAtBuild.test_a_paraphrase_is_refused)
0.018s     test_unknown_claim_kind_stops_the_build (test_build.Build.test_unknown_claim_kind_stops_the_build)
0.017s     test_a_quote_from_a_missing_document_is_refused (test_excerpts.QuotesAtBuild.test_a_quote_from_a_missing_document_is_refused)
0.017s     test_two_thresholds_in_force_at_once_stop_the_build (test_build.Build.test_two_thresholds_in_force_at_once_stop_the_build)
0.017s     test_deliverables_are_left_out_unless_asked_for (test_projects.Answers.test_deliverables_are_left_out_unless_asked_for)
0.016s     test_a_request_without_the_key_gets_nothing (test_embedder.Warm.test_a_request_without_the_key_gets_nothing)
0.016s     test_dates_the_wrong_way_round_stop_the_build (test_build.Build.test_dates_the_wrong_way_round_stop_the_build)
0.016s     test_a_quote_too_long_is_refused (test_excerpts.QuotesAtBuild.test_a_quote_too_long_is_refused)
0.015s     test_quotes_stay_within_the_budget (test_excerpts.QuotesAtRecall.test_quotes_stay_within_the_budget)
0.015s     test_every_quote_in_every_record_is_in_its_input (test_project_cases.Cases.test_every_quote_in_every_record_is_in_its_input)
0.015s     test_a_record_whose_quote_is_not_in_its_input_stops_the_build (test_projects.Build.test_a_record_whose_quote_is_not_in_its_input_stops_the_build)
0.014s     test_context_answers_as_of_a_date (test_kl_openspec.OpenSpecInTheGraph.test_context_answers_as_of_a_date)
0.014s     test_name_with_two_types_stops_the_build (test_build.Build.test_name_with_two_types_stops_the_build)
0.014s     test_the_cases_follow_on_from_each_other (test_project_cases.Cases.test_the_cases_follow_on_from_each_other)
0.014s     test_space_runs_out_on_call_sites_and_never_on_dependents (test_code.Dependents.test_space_runs_out_on_call_sites_and_never_on_dependents)
0.012s     test_a_modified_requirement_ends_the_old_claim_the_day_its_change_was_archived (test_kl_openspec.OpenSpecInTheGraph.test_a_modified_requirement_ends_the_old_claim_the_day_its_change_was_archived)
0.012s     test_only_the_root_key_creates_workspaces (test_kl_auth_events.Auth.test_only_the_root_key_creates_workspaces)
0.011s     test_quotes_already_sent_are_not_repeated (test_excerpts.QuotesAtRecall.test_quotes_already_sent_are_not_repeated)
0.010s     test_the_whole_plan_when_asked_for (test_projects.Answers.test_the_whole_plan_when_asked_for)
0.010s     test_every_caller_and_every_call_is_there (test_code.FanIn.test_every_caller_and_every_call_is_there)
0.010s     test_a_person_says_which_workspace (test_kl_auth_events.Auth.test_a_person_says_which_workspace)
0.010s     test_answer_survives (test_growth.Busy1000.test_answer_survives)
0.010s     test_in_time_says_nothing (test_growth.TimeBudget.test_in_time_says_nothing)
0.010s     test_a_test_that_names_a_scenario_verifies_it (test_kl_openspec.OpenSpecInTheGraph.test_a_test_that_names_a_scenario_verifies_it)
0.009s     test_a_session_entry_is_kept_on_its_own_for_ingest (test_projects.Digest.test_a_session_entry_is_kept_on_its_own_for_ingest)
0.009s     test_the_sign_off_is_walked_from_the_project_to_the_person (test_projects.Answers.test_the_sign_off_is_walked_from_the_project_to_the_person)
0.009s     test_the_status_comes_first_with_why_and_the_plan_in_a_line (test_projects.Answers.test_the_status_comes_first_with_why_and_the_plan_in_a_line)
0.008s     test_one_name_in_any_style_names_one_symbol (test_code.Answers.test_one_name_in_any_style_names_one_symbol)
0.008s     test_what_changed_is_the_history_newest_first (test_projects.Answers.test_what_changed_is_the_history_newest_first)
0.008s     test_the_plan_its_order_the_sources_and_the_history_have_tables (test_projects.Build.test_the_plan_its_order_the_sources_and_the_history_have_tables)
0.008s     test_a_handler_change_shows_the_bodies_its_clients_send (test_code.Dependents.test_a_handler_change_shows_the_bodies_its_clients_send)
0.008s     test_errors_are_problems (test_kl_auth_events.Auth.test_errors_are_problems)
0.008s     test_document_questions_are_answered_as_before (test_projects.Answers.test_document_questions_are_answered_as_before)
0.008s     test_quick_enough_for_the_hook (test_projects.Answers.test_quick_enough_for_the_hook)
0.008s     test_same_question_same_facts (test_graph.GraphTestCases.test_same_question_same_facts)
0.008s     test_a_past_date_gets_that_days_status_and_nothing_learnt_later (test_projects.Answers.test_a_past_date_gets_that_days_status_and_nothing_learnt_later)
0.008s     test_cover_on_a_given_day (test_dates.ExampleQuestions.test_cover_on_a_given_day)
0.007s     test_a_project_name_wins_over_an_alias_inside_it (test_projects.Answers.test_a_project_name_wins_over_an_alias_inside_it)
0.007s     test_what_a_person_is_working_on (test_projects.Answers.test_what_a_person_is_working_on)
0.006s     test_the_specs_are_in_the_format (test_kl_specs.ServiceSpecs.test_the_specs_are_in_the_format)
0.006s     test_no_index_means_no_start (test_embedder.NotRunning.test_no_index_means_no_start)
0.006s     test_answer_survives (test_growth.Busy100.test_answer_survives)
0.005s     test_the_provenance_counts_the_code (test_code.Answers.test_the_provenance_counts_the_code)
0.005s     test_claims_stay_on_topic (test_graph.GraphTestCases.test_claims_stay_on_topic)
0.005s     test_a_question_about_projects_that_names_none (test_projects.Answers.test_a_question_about_projects_that_names_none)
0.005s     test_the_trace_follows_past_three_hops (test_code.Answers.test_the_trace_follows_past_three_hops)
0.005s     test_row_security_hides_other_workspaces_even_without_a_filter (test_kl_store.Postgres.test_row_security_hides_other_workspaces_even_without_a_filter)
0.004s     test_a_removed_requirement_ends_that_day (test_kl_openspec.OpenSpecInTheGraph.test_a_removed_requirement_ends_that_day)
0.004s     test_supplier_payments_walk_two_hops_to_alex (test_graph.GraphTestCases.test_supplier_payments_walk_two_hops_to_alex)
0.004s     test_an_unknown_keeps_its_own_words (test_excerpts.QuotesAtRecall.test_an_unknown_keeps_its_own_words)
0.004s     test_near_misses_are_not_dates (test_project_cases.Dates.test_near_misses_are_not_dates)
0.004s     test_the_answer_comes_with_its_sources (test_excerpts.QuotesAtRecall.test_the_answer_comes_with_its_sources)
0.004s     test_800_refund_in_march_goes_to_marcus (test_dates.ExampleQuestions.test_800_refund_in_march_goes_to_marcus)
0.004s     test_a_deadline_in_words_is_not_a_date (test_project_cases.Refused.test_a_deadline_in_words_is_not_a_date)
0.004s     test_300_refund_in_june_2025_needed_a_director (test_dates.ExampleQuestions.test_300_refund_in_june_2025_needed_a_director)
0.004s     test_undated_facts_hold_at_any_date (test_dates.ExampleQuestions.test_undated_facts_hold_at_any_date)
0.004s     test_compact_format_for_the_model (test_graph.GraphTestCases.test_compact_format_for_the_model)
0.004s     test_the_model_is_not_told_the_timing (test_excerpts.QuotesAtRecall.test_the_model_is_not_told_the_timing)
0.004s     test_provenance_line_tells_the_model_how_to_use_the_facts (test_excerpts.QuotesAtRecall.test_provenance_line_tells_the_model_how_to_use_the_facts)
0.004s     test_pretty_format_for_people (test_graph.GraphTestCases.test_pretty_format_for_people)
0.004s     test_refund_in_march_walks_three_hops_to_marcus (test_graph.GraphTestCases.test_refund_in_march_walks_three_hops_to_marcus)
0.004s     test_injection_is_capped_at_eight_facts (test_graph.GraphTestCases.test_injection_is_capped_at_eight_facts)
0.004s     test_conditions_travel_with_the_facts_as_claims (test_graph.GraphTestCases.test_conditions_travel_with_the_facts_as_claims)
0.004s     test_a_date_the_input_does_not_state (test_project_cases.Refused.test_a_date_the_input_does_not_state)
0.004s     test_threshold_history_shows_both_versions_with_dates (test_dates.ExampleQuestions.test_threshold_history_shows_both_versions_with_dates)
0.004s     test_threshold_in_2025 (test_dates.ExampleQuestions.test_threshold_in_2025)
0.004s     test_800_refund_in_april_goes_to_sarah (test_dates.ExampleQuestions.test_800_refund_in_april_goes_to_sarah)
0.003s     test_onboarding_is_one_hop_several_edges (test_graph.GraphTestCases.test_onboarding_is_one_hop_several_edges)
0.003s     test_the_repo_extraction_is_consistent (test_build.Build.test_the_repo_extraction_is_consistent)
0.003s     test_300_refund_today_any_agent (test_dates.ExampleQuestions.test_300_refund_today_any_agent)
0.003s     test_recording_it_gives_the_projects_case_02_starts_from (test_projects.Plans.test_recording_it_gives_the_projects_case_02_starts_from)
0.003s     test_what_the_documents_leave_open_is_said (test_excerpts.QuotesAtRecall.test_what_the_documents_leave_open_is_said)
0.003s     test_the_code_zip_is_indexed_and_its_specs_read (test_kl_openspec.OpenSpecInTheGraph.test_the_code_zip_is_indexed_and_its_specs_read)
0.003s     test_the_story_needs_no_look_on_the_28th (test_projects.Health.test_the_story_needs_no_look_on_the_28th)
0.003s     test_the_forms_a_date_is_said_in (test_project_cases.Dates.test_the_forms_a_date_is_said_in)
0.003s     test_each_expected_change_set_is_valid (test_project_cases.Cases.test_each_expected_change_set_is_valid)
0.003s     test_overdue_stale_and_old_questions (test_projects.Health.test_overdue_stale_and_old_questions)
0.003s     test_research_that_checks_out_is_kept_as_a_source (test_projects.Plans.test_research_that_checks_out_is_kept_as_a_source)
0.003s     test_priya_is_seeded_by_alias (test_graph.GraphTestCases.test_priya_is_seeded_by_alias)
0.003s     test_the_app_role_is_not_a_superuser (test_kl_store.Postgres.test_the_app_role_is_not_a_superuser)
0.002s     test_every_claim_quotes_a_line_of_its_file (test_code.Index.test_every_claim_quotes_a_line_of_its_file)
0.002s     test_a_new_plan_replaces_the_agreed_one_as_version_two (test_projects.Plans.test_a_new_plan_replaces_the_agreed_one_as_version_two)
0.002s     test_a_deliverable_the_project_does_not_have (test_projects.Plans.test_a_deliverable_the_project_does_not_have)
0.002s     test_a_project_is_found_by_its_title_and_its_alias (test_projects.Build.test_a_project_is_found_by_its_title_and_its_alias)
0.002s     test_applying_it_gives_the_stored_result (test_project_cases.Cases.test_applying_it_gives_the_stored_result)
0.002s     test_research_the_file_does_not_say (test_projects.Plans.test_research_the_file_does_not_say)
0.002s     test_no_embedder_means_no_vectors (test_embedder.NotRunning.test_no_embedder_means_no_vectors)
0.002s     test_a_day_said_relative_to_the_input (test_project_cases.Dates.test_a_day_said_relative_to_the_input)
0.002s     test_row_security_refuses_writes_for_another_workspace (test_kl_store.Postgres.test_row_security_refuses_writes_for_another_workspace)
0.002s     test_every_site_quotes_its_line (test_code.Index.test_every_site_quotes_its_line)
0.002s     test_a_step_owner_the_graph_does_not_know (test_projects.Plans.test_a_step_owner_the_graph_does_not_know)
0.002s     test_the_status_history_is_dated_claims (test_projects.Build.test_the_status_history_is_dated_claims)
0.002s     test_a_step_waiting_on_a_later_one (test_projects.Plans.test_a_step_waiting_on_a_later_one)
0.002s     test_a_step_can_be_moved_too (test_projects.Status.test_a_step_can_be_moved_too)
0.002s     test_an_open_change_is_not_a_fact (test_kl_openspec.OpenSpecInTheGraph.test_an_open_change_is_not_a_fact)
0.002s     test_out_of_time_says_so (test_growth.TimeBudget.test_out_of_time_says_so)
0.002s     test_your_words_are_the_quote (test_projects.Status.test_your_words_are_the_quote)
0.001s     test_done_needs_your_confirmation (test_projects.Status.test_done_needs_your_confirmation)
0.001s     test_projects_and_deliverables_are_entities (test_projects.Build.test_projects_and_deliverables_are_entities)
0.001s     test_propose_wraps_the_reply_with_the_input (test_project_cases.Ingest.test_propose_wraps_the_reply_with_the_input)
0.001s     test_a_refused_answer_is_sent_back_once_with_the_problems (test_project_cases.Ingest.test_a_refused_answer_is_sent_back_once_with_the_problems)
0.001s     test_a_good_answer_is_not_sent_back (test_project_cases.Ingest.test_a_good_answer_is_not_sent_back)
0.001s     test_links_join_the_projects_to_the_graph (test_projects.Build.test_links_join_the_projects_to_the_graph)
0.001s     test_outside_the_vocabulary_fails_loudly (test_graph.GraphTestCases.test_outside_the_vocabulary_fails_loudly)
0.001s     test_missing_graph_says_how_to_build_it (test_graph.NoUsableGraph.test_missing_graph_says_how_to_build_it)
0.001s     test_apply_leaves_the_records_it_was_given_alone (test_project_cases.Cases.test_apply_leaves_the_records_it_was_given_alone)
0.001s     test_a_dependency_cycle (test_project_cases.Refused.test_a_dependency_cycle)
0.001s     test_a_step_can_move_its_due_date_alone (test_project_cases.Defaults.test_a_step_can_move_its_due_date_alone)
0.001s     test_a_status_without_from_holds_from_the_inputs_date (test_project_cases.Defaults.test_a_status_without_from_holds_from_the_inputs_date)
0.000s     test_a_new_project_starting_active (test_project_cases.Refused.test_a_new_project_starting_active)
0.000s     test_a_step_change_with_neither_status_nor_due (test_project_cases.Refused.test_a_step_change_with_neither_status_nor_due)
0.000s     test_changing_an_owner_already_set_needs_you (test_project_cases.Refused.test_changing_an_owner_already_set_needs_you)
0.000s     test_a_quote_over_300_characters (test_project_cases.Refused.test_a_quote_over_300_characters)
0.000s     test_a_person_the_graph_does_not_know (test_project_cases.Refused.test_a_person_the_graph_does_not_know)
0.000s     test_a_later_change_is_still_checked_after_a_bad_one (test_project_cases.Refused.test_a_later_change_is_still_checked_after_a_bad_one)
0.000s     test_a_project_that_does_not_exist (test_project_cases.Refused.test_a_project_that_does_not_exist)
0.000s     test_answering_a_question_twice (test_project_cases.Refused.test_answering_a_question_twice)
0.000s     test_a_short_name_where_the_full_one_is_needed (test_project_cases.Refused.test_a_short_name_where_the_full_one_is_needed)
0.000s     test_a_paraphrased_quote (test_project_cases.Refused.test_a_paraphrased_quote)
0.000s     test_a_status_move_the_table_does_not_allow (test_project_cases.Refused.test_a_status_move_the_table_does_not_allow)
0.000s     test_a_step_the_plan_does_not_have (test_project_cases.Refused.test_a_step_the_plan_does_not_have)
0.000s     test_done_is_not_refused_but_needs_you (test_project_cases.Refused.test_done_is_not_refused_but_needs_you)
0.000s     test_the_discussion_renders_to_the_file_the_quotes_are_checked_against (test_projects.Plans.test_the_discussion_renders_to_the_file_the_quotes_are_checked_against)
0.000s     test_projects_are_on_by_default (test_projects.Digest.test_projects_are_on_by_default)
0.000s     test_creating_a_project_twice (test_project_cases.Refused.test_creating_a_project_twice)
0.000s     test_restating_a_recorded_due_date_is_not_refused (test_project_cases.Refused.test_restating_a_recorded_due_date_is_not_refused)
0.000s     test_the_date_comes_from_the_file_name (test_project_cases.Ingest.test_the_date_comes_from_the_file_name)
0.000s     test_the_result_meets_the_case_expectations (test_project_cases.Cases.test_the_result_meets_the_case_expectations)
0.000s     test_the_build_refuses_a_call_site_the_code_lacks (test_code.Freshness.test_the_build_refuses_a_call_site_the_code_lacks)
0.000s     test_writing_a_plan_from_a_meeting (test_project_cases.Refused.test_writing_a_plan_from_a_meeting)
0.000s     test_going_active_without_an_agreed_plan (test_project_cases.Refused.test_going_active_without_an_agreed_plan)
0.000s     test_the_build_refuses_an_index_whose_quotes_the_code_lacks (test_code.Freshness.test_the_build_refuses_an_index_whose_quotes_the_code_lacks)
0.000s     test_every_table_but_two_carries_its_workspace (test_kl_store.Postgres.test_every_table_but_two_carries_its_workspace)
0.000s     test_moving_a_step_with_no_agreed_plan (test_project_cases.Refused.test_moving_a_step_with_no_agreed_plan)
0.000s     test_every_table_but_two_carries_its_workspace (test_kl_store.Backends.test_every_table_but_two_carries_its_workspace)
0.000s     test_prose_is_unchanged (test_code.Tokens.test_prose_is_unchanged)
0.000s     test_words_that_only_look_like_dates (test_dates.Period.test_words_that_only_look_like_dates)
0.000s     test_open_ended (test_dates.Period.test_open_ended)
0.000s     test_days (test_dates.Period.test_days)
0.000s     test_a_new_project_is_found_short_of_owner_date_and_plan (test_project_cases.Cases.test_a_new_project_is_found_short_of_owner_date_and_plan)
0.000s     test_the_parser_checks_the_format (test_kl_openspec.OpenSpecInTheGraph.test_the_parser_checks_the_format)
0.000s     test_short_names_are_written_out (test_project_cases.Ingest.test_short_names_are_written_out)
0.000s     test_a_year (test_dates.Period.test_a_year)
0.000s     test_a_month_without_a_year_is_this_year (test_dates.Period.test_a_month_without_a_year_is_this_year)
0.000s     test_every_naming_style_comes_apart_at_the_same_seams (test_code.Tokens.test_every_naming_style_comes_apart_at_the_same_seams)
0.000s     test_a_reply_without_changes_is_an_error (test_project_cases.Ingest.test_a_reply_without_changes_is_an_error)
0.000s     test_a_fenced_reply_parses (test_project_cases.Ingest.test_a_fenced_reply_parses)
0.000s     test_a_run_of_capitals_is_one_word (test_code.Tokens.test_a_run_of_capitals_is_one_word)
0.000s     test_keyword_only_keeps_its_order (test_rag.Fusion.test_keyword_only_keeps_its_order)
0.000s     test_the_hash_ignores_line_endings (test_project_cases.Cases.test_the_hash_ignores_line_endings)
0.000s     test_each_input_is_recorded_once_per_project_with_what_it_was_used_for (test_project_cases.Cases.test_each_input_is_recorded_once_per_project_with_what_it_was_used_for)
0.000s     test_no_date_means_today (test_dates.Period.test_no_date_means_today)
0.000s     test_meaning_leg_breaks_a_tie (test_rag.Fusion.test_meaning_leg_breaks_a_tie)
0.000s     test_month_and_year (test_dates.Period.test_month_and_year)
0.000s     test_a_new_projects_id_may_be_written_id (test_project_cases.Ingest.test_a_new_projects_id_may_be_written_id)
0.000s     test_scores_add_across_legs (test_rag.Fusion.test_scores_add_across_legs)
0.000s     test_a_history_question_spans_all_dates (test_dates.Period.test_a_history_question_spans_all_dates)
0.000s     test_the_body_fields_sent_and_read (test_code.Index.test_the_body_fields_sent_and_read)
0.000s     test_any_alphabet (test_code.Tokens.test_any_alphabet)
0.000s     test_there_are_seven (test_project_cases.Cases.test_there_are_seven)
0.000s     test_every_predicate_the_index_writes_is_followed (test_code.Dependents.test_every_predicate_the_index_writes_is_followed)
0.000s     test_what_it_finds (test_code.Index.test_what_it_finds)
0.000s     test_the_inputs_own_date_needs_no_saying (test_project_cases.Dates.test_the_inputs_own_date_needs_no_saying)
0.000s     test_a_chain_of_calls_to_a_constant (test_code.Index.test_a_chain_of_calls_to_a_constant)
0.000s     test_digits_stay_with_the_letters_before_them (test_code.Tokens.test_digits_stay_with_the_letters_before_them)
0.000s     test_nothing_reaches_the_legacy_refund (test_code.Index.test_nothing_reaches_the_legacy_refund)
0.000s     test_a_value_in_the_body_picks_the_branch (test_code.Index.test_a_value_in_the_body_picks_the_branch)
0.000s     test_a_lookup_table_gives_one_case_per_entry (test_code.Index.test_a_lookup_table_gives_one_case_per_entry)
0.000s     test_tests_are_their_own_kind_and_call_what_they_test (test_code.Index.test_tests_are_their_own_kind_and_call_what_they_test)
0.000s     test_buttons_own_what_their_onclick_runs (test_code.Index.test_buttons_own_what_their_onclick_runs)
0.000s     test_a_url_built_from_constants_in_two_files (test_code.Index.test_a_url_built_from_constants_in_two_files)
0.000s     test_a_function_passed_and_not_called_is_referenced (test_code.Index.test_a_function_passed_and_not_called_is_referenced)
0.000s     test_a_literal_body_in_the_fetch_picks_the_case (test_code.Index.test_a_literal_body_in_the_fetch_picks_the_case)
0.000s     test_an_explicit_route_matched_across_parameter_syntaxes (test_code.Index.test_an_explicit_route_matched_across_parameter_syntaxes)
0.000s     test_an_import_through_a_package_is_followed_to_the_definition (test_code.Index.test_an_import_through_a_package_is_followed_to_the_definition)
0.000s     test_the_import_decides_which_validate (test_code.Index.test_the_import_decides_which_validate)

----------------------------------------------------------------------
Ran 307 tests in 118.588s

OK
````

### L7 · Graph: £800 refund in March

`python src/recall.py --pretty "A customer wants an £800 refund in March. Who signs it off?"` · started 22:04:42.020 · exit 0 · 101 ms

stdout:

````text
memory: 8 facts recalled in 8.0 ms, for March 2026
These facts come from your documents (9, extracted 2026-09-24). Quoted lines are the documents' own words, checked against the files just now: answer from them, and open a file only if its line says it changed or is missing.

Refund approvals --[approved_by]--> Ops Manager           (refund-policy.md) (from 2026-01-01)
Customer support SOP --[references]--> Refund approvals   (customer-support-sop.md)
Ops Manager --[held_by]--> Sarah Chen                     (org-chart.md)
Onboarding process --[references]--> Ops Manager          (onboarding-process.md)
Customer support SOP --[references]--> Support Lead       (customer-support-sop.md)
Sarah Chen --[delegates_to]--> Marcus Webb                (delegation-memo.md) (2026-03-01 to 2026-03-31)
Support Lead --[held_by]--> Priya Patel                   (org-chart.md)
Incident response --[references]--> Support Lead          (incident-response.md)

where:
  Customer support SOP: Support agents answer tickets within one business day
  Customer support SOP: "Refunds under the approval threshold in the refund approvals policy are processed directly by the agent." [customer-support-sop.md]
  Marcus Webb: "During this period all of her sign-offs and approvals are delegated to Marcus Webb." [delegation-memo.md] (2026-03-01 to 2026-03-31)
  Ops Manager: "Ops Manager: Sarah Chen. Owns day-to-day operations, budgets and sign-offs." [org-chart.md]
  Ops Manager: Approves refunds over £500 (from 2026-01-01)
  Refund approvals: "Superseded on 1 January 2026 by the current refund approvals policy." [refund-policy-2024.md]
  Refund approvals: "Refunds over £500 require approval by the Ops Manager before payment is released." [refund-policy.md] (from 2026-01-01)
  Refund approvals: "Standard refunds under £500 are processed by any support agent within 48 hours." [refund-policy.md] (from 2026-01-01)
  Refund approvals: "Approved refunds are paid back to the original payment method only." [refund-policy.md] (from 2026-01-01)
  Sarah Chen: The Ops Manager
  Sarah Chen: "Sarah Chen is on leave from 1 to 31 March 2026." [delegation-memo.md] (2026-03-01 to 2026-03-31)
````

### L8 · Graph: Supplier payments over £2,000

`python src/recall.py --pretty "Who approves supplier payments over £2,000?"` · started 22:04:42.132 · exit 0 · 96 ms

stdout:

````text
memory: 7 facts recalled in 7.1 ms, as of 2026-09-28
These facts come from your documents (9, extracted 2026-09-24). Quoted lines are the documents' own words, checked against the files just now: answer from them, and open a file only if its line says it changed or is missing.

Supplier payments --[approved_by]--> Founder             (supplier-payments.md)
Supplier payments --[references]--> Tooling inventory    (supplier-payments.md)
Founder --[held_by]--> Alex Doyle                        (org-chart.md)
Incident response --[references]--> Founder              (incident-response.md)
Onboarding process --[references]--> Tooling inventory   (onboarding-process.md)
Onboarding process --[references]--> Ops Manager         (onboarding-process.md)
Incident response --[references]--> Support Lead         (incident-response.md)

where:
  Founder: Sets pricing, signs anything customer-facing
  Founder: Signs off supplier payments over £2,000
  Incident response: "Incidents are raised in the ops channel and triaged by the Support Lead." [incident-response.md]
  Incident response: "Severity-1 incidents (site down, payments failing) escalate to the Founder immediately." [incident-response.md]
  Onboarding process: "New starters are onboarded over their first week, owned by the Ops Manager." [onboarding-process.md]
  Onboarding process: Day one covers accounts and access, using the tooling inventory as the checklist
  Ops Manager: Owns day-to-day operations, budgets and sign-offs
  Ops Manager: "Refunds over £500 require approval by the Ops Manager before payment is released." [refund-policy.md] (from 2026-01-01)
  Supplier payments: "Supplier invoices are paid on 30-day terms." [supplier-payments.md]
  Supplier payments: "Any payment over £2,000 requires Founder sign-off before it is scheduled." [supplier-payments.md]
  Supplier payments: "New suppliers must be added to the tooling inventory before their first invoice." [supplier-payments.md]
  Tooling inventory: "The systems the company runs on: helpdesk, payments, accounting, and the shared drive." [tooling-inventory.md]
  Tooling inventory: The onboarding process uses it as its day-one checklist
````

### L9 · Graph: Onboarding process

`python src/recall.py --pretty "What is the onboarding process?"` · started 22:04:42.219 · exit 0 · 115 ms

stdout:

````text
memory: 7 facts recalled in 6.9 ms, as of 2026-09-28
These facts come from your documents (9, extracted 2026-09-24). Quoted lines are the documents' own words, checked against the files just now: answer from them, and open a file only if its line says it changed or is missing.

Onboarding process --[references]--> Tooling inventory    (onboarding-process.md)
Onboarding process --[references]--> Ops Manager          (onboarding-process.md)
Supplier payments --[references]--> Tooling inventory     (supplier-payments.md)
Ops Manager --[held_by]--> Sarah Chen                     (org-chart.md)
Refund approvals --[approved_by]--> Ops Manager           (refund-policy.md) (from 2026-01-01)
Customer support SOP --[references]--> Refund approvals   (customer-support-sop.md)
Supplier payments --[approved_by]--> Founder              (supplier-payments.md)

where:
  Customer support SOP: "Support agents answer tickets within one business day." [customer-support-sop.md]
  Customer support SOP: "Refunds under the approval threshold in the refund approvals policy are processed directly by the agent." [customer-support-sop.md]
  Onboarding process: "New starters are onboarded over their first week, owned by the Ops Manager." [onboarding-process.md]
  Onboarding process: "Day one covers accounts and access, using the tooling inventory as the checklist." [onboarding-process.md]
  Onboarding process: Week one ends with a shadowing shift alongside the support team
  Ops Manager: "Ops Manager: Sarah Chen. Owns day-to-day operations, budgets and sign-offs." [org-chart.md]
  Ops Manager: Approves refunds over £500 (from 2026-01-01)
  Refund approvals: "Refunds over £500 require approval by the Ops Manager before payment is released." [refund-policy.md] (from 2026-01-01)
  Refund approvals: "Standard refunds under £500 are processed by any support agent within 48 hours." [refund-policy.md] (from 2026-01-01)
  Tooling inventory: The systems the company runs on: helpdesk, payments, accounting and the shared drive
  Tooling inventory: "The onboarding process uses this document as its day-one checklist." [tooling-inventory.md]
````

### L10 · Graph: What does Priya do?

`python src/recall.py --pretty "What does Priya do?"` · started 22:04:42.346 · exit 0 · 102 ms

stdout:

````text
memory: 5 facts recalled in 6.1 ms, as of 2026-09-28
These facts come from your documents (9, extracted 2026-09-24). Quoted lines are the documents' own words, checked against the files just now: answer from them, and open a file only if its line says it changed or is missing.

Support Lead --[held_by]--> Priya Patel                   (org-chart.md)
Customer support SOP --[references]--> Support Lead       (customer-support-sop.md)
Incident response --[references]--> Support Lead          (incident-response.md)
Customer support SOP --[references]--> Refund approvals   (customer-support-sop.md)
Incident response --[references]--> Founder               (incident-response.md)

where:
  Priya Patel: "Support Lead: Priya Patel." [org-chart.md]
  Support Lead: "Complaints and anything unresolved after two replies escalate to the Support Lead." [customer-support-sop.md]
  Support Lead: "Support Lead: Priya Patel. Runs the support rota and handles escalations." [org-chart.md]
````

### L11 · Graph: Boss is away

`python src/recall.py --pretty "Who is in charge when the boss is away?"` · started 22:04:42.447 · exit 0 · 94 ms

stdout:

````text
memory: 0 facts recalled in 3.6 ms, as of 2026-09-28
(no memory matches for this prompt)
````

### L12 · RAG: Mileage rate

`python rag/search.py "what is the mileage rate"` · started 22:04:42.540 · exit 0 · 1,603 ms

stdout:

````text
1. [expenses.md § Expenses]  legs: keyword+meaning
   # Expenses
   
   Keep receipts for everything. Photos are fine, screenshots of banking apps are not.
   
   Anything under £100: spend it, log it, claim it monthly. Between £100 and £500: log it in advance where you can. Any single expense over £500 needs approval from your manager before you spend, no exceptions, and Dee will bounce claims that skipped it.
   
   Mileage at the HMRC rate. No alcohol on expenses at customer meetings.

2. [supplier-notes.md § Suppliers — working notes]  legs: meaning
   # Suppliers — working notes
   
   Couriers: current contract to September. The January delivery issues are credited on the February invoice; chase if the credit isn't showing.
   
   Packaging: two quotes in, waiting on a third. Anything we commit over £2,000 needs Alex's sign-off first.
   
   Helpdesk software: renews in June, seats increased to 8. Dee has the payment schedule.

3. [brand-voice.md § Brand voice, one page]  legs: meaning
   # Brand voice, one page
   
   We sound like a competent friend, not a corporation and not a mate at the pub. Plain words beat clever ones. We never say "utilise", "reach out", or "as per".
   
   We admit mistakes fast and specifically. "We sent the wrong size and we're sorry" beats any apology template ever written.
   
   Numbers over adjectives: "delivered in 2 days" not "lightning-fast delivery".
````

### L13 · RAG: Talk to customers in writing

`python rag/search.py "how do we talk to customers in writing"` · started 22:04:44.142 · exit 0 · 1,501 ms

stdout:

````text
1. [customer-ops-handbook.md § Tone of voice]  legs: meaning
   · Partial refunds follow the same thresholds as full ones. Goodwill credits under £50 are at the agent's discretion, once per customer per quarter.
   · 
   · ## Complaints
   · 
   · A complaint that isn't resolved after two replies escalates to the support lead. If a customer uses the word "legal" or mentions a regulator, escalate immediately regardless of reply count.
   · 
   ## Tone of voice
   
   Plain words. Short sentences. Never blame the customer, the courier, or "the system". Read your reply out loud before sending; if you wouldn't say it across a counter, rewrite it.

2. [it-setup.md § New starter IT setup]  legs: keyword
   # New starter IT setup
   
   Day one: email, helpdesk seat, shared drive, password manager. Ask Marcus for the checklist; don't improvise access levels.
   
   Laptops are ordered the week before start date. Everyone gets the standard build; exceptions need a reason in writing.
   
   Leavers: access revoked same day, hardware back within a week.

3. [brand-voice.md § Brand voice, one page]  legs: meaning
   # Brand voice, one page
   
   We sound like a competent friend, not a corporation and not a mate at the pub. Plain words beat clever ones. We never say "utilise", "reach out", or "as per".
   
   We admit mistakes fast and specifically. "We sent the wrong size and we're sorry" beats any apology template ever written.
   
   Numbers over adjectives: "delivered in 2 days" not "lightning-fast delivery".
````

### L14 · RAG: Sign-off while Sarah is away

`python rag/search.py "who has sign-off while Sarah is away"` · started 22:04:45.635 · exit 0 · 1,543 ms

stdout:

````text
1. [ooo-march-sarah.md § distilled]  legs: keyword+meaning
   who has sign-off while Sarah is away in March?
   who is covering for Sarah during her sabbatical?
   Sarah is out for all of March; Marcus holds her authority.
   Marcus has full authority on ops decisions for March.
   anything that needs my sign-off goes to Marcus

2. [ooo-march-sarah.md § ooo-march-sarah]  legs: keyword+meaning
   Subject: Out of office — March
   
   Hi all,
   
   I'm away from the 1st to the 31st of March (finally taking the sabbatical month).
   
   While I'm out, anything that needs my sign-off goes to Marcus — he has full authority on ops decisions for the month, so please don't queue things up waiting for me. Genuine emergencies: Alex knows how to reach me.
   
   Supplier renewals for Q2 are already approved and with Dee.
   
   See you in April,
   Sarah

3. [team.md § Who's who]  legs: keyword+meaning
   # Who's who
   
   - Alex Doyle — founder. Pricing, partnerships, anything customer-facing that commits us publicly.
   - Sarah Chen — runs operations day to day (the Operations Manager). Budgets, sign-offs, supplier relationships.
   - Priya Patel — support lead. Owns the rota, handles escalations, writes the monthly support report.
   - Marcus Webb — operations analyst. Reporting, process docs, covers for Sarah when she's away.
   - Dee (freelance) — bookkeeping, two days a week.
````

### L15 · RAG: £800 refund in March

`python rag/search.py "A customer wants an £800 refund in March. Who signs it off?"` · started 22:04:47.189 · exit 0 · 1,476 ms

stdout:

````text
1. [customer-ops-handbook.md § distilled]  legs: keyword+meaning
   who signs off refunds over £500?
   how fast should a refund be processed?
   Agents refund up to £500 within 48 hours; bigger refunds need the Operations Manager.
   Refunds over £500 need Operations Manager sign-off before Finance pays.
   Any refund exceeding £500 must be signed off by the Operations Manager before Finance releases the payment.

2. [newsletter-march-draft.md § March newsletter — draft 2]  legs: keyword+meaning
   # March newsletter — draft 2
   
   Subject line options:
   - "Spring cleaning, the useful kind"
   - "What we fixed in February"
   
   Body: lead with the courier fix and the new refund guarantee ("if it's our fault, your money's back within 48 hours, no forms"). Middle section: customer story (the bakery, pending their sign-off on the quote). Close: April webinar plug.
   
   Do not send before the pricing page is updated. Check with Alex.

3. [customer-ops-handbook.md § Refunds and credits]  legs: keyword+meaning
   · ## Tickets
   · 
   · Every ticket gets a first reply within one business day. If you can resolve it in the first reply, do. If a ticket needs someone else's input, say who you're asking and when you'll be back. Nothing sits unanswered over a weekend without a holding reply.
   · 
   · Tag tickets properly. The monthly report is built from tags and untagged tickets make the numbers lie.
   · 
   ## Refunds and credits
   
   We'd rather refund quickly than argue slowly. If the product didn't do what we said it would, the customer gets their money back, no forms.
   
   For amounts up to £500, any support agent can process the refund directly, and it should be done within 48 hours of the request. Any refund exceeding £500 must be signed off by the Operations Manager before Finance releases the payment. Refunds always go back to the original payment method; we don't do bank transfers or credit-in-lieu unless the original method no longer exists.
   
   Partial refunds follow the same thresholds as full ones. Goodwill credits under £50 are at the agent's discretion, once per customer per quarter.
   
   · ## Complaints
   · 
   · A complaint that isn't resolved after two replies escalates to the support lead. If a customer uses the word "legal" or mentions a regulator, escalate immediately regardless of reply count.
   · 
   · ## Tone of voice
   ·
````

### L16 · Graph prompt hook

`python src/recall_hook.py` · started 22:04:48.666 · exit 0 · 103 ms

stdin:

````text
{"prompt": "A customer wants an £800 refund in March. Who signs it off?"}
````

stdout:

````text
{"systemMessage": "memory: 8 facts recalled in 7.2 ms, for March 2026", "hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": "memory: 8 facts, for March 2026\nThese facts come from your documents (9, extracted 2026-09-24). Quoted lines are the documents' own words, checked against the files just now: answer from them, and open a file only if its line says it changed or is missing.\nRefund approvals approved_by Ops Manager [refund-policy.md] (from 2026-01-01)\nCustomer support SOP references Refund approvals [customer-support-sop.md]\nOps Manager held_by Sarah Chen [org-chart.md]\nOnboarding process references Ops Manager [onboarding-process.md]\nCustomer support SOP references Support Lead [customer-support-sop.md]\nSarah Chen delegates_to Marcus Webb [delegation-memo.md] (2026-03-01 to 2026-03-31)\nSupport Lead held_by Priya Patel [org-chart.md]\nIncident response references Support Lead [incident-response.md]\nwhere:\nCustomer support SOP: Support agents answer tickets within one business day\nCustomer support SOP: \"Refunds under the approval threshold in the refund approvals policy are processed directly by the agent.\" [customer-support-sop.md]\nMarcus Webb: \"During this period all of her sign-offs and approvals are delegated to Marcus Webb.\" [delegation-memo.md] (2026-03-01 to 2026-03-31)\nOps Manager: \"Ops Manager: Sarah Chen. Owns day-to-day operations, budgets and sign-offs.\" [org-chart.md]\nOps Manager: Approves refunds over \u00a3500 (from 2026-01-01)\nRefund approvals: \"Superseded on 1 January 2026 by the current refund approvals policy.\" [refund-policy-2024.md]\nRefund approvals: \"Refunds over \u00a3500 require approval by the Ops Manager before payment is released.\" [refund-policy.md] (from 2026-01-01)\nRefund approvals: \"Standard refunds under \u00a3500 are processed by any support agent within 48 hours.\" [refund-policy.md] (from 2026-01-01)\nRefund approvals: \"Approved refunds are paid back to the original payment method only.\" [refund-policy.md] (from 2026-01-01)\nSarah Chen: The Ops Manager\nSarah Chen: \"Sarah Chen is on leave from 1 to 31 March 2026.\" [delegation-memo.md] (2026-03-01 to 2026-03-31)"}}
````

additionalContext, decoded:

````text
memory: 8 facts, for March 2026
These facts come from your documents (9, extracted 2026-09-24). Quoted lines are the documents' own words, checked against the files just now: answer from them, and open a file only if its line says it changed or is missing.
Refund approvals approved_by Ops Manager [refund-policy.md] (from 2026-01-01)
Customer support SOP references Refund approvals [customer-support-sop.md]
Ops Manager held_by Sarah Chen [org-chart.md]
Onboarding process references Ops Manager [onboarding-process.md]
Customer support SOP references Support Lead [customer-support-sop.md]
Sarah Chen delegates_to Marcus Webb [delegation-memo.md] (2026-03-01 to 2026-03-31)
Support Lead held_by Priya Patel [org-chart.md]
Incident response references Support Lead [incident-response.md]
where:
Customer support SOP: Support agents answer tickets within one business day
Customer support SOP: "Refunds under the approval threshold in the refund approvals policy are processed directly by the agent." [customer-support-sop.md]
Marcus Webb: "During this period all of her sign-offs and approvals are delegated to Marcus Webb." [delegation-memo.md] (2026-03-01 to 2026-03-31)
Ops Manager: "Ops Manager: Sarah Chen. Owns day-to-day operations, budgets and sign-offs." [org-chart.md]
Ops Manager: Approves refunds over £500 (from 2026-01-01)
Refund approvals: "Superseded on 1 January 2026 by the current refund approvals policy." [refund-policy-2024.md]
Refund approvals: "Refunds over £500 require approval by the Ops Manager before payment is released." [refund-policy.md] (from 2026-01-01)
Refund approvals: "Standard refunds under £500 are processed by any support agent within 48 hours." [refund-policy.md] (from 2026-01-01)
Refund approvals: "Approved refunds are paid back to the original payment method only." [refund-policy.md] (from 2026-01-01)
Sarah Chen: The Ops Manager
Sarah Chen: "Sarah Chen is on leave from 1 to 31 March 2026." [delegation-memo.md] (2026-03-01 to 2026-03-31)
````

### L17 · RAG prompt hook

`python rag/recall_hook.py` · started 22:04:48.761 · exit 0 · 1,444 ms

stdin:

````text
{"prompt": "A customer wants an £800 refund in March. Who signs it off?"}
````

stdout:

````text
{"systemMessage": "memory: 4 hits", "hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": "From your notes:\n\n[customer-ops-handbook.md \u00a7 distilled]\nwho signs off refunds over \u00a3500? how fast should a refund be processed? Agents refund up to \u00a3500 within 48 hours; bigger refunds need the Operations Manager. Refunds over \u00a3500 need Operations Manager sign-off before Finance pays. Any refund exceeding \u00a3500 must be signed off by th...\n\n[newsletter-march-draft.md \u00a7 March newsletter \u2014 draft 2]\n# March newsletter \u2014 draft 2 Subject line options: - \"Spring cleaning, the useful kind\" - \"What we fixed in February\" Body: lead with the courier fix and the new refund guarantee (\"if it's our fault, your money's back within 48 hours, no forms\"). Middle section: customer story (t...\n\n[customer-ops-handbook.md \u00a7 Refunds and credits]\n## Refunds and credits We'd rather refund quickly than argue slowly. If the product didn't do what we said it would, the customer gets their money back, no forms. For amounts up to \u00a3500, any support agent can process the refund directly, and it should be done within 48 hours of t...\n\n[ooo-march-sarah.md \u00a7 distilled]\nwho has sign-off while Sarah is away in March? who is covering for Sarah during her sabbatical? Sarah is out for all of March; Marcus holds her authority. Marcus has full authority on ops decisions for March. anything that needs my sign-off goes to Marcus"}}
````

additionalContext, decoded:

````text
From your notes:

[customer-ops-handbook.md § distilled]
who signs off refunds over £500? how fast should a refund be processed? Agents refund up to £500 within 48 hours; bigger refunds need the Operations Manager. Refunds over £500 need Operations Manager sign-off before Finance pays. Any refund exceeding £500 must be signed off by th...

[newsletter-march-draft.md § March newsletter — draft 2]
# March newsletter — draft 2 Subject line options: - "Spring cleaning, the useful kind" - "What we fixed in February" Body: lead with the courier fix and the new refund guarantee ("if it's our fault, your money's back within 48 hours, no forms"). Middle section: customer story (t...

[customer-ops-handbook.md § Refunds and credits]
## Refunds and credits We'd rather refund quickly than argue slowly. If the product didn't do what we said it would, the customer gets their money back, no forms. For amounts up to £500, any support agent can process the refund directly, and it should be done within 48 hours of t...

[ooo-march-sarah.md § distilled]
who has sign-off while Sarah is away in March? who is covering for Sarah during her sabbatical? Sarah is out for all of March; Marcus holds her authority. Marcus has full authority on ops decisions for March. anything that needs my sign-off goes to Marcus
````

### L18 · Graph prompt hook, a question outside the graph

`python src/recall_hook.py` · started 22:04:50.212 · exit 0 · 1,417 ms

stdin:

````text
{"prompt": "Who is in charge when the boss is away?"}
````

stdout:

````text
{"systemMessage": "memory: 0 facts recalled in 3.6 ms, as of 2026-09-28; 3 passages from your notes", "hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": "memory: 0 facts, as of 2026-09-28\n(no memory matches for this prompt)\nPassages from your notes that may help. These are search results, not checked facts:\n[team.md \u00a7 Who's who] # Who's who - Alex Doyle \u2014 founder. Pricing, partnerships, anything customer-facing that commits us publicly. - Sarah Chen \u2014 runs operations day to day (the Operations Manager). Budgets, sign-offs, supplier relationships. - Priya Patel \u2014 support lead. Owns the rota, handles escalations, writes the m...\n[ooo-march-sarah.md \u00a7 distilled] who has sign-off while Sarah is away in March? who is covering for Sarah during her sabbatical? Sarah is out for all of March; Marcus holds her authority. Marcus has full authority on ops decisions for March. anything that needs my sign-off goes to Marcus\n[ooo-march-sarah.md \u00a7 ooo-march-sarah] Subject: Out of office \u2014 March Hi all, I'm away from the 1st to the 31st of March (finally taking the sabbatical month). While I'm out, anything that needs my sign-off goes to Marcus \u2014 he has full authority on ops decisions for the month, so please don't queue things up waiting for me. Genuine emerg..."}}
````

additionalContext, decoded:

````text
memory: 0 facts, as of 2026-09-28
(no memory matches for this prompt)
Passages from your notes that may help. These are search results, not checked facts:
[team.md § Who's who] # Who's who - Alex Doyle — founder. Pricing, partnerships, anything customer-facing that commits us publicly. - Sarah Chen — runs operations day to day (the Operations Manager). Budgets, sign-offs, supplier relationships. - Priya Patel — support lead. Owns the rota, handles escalations, writes the m...
[ooo-march-sarah.md § distilled] who has sign-off while Sarah is away in March? who is covering for Sarah during her sabbatical? Sarah is out for all of March; Marcus holds her authority. Marcus has full authority on ops decisions for March. anything that needs my sign-off goes to Marcus
[ooo-march-sarah.md § ooo-march-sarah] Subject: Out of office — March Hi all, I'm away from the 1st to the 31st of March (finally taking the sabbatical month). While I'm out, anything that needs my sign-off goes to Marcus — he has full authority on ops decisions for the month, so please don't queue things up waiting for me. Genuine emerg...
````
