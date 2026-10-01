"""The query cases, live: a model writing SQL against the database, with and without the
query the company already uses for the question.

    python bench/query_eval.py                               sonnet, twice per case and condition
    python bench/query_eval.py --models haiku,sonnet --reps 1 --cases 01,03

Spends model usage on your subscription and needs `claude` on the PATH.
Writes bench/query-report.md, and each run's events to bench/query-raw/.

Both conditions get the question, the schema, and a read-only way to run SQL
(`python query.py "..."`, the only tool allowed), in a folder holding a fresh copy of
the database and nothing else. The indexed condition also gets the source file that
holds the case's query, whole, as the knowledge layer would hand it over: decoys in
the same file included, and dates and parameters still to adjust. The run is graded
by running the last ```sql block of its answer against the database.
"""
import argparse
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASES_DIR = ROOT / "querygraph" / "cases"
sys.path.insert(0, str(CASES_DIR))
import check  # noqa: E402

OUT = ROOT / "bench" / "query-report.md"
RAW = ROOT / "bench" / "query-raw"
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


def prompt(case, condition):
    db = case["database"]
    ddl = (CASES_DIR / db / "schema.sql").read_text(encoding="utf-8").strip()
    parts = [case["question"], "",
             f"The database is {db}.db in this folder: SQLite, read-only. Its schema:", "", ddl, "",
             'Run a query with: python query.py "<SQL>"', ""]
    if condition == "indexed":
        src = case["source"]
        parts += [f"The knowledge layer found this for the question, in {src['path'].split('/', 1)[1]}:", "",
                  "-----", (CASES_DIR / src["path"]).read_text(encoding="utf-8").strip(), "-----", ""]
    parts += ["Finish with the answer, and the one SQLite query that gives it in a ```sql block, "
              "with the answer in the first column of its first row. Give a percentage as a percentage (12.5, not 0.125)."]
    return "\n".join(parts)


def run(claude, model, case, condition, rep, dbs, raw):
    work = Path(tempfile.mkdtemp(prefix="qeval-"))
    try:
        shutil.copy(dbs[case["database"]], work / f"{case['database']}.db")
        (work / "query.py").write_text(QUERY_PY, encoding="utf-8")
        argv = [claude, "-p", "--model", model, "--output-format", "stream-json", "--verbose",
                "--tools", "Bash", "--allowedTools", "Bash(python query.py:*)",
                "--setting-sources", "local", "--strict-mcp-config", "--no-session-persistence"]
        t0 = time.perf_counter()
        p = subprocess.run(argv, cwd=work, input=prompt(case, condition).encode("utf-8"), capture_output=True)
        seconds = time.perf_counter() - t0
    finally:
        shutil.rmtree(work, ignore_errors=True)
    events = [json.loads(line) for line in p.stdout.decode("utf-8", "replace").splitlines() if line.startswith("{")]
    name = f"{case['id']}-{condition}-{model}-{rep}"
    (raw / f"{name}.jsonl").write_text("\n".join(json.dumps(e) for e in events), encoding="utf-8")
    result = next((e for e in reversed(events) if e.get("type") == "result"), {})
    text = result.get("result", "")
    queries = sum(1 for e in events if e.get("type") == "assistant"
                  for b in e["message"].get("content", []) if b.get("type") == "tool_use")
    got, error = grade(case, text, dbs)
    return {"case": case["id"], "condition": condition, "model": model, "rep": rep, "got": got, "error": error,
            "correct": check.right(case, got) if isinstance(got, (int, float)) else False,
            "seconds": round(seconds, 1), "queries": queries, "cost": result.get("total_cost_usd")}


def grade(case, text, dbs):
    """Run the answer's last ```sql block: its first column, or the case's answer column."""
    blocks = [b.split("```", 1)[0] for b in text.split("```sql")[1:]]
    if not blocks:
        return None, "no sql block"
    try:
        with closing(sqlite3.connect(f"file:{dbs[case['database']]}?mode=ro", uri=True)) as conn:
            cur = conn.execute(blocks[-1])
            row, names = cur.fetchone(), [d[0] for d in cur.description]
    except sqlite3.Error as e:
        return None, f"sql error: {e}"
    if row is None:
        return None, "no rows"
    col = case.get("answer_column")
    if col in names and check.right(case, row[names.index(col)]):
        return row[names.index(col)], None
    numbers = [v for v in row if isinstance(v, (int, float))]
    return (numbers[0], None) if numbers else (None, f"no number in the first row: {row}")


def regrade(rows, cases, dbs):
    """The saved runs graded again with the current grade() and answers; times and costs kept."""
    by_id = {c["id"]: c for c in cases}
    out = []
    for r in (r for r in rows if r["case"] in by_id):
        case = by_id[r["case"]]
        events = [json.loads(line) for line in
                  (RAW / f"{r['case']}-{r['condition']}-{r['model']}-{r['rep']}.jsonl").read_text(encoding="utf-8").splitlines()]
        result = next((e for e in reversed(events) if e.get("type") == "result"), {})
        got, error = grade(case, result.get("result", ""), dbs)
        out.append({**r, "got": got, "error": error,
                    "correct": check.right(case, got) if isinstance(got, (int, float)) else False})
    return out


def report(rows, args):
    lines = [f"# Query cases, live ({datetime.now():%d %B %Y})", "",
             f"Made by `python bench/query_eval.py --models {args.models} --reps {args.reps}"
             + (f" --cases {args.cases}" if args.cases else "") + "`.", "",
             "Both conditions: the question, the schema, and read-only SQL through `python query.py`. "
             "Indexed: also the source file holding the company's query for it. "
             "Graded by running the answer's last SQL block.", "",
             "| Case | Model | Schema only | Indexed |", "|---|---|---|---|"]
    for cid in dict.fromkeys(r["case"] for r in rows):
        for model in args.models.split(","):
            cell = {}
            for cond in ("schema", "indexed"):
                rs = [r for r in rows if r["case"] == cid and r["model"] == model and r["condition"] == cond]
                vals = ", ".join(str(r["got"]) if r["got"] is not None else r["error"] for r in rs)
                cell[cond] = f"{sum(r['correct'] for r in rs)} of {len(rs)} ({vals})"
            lines.append(f"| {cid} | {model} | {cell['schema']} | {cell['indexed']} |")
    lines += ["", "| Condition | Model | Correct | Median time | Median queries run | Cost |", "|---|---|---|---|---|---|"]
    for model in args.models.split(","):
        for cond in ("schema", "indexed"):
            rs = [r for r in rows if r["model"] == model and r["condition"] == cond]
            med = lambda xs: sorted(xs)[len(xs) // 2] if xs else 0  # noqa: E731
            cost = sum(r["cost"] or 0 for r in rs)
            lines.append(f"| {cond} | {model} | {sum(r['correct'] for r in rs)} of {len(rs)} | "
                         f"{med([r['seconds'] for r in rs])} s | {med([r['queries'] for r in rs])} | ${cost:.2f} |")
    lines += ["", "Answers: " + "; ".join(f"{c['id']} {c['answer']}" for c in check.load()["cases"]
                                        if any(r["case"] == c["id"] for r in rows)), ""]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--models", default="sonnet")
    ap.add_argument("--reps", type=int, default=2)
    ap.add_argument("--cases", default="", help="comma-separated id prefixes")
    ap.add_argument("-j", type=int, default=5, help="runs at once")
    ap.add_argument("--regrade", action="store_true", help="grade the saved runs again, without running the model")
    args = ap.parse_args()
    claude = shutil.which("claude")
    if not claude and not args.regrade:
        sys.exit("claude is not on the PATH")
    wanted = [c for c in args.cases.split(",") if c]
    cases = [c for c in check.load()["cases"] if not wanted or any(c["id"].startswith(w) for w in wanted)]
    RAW.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        dbs = check.build_all(tmp)
        if args.regrade:
            rows = regrade(json.loads((RAW / "rows.json").read_text(encoding="utf-8")), cases, dbs)
        else:
            jobs = [(m, c, cond, rep) for m in args.models.split(",") for c in cases
                    for cond in ("schema", "indexed") for rep in range(1, args.reps + 1)]
            with ThreadPoolExecutor(args.j) as pool:
                rows = list(pool.map(lambda j: run(claude, j[0], j[1], j[2], j[3], dbs, RAW), jobs))
    for r in rows:
        print(f"{r['case']:<26} {r['condition']:<8} {r['model']:<7} {r['rep']}  "
              f"{'right' if r['correct'] else 'wrong'}  {r['got'] if r['got'] is not None else r['error']}  "
              f"{r['seconds']} s, {r['queries']} queries")
    (RAW / "rows.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
    OUT.write_text(report(rows, args), encoding="utf-8")
    print(f"\nwrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
