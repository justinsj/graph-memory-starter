"""Review the change sets ingest proposed, and apply or reject them.

    python projects/review.py                    what is waiting
    python projects/review.py <name>             one, checked against the records as they are now
    python projects/review.py <name> --apply     apply it; --yes also applies changes that need you
    python projects/review.py <name> --reject    drop it
    python projects/review.py --notice           the SessionStart hook: say when updates wait

Applying writes the records and their histories, notes the input in
projects/ingested.json so it is not read twice, rewrites projects/BOARD.md and
rebuilds graph.db. Rejecting notes the input too.
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

RECORDS = HERE / "records"
PENDING = HERE / "pending"
LEDGER = HERE / "ingested.json"


def entities(db=None) -> list:
    """The names the graph knows, from graph.db when it is built, else the extraction."""
    db = Path(db or ROOT / "graph.db")
    return model.entities_from_db(db) if db.is_file() else model.entities_from_extraction(ROOT / "extraction")


def ledger() -> dict:
    try:
        return json.loads(LEDGER.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def seen(doc, sha):
    """How an input was dealt with before, if this exact text was: applied, rejected, empty."""
    entry = ledger().get(doc)
    return entry["outcome"] if entry and entry["sha256"] == sha else None


def note(doc, sha, outcome) -> None:
    book = ledger()
    book[doc] = {"sha256": sha, "outcome": outcome, "on": date.today().isoformat()}
    LEDGER.write_text(json.dumps(book, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def pending() -> list:
    return sorted(PENDING.glob("*.json")) if PENDING.is_dir() else []


def load(name):
    """(path, change set, the input's text now, or None when it is gone)."""
    path = PENDING / (name if name.endswith(".json") else f"{name}.json")
    diff = json.loads(path.read_text(encoding="utf-8"))
    src = ROOT / diff["input"]
    return path, diff, src.read_text(encoding="utf-8") if src.is_file() else None


def check(diff, text, records, names) -> tuple:
    """validate(), plus: the input must still be there, and unchanged since it was read."""
    if text is None:
        return [f"{diff['input']} is gone"], []
    stale = ([f"{diff['input']} changed since this was proposed: ingest it again"]
             if diff.get("sha256") and model.digest(text) != diff["sha256"] else [])
    problems, confirm = model.validate(records, diff, text, names)
    return stale + problems, confirm


def touched_gaps(diff, after) -> dict:
    ids = {ch.get("project") for ch in diff["changes"]} & set(after)
    return {pid: model.gaps(after[pid]) for pid in sorted(ids) if model.gaps(after[pid])}


def show(name, records_dir=RECORDS, db=None) -> str:
    _, diff, text = load(name)
    records = model.load_records(records_dir)
    problems, confirm = check(diff, text, records, model.name_map(entities(db)))
    after = model.apply(records, diff, text)[0] if not problems else {}
    return model.review(diff, problems, confirm, touched_gaps(diff, after))


def apply_pending(name, records_dir=RECORDS, db=None, yes=False, build=True) -> str:
    """Apply one pending change set. Returns what happened; raises ValueError when it cannot."""
    path, diff, text = load(name)
    records = model.load_records(records_dir)
    problems, confirm = check(diff, text, records, model.name_map(entities(db)))
    if problems:
        raise ValueError("not applied, it has problems:\n" + "\n".join(f"  {p}" for p in problems))
    if confirm and not yes:
        raise ValueError("not applied, these need your confirmation (--yes):\n"
                         + "\n".join(f"  {c}" for c in confirm))
    after, events = model.apply(records, diff, text)
    model.save_records(records_dir, after, events)
    note(diff["input"], model.digest(text), "applied" if diff["changes"] else "empty")
    path.unlink()
    after_change(records_dir, build)
    return f"applied {path.stem}: {len(events)} change{'' if len(events) == 1 else 's'}"


def reject(name) -> str:
    path, diff, text = load(name)
    if text is not None:
        note(diff["input"], model.digest(text), "rejected")
    path.unlink()
    return f"rejected {path.stem}"


def after_change(records_dir=RECORDS, build=True) -> None:
    """Keep the board and the graph in step with the records."""
    import board

    board.write(records_dir)
    if build:
        sys.path.insert(0, str(ROOT / "src"))
        import build_graph

        print(build_graph.summary(build_graph.build(records=records_dir)))


def notice() -> None:
    """SessionStart: one line when proposed updates are waiting, nothing otherwise."""
    waiting = pending()
    if not waiting:
        return
    n = len(waiting)
    print(json.dumps({
        "systemMessage": f"projects: {n} update{'' if n == 1 else 's'} to review (/project-review)",
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": (f"{n} proposed project update{'' if n == 1 else 's'} "
                                  f"{'is' if n == 1 else 'are'} waiting for review in projects/pending/ "
                                  f"({', '.join(p.stem for p in waiting)}). Mention it once, in one line, "
                                  "and offer /project-review. Do not apply anything unasked."),
        }}))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("name", nargs="?", help="a pending change set (its file name, without .json)")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--yes", action="store_true", help="also apply changes that need your confirmation")
    ap.add_argument("--reject", action="store_true")
    ap.add_argument("--notice", action="store_true")
    ap.add_argument("--records", default=str(RECORDS))
    ap.add_argument("--no-build", action="store_true", help="do not rebuild graph.db afterwards")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    if args.notice:
        try:
            notice()
        except Exception:  # a session opening is never blocked by this
            pass
        return
    if not args.name:
        waiting = pending()
        if not waiting:
            print("nothing waiting")
        for p in waiting:
            _, diff, _ = load(p.stem)
            print(f"{p.stem}: {len(diff['changes'])} changes from {diff['input']}")
        return
    try:
        if args.reject:
            print(reject(args.name))
        elif args.apply:
            print(apply_pending(args.name, args.records, yes=args.yes, build=not args.no_build))
        else:
            print(show(args.name, args.records))
    except ValueError as exc:
        sys.exit(str(exc))


if __name__ == "__main__":
    main()
