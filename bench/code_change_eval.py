"""Live: changing code that other code depends on, with the graph hook or by searching, on a pinned snapshot.

    python bench/code_change_eval.py --check                    no model: every case fails on the snapshot and
                                                                passes with its reference change
    python bench/code_change_eval.py                            sonnet, both conditions, every case, once
    python bench/code_change_eval.py --models haiku,sonnet --reps 3 --cases 01,05 --jobs 3
    python bench/code_change_eval.py --regrade                  grade the kept folders again, no calls

The cases are bench/code-change/cases.json: six changes to the sample shop (a Flask backend and a TypeScript
frontend), each to a function or constant that other code depends on, across files, packages or languages.

The snapshot. Every run starts from codegraph/cases/shop as the commit pinned in cases.json has it: extracted
from git (git archive) into a fresh folder, then checked file by file against the SHA-256s in cases.json.
The working tree's copy is never used, so editing the shop cannot change a run.

Two conditions, in folders holding the same files: the snapshot, the company documents, the CLAUDE.md rule, and
run_tests.py (the shop's tests, run without pytest). The model may Read, Grep, Glob, Edit, Write, and run
`python run_tests.py`; nothing else.

    search   no hook: the model finds what depends on what itself
    graph    the graph hook too, over a graph of the documents and the snapshot's code, built from a
             restored copy before any run

Grading. When the model is done, the case's hidden tests (bench/code-change/hidden/, never in the model's folder
while it works) run against the folder as the model left it, beside the shop's own tests as the model left
them. A run passes when every one does. The frontend is checked by reading its source, as there is no
TypeScript compiler here.

Writes bench/code-change-report.md, and to bench/code-change-raw/ (not committed) each run's event stream and
the folder it left. Spends one claude -p run per case, condition, model and rep.
"""
import argparse
import hashlib
import io
import json
import os
import shutil
import statistics
import subprocess
import sys
import tarfile
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src")]
import build_graph  # noqa: E402

HERE = ROOT / "bench" / "code-change"
DOC = json.loads((HERE / "cases.json").read_text(encoding="utf-8"))
SNAP, CASES = DOC["snapshot"], DOC["cases"]
NOW = "2026-09-28"
OUT, RAW = ROOT / "bench" / "code-change-report.md", ROOT / "bench" / "code-change-raw"
TOOLS = "Read,Grep,Glob,Edit,Write,Bash"
ALLOWED = "Read,Grep,Glob,Edit,Write,Bash(python run_tests.py)"
EXTRAS = ("CLAUDE.md", "run_tests.py")  # what a run's folder holds beside the shop and the documents
RUN_TIMEOUT = 900  # seconds for one claude -p run


# ---- the snapshot ---------------------------------------------------------------------------------------------------

def manifest(folder: Path, only=None) -> dict:
    """{relative path: sha256} of the files under folder, caches left out."""
    out = {}
    for f in sorted(Path(folder).rglob("*")):
        rel = f.relative_to(folder).as_posix()
        if f.is_file() and "__pycache__" not in f.parts and (only is None or rel.split("/")[0] in only):
            out[rel] = hashlib.sha256(f.read_bytes()).hexdigest()
    return out


def restore(dest: Path) -> Path:
    """The pinned snapshot into dest, which must not exist yet; refuses if any file differs from cases.json."""
    tar = subprocess.run(["git", "-C", str(ROOT), "archive", "--format=tar", SNAP["commit"], SNAP["path"]],
                         capture_output=True, check=True).stdout
    dest.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(tar)) as t:
        for m in t.getmembers():
            if m.isfile():
                target = dest / PurePosixPath(m.name).relative_to(SNAP["path"])
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(t.extractfile(m).read())
    got = manifest(dest)
    if got != SNAP["files"]:
        wrong = sorted(set(got.items()) ^ set(SNAP["files"].items()))
        raise SystemExit(f"the snapshot restored from {SNAP['commit'][:10]} is not the pinned one: {wrong[:4]}")
    return dest


def workspace(dest: Path) -> Path:
    """A run's folder: the snapshot, the company documents, the CLAUDE.md rule, run_tests.py."""
    restore(dest)
    for doc in (ROOT / "corpus").glob("*.md"):
        shutil.copy(doc, dest / doc.name)
    shutil.copy(ROOT / "claude-md-snippet.md", dest / "CLAUDE.md")
    shutil.copy(HERE / "runner.py", dest / "run_tests.py")
    return dest


# ---- grading ---------------------------------------------------------------------------------------------------------

def run_tests(folder: Path, files) -> list:
    out = subprocess.run([sys.executable, str(HERE / "runner.py"), "--json", *map(str, files)], cwd=folder / "backend",
                         capture_output=True, text=True, encoding="utf-8", timeout=180,
                         env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    try:
        return json.loads(out.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return [{"file": "(runner)", "test": "(run)", "ok": False, "error": (out.stderr or out.stdout)[-300:]}]


def grade(folder: Path, case: dict) -> dict:
    """The hidden tests and the shop's own tests against the folder as it is; what changed against the snapshot."""
    grading = folder / ".grading"
    shutil.rmtree(grading, ignore_errors=True)
    grading.mkdir()
    for name in ("_support.py", case["hidden"]):
        shutil.copy(HERE / "hidden" / name, grading / name)
    hidden = run_tests(folder, [grading / case["hidden"]])
    own = run_tests(folder, sorted((folder / "backend" / "tests").glob("test_*.py")))
    shutil.rmtree(grading, ignore_errors=True)
    now = manifest(folder, only=("backend", "frontend"))
    was = {k: v for k, v in SNAP["files"].items()}
    changed = sorted(k for k in now if k in was and now[k] != was[k])
    added = sorted(k for k in now if k not in was)
    removed = sorted(k for k in was if k not in now)
    return {"passed": all(r["ok"] for r in hidden + own) and bool(hidden),
            "hidden": hidden, "own": own, "changed": changed, "added": added, "removed": removed}


def check_case(case) -> tuple:
    """(graded on the snapshot, graded with the reference change): no model."""
    with tempfile.TemporaryDirectory(prefix="cc-check-") as tmp:
        folder = workspace(Path(tmp) / "shop")
        before = grade(folder, case)
        ref = HERE / "reference" / case["id"]
        for f in ref.rglob("*"):
            if f.is_file():
                shutil.copy(f, folder / f.relative_to(ref))
        return before, grade(folder, case)


def check() -> bool:
    """No model: each case must fail on the snapshot, and pass with its reference change."""
    ok = True
    for case in CASES:
        before, after = check_case(case)
        failing = [r["test"] for r in before["hidden"] if not r["ok"]]
        bad_after = [f"{r['file']}::{r['test']}: {r.get('error', '')}" for r in after["hidden"] + after["own"] if not r["ok"]]
        good = bool(failing) and not bad_after and after["passed"]
        ok &= good
        print(f"{'ok ' if good else 'BAD'} {case['id']}: snapshot fails {len(failing)} of {len(before['hidden'])} "
              f"hidden tests; reference passes {sum(r['ok'] for r in after['hidden'])} of {len(after['hidden'])}, "
              f"own tests {sum(r['ok'] for r in after['own'])} of {len(after['own'])}; reference changes "
              f"{len(after['changed']) + len(after['added'])} files")
        for line in bad_after:
            print("    " + line)
    return ok


# ---- one run ---------------------------------------------------------------------------------------------------------

def graph_setup(work: Path) -> dict:
    """A graph of the documents and a restored copy of the snapshot's code; the hook's settings; its environment."""
    pristine = restore(work / "pristine")
    db = work / "graph.db"
    build_graph.build(db_path=db, code=pristine, records=work / "no-records", now=date.fromisoformat(NOW))
    hook = f'python "{(ROOT / "src" / "recall_hook.py").as_posix()}"'
    (work / "graph-settings.json").write_text(json.dumps({"hooks": {"UserPromptSubmit": [
        {"hooks": [{"type": "command", "command": hook, "timeout": 10}]}]}}), encoding="utf-8")
    return {"GRAPH_MEMORY_DB": str(db), "GRAPH_MEMORY_TODAY": NOW, "GRAPH_MEMORY_STATE": str(work / "state"),
            "GRAPH_MEMORY_RAG_DB": str(work / "no-rag.db")}


def summarise(events, wall) -> dict:
    out = {"wall_ms": round(wall), "turns": 0, "tool_calls": 0, "tools": {}, "cost": None, "input_tokens": 0,
           "output_tokens": 0, "model_id": None, "hook_ms": None, "first_edit_ms": None, "text": ""}
    hook_start = None
    for ev in events:
        t, e = ev["t"], ev["e"]
        kind, sub = e.get("type"), e.get("subtype")
        if kind == "system" and sub == "init":
            out["model_id"] = e.get("model")
        elif kind == "system" and sub == "hook_started":
            hook_start = t
        elif kind == "system" and sub == "hook_response" and hook_start is not None:
            out["hook_ms"] = round(t - hook_start, 1)
        elif kind == "stream_event" and e["event"]["type"] == "message_start":
            out["turns"] += 1
        elif kind == "assistant":
            for b in e["message"].get("content", []):
                if b.get("type") == "tool_use":
                    out["tool_calls"] += 1
                    out["tools"][b["name"]] = out["tools"].get(b["name"], 0) + 1
                    if b["name"] in ("Edit", "Write") and out["first_edit_ms"] is None:
                        out["first_edit_ms"] = t
        elif kind == "result":
            u = e.get("usage") or {}
            out.update(text=e.get("result", ""), cost=e.get("total_cost_usd"),
                       input_tokens=sum(u.get(k, 0) for k in ("input_tokens", "cache_creation_input_tokens",
                                                                "cache_read_input_tokens")),
                       output_tokens=u.get("output_tokens", 0))
    return out


def run_one(claude, work, env_graph, condition, model_name, case, rep) -> dict:
    name = f"{case['id'][:2]}-{condition}-{model_name}-{rep}"
    folder = workspace(work / "runs" / name)
    argv = [claude, "-p", "--model", model_name, "--output-format", "stream-json", "--verbose",
            "--include-partial-messages", "--include-hook-events", "--tools", TOOLS, "--allowedTools", ALLOWED,
            "--setting-sources", "local,project", "--strict-mcp-config", "--no-session-persistence"]
    if condition == "graph":
        argv += ["--settings", str(work / "graph-settings.json")]
    env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE")}
    if condition == "graph":
        env.update(env_graph)
    prompt = f"{case['prompt']}\n\n{DOC['prompt_end']}"
    t0 = time.perf_counter()
    p = subprocess.Popen(argv, cwd=folder, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.DEVNULL)
    p.stdin.write(prompt.encode("utf-8"))
    p.stdin.close()
    events, timed_out = [], False
    deadline = t0 + RUN_TIMEOUT
    for line in p.stdout:
        t = (time.perf_counter() - t0) * 1000
        try:
            events.append({"t": round(t, 1), "e": json.loads(line)})
        except ValueError:
            pass
        if time.perf_counter() > deadline:
            p.kill()
            timed_out = True
            break
    p.wait()
    wall = (time.perf_counter() - t0) * 1000
    graded = grade(folder, case)
    keep = RAW / name
    shutil.rmtree(keep, ignore_errors=True)
    keep.mkdir(parents=True)
    (keep / "events.jsonl").write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in events), encoding="utf-8")
    shutil.copytree(folder, keep / "folder", ignore=shutil.ignore_patterns("__pycache__"))
    s = summarise(events, wall)
    return {"case": case["id"], "condition": condition, "model": model_name, "rep": rep, "run": name,
            "timed_out": timed_out, **{k: v for k, v in s.items() if k != "text"}, "reply": s["text"][-600:],
            **graded}


# ---- the report ------------------------------------------------------------------------------------------------------

def sec(ms):
    return "—" if ms is None else f"{ms / 1000:.1f} s"


def report(rows, argv) -> str:
    lines = ["# Live eval: changing code that other code depends on, search against graph", "",
             f"Run {datetime.now():%Y-%m-%d %H:%M}. Made by `python bench/code_change_eval.py {' '.join(argv)}`. "
             f"Every run starts from the shop at commit {SNAP['commit'][:10]}, restored from git and checked file "
             "by file. Both folders hold the snapshot, the company documents, the CLAUDE.md rule and "
             "run_tests.py; the graph condition adds the graph hook. A run passes when every hidden test and "
             "every one of the shop's own tests passes on the folder it leaves.", "",
             "| Model | Condition | Passed | Hidden tests passed | Median time | Median time to first edit "
             "| Median tool calls | Reads | Cost per run |",
             "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for m in dict.fromkeys(r["model"] for r in rows):
        for c in ("search", "graph"):
            mine = [r for r in rows if r["model"] == m and r["condition"] == c]
            if not mine:
                continue
            tests = sum(len(r["hidden"]) for r in mine)
            edits = [r["first_edit_ms"] for r in mine if r["first_edit_ms"] is not None]
            lines.append(
                f"| {m} | {c} | {sum(r['passed'] for r in mine)} of {len(mine)} | "
                f"{sum(t['ok'] for r in mine for t in r['hidden'])} of {tests} | "
                f"{sec(statistics.median(r['wall_ms'] for r in mine))} | "
                f"{sec(statistics.median(edits)) if edits else '—'} | "
                f"{statistics.median(r['tool_calls'] for r in mine):g} | "
                f"{statistics.median(r['tools'].get('Read', 0) for r in mine):g} | "
                f"${statistics.mean(r['cost'] or 0 for r in mine):.3f} |")
    lines += ["", "| Case | Condition | Model | Rep | Passed | Hidden tests | Own tests | Time | Tool calls | Files changed | Failing |",
              "| --- | --- | --- | ---: | --- | ---: | ---: | ---: | ---: | --- | --- |"]
    for r in sorted(rows, key=lambda r: (r["case"], r["model"], r["condition"], r["rep"])):
        fails = "; ".join(f"{t['test']}: {t.get('error', '')[:80]}" for t in r["hidden"] + r["own"] if not t["ok"])
        lines.append(f"| {r['case']} | {r['condition']} | {r['model']} | {r['rep']} | {'yes' if r['passed'] else 'NO'} | "
                     f"{sum(t['ok'] for t in r['hidden'])} of {len(r['hidden'])} | "
                     f"{sum(t['ok'] for t in r['own'])} of {len(r['own'])} | {sec(r['wall_ms'])}"
                     f"{' (timed out)' if r['timed_out'] else ''} | {r['tool_calls']} | "
                     f"{', '.join(r['changed'] + [a + ' (new)' for a in r['added']]) or '—'} | "
                     f"{fails.replace('|', '/') or '—'} |")
    return "\n".join(lines) + "\n"


def main():
    global OUT, RAW
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="validate the cases against the snapshot, no model")
    ap.add_argument("--models", default="sonnet")
    ap.add_argument("--reps", type=int, default=1)
    ap.add_argument("--conditions", default="search,graph")
    ap.add_argument("--cases", default="", help="case numbers, e.g. 01,05 (default: all)")
    ap.add_argument("--jobs", type=int, default=2)
    ap.add_argument("--regrade", action="store_true", help="grade the kept folders again, no calls")
    ap.add_argument("--tag", default="", help="write code-change-report-<tag>.md and code-change-raw-<tag>/")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    if args.check:
        sys.exit(0 if check() else 1)
    if args.tag:
        OUT, RAW = OUT.with_name(f"{OUT.stem}-{args.tag}.md"), RAW.with_name(f"{RAW.name}-{args.tag}")
    wanted = {c.strip().zfill(2) for c in args.cases.split(",") if c.strip()}
    cases = [c for c in CASES if not wanted or c["id"][:2] in wanted]
    if args.regrade:
        rows = json.loads((RAW / "rows.json").read_text(encoding="utf-8"))
        by_id = {c["id"]: c for c in CASES}
        for r in rows:
            r.update(grade(RAW / r["run"] / "folder", by_id[r["case"]]))
    else:
        claude = shutil.which("claude")
        if not claude:
            sys.exit("claude is not on the PATH")
        work = Path(tempfile.mkdtemp(prefix="cc-"))
        env_graph = graph_setup(work)
        jobs = [(c, m, case, rep) for rep in range(1, args.reps + 1) for case in cases
                for m in args.models.split(",") for c in args.conditions.split(",")]
        RAW.mkdir(parents=True, exist_ok=True)
        with ThreadPoolExecutor(max_workers=args.jobs) as pool:
            rows = list(pool.map(lambda j: run_one(claude, work, env_graph, *j), jobs))
        shutil.rmtree(work, ignore_errors=True)
        for r in rows:
            print(f"{r['case'][:2]} {r['condition']:<6} {r['model']:<7} rep {r['rep']}: "
                  f"{'PASS' if r['passed'] else 'FAIL'} {sum(t['ok'] for t in r['hidden'])}/{len(r['hidden'])} hidden, "
                  f"{sec(r['wall_ms'])}, {r['tool_calls']} tools")
    RAW.mkdir(parents=True, exist_ok=True)
    (RAW / "rows.json").write_text(json.dumps(rows, indent=1, ensure_ascii=False), encoding="utf-8")
    OUT.write_text(report(rows, sys.argv[1:]), encoding="utf-8")
    print(f"{sum(r['passed'] for r in rows)} of {len(rows)} passed -> {OUT.relative_to(ROOT).as_posix()}")


if __name__ == "__main__":
    main()
