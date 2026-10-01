"""Live: does the thesis prompt work beyond case 01? Six inputs from different kinds of project, each through the
service's own thesis path, with the thesis prompt as it was and as it is.

    python bench/thesis_domain_eval.py [--reps 3] [--prompts old,new] [--cases 01,02] [--workers 3]
    python bench/thesis_domain_eval.py --dry      # no model calls: check each case's fixed change set passes
    python bench/thesis_domain_eval.py --regrade  # grade the saved runs again, no calls

The cases (bench/thesis-domains/cases.json): case 01's helpdesk migration and five more (e-commerce page speed,
cancelling unused software seats, hiring technicians, a win-back email, and a legal footer change with nothing to
count). Each is a meeting transcript sent to the service as it runs by default (research before review, the thesis
call beside the change set's), in a workspace of the corpus and the documents in bench/thesis-domains/docs/, their
figures in the graph from recorded extractions. The change set is fixed per case, so the thesis is the only model
call; the research that follows (each number looked up in the graph by its label's words, or asked of a person) is
the service's own code.

The prompts: "old" is projects/thesis-prompt.md as it was, its worked example case 01's own answer
(bench/thesis-domains/prompts/); "new" is projects/thesis-prompt.md now, its example a clinic's missed
appointments, outside every case.

Each run is graded on what the service did with the draft: a thesis drafted from the input (or none, where the
case expects none); the research change request opened, its checks passed; the "because" quote traced to the
input; each formula number found in a document or asked of a named person; the figures a sound thesis would use
found (expect.use); none found that misreads the number (expect.wrong); no constant that is neither a unit
conversion nor a number the input states; no words from the prompt's own example in another domain's draft.
Writes bench/thesis-domains-report.md, and each run's calls and outcome to bench/thesis-domains-raw/.
"""
import argparse
import json
import re
import statistics
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "bench")]
import project_create_eval as pce  # noqa: E402  sets the day, the paths; its call() times one claude -p run
import kl_support as ks  # noqa: E402
import cases as case_files  # noqa: E402
from kl.extractors import ClaudeCliExtractor, FixtureExtractor  # noqa: E402

HERE = ROOT / "bench" / "thesis-domains"
RAW = ROOT / "bench" / "thesis-domains-raw"
OUT = ROOT / "bench" / "thesis-domains-report.md"
FIX = ROOT / "tests" / "fixtures" / "impact"
PROMPTS = {"old": HERE / "prompts" / "thesis-prompt.case01-example.md", "new": ROOT / "projects" / "thesis-prompt.md"}
EXAMPLE_WORDS = {"old": ("helpdesk", "tagging", "agent"), "new": ("appointment", "no-show", "reminder", "patient")}
EXAMPLE_CASE = {"old": "01", "new": None}  # the case each prompt's example is drawn from
CONVERSIONS = {7, 12, 24, 52, 60, 100, 365, 1000}
WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
         "ten": 10, "eleven": 11, "twelve": 12}
SPEC = json.loads((HERE / "cases.json").read_text(encoding="utf-8"))


def load_case(c):
    """The case with its input's text, file name, date and change set."""
    if c.get("from_case"):
        old = case_files.load(ROOT / c["from_case"])
        return {**c, "text": old["text"], "name": Path(old["diff"]["input"]).name, "on": old["diff"]["on"],
                "changes": old["diff"]["changes"]}
    return {**c, "text": (HERE / c["input"]).read_text(encoding="utf-8"), "name": Path(c["input"]).name}


def stated_numbers(text):
    """The numbers an input states, in digits or in words."""
    out = {float(x.replace(",", "")) for x in re.findall(r"\d[\d,]*(?:\.\d+)?", text)}
    return out | {float(v) for w, v in WORDS.items() if re.search(rf"\b{w}\b", text, re.I)}


# ---- one run: the service, its thesis call live ----------------------------------------------------------------------

class ThesisCall(ClaudeCliExtractor):
    """The service's claude-cli extractor with the change set fixed: the thesis call is the only live one, made
    with the prompt under test. dry: no model; every thesis call answers {"change": null}."""

    def __init__(self, model_name, prompt_path, changes, raw_dir, dry=False):
        super().__init__(model_name)
        self.prompt_path, self.changes, self.raw_dir, self.dry = prompt_path, changes, raw_dir, dry
        self.calls, self.drafts, self._lock = [], [], threading.Lock()
        self.fixture = FixtureExtractor()
        for folder in (FIX / "extraction", HERE / "extraction"):
            self.fixture.by_name.update(FixtureExtractor(folder).by_name)
        self.scratch = Path(tempfile.mkdtemp(prefix="kl-thesis-"))

    def extract(self, text, path):
        return self.fixture.extract(text, path)

    def propose_changes(self, text, path, kind, on, records, entities, preloaded=False):
        return json.loads(json.dumps(self.changes))

    def _ask(self, prompt, body):
        with self._lock:
            n = len(self.calls) + 1
            self.calls.append(None)
        if self.dry:
            r = {"text": '{"change": null}', "wall_ms": 0, "cost": 0.0}
        else:
            r = pce.call(self.model, body, self.scratch, raw=self.raw_dir / f"call-{n}.jsonl", system_prompt=prompt,
                         no_tools=True)
        self.calls[n - 1] = {"n": n, "body": body, **r}
        return r["text"]

    def _thesis(self, body):
        """As the service's own: the reply's JSON, a draft only when it names a change; every reply kept."""
        reply = self._ask(self.prompt_path.read_text(encoding="utf-8"), body)
        m = re.search(r"\{.*\}", reply, re.S)
        if not m:
            self.drafts.append(None)
            return None
        try:
            draft = json.loads(m.group(0))
        except ValueError:
            self.drafts.append({"unparsed": m.group(0)[:2000]})
            raise
        self.drafts.append(draft)
        return draft if draft.get("change") else None


def run_one(case, prompt, rep, model_name, dry=False):
    raw_dir = RAW / f"{case['id']}-{prompt}-{rep}"
    ex = ThesisCall(model_name, PROMPTS[prompt], case["changes"], raw_dir, dry=dry)
    svc, _, p = ks.seeded(Path(tempfile.mkdtemp(prefix="thesis-run-")))
    svc.extractor = ex
    ws = p.workspace_id
    svc.ingest(p, name="support-metrics.md", data=(FIX / "support-metrics.md").read_bytes())
    for name in SPEC["docs"]:
        svc.ingest(p, name=name, data=(HERE / "docs" / name).read_bytes())
    svc.projector.apply_pending(ws)
    seen = {}
    research_input = svc.research_input

    def watched(*a, **k):
        seen["research"] = out = research_input(*a, **k)
        return out
    svc.research_input = watched
    t0 = time.perf_counter()
    r = svc.ingest(p, name=case["name"], kind="transcript", text=case["text"], on=case["on"])
    wall = (time.perf_counter() - t0) * 1000
    result = r["job"]["result"]
    cr1 = svc.get_change_request(p, result["change_request"])
    cr2 = svc.get_change_request(p, result["research"]) if result.get("research") else None
    before_review = len(ex.calls)
    pid = next(ch["project"] for ch in case["changes"] if ch["op"] == "create_project")
    impact = None
    if cr2 and not dry:  # approve both, as a reviewer would, to read the thesis the service states
        svc.approve_change_request(p, cr1["id"], note="eval")
        svc.approve_change_request(p, cr2["id"], note="eval")
        impact = svc.project_impact(p, pid)
    svc.close()
    research = seen.get("research") or {}
    return {"case": case["id"], "prompt": prompt, "rep": rep, "model": model_name, "wall_ms": round(wall),
            "cr1_problems": cr1["problems"], "project": pid,
            "research": {"opened": bool(cr2), "notes": research.get("notes"), "problems": research.get("problems"),
                         "ops": cr2["ops"] if cr2 else None, "diff": cr2["diff"] if cr2 else None},
            "impact": {k: impact.get(k) for k in ("thesis", "working", "value", "unit", "direction", "missing",
                                                  "estimated", "complete")} if impact else None,
            "drafts": ex.drafts, "calls_before_review": before_review,
            "calls": [{k: v for k, v in c.items() if k in ("n", "wall_ms", "cost", "input_tokens", "output_tokens",
                                                           "model", "text", "first_token_ms")} for c in ex.calls]}


# ---- grading ---------------------------------------------------------------------------------------------------------

def grade(run, case):
    exp = case["expect"]
    first = run["drafts"][0] if run["drafts"] else None
    drafted = bool(isinstance(first, dict) and first.get("change"))
    ops = run["research"]["ops"] or []
    th = next((o for o in ops if o["op"] == "set_thesis"), None)
    formula = (th or {}).get("formula") or []
    keys = [k for k in formula if isinstance(k, str)]
    consts = [k for k in formula if isinstance(k, dict)]
    nums = {o["key"]: o for o in ops if o["op"] == "set_number"}
    found = {k: nums[k]["value"] for k in keys if nums.get(k, {}).get("status") == "found"}
    statuses = [nums.get(k, {}).get("status", "missing") for k in keys]
    found_vals = {float(v) for v in found.values()}
    allowed = CONVERSIONS | stated_numbers(case["text"])
    odd_consts = [c for c in consts if float(c.get("value", 0)) not in allowed]
    draft_text = json.dumps(run["drafts"], ensure_ascii=False).lower()
    leak = [w for w in EXAMPLE_WORDS[run["prompt"]] if w in draft_text] \
        if case["id"] != EXAMPLE_CASE[run["prompt"]] else []
    g = {"drafted": drafted, "opened": run["research"]["opened"], "refused": run["research"]["problems"] or [],
         "because": bool((th or {}).get("because", {}).get("source")),
         "found": sum(s == "found" for s in statuses), "asked": sum(s == "asked" for s in statuses),
         "needed": sum(s in ("needed", "missing") for s in statuses),
         "use_hit": sorted(set(map(float, exp["use"])) & found_vals), "use_of": len(exp["use"]),
         "wrong": sorted(set(map(float, exp["wrong"])) & found_vals), "odd_consts": odd_consts, "leak": leak,
         "calls": len(run["calls"]), "cost": sum(c.get("cost") or 0 for c in run["calls"])}
    if exp["thesis"]:
        g["ok"] = (drafted and g["opened"] and g["because"] and not g["needed"] and not g["wrong"]
                   and not odd_consts and not leak and len(g["use_hit"]) == len(exp["use"]))
    else:
        g["ok"] = not g["opened"] and not any(isinstance(d, dict) and d.get("change") for d in run["drafts"])
    return g


# ---- the report ------------------------------------------------------------------------------------------------------

def fmt_vals(vals):
    return ", ".join(f"{v:,g}" for v in vals) or "none"


def report(runs, cases):
    by = {}
    for r in runs:
        by.setdefault((r["case"], r["prompt"]), []).append(r)
    prompts = [p for p in ("old", "new") if any(k[1] == p for k in by)]
    lines = ["# The thesis call across kinds of project", "",
             f"{len(runs)} runs: {len(cases)} cases × prompts {', '.join(prompts)} × "
             f"{max(r['rep'] for r in runs) + 1} runs each. Model: {runs[0]['model']}. "
             "Written by bench/thesis_domain_eval.py.", "",
             "old: the thesis prompt with case 01's answer as its example. new: an example from a clinic, outside "
             "every case.", "",
             "| Case | Prompt | Sound | Drafted | Opened | Because | Found / asked / none | Expected figures found "
             "| Misread | Odd constant | Example's words | Calls | Cost |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    detail = []
    for c in cases:
        for pr in prompts:
            rs = by.get((c["id"], pr), [])
            if not rs:
                continue
            gs = [grade(r, c) for r in rs]
            n = len(gs)
            cnt = lambda key: sum(bool(g[key]) for g in gs)  # noqa: E731
            lines.append(
                f"| {c['id']} {c['title']} | {pr} | **{cnt('ok')}/{n}** | {cnt('drafted')}/{n} | {cnt('opened')}/{n} "
                f"| {cnt('because')}/{n} | {' · '.join(f'{g['found']}/{g['asked']}/{g['needed']}' for g in gs)} "
                f"| {' · '.join(f'{len(g['use_hit'])} of {g['use_of']}' for g in gs)} "
                f"| {' · '.join(fmt_vals(g['wrong']) for g in gs)} | {cnt('odd_consts')}/{n} | {cnt('leak')}/{n} "
                f"| {statistics.mean(g['calls'] for g in gs):.1f} | ${sum(g['cost'] for g in gs) / n:.3f} |")
            detail.append(f"\n### {c['id']} {c['title']} ({c['domain']}), prompt {pr}\n")
            for r, g in zip(rs, gs):
                imp = r["impact"] or {}
                d = next((x for x in r["drafts"] if isinstance(x, dict)), None) or {}
                th = next((o for o in (r["research"]["ops"] or []) if o["op"] == "set_thesis"), {})
                nums = [o for o in (r["research"]["ops"] or []) if o["op"] == "set_number"]
                detail.append(f"- run {r['rep'] + 1}: {'sound' if g['ok'] else 'NOT sound'}. "
                              + (f"Thesis: {imp.get('thesis')} Working: {imp.get('working') or '(none)'}. "
                                 if imp else f"No thesis opened. First reply: {json.dumps(r['drafts'][:1])[:300]}. ")
                              + (f"Formula: {th.get('formula')}; unit {th.get('unit')!r}. " if th else "")
                              + ("Numbers: " + "; ".join(
                                  f"{o['key']} ({o.get('label')}, {o.get('unit')}): {o['status']}"
                                  + (f" {o['value']:,g}" if o.get("value") is not None else "")
                                  + (f" in {o['found_in']['source']}" if o.get("found_in") else "")
                                  + (f", ask {o['ask']}" if o.get("ask") else "") for o in nums) + ". " if nums else "")
                              + (f"Refused: {g['refused']}. " if g["refused"] else "")
                              + (f"Odd constants: {g['odd_consts']}. " if g["odd_consts"] else "")
                              + (f"Example's words: {g['leak']}. " if g["leak"] else "")
                              + (f"Draft's change: {d.get('change')!r}." if not imp and d.get("change") else ""))
    OUT.write_text("\n".join(lines + ["", "## Each run"] + detail) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--prompts", default="old,new")
    ap.add_argument("--cases", default="")
    ap.add_argument("--model", default="sonnet")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--dry", action="store_true", help="no model calls: check each case's change set passes")
    ap.add_argument("--regrade", action="store_true", help="grade the saved runs again, no calls")
    args = ap.parse_args()
    cases = [load_case(c) for c in SPEC["cases"] if not args.cases or c["id"] in args.cases.split(",")]
    saved = RAW / "runs.json"
    if args.regrade:
        report(json.loads(saved.read_text(encoding="utf-8"))["runs"], cases)
        return
    if args.dry:
        for c in cases:
            r = run_one(c, "new", 0, args.model, dry=True)
            print(c["id"], "change set problems:", r["cr1_problems"] or "none", "| thesis calls:", len(r["calls"]))
        return
    warm, _, _ = ks.seeded(Path(tempfile.mkdtemp(prefix="thesis-warm-")))  # the template, made once, before threads
    warm.close()
    jobs = [(c, pr, rep) for rep in range(args.reps) for c in cases for pr in args.prompts.split(",")]
    runs, lock = [], threading.Lock()

    def go(job):
        c, pr, rep = job
        r = run_one(c, pr, rep, args.model)
        g = grade(r, c)
        with lock:
            runs.append(r)
            print(f"[{len(runs)}/{len(jobs)}] {c['id']} {pr} run {rep + 1}: {'sound' if g['ok'] else 'NOT sound'}, "
                  f"{g['calls']} call(s), ${g['cost']:.3f}", flush=True)
        return r
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        list(pool.map(go, jobs))
    runs.sort(key=lambda r: (r["case"], r["prompt"], r["rep"]))
    RAW.mkdir(parents=True, exist_ok=True)
    saved.write_text(json.dumps({"runs": runs}, ensure_ascii=False, indent=1), encoding="utf-8")
    report(runs, cases)


if __name__ == "__main__":
    main()
