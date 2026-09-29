"""Load extraction/*.json into graph.db. Deterministic: same input, same db.

Each node carries claims: one-sentence facts about it, each with a kind, the
source's own words it rests on (a quote), and, when the source says so, the
dates it holds for. Links can carry dates too. So a policy amended on a date
keeps both versions, each with its dates and its quote.

Also builds the access layer recall.py reads (see schema.sql): the name
index, the indexes on both ends of every link, and the full-text index.

The build stops, rather than guess, when the extraction is inconsistent:
a name given two types, an unknown claim kind, a bad date, two versions of
the same fact whose dates overlap, or a quote its source does not contain.
It warns about gaps: a role nobody holds, an entity nothing is said about.

Project records (projects/records/*.json) are loaded beside the documents: a
project and its deliverables become entities, its status, due date, decisions
and open questions dated claims, its owner and dependencies links, and its
steps, sources and history their own tables. A record whose quotes are not in
its inputs stops the build too. What needs looking at (stale, overdue, a source
changed since it was read) is reported, not refused.

A codebase (--code) is indexed beside them by codegraph/index.py, with no
model: its functions, constants, routes and buttons become entities, what
reaches what their links, and each defining line a claim whose quote is checked
against the file, as a document's are.
"""
import json
import sqlite3
import sys
import uuid
from contextlib import closing
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from recall import plain, today, words  # noqa: E402  split and compare text the way recall does

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "graph.db"
EXTRACTION = ROOT / "extraction"
DOCS = ROOT / "corpus"  # the documents the extraction was made from
RECORDS = ROOT / "projects" / "records"  # project records; their sources resolve against ROOT
DEPENDS = {"needs": "depends_on", "subject_to": "subject_to", "blocked_by": "blocked_by"}
NEEDS = {"needs": "Needs", "subject_to": "Subject to", "blocked_by": "Blocked by"}

KINDS = {"threshold", "deadline", "availability", "unknown", "responsibility", "rule", "note",
         "value"}  # value: a constant in code
ONE_AT_A_TIME = {"threshold", "availability"}  # two of these at once is a conflict
MAX_QUOTE = 300  # characters: the longest sentence in the demo documents is 295


def normalise(name: str) -> str:
    return name.lower().strip().replace(" ", "_")


def entity_id(type_: str, name: str) -> str:
    key = f"{type_}:{normalise(name)}"
    return str(uuid.uuid5(uuid.NAMESPACE_OID, key))
    # "Ops Manager" in doc 1 and doc 4 -> the same node. No ML, no lookup.


def claims_of(node: dict) -> list:
    """A node's claims. An older extraction's single description becomes one note."""
    if "claims" in node:
        return node["claims"]
    return [{"kind": "note", "text": node["description"]}] if node.get("description") else []


def clashes(docs: list) -> dict:
    """Names given two types. Links name their ends without a type, so two
    entities sharing a name would silently share each other's links."""
    types = {}
    for doc in docs:
        for n in doc["nodes"]:
            types.setdefault(normalise(n["name"]), {}).setdefault(n["type"], doc["source_doc"])
    return {name: seen for name, seen in types.items() if len(seen) > 1}


def problems(docs: list, docs_root: Path = None) -> list:
    """Everything in the extraction the build refuses to guess about."""
    docs_root = Path(docs_root or DOCS)
    out, sources = [], {}

    def source_text(name):
        if name not in sources:
            path = docs_root / name
            sources[name] = plain(path.read_text(encoding="utf-8")) if path.is_file() else None
        return sources[name]

    def check_dates(item, where):
        vf, vt = item.get("valid_from"), item.get("valid_to")
        for value in (vf, vt):
            if value is not None:
                try:
                    date.fromisoformat(value)
                except (TypeError, ValueError):
                    out.append(f"{where}: {value!r} is not a YYYY-MM-DD date")
                    return
        if vf and vt and vf >= vt:
            out.append(f"{where}: valid_from {vf} is not before valid_to {vt}")

    held = {}  # (entity, kind) -> [(from, to, text, doc)] for the one-at-a-time kinds
    for doc in docs:
        src = doc["source_doc"]
        for n in doc["nodes"]:
            for c in claims_of(n):
                where = f"{src}, {n['name']}: \"{c.get('text', '')}\""
                if c.get("kind") not in KINDS:
                    out.append(f"{where}: kind {c.get('kind')!r} is not one of {sorted(KINDS)}")
                check_dates(c, where)
                quote = c.get("quote")
                if quote is not None:
                    if len(quote) > MAX_QUOTE:
                        out.append(f"{where}: the quote is {len(quote)} characters; "
                                   f"quote at most {MAX_QUOTE}")
                    elif source_text(src) is None:
                        out.append(f"{where}: {src} is not in {docs_root}, so the quote "
                                   "cannot be checked")
                    elif plain(quote) not in source_text(src):
                        out.append(f"{where}: {src} does not contain the quote "
                                   f"\"{quote}\" - copy it word for word")
                if c.get("kind") in ONE_AT_A_TIME:
                    held.setdefault((normalise(n["name"]), c["kind"]), []).append(
                        (c.get("valid_from") or "0000-01-01", c.get("valid_to") or "9999-12-31",
                         c["text"], src))
        for e in doc["edges"]:
            check_dates(e, f"{src}, {e['source']} --[{e['predicate']}]--> {e['target']}")
        for site in doc.get("sites", []):  # code: each link's own line
            where = f"{src}:{site['line']}, {site['source']} {site['predicate']} {site['target']}"
            if source_text(src) is None:
                out.append(f"{where}: {src} is not in {docs_root}")
            elif plain(site["quote"]) not in source_text(src):
                out.append(f"{where}: {src} does not contain the line \"{site['quote']}\"")
    for (name, kind), versions in held.items():
        for i, (a_from, a_to, a_text, a_doc) in enumerate(versions):
            for b_from, b_to, b_text, b_doc in versions[i + 1:]:
                if plain(a_text) == plain(b_text):
                    continue  # the same fact, said by two sources: one claim, confirmed twice
                if a_from < b_to and b_from < a_to:
                    out.append(f"{name}: two {kind} claims hold at once - give them dates "
                               f"that do not overlap:\n    \"{a_text}\" ({a_doc})\n"
                               f"    \"{b_text}\" ({b_doc})")
    return out


def coverage(db: sqlite3.Connection) -> list:
    """Gaps a question would fall into: the model goes looking for what is not here."""
    out = [f"{name}: a role nobody holds - add a held_by link, or an unknown claim saying "
           "the documents name nobody" for (name,) in db.execute("""
        SELECT name FROM entities e WHERE type = 'ROLE'
          AND NOT EXISTS (SELECT 1 FROM relations r WHERE r.source_id = e.id
                          AND r.predicate = 'held_by')
          AND NOT EXISTS (SELECT 1 FROM claims c WHERE c.entity_id = e.id
                          AND c.kind = 'unknown')
        ORDER BY name""")]
    out += [f"{name}: no claims - nothing the model can be told about it" for (name,) in db.execute(
        "SELECT name FROM entities e WHERE NOT EXISTS "
        "(SELECT 1 FROM claims c WHERE c.entity_id = e.id) ORDER BY name")]
    return out


def _projects_module():
    sys.path.insert(0, str(ROOT / "projects"))
    import model  # projects/model.py: the record and its checks

    return model


def load_records(records: Path) -> tuple:
    """({id: record}, {id: [history lines]}), or nothing when there are no records."""
    folder = Path(records)
    if not folder.is_dir() or not any(folder.glob("*.json")):
        return {}, {}
    recs = {pid: rec for pid, rec in _projects_module().load_records(folder).items()
            if not rec.get("deleted")}  # soft-deleted: kept in the records, left out of the graph
    logs = {}
    for pid in recs:
        log = folder / f"{pid}.log.jsonl"
        logs[pid] = ([json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line.strip()]
                     if log.is_file() else [])
    return recs, logs


def record_problems(recs: dict, root: Path) -> list:
    """Records the build refuses: a quote its input does not contain, or no record at all."""
    out = []
    for pid, rec in recs.items():
        try:
            out += _projects_module().check_record(rec, root)
        except (KeyError, TypeError, AttributeError) as e:
            out.append(f"{pid}: not a project record ({type(e).__name__}: {e})")
    return out


def first_read(rec: dict) -> dict:
    """{source: the day it was first read}: what a record learnt from it holds from then."""
    out = {}
    for src in rec["sources"]:
        out.setdefault(src["doc"], src["read_on"])
    return out


def project_claims(rec: dict, recs: dict) -> list:
    """(kind, text, quote, valid_from, valid_to, source) for what a record says about its project.

    Each holds from the day its source was read, so a question about an earlier
    date is not told what nobody knew yet; a status holds from its own date.
    """
    read = first_read(rec)
    since = lambda item: read.get(item["source"])  # noqa: E731
    out = [("note", rec["description"]["text"], rec["description"]["quote"], since(rec["description"]), None,
            rec["description"]["source"])]
    status = rec["status"]
    for i, st in enumerate(status):
        ends = status[i + 1]["from"] if i + 1 < len(status) else None
        if ends != st["from"]:  # a status replaced the same day never held
            out.append(("status", f"Status: {st['value'].replace('_', ' ')}", st["quote"], st["from"], ends,
                        st["source"]))
    for field, label in (("owner", "Owned by"), ("requested_by", "Requested by")):
        if rec[field]:
            out.append(("responsibility", f"{label} {rec[field]['entity']}", rec[field]["quote"],
                        since(rec[field]), None, rec[field]["source"]))
    due = rec["due"]
    if due:
        when = due.get("date") or due["text"]
        text = f"Due {when}" + (f" ({due['text']})" if due.get("date") and due["text"] != when else "")
        out.append(("deadline", text, due["quote"], since(due), None, due["source"]))
    for d in rec["dependencies"]:
        other = recs.get(d["on"][8:]) if d["on"].startswith("project:") else None
        out.append(("rule", f"{NEEDS[d['kind']]} {other['title'] if other else d['on']}", d["quote"], since(d),
                    None, d["source"]))
    out += [("decision", f"Decided: {d['text']}", d["quote"], d["on"], None, d["source"]) for d in rec["decisions"]]
    out += [("unknown", f"Open question: {q['text']}", q["quote"], since(q), None, q["source"])
            for q in rec["questions"] if not q.get("answered")]
    return out


def add_project_entities(db: sqlite3.Connection, recs: dict) -> dict:
    """Projects and deliverables as entities, with their claims. Returns {id: entity id}."""
    ids = {}

    def claim(eid, kind, text, quote, vf, vt, source):
        db.execute("INSERT INTO claims (entity_id, kind, text, quote, valid_from, valid_to, source_doc)"
                   " VALUES (?,?,?,?,?,?,?)", (eid, kind, text, quote, vf, vt, source))

    for pid, rec in sorted(recs.items()):
        eid = ids[pid] = entity_id("PROJECT", pid)  # the id, not the title: a rename keeps its links
        db.execute("INSERT INTO entities VALUES (?,?,?,?)", (eid, rec["title"], "PROJECT",
                                                            rec["description"]["source"]))
        for c in project_claims(rec, recs):
            claim(eid, *c)
        for d in rec["deliverables"]:
            did = entity_id("DELIVERABLE", f"{pid}/{d['key']}")
            db.execute("INSERT INTO entities VALUES (?,?,?,?)", (did, d["title"], "DELIVERABLE", d["source"]))
            claim(did, "note", f"{d['key']} of {rec['title']}" + (f", due {d['due']}" if d["due"] else ""),
                  d["quote"], first_read(rec).get(d["source"]), None, d["source"])
            if d["status"] != "planned" and d.get("update"):
                claim(did, "status", f"Status: {d['status'].replace('_', ' ')}", d["update"]["quote"],
                      d["on"], None, d["update"]["source"])
    return ids


def add_project_links(db: sqlite3.Connection, recs: dict, logs: dict, ids: dict) -> list:
    """Links from each project to people, documents, policies and other projects, and the
    project tables. Returns warnings for names the graph does not know."""
    model = _projects_module()
    people = {normalise(n): eid for eid, n in db.execute(
        "SELECT id, name FROM entities WHERE type NOT IN ('PROJECT', 'DELIVERABLE')")}
    warnings = []

    def resolve(name, where):
        eid = people.get(normalise(name))
        if eid is None:
            warnings.append(f"{where}: {name} is not in the graph, so it is not linked")
        return eid

    for pid, rec in sorted(recs.items()):
        eid, read = ids[pid], first_read(rec)

        def link(s, t, predicate, source):  # a link holds from the day its source was read
            if s and t:
                db.execute("INSERT INTO relations VALUES (?,?,?,?,?,?)",
                           (s, t, predicate, source, read.get(source), None))

        owner = resolve(rec["owner"]["entity"], pid) if rec["owner"] else None
        link(eid, owner, "owned_by", rec["owner"] and rec["owner"]["source"])
        if rec["requested_by"]:
            link(eid, resolve(rec["requested_by"]["entity"], pid), "requested_by", rec["requested_by"]["source"])
        for d in rec["dependencies"]:
            target = ids.get(d["on"][8:]) if d["on"].startswith("project:") else resolve(d["on"], pid)
            link(eid, target, DEPENDS[d["kind"]], d["source"])
        dates = [st["from"] for st in rec["status"]] + [src["read_on"] for src in rec["sources"]]
        due = rec["due"] or {}
        db.execute("INSERT INTO projects VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                   (eid, pid, model.status_of(rec) or "proposed", rec["status"][-1]["from"] if rec["status"] else None,
                    rec["plan"]["state"], rec["plan"]["version"], rec["plan"].get("agreed_on"), owner,
                    min(dates) if dates else None, model.last_activity(rec), due.get("date"), due.get("text")))
        dids = {}
        for d in rec["deliverables"]:
            did = dids[d["key"]] = entity_id("DELIVERABLE", f"{pid}/{d['key']}")
            link(eid, did, "delivers", d["source"])
            d_owner = resolve(d["owner"], f"{pid} {d['key']}") if d["owner"] else None
            link(did, d_owner, "owned_by", d["source"])
            db.execute("INSERT INTO deliverables VALUES (?,?,?,?,?,?,?,?)",
                       (did, eid, d["key"], d["title"], d["status"], d["due"], d["on"], d_owner))
        step_ids = {}
        for st in rec["plan"]["steps"]:
            s_owner = resolve(st["owner"], f"{pid} step {st['n']}") if st["owner"] else None
            cur = db.execute("INSERT INTO steps (project_id, n, title, status, due, on_date, owner_id,"
                             " deliverable_id, source_doc, quote) VALUES (?,?,?,?,?,?,?,?,?,?)",
                             (eid, st["n"], st["title"], st["status"], st["due"], st["on"], s_owner,
                              dids.get(st["delivers"]), st["source"], st["quote"]))
            step_ids[st["n"]] = cur.lastrowid
        for st in rec["plan"]["steps"]:
            db.executemany("INSERT INTO step_after VALUES (?,?)",
                           [(step_ids[st["n"]], step_ids[a]) for a in st["after"] if a in step_ids])
        db.executemany("INSERT OR IGNORE INTO sources VALUES (?,?,?,?,?,?)",
                       [(eid, src["doc"], src["kind"], src["read_on"], src["sha256"], json.dumps(src["used_for"]))
                        for src in rec["sources"]])
        for ev in logs.get(pid, []):
            subject = (f"step {ev['step']}" if "step" in ev else ev.get("key") or ev.get("field"))
            db.execute("INSERT INTO events (project_id, on_date, op, subject, old, new, by, source_doc, quote)"
                       " VALUES (?,?,?,?,?,?,?,?,?)",
                       (eid, ev["on"], ev["op"], subject, None if ev.get("old") is None else str(ev["old"]),
                        None if ev.get("new") is None else str(ev["new"]), ev.get("by"), ev.get("source"),
                        ev.get("quote")))
    return warnings


def project_health(db: sqlite3.Connection, recs: dict, root: Path, now) -> list:
    """What needs looking at, per project: see projects/model.py health()."""
    model = _projects_module()
    names = {plain(text): name for text, name in db.execute(
        "SELECT n.text, e.name FROM names n JOIN entities e ON e.id = n.entity_id "
        "WHERE e.type NOT IN ('PROJECT', 'DELIVERABLE')")}
    return [f"{pid}: {w}" for pid, rec in sorted(recs.items())
            for w in model.health(rec, recs, root, now, names)]


def index_code(code: Path) -> dict:
    """codegraph/index.py's output for the codebase at code."""
    sys.path.insert(0, str(ROOT / "codegraph"))
    import index  # codegraph/index.py

    return index.index(code)


def build(extraction: Path = None, db_path: Path = None, docs_root: Path = None,
          records: Path = None, records_root: Path = None, now=None, code: Path = None) -> dict:
    """Build graph.db. records: the project records folder (default projects/records);
    records_root: what their sources' paths are relative to (default this folder);
    code: a codebase to index beside the documents (default none)."""
    extraction = Path(extraction or EXTRACTION)
    db_path = Path(db_path or DB)
    docs_root = Path(docs_root or DOCS).resolve()
    records_root = Path(records_root or ROOT).resolve()
    files = sorted(extraction.glob("*.json"))
    docs = [json.loads(f.read_text(encoding="utf-8")) for f in files]
    recs, logs = load_records(records or RECORDS)
    code_root = Path(code).resolve() if code else None
    coded = index_code(code_root) if code_root else {"docs": [], "symbols": {}, "files": 0, "indexed": ""}

    clash = clashes(docs + coded["docs"])
    if clash:
        raise SystemExit("same name, different types - rename one of each:\n" + "\n".join(
            f"  {name}: " + ", ".join(f"{t} in {d}" for t, d in seen.items())
            for name, seen in clash.items()))
    bad = problems(docs, docs_root)
    if bad:
        raise SystemExit("the extraction needs fixing first:\n" + "\n".join(f"  {p}" for p in bad))
    bad = problems(coded["docs"], code_root) if code_root else []
    if bad:
        raise SystemExit("the code index does not match the code:\n" + "\n".join(f"  {p}" for p in bad))
    bad = record_problems(recs, records_root)
    if bad:
        raise SystemExit("the project records need fixing first:\n" + "\n".join(f"  {p}" for p in bad))

    db_path.unlink(missing_ok=True)
    with closing(sqlite3.connect(db_path)) as db:
        db.execute("PRAGMA foreign_keys = ON")  # SQLite only enforces them when asked
        db.executescript((ROOT / "src" / "schema.sql").read_text(encoding="utf-8"))

        # Pass 1 - every node from every doc, content-addressed, with its claims.
        # A node named in several docs is one entity holding every doc's claims.
        for doc in docs + coded["docs"]:
            for n in doc["nodes"]:
                eid = entity_id(n["type"], n["name"])
                db.execute("INSERT OR IGNORE INTO entities VALUES (?,?,?,?)",
                           (eid, n["name"], n["type"], doc["source_doc"]))
                for c in claims_of(n):
                    db.execute(
                        "INSERT INTO claims (entity_id, kind, text, quote, amount, unit,"
                        " valid_from, valid_to, source_doc) VALUES (?,?,?,?,?,?,?,?,?)",
                        (eid, c["kind"], c["text"], c.get("quote"), c.get("amount"),
                         c.get("unit"), c.get("valid_from"), c.get("valid_to"),
                         doc["source_doc"]))

        project_ids = add_project_entities(db, recs)
        by_name = {normalise(name): eid for eid, name in db.execute(
            "SELECT id, name FROM entities WHERE type NOT IN ('PROJECT', 'DELIVERABLE')")}

        # Pass 2 - edges, endpoints resolved by normalised name; and every name
        # and alias, as a run of words, in the one table recall searches.
        names = {(" ".join(words(n)), eid): ("name", n)
                 for eid, n in db.execute("SELECT id, name FROM entities")}
        skipped = []
        for doc in docs + coded["docs"]:
            for e in doc["edges"]:
                s = by_name.get(normalise(e["source"]))
                t = by_name.get(normalise(e["target"]))
                if s and t:
                    db.execute("INSERT INTO relations VALUES (?,?,?,?,?,?)",
                               (s, t, e["predicate"], doc["source_doc"],
                                e.get("valid_from"), e.get("valid_to")))
                else:
                    skipped.append((doc["source_doc"], e))
            for a in doc.get("aliases", []):
                eid = by_name.get(normalise(a["entity"]))
                if eid:
                    names.setdefault((" ".join(words(a["alias"])), eid), ("alias", a["alias"]))
        for pid, rec in recs.items():  # a project's other names, old titles among them
            for a in rec["aliases"]:
                names.setdefault((" ".join(words(a)), project_ids[pid]), ("alias", a))
        project_warnings = add_project_links(db, recs, logs, project_ids)
        db.executemany("INSERT INTO code_symbols VALUES (?,?,?,?,?,?)",
                       [(entity_id(i["type"], name), i["file"], i["line"], i["language"], i["value"], i["resolved"])
                        for name, i in sorted(coded["symbols"].items())])
        sym = coded["symbols"]
        db.executemany("INSERT INTO call_sites VALUES (?,?,?,?,?,?,?)", [
            (entity_id(sym[x["source"]]["type"], x["source"]), entity_id(sym[x["target"]]["type"], x["target"]),
             x["predicate"], d["source_doc"], x["line"], x["quote"], x.get("detail"))
            for d in coded["docs"] for x in d.get("sites", [])])
        db.executemany("INSERT INTO names VALUES (?,?,?,?)",
                       sorted((norm, eid, kind, text) for (norm, eid), (kind, text) in names.items()))

        # Pass 3 - the access layer: every entity's name and claims in the
        # full-text index.
        db.execute("""
            INSERT INTO entity_fts
            SELECT e.id, e.name,
                   COALESCE((SELECT group_concat(text, '; ')
                             FROM (SELECT text FROM claims WHERE entity_id = e.id ORDER BY id)), '')
            FROM entities e""")

        counts = {t: db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]  # noqa: S608
                  for t in ("entities", "claims", "relations")}
        counts["aliases"] = db.execute("SELECT COUNT(*) FROM names WHERE kind = 'alias'").fetchone()[0]
        where = docs_root.relative_to(ROOT).as_posix() if docs_root.is_relative_to(ROOT) \
            else docs_root.as_posix()
        if code_root:
            db.executemany("INSERT INTO meta VALUES (?,?)", [
                ("code_root", code_root.relative_to(ROOT).as_posix() if code_root.is_relative_to(ROOT)
                 else code_root.as_posix()),
                ("code_files", str(coded["files"])), ("code_indexed", coded["indexed"])])
        if recs:
            where_records = records_root.relative_to(ROOT).as_posix() if records_root.is_relative_to(ROOT) \
                else records_root.as_posix()
            db.executemany("INSERT INTO meta VALUES (?,?)", [
                ("projects", str(len(recs))), ("records_root", where_records or "."),
                ("projects_updated", max(filter(None, (_projects_module().last_activity(r)
                                                      for r in recs.values())), default=""))])
        db.executemany("INSERT INTO meta VALUES (?,?)", [
            ("entities", str(counts["entities"])),
            ("longest_name", str(max((len(norm.split()) for norm, _ in names), default=1))),
            ("docs_root", where),
            ("docs", str(len({d["source_doc"] for d in docs}))),
            # when the facts were extracted: the newest extraction file, so the
            # same input still builds the same db, whatever day it is built
            ("extracted", date.fromtimestamp(max(f.stat().st_mtime for f in files)).isoformat()
             if files else ""),
        ])
        warnings = coverage(db)
        checks = project_warnings + project_health(db, recs, records_root, now or today())
        db.commit()
    return {**counts, "docs": len(files), "projects": len(recs), "code_files": coded["files"], "skipped": skipped,
            "warnings": warnings, "checks": checks, "db": db_path}


def summary(result: dict) -> str:
    """The build line, then anything skipped, the gaps, and the projects needing a look."""
    lines = [f"built {Path(result.get('db', DB)).name}: {result['entities']} entities, {result['claims']} claims, "
             f"{result['relations']} relations, {result['aliases']} aliases from {result['docs']} docs"
             + (f", {result['code_files']} code files" if result.get("code_files") else "")
             + (f" and {result['projects']} project{'' if result['projects'] == 1 else 's'}"
                if result.get("projects") else "")]
    lines += [f"  skipped edge in {doc_name}: {e['source']} --[{e['predicate']}]--> {e['target']} "
              "(unknown endpoint)" for doc_name, e in result["skipped"]]
    lines += [f"  gap: {w}" for w in result["warnings"]]
    lines += [f"  project: {w}" for w in result.get("checks", [])]
    return "\n".join(lines)


def main() -> None:
    args = sys.argv[1:]
    code = args[args.index("--code") + 1] if "--code" in args else None
    print(summary(build(code=code)))


if __name__ == "__main__":
    main()
