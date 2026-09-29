"""Projects: the record, the change sets that update it, and the checks on both.

A project is a JSON record. Claude never edits one: it proposes a change set, a
list of operations each quoting the input it came from. Code checks the set
(validate) and applies it (apply). Applying is a pure function, so a case can
say exactly what should come out of it; see cases/.

    diff = {"input": "inputs/2026-09-24-support-sync.md", "kind": "transcript",
            "on": "2026-09-24",
            "changes": [{"op": "set_step", "project": "helpdesk-migration", "n": 1,
                         "status": "done",
                         "quote": "Shortlist's done, three options in the shared drive."}]}

Every change carries one quote, found word for word in the input (markdown and
spacing aside). A date counts only when the input states it or it is the input's
own date. A plan is agreed with you, not read from a meeting: only a change set
from a discussion (kind "discussion", written by plan.py) may agree one, so an
input can move a step along but never add one.
"""
import copy
import hashlib
import json
import re
import sqlite3
import sys
from contextlib import closing
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from recall import plain  # noqa: E402  the build's own quote comparison

MAX_QUOTE = 300  # as for claims: any one sentence fits
STATUSES = ("proposed", "planning", "active", "blocked", "on_hold", "done", "cancelled")
FIRST = ("proposed", "planning")  # asked for, or agreed to go ahead
MOVES = {
    "proposed": {"planning", "cancelled"},
    "planning": {"active", "on_hold", "cancelled"},  # active only with an agreed plan
    "active": {"blocked", "on_hold", "done", "cancelled"},
    "blocked": {"active", "on_hold", "cancelled"},
    "on_hold": {"planning", "active", "cancelled"},
    "done": {"active"},  # reopened
    "cancelled": {"planning"},  # revived
}
CONFIRM = {"done", "cancelled"}  # moving to or from these always needs you
STEP_STATUSES = ("todo", "doing", "done", "blocked", "skipped")
DELIVERABLE_STATUSES = ("planned", "in_progress", "delivered", "accepted", "dropped")
DEPENDENCY_KINDS = ("needs", "subject_to", "blocked_by")
FIELDS = ("title", "description", "owner", "requested_by", "due")
OPS = {  # operation: what it must carry besides "op" and "quote"
    "create_project": ("project", "title", "description"),
    "set_status": ("project", "value"),  # from: the input's date unless it names another
    "set_field": ("project", "field", "value"),
    "add_dependency": ("project", "on", "kind"),
    "add_deliverable": ("project", "key", "title"),
    "set_deliverable": ("project", "key", "status"),
    "set_step": ("project", "n"),  # and a status, a due date, or both
    "add_question": ("project", "key", "text"),
    "close_question": ("project", "key"),
    "add_decision": ("project", "text"),
    "agree_plan": ("project", "steps"),  # a discussion's only: see plan.py
    "delete_project": ("project",),  # soft: the record stays, out of the graph, until restored
    "restore_project": ("project",),
}
MAX_STEPS = 25  # more than this is two projects
STALE_DAYS = 14  # an active project with nothing new for this long is flagged
QUESTION_DAYS = 7  # an open question this old is flagged
MONTHS = ("january", "february", "march", "april", "may", "june", "july", "august",
          "september", "october", "november", "december")
SLUG = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")
RELATIVE = {"yesterday": -1, "last night": -1, "today": 0, "tonight": 0, "this morning": 0,
            "this afternoon": 0, "this evening": 0, "tomorrow": 1}  # days from the input's date
NOTE_KINDS = ("threshold", "responsibility", "note", "rule", "deadline", "availability")
NOTE_CLAIMS = 2  # claims shown beside a name, so the model knows what a policy covers


# ---- names the graph knows -----------------------------------------------------------------

def _note(claims) -> str:
    """What an entity is, in its own claims: the ones in force, most telling first."""
    ranked = sorted((c for c in claims if c[0] in NOTE_KINDS), key=lambda c: NOTE_KINDS.index(c[0]))
    return "; ".join(text for _, text in ranked[:NOTE_CLAIMS])


def entities_from_db(db_path, today=None, leave_out=("PROJECT", "DELIVERABLE")) -> list:
    """[(name, type, [aliases], note)] from a built graph.db: the entities a project can
    name. Projects and deliverables are left out; they are the records themselves."""
    today = (today or date.today()).isoformat()
    with closing(sqlite3.connect(db_path)) as db:
        rows = db.execute("SELECT id, name, type FROM entities").fetchall()
        aliases, claims = {}, {}
        for eid, text in db.execute("SELECT entity_id, text FROM names WHERE kind = 'alias'"):
            aliases.setdefault(eid, []).append(text)
        for eid, kind, text in db.execute(
                "SELECT entity_id, kind, text FROM claims WHERE valid_to IS NULL OR valid_to > ? "
                "ORDER BY id", (today,)):
            claims.setdefault(eid, []).append((kind, text))
    return sorted((name, kind, sorted(aliases.get(eid, [])), _note(claims.get(eid, [])))
                  for eid, name, kind in rows if kind not in leave_out)


def entities_from_extraction(folder) -> list:
    """The same, read straight from extraction/*.json, so no build is needed."""
    docs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(Path(folder).glob("*.json"))]
    found = {}
    for doc in docs:
        for node in doc.get("nodes", []):
            entry = found.setdefault(node["name"], (node["type"], set(), []))
            entry[2].extend((c["kind"], c["text"]) for c in node.get("claims", []) if not c.get("valid_to"))
    for doc in docs:  # an alias can name an entity another document introduced
        for a in doc.get("aliases", []):
            if a["entity"] in found:
                found[a["entity"]][1].add(a["alias"])
    return sorted((name, kind, sorted(al), _note(cl)) for name, (kind, al, cl) in found.items())


def name_map(entities) -> dict:
    """{a name or alias, as compared: the entity's full name}."""
    out = {}
    for name, _, aliases, *_ in entities:
        for n in (name, *aliases):
            out.setdefault(plain(n), name)
    return out


# ---- records -------------------------------------------------------------------------------

def status_of(record):
    return record["status"][-1]["value"] if record["status"] else None


def open_questions(record) -> list:
    return [q for q in record["questions"] if not q.get("answered")]


def gaps(record) -> list:
    """What a project still lacks. Shown at review; absence has no quote to ask with."""
    out = []
    if not record["owner"]:
        out.append("no owner")
    if not (record["due"] and record["due"].get("date")):
        out.append("no due date")
    if record["plan"]["state"] != "agreed" and status_of(record) in ("planning", "active"):
        out.append("no agreed plan")
    return out


def last_activity(record):
    """The newest date anything happened on a project."""
    dates = [s["from"] for s in record["status"]] + [d["on"] for d in record["decisions"]]
    dates += [x["on"] for x in record["plan"]["steps"] + record["deliverables"] if x.get("on")]
    dates += [s["read_on"] for s in record["sources"]]
    return max(dates) if dates else None


def health(record, records, root, today, names=None) -> list:
    """What needs looking at: stale, overdue, a source changed since it was read, an old
    open question, a dependency that is over, a name the graph no longer knows."""
    today = today if isinstance(today, date) else date.fromisoformat(today)
    now, status, out = today.isoformat(), status_of(record), []
    last = last_activity(record)
    if status == "active" and last and (today - date.fromisoformat(last)).days > STALE_DAYS:
        out.append(f"no update since {last}")
    if status not in ("done", "cancelled"):
        out += [f"step {s['n']} overdue since {s['due']}" for s in record["plan"]["steps"]
                if s["due"] and s["due"] < now and s["status"] not in ("done", "skipped")]
        out += [f"{d['key']} overdue since {d['due']}" for d in record["deliverables"]
                if d["due"] and d["due"] < now and d["status"] not in ("delivered", "accepted", "dropped")]
        due = (record["due"] or {}).get("date")
        if due and due < now:
            out.append(f"overdue since {due}")
        if status == "active" and record["plan"]["state"] != "agreed":
            out.append("active without an agreed plan")
    first, latest = {}, {}
    for s in record["sources"]:
        first.setdefault(s["doc"], s["read_on"])
        latest[s["doc"]] = s
    for doc, s in latest.items():
        path = Path(root) / doc
        if s.get("kind") == "research":
            continue  # read during planning; the plan, not the file, is the record
        if not path.is_file():
            out.append(f"{doc} is no longer there")
        elif digest(path.read_text(encoding="utf-8")) != s["sha256"]:
            out.append(f"{doc} changed since it was read on {s['read_on']}: ingest it again")
    for q in open_questions(record):
        asked = first.get(q["source"])
        if asked and (today - date.fromisoformat(asked)).days > QUESTION_DAYS:
            out.append(f"{q['key']} open since {asked}: {q['text']}")
    for d in record["dependencies"]:
        if d["on"].startswith("project:"):
            other = records.get(d["on"][8:])
            if other is None:
                out.append(f"depends on {d['on']}, which does not exist")
            elif status_of(other) in ("done", "cancelled"):
                out.append(f"depends on {other['title']}, which is {status_of(other)}: is it still waiting?")
    if names is not None:
        people = [record[f]["entity"] for f in ("owner", "requested_by") if record[f]]
        people += [x["owner"] for x in record["plan"]["steps"] + record["deliverables"] if x.get("owner")]
        people += [d["on"] for d in record["dependencies"] if not d["on"].startswith("project:")]
        out += [f"{n} is not in the graph any more" for n in dict.fromkeys(people) if plain(n) not in names]
    return out


def digest(text: str) -> str:
    """The sha256 an input is known by. Line endings are normalised, so a checkout
    that turns them into CRLF does not make an unchanged input look changed."""
    return hashlib.sha256(text.replace("\r\n", "\n").encode("utf-8")).hexdigest()


def check_record(record, root) -> list:
    """Problems with a record as stored: each quote must be in its source file under root."""
    out, texts = [], {}

    def walk(node, where):
        if isinstance(node, dict):
            if "quote" in node and "source" in node and node["quote"]:
                doc = node["source"]
                if doc not in texts:
                    path = Path(root) / doc
                    texts[doc] = plain(path.read_text(encoding="utf-8")) if path.is_file() else None
                if texts[doc] is None:
                    out.append(f"{record['id']} {where}: no file {doc}")
                elif plain(node["quote"]) not in texts[doc]:
                    out.append(f"{record['id']} {where}: quote not in {doc}: {node['quote']!r}")
            for k, v in node.items():
                walk(v, f"{where}.{k}" if where else k)
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{where}[{i}]")

    walk(record, "")
    bad = [s["value"] for s in record["status"] if s["value"] not in STATUSES]
    bad += [s["status"] for s in record["plan"]["steps"] if s["status"] not in STEP_STATUSES]
    bad += [d["status"] for d in record["deliverables"] if d["status"] not in DELIVERABLE_STATUSES]
    return out + [f"{record['id']}: unknown status {b!r}" for b in bad]


def load_records(folder) -> dict:
    return {p.stem: json.loads(p.read_text(encoding="utf-8"))
            for p in sorted(Path(folder).glob("*.json"))}


def save_records(folder, records, events) -> None:
    """Write each record, and append each event to its project's .log.jsonl history."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    for pid, rec in records.items():
        (folder / f"{pid}.json").write_text(json.dumps(rec, indent=1, ensure_ascii=False) + "\n",
                                            encoding="utf-8")
    for ev in events:
        with (folder / f"{ev['project']}.log.jsonl").open("a", encoding="utf-8") as log:
            log.write(json.dumps(ev, ensure_ascii=False) + "\n")


def as_state(records) -> dict:
    return {"projects": [records[k] for k in sorted(records)]}


def from_state(state) -> dict:
    return {p["id"]: p for p in state["projects"]}


# ---- checking a change set -----------------------------------------------------------------

def stated(iso, text: str, on: str) -> bool:
    """True when a date is the input's own date, or the input says it: in full ("2
    October", "Oct 2nd", "2026-10-02"), or as a day next to the input's ("last night")."""
    try:
        d = date.fromisoformat(str(iso))
    except ValueError:
        return False
    if iso == on:
        return True
    t = plain(text)
    offset = (d - date.fromisoformat(on)).days
    if any(days == offset and re.search(rf"\b{words}\b", t) for words, days in RELATIVE.items()):
        return True
    month = MONTHS[d.month - 1]
    months = (month, month[:3], month[:4])  # "september", "sep", "sept"
    day = str(d.day)
    days = [day] + [day + s for s in ("st", "nd", "rd", "th")]  # "4", "4th"
    forms = [str(iso)] + [f"{d_} {m}" for d_ in days for m in months] \
        + [f"{m} {d_}" for d_ in days for m in months]
    if not any(re.search(rf"(?<!\d){re.escape(f)}\b", t) for f in forms):
        return False
    year = date.fromisoformat(on).year  # "4 January", said in September, is next year
    return d.year in (year, year + 1) or str(d.year) in t


def _date(value, ctx, label) -> list:
    return [] if stated(value, ctx["text"], ctx["on"]) else [f"{label} {value} is not stated in the input"]


def _entity(name, ctx) -> list:
    if ctx["names"] is None:
        return []
    full = ctx["names"].get(plain(str(name)))
    if full is None:
        return [f"{name} is not in the graph"]
    return [] if full == name else [f"write {full}, not {name}"]


def _reaches(state, start, target) -> bool:
    """True when project start depends, however indirectly, on project target."""
    seen, todo = set(), [start]
    while todo:
        pid = todo.pop()
        if pid == target:
            return True
        if pid in seen or pid not in state:
            continue
        seen.add(pid)
        todo += [d["on"][8:] for d in state[pid]["dependencies"] if d["on"].startswith("project:")]
    return False


def _find(items, key, value):
    return next((x for x in items if x[key] == value), None)


def _check_status(rec, ch, ctx, state):
    value, now = ch["value"], status_of(rec)
    if value not in STATUSES:
        return [f"unknown status {value!r}"]
    out = []
    if now is None and value not in FIRST:
        out.append(f"a new project starts as proposed or planning, not {value}")
    elif now == value:
        out.append(f"already {value}")
    elif now is not None and value not in MOVES[now]:
        out.append(f"{now} → {value} is not allowed")
    elif now == "planning" and value == "active" and rec["plan"]["state"] != "agreed":
        out.append("planning → active needs an agreed plan")
    return out + (_date(ch["from"], ctx, "from") if ch.get("from") else [])


def _check_field(rec, ch, ctx, state):
    field, value = ch["field"], ch["value"]
    if field not in FIELDS:
        return [f"unknown field {field!r}"]
    out = []
    if field in ("owner", "requested_by"):
        out += _entity(value, ctx)
    if field == "due" and ch.get("date") and ch["date"] != (rec["due"] or {}).get("date"):
        out += _date(ch["date"], ctx, "due date")  # a date already recorded is not a new claim
    if field == "title" and value == rec["title"]:
        out.append("title unchanged")
    return out


def _check_dependency(rec, ch, ctx, state):
    kind, on = ch["kind"], str(ch["on"])
    out = [] if kind in DEPENDENCY_KINDS else [f"unknown dependency kind {kind!r}"]
    if on.startswith("project:"):
        other = on[8:]
        if other == rec["id"]:
            out.append("a project cannot depend on itself")
        elif other not in state:
            out.append(f"no project {other}")
        elif _reaches(state, other, rec["id"]):
            out.append(f"a cycle: {other} already depends on {rec['id']}")
    else:
        out += _entity(on, ctx)
    if any(d["on"] == on and d["kind"] == kind for d in rec["dependencies"]):
        out.append("already listed")
    return out


def _check_add_deliverable(rec, ch, ctx, state):
    out = []
    if not re.fullmatch(r"D\d+", str(ch["key"])):
        out.append(f"deliverable keys are D1, D2 ...: not {ch['key']!r}")
    elif _find(rec["deliverables"], "key", ch["key"]):
        out.append(f"{ch['key']} already exists")
    if ch.get("owner"):
        out += _entity(ch["owner"], ctx)
    if ch.get("due"):
        out += _date(ch["due"], ctx, "due")
    return out


def _check_set_deliverable(rec, ch, ctx, state):
    d = _find(rec["deliverables"], "key", ch["key"])
    if d is None:
        return [f"no deliverable {ch['key']}"]
    if ch["status"] not in DELIVERABLE_STATUSES:
        return [f"unknown deliverable status {ch['status']!r}"]
    out = [f"{ch['key']} is already {ch['status']}"] if d["status"] == ch["status"] else []
    return out + (_date(ch["on"], ctx, "on") if ch.get("on") else [])


def _check_step(rec, ch, ctx, state):
    if rec["plan"]["state"] != "agreed":
        return ["no agreed plan to update"]
    step = _find(rec["plan"]["steps"], "n", ch["n"])
    if step is None:
        return [f"no step {ch['n']}"]
    if not ch.get("status") and not ch.get("due"):
        return ["a step change needs a status, a due date or both"]
    if ch.get("status") and ch["status"] not in STEP_STATUSES:
        return [f"unknown step status {ch['status']!r}"]
    out = []
    if step["status"] == ch.get("status") and not ch.get("due"):
        out.append(f"step {ch['n']} is already {ch['status']}")
    if ch.get("due") and ch["due"] != step["due"]:  # restating the recorded due is fine
        out += _date(ch["due"], ctx, "due")
    return out + (_date(ch["on"], ctx, "on") if ch.get("on") else [])


def _check_add_question(rec, ch, ctx, state):
    if not re.fullmatch(r"Q\d+", str(ch["key"])):
        return [f"question keys are Q1, Q2 ...: not {ch['key']!r}"]
    return [f"{ch['key']} already exists"] if _find(rec["questions"], "key", ch["key"]) else []


def _check_close_question(rec, ch, ctx, state):
    q = _find(rec["questions"], "key", ch["key"])
    if q is None:
        return [f"no question {ch['key']}"]
    return [f"{ch['key']} is already answered"] if q.get("answered") else []


def _check_decision(rec, ch, ctx, state):
    return _date(ch["on"], ctx, "on") if ch.get("on") else []


def _check_plan(rec, ch, ctx, state):
    if ctx["kind"] != "discussion":
        return ["a plan is agreed in a discussion with you, not read from an input"]
    steps = ch["steps"]
    if not isinstance(steps, list):
        return ["steps must be a list"]
    if len(steps) > MAX_STEPS:
        return [f"{len(steps)} steps: more than {MAX_STEPS} is two projects"]
    keys = {d["key"] for d in rec["deliverables"]}
    out = []
    for i, step in enumerate(steps, 1):
        where = f"step {i}"
        if step.get("n") != i:
            out.append(f"{where}: steps are numbered 1, 2, 3 ... in order")
        if not step.get("title"):
            out.append(f"{where}: no title")
        if step.get("owner"):
            out += [f"{where}: {p}" for p in _entity(step["owner"], ctx)]
        if step.get("due"):
            out += [f"{where}: {p}" for p in _date(step["due"], ctx, "due")]
        for a in step.get("after") or []:
            if not isinstance(a, int) or not 1 <= a < i:
                out.append(f"{where}: can wait only on an earlier step, not {a!r}")
        if step.get("delivers") and step["delivers"] not in keys:
            out.append(f"{where}: no deliverable {step['delivers']}")
        if step.get("status", "todo") not in STEP_STATUSES:
            out.append(f"{where}: unknown step status {step['status']!r}")
        if not step.get("quote") or plain(step["quote"]) not in ctx["plain"]:
            out.append(f"{where}: its line is not in the discussion")
    return out


def _check_delete(rec, ch, ctx, state):
    return ["already deleted"] if rec.get("deleted") else []


def _check_restore(rec, ch, ctx, state):
    return [] if rec.get("deleted") else ["not deleted"]


CHECKS = {"agree_plan": _check_plan, "set_status": _check_status, "set_field": _check_field,
          "add_dependency": _check_dependency, "add_deliverable": _check_add_deliverable,
          "set_deliverable": _check_set_deliverable, "set_step": _check_step,
          "add_question": _check_add_question, "close_question": _check_close_question,
          "add_decision": _check_decision, "delete_project": _check_delete, "restore_project": _check_restore}


def _problems(state, ch, ctx) -> list:
    op = ch.get("op")
    if op not in OPS:
        return [f"unknown operation {op!r}"]
    missing = [f for f in (*OPS[op], "quote") if ch.get(f) in (None, "", [])]
    if missing:
        return [f"missing {', '.join(missing)}"]
    out = []
    if len(ch["quote"]) > MAX_QUOTE:
        out.append(f"quote over {MAX_QUOTE} characters")
    elif plain(ch["quote"]) not in ctx["plain"]:
        out.append(f"quote not in the input: {ch['quote']!r}")
    if op == "create_project":
        if not SLUG.fullmatch(str(ch["project"])):
            out.append(f"ids are lowercase words joined by hyphens: not {ch['project']!r}")
        elif ch["project"] in state:
            out.append(f"project {ch['project']} already exists")
        return out
    rec = state.get(ch["project"])
    if rec is None:
        return out + [f"no project {ch['project']}"]
    return out + CHECKS[op](rec, ch, ctx, state)


def _needs_you(state, ch) -> bool:
    rec = state.get(ch.get("project"))
    if ch["op"] == "agree_plan":
        return rec["plan"]["state"] == "agreed"  # replacing an agreed plan
    if ch["op"] == "set_status":
        return ch["value"] in CONFIRM or status_of(rec) in CONFIRM
    if ch["op"] == "set_field" and ch["field"] in ("owner", "due"):
        return rec[ch["field"]] is not None  # changing one already set, not filling a gap
    return False


def _context(diff, text, names) -> dict:
    return {"doc": diff["input"], "kind": diff.get("kind", "transcript"), "on": diff["on"],
            "by": diff.get("by", "ingest"), "text": text, "plain": plain(text), "names": names}


def validate(records, diff, text, names) -> tuple:
    """What is wrong with a change set, and which changes need your confirmation.

    Returns (problems, confirm), each a list of sentences naming the change by
    number. A set with problems is never applied. Changes are checked in order
    against the records as the earlier ones leave them, so a set can create a
    project and then add to it. names: name_map() of the graph.
    """
    missing = [k for k in ("input", "on", "changes") if k not in diff]
    if missing:
        return [f"the change set has no {', '.join(missing)}"], []
    if not stated(diff["on"], "", diff["on"]):
        return [f"the change set's date {diff['on']!r} is not YYYY-MM-DD"], []
    ctx, state = _context(diff, text, names), copy.deepcopy(records)
    problems, confirm = [], []
    for i, ch in enumerate(diff["changes"], 1):
        found = _problems(state, ch, ctx)
        if found:
            problems += [f"change {i} ({ch.get('op', '?')}): {p}" for p in found]
            continue  # the rest are checked without it
        if _needs_you(state, ch):
            confirm.append(f"change {i}: {describe(ch)}")
        _apply_one(state, ch, ctx)
    return problems, confirm


# ---- applying a change set -----------------------------------------------------------------

def _label(ch, ev) -> str:
    """What an input was used for, as its sources entry records it."""
    op = ch["op"]
    if op == "agree_plan":
        return "plan " + ev["new"].split(",")[0]
    return {"create_project": "created", "set_status": f"status {ch.get('value')}",
            "set_field": ch.get("field"), "add_dependency": "dependencies",
            "add_deliverable": "deliverables", "set_deliverable": f"{ch.get('key')} {ch.get('status')}",
            "set_step": f"step {ch.get('n')} {ch.get('status') or 'due'}", "add_question": "questions",
            "close_question": f"{ch.get('key')} answered", "add_decision": "decisions",
            "delete_project": "deleted", "restore_project": "restored"}[op]


def _apply_one(state, ch, ctx) -> dict:
    """Apply one checked change to state in place; return its history line."""
    op, src = ch["op"], {"source": ctx["doc"], "quote": ch["quote"]}
    pid = ch["project"]
    ev = {}
    if op == "create_project":
        state[pid] = {"id": pid, "title": ch["title"], "aliases": list(ch.get("aliases") or []),
                      "description": {"text": ch["description"], **src},
                      "requested_by": None, "owner": None, "status": [], "due": None,
                      "dependencies": [], "deliverables": [],
                      "plan": {"state": "none", "version": 0, "steps": []},
                      "questions": [], "decisions": [], "sources": []}
        ev = {"new": ch["title"]}
    else:
        rec = state[pid]
        if op == "set_status":
            ev = {"old": status_of(rec), "new": ch["value"]}
            rec["status"].append({"value": ch["value"], "from": ch.get("from") or ctx["on"], **src})
        elif op == "set_field":
            field, value = ch["field"], ch["value"]
            if field == "title":
                ev = {"field": field, "old": rec["title"], "new": value}
                if rec["title"] not in rec["aliases"]:
                    rec["aliases"].append(rec["title"])  # old titles still find it
                rec["title"] = value
            elif field == "description":
                ev = {"field": field, "old": rec["description"]["text"], "new": value}
                rec["description"] = {"text": value, **src}
            elif field == "due":
                old = rec["due"]
                ev = {"field": field, "old": old and (old.get("date") or old["text"]),
                      "new": ch.get("date") or value}
                rec["due"] = {"text": value, "date": ch.get("date"), **src}
            else:
                ev = {"field": field, "old": rec[field] and rec[field]["entity"], "new": value}
                rec[field] = {"entity": value, **src}
        elif op == "add_dependency":
            rec["dependencies"].append({"on": ch["on"], "kind": ch["kind"], **src})
            ev = {"new": f"{ch['kind']} {ch['on']}"}
        elif op == "add_deliverable":
            rec["deliverables"].append({"key": ch["key"], "title": ch["title"],
                                        "owner": ch.get("owner"), "due": ch.get("due"),
                                        "status": "planned", "on": None, **src, "update": None})
            ev = {"key": ch["key"], "new": ch["title"]}
        elif op == "set_deliverable":
            d = _find(rec["deliverables"], "key", ch["key"])
            ev = {"key": ch["key"], "old": d["status"], "new": ch["status"]}
            d.update(status=ch["status"], on=ch.get("on") or ctx["on"], update=src)
        elif op == "set_step":
            s = _find(rec["plan"]["steps"], "n", ch["n"])
            ev = {"step": ch["n"]}
            if ch.get("status"):
                ev.update(old=s["status"], new=ch["status"])
                s.update(status=ch["status"], on=ch.get("on") or ctx["on"])
            if ch.get("due"):
                ev["due"] = s["due"] = ch["due"]
            s["update"] = src
        elif op == "add_question":
            rec["questions"].append({"key": ch["key"], "text": ch["text"], **src, "answered": None})
            ev = {"key": ch["key"], "new": ch["text"]}
        elif op == "close_question":
            q = _find(rec["questions"], "key", ch["key"])
            q["answered"] = {"on": ctx["on"], **src}
            ev = {"key": ch["key"], "old": q["text"]}
        elif op == "add_decision":
            rec["decisions"].append({"text": ch["text"], "on": ch.get("on") or ctx["on"], **src})
            ev = {"new": ch["text"]}
        elif op == "delete_project":
            rec["deleted"] = {"on": ctx["on"], **src}
            ev = {"new": "deleted"}
        elif op == "restore_project":
            rec["deleted"] = None
            ev = {"old": "deleted", "new": "restored"}
        elif op == "agree_plan":
            old = rec["plan"]
            version = old["version"] + 1
            rec["plan"] = {"state": "agreed", "version": version, "agreed_on": ctx["on"],
                           "source": ctx["doc"],
                           "steps": [{"n": st["n"], "title": st["title"], "owner": st.get("owner"),
                                      "due": st.get("due"), "after": list(st.get("after") or []),
                                      "delivers": st.get("delivers"), "status": st.get("status", "todo"),
                                      "on": None, "source": ctx["doc"], "quote": st["quote"],
                                      "update": None} for st in ch["steps"]]}
            ev = {"old": f"v{old['version']}, {len(old['steps'])} steps" if old["state"] == "agreed" else None,
                  "new": f"v{version}, {len(ch['steps'])} steps"}
    return {"on": ctx["on"], "project": pid, "op": op, **ev, "by": ctx["by"], **src}


def apply(records, diff, text) -> tuple:
    """The records after a change set, and the history lines it adds.

    Pure: the records passed in are left as they were. Check the set with
    validate() first; this trusts it. Each project the set touches gets the
    input in its sources, with its sha256 and what it was used for.
    """
    state, ctx = copy.deepcopy(records), _context(diff, text, None)
    events, used = [], {}
    for ch in diff["changes"]:
        ev = _apply_one(state, ch, ctx)
        events.append(ev)
        labels = used.setdefault(ev["project"], [])
        if _label(ch, ev) not in labels:
            labels.append(_label(ch, ev))
    sha = digest(text)
    for pid, labels in used.items():
        entry = next((s for s in state[pid]["sources"]
                      if s["doc"] == ctx["doc"] and s["sha256"] == sha), None)
        if entry is None:
            state[pid]["sources"].append({"doc": ctx["doc"], "kind": ctx["kind"], "read_on": ctx["on"],
                                          "sha256": sha, "used_for": labels})
        else:
            entry["used_for"] += [lb for lb in labels if lb not in entry["used_for"]]
    return state, events


# ---- showing a change set ------------------------------------------------------------------

def describe(ch) -> str:
    """One line per change, for the review."""
    op, p = ch.get("op"), ch.get("project", "")
    if op == "create_project":
        return f"+ project      {ch.get('title')} ({p})"
    if op == "set_status":
        return f"~ status       {p}: {ch.get('value')}" + (f", from {ch['from']}" if ch.get("from") else "")
    if op == "set_field":
        when = f" ({ch['date']})" if ch.get("date") else ""
        return f"~ {ch.get('field', ''):<12} {p}: {ch.get('value')}{when}"
    if op == "add_dependency":
        return f"+ {str(ch.get('kind', '')).replace('_', ' '):<12} {p} → {ch.get('on')}"
    if op == "add_deliverable":
        extra = "".join(f", {x}" for x in (ch.get("owner"), ch.get("due") and f"due {ch['due']}") if x)
        return f"+ deliverable  {p} {ch.get('key')} {ch.get('title')}{extra}"
    if op == "set_deliverable":
        return f"~ deliverable  {p} {ch.get('key')}: {ch.get('status')}"
    if op == "set_step":
        what = ", ".join(x for x in (ch.get("status"), ch.get("due") and f"due {ch['due']}") if x)
        return f"~ step {ch.get('n')!s:<7} {p}: {what}"
    if op == "add_question":
        return f"? question     {p} {ch.get('key')}: {ch.get('text')}"
    if op == "close_question":
        return f"✓ answered     {p} {ch.get('key')}"
    if op == "add_decision":
        return f"+ decision     {p}: {ch.get('text')}"
    if op == "agree_plan":
        return f"+ plan         {p}: {len(ch.get('steps') or [])} steps agreed"
    if op == "delete_project":
        return f"- project      {p}: deleted (can be restored)"
    if op == "restore_project":
        return f"+ project      {p}: restored"
    return f"! {op}"


def review(diff, problems=(), confirm=(), gaps_by_project=None) -> str:
    """The change set as you would read it before applying it."""
    lines = [f"{diff['input']}  →  {len(diff['changes'])} change"
             f"{'' if len(diff['changes']) == 1 else 's'}", ""]
    lines += [describe(ch) for ch in diff["changes"]] or ["(nothing to change)"]
    for pid, found in (gaps_by_project or {}).items():
        lines += [f"  gap          {pid}: {g}" for g in found]
    if problems:
        lines += ["", "Problems, so nothing will be applied:"] + [f"  {p}" for p in problems]
    if confirm:
        lines += ["", "Needs your confirmation:"] + [f"  {c}" for c in confirm]
    return "\n".join(lines)
