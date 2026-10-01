"""Archived evidence changes into graph facts. No model is needed: the evidence schema
(evidence/openspec/schemas/evidence) is strict enough, and the parser forgives the usual drift (bold
labels, columns in another order, a heading without an id).

    python evidence/evidence_index.py [openspec root] [--number] [--json]    each archived evidence.md's facts

Each `## <set-id>: <title>` section of an evidence.md becomes an EVIDENCE entity, named "<set-id>
evidence", so the same set in a later change is the same entity. Its aliases are its title and keywords,
so a question in those words names it, and it `reads` a TABLE entity for each table it names, whose
aliases are its columns (orders.total_quantity). Two layouts put the numbers in the graph:
- set: every claim on the set's entity, each quoting its own line: the claim and verdict, one per row of
  the numbers table (the figure as the claim's amount, with the row's unit, so the thesis research finds
  it by its label's words), and one per note, as written;
- number: the claim, verdict and notes on the set's entity, and each row its own FINDING entity, part_of
  the set, named "<set-id> <key>" and aliased by its key's words, its label (less a period after a
  comma) and its figure as written, so a question naming the number, or quoting it, starts there.

A later archive that repeats a set's id supersedes it: the earlier claims end on the later change's date
(valid_to). They carry no valid_from. The date a finding was archived is not the period it measures, and
a question about July must still find July's numbers archived in September.
"""
import json
import re
import sys
from pathlib import Path

MAX_QUOTE = 300
ARCHIVED = re.compile(r"(?:^|/)changes/archive/(\d{4}-\d{2}-\d{2})-([^/]+)/evidence\.md$")
SET_HEADING = re.compile(r"^##\s+(.+?)\s*$")
FIELD = re.compile(r"^\s*(?:[-*]\s+)?\**(claim|verdict|keywords|tables|period|data|supersedes)\**\s*:\**\s*(.*?)\s*$", re.I)
NOTES = re.compile(r"^\s*\**notes\**\s*:?\**\s*$", re.I)
BULLET = re.compile(r"^\s*[-*]\s+(.+?)\s*$")
FIGURE = re.compile(r"^[£$€]?\s*(-?\d{1,3}(?:,\d{3})+|-?\d+)(\.\d+)?\s*(%|[a-z]+)?$", re.I)
TABLE_NAME = re.compile(r"([A-Za-z_][\w]*)\s*(?:\(([^)]*)\))?")


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def clip(text: str) -> str:
    return text if len(text) <= MAX_QUOTE else text[:MAX_QUOTE].rsplit(" ", 1)[0]


def figure(value: str):
    """The number a table cell states, or None: "178,905.30", "£9,185.90", "23.6%", "38.0"."""
    m = FIGURE.match(value.strip().replace("**", ""))
    if not m:
        return None
    x = float(m.group(1).replace(",", "") + (m.group(2) or ""))
    return int(x) if x.is_integer() and not m.group(2) else x


def _cells(line: str) -> list:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _columns(header: list) -> dict:
    """Which cell is which: key, label, value, unit, found by the header's words."""
    names = {"key": ("key", "id"), "label": ("number", "label", "measure", "metric", "name", "what"),
             "value": ("value", "figure", "result"), "unit": ("unit", "units")}
    out = {}
    for i, h in enumerate(c.lower().strip("* ") for c in header):
        for col, words in names.items():
            if col not in out and h in words:
                out[col] = i
    if "label" not in out and "key" in out:
        out["label"] = out["key"]
    return out


def parse(text: str) -> dict:
    """{period, data, supersedes, sets: [{id, title, claim, verdict, keywords, tables, numbers, notes, sql}]}."""
    lines = text.split("\n")
    doc = {"period": None, "data": None, "supersedes": None, "sets": []}
    cur, in_notes, in_sql, table = None, False, False, None
    for raw in lines:
        line = raw.rstrip()
        if line.strip().startswith("```"):
            in_sql = not in_sql
            if in_sql and cur is not None:
                cur["sql"].append("")
            continue
        if in_sql:
            if cur is not None:
                cur["sql"][-1] += line + "\n"
            continue
        m = SET_HEADING.match(line)
        if m and not line.startswith("###"):
            head = m.group(1).strip()
            idm = re.match(r"^`?([a-z0-9][a-z0-9_-]*)`?\s*[:—–-]\s+(.+)$", head)
            set_id, title = (idm.group(1), idm.group(2)) if idm else (slug(head), head)
            cur = {"id": set_id, "title": title.strip(), "claim": None, "verdict": None, "keywords": [],
                   "tables": [], "numbers": [], "notes": [], "sql": [], "lines": {}}
            doc["sets"].append(cur)
            in_notes, table = False, None
            continue
        f = FIELD.match(line)
        if f and not in_notes:
            key, value = f.group(1).lower(), f.group(2).strip()
            if cur is None:
                doc[key] = value
            elif key == "keywords":
                cur["keywords"] = [k.strip() for k in value.split(",") if k.strip()]
                cur["lines"]["keywords"] = line.strip()
            elif key == "tables":
                cur["tables"] = [(t, [c.strip() for c in (cols or "").split(",") if c.strip()])
                                 for t, cols in TABLE_NAME.findall(re.sub(r"\([^)]*\)", lambda x: x.group(0).replace(",", ";"), value).replace(";", ","))
                                 if t.lower() not in ("and",)]
            elif key in ("claim", "verdict"):
                cur[key] = value
                cur["lines"][key] = line.strip()
            continue
        if cur is None:
            continue
        if NOTES.match(line):
            in_notes, table = True, None
            continue
        if line.strip().startswith("|"):
            cells = _cells(line)
            if table is None:
                table = {"cols": _columns(cells)}
            elif all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
                continue
            elif "value" in table["cols"]:
                cols = table["cols"]
                get = lambda k: cells[cols[k]] if k in cols and cols[k] < len(cells) else ""  # noqa: E731
                cur["numbers"].append({"key": get("key") or slug(get("label")).replace("-", "_"),
                                       "label": get("label") or get("key"), "value": get("value"),
                                       "unit": get("unit"), "line": line.strip()})
            continue
        table = None
        b = BULLET.match(line)
        if in_notes and b:
            cur["notes"].append(b.group(1))
        elif in_notes and line.strip() and cur["notes"] and raw.startswith(("  ", "\t")):
            cur["notes"][-1] += " " + line.strip()  # a wrapped bullet
    return doc


def bare(text: str) -> str:
    """The same evidence as numbers only: each set's heading and its numbers table, under the period line.
    What a store that keeps the figures and nothing else would hold."""
    out, keep = [], False
    for line in text.split("\n"):
        if line.startswith("# ") or line.lower().startswith("period:"):
            out.append(line)
        elif SET_HEADING.match(line) and not line.startswith("###"):
            out += ["", line, ""]
        elif line.strip().startswith("|"):
            out.append(line)
    return "\n".join(out).strip() + "\n"


def evidence_name(set_id: str) -> str:
    return f"{set_id} evidence"


LAYOUTS = ("set", "number")
PERIOD_SUFFIX = re.compile(r",\s*(first half of \d{4}|[a-z]+ and [a-z]+ \d{4}|[a-z]+ \d{4}|\d{4})\s*$", re.I)


def number_name(set_id: str, key: str) -> str:
    return f"{set_id} {key}"


def number_aliases(n: dict) -> list:
    """What a question may call a number: its key's words, its label less a trailing period, its figure."""
    out = [n["key"].strip("` ").replace("_", " "), PERIOD_SUFFIX.sub("", n["label"])]
    if figure(n["value"]) is not None:
        out.append(n["value"].strip().strip("£$€% "))
    return [a for a in dict.fromkeys(out) if a and a.lower() not in ("verdict", "value")]


def extraction(text: str, path: str, archived: str, ends: dict = None, change: str = "",
               layout: str = "set") -> tuple:
    """(extraction doc, problems) for one archived evidence.md. ends: {set id: the date a later change
    superseded it}. layout: set or number (see the module's doc)."""
    doc, problems, ends = parse(text), [], ends or {}
    period = doc["period"] or "period not stated"
    nodes, edges, aliases, tables = [], [], [], {}
    seen = set()
    for s in doc["sets"]:
        name = evidence_name(s["id"])
        if name in seen:
            problems.append(f"{path}: set {s['id']} appears twice")
            continue
        seen.add(name)
        dates = {"valid_to": ends[s["id"]]} if s["id"] in ends else {}
        where = f"{period}; {change or 'evidence'} archived {archived}"
        claims = []
        if s["claim"] or s["verdict"]:
            text_ = " ".join(x for x in (s["claim"], f"Verdict: {s['verdict']}." if s["verdict"] else None) if x)
            quote = s["lines"].get("verdict") or s["lines"].get("claim")
            claims.append({"kind": "note", "text": f"{text_} ({where})", "quote": clip(quote), **dates})
        if not s["numbers"]:
            problems.append(f"{path}: set {s['id']} has no numbers table (Key | Number | Value | Unit)")
        for n in s["numbers"]:
            amount = figure(n["value"])
            unit = n["unit"] or ("%" if n["value"].strip().endswith("%") else "")
            c = {"kind": "note", "text": f"{n['label']}: {n['value']} {unit} ({period})".replace("  ", " "),
                 "quote": clip(n["line"]), **dates}
            if amount is not None:
                c.update(amount=amount, unit=unit)
            key = n["key"].strip("` ").lower()
            if layout == "number" and key != "verdict":
                nn = number_name(s["id"], key)
                nodes.append({"name": nn, "type": "FINDING", "claims": [c]})
                edges.append({"source": nn, "predicate": "part_of", "target": name, **dates})
                aliases += [{"entity": nn, "alias": a} for a in number_aliases(n)]
            else:
                claims.append(c)
        for note in s["notes"]:
            quote = clip(note)
            if quote != note:
                problems.append(f"{path}: a note in {s['id']} is over {MAX_QUOTE} characters; it is quoted in part")
            claims.append({"kind": "note", "text": note, "quote": quote, **dates})
        nodes.append({"name": name, "type": "EVIDENCE", "claims": claims})
        for a in [s["title"], s["id"].replace("-", " ")] + s["keywords"]:
            if a and a.lower() != name.lower():
                aliases.append({"entity": name, "alias": a})
        for t, cols in s["tables"]:
            tables.setdefault(t, set()).update(cols)
            edges.append({"source": name, "predicate": "reads", "target": f"{t} table", **dates})
    for t, cols in sorted(tables.items()):
        nodes.append({"name": f"{t} table", "type": "TABLE", "claims": []})
        aliases += [{"entity": f"{t} table", "alias": f"{t}.{c}"} for c in sorted(cols)]
    return {"source_doc": path, "nodes": nodes, "edges": edges, "aliases": aliases}, problems


def archives(files: dict) -> list:
    """[(date, change, path, text)] for every archived evidence.md, oldest first. files: {path: text}."""
    return sorted((m.group(1), m.group(2), path, text) for path, text in files.items() if (m := ARCHIVED.search(path)))


def index(files: dict, name_of=None, layout: str = "set") -> tuple:
    """({graph doc path: extraction}, problems) for every archived evidence.md in files ({path: text}).
    name_of(date, change) gives the document's path in the graph (default evidence/<date>-<change>/evidence.md)."""
    name_of = name_of or (lambda d, c: f"evidence/{d}-{c}/evidence.md")
    found = archives(files)
    ends_by = {}
    later = {}
    for date, change, path, text in reversed(found):  # newest first: each set's next archive
        ids = [s["id"] for s in parse(text)["sets"]]
        ends_by[(date, change)] = {i: later[i] for i in ids if i in later}
        for i in ids:
            later[i] = date
    out, problems = {}, []
    for date, change, path, text in found:
        doc_path = name_of(date, change)
        x, p = extraction(text, doc_path, date, ends_by[(date, change)], change, layout)
        out[doc_path] = x
        problems += p
    return out, problems


def read_root(root: Path) -> dict:
    """{path relative to the root's parent: text} for an OpenSpec root's archived evidence."""
    root = Path(root)
    return {f.relative_to(root.parent).as_posix(): f.read_text(encoding="utf-8")
            for f in sorted(root.glob("changes/archive/*/evidence.md"))}


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    root = Path(args[0]) if args else Path(__file__).resolve().parent / "openspec"
    docs, problems = index(read_root(root), layout="number" if "--number" in sys.argv else "set")
    for path, x in docs.items():
        ev = [n for n in x["nodes"] if n["type"] in ("EVIDENCE", "FINDING")]
        print(f"{path}: {len(ev)} evidence and finding entities, {sum(len(n['claims']) for n in ev)} claims, "
              f"{sum(1 for n in ev for c in n['claims'] if 'amount' in c)} with a figure, "
              f"{len(x['aliases'])} aliases, ends {sorted({c['valid_to'] for n in ev for c in n['claims'] if 'valid_to' in c}) or 'none'}")
    for p in problems:
        print("problem:", p)
    if "--json" in sys.argv:
        print(json.dumps(docs, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
