"""Query the graph: find the names in the question, score relevance, walk, rank.

Pure SQLite, no model call anywhere in this file. This is the code that runs
inside the prompt hook, so it has to be deterministic and fast.

    0. when      the dates the question is about: a day, month or year it
                 names, today when it names none, all dates for a history
                 question ("how has it changed")
    1. names     the question's word runs, looked up in an index
    2. relevance full-text search over every entity (FTS5, BM25): rare words
                 weigh more, so "March" outweighs "sign"
    3. walk      one indexed query per node, at most CAP links of each type,
                 the most relevant first, only links in force in that period
    4. rank      relevance, people and distance; every fact keeps its chain
                 back to a name in the question; claims in force are added
    5. sources   each claim in the documents' own words where the budget allows,
                 checked against the files as they are now, so the model has no
                 reason to go and read them; a changed or missing file is said
                 out loud instead of left for the model to discover
    6. projects  for a project the question names: its plan in one line (progress,
                 what is being done, what is next), and the whole plan, its
                 deliverables or its history when the question asks for them; a
                 question about projects that names none ("what is blocked?")
                 reads the projects table instead
    7. code      for code the question names: everything that depends on it
                 (callers, references, imports, the routes and buttons that reach
                 it) and everything it depends on, both ways whatever the
                 wording, followed to the end rather than for three hops; each
                 direct dependent's call site, and for a handler, the request
                 body each client sends and the fields it reads. No dependent is
                 left out for space; call sites are, first. A symbol nothing
                 reaches is said to be unreached

The whole call has a time budget. Past it, recall returns what it has and
says so, rather than being killed by the hook's timeout with nothing said.
"""
import os
import re
import sqlite3
import sys
import time
from collections import namedtuple
from contextlib import closing
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tokens  # noqa: E402  words, in prose and in code identifiers alike

ROOT = Path(__file__).resolve().parents[1]
DB = Path(os.environ.get("GRAPH_MEMORY_DB") or ROOT / "graph.db")

HOPS = 3         # how far from a named entity the walk goes
CAP = 3          # links followed per node, per link type and direction
TOP_K = 8        # facts in the injection
BUDGET_MS = 500  # past this, stop and say so
MAX_TERMS = 32   # question words scored for relevance; a pasted file needs no more
EXCERPT_BUDGET = 2000  # characters of source quotes per prompt: about 700 tokens on Sonnet 5
MAX_EXCERPTS = 8       # source quotes per prompt, like TOP_K facts
MAX_PROJECT_CARDS = 3  # projects shown in full for a question naming none, then a count
PLAN_LINES = 8         # steps shown when the question asks for the plan
EVENTS_SHOWN = 8       # history lines when the question asks what changed

# Words that ask for more than a project's one-line plan, or ask about projects at all.
PLAN_WORDS = {"plan", "plans", "step", "steps", "todo", "doing", "progress"}
DELIVERABLE_WORDS = {"deliverable", "deliverables", "deliver", "delivers", "delivered", "output", "outputs"}
EVENT_WORDS = {"changed", "change", "changes", "history", "happened", "updates", "updated",
               "latest", "recent", "recently", "since"}
PORTFOLIO_WORDS = {"project", "projects", "working"}
STATUS_WORDS = {"blocked": "blocked", "stuck": "blocked", "active": "active", "hold": "on_hold",
                "paused": "on_hold", "done": "done", "finished": "done", "completed": "done",
                "cancelled": "cancelled", "canceled": "cancelled", "proposed": "proposed",
                "planning": "planning"}
LATE_WORDS = {"overdue", "late", "behind"}

CODE_TYPES = ("FUNCTION", "COMPONENT", "TEST", "VARIABLE", "MODULE", "ROUTE", "ROUTE_CASE", "UI_ACTION")
LEADS = ("triggers", "calls", "requests", "handled_by", "dispatches_to", "reads", "references",
         "imports")  # source depends on target
BACK_ONLY = ("looks_up",)  # a handler looking up a table depends on it, but runs one entry, not all
PASSIVE = {"looks_up": "is looked up by", "calls": "is called by", "reads": "is read by", "references": "is referenced by",
           "imports": "is imported by", "requests": "is requested by", "handled_by": "handles",
           "dispatches_to": "is run by", "triggers": "is triggered by"}
TRACE_DEPTH = 8     # links followed from a named symbol, each way: a button to a constant is five or six
CODE_BUDGET = 6000  # characters of trace: no dependent is dropped for it; call sites and body lines are
FORWARD_WORDS = {"happens", "happen", "runs", "run", "calls", "call", "trace", "flow", "reach", "reaches",
                 "hit", "hits", "handles", "handle", "handled", "serves", "serve", "server", "backend",
                 "endpoint", "leads", "lead", "triggers", "trigger", "does", "do", "decide", "decides",
                 "sends", "send", "compare", "compares", "value", "hold", "holds"}
CHANGE_WORDS = {"change", "changes", "changing", "add", "adding", "remove", "removing", "rename", "renaming",
                "make", "require", "requires", "update", "modify", "delete", "drop", "replace", "refactor",
                "extend", "move", "split", "take", "accept", "argument", "arguments", "parameter",
                "parameters", "signature", "return", "returns", "field", "fields"}
IMPACT_WORDS = {"affect", "affects", "affected", "impact", "impacts", "break", "breaks", "change", "changes",
                "changing", "used", "uses", "use", "using", "references", "referenced", "depends", "depend",
                "callers", "caller", "who", "where", "still", "anywhere"}

STOPWORDS = {  # the RAG layer's list, rag/search.py
    "a", "an", "and", "are", "at", "can", "do", "does", "for", "how", "i",
    "in", "is", "it", "my", "of", "on", "or", "our", "the", "to", "we",
    "what", "when", "where", "who", "why", "with", "you", "your",
}

NO_GRAPH = "no graph yet: run python src/build_graph.py"
OLD_GRAPH = "graph.db is from an older version: run python src/build_graph.py"

RELEVANCE = """
SELECT entity_id, -bm25(entity_fts, 0.0, 2.0, 1.0)   -- a name counts double
FROM entity_fts WHERE entity_fts MATCH :terms
ORDER BY 2 DESC LIMIT 200
"""

IN_FORCE = "(valid_from IS NULL OR valid_from < :end) AND (valid_to IS NULL OR valid_to > :start)"

NEIGHBOURS = f"""
WITH links AS (
    SELECT rowid AS rid, source_id, predicate, target_id, source_doc,
           valid_from, valid_to, target_id AS other, 'out' AS dir
    FROM relations WHERE source_id = :node AND {IN_FORCE}
    UNION ALL
    SELECT rowid, source_id, predicate, target_id, source_doc,
           valid_from, valid_to, source_id, 'in'
    FROM relations WHERE target_id = :node AND {IN_FORCE}),
ranked AS (
    SELECT links.*, ROW_NUMBER() OVER (
               PARTITION BY predicate, dir
               ORDER BY COALESCE(rel.rel, 0) DESC, rid) AS rn
    FROM links LEFT JOIN temp.rel AS rel ON rel.entity_id = links.other)
SELECT r.rid, s.name, r.predicate, t.name, r.source_doc, r.valid_from, r.valid_to,
       r.source_id, r.target_id, s.type, t.type, r.other
FROM ranked r
JOIN entities s ON s.id = r.source_id
JOIN entities t ON t.id = r.target_id
WHERE r.rn <= :cap
"""

Link = namedtuple("Link", "source predicate target doc valid_from valid_to depth "
                          "source_id target_id types")
Fact = namedtuple("Fact", "source predicate target doc valid_from valid_to")


def words(text: str) -> list:
    """Lower-cased words. Names and questions are split the same way, identifiers
    too: needs_approval, needsApproval and "needs approval" are the same words
    (src/tokens.py)."""
    return tokens.words(text)


def plain(text: str) -> str:
    """Text as compared with a quote: no markdown emphasis, spacing collapsed, lower case."""
    return " ".join(re.sub(r"[*`]", "", text).split()).lower()


def excerpt_key(doc: str, quote: str) -> str:
    """How a source quote is remembered, so a conversation is not shown it twice."""
    return f"{doc}|{plain(quote)}"


# --- 0. when: the period a question is about ---------------------------------

MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July",
               "August", "September", "October", "November", "December"]
MONTHS = {m.lower(): i for i, m in enumerate(MONTH_NAMES, start=1)}
MONTHS.update({m[:3]: i for m, i in list(MONTHS.items())} | {"sept": 9})
MONTH = "(" + "|".join(sorted(MONTHS, key=len, reverse=True)) + r")\b"
PREP = r"\b(?:(since|after|from|before|until|till|in|during|for|of|on|by)\s+)"
DAY = r"(\d{1,2})(?:st|nd|rd|th)?"
HISTORY = re.compile(r"\b(history|changed?|changes|previous(?:ly)?|used to|over time|"
                     r"originally|over the years|all versions)\b")


@dataclass
class Period:
    start: str  # ISO date, inclusive
    end: str  # ISO date, exclusive
    label: str  # for the header: "as of 2026-09-23", "for March 2026", ...


EVER = Period("0000-01-01", "9999-12-31", "for all dates")


def today() -> date:
    """Today, or the date in GRAPH_MEMORY_TODAY (tests pin it, so dates never expire)."""
    pinned = os.environ.get("GRAPH_MEMORY_TODAY")
    return date.fromisoformat(pinned) if pinned else date.today()


def _next_month(d: date) -> date:
    return date(d.year + d.month // 12, d.month % 12 + 1, 1)


def _named_date(q: str, now: date):
    """The first date the question names: (start, end, label, preposition) or None."""
    patterns = [  # most specific first; a month without a year is this year's
        (PREP + r"?\b(\d{4})-(\d{2})-(\d{2})\b",
         lambda g: date(int(g[1]), int(g[2]), int(g[3])), "day"),
        (PREP + r"?\b" + DAY + r"\s+" + MONTH + r"\s+(\d{4})\b",
         lambda g: date(int(g[3]), MONTHS[g[2]], int(g[1])), "day"),
        (PREP + r"?\b" + MONTH + r"\s+" + DAY + r",?\s+(\d{4})\b",
         lambda g: date(int(g[3]), MONTHS[g[1]], int(g[2])), "day"),
        (PREP + r"?\b" + MONTH + r"\s+(\d{4})\b",
         lambda g: date(int(g[2]), MONTHS[g[1]], 1), "month"),
        (PREP + r"?\b" + DAY + r"\s+" + MONTH,
         lambda g: date(now.year, MONTHS[g[2]], int(g[1])), "day"),
        (PREP + MONTH,  # a bare month needs its preposition: "in March", not "may"
         lambda g: date(now.year, MONTHS[g[1]], 1), "month"),
        (PREP + r"((?:19|20)\d{2})\b",
         lambda g: date(int(g[1]), 1, 1), "year"),
    ]
    for pattern, make, unit in patterns:
        for m in re.finditer(pattern, q):
            groups = [m.group(0)] + list(m.groups()[1:])
            try:
                start = make(groups)
            except ValueError:  # "31 February"
                continue
            if unit == "day":
                end, label = start + timedelta(days=1), start.isoformat()
            elif unit == "month":
                end, label = _next_month(start), f"{MONTH_NAMES[start.month - 1]} {start.year}"
            else:
                end, label = date(start.year + 1, 1, 1), str(start.year)
            return start, end, label, m.group(1)
    for phrase, year in (("last year", now.year - 1), ("this year", now.year)):
        if phrase in q:
            return date(year, 1, 1), date(year + 1, 1, 1), str(year), None
    return None


def period(question: str, now: date = None) -> Period:
    """The dates a question is about. Facts outside them are left out."""
    now = now or today()
    q = question.lower()
    if HISTORY.search(q):
        return EVER
    named = _named_date(q, now)
    if not named:
        return Period(now.isoformat(), (now + timedelta(days=1)).isoformat(),
                      f"as of {now.isoformat()}")
    start, end, label, prep = named
    s, e = start.isoformat(), end.isoformat()
    if prep in ("since", "from"):
        return Period(s, EVER.end, f"since {label}")
    if prep == "after":
        return Period(e, EVER.end, f"after {label}")
    if prep == "before":
        return Period(EVER.start, s, f"before {label}")
    if prep in ("until", "till"):
        return Period(EVER.start, e, f"until {label}")
    return Period(s, e, f"for {label}")


def span(valid_from: str, valid_to: str) -> str:
    """When a dated fact holds, for people: the end date shown is the last day it holds."""
    if not valid_from and not valid_to:
        return ""
    last = (date.fromisoformat(valid_to) - timedelta(days=1)).isoformat() if valid_to else None
    if valid_from and last:
        return f" ({valid_from} to {last})"
    return f" (from {valid_from})" if valid_from else f" (until {last})"


@dataclass
class Facts:
    triples: list  # Fact(source, predicate, target, source_doc, valid_from, valid_to)
    notes: list  # (entity_name, claim_text, valid_from, valid_to), claims in force
    ms: float
    stopped: bool = False  # the time budget ran out
    problem: str = ""  # no usable graph
    when: Period = field(default=None)
    provenance: str = ""  # where the facts come from and when, and how to use them
    sources: list = field(default_factory=list)  # per note: None or (doc, quote, status)
    excerpts: list = field(default_factory=list)  # (source_doc, quote, "ok" | "changed" | "missing")
    excerpt_keys: list = field(default_factory=list)  # the quotes sent, for the hook to remember
    repeats: int = 0  # quotes not sent again: this conversation already has them
    kinds: list = field(default_factory=list)  # per note: its claim kind
    code: list = field(default_factory=list)  # trace lines for code the question names
    projects: list = field(default_factory=list)  # plan, portfolio and history lines
    project_count: int = 0  # projects those lines cover
    claim_ids: list = field(default_factory=list)  # per note: its row in claims, for callers that cite it

    def header(self) -> str:
        """The status line the user sees at submit, with the time it took."""
        if self.problem:
            return f"memory: {self.problem}"
        text = f"memory: {len(self.triples)} facts recalled in {self.ms:.1f} ms"
        if self.when:
            text += f", {self.when.label}"
        text += self._projects_part()
        if self.stopped:
            text += " (stopped at the time budget; facts may be incomplete)"
        return text

    def lead(self) -> str:
        """The injection's first line: the header without the timing the model has no use for."""
        text = f"memory: {len(self.triples)} facts" + (f", {self.when.label}" if self.when else "")
        text += self._projects_part()
        if self.stopped:
            text += " (stopped at the time budget; facts may be incomplete)"
        return text

    def _projects_part(self) -> str:
        n = self.project_count
        return f"; {n} project{'' if n == 1 else 's'}" if n else ""

    def as_text(self, pretty: bool = False) -> str:
        if self.problem:
            return self.header()
        head = self.header() if pretty else self.lead()
        if not self.triples and not self.projects and not self.code:
            return head + "\n(no memory matches for this prompt)"
        sources = self.sources or [None] * len(self.notes)
        if pretty:  # aligned, for people reading it
            width = max((len(f"{f.source} --[{f.predicate}]--> {f.target}") for f in self.triples), default=0)
            lines = [f"{f'{f.source} --[{f.predicate}]--> {f.target}':<{width}}   "
                     f"({f.doc}){span(f.valid_from, f.valid_to)}" for f in self.triples]
            gap, indent = "\n\n", "  "
        else:  # compact, for the model: no padding to pay tokens for
            lines = [f"{f.source} {f.predicate} {f.target} [{f.doc}]{span(f.valid_from, f.valid_to)}"
                     for f in self.triples]
            gap, indent = "\n", ""
        kinds = self.kinds or [None] * len(self.notes)
        notes = [indent + _note_line(n, t, vf, vt, src, kind)
                 for (n, t, vf, vt), src, kind in zip(self.notes, sources, kinds)]
        parts = [head + ("\n" + self.provenance if self.provenance else "")]
        if lines:
            parts.append("\n".join(lines))
        if notes:
            # The conditions live in claims on the entities, not the edges - carry them,
            # in the documents' own words where there is room.
            parts.append("where:\n" + "\n".join(notes))
        if self.projects:
            parts.append("projects:\n" + "\n".join(indent + line for line in self.projects))
        if self.code:
            parts.append("code:\n" + "\n".join(indent + line for line in self.code))
        return gap.join(parts)


def _note_line(name: str, text: str, valid_from: str, valid_to: str, source, kind=None) -> str:
    """One claim: its quote in place of the paraphrase when the quote is sent. A status
    keeps its words and dates first, and the quote after as the evidence: the value is
    the answer, the quote only why."""
    dates = span(valid_from, valid_to)
    if source is None:
        return f"{name}: {text}{dates}"
    doc, quote, status = source
    if status == "ok":
        if kind == "status":
            return f'{name}: {text}{dates}, on the words "{quote}" [{doc}]'
        return f'{name}: "{quote}" [{doc}]{dates}'
    if status == "earlier":
        return f"{name}: {text} [{doc}, quoted earlier]{dates}"
    if status == "changed":
        return f"{name}: {text} [{doc} changed since extraction: check it]{dates}"
    return f"{name}: {text} [{doc} is no longer in the documents folder]{dates}"


def _meta(db: sqlite3.Connection, key: str, default: int) -> int:
    row = db.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return int(row[0]) if row else default


def _meta_text(db: sqlite3.Connection, key: str, default: str = "") -> str:
    row = db.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row[0] if row else default


def _seeds(db: sqlite3.Connection, question: str) -> list:
    """An entity is named when a name or alias of it is a run of the question's words."""
    w = words(question)
    longest = _meta(db, "longest_name", 4)
    spans = {(i, k): " ".join(w[i:i + k]) for k in range(1, longest + 1) for i in range(len(w) - k + 1)}
    runs = sorted(set(spans.values()))
    hits = {}
    for i in range(0, len(runs), 500):  # a pasted file makes many runs
        batch = runs[i:i + 500]
        for norm, eid in db.execute(
                f"SELECT norm, entity_id FROM names WHERE norm IN ({','.join('?' * len(batch))})",  # noqa: S608
                batch):
            hits.setdefault(norm, set()).add(eid)
    code, code_spans = set(), []
    if _meta(db, "code_files", 0):  # two words in a row name code: "approval threshold", APPROVAL_THRESHOLD_GBP
        # a test is named after what it tests; it is a dependent, named in the trace, unless tests are asked about
        types = CODE_TYPES if {"test", "tests"} & set(w) else tuple(t for t in CODE_TYPES if t != "TEST")
        aliases = db.execute(
            "SELECT n.entity_id, n.norm FROM names n JOIN entities e ON e.id = n.entity_id "
            f"WHERE e.type IN ({','.join('?' * len(types))})", types).fetchall()
        for (i, k), run in spans.items():
            if k < 2:
                continue
            got = {eid for eid, norm in aliases if " " in norm and f" {run} " in f" {norm} "}
            if got:
                code |= got
                code_spans.append((i, i + k))
    if not _meta(db, "projects", 0) and not code_spans:
        return sorted(set().union(*hits.values()))
    # A project's or a symbol's name wins over the words inside it: "refunds dashboard" is the
    # project, not also the refund policy that "refunds" is an alias of; legacy_refund is the
    # function, not the policy either.
    projects = dict(db.execute("SELECT p.entity_id, e.name FROM projects p JOIN entities e ON e.id = p.entity_id")) \
        if _meta(db, "projects", 0) else {}
    covered = code_spans + [(i, i + k) for (i, k), run in spans.items() if hits.get(run, set()) & set(projects)]
    found = set()
    for (i, k), run in spans.items():
        if run in hits and not any(a <= i and i + k <= b and b - a > k for a, b in covered):
            found |= hits[run]
    # And a word of a project's title names it too: "the helpdesk contract" is the Helpdesk migration's.
    asked = {x for x in w if len(x) >= 4 and x not in STOPWORDS and x not in PORTFOLIO_WORDS}
    found |= {eid for eid, name in projects.items() if asked & set(words(name))}
    return sorted(found | code)


def _relevance(db: sqlite3.Connection, question: str, over) -> dict:
    """Entity id -> how much the question is about it, by full-text search."""
    db.execute("CREATE TEMP TABLE rel (entity_id TEXT PRIMARY KEY, rel REAL)")
    terms = [w for w in dict.fromkeys(words(question)) if w not in STOPWORDS][:MAX_TERMS]
    # A word on more than 5% of entities says nothing and costs the most: skip it.
    common = max(20, _meta(db, "entities", 0) // 20)
    kept = []
    for term in terms:
        if over():
            break
        n = db.execute(
            "SELECT COUNT(*) FROM (SELECT 1 FROM entity_fts WHERE entity_fts MATCH ? LIMIT ?)",
            (f'"{term}"', common + 1)).fetchone()[0]
        if n <= common:
            kept.append(term)
    if kept:
        db.execute("INSERT INTO temp.rel " + RELEVANCE,
                   {"terms": " OR ".join(f'"{t}"' for t in kept)})
    return dict(db.execute("SELECT entity_id, rel FROM temp.rel"))


def _walk(db: sqlite3.Connection, seeds: list, when: Period, hops: int, cap: int, over,
          skip: frozenset = frozenset()):
    """Breadth first from the named entities, one indexed query per node. Links to an
    entity of a type in skip are not followed."""
    depth = {s: 0 for s in seeds}
    via = {}  # entity -> the link that first reached it
    links = {}  # link rowid -> Link
    frontier = list(seeds)
    for d in range(hops):
        nxt = []
        for node in frontier:
            if over():
                return links, depth, via, True
            try:
                rows = db.execute(NEIGHBOURS, {"node": node, "cap": cap,
                                               "start": when.start, "end": when.end}).fetchall()
            except sqlite3.OperationalError as e:
                if "interrupt" in str(e):
                    return links, depth, via, True
                raise
            for rid, s, p, t, doc, vf, vt, sid, tid, stype, ttype, other in rows:
                if stype in skip or ttype in skip:
                    continue
                if rid not in links:
                    links[rid] = Link(s, p, t, doc, vf, vt, d, sid, tid, (stype, ttype))
                if other not in depth:
                    depth[other] = d + 1
                    via[other] = rid
                    nxt.append(other)
        frontier = nxt
    return links, depth, via, False


def _rank(links: dict, depth: dict, via: dict, rel: dict, top_k: int) -> list:
    """The top_k link ids: best score first, each with its chain to a named entity."""
    top = max(rel.values(), default=0.0) or 1.0

    def score(rid):
        link = links[rid]
        return (rel.get(link.source_id, 0.0) / top + rel.get(link.target_id, 0.0) / top
                + 0.5 * ("PERSON" in link.types) - 0.5 * link.depth)

    def nearer(link):
        s = depth.get(link.source_id, HOPS + 1)
        return link.source_id if s <= depth.get(link.target_id, HOPS + 1) else link.target_id

    def chain(rid):
        out, node = [rid], nearer(links[rid])
        while node in via and via[node] not in out:
            out.append(via[node])
            node = nearer(links[via[node]])
        return out

    chosen = []
    for rid in sorted(links, key=lambda r: (-score(r), links[r].depth, r)):
        for c in reversed(chain(rid)):  # the chain first, so no fact arrives without it
            if c not in chosen and len(chosen) < top_k:
                chosen.append(c)
        if len(chosen) >= top_k:
            break
    return sorted(chosen, key=lambda r: (links[r].depth, -score(r), r))


CLAIMS_NAMED = 4  # claims shown for an entity the question names
CLAIMS_OTHER = 2  # for any other entity the question is about
KIND_ORDER = {"status": -1, "threshold": 0, "value": 0.5, "availability": 1, "unknown": 2, "responsibility": 3,
              "deadline": 4, "decision": 4.5, "rule": 5, "note": 6}


def _claims(db: sqlite3.Connection, question: str, ids: set, seeds: set, near: set,
            rel: dict, when: Period) -> list:
    """Claims in force for the entities the question is about, best first.

    That is: what the question names, what is one link from it (the role a
    person holds), and what full-text search found relevant. An entity in the
    facts only because the walk passed through it brings no claims.
    Rows: (entity_id, name, kind, text, valid_from, valid_to, id, quote, source_doc).
    """
    about = sorted(i for i in ids if i in seeds or i in near or rel.get(i, 0) > 0)
    if not about:
        return []
    rows = db.execute(
        f"SELECT e.id, e.name, c.kind, c.text, c.valid_from, c.valid_to, c.id, "  # noqa: S608
        f"c.quote, c.source_doc FROM claims c JOIN entities e ON e.id = c.entity_id "
        f"WHERE c.entity_id IN ({','.join('?' * len(about))}) "
        f"AND (c.valid_from IS NULL OR c.valid_from < ?) "
        f"AND (c.valid_to IS NULL OR c.valid_to > ?)",
        (*about, when.end, when.start)).fetchall()
    asked = {w.rstrip("s") for w in words(question) if w not in STOPWORDS}

    def best(row):
        shares = bool(asked & {w.rstrip("s") for w in words(row[3])})
        return (not shares, KIND_ORDER.get(row[2], 9), row[6])

    kept, count = [], {}
    for row in sorted(rows, key=best):
        limit = CLAIMS_NAMED if row[0] in seeds else CLAIMS_OTHER
        if count.get(row[0], 0) < limit:
            count[row[0]] = count.get(row[0], 0) + 1
            kept.append(row)
    return kept


def _excerpts(ranked: list, root: Path, sent, records_root: Path = None, code_root: Path = None) -> tuple:
    """The source quotes behind the claims shown, best claim first, checked against the files now.

    Returns ({claim id: (doc, quote, status)}, excerpts sent, their keys, how many
    were not sent again). Status: ok, changed, missing, or earlier (already sent in
    this conversation). An unknown claim keeps its own words: the quote shows what
    the document says, not what it leaves open.
    """
    by_claim, out, keys, seen, texts, used, repeats = {}, [], [], set(), {}, 0, 0
    for row in ranked:
        kind, cid, quote, doc = row[2], row[6], row[7], row[8]
        if not quote or kind == "unknown":
            continue
        key = excerpt_key(doc, quote)
        if key in seen:  # one quote can back several claims: show it once
            continue
        seen.add(key)
        if key in sent:
            by_claim[cid] = (doc, quote, "earlier")
            repeats += 1
            continue
        size = len(doc) + len(quote) + 6
        if len(out) >= MAX_EXCERPTS or used + size > EXCERPT_BUDGET:
            continue  # over budget: this claim keeps its paraphrase
        if doc not in texts:
            path = root / doc
            if not path.is_file() and records_root is not None:  # a project's input
                path = records_root / doc
            if not path.is_file() and code_root is not None:  # a code file
                path = code_root / doc
            texts[doc] = plain(path.read_text(encoding="utf-8")) if path.is_file() else None
        status = ("missing" if texts[doc] is None
                  else "ok" if plain(quote) in texts[doc] else "changed")
        by_claim[cid] = (doc, quote, status)
        out.append((doc, quote, status))
        keys.append(key)
        used += size
    return by_claim, out, keys, repeats


def _late(due, status, now_iso, finished=("done", "skipped")) -> str:
    return f", overdue since {due}" if due and due < now_iso and status not in finished else ""


def _step_text(n, title, status, due, owner, now_iso) -> str:
    who = ", ".join(x for x in (owner, due and f"due {due}") if x)
    return f"step {n}, {title}" + (f" ({who})" if who else "") + _late(due, status, now_iso)


def _steps(db: sqlite3.Connection, pid: str) -> tuple:
    """A project's steps, (id, n, title, status, due, owner), and {step id: [n it waits on]}."""
    rows = db.execute("SELECT s.id, s.n, s.title, s.status, s.due, o.name FROM steps s "
                      "LEFT JOIN entities o ON o.id = s.owner_id WHERE s.project_id = ? ORDER BY s.n",
                      (pid,)).fetchall()
    after = {}
    for sid, n in db.execute("SELECT a.step_id, b.n FROM step_after a JOIN steps b ON b.id = a.after_id "
                             "WHERE b.project_id = ? ORDER BY b.n", (pid,)):
        after.setdefault(sid, []).append(n)
    return rows, after


def _doing_and_next(title, steps, after, now_iso) -> list:
    """The steps under way or stuck, and the first one ready to start."""
    out = [f"{title}: {st}: {_step_text(n, t, st, due, owner, now_iso)}"
           for _, n, t, st, due, owner in steps if st in ("doing", "blocked")]
    finished = {n for _, n, _, st, _, _ in steps if st in ("done", "skipped")}
    for sid, n, t, st, due, owner in steps:
        if st == "todo" and all(a in finished for a in after.get(sid, [])):
            waits = after.get(sid)
            out.append(f"{title}: next: {_step_text(n, t, st, due, owner, now_iso)}"
                       + (f", after step {', '.join(map(str, waits))}" if waits else ""))
            break
    return out


EVENT_TEXT = {
    "create_project": lambda s, o, n: "created",
    "set_status": lambda s, o, n: f"status {o} → {n}" if o else f"status {n}",
    "set_step": lambda s, o, n: f"{s} {o} → {n}" if n else f"{s} due date changed",
    "set_deliverable": lambda s, o, n: f"{s} {o} → {n}",
    "set_field": lambda s, o, n: f"{s} {o} → {n}" if o else f"{s} set to {n}",
    "add_dependency": lambda s, o, n: f"dependency added: {n}",
    "add_deliverable": lambda s, o, n: f"deliverable {s} added: {n}",
    "add_question": lambda s, o, n: f"question {s}: {n}",
    "close_question": lambda s, o, n: f"{s} answered: {o}",
    "add_decision": lambda s, o, n: f"decided: {n}",
    "agree_plan": lambda s, o, n: f"plan agreed: {n}",
    "set_thesis": lambda s, o, n: f"thesis {o} → {n}" if o else f"thesis set: {n}",
    "set_number": lambda s, o, n: f"number {s}: {o} → {n}" if o else f"number {s}: {n}",
    "set_effort": lambda s, o, n: f"estimated effort {o} → {n}" if o else f"estimated effort: {n}",
}


def _project_lines(db: sqlite3.Connection, pids: list, asked: set, when: Period, now: date) -> list:
    """For projects the question names: the plan in a line, and more when asked for.

    Steps and deliverables are as they are now, so they are shown only when the
    question's period includes today; the history is shown for its period.
    """
    now_iso, out = now.isoformat(), []
    current = when.start <= now_iso < when.end
    for pid in pids:
        row = db.execute("SELECT e.name, p.status, p.plan_state, p.plan_version, p.plan_agreed_on, p.due "
                         "FROM projects p JOIN entities e ON e.id = p.entity_id WHERE p.entity_id = ?",
                         (pid,)).fetchone()
        if row is None:
            continue
        title, status, plan_state, version, agreed_on, due = row
        if current:
            steps, after = _steps(db, pid)
            if plan_state == "agreed":
                done = sum(1 for st in steps if st[3] in ("done", "skipped"))
                out.append(f"{title}: plan v{version} agreed {agreed_on}; {done} of {len(steps)} steps done"
                           + (f"; due {due}" + _late(due, status, now_iso, ("done", "cancelled")) if due else ""))
                if asked & PLAN_WORDS:
                    out += [f"{title}: {st}: {_step_text(n, t, st, d, o, now_iso)}"
                            for _, n, t, st, d, o in steps[:PLAN_LINES]]
                    if len(steps) > PLAN_LINES:
                        out.append(f"{title}: and {len(steps) - PLAN_LINES} more steps")
                else:
                    out += _doing_and_next(title, steps, after, now_iso)
            elif status in ("proposed", "planning", "active"):
                out.append(f"{title}: no agreed plan yet")
            if asked & DELIVERABLE_WORDS:
                for key, d_title, st, d_due, owner in db.execute(
                        "SELECT d.key, d.title, d.status, d.due, o.name FROM deliverables d "
                        "LEFT JOIN entities o ON o.id = d.owner_id WHERE d.project_id = ? ORDER BY d.key", (pid,)):
                    who = ", ".join(x for x in (owner, d_due and f"due {d_due}") if x)
                    out.append(f"{title}: {key} {d_title}: {st.replace('_', ' ')}" + (f" ({who})" if who else "")
                               + _late(d_due, st, now_iso, ("delivered", "accepted", "dropped")))
        if asked & EVENT_WORDS or when is EVER:
            for on, op, subject, old, new in db.execute(
                    "SELECT on_date, op, subject, old, new FROM events WHERE project_id = ? AND on_date >= ? "
                    "AND on_date < ? ORDER BY on_date DESC, id DESC LIMIT ?",
                    (pid, when.start, when.end, EVENTS_SHOWN)):
                text = EVENT_TEXT.get(op, lambda s_, o_, n_: f"{op} {s_ or ''} {n_ or ''}".strip())(subject, old, new)
                out.append(f"{title}: {on} {text}")
    return out


def _portfolio(db: sqlite3.Connection, asked: set, seeds: list, now: date) -> tuple:
    """For a question about projects that names none: those it asks about, by status,
    lateness or person. Returns (lines, the projects shown)."""
    now_iso = now.isoformat()
    wanted = {STATUS_WORDS[w] for w in asked if w in STATUS_WORDS}
    late = bool(asked & LATE_WORDS)
    people = [(eid, name) for eid, name, kind in db.execute(
        f"SELECT id, name, type FROM entities WHERE id IN ({','.join('?' * len(seeds))})", seeds)  # noqa: S608
        if kind == "PERSON"] if seeds else []

    def overdue(pid, status, due):
        if status in ("done", "cancelled"):
            return False
        return bool((due and due < now_iso) or db.execute(
            "SELECT 1 FROM steps WHERE project_id = ? AND due < ? AND status NOT IN ('done', 'skipped') "
            "UNION SELECT 1 FROM deliverables WHERE project_id = ? AND due < ? "
            "AND status NOT IN ('delivered', 'accepted', 'dropped')", (pid, now_iso, pid, now_iso)).fetchone())

    def involves(pid, person):
        return bool(db.execute(
            "SELECT 1 FROM relations WHERE source_id = ? AND target_id = ? AND predicate IN ('owned_by', "
            "'requested_by') UNION SELECT 1 FROM steps WHERE project_id = ? AND owner_id = ? "
            "UNION SELECT 1 FROM deliverables WHERE project_id = ? AND owner_id = ?",
            (pid, person, pid, person, pid, person)).fetchone())

    rows = db.execute("SELECT p.entity_id, e.name, p.status, p.status_from, p.plan_state, o.name, p.due "
                      "FROM projects p JOIN entities e ON e.id = p.entity_id "
                      "LEFT JOIN entities o ON o.id = p.owner_id ORDER BY e.name").fetchall()
    picked = [r for r in rows if (not wanted or r[2] in wanted) and (not late or overdue(r[0], r[2], r[6]))
              and all(involves(r[0], person) for person, _ in people)]
    what = " and ".join(filter(None, [" or ".join(sorted(w.replace("_", " ") for w in wanted)),
                                      "overdue" if late else ""]))
    who = f" involving {' and '.join(name for _, name in people)}" if people else ""
    if not picked:
        return [f"no {what + ' ' if what else ''}projects{who}, as of {now_iso}"], []
    out = [f"{len(picked)} {what + ' ' if what else ''}project{'' if len(picked) == 1 else 's'}{who}, "
           f"as of {now_iso}:"]
    for pid, title, status, since, plan_state, owner, due in picked[:MAX_PROJECT_CARDS]:
        line = f"{title}: {status.replace('_', ' ')} since {since}; owner {owner or 'not named'}"
        steps, after = _steps(db, pid)
        if plan_state == "agreed":
            done = sum(1 for st in steps if st[3] in ("done", "skipped"))
            line += f"; {done} of {len(steps)} steps done"
        if due:
            line += f"; due {due}" + _late(due, status, now_iso, ("done", "cancelled"))
        out.append(line)
        out += _doing_and_next(title, steps, after, now_iso) if plan_state == "agreed" else []
        for person, name in people:  # what the person has on it
            theirs = [f"step {n} {st}" for _, n, _, st, _, o in steps if o == name]
            if theirs:
                out.append(f"{title}: {name}: {', '.join(theirs)}")
    if len(picked) > MAX_PROJECT_CARDS:
        out.append(f"and {len(picked) - MAX_PROJECT_CARDS} more: "
                   + ", ".join(r[1] for r in picked[MAX_PROJECT_CARDS:]))
    return out, [r[0] for r in picked[:MAX_PROJECT_CARDS]]


def _trace(db: sqlite3.Connection, start: str, forward: bool) -> list:
    """The links from start, forward (what it depends on) or back (what depends on it), breadth
    first, TRACE_DEPTH deep: (source name, predicate, target name, target id, other id), nearest first."""
    col = "source_id" if forward else "target_id"
    preds = LEADS if forward else LEADS + BACK_ONLY
    edges, seen, frontier = [], {start}, [start]
    for _ in range(TRACE_DEPTH):
        nxt = []
        for node in frontier:
            for sid, sname, pred, tid, tname in db.execute(
                    "SELECT r.source_id, s.name, r.predicate, r.target_id, t.name FROM relations r "
                    "JOIN entities s ON s.id = r.source_id JOIN entities t ON t.id = r.target_id "
                    f"WHERE r.{col} = ? AND r.predicate IN ({','.join('?' * len(preds))}) ORDER BY r.rowid",
                    (node, *preds)):
                other = tid if forward else sid
                if (sname, pred, tname) not in {(e[0], e[1], e[2]) for e in edges}:
                    edges.append((sname, pred, tname, tid, other))
                if other not in seen:
                    seen.add(other)
                    nxt.append(other)
        frontier = nxt
    return edges


def _code_lines(db: sqlite3.Connection, seeds: list, asked: set, code_root: Path = None,
                question: str = "") -> list:
    """For code the question names: what depends on it and what it depends on, both ways.

    A change to a function's arguments reaches every caller, every reference and
    import, and on back through routes to the buttons; the walk's facts stop
    three hops out. These follow the links to the end and name every dependent,
    grouped by link, then list where each direct dependent uses the symbol, and
    for a handler, what each client sends in the body and what it reads.
    """
    rows = db.execute(f"SELECT id, name FROM entities WHERE id IN ({','.join('?' * len(seeds))}) "  # noqa: S608
                      f"AND type IN ({','.join('?' * len(CODE_TYPES))}) ORDER BY name", (*seeds, *CODE_TYPES)).fetchall()
    if not rows:
        return []
    # the one written as it is in the code goes first: "cancelOrder" is frontend.api.cancelOrder before
    # the backend's cancel_order and the 'Cancel order' button, which the same two words also name
    rows.sort(key=lambda r: (not re.search(rf"(?<![\w.]){re.escape(r[1].rsplit('.', 1)[-1])}(?!\w)", question),
                             r[1]))
    forward_first = bool(asked & FORWARD_WORDS) and not asked & (CHANGE_WORDS | IMPACT_WORDS)
    values = {eid: (value, resolved) for eid, value, resolved in db.execute(
        "SELECT entity_id, value, resolved FROM code_symbols WHERE value IS NOT NULL")}
    texts = {}

    def shown(name, eid):
        if eid not in values:
            return name
        value, resolved = values[eid]
        extra = f', which is "{resolved}"' if resolved is not None and resolved != value.strip("\"'") else ""
        return f"{name} (= {value}{extra})"

    def fresh(file, quote):
        if code_root is None:
            return ""
        if file not in texts:
            path = code_root / file
            texts[file] = plain(path.read_text(encoding="utf-8")) if path.is_file() else None
        if texts[file] is None:
            return f" [{file} is no longer there]"
        return "" if plain(quote) in texts[file] else " [this line has changed since indexing: check it]"

    out, groups_shown = [], {}  # out: (line, droppable); groups_shown: (node, predicate, way) -> whose block

    def names_block(eid, name, forward):
        edges = _trace(db, eid, forward)
        groups = {}
        for sname, pred, tname, tid, other in edges:
            key = (sname, pred) if forward else (tname, pred)
            groups.setdefault(key, []).append((tname, tid) if forward else (sname, other))
        lines, earlier = [], []
        for (node, pred), others in groups.items():
            if (node, pred, forward) in groups_shown:
                earlier.append(groups_shown[(node, pred, forward)])
                continue
            groups_shown[(node, pred, forward)] = name
            listed = ", ".join(shown(n, i) for n, i in dict.fromkeys(others))
            lines.append(f"{node} {pred} {listed}" if forward else f"{node} {PASSIVE[pred]} {listed}")
        head = f"{name}, {'what it depends on' if forward else 'what depends on it'}:"
        if earlier:  # links another named symbol shares are listed once, under it
            head += f" (with the links listed above under {', '.join(dict.fromkeys(earlier))})"
        if edges:
            out.append((head, False))
            out.extend((line, False) for line in lines)
        return edges

    def sites_block(eid):
        sites = db.execute(
            "SELECT s.name, c.predicate, c.file, c.line, c.quote FROM call_sites c JOIN entities s ON s.id = c.source_id "
            "WHERE c.target_id = ? AND c.predicate != 'reads_body' ORDER BY c.file, c.line", (eid,)).fetchall()
        if sites:
            out.append((f"{name}, where each use is:", True))
            out.extend((f"  {f}:{ln}, {src} {pred} it: {q}{fresh(f, q)}", True) for src, pred, f, ln, q in sites)

    def contract_block(eid, name):
        routes = [r for (r,) in db.execute(
            "SELECT r.source_id FROM relations r JOIN entities e ON e.id = r.source_id WHERE r.target_id = ? "
            "AND r.predicate = 'handled_by' AND e.type IN ('ROUTE', 'ROUTE_CASE')", (eid,))]
        routes += [r for (r,) in db.execute("SELECT id FROM entities WHERE id = ? AND type IN ('ROUTE', 'ROUTE_CASE')",
                                            (eid,))]
        lines = []
        for route in routes:
            for src, f, ln, q, detail in db.execute(
                    "SELECT s.name, c.file, c.line, c.quote, c.detail FROM call_sites c JOIN entities s "
                    "ON s.id = c.source_id WHERE c.target_id = ? AND c.predicate = 'requests' ORDER BY c.file, c.line",
                    (route,)):
                what = f"sends {detail}" if detail else "requests it"  # no literal body: the quote shows it
                lines.append(f"  {f}:{ln}, {src} {what}: {q}{fresh(f, q)}")
            for src, f, ln, q, detail in db.execute(
                    "SELECT s.name, c.file, c.line, c.quote, c.detail FROM call_sites c JOIN entities s "
                    "ON s.id = c.source_id WHERE c.target_id = ? AND c.predicate = 'reads_body' ORDER BY c.line",
                    (route,)):
                lines.append(f"  {f}:{ln}, {src} reads {detail}: {q}{fresh(f, q)}")
        if lines:
            out.append((f"{name}, the request: what each client sends, and what the handler reads:", True))
            out.extend((line, True) for line in dict.fromkeys(lines))

    for eid, name in rows:
        for forward in ((True, False) if forward_first else (False, True)):
            edges = names_block(eid, name, forward)
            if not forward:
                if not edges:
                    out.append((f"{name}: nothing in the code calls, reads, references, imports, requests or "
                                "triggers it", False))
                sites_block(eid)
                contract_block(eid, name)
    kept = sum(len(line) for line, drop in out if not drop)
    lines, dropped = [], 0
    for line, drop in out:
        if drop and kept + len(line) > CODE_BUDGET:
            dropped += line.startswith("  ")
            continue
        kept += len(line) if drop else 0
        lines.append(line)
    heads = {line for line, drop in out if drop and not line.startswith("  ")}
    lines = [line for i, line in enumerate(lines)  # a heading whose lines all went goes too
             if line not in heads or (i + 1 < len(lines) and lines[i + 1].startswith("  "))]
    if dropped:
        lines.append(f"({dropped} call-site lines left out for space; every dependent is named above)")
    return list(dict.fromkeys(lines))


def recall(question: str, hops: int = HOPS, top_k: int = TOP_K,
           cap: int = CAP, budget_ms: float = BUDGET_MS, now: date = None,
           sent: frozenset = frozenset(), db: Path = None) -> Facts:
    """The facts for a question. `sent`: source quotes this conversation already has.
    `db`: the graph to read, when not the module's DB (a service holds one per workspace)."""
    t0 = time.perf_counter()
    graph = Path(db) if db is not None else Path(DB)
    now = now or today()
    when = period(question, now)

    def elapsed():
        return (time.perf_counter() - t0) * 1000

    def over():
        return elapsed() > budget_ms

    if not graph.is_file():
        return Facts([], [], elapsed(), problem=NO_GRAPH)
    with closing(sqlite3.connect(graph)) as db:
        # The budget holds inside a long query too: SQLite asks every 1,000 steps.
        db.set_progress_handler(over, 1000)
        try:
            seeds = _seeds(db, question)
            asked = set(words(question))
            has_projects = _meta(db, "projects", 0) > 0
            named_projects = [r[0] for r in db.execute(
                f"SELECT entity_id FROM projects WHERE entity_id IN ({','.join('?' * len(seeds))})",  # noqa: S608
                seeds)] if has_projects and seeds else []
            about_projects = has_projects and not named_projects and bool(
                asked & PORTFOLIO_WORDS or (not seeds and asked & (set(STATUS_WORDS) | LATE_WORDS)))
            if not seeds and not about_projects:
                return Facts([], [], elapsed(), when=when)
            project_lines, shown_projects = _portfolio(db, asked, seeds, now) if about_projects else ([], [])
            code_lines, code_root = [], ""
            links, depth, via, stopped, chosen, ranked, rel = {}, {}, {}, False, [], [], {}
            if seeds:
                rel = _relevance(db, question, over)
                # deliverables only when asked for: otherwise they crowd out the rest
                skip = frozenset({"MODULE"} | (set() if asked & DELIVERABLE_WORDS else {"DELIVERABLE"}))
                links, depth, via, stopped = _walk(db, seeds, when, hops, cap, over, skip)
                db.set_progress_handler(None, 1000)
                chosen = _rank(links, depth, via, rel, top_k)
                named_code = [r[0] for r in db.execute(
                    f"SELECT id FROM entities WHERE id IN ({','.join('?' * len(seeds))}) "  # noqa: S608
                    f"AND type IN ({','.join('?' * len(CODE_TYPES))})", (*seeds, *CODE_TYPES))]
                ids = {i for r in chosen for i in (links[r].source_id, links[r].target_id)} | set(named_projects) \
                    | set(named_code)
                near = {e for e, d in depth.items() if d == 1}
                ranked = _claims(db, question, ids, set(seeds), near, rel, when)
            db.set_progress_handler(None, 1000)
            project_lines += _project_lines(db, named_projects, asked, when, now)
            code_root = _meta_text(db, "code_root", "")
            croot = (Path(code_root) if Path(code_root).is_absolute() else ROOT / code_root) if code_root else None
            code_lines = _code_lines(db, seeds, asked, croot, question) if seeds and _meta(db, "code_files", 0) \
                else []
            where = (os.environ.get("GRAPH_MEMORY_DOCS") if graph == Path(DB) else None) \
                or _meta_text(db, "docs_root", "corpus")
            records_root = _meta_text(db, "records_root", "")
            records = (f" and project records ({_meta_text(db, 'projects')}, updated "
                       f"{_meta_text(db, 'projects_updated', '?')})"
                       if has_projects and (project_lines or named_projects) else "")
            if code_lines:
                records += (f"{' and' if not records else ','} your code ({_meta_text(db, 'code_files')} files, "
                            f"indexed {_meta_text(db, 'code_indexed', '?')})")
            # No folder named: a folder the model cannot find sends it looking.
            provenance = (f"These facts come from your documents ({_meta_text(db, 'docs', '?')}, "
                          f"extracted {_meta_text(db, 'extracted', '?')}){records}. Quoted lines are the "
                          f"{'sources' if records else 'documents'}' own words, checked against the files "
                          "just now: answer from them, and open a file only if its line says it changed or "
                          "is missing.")
        except sqlite3.OperationalError as e:
            if "no such table" in str(e) or "no such column" in str(e):
                return Facts([], [], elapsed(), problem=OLD_GRAPH)
            if "interrupt" in str(e):
                return Facts([], [], elapsed(), stopped=True, when=when)
            raise
    triples = [Fact(links[r].source, links[r].predicate, links[r].target, links[r].doc,
                    links[r].valid_from, links[r].valid_to) for r in chosen]
    root = Path(where) if Path(where).is_absolute() else ROOT / where
    rroot = (Path(records_root) if Path(records_root).is_absolute() else ROOT / records_root) \
        if records_root else None
    croot = (Path(code_root) if Path(code_root).is_absolute() else ROOT / code_root) if code_root else None
    by_claim, excerpts, keys, repeats = (_excerpts(ranked, root, sent, rroot, croot)
                                         if triples or named_projects or code_lines else ({}, [], [], 0))
    shown = sorted(ranked, key=lambda r: (r[1], r[4] or "", r[6]))
    notes = [(name, text, vf, vt) for _, name, _, text, vf, vt, _, _, _ in shown]
    sources = [by_claim.get(r[6]) for r in shown]
    return Facts(triples, notes, elapsed(), stopped, when=when, provenance=provenance,
                 sources=sources, excerpts=excerpts, excerpt_keys=keys, repeats=repeats,
                 kinds=[r[2] for r in shown], projects=project_lines, code=code_lines,
                 project_count=len(set(named_projects) | set(shown_projects)), claim_ids=[r[6] for r in shown])


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles default to cp1252
    args = sys.argv[1:]
    pretty = "--pretty" in args
    question = " ".join(a for a in args if a != "--pretty") or "what do we know?"
    print(recall(question).as_text(pretty=pretty))
