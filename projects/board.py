"""The projects at a glance: projects/BOARD.md, or one project's card.

    python projects/board.py                      write projects/BOARD.md
    python projects/board.py helpdesk-migration   print one project: its card, gaps and checks

review.py, plan.py and status.py rewrite the board after every change.
"""
import json
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "src"))
import model  # noqa: E402
from recall import today  # noqa: E402  GRAPH_MEMORY_TODAY pins it, as for recall

BOARD = HERE / "BOARD.md"


def _progress(rec) -> str:
    steps = rec["plan"]["steps"]
    if rec["plan"]["state"] != "agreed":
        return "no agreed plan"
    done = sum(s["status"] in ("done", "skipped") for s in steps)
    return f"v{rec['plan']['version']}: {done} of {len(steps)} done"


def _now_next(rec) -> str:
    steps = rec["plan"]["steps"]
    now = [f"{s['n']} {s['status']}" for s in steps if s["status"] in ("doing", "blocked")]
    finished = {s["n"] for s in steps if s["status"] in ("done", "skipped")}
    nxt = next((s for s in steps if s["status"] == "todo" and all(a in finished for a in s["after"])), None)
    return "; ".join(filter(None, [", ".join(now), nxt and f"next {nxt['n']}: {nxt['title']}"])) or "—"


def render(records, root=ROOT, now: date = None) -> str:
    now = now or today()
    lines = ["# Projects", "", f"As of {now.isoformat()}. Written by projects/board.py from projects/records/; "
             "do not edit by hand.", ""]
    if not records:
        return "\n".join(lines + ["No projects yet. Ingest a request or a meeting: python projects/ingest.py <file>", ""])
    lines += ["| Project | Status | Owner | Plan | Now and next | Due |", "|---|---|---|---|---|---|"]
    for pid, rec in sorted(records.items(), key=lambda kv: kv[1]["title"]):
        st = rec["status"][-1] if rec["status"] else {"value": "?", "from": "?"}
        due = rec["due"] and (rec["due"].get("date") or rec["due"]["text"])
        lines.append(f"| {rec['title']} (`{pid}`) | {st['value'].replace('_', ' ')} since {st['from']} "
                     f"| {rec['owner']['entity'] if rec['owner'] else '—'} | {_progress(rec)} "
                     f"| {_now_next(rec)} | {due or '—'} |")
    checks = [(rec["title"], w) for pid, rec in sorted(records.items())
              for w in model.gaps(rec) + model.health(rec, records, root, now)]
    lines += ["", "## Needs a look", ""] + ([f"- {t}: {w}" for t, w in checks] or ["Nothing."])
    return "\n".join(lines + [""])


def card(rec, records, root=ROOT, now: date = None) -> str:
    """One project as the plan discussion starts from it."""
    import ingest

    now = now or today()
    out = [json.dumps(ingest.card(rec), indent=1, ensure_ascii=False)]
    gaps = model.gaps(rec)
    checks = model.health(rec, records, root, now)
    if gaps or checks:
        out += ["", "Needs a look:"] + [f"- {w}" for w in gaps + checks]
    return "\n".join(out)


def write(records_dir=None, root=ROOT) -> Path:
    BOARD.write_text(render(model.load_records(records_dir or HERE / "records"), root), encoding="utf-8")
    return BOARD


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    records = model.load_records(HERE / "records")
    if len(sys.argv) > 1:
        pid = sys.argv[1]
        if pid not in records:
            sys.exit(f"no project {pid}; there are: {', '.join(sorted(records)) or 'none'}")
        print(card(records[pid], records))
    else:
        print(f"wrote {write().relative_to(ROOT).as_posix()}")


if __name__ == "__main__":
    main()
