"""The evidence cases, live: a model gathers evidence from the sales ledger and stores it as an OpenSpec
evidence change; later, questions are answered from what was stored, without the database.

    python bench/evidence_eval.py                          both stages, sonnet, 2 gatherings, 1 answer per question
    python bench/evidence_eval.py --stage answer --conditions whole-gold,recall-gold
    python bench/evidence_eval.py --regrade                grade the saved runs again, no calls

Spends model usage on your subscription and needs `claude` on the PATH. Writes bench/evidence-report.md,
and each call's events, each gathering's OpenSpec root and the rows to bench/evidence-raw/.

Stage 1, gather (evidence/cases/evidence.json's brief): in a folder holding a fresh copy of sales.db,
`python query.py` (read-only SQL, the only command allowed), and an OpenSpec root with the evidence schema
and the first half's archived change, the model writes openspec/changes/bundle-evidence/ (proposal.md,
evidence.md, tasks.md). The harness then archives it as `openspec archive` would, to
changes/archive/2026-09-15-bundle-evidence/. Graded on each number the brief asks for, by key, against
the recorded value; a wrong value that matches a recorded slip (UTC days, the order headers) is named.

Stage 2, answer (evidence/cases/questions.json): one question per call, no tools, from a store:
- whole-<store>: every archived evidence.md of the store, whole: the store's content with retrieval perfect;
- recall-<store>: the knowledge layer's context call for the question, over a workspace of the corpus and
  the store indexed by evidence/evidence_index.py (number layout): content and retrieval together;
- db: no store, the database and its schema with read-only SQL: re-deriving, as with nothing stored.
  Questions about the stored evidence itself (store: true) are not asked here.
Stores: gold (evidence/openspec as written), bare (the same numbers, nothing else), own-<n> (gathering n's
archive beside the first half's). Graded on the reply's JSON answer: a number within the question's
tolerance, the date, the word, any of its keywords, or null where the evidence does not say.
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
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "bench"), str(ROOT / "evidence")]
import project_create_eval as pce  # noqa: E402  claude -p's argv, the stream summary, the timeout
import evidence_index as index  # noqa: E402
import score  # noqa: E402

check = score.check  # evidence/cases/check.py

os.environ["GRAPH_MEMORY_TODAY"] = "2026-09-23"  # as the scorecard and the kl tests run
CASES = ROOT / "evidence" / "cases"
GOLD = ROOT / "evidence" / "openspec"
RAW = ROOT / "bench" / "evidence-raw"
OUT = ROOT / "bench" / "evidence-report.md"
ARCHIVED_AS = "2026-09-15-bundle-evidence"
QUERY_PY = '''"""Run one read-only SQL query on the database in this folder: python query.py "SELECT ..." """
import glob, sqlite3, sys
conn = sqlite3.connect(f"file:{glob.glob('*.db')[0]}?mode=ro", uri=True)
try:
    cur = conn.execute(sys.argv[1])
except sqlite3.Error as e:
    sys.exit(f"error: {e}")
print("\\t".join(d[0] for d in cur.description or []))
for i, row in enumerate(cur):
    if i == 200:
        sys.exit("... more than 200 rows, not shown")
    print("\\t".join("NULL" if v is None else str(v) for v in row))
'''
ANSWER_SYSTEM = """You answer one question about Kettle & Kiln's sales, using only the evidence the knowledge
layer gives you. You have no database and no tools. Today is 23 September 2026.

Reply with one JSON object and nothing else:
{"answer": <a number, a YYYY-MM-DD date, a short phrase, or null>, "unit": "<unit or empty>", "basis": "<which evidence, in a few words>"}

- A number is a bare number: 1234.5, not "£1,234.50" or "12%".
- Answer yes or no questions with "yes" or "no".
- If the evidence does not establish the answer, the answer is null. Do not estimate from general knowledge."""
DB_SUFFIX = """Finish with one JSON object on its own line, and nothing after it:
{"answer": <a number, a YYYY-MM-DD date, a short phrase, or null>, "unit": "<unit or empty>", "basis": "<the query, in a few words>"}
A number is a bare number (1234.5, not "£1,234.50" or "12%"). Answer yes or no questions with "yes" or "no".
If the data cannot establish the answer, the answer is null."""
TOLERANCE = {"GBP": 0.01, "%": 0.1}
GATHER_TIMEOUT = 1500  # s: a gathering runs dozens of queries
ANSWER_TIMEOUT = 300


def run_claude(model, body, cwd, raw, system_prompt=None, tools=None, allowed=None, timeout=300):
    """One claude -p run in cwd: its reply, cost and timings (project_create_eval's summary). Each event is
    written to raw as it arrives, and stdout is read on its own thread, so a stalled call is seen while it
    runs and ends at the timeout even when a child keeps the pipe open."""
    argv = [*pce.claude_argv(), "-p", "--model", model, "--output-format", "stream-json", "--verbose",
            "--include-partial-messages", "--setting-sources", "local", "--strict-mcp-config",
            "--no-session-persistence", "--tools", tools or ""]
    if allowed:
        argv += ["--allowedTools", allowed]
    if system_prompt:
        argv += ["--system-prompt", system_prompt]
    env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE")}
    raw.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    p = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.DEVNULL)
    p.stdin.write(body.encode("utf-8"))
    p.stdin.close()
    events = []

    def read():
        with raw.open("w", encoding="utf-8") as out:
            for line in p.stdout:
                try:
                    ev = {"t": round((time.perf_counter() - t0) * 1000, 1), "e": json.loads(line)}
                except ValueError:
                    continue
                events.append(ev)
                if ev["e"].get("type") != "stream_event":  # the deltas are many; the messages say it all
                    out.write(json.dumps(ev, ensure_ascii=False) + "\n")
                    out.flush()
    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    reader.join(timeout)
    timed_out = reader.is_alive()
    if timed_out:
        pce.kill_tree(p)
        reader.join(10)
    wall = (time.perf_counter() - t0) * 1000
    return {**pce.summarise(list(events), wall), **({"timed_out": True} if timed_out else {})}


# ---- stage 1: gather --------------------------------------------------------------------------------------

def gather_prompt():
    return "\n".join([
        check.brief_text(), "",
        "The database is sales.db in this folder: SQLite, read-only. Its schema:", "",
        (CASES / "sales" / "schema.sql").read_text(encoding="utf-8").strip(), "",
        'Run a query with: python query.py "<SQL>". It is the only command that runs here: other commands, '
        "and scripts of your own, are refused. Files can be read, and written inside this folder only.", "",
        "Record the evidence as an OpenSpec change in this folder's OpenSpec root, with the evidence schema "
        "(openspec/schemas/evidence/schema.yaml: read its instructions and its templates first):",
        "- openspec/changes/bundle-evidence/.openspec.yaml with the lines `schema: evidence` and `skip_specs: true`;",
        "- proposal.md, evidence.md and tasks.md in that folder, as the schema says.",
        "openspec/changes/archive/2026-07-01-h1-sales-evidence/ is the evidence gathered for the first half of the "
        "year: this change updates it for the sets it repeats. Use each number's key as given above, and keep each "
        "set's id. When every number is in evidence.md and every task is ticked, say done."])


def gather(model, n):
    """One gathering: the model's change, archived. Returns its row, with its OpenSpec root kept in RAW."""
    work = Path(tempfile.mkdtemp(prefix="evidence-gather-"))
    try:
        check.build.build("sales", work)  # work/sales.db
        (work / "query.py").write_text(QUERY_PY, encoding="utf-8")
        osr = work / "openspec"
        shutil.copytree(GOLD, osr, ignore=shutil.ignore_patterns(ARCHIVED_AS))
        r = run_claude(model, gather_prompt(), work, RAW / f"gather-{n}.jsonl", tools="Bash,Read,Write,Edit,Glob",
                       allowed="Bash(python query.py:*),Read,Glob,Edit(./**),Write(./**)", timeout=GATHER_TIMEOUT)
        change = osr / "changes" / "bundle-evidence"
        kept = RAW / f"own-{n}" / "openspec"
        if kept.parent.exists():
            shutil.rmtree(kept.parent)
        archived = change.is_dir()
        if archived:  # as `openspec archive bundle-evidence` moves it
            shutil.move(str(change), str(osr / "changes" / "archive" / ARCHIVED_AS))
        shutil.copytree(osr, kept)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    row = {"stage": "gather", "n": n, "model": model, "archived": archived, "cost": r["cost"],
           "timed_out": bool(r.get("timed_out")),
           "seconds": round(r["wall_ms"] / 1000, 1), "tool_calls": r["tool_calls"], "reply": r["text"][-500:]}
    return {**row, **grade_gathering(kept)}


def grade_gathering(root):
    """Each number the brief asks for, by key, against the recorded value; slips named."""
    path = root / "changes" / "archive" / ARCHIVED_AS / "evidence.md"
    if not path.is_file():
        return {"numbers": [], "right": 0, "asked": 0, "notes": 0, "keywords": 0, "problems": ["no evidence.md"]}
    text = path.read_text(encoding="utf-8")
    parsed = {s["id"]: s for s in index.parse(text)["sets"]}
    spec = check.load()
    with tempfile.TemporaryDirectory() as tmp:
        with closing(check.connect(check.build.build("sales", tmp))) as conn:
            slips = check.traps(conn, spec)
    new = next(a for a in spec["archives"] if a["date"] == "2026-09-15")
    rows = []
    for s in new["sets"]:
        have = {n["key"].strip("` ").lower(): n for n in (parsed.get(s["id"]) or {}).get("numbers", [])}
        verdict = (parsed.get(s["id"]) or {}).get("verdict") or ""
        for n in s["numbers"]:
            cell = have.get(n["key"], {}).get("value")
            if n["key"] == "verdict":
                cell = cell or verdict
            got = index.figure(cell) if cell else None
            got = cell if got is None else got
            ok = got is not None and check.same(n["value"], got if not isinstance(got, str) else got.strip().lower()
                                                .rstrip("."), n.get("tolerance", TOLERANCE.get(n["unit"], 0.01)))
            slip = next((why for v, why in slips.get(("2026-09-15", s["id"], n["key"]), [])
                         if got is not None and check.same(v, got, 0.01)), None)
            rows.append({"set": s["id"], "key": n["key"], "want": n["value"], "got": got, "right": ok, "slip": slip})
    sets = list(parsed.values())
    return {"numbers": rows, "right": sum(r["right"] for r in rows), "asked": len(rows),
            "notes": sum(len(s["notes"]) for s in sets), "keywords": sum(len(s["keywords"]) for s in sets),
            "sets": len(sets), "chars": len(text), "problems": index.index(index.read_root(root))[1]}


# ---- stage 2: answer --------------------------------------------------------------------------------------

def store_root(store):
    return GOLD if store in ("gold", "bare") else RAW / store / "openspec"


def store_kind(store):
    return "own" if store.startswith("own-") else store


def contexts(conditions, questions):
    """{(condition, question id): the text the model is given}, made before any call: the service is one thread's."""
    out = {}
    for cond in conditions:
        if cond == "db":
            continue
        how, store = cond.split("-", 1)
        files = score.store_files(store_kind(store), store_root(store))
        if how == "whole":
            whole = "\n\n".join(f"===== {path} =====\n{text}" for path, text in sorted(files.items()))
            for q in questions:
                out[(cond, q["id"])] = whole
            continue
        svc, p, _, problems = score.workspace(files, "number")
        try:
            for q in questions:
                out[(cond, q["id"])] = svc.context(p, q["question"])["text"]
        finally:
            svc.close()
    return out


def answer(model, cond, q, ctx, rep, db_path):
    raw = RAW / f"answer-{cond}-{q['id']}-{rep}.jsonl"
    if cond == "db":
        work = Path(tempfile.mkdtemp(prefix="evidence-db-"))
        try:
            shutil.copy(db_path, work / "sales.db")
            (work / "query.py").write_text(QUERY_PY, encoding="utf-8")
            body = "\n".join([q["question"], "", "Today is 23 September 2026. The database is sales.db in this folder: "
                              "Kettle & Kiln's sales ledger, SQLite, read-only. Its schema:", "",
                              (CASES / "sales" / "schema.sql").read_text(encoding="utf-8").strip(), "",
                              'Run a query with: python query.py "<SQL>"', "", DB_SUFFIX])
            r = run_claude(model, body, work, raw, tools="Bash", allowed="Bash(python query.py:*)", timeout=ANSWER_TIMEOUT)
        finally:
            shutil.rmtree(work, ignore_errors=True)
    else:
        body = f"Question: {q['question']}\n\nWhat the knowledge layer has:\n-----\n{ctx}\n-----"
        r = run_claude(model, body, tempfile.mkdtemp(prefix="evidence-ask-"), raw, system_prompt=ANSWER_SYSTEM,
                       timeout=ANSWER_TIMEOUT)
    return {"stage": "answer", "condition": cond, "q": q["id"], "kind": q["kind"], "rep": rep, "model": model,
            "reply": r["text"], "cost": r["cost"], "seconds": round(r["wall_ms"] / 1000, 1),
            "tool_calls": r["tool_calls"], "context_chars": len(ctx or "")}


def parse_reply(text):
    for m in reversed(list(re.finditer(r"\{[^{}]*\"answer\"[^{}]*\}", text or "", re.S))):
        try:
            return json.loads(m.group(0))
        except ValueError:
            continue
    return None


def grade(row, q):
    reply = parse_reply(row["reply"])
    if reply is None:
        return {"right": False, "got": None, "why": "no JSON answer"}
    got = reply.get("answer")
    want = check.answer_of(q) if q["grade"] != "none" else None
    g = q["grade"]
    if g == "none":
        right = got is None or (isinstance(got, str) and re.search(r"not (established|known|in)|unknown|no data", got, re.I))
    elif got is None:
        right = False
    elif g == "number":
        try:
            num = float(str(got).replace(",", "").replace("£", "").rstrip("%"))
        except ValueError:
            num = None
        right = num is not None and abs(num - float(want)) <= q.get("tolerance", 0) + 1e-9
    elif g == "date":
        right = str(got).strip()[:10] == want
    elif g == "word":
        right = re.sub(r"[^a-z ]", "", str(got).lower()).strip().split(" ")[0] == want.lower()
    else:
        right = any(k in str(got).lower() for k in q["keywords"])
    slip = next((why for v, why in (q.get("slips") or {}).items() if not right and got is not None
                 and str(got).strip().lower().rstrip("0").rstrip(".") == v.lower().rstrip("0").rstrip(".")), None)
    return {"right": bool(right), "got": got, "why": slip}


# ---- the report -------------------------------------------------------------------------------------------

def fmt_cost(rows):
    return f"${sum(r.get('cost') or 0 for r in rows):.2f}"


def report(rows, args):
    questions = {q["id"]: q for q in check.load_questions()["questions"]}
    gathers = [r for r in rows if r["stage"] == "gather"]
    for g in gathers:  # graded again from the archive the run left, so a fix to the grader reaches saved runs
        if (RAW / f"own-{g['n']}" / "openspec").is_dir():
            g.update(grade_gathering(RAW / f"own-{g['n']}" / "openspec"))
    answers = [r for r in rows if r["stage"] == "answer" and r["q"] in questions
               and not (r["condition"] == "db" and questions[r["q"]].get("store"))]  # as the run plans them
    for r in answers:
        r.update(grade=grade(r, questions[r["q"]]))
    lines = [f"# Evidence cases, live ({datetime.now():%d %B %Y})", "",
             f"Made by `python bench/evidence_eval.py` (model {args.model}). Stage 1 gathers the evidence and archives "
             "it as an OpenSpec change; stage 2 answers later questions from a store, without the database.", ""]
    if gathers:
        lines += ["## Stage 1: gathering", "",
                  "| Run | Archived | Numbers right | Slips | Sets | Notes | Keywords | Tool calls | Time | Cost |",
                  "|---|---|---|---|---|---|---|---|---|---|"]
        for g in sorted(gathers, key=lambda r: r["n"]):
            slips = sorted({f"{x['key']} ({x['slip']})" for x in g["numbers"] if x["slip"]})
            lines.append(f"| {g['n']} | {'yes' if g['archived'] else 'no'} | {g['right']} of {g['asked']} | "
                         f"{', '.join(slips) or 'none'} | {g.get('sets', 0)} | {g['notes']} | {g['keywords']} | "
                         f"{g['tool_calls']} | {g['seconds']} s | {fmt_cost([g])} |")
        lines.append("")
        for g in sorted(gathers, key=lambda r: r["n"]):
            wrong = [f"{x['set']}/{x['key']}: {x['got']!r} (want {x['want']!r})" for x in g["numbers"] if not x["right"]]
            lines.append(f"- run {g['n']} wrong or missing: {'; '.join(wrong) or 'none'}")
        lines.append("")
    if answers:
        conds = list(dict.fromkeys(r["condition"] for r in answers))
        kinds = list(dict.fromkeys(q["kind"] for q in questions.values()))
        lines += ["## Stage 2: answering from the store", "",
                  "| Condition | Right | " + " | ".join(kinds) + " | Median context | Cost |",
                  "|---|---|" + "---|" * len(kinds) + "---|---|"]
        for c in conds:
            rs = [r for r in answers if r["condition"] == c]
            by_kind = []
            for k in kinds:
                ks_ = [r for r in rs if r["kind"] == k]
                by_kind.append(f"{sum(r['grade']['right'] for r in ks_)}/{len(ks_)}" if ks_ else "")
            lines.append(f"| {c} | **{sum(r['grade']['right'] for r in rs)} of {len(rs)}** | " + " | ".join(by_kind)
                         + f" | {statistics.median(r['context_chars'] for r in rs):,.0f} chars | {fmt_cost(rs)} |")
        lines += ["", "| Question | Answer | " + " | ".join(conds) + " |", "|---|---|" + "---|" * len(conds)]
        for qid, q in questions.items():
            cells = []
            for c in conds:
                rs = [r for r in answers if r["condition"] == c and r["q"] == qid]
                if not rs:
                    cells.append("")
                    continue
                cells.append(" · ".join(("ok" if r["grade"]["right"] else f"**{r['grade']['got']!s}**"
                                         + (f" ({r['grade']['why']})" if r["grade"]["why"] else "")) for r in rs))
            want = check.answer_of(q) if q["grade"] != "none" else "null"
            lines.append(f"| {qid} | {want} | " + " | ".join(cells) + " |")
        lines.append("")
    lines.append(f"Total cost {fmt_cost(rows)}.")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--model", default="sonnet")
    ap.add_argument("--stage", default="both", choices=["both", "gather", "answer"])
    ap.add_argument("--gatherings", type=int, default=2)
    ap.add_argument("--reps", type=int, default=1)
    ap.add_argument("--conditions", default="")
    ap.add_argument("--questions", default="", help="comma-separated question id prefixes")
    ap.add_argument("-j", type=int, default=5, help="calls at once")
    ap.add_argument("--regrade", action="store_true")
    args = ap.parse_args()
    RAW.mkdir(parents=True, exist_ok=True)
    saved = RAW / "rows.json"
    rows = json.loads(saved.read_text(encoding="utf-8")) if saved.exists() else []
    if args.regrade:
        OUT.write_text(report(rows, args), encoding="utf-8")
        print(f"wrote {OUT.relative_to(ROOT)}")
        return
    if not shutil.which("claude"):
        sys.exit("claude is not on the PATH")
    lock = threading.Lock()

    def keep(new):
        with lock:
            rows[:] = [r for r in rows if not same_run(r, new)] + [new]
            saved.write_text(json.dumps(rows, indent=1, ensure_ascii=False, default=str), encoding="utf-8")

    if args.stage in ("both", "gather"):
        with ThreadPoolExecutor(min(args.j, args.gatherings)) as pool:
            for g in pool.map(lambda n: gather(args.model, n), range(1, args.gatherings + 1)):
                keep(g)
                print(f"gathering {g['n']}: archived {g['archived']}, {g['right']} of {g['asked']} numbers right, "
                      f"{g['notes']} notes, {g['seconds']} s, ${g['cost'] or 0:.2f}", flush=True)
    if args.stage in ("both", "answer"):
        owns = sorted(p.name for p in RAW.glob("own-*") if (p / "openspec").is_dir())
        default = ["whole-gold", "whole-bare", "recall-gold", "recall-bare"] + \
            [f"{h}-{o}" for o in owns for h in ("whole", "recall")] + ["db"]
        conds = [c for c in args.conditions.split(",") if c] or default
        wanted = [w for w in args.questions.split(",") if w]
        questions = [q for q in check.load_questions()["questions"] if not wanted or any(q["id"].startswith(w) for w in wanted)]
        ctx = contexts(conds, questions)
        with tempfile.TemporaryDirectory() as tmp:
            db_path = check.build.build("sales", tmp)
            jobs = [(c, q, rep) for rep in range(1, args.reps + 1) for c in conds for q in questions
                    if not (c == "db" and q.get("store"))]
            done = [0]

            def go(job):
                c, q, rep = job
                r = answer(args.model, c, q, ctx.get((c, q["id"])), rep, db_path)
                keep(r)
                g = grade(r, q)
                with lock:
                    done[0] += 1
                    print(f"[{done[0]}/{len(jobs)}] {c:<14} {q['id']:<24} {'right' if g['right'] else 'WRONG'} "
                          f"{g['got']!s:.40}", flush=True)
            with ThreadPoolExecutor(args.j) as pool:
                list(pool.map(go, jobs))
    OUT.write_text(report(rows, args), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")


def same_run(a, b):
    if a["stage"] != b["stage"]:
        return False
    if a["stage"] == "gather":
        return a["n"] == b["n"] and a["model"] == b["model"]
    return (a["condition"], a["q"], a["rep"], a["model"]) == (b["condition"], b["q"], b["rep"], b["model"])


if __name__ == "__main__":
    main()
