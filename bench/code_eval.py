"""Live: questions about a codebase, searched for by the model, or answered through the graph hook.

    python bench/code_eval.py                      told where the code is, both conditions
    python bench/code_eval.py --plain --reps 1     asked plainly
    python bench/code_eval.py --regrade            grade the saved answers again, no calls
    python bench/code_eval.py --cases 12,13 --tag deps   some cases, into code-raw-deps and code-report-deps.md

The questions are codegraph/cases/questions.json. Both conditions run in folders
holding the same files: the sample shop's code (codegraph/cases/shop: a Python
API and a TypeScript frontend), the company documents, and the CLAUDE.md rule.

    search   no hook: the model finds the answer itself with Grep, Read and Glob
    graph    the graph hook, over a graph of the documents and the indexed code

Today is pinned to 28 September 2026. Each answer's final ANSWER line is graded
with the case's answer_all, answer_any, answer_groups and answer_none words; a case
with grade_reply (the change requests) is graded on the whole reply instead, since
it must name every call site that has to change, more than an ANSWER line holds.
Writes bench/code-report.md (or code-report-plain.md) and the event streams.
"""
import argparse
import json
import os
import shutil
import statistics
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "bench"), str(ROOT / "src")]
import build_graph  # noqa: E402
import live_eval  # noqa: E402

NOW = "2026-09-28"
SHOP = ROOT / "codegraph" / "cases" / "shop"
CASES = json.loads((ROOT / "codegraph" / "cases" / "questions.json").read_text(encoding="utf-8"))
HINT = "Our code and company docs are in this folder. "
SUFFIX = "\n\nEnd your reply with one line: ANSWER: <your answer in a few words>"
OUT, RAW = ROOT / "bench" / "code-report.md", ROOT / "bench" / "code-raw"


def grade(case, answer: str, reply: str = "") -> bool:
    """answer_all: every word; answer_any: one of them; answer_groups: one from each group;
    answer_none: none of them. Case-insensitive, in the final ANSWER line, or in the whole
    reply for a case with grade_reply."""
    a = (reply if case.get("grade_reply") else answer).lower() + " "
    return (all(w.lower() in a for w in case.get("answer_all", []))
            and (not case.get("answer_any") or any(w.lower() in a for w in case["answer_any"]))
            and all(any(w.lower() in a for w in g) for g in case.get("answer_groups", []))
            and not any(w.lower() in a for w in case.get("answer_none", [])))


def stall(events) -> float:
    """The longest silence in a run's event stream, when it is over a minute, else 0. Grep, Read
    and Glob answer in milliseconds here, so a silence that long is the service stalling, before a
    request or in the middle of a response: its time, not the model's work. Times are also given
    without it."""
    worst = max((b["t"] - a["t"] for a, b in zip(events, events[1:])), default=0.0)
    return worst if worst > 60000 else 0.0


def answer_line(text: str) -> str:
    lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip().upper().startswith("ANSWER:")]
    return lines[-1][7:].strip() if lines else (text.strip().splitlines() or [""])[-1]


def setup(work: Path) -> None:
    """A graph of the documents and the shop; two folders holding the same code, documents and rule."""
    db = work / "graph.db"
    build_graph.build(db_path=db, code=SHOP, records=work / "no-records", now=date.fromisoformat(NOW))
    for condition in ("search", "graph"):
        folder = work / condition
        shutil.copytree(SHOP, folder)
        for doc in (ROOT / "corpus").glob("*.md"):
            shutil.copy(doc, folder / doc.name)
        shutil.copy(ROOT / "claude-md-snippet.md", folder / "CLAUDE.md")
    hook = f'python "{(ROOT / "src" / "recall_hook.py").as_posix()}"'
    (work / "graph-settings.json").write_text(json.dumps({"hooks": {"UserPromptSubmit": [
        {"hooks": [{"type": "command", "command": hook, "timeout": 10}]}]}}), encoding="utf-8")
    os.environ.update(GRAPH_MEMORY_DB=str(db), GRAPH_MEMORY_TODAY=NOW, GRAPH_MEMORY_STATE=str(work / "state"),
                      GRAPH_MEMORY_RAG_DB=str(work / "no-rag.db"))


def run_one(claude, work, condition, model_name, ci, rep, hint) -> dict:
    case = CASES[ci]
    events = live_eval.run(claude, model_name, condition, (HINT if hint else "") + case["question"] + SUFFIX, work,
                           "local,project")
    RAW.mkdir(exist_ok=True)
    (RAW / f"{condition}-{model_name}-{case['id'][:2]}-{rep}.jsonl").write_text(
        "\n".join(json.dumps(e, ensure_ascii=False) for e in events), encoding="utf-8")
    s = live_eval.summarise(events)
    text = next((e["e"].get("result", "") for e in events if e["e"].get("type") == "result"), "")
    ans = answer_line(text)
    return {"case": case["id"], "kind": case["kind"], "question": case["question"], "condition": condition,
            "model": model_name, "rep": rep, "answer": ans, "reply": text, "correct": grade(case, ans, text),
            "stall": stall(events),
            **{k: s[k] for k in ("end", "first_text", "turns", "tool_calls", "first_input_tokens", "cost")}}


def summary(rows) -> dict:
    return {"n": len(rows), "correct": sum(r["correct"] for r in rows),
            "searched": sum(r["tool_calls"] > 0 for r in rows), "tools": sum(r["tool_calls"] for r in rows),
            "time": statistics.mean(r["end"] for r in rows) / 1000,
            "median": statistics.median(r["end"] for r in rows) / 1000,
            "working": statistics.mean(r["end"] - r.get("stall", 0) for r in rows) / 1000,
            "stalls": sum(r.get("stall", 0) > 0 for r in rows),
            "first": statistics.mean(r["first_text"] or r["end"] for r in rows) / 1000,
            "tokens": statistics.mean(r["first_input_tokens"] or 0 for r in rows),
            "cost": statistics.mean(r["cost"] or 0 for r in rows)}


def report(rows, argv, hint) -> str:
    models = list(dict.fromkeys(r["model"] for r in rows))
    lines = ["# Live eval: questions about a codebase, search against graph", "",
             f"Run {datetime.now():%Y-%m-%d %H:%M}. Made by `python bench/code_eval.py {' '.join(argv)}`. "
             + (f"Every prompt starts \"{HINT.strip()}\". " if hint else "Asked plainly. ")
             + "Both folders hold the shop's code, the company documents and the CLAUDE.md rule; the graph "
             "condition adds the graph hook. Cases marked * are graded on the whole reply: it must name every "
             "call site that has to change.", "",
             "| Model | Condition | Correct | Runs that searched | Tool calls | Average time | Median time "
             "| Average without service waits | First-request tokens | Cost per question |",
             "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for m in models:
        for c in ("search", "graph"):
            mine = [r for r in rows if r["model"] == m and r["condition"] == c]
            if mine:
                s = summary(mine)
                waited = f" ({s['stalls']} waited)" if s["stalls"] else ""
                lines.append(f"| {m} | {c} | {s['correct']} of {s['n']} | {s['searched']} of {s['n']} | {s['tools']} "
                             f"| {s['time']:.1f} s | {s['median']:.1f} s | {s['working']:.1f} s{waited} "
                             f"| {s['tokens']:,.0f} | ${s['cost']:.4f} |")
    lines += ["", "| Case | Condition | Model | Rep | Answer | Correct | Tool calls | Time |",
              "| --- | --- | --- | ---: | --- | --- | ---: | ---: |"]
    strict = {c["id"] for c in CASES if c.get("grade_reply")}
    for r in sorted(rows, key=lambda r: (r["case"], r["condition"] != "search", r["model"], r["rep"])):
        lines.append(f"| {r['case']}{' *' if r['case'] in strict else ''} | {r['condition']} | {r['model']} | {r['rep']} | {r['answer'].replace('|', '/')} "
                     f"| {'yes' if r['correct'] else 'NO'} | {r['tool_calls']} | {r['end'] / 1000:.1f} s |")
    return "\n".join(lines) + "\n"


def main():
    global OUT, RAW
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--models", default="haiku,sonnet")
    ap.add_argument("--reps", type=int, default=2)
    ap.add_argument("--conditions", default="search,graph")
    ap.add_argument("--plain", action="store_true", help="ask without saying where the code is")
    ap.add_argument("--regrade", action="store_true")
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--cases", default="", help="case numbers to run, e.g. 12,13 (default: all)")
    ap.add_argument("--tag", default="", help="write code-report-<tag>.md and code-raw-<tag>/ instead")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    if args.plain:
        OUT, RAW = OUT.with_name("code-report-plain.md"), RAW.with_name("code-raw-plain")
    if args.tag:
        OUT, RAW = OUT.with_name(f"{OUT.stem}-{args.tag}.md"), RAW.with_name(f"{RAW.name}-{args.tag}")
    wanted = {c.strip().zfill(2) for c in args.cases.split(",") if c.strip()}
    if args.regrade:
        rows = json.loads((RAW / "rows.json").read_text(encoding="utf-8"))
        by_id = {c["id"]: c for c in CASES}
        for r in rows:
            raw = RAW / f"{r['condition']}-{r['model']}-{r['case'][:2]}-{r['rep']}.jsonl"
            if raw.is_file():
                events = [json.loads(line) for line in raw.read_text(encoding="utf-8").splitlines()]
                r["stall"] = stall(events)
                r["reply"] = next((e["e"].get("result", "") for e in events if e["e"].get("type") == "result"), "")
            r["correct"] = grade(by_id[r["case"]], r["answer"], r.get("reply", ""))
    else:
        claude = shutil.which("claude")
        if not claude:
            sys.exit("claude is not on the PATH")
        work = Path(tempfile.mkdtemp())
        setup(work)
        jobs = [(c, m, ci, rep) for rep in range(1, args.reps + 1) for c in args.conditions.split(",")
                for m in args.models.split(",") for ci in range(len(CASES))
                if not wanted or CASES[ci]["id"][:2] in wanted]
        with ThreadPoolExecutor(max_workers=args.jobs) as pool:
            rows = list(pool.map(lambda j: run_one(claude, work, *j, hint=not args.plain), jobs))
        for r in rows:
            print(f"{r['condition']:<6} {r['model']:<7} {r['case'][:2]} rep {r['rep']}: "
                  f"{'OK ' if r['correct'] else 'BAD'} {r['end'] / 1000:5.1f} s tools={r['tool_calls']}  {r['answer'][:70]}")
    RAW.mkdir(exist_ok=True)
    (RAW / "rows.json").write_text(json.dumps(rows, indent=1, ensure_ascii=False), encoding="utf-8")
    OUT.write_text(report(rows, sys.argv[1:], not args.plain), encoding="utf-8")
    print(f"{sum(r['correct'] for r in rows)} of {len(rows)} correct -> {OUT.relative_to(ROOT).as_posix()}")


if __name__ == "__main__":
    main()
