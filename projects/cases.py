"""The worked cases: an input, the projects before it, the change set it should
produce, and the projects after.

    cases/<nn-name>/case.json    what it tests: the input, its kind and date, and
                                 what must be true afterwards ("expect")
    cases/<nn-name>/before.json  the projects before, {"projects": [...]}
    cases/<nn-name>/diff.json    the change set a careful reader would propose
    cases/<nn-name>/after.json   the projects after it, and the history it adds
    cases/inputs/                every input the records quote, so quotes check

tests/test_project_cases.py replays each case without a model: the expected
set must pass validate and apply to exactly after.json. eval_ingest.py asks the
model instead and scores its set with check(), which reads only what "expect"
names, so different wording, ids or keys are not failures.
"""
import json
from pathlib import Path

import model

CASES = Path(__file__).resolve().parent / "cases"


def load(folder) -> dict:
    folder = Path(folder)
    read = lambda name: json.loads((folder / name).read_text(encoding="utf-8"))  # noqa: E731
    case = read("case.json")
    case.update(name=folder.name, before=model.from_state(read("before.json")),
                diff=read("diff.json"), after=read("after.json"),
                text=(CASES / case["input"]).read_text(encoding="utf-8"))
    return case


def all_cases() -> list:
    return [load(p) for p in sorted(CASES.iterdir()) if (p / "case.json").is_file()]


def story() -> tuple:
    """The cases in the order they happened, with the plan discussion between 01 and 02:
    the records as they stand on 26 September 2026, and their whole history. The
    project questions and the recall tests start from here."""
    import plan

    by = {c["name"][:2]: c for c in all_cases()}
    records, events = {}, []
    for step in ("01", "plan", "02", "04", "05"):  # 03 changes nothing
        if step == "plan":
            data = json.loads((CASES / "inputs/discussions/2026-09-15-helpdesk-migration.json")
                              .read_text(encoding="utf-8"))
            done = plan.record_plan(records, "helpdesk-migration", data,
                                    model.entities_from_extraction(model.ROOT / "extraction"), CASES)
            assert not done["problems"], done["problems"]
            records, added = done["records"], done["events"]
        else:
            records, added = model.apply(records, by[step]["diff"], by[step]["text"])
        events += added
    return records, events


def _person(rec, field):
    return rec[field] and rec[field]["entity"]


def _compare(rec, want) -> list:
    """What differs between a project and the facts a case expects of it."""
    got = {
        "status": lambda: model.status_of(rec),
        "requested_by": lambda: _person(rec, "requested_by"),
        "owner": lambda: _person(rec, "owner"),
        "due_date": lambda: rec["due"] and rec["due"]["date"],
        "deliverables": lambda: len(rec["deliverables"]),
        "open_questions": lambda: len(model.open_questions(rec)),
        "decisions": lambda: len(rec["decisions"]),
    }
    fails = []
    for key, value in want.items():
        if key in got:
            if got[key]() != value:
                fails.append(f"{key} is {got[key]()!r}, expected {value!r}")
        elif key == "deps":  # each entry: one dependency, or a list of acceptable ones
            have = {f"{d['kind']} {d['on']}" for d in rec["dependencies"]}
            for need in value:
                options = need if isinstance(need, list) else [need]
                if not have & set(options):
                    fails.append(f"no dependency {' or '.join(options)} (has {sorted(have)})")
        elif key in ("deliverables_min", "questions_min", "decisions_min"):
            n = len(rec[key[:-4]])
            if n < value:
                fails.append(f"{n} {key[:-4]}, expected at least {value}")
        elif key == "deliverable_status":
            for k, status in value.items():
                d = next((d for d in rec["deliverables"] if d["key"] == k), None)
                if (d and d["status"]) != status:
                    fails.append(f"{k} is {d and d['status']!r}, expected {status!r}")
        elif key in ("steps", "step_due"):
            field = "status" if key == "steps" else "due"
            for n, v in value.items():
                s = next((s for s in rec["plan"]["steps"] if str(s["n"]) == str(n)), None)
                if (s and s[field]) != v:
                    fails.append(f"step {n} {field} is {s and s[field]!r}, expected {v!r}")
        else:
            fails.append(f"unknown expectation {key!r}")
    return fails


def check(expect, before, diff, after) -> list:
    """Failures of a change set, as applied, against what a case expects.

    expect: "changes" (exactly this many), "created" (projects), "projects"
    ({an id, or "new#1" for the first project created: {fact: value}}) and
    "untouched" (ids that must come out unchanged).
    """
    fails, changes = [], diff["changes"]
    created = [ch["project"] for ch in changes if ch.get("op") == "create_project"]
    if "changes" in expect and len(changes) != expect["changes"]:
        fails.append(f"{len(changes)} changes, expected {expect['changes']}")
    if "created" in expect and len(created) != expect["created"]:
        fails.append(f"{len(created)} projects created, expected {expect['created']}")
    for key, want in expect.get("projects", {}).items():
        if key.startswith("new#"):
            n = int(key[4:])
            if n > len(created):
                fails.append(f"{key}: not created")
                continue
            pid = created[n - 1]
        else:
            pid = key
        if pid not in after:
            fails.append(f"{key}: no such project afterwards")
            continue
        fails += [f"{key}: {f}" for f in _compare(after[pid], want)]
    for pid in expect.get("untouched", []):
        if before.get(pid) != after.get(pid):
            fails.append(f"{pid}: changed, expected untouched")
    return fails
