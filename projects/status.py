"""Change a project's status, or a step's, in your own words.

    python projects/status.py helpdesk-migration "Waiting on the supplier's revised quote." --status blocked
    python projects/status.py helpdesk-migration "Alex signed the contract today." --step 3 done
    python projects/status.py helpdesk-migration "Live, with history imported." --status done --yes

Your words are saved as inputs/notes/<date>-<id>.md and quoted as the source,
so the change is checked like any other. Moving to done or cancelled, or out
of them, needs --yes.
"""
import argparse
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import model  # noqa: E402
import review  # noqa: E402


def note_path(pid, on) -> str:
    """inputs/notes/<date>-<id>.md, numbered when there is already one that day."""
    base, n = f"inputs/notes/{on}-{pid}", 1
    while (ROOT / f"{base}{'' if n == 1 else f'-{n}'}.md").exists():
        n += 1
    return f"{base}{'' if n == 1 else f'-{n}'}.md"


def status_change(records, pid, words, status=None, step=None, on=None, doc=None) -> dict:
    """The note and the change set for one status or step change. Nothing is written."""
    on = on or date.today().isoformat()
    title = records[pid]["title"] if pid in records else pid
    text = f"# Note on {title}, {on}\n\n{words.strip()}\n"
    changes = []
    if status:
        changes.append({"op": "set_status", "project": pid, "value": status, "quote": words.strip()})
    if step:
        changes.append({"op": "set_step", "project": pid, "n": int(step[0]), "status": step[1],
                        "quote": words.strip()})
    diff = {"input": doc or note_path(pid, on), "kind": "note", "by": "you", "on": on, "changes": changes}
    return {"diff": diff, "text": text}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("project")
    ap.add_argument("words", help="why, in your own words: they are saved and quoted")
    ap.add_argument("--status", choices=model.STATUSES)
    ap.add_argument("--step", nargs=2, metavar=("N", "STATUS"))
    ap.add_argument("--on", help="the date it happened, YYYY-MM-DD (default: today)")
    ap.add_argument("--yes", action="store_true", help="confirm a move to or from done or cancelled")
    ap.add_argument("--records", default=str(review.RECORDS))
    ap.add_argument("--no-build", action="store_true")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    if not args.status and not args.step:
        sys.exit("say what changes: --status <status> and/or --step <n> <status>")
    records = model.load_records(args.records)
    change = status_change(records, args.project, args.words, args.status, args.step, args.on)
    diff, text = change["diff"], change["text"]
    problems, confirm = model.validate(records, diff, text, model.name_map(review.entities()))
    print(model.review(diff, problems, confirm))
    if problems:
        sys.exit("not changed")
    if confirm and not args.yes:
        sys.exit("not changed: add --yes to confirm")
    path = ROOT / diff["input"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    after, events = model.apply(records, diff, text)
    model.save_records(args.records, after, events)
    print(f"\nchanged: {diff['input']}")
    review.after_change(args.records, build=not args.no_build)


if __name__ == "__main__":
    main()
