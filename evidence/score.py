"""The knowledge layer holding the evidence: what it finds, with no model in the loop.

    python evidence/score.py                    the gold and bare stores, in both index layouts
    python evidence/score.py --own DIR          also an OpenSpec root of a run's own (its archive beside the H1 one)
    python evidence/score.py --json OUT         the rows as JSON too

A store is the archived evidence changes as some policy wrote them:
- gold: evidence/openspec as written: numbers, keywords, queries and notes;
- bare: the same numbers and nothing else (index.bare: headings and tables), what a numbers-only store keeps;
- own: an OpenSpec root a run wrote (bench/evidence_eval.py keeps one per run).

Each goes into a workspace of the corpus, each evidence.md ingested as a document with evidence/evidence_index.py's
facts, and is scored on:
- thesis: each thesis number looked up as the service's research looks (kl/impact.py: every word of the
  label in one fact, one figure): found, and the right figure? The take-up is in no data, so it is right
  not to find it.
- recall: for each question, the service's context call. sets: the evidence sets the answer comes from are in
  it. numbers: the facts holding those numbers (from the archive the question is about) are in it. support: a
  caveat's wording is in it. superseded: a figure a later archive replaced is in it (for a question not about an earlier period).
"""
import argparse
import importlib.util
import json
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "evidence"
sys.path[:0] = [str(ROOT), str(ROOT / "tests"), str(HERE)]
import kl_support as ks  # noqa: E402  pins today (2026-09-23), as the kl tests run
_spec = importlib.util.spec_from_file_location("evidence_check", HERE / "cases" / "check.py")
check = sys.modules.setdefault("evidence_check", importlib.util.module_from_spec(_spec))  # not querygraph's check
if not hasattr(check, "load"):
    _spec.loader.exec_module(check)
import evidence_index as index  # noqa: E402  (codegraph has an index module too)

GOLD = HERE / "openspec"
H1 = "2026-07-01"


def store_files(kind: str, root: Path = None) -> dict:
    """{path: text} of the archived evidence a store holds. own: the run's root, plus the H1 archive if the
    run did not keep its own copy of it."""
    files = index.read_root(root or GOLD)
    if kind == "own" and not any(index.ARCHIVED.search(p) and H1 in p for p in files):
        files.update({p: t for p, t in index.read_root(GOLD).items() if H1 in p})
    if kind == "bare":
        files = {p: index.bare(t) for p, t in files.items()}
    return files


def workspace(files: dict, layout: str = "set"):
    """(service, principal, {graph doc path: (extraction, text)}, problems): a seeded workspace holding the store."""
    svc, _, p = ks.seeded(Path(tempfile.mkdtemp(prefix="evidence-score-")))
    docs, problems = index.index(files, layout=layout)
    by_doc = {}
    texts = {f"evidence/{d}-{c}/evidence.md": t for d, c, _, t in index.archives(files)}
    for path, x in docs.items():
        r = svc.ingest(p, name=path, text=texts[path], extraction=x)
        if r["status"] not in ("active", "current"):
            problems += [f"{path}: {r['status']}"] + list(r.get("problems") or [])
        by_doc[path] = (x, texts[path])
    svc.projector.apply_pending(p.workspace_id)
    return svc, p, by_doc, problems


def number_claims(by_doc: dict) -> dict:
    """{(archive date, set id, key): (doc path, claim)} for every numbers-table row a store indexed."""
    out = {}
    for path, (x, text) in by_doc.items():
        date = re.search(r"\d{4}-\d{2}-\d{2}", path).group(0)
        parsed = index.parse(text)
        for s in parsed["sets"]:
            for n in s["numbers"]:
                c = next((c for node in x["nodes"] for c in node["claims"] if c.get("quote") == index.clip(n["line"])),
                         None)
                if c:
                    out[(date, s["id"], n["key"].strip("` ").lower())] = (path, c)
    return out


def thesis_rows(svc, p, spec) -> list:
    ws = p.workspace_id
    facts = svc._number_facts(ws)
    rows = []
    for n in spec["thesis"]["numbers"]:
        hit, note = svc._find(facts, n)
        rec = check.number(spec, "2026-09-15", n["expect"]["set"], n["expect"]["key"]) if n["expect"] else {}
        want = rec.get("value")
        got = hit["value"] if hit else None
        right = (got is None) if want is None else (got is not None and check.same(want, got, rec.get("tolerance", 0.005)))
        rows.append({"key": n["key"], "label": n["label"], "want": want, "got": got, "right": right,
                     "source": hit["source"] if hit else None, "note": note})
    return rows


def recall_rows(svc, p, spec, questions, by_doc) -> list:
    claims_of = number_claims(by_doc)
    rows = []
    for q in questions:
        ctx = svc.context(p, q["question"])
        text = ctx["text"].lower()
        got = ctx["claims"]
        entities = {c["entity"].lower() for c in got}
        refs = [r.split("/") for r in (q.get("from") or {}).values()]
        need_sets = sorted({index.evidence_name(s) for _, s, _ in refs})
        sets_in = [s for s in need_sets if s in entities or any(e.startswith(s[:-len("evidence")]) for e in entities)]
        nums_in, nums_missing = [], []
        for date, set_id, key in refs:
            held = claims_of.get((date, set_id, key))
            if held is None:
                nums_missing.append(f"{date}/{set_id}/{key} (not stored)")
                continue
            doc, claim = held
            if any(c["text"] == claim["text"] and (c.get("source") or {}).get("doc", "").endswith(doc) for c in got) \
                    or index.clip(claim["quote"]).lower() in text:
                nums_in.append(f"{date}/{set_id}/{key}")
            else:
                nums_missing.append(f"{date}/{set_id}/{key}")
        support = q.get("support")
        supported = None if not support else any(s.lower() in text for s in support)
        stale = None
        if q["kind"] != "period":  # a question about today: is a superseded figure shown for it?
            stale = any((c.get("valid_to") or "9999") <= ctx["as_of"] for c in got)
        rows.append({"id": q["id"], "kind": q["kind"], "period": ctx["period"], "sets": f"{len(sets_in)}/{len(need_sets)}",
                     "numbers": f"{len(nums_in)}/{len(refs)}", "missing": nums_missing, "support": supported,
                     "stale": stale, "claims": len(got), "chars": len(ctx["text"]),
                     "complete": len(nums_in) == len(refs) and supported is not False})
    return rows


def score(kind, root=None, layout="set"):
    spec, questions = check.load(), check.load_questions()["questions"]
    svc, p, by_doc, problems = workspace(store_files(kind, root), layout)
    try:
        return {"store": kind, "layout": layout, "problems": problems, "thesis": thesis_rows(svc, p, spec),
                "recall": recall_rows(svc, p, spec, [q for q in questions if q["kind"] != "out-of-scope"], by_doc)}
    finally:
        svc.close()


def show(result):
    print(f"\n== {result['store']}, {result['layout']} layout ==")
    for prob in result["problems"]:
        print("  problem:", prob)
    th = result["thesis"]
    print(f"  thesis numbers right: {sum(r['right'] for r in th)} of {len(th)}")
    for r in th:
        print(f"    {r['key']:<22} {'right' if r['right'] else 'WRONG':<6} got {r['got']!s:<10} want {r['want']!s:<10} {r['note'][:110]}")
    rc = result["recall"]
    print(f"  questions whose recall holds every number and caveat they need: {sum(r['complete'] for r in rc)} of {len(rc)}")
    for r in rc:
        flags = [f"sets {r['sets']}", f"numbers {r['numbers']}"]
        if r["support"] is not None:
            flags.append(f"support {'yes' if r['support'] else 'NO'}")
        if r["stale"]:
            flags.append("superseded shown")
        print(f"    {r['id']:<22} {r['kind']:<9} {'ok  ' if r['complete'] else 'MISS'} {', '.join(flags)}; "
              f"{r['claims']} claims, {r['chars']} chars, {r['period']}" + (f"; missing {r['missing']}" if r["missing"] else ""))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--own", help="an OpenSpec root holding a run's archived evidence")
    ap.add_argument("--stores", default="gold,bare")
    ap.add_argument("--layouts", default="set,number")
    ap.add_argument("--json", help="write the rows here too")
    args = ap.parse_args()
    layouts = [x for x in args.layouts.split(",") if x]
    results = [score(k, layout=lay) for k in args.stores.split(",") if k for lay in layouts]
    if args.own:
        results += [score("own", Path(args.own), lay) for lay in layouts]
    for r in results:
        show(r)
    if args.json:
        Path(args.json).write_text(json.dumps(results, indent=1, ensure_ascii=False, default=str), encoding="utf-8")


if __name__ == "__main__":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    main()
