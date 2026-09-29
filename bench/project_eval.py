"""Live: questions about projects, searched for by the model, or answered through the graph hook.

    python bench/project_eval.py
    python bench/project_eval.py --models sonnet --reps 2 --conditions graph
    python bench/project_eval.py --hint        every prompt starts "Our company docs are in this folder."
    python bench/project_eval.py --regrade     grade the saved answers again, no calls

Two conditions, in folders holding the same files: the repo's documents and
the inputs the story's two projects were built from (projects/cases.py: as
they stand on 26 September 2026), and the CLAUDE.md rule from
claude-md-snippet.md.

    search   no hook: the model finds the answer itself with Grep, Read and Glob
    graph    the graph hook, over a graph of the documents and the project records

Today is pinned to 28 September 2026. Each answer's final ANSWER line is
graded; a searcher does not know the graph's status words, so their plain
English equivalents count too.

Writes bench/project-report.md, and the event streams to bench/project-raw/.
Spends one claude -p call per question, model and rep.
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
sys.path[:0] = [str(ROOT / "bench"), str(ROOT / "src"), str(ROOT / "projects")]
import build_graph  # noqa: E402
import cases  # noqa: E402
import live_eval  # noqa: E402
import model  # noqa: E402

NOW = "2026-09-28"
OUT = ROOT / "bench" / "project-report.md"
RAW = ROOT / "bench" / "project-raw"
SUFFIX = "\n\nEnd your reply with one line: ANSWER: <your answer in a few words>"
HINT = "Our company docs are in this folder. "  # search at its best: told where to look
BLOCKED = ("blocked", "stalled", "on hold", "paused", "waiting")
ACTIVE = ("active", "in progress", "under way", "underway", "ongoing", "proceeding", "going ahead",
          "shortlist")  # "still in the shortlisting phase": step 1 of the agreed plan, under way
QUESTIONS = [  # (label, question, expected, grade on the ANSWER line, lower case)
    ("Status", "What's the status of the helpdesk migration?", "blocked", lambda a: any(w in a for w in BLOCKED)),
    ("Sign-off", "Who has to sign off the helpdesk contract?", "Alex Doyle, the Founder",
     lambda a: "alex" in a or "founder" in a),
    ("Next step", "What's the next step on the helpdesk migration, and who has it?",
     "step 3, the contract: Alex Doyle", lambda a: "alex" in a),
    ("Anything blocked", "Is anything blocked right now?", "the helpdesk migration", lambda a: "helpdesk" in a),
    ("Status on a date", "What was the status of the helpdesk migration on 20 September?", "active",
     lambda a: any(w in a for w in ACTIVE)),
    ("Depends on", "What does the refunds dashboard depend on?", "the helpdesk migration",
     lambda a: "helpdesk" in a),
    ("A decision", "What did we decide about the old helpdesk?", "read-only for 90 days, then closed",
     lambda a: "90" in a),
    ("A person's work", "Which projects is Marcus working on?", "the helpdesk migration",
     lambda a: "helpdesk" in a),
]


def answer_line(text: str) -> str:
    lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip().upper().startswith("ANSWER:")]
    return lines[-1][7:].strip() if lines else text.strip().splitlines()[-1] if text.strip() else ""


def story_inputs() -> list:
    """The inputs the story's records were built from: cases 01 to 05 and the plan discussion.
    Later inputs (06, 07) would tell a searcher what the graph does not know yet."""
    names = {c["input"] for c in cases.all_cases() if c["name"][:2] <= "05"}
    return sorted(names | {"inputs/discussions/2026-09-15-helpdesk-migration.md"})


def setup(work: Path) -> None:
    """The story's graph; two folders holding the same documents, inputs and rule; the hook."""
    records, events = cases.story()
    model.save_records(work / "records", records, events)
    db = work / "graph.db"
    build_graph.build(db_path=db, records=work / "records", records_root=cases.CASES,
                      now=date.fromisoformat(NOW))
    for condition in ("search", "graph"):  # live_eval runs in work/<condition>
        folder = work / condition
        shutil.copytree(ROOT / "corpus", folder)
        for doc in story_inputs():
            (folder / doc).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(cases.CASES / doc, folder / doc)
        shutil.copy(ROOT / "claude-md-snippet.md", folder / "CLAUDE.md")
    hook = f'python "{(ROOT / "src" / "recall_hook.py").as_posix()}"'
    (work / "graph-settings.json").write_text(json.dumps({"hooks": {"UserPromptSubmit": [
        {"hooks": [{"type": "command", "command": hook, "timeout": 10}]}]}}), encoding="utf-8")
    os.environ.update(GRAPH_MEMORY_DB=str(db), GRAPH_MEMORY_TODAY=NOW,
                      GRAPH_MEMORY_STATE=str(work / "state"), GRAPH_MEMORY_RAG_DB=str(work / "no-rag.db"))


def run_one(claude, work, condition, model_name, qi, rep, hint=False) -> dict:
    label, question, expected, grade = QUESTIONS[qi]
    events = live_eval.run(claude, model_name, condition, (HINT if hint else "") + question + SUFFIX, work,
                           "local,project")
    RAW.mkdir(exist_ok=True)
    (RAW / f"{condition}-{model_name}-q{qi + 1}-{rep}.jsonl").write_text(
        "\n".join(json.dumps(e, ensure_ascii=False) for e in events), encoding="utf-8")
    s = live_eval.summarise(events)
    text = next((e["e"].get("result", "") for e in events if e["e"].get("type") == "result"), "")
    ans = answer_line(text)
    return {"q": qi, "label": label, "question": question, "expected": expected, "condition": condition,
            "model": model_name, "rep": rep,
            "answer": ans, "correct": bool(grade(ans.lower())),
            **{k: s[k] for k in ("end", "first_text", "turns", "tool_calls", "first_input_tokens", "cost",
                                 "recall_line")}}


def summary(rows) -> dict:
    return {"n": len(rows), "correct": sum(r["correct"] for r in rows),
            "searched": sum(r["tool_calls"] > 0 for r in rows), "tools": sum(r["tool_calls"] for r in rows),
            "time": statistics.mean(r["end"] for r in rows) / 1000,
            "first": statistics.mean(r["first_text"] or r["end"] for r in rows) / 1000,
            "tokens": statistics.mean(r["first_input_tokens"] or 0 for r in rows),
            "cost": statistics.mean(r["cost"] or 0 for r in rows)}


def report(rows, argv) -> str:
    models = list(dict.fromkeys(r["model"] for r in rows))
    conditions = [c for c in ("search", "graph") if any(r["condition"] == c for r in rows)]
    lines = ["# Live eval: questions about projects, search against graph", "",
             f"Run {datetime.now():%Y-%m-%d %H:%M}. Made by `python bench/project_eval.py {' '.join(argv)}`. "
             + (f"Every prompt starts \"{HINT.strip()}\". " if RAW.name.endswith("hint") else "") +
             f"Today pinned to {NOW}. Both folders hold the repo's documents, the inputs the story's two projects "
             "were built from, and the CLAUDE.md rule; the graph condition adds the graph hook.", "",
             "| Model | Condition | Correct | Runs that searched | Tool calls | Average time | First answer word "
             "| First-request tokens | Cost per question |",
             "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for m in models:
        for c in conditions:
            s = summary([r for r in rows if r["model"] == m and r["condition"] == c])
            lines.append(f"| {m} | {c} | {s['correct']} of {s['n']} | {s['searched']} of {s['n']} | {s['tools']} "
                         f"| {s['time']:.1f} s | {s['first']:.1f} s | {s['tokens']:,.0f} | ${s['cost']:.4f} |")
    lines += ["", "| # | Question | Expected | Condition | Model | Rep | Answer | Correct | Tool calls | Time |",
              "| ---: | --- | --- | --- | --- | ---: | --- | --- | ---: | ---: |"]
    for r in sorted(rows, key=lambda r: (r["q"], r["condition"] != "search", r["model"], r["rep"])):
        lines.append(f"| {r['q'] + 1} | {r['question']} | {r['expected']} | {r['condition']} | {r['model']} "
                     f"| {r['rep']} | {r['answer'].replace('|', '/')} | {'yes' if r['correct'] else 'NO'} "
                     f"| {r['tool_calls']} | {r['end'] / 1000:.1f} s |")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--models", default="haiku,sonnet")
    ap.add_argument("--reps", type=int, default=1)
    ap.add_argument("--conditions", default="search,graph")
    ap.add_argument("--hint", action="store_true", help=f"start every prompt with {HINT.strip()!r}")
    ap.add_argument("--regrade", action="store_true", help="grade the saved answers again, no calls")
    ap.add_argument("--jobs", type=int, default=3)
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    global RAW, OUT
    if args.hint:
        RAW, OUT = RAW.with_name("project-raw-hint"), OUT.with_name("project-report-hint.md")
    if args.regrade:
        rows = json.loads((RAW / "rows.json").read_text(encoding="utf-8"))
        for r in rows:
            r["correct"] = bool(QUESTIONS[r["q"]][3](r["answer"].lower()))
        (RAW / "rows.json").write_text(json.dumps(rows, indent=1, ensure_ascii=False), encoding="utf-8")
        OUT.write_text(report(rows, sys.argv[1:]), encoding="utf-8")
        print(f"{sum(r['correct'] for r in rows)} of {len(rows)} correct -> {OUT.relative_to(ROOT).as_posix()}")
        return
    claude = shutil.which("claude")
    if not claude:
        sys.exit("claude is not on the PATH")
    work = Path(tempfile.mkdtemp())
    setup(work)
    jobs = [(c, m, qi, rep) for rep in range(1, args.reps + 1) for c in args.conditions.split(",")
            for m in args.models.split(",") for qi in range(len(QUESTIONS))]
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        rows = list(pool.map(lambda j: run_one(claude, work, *j, hint=args.hint), jobs))
    for r in rows:
        print(f"{r['condition']:<6} {r['model']:<7} q{r['q'] + 1} rep {r['rep']}: {'OK ' if r['correct'] else 'BAD'} "
              f"{r['end'] / 1000:5.1f} s tools={r['tool_calls']}  {r['answer'][:70]}")
    OUT.write_text(report(rows, sys.argv[1:]), encoding="utf-8")
    (RAW / "rows.json").write_text(json.dumps(rows, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{sum(r['correct'] for r in rows)} of {len(rows)} correct -> {OUT.relative_to(ROOT).as_posix()}")


if __name__ == "__main__":
    main()
