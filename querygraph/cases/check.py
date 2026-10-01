"""Each case in questions.json, run against a fresh build of its database.

    python querygraph/cases/check.py              the values, one table per case
    python querygraph/cases/check.py --cases 01   some of the cases

For each case it runs:
- the indexed query, taken from its source file and adjusted as the case records
  (parameters bound, or hard-coded dates and filters edited by hand);
- the query written from the schema alone;
- the indexed query with each rule taken out, one at a time.

Only the first should give the answer. tests/test_query_cases.py asserts it.
"""
import argparse
import ast
import json
import re
import sqlite3
import sys
import tempfile
from contextlib import closing
from pathlib import Path

CASES_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(CASES_DIR))
import build  # noqa: E402


def load():
    return json.loads((CASES_DIR / "questions.json").read_text(encoding="utf-8"))


def extract(path, how):
    """The query as its source holds it: a Python string constant, the nth ```sql block
    of a Markdown file, or a whole .sql file."""
    text = (CASES_DIR / path).read_text(encoding="utf-8")
    if "python_constant" in how:
        for node in ast.walk(ast.parse(text)):
            if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == how["python_constant"] for t in node.targets):
                return node.value.value
        raise KeyError(f"{path} has no constant {how['python_constant']}")
    if "sql_block" in how:
        return re.findall(r"```sql\n(.*?)```", text, re.S)[how["sql_block"] - 1]
    return text


def edit(sql, edits):
    """Apply [find, replace] pairs in order, each to every occurrence. A find that is not
    there is an error, so an edit can never silently do nothing."""
    for find, replace in edits:
        if find not in sql:
            raise ValueError(f"not in the query: {find!r}")
        sql = sql.replace(find, replace)
    return sql


def indexed_query(case):
    src = case["source"]
    return edit(extract(src["path"], src["extract"]), src.get("adjust", []))


def value(conn, sql, params=None, column=None):
    cur = conn.execute(sql, params or {})
    row = cur.fetchone()
    names = [d[0] for d in cur.description]
    return row[names.index(column)] if column else row[0]


def run(case, conn):
    """The indexed query's value, the schema-only query's, and each rule's ablation."""
    sql, params, column = indexed_query(case), case["source"].get("params", {}), case.get("answer_column")
    out = {"indexed": value(conn, sql, params, column), "naive": value(conn, case["naive_sql"]), "without": {}}
    for rule in case["rules"]:
        out["without"][rule["id"]] = value(conn, *ablation(case, rule), column)
    return out


def ablation(case, rule):
    """The indexed query with one rule taken out, and its parameters."""
    w, params = rule["without"], case["source"].get("params", {})
    return edit(indexed_query(case), w.get("edits", [])), {**params, **w.get("params", {})}


def right(case, got):
    return got is not None and abs(got - case["answer"]) <= case.get("tolerance", 0)


def build_all(out_dir):
    return {name: build.build(name, out_dir) for name in build.DATABASES}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cases", default="", help="comma-separated id prefixes, e.g. 01,04")
    args = ap.parse_args()
    wanted = [c for c in args.cases.split(",") if c]
    with tempfile.TemporaryDirectory() as tmp:
        dbs = build_all(tmp)
        for case in load()["cases"]:
            if wanted and not any(case["id"].startswith(w) for w in wanted):
                continue
            with closing(sqlite3.connect(dbs[case["database"]])) as conn:
                got = run(case, conn)
            mark = lambda v: "right" if right(case, v) else "wrong"  # noqa: E731
            print(f"\n{case['id']}: {case['question']}")
            print(f"  answer                 {case['answer']}")
            print(f"  indexed query          {got['indexed']}  {mark(got['indexed'])}")
            print(f"  from the schema alone  {got['naive']}  {mark(got['naive'])}")
            for rule in case["rules"]:
                v = got["without"][rule["id"]]
                print(f"  without {rule['id']:<22} {v}  {mark(v)}")


if __name__ == "__main__":
    main()
