"""Record a plan agreed with you: the discussion saved as an input, then one change set.

    python projects/plan.py helpdesk-migration discussion.json
    python projects/plan.py helpdesk-migration discussion.json --no-build

The /project-plan command writes discussion.json once you have agreed a plan:

    {"asked": ["Who owns it end to end?", ...],
     "answered": "your answers, in your own words",
     "found": [{"doc": "corpus/tooling-inventory.md", "quote": "..."}],   research, optional
     "steps": [{"title": "...", "owner": "Marcus Webb", "due": "2026-09-23",
                "after": [1], "delivers": "D1"}, ...],
     "approved": "your approval, in your own words",
     "changes": [{"op": "set_field", "field": "owner", "value": "Priya Patel",
                  "quote": "Priya owns it end to end."}, ...],                 optional
     "on": "2026-09-15"}                                                       optional

It renders that into inputs/discussions/<date>-<id>.md, so every quote can be
checked, and applies one change set: the plan, the changes your answers make,
and the move to active. What research found is checked against its file and
kept among the project's sources. Nothing is written if a check fails.
"""
import argparse
import json
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import model  # noqa: E402
import review  # noqa: E402

MONTH_NAMES = [m.capitalize() for m in model.MONTHS]


def long_date(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d.day} {MONTH_NAMES[d.month - 1]} {d.year}"


def step_line(n: int, step: dict) -> str:
    """How a step reads in the discussion, and so the quote it is checked by."""
    after = step.get("after") or []
    parts = [step.get("owner"), step.get("due") and f"due {step['due']}",
             after and f"after step{'s' if len(after) > 1 else ''} {', '.join(map(str, after))}",
             step.get("delivers") and f"delivers {step['delivers']}"]
    extra = ", ".join(p for p in parts if p)
    return f"{n}. {step['title']}" + (f" ({extra})" if extra else "")


def render(title: str, on: str, data: dict) -> str:
    """The discussion as the file that records it."""
    lines = [f"# Plan discussion: {title}, {long_date(on)}", ""]
    if data.get("asked"):
        lines += ["Claude asked:"] + [f"{i}. {q}" for i, q in enumerate(data["asked"], 1)] + [""]
    if data.get("answered"):
        lines += ["You answered:", data["answered"], ""]
    if data.get("found"):
        lines += ["Claude found:"] + [f'- {f["doc"]}: "{f["quote"]}"' for f in data["found"]] + [""]
    steps = data.get("steps") or []
    lines += [f"Claude proposed a plan of {len(steps)} step{'' if len(steps) == 1 else 's'}:"]
    lines += [step_line(i, s) for i, s in enumerate(steps, 1)] + ["", "You answered:", data["approved"], ""]
    return "\n".join(lines)


def change_set(records, pid, data, doc, on, text) -> dict:
    """The plan, the changes the answers make, and the moves up to active."""
    steps = [{**s, "n": i, "quote": step_line(i, s)} for i, s in enumerate(data.get("steps") or [], 1)]
    changes = [{"op": "agree_plan", "project": pid, "steps": steps, "quote": data["approved"]}]
    changes += [{**c, "project": pid} for c in data.get("changes") or []]
    now = model.status_of(records[pid])
    for status in {"proposed": ["planning", "active"], "planning": ["active"],
                   "on_hold": ["active"]}.get(now, []):
        changes.append({"op": "set_status", "project": pid, "value": status, "quote": data["approved"]})
    return {"input": doc, "kind": "discussion", "by": "you", "on": on, "changes": changes}


def record_plan(records, pid, data, entities, root, on=None) -> dict:
    """Everything plan.py would write, without writing it.

    Returns {"diff", "text", "doc", "problems", "confirm", "records", "events"};
    records and events are None when there are problems.
    """
    if pid not in records:
        return {"problems": [f"no project {pid}"], "records": None, "events": None}
    on = on or data.get("on") or date.today().isoformat()
    doc = f"inputs/discussions/{on}-{pid}.md"
    text = render(records[pid]["title"], on, data)
    diff = change_set(records, pid, data, doc, on, text)
    problems, confirm = model.validate(records, diff, text, model.name_map(entities))
    for f in data.get("found") or []:
        path = Path(root) / f["doc"]
        if not path.is_file():
            problems.append(f"research: no file {f['doc']}")
        elif model.plain(f["quote"]) not in model.plain(path.read_text(encoding="utf-8")):
            problems.append(f"research: {f['doc']} does not contain {f['quote']!r}")
    out = {"diff": diff, "text": text, "doc": doc, "problems": problems, "confirm": confirm,
           "records": None, "events": None}
    if problems:
        return out
    after, events = model.apply(records, diff, text)
    for f in data.get("found") or []:  # what research read, kept like any other source
        body = (Path(root) / f["doc"]).read_text(encoding="utf-8")
        entry = {"doc": f["doc"], "kind": "research", "read_on": on, "sha256": model.digest(body),
                 "used_for": ["plan research"]}
        if not any(s["doc"] == entry["doc"] and s["sha256"] == entry["sha256"] for s in after[pid]["sources"]):
            after[pid]["sources"].append(entry)
    out.update(records=after, events=events)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("project", help="the project's id")
    ap.add_argument("discussion", help="the discussion as JSON (see above)")
    ap.add_argument("--records", default=str(review.RECORDS))
    ap.add_argument("--db", default=str(ROOT / "graph.db"))
    ap.add_argument("--no-build", action="store_true", help="do not rebuild graph.db afterwards")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    data = json.loads(Path(args.discussion).read_text(encoding="utf-8"))
    records = model.load_records(args.records)
    result = record_plan(records, args.project, data, model.entities_from_db(args.db), ROOT)
    if result["problems"]:
        sys.exit("not recorded:\n" + "\n".join(f"  {p}" for p in result["problems"]))
    path = ROOT / result["doc"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(result["text"], encoding="utf-8")
    model.save_records(args.records, result["records"], result["events"])
    print(model.review(result["diff"]))
    print(f"\nrecorded: {result['doc']}, {len(result['events'])} changes to {args.project}")
    review.after_change(args.records, build=not args.no_build)


if __name__ == "__main__":
    main()
