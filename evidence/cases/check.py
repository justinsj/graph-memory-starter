"""Every number in evidence.json and every answer in questions.json, against a fresh build of the database.

    python evidence/cases/check.py              the values, one table per evidence set, then the questions
    python evidence/cases/check.py --fill       write each number's value into evidence.json (after a seed change)

A number's value is what its SQL gives over the views evidence.json defines. A recorded value that the SQL
no longer gives is reported, and tests/test_evidence_cases.py fails on it. A question's answer is worked
out from the numbers it names (`from`), so the questions cannot drift from the evidence.
"""
import argparse
import importlib.util
import json
import sqlite3
import sys
import tempfile
from contextlib import closing
from pathlib import Path

CASES_DIR = Path(__file__).resolve().parent


def load_module(name, path):
    """A module by its path, under a name of its own: querygraph/cases has a check.py and a build.py too,
    and one process may load both."""
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, path)
        sys.modules[name] = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(sys.modules[name])
    return sys.modules[name]


build = load_module("evidence_build", CASES_DIR / "build.py")

EVIDENCE = CASES_DIR / "evidence.json"
QUESTIONS = CASES_DIR / "questions.json"


def load():
    return json.loads(EVIDENCE.read_text(encoding="utf-8"))


def load_questions():
    return json.loads(QUESTIONS.read_text(encoding="utf-8"))


def connect(path):
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    for view in load()["views"]:
        conn.execute(view)
    return conn


def scalar(conn, sql):
    row = conn.execute(sql).fetchone()
    v = row[0] if row else None
    return int(v) if isinstance(v, float) and v.is_integer() and "ROUND" not in sql.upper() else v


def computed(conn, spec=None):
    """{(archive date, set id, key): value} for every number: from its SQL, or as written (a verdict)."""
    spec = spec or load()
    out = {}
    for a in spec["archives"]:
        for s in a["sets"]:
            for n in s["numbers"]:
                out[(a["date"], s["id"], n["key"])] = scalar(conn, n["sql"]) if "sql" in n else n["value"]
    return out


def traps(conn, spec=None):
    """{(archive date, set id, key): [(value, why)]}: what each plausible slip gives instead."""
    spec = spec or load()
    return {(a["date"], s["id"], n["key"]): [(scalar(conn, t["sql"]), t["why"]) for t in n["traps"]]
            for a in spec["archives"] for s in a["sets"] for n in s["numbers"] if n.get("traps")}


def number(spec, date, set_id, key):
    a = next(a for a in spec["archives"] if a["date"] == date)
    s = next(s for s in a["sets"] if s["id"] == set_id)
    return next(n for n in s["numbers"] if n["key"] == key)


def same(want, got, tolerance=0.0):
    if isinstance(want, (int, float)) and isinstance(got, (int, float)):
        return abs(float(want) - float(got)) <= tolerance + 1e-9
    return str(want).strip().lower() == str(got).strip().lower()


def answer_of(q, spec=None):
    """A question's answer from the numbers it names: one number as it is, or a formula over several."""
    spec = spec or load()
    vals = {}
    for name, ref in (q.get("from") or {}).items():
        date, set_id, key = ref.split("/")
        vals[name] = number(spec, date, set_id, key)["value"]
    if "formula" in q:
        v = eval(q["formula"], {"__builtins__": {}, "round": round}, vals)  # noqa: S307  the case's own arithmetic
        return round(v, q.get("round", 2))
    if "answer" in q:
        return q["answer"]
    return next(iter(vals.values()))


def brief_text(spec=None):
    """What an analyst is told: the thesis, the period, the definitions, and for each set the numbers to
    establish by key, in words that are not the evidence's own labels."""
    spec = spec or load()
    b = spec["brief"]
    a = next(a for a in spec["archives"] if a["change"] == "bundle-evidence")
    lines = [f"# {b['title']}", "", f"Thesis: {b['thesis']}", f"Period: {b['period']}", "", "Definitions:"]
    lines += [f"- {d}" for d in b["definitions"]]
    lines += ["", "Evidence sets, and the numbers each must give, by key (more numbers are welcome):"]
    for ask, s in zip(b["asks"], a["sets"]):
        lines.append(f"- {ask}")
        lines += [f"  - `{n['key']}`: {n['ask']}" for n in s["numbers"]]
    return "\n".join(lines)


def fmt(v):
    if isinstance(v, float):
        return f"{v:,.2f}" if abs(v) >= 1000 else f"{v:g}"
    return f"{v:,}" if isinstance(v, int) else str(v)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--fill", action="store_true", help="write each number's value into evidence.json")
    args = ap.parse_args()
    spec = load()
    with tempfile.TemporaryDirectory() as tmp:
        with closing(connect(build.build("sales", tmp))) as conn:
            got, trapped = computed(conn, spec), traps(conn, spec)
    if args.fill:
        text = EVIDENCE.read_text(encoding="utf-8")
        for a in spec["archives"]:
            for s in a["sets"]:
                for n in s["numbers"]:
                    if "sql" in n:
                        n["value"] = got[(a["date"], s["id"], n["key"])]
        out = json.dumps(spec, ensure_ascii=False, indent=1)
        EVIDENCE.write_text(out + "\n", encoding="utf-8")
        print(f"filled {sum(1 for k in got)} values into {EVIDENCE.name}" + (" (unchanged)" if out + "\n" == text else ""))
        return
    bad = 0
    for a in spec["archives"]:
        print(f"\n{a['date']}-{a['change']} ({a['period']})")
        for s in a["sets"]:
            print(f"  {s['id']}: {s['claim']}")
            for n in s["numbers"]:
                k = (a["date"], s["id"], n["key"])
                mark = "" if "value" not in n or same(n["value"], got[k]) else f"   RECORDED {fmt(n['value'])}"
                bad += bool(mark)
                trap = "".join(f"   (slip: {fmt(v)}, {why})" for v, why in trapped.get(k, []))
                print(f"    {n['key']:<28} {fmt(got[k]):>14} {n['unit']:<14}{mark}{trap}")
    if QUESTIONS.exists():
        print("\nquestions")
        for q in load_questions()["questions"]:
            print(f"  {q['id']:<24} {q['kind']:<10} {fmt(answer_of(q, spec)):>14}  {q['question']}")
    if bad:
        sys.exit(f"\n{bad} recorded value(s) the SQL no longer gives: run with --fill after checking them")


if __name__ == "__main__":
    main()
