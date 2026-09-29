"""Time graph recall offline, as the graph grows. Writes bench/recall-report.md.

    python bench/recall_bench.py

No model, no network. Builds test graphs in a temp folder (tests/graphs.py),
so the repo's graph.db is left alone. Takes a minute or so.
"""
import json
import os
import platform
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from graphs import REFUND, build, clusters, policies, recall  # noqa: E402

OUT = ROOT / "bench" / "recall-report.md"
QUESTIONS = [
    REFUND,
    "Who approves supplier payments over £2,000?",
    "What is the onboarding process?",
    "What does Priya do?",
    "Who is in charge when the boss is away?",
]
GROWTH = [
    ("Demo graph", None),
    ("+1,000 policies elsewhere", clusters(1000)),
    ("+10,000 policies elsewhere", clusters(10000)),
    ("+100 policies on the Ops Manager", policies(100)),
    ("+1,000 policies on the Ops Manager", policies(1000)),
    ("+10,000 policies on the Ops Manager", policies(10000)),
]
ANSWER = ("Sarah Chen", "delegates_to", "Marcus Webb")


def median_ms(fn, runs):
    times = []
    for _ in range(runs):
        t0 = time.perf_counter()
        fn()
        times.append((time.perf_counter() - t0) * 1000)
    return statistics.median(times)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    tmp = tempfile.TemporaryDirectory()
    rows = []
    for label, extra in GROWTH:
        folder = Path(tmp.name) / str(len(rows))
        t0 = time.perf_counter()
        recall.DB = build(folder, *([extra] if extra else []))
        build_ms = (time.perf_counter() - t0) * 1000
        with sqlite3.connect(recall.DB) as db:
            entities = db.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
        db.close()
        facts = recall.recall(REFUND)
        ms = statistics.median(recall.recall(REFUND).ms for _ in range(15))
        kept = ANSWER in {(f.source, f.predicate, f.target) for f in facts.triples}
        rows.append((label, entities, ms, len(facts.triples), len(facts.as_text()), kept, build_ms))
        print(f"{label}: {ms:.2f} ms", flush=True)

    recall.DB = build(Path(tmp.name) / "demo")
    sizes = [(q, recall.recall(q)) for q in QUESTIONS]
    prompt = json.dumps({"prompt": REFUND}).encode()
    env = {**os.environ, "GRAPH_MEMORY_DB": str(recall.DB)}
    python_ms = median_ms(lambda: subprocess.run([sys.executable, "-c", "pass"]), 25)
    hook_ms = median_ms(lambda: subprocess.run(
        [sys.executable, str(ROOT / "src" / "recall_hook.py")], input=prompt,
        capture_output=True, env=env), 25)
    recall.DB = recall.ROOT / "graph.db"
    tmp.cleanup()

    lines = [
        "# Graph recall benchmark",
        "",
        f"Run {datetime.now():%Y-%m-%d %H:%M} on {platform.system()} {platform.release()}, "
        f"Python {platform.python_version()}, SQLite {sqlite3.sqlite_version}. "
        "Made by `python bench/recall_bench.py`.",
        "",
        "## Recall as the graph grows",
        "",
        "The refund question: “A customer wants an £800 refund in March. Who signs it off?”. "
        "Time is `recall()` alone, median of 15 warm calls.",
        "",
        "| Graph | Entities | recall() | Facts | Injection chars | Answer in the facts | Build |",
        "| --- | ---: | ---: | ---: | ---: | --- | ---: |",
    ]
    for label, entities, ms, n, chars, kept, build_ms in rows:
        lines.append(f"| {label} | {entities:,} | {ms:.2f} ms | {n} | {chars:,} | "
                     f"{'yes' if kept else 'no'} | {build_ms:,.0f} ms |")
    lines += [
        "",
        "## The hook as a process",
        "",
        "| Measure | Median of 25 |",
        "| --- | ---: |",
        f"| Python starting, doing nothing | {python_ms:.0f} ms |",
        f"| `src/recall_hook.py`, refund question, demo graph | {hook_ms:.0f} ms |",
        "",
        "Inside Claude Code the hook takes longer: Claude Code has to launch it.",
        "",
        "## Injection size by question, demo graph",
        "",
        "| Question | Facts | Characters |",
        "| --- | ---: | ---: |",
    ]
    for q, facts in sizes:
        lines.append(f"| {q} | {len(facts.triples)} | {len(facts.as_text()):,} |")
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
