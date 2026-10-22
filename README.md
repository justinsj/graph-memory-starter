# graph-memory-starter

A knowledge graph your AI assistant reads before it answers.
Three SQLite tables and their indexes, one prompt hook. No server, no API key.
Purpose: demonstrate the design's effectiveness so you can apply it to your own system.

## Which one

    rag/    works on notes as they are, matches meaning when words differ
    graph   modelled docs, typed links, multi-hop answers walked by code

Start with rag/. Move up when your questions chain facts across
documents and you are willing to model for it.

## Set up

Two pastes, both for Claude Code, opened in the folder you keep your notes in.
The first is the RAG. The second is the digest, which turns every session you
close into a note the RAG can find.

Check Python first. In a terminal, try `python3 --version`, then
`python --version`, then `py --version`. One of them prints a 3.x version. If
none does, install Python from python.org with "Add to PATH" ticked.

### Paste one, the RAG

```
Set up the memory starter for me, one step at a time, and stop if a step fails.
1. Check Python 3.10 or newer runs here (try python3, python, then py). If none runs, or the one that runs is older than 3.10, stop and tell me to install it from python.org with "Add to PATH" ticked.
2. Clone https://github.com/Glitch-Cat-Club/graph-memory-starter into a folder called memory-starter here, inside this folder and nowhere else (no git installed: download the zip from that page and unzip it as memory-starter). Then run: python -m pip install fastembed
3. Ask me which folder my markdown notes are in. Then run: python memory-starter/rag/build_index.py --corpus <that folder>
4. Run: python memory-starter/rag/search.py "a question about my notes" and show me the top hits.
5. Merge the recall hook from memory-starter/rag/hooks.json into .claude/settings.json here. Keep any permissions and model already in it. Use python3 in the hook command if that is the one that runs.
6. Tell me in five lines what you did, and how to rebuild the index when I add notes.
```

Then `/exit` and open Claude Code again, so the hook loads.

### Paste two, the digest

```
Add the digest to my memory starter, one step at a time, and stop if a step fails.
1. Merge the three hooks from memory-starter/digest/hooks.json into .claude/settings.json here. Keep everything already in it, including the recall hook from lesson 1. Use python3 in the hook commands if that is the one that runs.
2. Open memory-starter/digest/config.json. It ships as "session". If claude -p runs from this folder (try: claude -p "say ok"), set "mode" to "headless". If it does not, leave it and tell me.
3. Tell me in three lines where the daily log will land and how to switch the digest off.
```

Then `/exit` and open Claude Code again.

### Which model does what

    bge-small-en-v1.5   local, 67 MB, your CPU, no key. Turns text into a
                        384-dim vector for the meaning leg of the search. Downloaded
                        once on the first index build, by fastembed.
    Claude              distils a note into questions, writes the session
                        entry, answers you. Through claude -p on your
                        subscription, so no API key here either.

Markdown files, subfolders included. Hidden folders, `.git`, `node_modules`,
`__pycache__` and this starter's own folder are skipped, so a starter cloned
inside your notes never indexes itself.

### The two digest modes

    session    the filtered text waits in digest/pending/. Your next session
               hands it to a background sub-agent, so you carry on working.
    headless   the hook starts claude -p with no window. The entry lands about
               a minute later, and your next session opens clean.

One switch, `"mode"` in `digest/config.json`. Headless needs `claude` on your
PATH.

### The dials

All of them are one line in `digest/config.json`, apart from the voice, which
is `digest/digest-prompt.md`.

    max_turns    30       how much of the session is read
    max_chars    15000    the character budget, the end kept
    min_turns    5        below this the session is not memory
    model        sonnet   which Claude writes the entry
    log_dir      daily    the folder inside your notes the entry lands in
    distil       true     whether the entry feeds the index
    mode         session  session or headless

What is kept from a session is not a dial, it is code: your words and the
replies. Tool calls, results, file dumps and thinking are dropped before any
model reads it, so nothing is judged out by mistake.

### Switch it off

Take the hook entries back out of `.claude/settings.json`, the recall hook and
the three digest ones. Your notes, your logs and the index all stay, and the
index rebuilds any time.

### Time budgets for scripts, paste three

Optional, and separate from memory. A PreToolUse hook sends every data or test
command through a time budget, refuses to re-run an unchanged script that
overran, and wants database connections opened through `runguard/safe_db.py`,
which sets lock and statement timeouts and runs reads only.

```
Add the run guard from my memory starter, one step at a time, and stop if a step fails.
1. Merge the hook from memory-starter/runguard/hooks.json into .claude/settings.json here. Keep everything already in it. Use python3 in the hook command if that is the one that runs.
2. Copy memory-starter/runguard/skill/script-preflight into .claude/skills/ here, so the folder is .claude/skills/script-preflight/SKILL.md.
3. Run: python -m unittest discover -s memory-starter/tests -p test_runguard.py and show me the last line.
4. Tell me in three lines how to run a script with a budget, where the ledger is, and how to switch from warn to block.
```

It ships in warn mode: commands run, and the model is told what was wrong.
After a week, `python memory-starter/runguard/ledger.py report --all` shows
what it caught; set `"mode": "block"` in `runguard/config.json` to enforce.
How each database is protected, and the limits: `runguard/README.md`.

## Prerequisites

Python 3, SQLite included. Claude Code, or another assistant with prompt hooks.
For the meaning leg of the search, `python -m pip install fastembed`. Without
it the search runs keyword only and says so. The graph half needs nothing
installed.

## Layout

    rag/               the semantic layer: index, search, recall hook, distil
    digest/            the session write up: hooks, config, prompt
    runguard/          time budgets for scripts and tests, the re-run block, safe read-only DB connections, /script-preflight
    projects/          projects from requests, meetings and sessions: records, plans, cases, evals
    commands/          /project-new, /project-plan, /project-review, copy into .claude/commands/
    skills/            /pr-review-loop, response-format and question-format, copy into .claude/skills/
    openspec-rules/    pre-answered OpenSpec questions, decisions.md and mockups, with the script that patches OpenSpec's skills
    sessionmerge/      /merge-session: the handoff script and its skill
    codegraph/         a codebase in the graph: the indexer, a sample shop, eleven code questions
    querygraph/        a company's own database queries: five cases on four databases, the indexer to come
    corpus/            8 modelled docs (front matter)
    corpus-before/     12 unstructured docs (the A/B control)
    extraction/        LLM output per doc: nodes, edges, aliases
    src/               schema.sql, build_graph.py, recall.py, recall_hook.py
    tests/             the test suite, standard library only
    bench/             recall timings and the live eval, with their reports
    docs/              the Sep 2026 review: claim check, improvement proposals
    hooks.json         the graph hooks (recall, forget, warm model, project notice), copy into .claude/settings.json
    claude-md-snippet.md  one paragraph for CLAUDE.md where you work
    extract-prompt.md  the extraction prompt, for your own docs

## Modelling

Ontology: a closed vocabulary, fixed before writing any doc.
Entity types: PERSON, ROLE, POLICY, PROCESS, DOCUMENT.
Relationships: approved_by, held_by, delegates_to, part_of, references.
Claim kinds: threshold, deadline, availability, unknown, responsibility, rule, note.
Logical model: entities with hashed identity (uuid5 of type + name); claims
about them, one sentence each, with the source's own words (a quote the build
checks) and the dates they hold for when the source gives them; typed
relations carrying their source doc and dates; names and aliases in one table,
each alias kept as the extraction wrote it. What a document leaves open, like
a role nobody is named for, is an unknown claim. Each doc declares its type,
entities and links in front matter.
Apply the same design to your own docs; your AI assistant can do the extraction.

## Run

    python src/build_graph.py
    python src/recall.py "A customer wants an £800 refund in March. Who signs it off?"

Wire hooks.json and the same lookup runs before every prompt, injected as context.
The build stops if one name has two types: links name their ends without one.
It also stops on an unknown claim kind, a date that is not YYYY-MM-DD, two
versions of a threshold or an absence whose dates overlap, or a quote its
document does not contain. It warns about gaps a question would fall into: a
role nobody holds, an entity nothing is said about.

## Recall

`src/recall.py` answers in six steps, all SQLite, no model:

    when        the dates the question is about: a day, month or year it
                names, today when it names none, all dates for "how has it
                changed"; facts that do not hold then are left out
    names       the question's word runs, looked up in an index of every
                name and alias
    relevance   full-text search (FTS5) over every entity; rare words weigh
                more, so "March" outweighs "sign"
    walk        3 hops, one indexed query per node, at most 3 links of each
                type, the most relevant first, so a busy node cannot flood it
    rank        relevance, people and distance; the top 8 facts, each with
                its chain back to a name in the question, and the claims that
                hold about what the question concerns
    sources     each claim in the documents' own words where the budget allows,
                up to 8 quotes and 2,000 characters (about 700 tokens), checked
                against the files as they are now: a changed or missing file
                is marked on its line

It stops at 500 ms and says so, rather than letting the hook time out
silently. The dials are the constants at the top of `src/recall.py`. The
indexes are built with the graph, so rebuild after pulling a new version.

The quotes are there so the model has no reason to go and read the files. A
line under the header says the facts come from your documents, when they were
extracted, and to open a file only if its line says it changed or is missing.
Within one conversation a quote is sent once: `hooks.json` also runs the hook
with `--forget` before compaction and on a cleared session, when the
conversation loses what it was shown. Add `claude-md-snippet.md` to CLAUDE.md
in the folder you work in, so the model reads the same rule as project
guidance. It is the biggest lever: with a prompt pointing at the documents,
Sonnet 5 searched them in 2 of 11 live runs with the rule, 9 of 11 without. See `docs/why-the-model-rereads.html` for why this matters, and
`docs/rereads-fix-results.html` and `docs/rereads-fix-results-2.html` for
what it changed.

When the question names nothing the graph knows, the hook still says so, then
adds up to three passages from the RAG index (`rag/rag.db`), labelled as
search results rather than checked facts. No index, and the loud line stands
alone. Searching needs the embedding model, about 1.5 s to load, so `hooks.json`
also starts the warm one from `rag/embedder.py` when a session starts: the
fallback then takes 0.1–0.2 s. With no index it does not start.

The injection is compact, one fact per line. To read it aligned:

    python src/recall.py --pretty "What does Priya do?"

Point it at another graph with the `GRAPH_MEMORY_DB` environment variable.

## Test cases

| Question | Expected | Why |
|---|---|---|
| A customer wants an £800 refund in March. Who signs it off? | Marcus Webb | 3 hops: policy, role, holder, delegate |
| Who approves supplier payments over £2,000? | Alex Doyle | 2 hops: policy, role, holder |
| What is the onboarding process? | Ops Manager, day-one checklist | 1 hop, several edges |
| What does Priya do? | Support Lead | alias seeding |
| Who is in charge when the boss is away? | no memory matches, then passages from your notes | outside the vocabulary; says so, never guesses, and hands over labelled search results |

The same five and more, as code: questions about dates (see Dates and
amendments), source quotes and changed files, the graph grown to 30,013
entities, the hooks as Claude Code runs them, the build, and the RAG cases
(those need fastembed and skip without it).
Nothing else to install.

    python -m unittest discover tests

To time recall as the graph grows, `python bench/recall_bench.py`; it writes
`bench/recall-report.md`. To rerun the evals below live, `python
bench/live_eval.py`; it spends a little model usage and writes
`bench/live-report.md`.

## Dates and amendments

Facts change. The refund policy did: until 31 December 2025, refunds over £250
needed a Director; from 1 January 2026, refunds over £500 need the Ops Manager.
Both versions are in the graph, as claims with dates, and so is Sarah Chen's
leave, 1-31 March 2026, with the delegation to Marcus Webb that lasts as long.
Recall keeps only what holds in the period the question is about.

| Question | Period | Facts that decide it | Answer |
|---|---|---|---|
| A customer wants an £800 refund in March. Who signs it off? | March 2026 | over £500 needs the Ops Manager; Sarah Chen is on leave and delegates to Marcus Webb | Marcus Webb |
| A customer wants an £800 refund in April 2026. Who signs it off? | April 2026 | over £500 needs the Ops Manager, held by Sarah Chen; the cover has ended | Sarah Chen |
| Who approves a £300 refund in June 2025? | June 2025 | over £250 needed a Director, until 31 December 2025 | a Director |
| Who approves a £300 refund? | today | under £500, any support agent, within 48 hours | any support agent |
| What was the refund approval threshold in 2025? | 2025 | over £250 needed a Director | £250 |
| How has the refund approval threshold changed? | all dates | £250 and a Director until 2025-12-31; £500 and the Ops Manager from 2026-01-01 | £250, then £500 from 1 January 2026 |
| Who approves supplier payments over £2,000 in 2025? | 2025 | undated facts hold at any date | Alex Doyle, the Founder |

A month without a year means this year's. "since", "after", "before" and
"until" leave the period open at one end. Each row is a test in
`tests/test_dates.py`, run as of 23 September 2026. What the model gets for
the history question, trimmed:

    memory: 8 facts recalled in 3.3 ms, for all dates
    Refund approvals approved_by Director [refund-policy-2024.md] (until 2025-12-31)
    Refund approvals approved_by Ops Manager [refund-policy.md] (from 2026-01-01)
    ...
    where:
    Refund approvals: Refunds over £250 need Director approval (until 2025-12-31)
    Refund approvals: Refunds over £500 need Ops Manager approval before payment is released (from 2026-01-01)
    ...

Claims live in their own table, `claims`, with a foreign key to `entities`:
one sentence each, a kind, an optional amount, and `valid_from` / `valid_to`
(the first day a claim holds, and the first day it no longer does). Links in
`relations` carry the same two dates. A claim or link with no dates always
holds. To record an amendment, add the new document and give each version the
dates it holds for; `extract-prompt.md` asks for them.

## Projects

The graph holds projects as well as documents. A request, a meeting
transcript or a session write-up goes in. Claude proposes the changes it makes,
each quoting the input, and code checks them:
- a quote the input does not contain is refused;
- so is a date it does not state, a status move outside the table, a name the
  graph does not know, or a plan read from a meeting.

You apply or reject what is left. A plan comes only from a discussion with you,
and Claude researches before it asks. Once recorded, a project is an entity like
any other: "What's the status of the helpdesk migration?", "Who signs off its
contract?" (walked through the supplier payments policy to Alex Doyle) and
"What's blocked?" are answered from the graph before the model starts.

    python projects/ingest.py path/to/2026-09-24-meeting.md    # propose; nothing applied
    python projects/review.py                                  # what is waiting; --apply, --reject
    python projects/status.py <id> "why" --status blocked      # a quick change, in your words

Copy `commands/` into `.claude/commands/` for `/project-new`, `/project-plan`
and `/project-review`. Records live in `projects/records/`, one JSON file per
project with its history beside it, and the build loads them. How it works,
the seven worked cases and their evals: `projects/README.md`.

Measured on eight project questions, both models, told where the documents are
(`bench/project_eval.py --hint`): the model searching the files itself got 29
of 32 right in 12.0 s on average; through the graph, 32 of 32 in 4.5 s, with no
tool calls. Asked plainly, searching got 22 of 32, often answering "no
information" without looking (`docs/projects-results.html`).

## Code

The graph can hold a codebase too, indexed with no model:

    python src/build_graph.py --code path/to/repo

Functions, tests, constants, files, routes, the branches a request body picks,
and buttons become entities. What reaches what becomes links: calls, imports,
callbacks, lookup tables and requests. Each link keeps the line where it
happens, checked against the file. For code a question names, the hook traces
both ways to the end of the chain, whatever the wording:
- forward, from a button through a URL built from constants in another file to
  the route, the branch its body value picks, and the constant that decides;
- back, from a function to every caller, importer, test and callback, and on to
  every endpoint and screen a change would reach, with each call's line.

For a handler, it also shows each client's body line and the fields the
handler reads. No dependent is left out for space. A symbol nothing reaches is
said to be unreached. Names match in any style: `needs_approval`,
`needsApproval` and "needs approval" are one name. Python and TypeScript, with
the limits and the sixteen worked questions, are in `codegraph/README.md`.

## Service

The same graph as a hosted service (`kl/`), shared by teams in separate
workspaces, on Postgres or SQLite:

    pip install -r requirements-service.txt
    python -m kl init --workspace acme --name "Acme Ltd" --admin-email you@acme.example --admin-name You
    python -m kl serve --port 8080      # REST at /v1, OpenAPI at /openapi.json, MCP at /mcp

- **Files in.** Input handlers send any set of files. They are deduplicated
  (the same bytes, the same text, a new version, a near copy), extracted, and
  checked against their text before they reach the graph.
- **Projects out.** A task app reads the approved projects. Every edit,
  whoever makes it, is a change request a person approves.
- **Plans run anywhere.** Deliverables have plans, as graphs of tasks, and can
  be imported from OpenSpec changes. An execution platform leases tasks to its
  machines and injects each run's token beside its own credentials. Any agent
  then works the task through REST or MCP.

The answers are the ones the hook gives: each workspace's graph is built by
`src/build_graph.py` from the service's log. Guide:
`docs/api-guide.html`. Reference: `docs/api-reference.html`. Internals:
`kl/README.md`. The Claude Code hook asks the service when `KL_API_URL` and
`KL_API_KEY` are set, and answers in-process when it cannot reach it.

## Evals

Glitch Cat Club evals, Aug 2026. One question, three model tiers, two conditions.
The answer needs a 3-hop chain: policy -> role -> holder -> delegate.

Search condition: ask in corpus-before/, no hook. Tooling: the model drives
Grep and Read itself.
Graph condition: wire hooks.json and ask. Tooling: indexed SQLite queries run
inside the hook before the model is invoked; the model receives the result as
text. Reproduce both yourself, or run `python bench/live_eval.py`.

| Model   | Condition | Tooling          | Result  | Hops reached | Tool calls | Docs read | Context read |
|---------|-----------|------------------|---------|-------------:|-----------:|----------:|-------------:|
| Fable 5 | search    | Grep+Read, model | correct |       3 of 3 |          6 |         4 |  ~780 tokens |
| Fable 5 | graph     | SQL walk, code   | correct |       3 of 3 |          0 |         0 |  ~400 tokens |
| Sonnet  | search    | Grep+Read, model | correct |       3 of 3 |         13 |         8 | ~1180 tokens |
| Sonnet  | graph     | SQL walk, code   | correct |       3 of 3 |          0 |         0 |  ~400 tokens |
| Haiku   | search    | Grep+Read, model | wrong   |       1 of 3 |          5 |         3 |  ~660 tokens |
| Haiku   | graph     | SQL walk, code   | correct |       3 of 3 |          0 |         0 |  ~400 tokens |

Re-measured in Sep 2026 (`bench/recall-report.md`, `bench/live-report.md`,
`docs/claim-check.html`). Recall takes about 3 ms per query: 3.5 ms at 30,014
entities, 48 ms with 10,000 links on one node. The hook as a whole takes about
140 ms inside Claude Code, most of it starting Python. The injection is capped
at 8 facts, plus the claims that hold about what the question concerns and up
to 2,000 characters of source quotes; for the refund question it is 1,990
characters, 644 input tokens on Haiku 4.5 and 836 on Sonnet 5. Headless
runs: searching took 10-16 s, almost
all of it model turns (the tools ran for about 0.1 s), and the graph answer
4-6 s. The first answer word comes one model turn, 2-4 s, after the recall line.

In the graph condition the model does no retrieval. Zero tool calls, zero
searching, zero multi-hop reasoning: the traversal ran as code before the model
was invoked, and the model reads the injected facts and states the answer.
Proof: the smallest model reaches 1 of 3 hops searching, and 3 of 3 through the
graph, because the graph walks the hops, never the model. Two places a model
still exists: one call speaks the final answer, and a strong model built the
graph once at write time. Spend intelligence at build; answer from structure.

In the Sep 2026 re-run, Haiku 4.5 found the answer by searching when told the
docs were in the folder, and without that it did not search at all; through
the graph it was right every time. Told the docs were there, Sonnet 5 re-read
them despite the injection, which cost the time the graph saves, until the rule
from `claude-md-snippet.md` was in CLAUDE.md: then it answered from the facts in
9 of 11 runs, and opened a file only where the documents leave a gap or the
graph had no match (`docs/rereads-fix-results-2.html`).
