"""Live: a meeting transcript to a full project and its thesis, through the graph or by searching the documents, timed.

    python bench/project_create_eval.py                        # sonnet, 3 runs of each
    python bench/project_create_eval.py --models haiku,sonnet --reps 3
    python bench/project_create_eval.py --build                # also time building the graph's facts
    python bench/project_create_eval.py --regrade              # grade the saved runs again, no calls
    python bench/project_create_eval.py --models haiku --no-thinking --append   # thinking off, added to the saved runs
    python bench/project_create_eval.py --reps 20 --profile --tag steps          # every step of the graph route timed

Case 01 (projects/cases/01-new-project), in the workspace docs/project-creation-example.html shows: the nine
corpus documents and support-metrics.md, no projects. Today is pinned to 28 September 2026.

    graph    The service, with the claude-cli extractor. The transcript goes in with no change set; the
             extraction call proposes one (and a repair round runs if the checks refuse it); change request 1
             is approved; the impact research runs (the thesis call, then each number looked up in the graph
             or asked of a person); change request 2 is approved. The graph was built beforehand, from the
             repo's recorded extractions: --build times building it with the model.
    fast-merged, fast-parallel
             The service with the speed-ups: lean calls (no tools, the instructions as the system prompt, no
             settings), the thesis drafted before review (in the change set's own call, or in a second call at the
             same time) and opened as change request 2 beside change request 1, and no graph rebuilds (what the
             process changes is saved as a pending diff). Both requests are approved, as in the graph route.
    preloaded-merged, preloaded-parallel
             The same, and each call told that what it is given is all there is (preload_note): every project,
             every name, every figure the graph holds. fast-* runs without that note, as they were measured.
    search   One claude -p run in a folder holding the same ten documents, with Grep, Read and Glob. It gets the
             same instructions (projects/ingest-prompt.md and projects/thesis-prompt.md) and the transcript, but
             no graph: it finds the names, the rules and the numbers itself, and answers in one JSON object.

Approvals are instant here: the time a person takes to review is left out of both. Every claude -p call runs with
user and project settings and MCP servers off (--setting-sources local --strict-mcp-config), in a folder of its
own, so neither condition pays for anything the other does not. The graph condition's calls are otherwise the
service's own: its prompt, its payload, no tool limits.

claude -p leaves extended thinking to the model: Haiku 4.5 thought at length on every call here, Sonnet 5.5
briefly on some. --no-thinking sets MAX_THINKING_TOKENS=0 for every call, and labels the runs "<model>-nothink".

Both outputs are graded by the same code: the service's checks (model.validate) and the case's expectations
(cases.check) on the change set; the thesis's "because" quote in the transcript; and each number said to be found
checked in the file it cites, its value in its quote.

Writes bench/project-create-report.md, and the event streams and outcomes to bench/project-create-raw/.
Spends 2 to 3 claude -p calls a graph run, 1 a search run, and 10 for --build (per model).
"""
import argparse
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["GRAPH_MEMORY_TODAY"] = "2026-09-28"
sys.path[:0] = [str(ROOT), str(ROOT / "src"), str(ROOT / "tests"), str(ROOT / "projects")]
import kl_support as ks  # noqa: E402
import cases  # noqa: E402
import ingest  # noqa: E402
import model  # noqa: E402
from kl.extractors import PROMPT as EXTRACT_PROMPT, THESIS_PROMPT, ClaudeCliExtractor, FixtureExtractor  # noqa: E402

OUT = ROOT / "bench" / "project-create-report.md"
RAW = ROOT / "bench" / "project-create-raw"
FIX = ROOT / "tests" / "fixtures" / "impact"
INGEST_PROMPT = ROOT / "projects" / "ingest-prompt.md"
CASE = cases.load(ROOT / "projects" / "cases" / "01-new-project")
NAME = "2026-09-14-support-tooling-review.md"
ON = "2026-09-14"
DOCS = sorted(ROOT.glob("corpus/*.md")) + [FIX / "support-metrics.md"]
THINKING = None  # MAX_THINKING_TOKENS for every call; None leaves claude -p's default
PROFILE = False  # time the service's own steps in the graph route (--profile)
CALL_TIMEOUT = 600  # s: a call still open after this is stopped, as the service's own extractor stops it
STATED = {11.0, 4.0, 1240.0}  # the figures support-metrics.md states that the thesis can use; 380 a week is not one
SEARCH_TASK = """You have two jobs, both about the meeting transcript at the end. The company's documents are in \
this folder: search them with Grep, Read and Glob. They are the only source of names, rules and numbers.

Answer with one JSON object and nothing else:

{"changes": [ ... ], "thesis": { ... }, "numbers": [ ... ]}

- "changes": the project changes the transcript makes, as Part A says. Where Part A speaks of the names the graph
  knows, use the names as the documents write them.
- "thesis": the thesis for the project those changes create, as Part B says. Where Part B speaks of facts from the
  knowledge graph, use the documents.
- "numbers": one entry for each number in the thesis's formula and reach. When a document states it:
  {"key": ..., "status": "found", "value": <the number>, "source": "<file name>", "quote": "<the line stating it,
  word for word>"}. When none does: {"key": ..., "status": "asked", "ask": "<the person to ask>", "question": ...}.
  Never guess a number.

# Part A

{ingest}

# Part B

{thesis}

---

Input: {name}
Kind: transcript
Date: {on}

Projects this input may be about:
(none yet)

The input:

{text}"""


# ---- one claude -p call, every stream event timed -----------------------------------------------------------------

def claude_argv():
    exe = shutil.which("claude")
    if exe is None:
        sys.exit("claude is not on the PATH")
    return ["cmd", "/c", exe] if exe.lower().endswith((".cmd", ".bat")) else [exe]


def kill_tree(p):
    """Stop a call and whatever it started: on Windows a child left holding the output pipe keeps the read open."""
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], capture_output=True)
    else:
        p.kill()


def call(model_name, stdin_text, cwd, tools=None, raw=None, system_prompt=None, no_tools=False):
    """One claude -p run in cwd. Returns its reply text and the numbers the report needs. system_prompt and
    no_tools: a lean call, as the service's extractor makes one."""
    argv = [*claude_argv(), "-p", "--model", model_name, "--output-format", "stream-json", "--verbose",
            "--include-partial-messages", "--setting-sources", "local", "--strict-mcp-config",
            "--no-session-persistence"]
    if tools:
        argv += ["--tools", tools, "--allowedTools", tools]
    elif no_tools:
        argv += ["--tools", ""]
    if system_prompt:
        argv += ["--system-prompt", system_prompt]
    env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE")}
    if THINKING is not None:
        env["MAX_THINKING_TOKENS"] = str(THINKING)
    t0 = time.perf_counter()
    p = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.DEVNULL)
    p.stdin.write(stdin_text.encode("utf-8"))
    p.stdin.close()
    stop = threading.Timer(CALL_TIMEOUT, kill_tree, args=(p,))  # a stalled stream would hold the whole bench
    stop.start()
    events = []
    for line in p.stdout:
        t = (time.perf_counter() - t0) * 1000
        try:
            events.append({"t": round(t, 1), "e": json.loads(line)})
        except ValueError:
            pass
    p.wait()
    stop.cancel()
    wall = (time.perf_counter() - t0) * 1000
    if raw:
        raw.parent.mkdir(parents=True, exist_ok=True)
        raw.write_text("\n".join(json.dumps(ev, ensure_ascii=False) for ev in events), encoding="utf-8")
    timed_out = {"timed_out": True} if wall >= CALL_TIMEOUT * 1000 else {}
    return {**summarise(events, wall), "t_start": t0, **timed_out}  # t_start: perf_counter, for --profile


def summarise(events, wall):
    out = {"wall_ms": round(wall), "first_token_ms": None, "turns": 0, "tool_calls": 0, "tools": [],
           "cost": None, "input_tokens": 0, "output_tokens": 0, "model": None, "text": "", "api_ms": None}
    for ev in events:
        t, e = ev["t"], ev["e"]
        kind = e.get("type")
        if kind == "system" and e.get("subtype") == "init":
            out["model"] = e.get("model")
        elif kind == "stream_event":
            se = e["event"]
            if se["type"] == "message_start":
                out["turns"] += 1
            elif se["type"] == "content_block_delta" and out["first_token_ms"] is None:
                out["first_token_ms"] = t
        elif kind == "assistant":
            for block in e["message"].get("content", []):
                if block.get("type") == "tool_use":
                    out["tool_calls"] += 1
                    out["tools"].append(block.get("name"))
        elif kind == "result":
            u = e.get("usage") or {}
            out.update(text=e.get("result", ""), cost=e.get("total_cost_usd"), api_ms=e.get("duration_api_ms"),
                       input_tokens=sum(u.get(k, 0) for k in ("input_tokens", "cache_creation_input_tokens",
                                                                "cache_read_input_tokens")),
                       output_tokens=u.get("output_tokens", 0))
    return out


# ---- the graph condition: the service's pipeline -------------------------------------------------------------------

class Timed(ClaudeCliExtractor):
    """The service's claude-cli extractor, its calls timed and isolated; documents from their recorded extractions."""

    def __init__(self, model_name, raw_dir, lean=False):
        super().__init__(model_name, lean=lean)
        self.raw_dir, self.calls, self.proposed = raw_dir, [], None
        self._n, self._lock = 0, threading.Lock()  # calls may run two at once (thesis_call parallel)
        self.fixture = FixtureExtractor()
        self.fixture.by_name.update(FixtureExtractor(FIX / "extraction").by_name)
        self.scratch = Path(tempfile.mkdtemp(prefix="kl-call-"))

    def extract(self, text, path):
        return self.fixture.extract(text, path)

    def _ask(self, prompt, body):
        label = ("thesis" if prompt == THESIS_PROMPT.read_text(encoding="utf-8") else
                 "repair" if "The checks refused it:" in body else
                 "extract+thesis" if "# Also: the new project's thesis" in prompt else "extract")
        with self._lock:
            self._n += 1
            n = self._n
        raw = self.raw_dir / f"{n}-{label}.jsonl"
        if self.lean:
            r = call(self.model, body, self.scratch, raw=raw, system_prompt=prompt, no_tools=True)
        else:
            r = call(self.model, f"{prompt}\n\n---\n\n{body}", self.scratch, raw=raw)
        self.calls.append({"label": label, "n": n, **{k: v for k, v in r.items() if k != "text"}})
        return r["text"]

    def propose_changes(self, text, path, kind, on, records, entities, preloaded=False):
        self.proposed = super().propose_changes(text, path, kind, on, records, entities, preloaded)
        return self.proposed

    def propose_with_thesis(self, text, path, kind, on, records, entities, figures, preloaded=False):
        self.proposed, thesis = super().propose_with_thesis(text, path, kind, on, records, entities, figures,
                                                            preloaded)
        return self.proposed, thesis


def watch(obj, name, label, log):
    """Record each call of obj.name as (label, start, end), perf_counter seconds."""
    fn = getattr(obj, name)

    def watched(*a, **k):
        s = time.perf_counter()
        try:
            return fn(*a, **k)
        finally:
            log.append((label, s, time.perf_counter()))
    setattr(obj, name, watched)


def run_graph(model_name, raw_dir, fast=None, preload=False):
    """fast: None for the service as it was; merged or parallel for the speed-ups, with that thesis call.
    preload: each call told that what it is given is all there is (preload_note)."""
    tmp = Path(tempfile.mkdtemp(prefix="kl-bench-"))
    svc, _, p = ks.seeded(tmp, research_before_review=bool(fast), thesis_call=fast or "separate",
                          graph_updates="deferred" if fast else "immediate", preload_note=preload)
    ex = Timed(model_name, raw_dir, lean=bool(fast))
    svc.extractor = ex
    svc.ingest(p, name="support-metrics.md", data=(FIX / "support-metrics.md").read_bytes())
    ws = p.workspace_id
    svc.projector.apply_pending(ws)  # the graph is up to date before the meeting arrives, in every route
    out = {"stages": {}, "problems": None}
    spans, marks = [], {}
    if PROFILE:  # the service's steps, each call timed: graph reads, checks, applying, research
        for obj, name in ((svc, "_entities"), (svc, "_records"), (svc.projector, "ensure"),
                          (svc, "open_input_change_request"), (svc, "_apply"), (svc, "_after_applied"),
                          (svc, "_draft"), (svc, "_number_facts"), (svc, "_research_ops"), (ex, "propose_changes"),
                          (svc, "_propose"), (svc, "research_input"), (svc, "_graph_now"),
                          (ex, "propose_with_thesis"), (ex, "draft_thesis_from_input")):
            watch(obj, name, name, spans)
    t0 = time.perf_counter()
    lap = lambda: round((time.perf_counter() - t0) * 1000)  # noqa: E731
    mark = lambda k: marks.__setitem__(k, time.perf_counter())  # noqa: E731
    try:
        r = svc.ingest(p, name=NAME, kind="transcript", text=CASE["text"], on=ON)
        mark("ingest_end")
        out["research_at_ingest"] = bool((r["job"].get("result") or {}).get("research"))
        cr1_id = (r["job"].get("result") or {}).get("change_request")
        out["stages"]["change request 1 open"] = lap()
        cr1 = svc.get_change_request(p, cr1_id) if cr1_id else None
        out["problems"] = cr1["problems"] if cr1 else ["no change request: the extraction proposed nothing"]
        if cr1 and not cr1["problems"]:
            mark("approve1_start")
            svc.approve_change_request(p, cr1_id)
            mark("approve1_end")
            out["stages"]["project created, research done"] = lap()
            research = svc.list_change_requests(p, state="open")["items"]  # only the research's is open now
            if research:
                mark("approve2_start")
                svc.approve_change_request(p, research[0]["id"])
                mark("approve2_end")
                out["stages"]["change request 2 applied"] = lap()
        out["total_ms"] = lap()
    except Exception as e:  # noqa: BLE001  a failed call is an outcome, not the end of the bench
        out.update(total_ms=lap(), error=f"{type(e).__name__}: {str(e)[:300]}")
    try:
        pid = next((c["project"] for c in ex.proposed or [] if c.get("op") == "create_project"), None)
        rec = svc._records(ws).get(pid) if pid else None
        out.update(changes=ex.proposed, thesis=(rec or {}).get("thesis"),
                   numbers=[{"key": n["key"], "status": n["status"], "value": n.get("value"),
                             "source": (n.get("found_in") or {}).get("source"),
                             "quote": (n.get("found_in") or {}).get("quote"), "ask": n.get("ask")}
                            for n in (rec or {}).get("numbers") or []])
        out["names"] = svc._names(ws)
    finally:
        svc.close()
        shutil.rmtree(tmp, ignore_errors=True)
        shutil.rmtree(ex.scratch, ignore_errors=True)
    out["calls"] = ex.calls
    out["model_ms"] = sum(c["wall_ms"] for c in ex.calls)
    if PROFILE:  # every time in ms from the transcript's arrival
        ms = lambda x: round((x - t0) * 1000, 2)  # noqa: E731
        out["profile"] = {"marks": {k: ms(v) for k, v in marks.items()},
                          "spans": [[label, ms(s), ms(e)] for label, s, e in spans if e >= t0],
                          "calls": [[c["label"], ms(c["t_start"]), ms(c["t_start"]) + c["wall_ms"]] for c in ex.calls]}
    return out


# ---- the search condition: one run over the documents ---------------------------------------------------------------

def run_search(model_name, raw_dir):
    work = Path(tempfile.mkdtemp(prefix="kl-search-"))
    for d in DOCS:
        shutil.copy(d, work / d.name)
    task = (SEARCH_TASK.replace("{ingest}", INGEST_PROMPT.read_text(encoding="utf-8").strip())
            .replace("{thesis}", THESIS_PROMPT.read_text(encoding="utf-8").strip())
            .replace("{name}", NAME).replace("{on}", ON).replace("{text}", CASE["text"]))
    try:
        r = call(model_name, task, work, tools="Grep,Read,Glob", raw=raw_dir / "1-search.jsonl")
    finally:
        shutil.rmtree(work, ignore_errors=True)
    out = {"total_ms": r["wall_ms"], "model_ms": r["wall_ms"], "calls": [{"label": "search", **{
        k: v for k, v in r.items() if k != "text"}}], "stages": {}}
    out.update(search_answer(r["text"]))
    return out


def search_answer(text) -> dict:
    """The search run's change set, thesis and numbers, read as the service reads a reply: a project given once
    beside the changes (the envelope projects/ingest-prompt.md allows) belongs to each change that names none."""
    try:
        found = json.loads(text[text.find("{"):text.rfind("}") + 1])
        changes, _ = ingest.parse_all(text)
        return {"changes": changes, "thesis": found.get("thesis"), "numbers": found.get("numbers") or []}
    except ValueError as e:
        return {"changes": None, "thesis": None, "numbers": [], "parse_error": str(e)}


# ---- grading: the same for both ------------------------------------------------------------------------------------

def figures(text):
    return {float(x.replace(",", "")) for x in re.findall(r"\d[\d,]*(?:\.\d+)?", text or "")}


def grade(run, names):
    g = {}
    changes = run.get("changes")
    if not isinstance(changes, list):
        return {"summary": "no change set", "ok": False}
    diff = {"input": f"inputs/{NAME}", "kind": "transcript", "on": ON, "changes": changes}
    try:
        g["problems"] = model.validate({}, diff, CASE["text"], names)[0]
    except Exception as e:  # noqa: BLE001  a malformed set
        g["problems"] = [f"the checks could not read it: {e}"]
    try:
        after = model.apply({}, diff, CASE["text"])[0]
        g["expect_fails"] = cases.check(CASE["expect"], {}, diff, after)
    except Exception as e:  # noqa: BLE001
        g["expect_fails"] = [f"could not be applied: {type(e).__name__}: {e}"]
    th = run.get("thesis") or {}
    because = (th.get("because") or {}).get("quote") or ""
    g["thesis"] = bool(th.get("change") and th.get("formula"))
    g["because_ok"] = bool(because) and model.plain(because) in model.plain(CASE["text"])
    docs = {d.name: d.read_text(encoding="utf-8") for d in DOCS}
    found = [n for n in run.get("numbers") or [] if n.get("status") == "found"]
    verified, unbacked = set(), []
    for n in found:
        doc = docs.get(Path(str(n.get("source") or "")).name, "")
        try:
            value = float(str(n.get("value")).replace(",", ""))
        except ValueError:
            value = None
        if doc and n.get("quote") and model.plain(n["quote"]) in model.plain(doc) and value in figures(n["quote"]):
            verified.add(value)
        else:
            unbacked.append(n.get("key"))
    g["found"] = len(verified & STATED)
    g["unbacked"] = unbacked
    g["asked"] = sum(1 for n in run.get("numbers") or [] if n.get("status") in ("asked", "needed"))
    g["ok"] = not g["problems"] and not g["expect_fails"] and g["thesis"] and g["because_ok"] and \
        g["found"] == len(STATED) and not unbacked
    g["summary"] = (f"{len(g['problems'])} check problems; {len(g['expect_fails'])} expectations missed; "
                    f"thesis {'yes' if g['thesis'] else 'NO'}{'' if g['because_ok'] else ' (because quote not in transcript)'}; "
                    f"numbers found {g['found']} of {len(STATED)}, asked {g['asked']}"
                    + (f", unbacked {', '.join(map(str, unbacked))}" if unbacked else ""))
    return g


# ---- the one-off cost: the graph's facts from the ten documents ------------------------------------------------------

def build(model_name, raw_dir):
    scratch = Path(tempfile.mkdtemp(prefix="kl-build-"))
    rows = []
    try:
        for d in DOCS:
            r = call(model_name, f"{EXTRACT_PROMPT.read_text(encoding='utf-8')}\n\n---\n\nsource_doc: {d.name}\n\n"
                     f"{d.read_text(encoding='utf-8')}", scratch, raw=raw_dir / f"build-{d.stem}.jsonl")
            ok = bool(re.search(r"\{.*\}", r["text"], re.S))
            rows.append({"doc": d.name, "ok": ok, **{k: v for k, v in r.items() if k != "text"}})
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    return rows


# ---- the report ----------------------------------------------------------------------------------------------------

def model_time(r):
    """The model's time on the clock: calls that ran at once counted once (from the profile, when there is one)."""
    spans = sorted((s, e) for _, s, e in (r.get("profile") or {}).get("calls", []))
    if not spans:
        return r["model_ms"]
    total, (cs, ce) = 0.0, spans[0]
    for s, e in spans[1:]:
        if s > ce:
            total, cs, ce = total + ce - cs, s, e
        else:
            ce = max(ce, e)
    return total + ce - cs


def sec(ms):
    return "—" if ms is None else f"{ms / 1000:.1f} s"


def report(runs, builds, started):
    lines = [f"# Live eval: a transcript to a full project and thesis, graph against search", "",
             f"Run {started}. Made by `python bench/project_create_eval.py`. Case 01, in the workspace of "
             "docs/project-creation-example.html (the nine corpus documents and support-metrics.md, no projects). "
             "Today pinned to 2026-09-28. Approvals are instant: a person's review time is left out of both.", "",
             "| Model | Condition | Runs | Correct | Median total | Range | Model time (median) | Other time (median) "
             "| Model calls | Tool calls | Cost per run |",
             "| --- | --- | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: |"]
    for m in sorted({r["model"] for r in runs}):
        for cond in ("search", "graph", "fast-merged", "fast-parallel", "preloaded-merged", "preloaded-parallel"):
            rs = [r for r in runs if r["model"] == m and r["condition"] == cond]
            if not rs:
                continue
            tot = [r["total_ms"] for r in rs]
            mod = [model_time(r) for r in rs]
            costs = [sum(c["cost"] or 0 for c in r["calls"]) for r in rs]
            lines.append(f"| {m} | {cond} | {len(rs)} | {sum(r['grade']['ok'] for r in rs)} of {len(rs)} | "
                         f"{sec(statistics.median(tot))} | {sec(min(tot))} to {sec(max(tot))} | "
                         f"{sec(statistics.median(mod))} | {sec(statistics.median([t - x for t, x in zip(tot, mod)]))} | "
                         f"{statistics.mean(len(r['calls']) for r in rs):.1f} | "
                         f"{statistics.mean(sum(c['tool_calls'] for c in r['calls']) for r in rs):.1f} | "
                         f"${statistics.mean(costs):.3f} |")
    lines += ["", "## Each run", "",
              "| Model | Condition | Rep | Total | Calls (label: wall, first token, turns, tools) | Stages | Outcome |",
              "| --- | --- | ---: | ---: | --- | --- | --- |"]
    for r in runs:
        calls = "; ".join(f"{c['label']}: {sec(c['wall_ms'])}, {sec(c['first_token_ms'])}, {c['turns']}, "
                          f"{c['tool_calls']}" for c in r["calls"])
        stages = "; ".join(f"{k} {sec(v)}" for k, v in r.get("stages", {}).items()) or "—"
        lines.append(f"| {r['model']} | {r['condition']} | {r['rep']} | {sec(r['total_ms'])} | {calls} | {stages} | "
                     f"{'ok' if r['grade']['ok'] else 'NOT OK'}: {r['grade']['summary']}"
                     f"{'; error: ' + r['error'] if r.get('error') else ''} |")
    if builds:
        lines += ["", "## Building the graph's facts (once, before any project)", "",
                  "| Model | Documents | Sum of calls | Longest call | Cost | Replies with JSON |",
                  "| --- | ---: | ---: | ---: | ---: | ---: |"]
        for m, rows in builds.items():
            lines.append(f"| {m} | {len(rows)} | {sec(sum(r['wall_ms'] for r in rows))} | "
                         f"{sec(max(r['wall_ms'] for r in rows))} | ${sum(r['cost'] or 0 for r in rows):.3f} | "
                         f"{sum(r['ok'] for r in rows)} of {len(rows)} |")
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--models", default="sonnet")
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--conditions", default="graph,search")
    ap.add_argument("--build", action="store_true", help="also time extracting the ten documents with the model")
    ap.add_argument("--regrade", action="store_true", help="grade the saved runs again, no calls")
    ap.add_argument("--no-thinking", action="store_true", help="MAX_THINKING_TOKENS=0: no extended thinking")
    ap.add_argument("--append", action="store_true", help="add to the saved runs instead of replacing them")
    ap.add_argument("--profile", action="store_true", help="time each of the service's steps in the graph route")
    ap.add_argument("--tag", help="keep these runs apart: bench/project-create-raw-<tag>/ and its own report")
    args = ap.parse_args()
    global THINKING, PROFILE, RAW, OUT
    THINKING = 0 if args.no_thinking else None
    PROFILE = args.profile
    if args.tag:
        RAW = ROOT / "bench" / f"project-create-raw-{args.tag}"
        OUT = ROOT / "bench" / f"project-create-report-{args.tag}.md"
    suffix = "-nothink" if args.no_thinking else ""
    sys.stdout.reconfigure(encoding="utf-8")
    RAW.mkdir(parents=True, exist_ok=True)
    started = datetime.now().strftime("%Y-%m-%d %H:%M")
    saved = RAW / "runs.json"
    if args.regrade:
        data = json.loads(saved.read_text(encoding="utf-8"))
        names = data["names"]
        for r in data["runs"]:
            stream = RAW / f"{r['model']}-{r['condition']}-{r['rep']}" / "1-search.jsonl"
            if r["condition"] == "search" and stream.is_file():  # read the answer again from its event stream
                events = [json.loads(line) for line in stream.read_text(encoding="utf-8").splitlines() if line.strip()]
                r.update(search_answer(next((ev["e"].get("result", "") for ev in events
                                             if ev["e"].get("type") == "result"), "")))
            r["grade"] = grade(r, names)
        saved.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        report(data["runs"], data.get("builds") or {}, started)
        return
    runs, names, builds = [], None, {}
    if args.append and saved.is_file():
        old = json.loads(saved.read_text(encoding="utf-8"))
        runs, names, builds = old["runs"], old.get("names"), old.get("builds") or {}
    for rep in range(1, args.reps + 1):
        for m in args.models.split(","):
            order = args.conditions.split(",")
            for cond in order if rep % 2 else order[::-1]:  # alternate which goes first
                raw_dir = RAW / f"{m}{suffix}-{cond}-{rep}"
                r = (run_graph(m, raw_dir) if cond == "graph" else
                     run_graph(m, raw_dir, fast=cond.split("-", 1)[1], preload=cond.startswith("preloaded-"))
                     if cond.startswith(("fast-", "preloaded-")) else
                     run_search(m, raw_dir))
                names = names or r.pop("names", None)
                r.pop("names", None)
                r.update(model=m + suffix, condition=cond, rep=rep)
                runs.append(r)
                print(f"{m}{suffix} {cond} {rep}: {sec(r['total_ms'])}, {len(r['calls'])} calls", flush=True)
                saved.write_text(json.dumps({"runs": runs, "names": names, "builds": builds}, ensure_ascii=False,
                                            indent=1), encoding="utf-8")
    if names is None:
        svc, _, p = ks.seeded(Path(tempfile.mkdtemp(prefix="kl-names-")))
        names = svc._names(p.workspace_id)
        svc.close()
    for r in runs:
        r["grade"] = grade(r, names)
        print(f"{r['model']} {r['condition']} {r['rep']}: {r['grade']['summary']}", flush=True)
    if args.build:
        for m in args.models.split(","):
            builds[m + suffix] = build(m, RAW / f"{m}{suffix}-build")
            print(f"build {m}{suffix}: {sec(sum(r['wall_ms'] for r in builds[m + suffix]))}", flush=True)
    saved.write_text(json.dumps({"runs": runs, "names": names, "builds": builds}, ensure_ascii=False, indent=1),
                     encoding="utf-8")
    report(runs, builds, started)
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
