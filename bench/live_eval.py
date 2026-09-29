"""The README's eval, live: searching the docs vs the graph hook, timed per event.

    python bench/live_eval.py                          # haiku and sonnet, once each
    python bench/live_eval.py --models haiku --reps 3 --hint

Spends model usage on your subscription (about $0.03 a run) and needs
`claude` on the PATH and a built graph (python src/build_graph.py).
Writes bench/live-report.md, and the raw event streams to bench/live-raw/.

The search condition gets the 12 unmodelled docs (corpus-before/), as in the
README's eval. The graph condition gets the docs the graph was built from
(corpus/), as in real use, where the facts' sources are in the folder you work
in; --graph-docs corpus-before gives it the unmodelled docs instead. Both get
the same tools (Grep, Read, Glob), with user and project settings and MCP
servers off. The graph condition adds only the graph's hooks.
"""
import argparse
import json
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "bench" / "live-report.md"
RAW = ROOT / "bench" / "live-raw"
QUESTION = "A customer wants an £800 refund in March. Who signs it off?"
HINT = "Our company docs are in this folder. "
ANSWER = "Marcus"


def run(claude, model, condition, prompt, work, setting_sources="local"):
    """One claude -p run; every stream event timestamped (ms) as it arrives.

    setting_sources "local" keeps your own settings out, and CLAUDE.md with them;
    "local,project" loads the CLAUDE.md in the run's folder.
    """
    argv = [claude, "-p", "--model", model, "--output-format", "stream-json", "--verbose",
            "--include-partial-messages", "--include-hook-events",
            "--tools", "Grep,Read,Glob", "--allowedTools", "Grep,Read,Glob",
            "--setting-sources", setting_sources, "--strict-mcp-config", "--no-session-persistence"]
    if condition == "graph":
        argv += ["--settings", str(work / "graph-settings.json")]
    t0 = time.perf_counter()
    p = subprocess.Popen(argv, cwd=work / condition, stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    p.stdin.write(prompt.encode("utf-8"))
    p.stdin.close()
    events = []
    for line in p.stdout:
        t = (time.perf_counter() - t0) * 1000
        try:
            events.append({"t": round(t, 1), "e": json.loads(line)})
        except ValueError:
            pass
    p.wait()
    return events


def summarise(events):
    """Turn the event stream into the few numbers the report needs."""
    hook_start = hook_end = first_text = end = None
    turns, tool_calls, tool_ms, read_chars, first_input = 0, 0, 0.0, 0, None
    started, result_text, cost = {}, "", None
    for ev in events:
        t, e = ev["t"], ev["e"]
        kind, sub = e.get("type"), e.get("subtype")
        if kind == "system" and sub == "hook_started":
            hook_start = t
        elif kind == "system" and sub == "hook_response":
            hook_end = t
        elif kind == "stream_event":
            se = e["event"]
            if se["type"] == "message_start":
                turns += 1
                if first_input is None:
                    u = se["message"].get("usage", {})
                    first_input = sum(u.get(k, 0) for k in (
                        "input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
                first_text = None  # only the final turn's first text counts
            elif se["type"] == "content_block_delta" and se["delta"].get("type") == "text_delta":
                first_text = first_text if first_text is not None else t
        elif kind == "assistant":
            for block in e["message"].get("content", []):
                if block.get("type") == "tool_use":
                    tool_calls += 1
                    started[block["id"]] = t
        elif kind == "user":
            content = e.get("message", {}).get("content", [])
            for block in content if isinstance(content, list) else []:
                if block.get("type") == "tool_result":
                    c = block.get("content", "")
                    read_chars += len(c) if isinstance(c, str) else sum(
                        len(x.get("text", "")) for x in c if isinstance(x, dict))
                    if block.get("tool_use_id") in started:
                        tool_ms += t - started[block["tool_use_id"]]
        elif kind == "result":
            end, result_text, cost = t, e.get("result", ""), e.get("total_cost_usd")
    return {"hook_ms": None if hook_start is None or hook_end is None else hook_end - hook_start,
            "recall_line": hook_end, "first_text": first_text, "end": end, "turns": turns,
            "tool_calls": tool_calls, "tool_ms": tool_ms, "read_chars": read_chars,
            "first_input_tokens": first_input, "correct": ANSWER in result_text, "cost": cost}


def s(ms):
    return "—" if ms is None else f"{ms / 1000:.2f} s"


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--models", default="haiku,sonnet")
    ap.add_argument("--reps", type=int, default=1)
    ap.add_argument("--hint", action="store_true", help=f'start the prompt with "{HINT.strip()}"')
    ap.add_argument("--graph-docs", default="corpus", choices=["corpus", "corpus-before"],
                    help="the docs in the graph condition's folder (default: the graph's sources)")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    claude = shutil.which("claude")
    if not claude:
        sys.exit("claude is not on the PATH")
    if not (ROOT / "graph.db").is_file():
        sys.exit("no graph yet: run python src/build_graph.py")
    prompt = (HINT if args.hint else "") + QUESTION

    work = Path(tempfile.mkdtemp())
    shutil.copytree(ROOT / "corpus-before", work / "search")
    shutil.copytree(ROOT / args.graph_docs, work / "graph")
    hook = f'python "{(ROOT / "src" / "recall_hook.py").as_posix()}"'
    (work / "graph-settings.json").write_text(json.dumps({"hooks": {"UserPromptSubmit": [
        {"hooks": [{"type": "command", "command": hook, "timeout": 10}]}]}}), encoding="utf-8")
    RAW.mkdir(exist_ok=True)

    rows = []
    for rep in range(1, args.reps + 1):
        for model in args.models.split(","):
            for condition in ("search", "graph"):
                events = run(claude, model, condition, prompt, work)
                name = f"{model}-{condition}-{rep}"
                (RAW / f"{name}.jsonl").write_text(
                    "\n".join(json.dumps(ev, ensure_ascii=False) for ev in events), encoding="utf-8")
                row = {"model": model, "condition": condition, "rep": rep, **summarise(events)}
                rows.append(row)
                print(f"{name}: {s(row['end'])}, {row['tool_calls']} tool calls, "
                      f"{'correct' if row['correct'] else 'WRONG'}", flush=True)
    shutil.rmtree(work, ignore_errors=True)

    lines = [
        "# Live eval: search vs graph",
        "",
        f"Run {datetime.now():%Y-%m-%d %H:%M} on {platform.system()} {platform.release()}. "
        f"Made by `python bench/live_eval.py --models {args.models} --reps {args.reps}"
        f"{' --hint' if args.hint else ''} --graph-docs {args.graph_docs}`. Prompt: “{prompt}”",
        "",
        "Runs that searched the docs: " + ", ".join(
            f"{c} {sum(r['tool_calls'] > 0 for r in rows if r['condition'] == c)} of "
            f"{sum(r['condition'] == c for r in rows)}" for c in ("search", "graph")) + ".",
        "",
        "Times are from the start of each `claude -p` run. Recall line = the graph hook's "
        "response. First answer word = the first text of the final model turn.",
        "",
        "| Model | Condition | Answer | Tool calls | Tools ran | Doc text read | Recall line "
        "| First answer word | Total | First request tokens | Cost |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for r in rows:
        cost = "—" if r["cost"] is None else f"${r['cost']:.3f}"
        lines.append(
            f"| {r['model']} | {r['condition']} | {'correct' if r['correct'] else 'wrong'} | "
            f"{r['tool_calls']} | {r['tool_ms'] / 1000:.2f} s | {r['read_chars']:,} | "
            f"{s(r['recall_line'])} | {s(r['first_text'])} | {s(r['end'])} | "
            f"{r['first_input_tokens'] or '—'} | {cost} |")
    lines += ["", "## What the injection costs", ""]
    for model in args.models.split(","):
        pairs = [(a, b) for a in rows for b in rows if a["model"] == b["model"] == model
                 and a["rep"] == b["rep"] and a["condition"] == "search" and b["condition"] == "graph"]
        for a, b in pairs:
            if a["first_input_tokens"] and b["first_input_tokens"]:
                lines.append(f"- {model}, run {a['rep']}: the graph hook added "
                             f"{b['first_input_tokens'] - a['first_input_tokens']} input tokens "
                             "to the first request.")
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
