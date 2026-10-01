"""Propose the project changes one input makes: a request, a transcript, a session.

    python projects/ingest.py path/to/2026-09-24-support-sync.md
    python projects/ingest.py path/to/2026-09-24-support-sync.md --apply
    python projects/ingest.py path/to/request.md --kind request

The input is saved under inputs/ first (unless it is already inside this
folder), so its quotes can always be checked. One claude -p call reads it, with
the projects it may be about and the names the graph knows, and answers with a
change set. Code checks it (model.validate), keeps it in projects/pending/ and
prints the review; review.py applies or rejects it later. --apply applies it at
once, and not even then while it has problems or needs your confirmation (--yes).
An input already dealt with, unchanged, is skipped unless --force.
The date is the one the file name starts with, or today.

Spends one claude -p call (the model in digest/config.json, sonnet by default).
"""
import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import model  # noqa: E402
import review  # noqa: E402

PROMPT = HERE / "ingest-prompt.md"
THESIS_PROMPT = HERE / "thesis-prompt.md"  # joined to PROMPT when one call writes the change set and the thesis
RECORDS = review.RECORDS
PENDING = review.PENDING
INPUTS = ROOT / "inputs"  # where inputs from outside this folder are kept
FOLDERS = {"transcript": "", "request": "requests", "session": "sessions", "note": "notes"}
CANDIDATES = 5  # existing projects offered to match an input against
REPAIR = ("\n\n---\n\nYour answer was:\n\n{answer}\n\nThe checks refused it:\n{problems}\n\n"
          "Answer again with the whole change set, corrected: fix what is named and keep the rest. "
          "JSON only.")
PRELOADED = ("Preloaded: this message holds everything the answer needs: {what}. Nothing else exists to search or "
             "check, so there is no need to weigh what might be missing: read the input and write the answer "
             "straight away.")


def preload_note(what: str) -> str:
    """The line that tells a call it has all there is, put before its payload: given only when nothing was cut."""
    return PRELOADED.format(what=what) + "\n\n"


def input_date(path, today=None) -> str:
    m = re.match(r"(\d{4}-\d{2}-\d{2})", Path(path).name)
    return m.group(1) if m else (today or date.today()).isoformat()


def card(rec) -> dict:
    """A project as the model sees it: its state, and the next free keys."""
    person = lambda f: rec[f] and rec[f]["entity"]  # noqa: E731
    return {"id": rec["id"], "title": rec["title"], "aliases": rec["aliases"],
            "status": model.status_of(rec), "description": rec["description"]["text"],
            "requested_by": person("requested_by"), "owner": person("owner"),
            "due": rec["due"] and {"text": rec["due"]["text"], "date": rec["due"]["date"]},
            "dependencies": [f"{d['kind']} {d['on']}" for d in rec["dependencies"]],
            "deliverables": [{k: d[k] for k in ("key", "title", "status", "owner", "due")}
                             for d in rec["deliverables"]],
            "plan": {"state": rec["plan"]["state"],
                     "steps": [{k: s[k] for k in ("n", "title", "status", "owner", "due", "delivers")}
                               for s in rec["plan"]["steps"]]},
            "open_questions": [{"key": q["key"], "text": q["text"]} for q in model.open_questions(rec)],
            "decisions": [d["text"] for d in rec["decisions"]],
            "next_deliverable_key": f"D{len(rec['deliverables']) + 1}",
            "next_question_key": f"Q{len(rec['questions']) + 1}"}


def candidates(records, text) -> list:
    """The projects an input most likely concerns, by the words they share."""
    words = set(re.findall(r"[a-z]{4,}", text.lower()))

    def score(rec):
        own = " ".join([rec["title"], *rec["aliases"], rec["description"]["text"]]).lower()
        return len(words & set(re.findall(r"[a-z]{4,}", own)))

    return sorted(records.values(), key=lambda r: (-score(r), r["id"]))[:CANDIDATES]


def payload(doc, kind, on, text, records, entities) -> str:
    names = "\n".join(f"- {n} ({t})" + (f", also: {', '.join(a)}" if a else "") + (f": {note}" if note else "")
                      for n, t, a, note in entities)
    cards = json.dumps([card(r) for r in candidates(records, text)], indent=1, ensure_ascii=False)
    return (f"Input: {doc}\nKind: {kind}\nDate: {on}\n\n"
            f"Names the graph knows:\n{names}\n\n"
            f"Projects this input may be about:\n{cards if records else '(none yet)'}\n\n"
            f"The input:\n\n{text}")


def parse(reply: str) -> list:
    """The changes in a reply, fenced or not. Raises ValueError when there are none."""
    return parse_all(reply)[0]


def parse_all(reply: str) -> tuple:
    """(changes, thesis or None) in a reply. A project given once beside the changes ({"project": id,
    "changes": [...]}) belongs to each change that names none."""
    start, end = reply.find("{"), reply.rfind("}")
    if start < 0 or end < start:
        raise ValueError("no JSON object in the reply")
    found = json.loads(reply[start:end + 1])
    if not isinstance(found, dict) or not isinstance(found.get("changes"), list):
        raise ValueError('the reply has no "changes" list')
    top = found.get("project")
    changes = [{"project": top, **ch} if isinstance(ch, dict) and top and "project" not in ch and "id" not in ch
               else ch for ch in found["changes"]]
    thesis = found.get("thesis")
    return changes, thesis if isinstance(thesis, dict) else None


def with_thesis(prompt: str) -> str:
    """The ingest instructions with the thesis's, for one call that writes both."""
    return (prompt.rstrip() + "\n\n# Also: the new project's thesis\n\n"
            "When the input creates a project, also draft that project's thesis, and give it beside the changes, "
            "in the same JSON object: {\"project\": \"<id>\", \"changes\": [ ... ], \"thesis\": { ... }}. Leave "
            "\"thesis\" out when the input creates no project. The instructions below were written for a call of "
            "their own: here the thesis goes in the \"thesis\" field of your one reply. The facts with figures it "
            "may draw on are in the payload, under \"Figures the graph holds\".\n\n"
            + THESIS_PROMPT.read_text(encoding="utf-8").strip() + "\n")


def tidy(changes, names) -> list:
    """Names as the checks expect them: short names in full ("Priya" → "Priya
    Patel"), and a project's own id without the project: that marks a project
    named as a dependency. Anything unknown is left for validate to name."""
    def full(value):
        if not isinstance(value, str) or value.startswith("project:"):
            return value
        return names.get(model.plain(value), value)

    out = []
    for ch in changes:
        ch, op = dict(ch), ch.get("op")
        if op == "create_project" and "project" not in ch and "id" in ch:
            ch["project"] = ch.pop("id")
        if isinstance(ch.get("project"), str) and ch["project"].startswith("project:"):
            ch["project"] = ch["project"][8:]
        if op == "set_field" and ch.get("field") in ("owner", "requested_by"):
            ch["value"] = full(ch.get("value"))
        elif op == "add_deliverable" and ch.get("owner"):
            ch["owner"] = full(ch["owner"])
        elif op == "add_dependency":
            ch["on"] = full(ch.get("on"))
        out.append(ch)
    return out


def propose(doc, text, records, entities, kind="transcript", on=None, llm=None, model_name=None,
            repair=True, figures=None, preloaded=False) -> dict:
    """The change set Claude proposes for one input, wrapped with its input, kind and date.

    When the checks refuse the first answer, Claude is shown what they named and
    asked once more (repair=False skips that); the set then carries "repaired",
    the problems the first answer had. llm(prompt, payload) -> reply text; one
    claude -p call each time when not given. figures: the facts with figures the
    graph holds; given, the same call also drafts the new project's thesis, and
    the set carries it as "thesis". preloaded: the caller vouches that the names
    (and figures) are all the graph holds; when every project fits among the
    candidates too, the payload opens by saying nothing else exists to look up.
    """
    on = on or input_date(doc)
    if llm is None:
        sys.path.insert(0, str(ROOT / "rag"))
        import distil  # the same headless call distil makes

        chosen = model_name or distil.model_name()
        llm = lambda prompt, body: distil.ask(chosen, prompt, body)  # noqa: E731
    names = model.name_map(entities)
    prompt, body = PROMPT.read_text(encoding="utf-8"), payload(doc, kind, on, text, records, entities)
    if figures is not None:  # one call for the change set and the new project's thesis
        prompt = with_thesis(prompt)
        body += "\n\nFigures the graph holds, for the thesis:\n" + (figures or "(none)")
    if preloaded and len(records) <= CANDIDATES:  # every project is among the candidates: nothing was cut
        body = preload_note("every project the workspace has, every name the graph knows"
                            + (", every fact with a figure it holds" if figures is not None else "")
                            + ", and the input") + body
    wrap = lambda changes: {"input": doc, "kind": kind, "on": on, "changes": changes}  # noqa: E731
    reply = llm(prompt, body)
    thesis = None
    try:
        changes, thesis = parse_all(reply)
        diff = wrap(tidy(changes, names))
        problems = model.validate(records, diff, text, names)[0]
    except ValueError as exc:  # no JSON at all: worth one more ask too
        diff, problems = None, [str(exc)]
    if problems and repair:
        answer = json.dumps({"changes": diff["changes"], **({"thesis": thesis} if thesis else {})},
                            ensure_ascii=False) if diff else reply.strip()[:2000]
        again = llm(prompt, body + REPAIR.format(answer=answer, problems="\n".join(f"- {p}" for p in problems)))
        try:
            changes, thesis_again = parse_all(again)
            diff = {**wrap(tidy(changes, names)), "repaired": problems}
            thesis = thesis_again or thesis
        except ValueError:
            pass  # keep the first answer; review shows its problems
    if diff is None:
        raise ValueError(problems[0])
    if thesis is not None:
        diff["thesis"] = thesis
    return diff


def keep(path, kind) -> Path:
    """The input inside this folder, copied under inputs/ when it is not already here."""
    path = Path(path).resolve()
    if path.is_relative_to(ROOT):
        return path
    target = INPUTS / FOLDERS.get(kind, "") / path.name
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.is_file() or target.read_bytes() != path.read_bytes():
        target.write_bytes(path.read_bytes())
    return target


def stage(path, kind="transcript", on=None, records_dir=RECORDS, db=None, model_name=None,
          llm=None, force=False) -> dict:
    """Propose, check and keep a change set for one input. Nothing is applied.

    Returns {"skipped": outcome} for an input already dealt with, else
    {"diff", "problems", "confirm", "review", "pending"}.
    """
    path = keep(path, kind)
    text = path.read_text(encoding="utf-8")
    doc, sha = path.relative_to(ROOT).as_posix(), model.digest(text)
    if not force and review.seen(doc, sha):
        return {"skipped": review.seen(doc, sha), "doc": doc}
    records = model.load_records(records_dir)
    entities = review.entities(db)
    diff = propose(doc, text, records, entities, kind, on or input_date(path), llm=llm,
                   model_name=model_name)
    diff["sha256"] = sha  # review.py refuses it if the input changes before it is applied
    problems, confirm = model.validate(records, diff, text, model.name_map(entities))
    PENDING.mkdir(parents=True, exist_ok=True)
    pending = PENDING / f"{path.stem}.json"
    pending.write_text(json.dumps(diff, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    after = model.apply(records, diff, text)[0] if not problems else {}
    return {"diff": diff, "problems": problems, "confirm": confirm, "pending": pending,
            "review": model.review(diff, problems, confirm, review.touched_gaps(diff, after))}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("input", help="the request, transcript or session entry, a markdown file")
    ap.add_argument("--kind", default="transcript", choices=sorted(FOLDERS))
    ap.add_argument("--on", help="the input's date, YYYY-MM-DD (default: from the file name)")
    ap.add_argument("--records", default=str(RECORDS), help="the project records folder")
    ap.add_argument("--db", default=str(ROOT / "graph.db"), help="the graph, for the names it knows")
    ap.add_argument("--model", help="default: the model in digest/config.json")
    ap.add_argument("--apply", action="store_true", help="apply it at once when it passes")
    ap.add_argument("--yes", action="store_true", help="also apply changes that need your confirmation")
    ap.add_argument("--force", action="store_true", help="read an input again although it was dealt with")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    result = stage(args.input, args.kind, args.on, args.records, args.db, args.model, force=args.force)
    if "skipped" in result:
        print(f"{result['doc']} was read before, unchanged ({result['skipped']}); --force to read it again")
        return
    print(result["review"])
    print(f"\nkept in {result['pending'].relative_to(ROOT).as_posix()}; "
          f"python projects/review.py {result['pending'].stem} --apply")
    if args.apply:
        try:
            print(review.apply_pending(result["pending"].stem, args.records, args.db, yes=args.yes))
        except ValueError as exc:
            sys.exit(str(exc))


if __name__ == "__main__":
    main()
