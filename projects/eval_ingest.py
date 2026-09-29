"""Re-test ingest against the cases, with the real model.

    python projects/eval_ingest.py
    python projects/eval_ingest.py --cases 01,04 --reps 3 --models haiku,sonnet

For each case: ask for a change set from the case's input and its projects
before (ingest.propose), check it (model.validate), apply it, and score the
result against what the case expects (cases.check). The score reads facts, not
wording, so a different id, title or quote is not a failure; a missing step, a
wrong status or an invented project is. Writes projects/eval-report.md, and
each change set to projects/eval-raw/. One claude -p call per case, model and rep.
"""
import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import cases  # noqa: E402
import ingest  # noqa: E402
import model  # noqa: E402

REPORT = HERE / "eval-report.md"
RAW = HERE / "eval-raw"


def run_one(case, model_name, rep, entities) -> dict:
    """One proposal for one case, checked, applied and scored."""
    t0 = time.perf_counter()
    row = {"case": case["name"], "model": model_name, "rep": rep, "diff": None,
           "problems": [], "confirm": [], "fails": [], "error": None}
    try:
        diff = ingest.propose(case["input"], case["text"], case["before"], entities,
                              case["kind"], case["on"], model_name=model_name)
        row["diff"] = diff
        row["problems"], row["confirm"] = model.validate(case["before"], diff, case["text"],
                                                         model.name_map(entities))
        if not row["problems"]:
            after = model.apply(case["before"], diff, case["text"])[0]
            row["fails"] = cases.check(case["expect"], case["before"], diff, after)
    except Exception as exc:  # a bad reply is a result, not a crash
        row["error"] = f"{type(exc).__name__}: {exc}"
    row["seconds"] = time.perf_counter() - t0
    row["passed"] = not (row["error"] or row["problems"] or row["fails"])
    RAW.mkdir(exist_ok=True)
    (RAW / f"{case['name']}-{model_name}-{rep}.json").write_text(
        json.dumps(row, indent=1, ensure_ascii=False), encoding="utf-8")
    return row


def report(rows, all_cases, argv) -> str:
    by_name = {c["name"]: c for c in all_cases}
    passed = sum(r["passed"] for r in rows)
    models = list(dict.fromkeys(r["model"] for r in rows))
    lines = [f"# Ingest eval: change sets proposed from the cases",
             "",
             (f"Run {datetime.now():%Y-%m-%d %H:%M}. Made by `python projects/eval_ingest.py {' '.join(argv)}`."
              if "--from-raw" not in argv else
              f"Rebuilt {datetime.now():%Y-%m-%d %H:%M} from projects/eval-raw/: the runs of "
              f"`--models {','.join(models)} --reps {max(r['rep'] for r in rows)}`."),
             "",
             f"**{passed} of {len(rows)} runs passed**: a valid change set whose result meets the case's expectations. "
             f"{sum(bool((r['diff'] or {}).get('repaired')) for r in rows)} needed the repair round (the checks' "
             "problems sent back once).",
             "",
             "| Case | " + " | ".join(models) + " |",
             "| --- | " + " | ".join("---:" for _ in models) + " |"]
    for name in dict.fromkeys(r["case"] for r in rows):
        cells = []
        for m in models:
            mine = [r for r in rows if r["case"] == name and r["model"] == m]
            cells.append(f"{sum(r['passed'] for r in mine)} of {len(mine)}")
        lines.append(f"| {name}: {by_name[name]['title']} | " + " | ".join(cells) + " |")
    lines += ["", "## Every run", "",
             "| Case | Model | Rep | Changes (expected) | Repaired | Valid | Expectations | Needs you | Time | Result |",
             "| --- | --- | ---: | ---: | --- | --- | --- | ---: | ---: | --- |"]
    for r in rows:
        case = by_name[r["case"]]
        n = len(r["diff"]["changes"]) if r["diff"] else "—"
        valid = "error" if r["error"] else ("yes" if not r["problems"] else f"no ({len(r['problems'])})")
        met = "—" if (r["error"] or r["problems"]) else ("all" if not r["fails"] else f"{len(r['fails'])} missed")
        fixed = len((r["diff"] or {}).get("repaired", []))
        lines.append(f"| {r['case']} | {r['model']} | {r['rep']} | {n} ({len(case['diff']['changes'])}) "
                     f"| {f'{fixed} fixed' if fixed else '—'} | {valid} "
                     f"| {met} | {len(r['confirm'])} | {r['seconds']:.1f} s | {'pass' if r['passed'] else 'FAIL'} |")
    lines += ["", "## What each run proposed", ""]
    for r in rows:
        case = by_name[r["case"]]
        lines += [f"### {r['case']}, {r['model']}, rep {r['rep']}: {'pass' if r['passed'] else 'FAIL'}",
                  "", f"{case['title']}. {case['tests']}", ""]
        if r["error"]:
            lines += [f"Error: {r['error']}", ""]
        for label, items in (("The first answer's problems, sent back once", (r["diff"] or {}).get("repaired", [])),
                             ("Problems", r["problems"]), ("Missed expectations", r["fails"]),
                             ("Needs your confirmation", r["confirm"])):
            if items:
                lines += [f"{label}:", ""] + [f"- {x}" for x in items] + [""]
        if r["diff"]:
            lines += ["Proposed:", "", "```"] + ([model.describe(c) for c in r["diff"]["changes"]]
                                                 or ["(nothing to change)"]) + ["```", ""]
        lines += ["Expected:", "", "```"] + ([model.describe(c) for c in case["diff"]["changes"]]
                                             or ["(nothing to change)"]) + ["```", ""]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cases", help="comma-separated case numbers, e.g. 01,04 (default: all)")
    ap.add_argument("--models", default="sonnet", help="comma-separated, e.g. haiku,sonnet")
    ap.add_argument("--reps", type=int, default=1)
    ap.add_argument("--jobs", type=int, default=3, help="calls at once")
    ap.add_argument("--from-raw", action="store_true", help="rewrite the report from eval-raw/, no calls")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    all_cases = cases.all_cases()
    if args.from_raw:
        rows = [json.loads(p.read_text(encoding="utf-8")) for p in RAW.glob("*.json")]
        rows.sort(key=lambda r: (r["rep"], r["model"] != "sonnet", r["model"], r["case"]))
        REPORT.write_text(report(rows, all_cases, sys.argv[1:]), encoding="utf-8")
        print(f"{sum(r['passed'] for r in rows)} of {len(rows)} passed -> {REPORT.relative_to(ROOT).as_posix()}")
        return
    chosen = [c for c in all_cases if not args.cases or c["name"][:2] in args.cases.split(",")]
    entities = model.entities_from_extraction(ROOT / "extraction")
    jobs = [(c, m, rep) for rep in range(1, args.reps + 1) for m in args.models.split(",") for c in chosen]
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        rows = list(pool.map(lambda j: run_one(*j, entities), jobs))
    for r in rows:
        print(f"{r['case']:<24} {r['model']:<7} rep {r['rep']}  {'pass' if r['passed'] else 'FAIL'}  "
              f"{r['seconds']:5.1f} s  " + "; ".join((r["problems"] + r["fails"] + [r["error"] or ""])[:3]))
    REPORT.write_text(report(rows, all_cases, sys.argv[1:]), encoding="utf-8")
    print(f"{sum(r['passed'] for r in rows)} of {len(rows)} passed -> {REPORT.relative_to(ROOT).as_posix()}")


if __name__ == "__main__":
    main()
