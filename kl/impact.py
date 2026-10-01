"""A project's thesis, the research behind its numbers, and the priorities they give.

A thesis says: if <change>, <outcome> will <fall | rise | improve> by potentially
<amount> <unit>. The amount is the product of the thesis's numbers (projects/impact.py),
and the numbers are gathered, not guessed:

1. found: the research step looks in the workspace's graph for a fact that has every
   word of the number's label and states one figure. It is recorded with the
   document and the sentence it came from.
2. asked: a number no document holds is asked of a person: the one the number
   names, or else the project's owner, or whoever asked for it. The question goes
   out (event number.asked) when a person approves the research.
3. answered or estimated: the person replies (POST .../numbers/{key}); an estimate
   stays marked as one.

Until every number is in, the amount reads "still being researched" and the project
is not ranked. Priority is projected impact per person-day of estimated effort,
ranked within each unit, or across units in money when the workspace gives a value
per unit (settings.unit_values, e.g. {"hours a year": 45}).

Every write here opens a change request, like any other edit: nothing is recorded
until a person approves it.
"""
import re
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

import sqlalchemy as sa

from . import db as t
from . import errors

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "projects"))
import impact  # noqa: E402  projects/impact.py: the thesis and what its numbers come to
import model  # noqa: E402
sys.path.insert(0, str(ROOT / "src"))
from recall import plain  # noqa: E402

RESEARCHER = ("service", "impact-research", "impact research")  # the proposer of research change requests
STOP = {"a", "an", "the", "per", "of", "in", "on", "to", "for", "and", "by", "each", "every", "over", "past",
        "last", "this", "that", "with", "is", "are", "has", "have", "at", "from", "about"}
FACTS_SHOWN = 60  # facts with figures given to whoever drafts a thesis
OPEN = ("proposed", "planning", "active", "blocked", "on_hold")  # the projects priorities are about


def stems(text: str) -> set:
    """Words by their first four letters, so "failures" meets "failed" and "clients" meets "client"."""
    return {w[:4] for w in re.findall(r"[a-z]+", str(text).lower()) if w not in STOP and len(w) > 1}


def digit_figures(quote: str) -> list:
    """The figures a sentence writes in digits, years left out."""
    out = []
    for m in impact.FIGURE.finditer(quote):
        raw = m.group(1)
        if len(raw) == 4 and "," not in raw and 1900 <= int(raw) <= 2100 and not m.group(2):
            continue
        out.append(float(raw.replace(",", "") + (m.group(2) or "")))
    return out


def tidy(x):
    return int(x) if float(x).is_integer() else float(x)


class ImpactMixin:

    # ---- reading the graph ---------------------------------------------------------------------

    def _doc_reader(self, ws, extra: dict = None):
        """A function from a snapshot path (docs/..., inputs/...) to its text, or None. extra: {path: text} read
        first. With graph updates deferred the snapshot may not hold a source that arrived since it was built
        (the input being turned into a project), so a path it lacks is read from the source's current version."""
        _, _, snap = self._graph_now(ws)
        base = Path(snap).resolve()
        extra = extra or {}

        def read(path):
            if str(path) in extra:
                return extra[str(path)]
            target = (base / str(path)).resolve()
            if base in target.parents and target.is_file():
                return target.read_text(encoding="utf-8")
            return self._source_text(ws, str(path))
        return read

    def _source_text(self, ws, path: str):
        """docs/<path> or inputs/<path> read from the source's current version, or None."""
        head, _, rest = path.partition("/")
        kinds = {"docs": ("document",), "inputs": ("transcript", "request", "session")}.get(head)
        if not kinds or not rest:
            return None
        with self.db.tx(ws) as c:
            row = c.execute(sa.select(t.source_versions.c.blob_key).select_from(
                t.documents.join(t.source_versions, t.source_versions.c.id == t.documents.c.current_version_id))
                .where(t.documents.c.workspace_id == ws, t.documents.c.path == rest, t.documents.c.kind.in_(kinds),
                       t.documents.c.deleted_at.is_(None))).first()
        return self.blobs.get(row[0]).decode("utf-8") if row else None

    def _number_facts(self, ws) -> list:
        """Every fact in the graph's documents that states a figure: (source, quote, text, amount, unit)."""
        graph, _, snap = self._graph_now(ws)
        today = self.clock.today().isoformat()
        with closing(sqlite3.connect(f"file:{graph}?mode=ro", uri=True)) as db:
            rows = db.execute(
                "SELECT c.source_doc, c.quote, c.text, c.amount, c.unit FROM claims c JOIN entities e "
                "ON e.id = c.entity_id WHERE e.type NOT IN ('PROJECT', 'DELIVERABLE') AND c.quote IS NOT NULL "
                "AND (c.valid_from IS NULL OR c.valid_from <= ?) AND (c.valid_to IS NULL OR c.valid_to > ?) "
                "ORDER BY c.source_doc, c.id", (today, today)).fetchall()
        out = []
        for src, quote, text, amount, unit in rows:
            if not (Path(snap) / "docs" / src).is_file():
                continue  # a document's facts only: not a project's, not code's
            if amount is not None or digit_figures(quote):
                out.append((f"docs/{src}", quote, text or "", amount, unit or ""))
        return out

    def _find(self, facts, number) -> tuple:
        """(found or None, note): the fact that states this number, if the graph agrees on one."""
        want = stems(number["label"])
        hits = []
        for src, quote, text, amount, unit in facts:
            if not want or not want <= stems(f"{quote} {text} {unit}"):
                continue
            if amount is not None and impact.mentions(amount, quote):
                value = float(amount)
            else:
                figs = set(digit_figures(quote))
                value = figs.pop() if len(figs) == 1 else None
            if value is not None:
                hits.append({"source": src, "quote": quote, "value": tidy(value)})
        values = sorted({h["value"] for h in hits})
        if len(values) == 1:
            return hits[0], f"found in {hits[0]['source']} (“{hits[0]['quote']}”)"
        if len(values) > 1:
            said = "; ".join(f"{impact.fmt(h['value'])} in {h['source']}" for h in hits)
            return None, f"the documents disagree ({said})"
        return None, "not in the graph"

    # ---- research ------------------------------------------------------------------------------

    def _who_to_ask(self, rec, number, names) -> str:
        for who in (number.get("ask"), (rec.get("owner") or {}).get("entity"),
                    (rec.get("requested_by") or {}).get("entity")):
            if who and plain(who) in names:
                return names[plain(who)]
        return None

    def _research_ops(self, ws, rec, numbers, names) -> tuple:
        """(operations, notes) for the numbers not yet known: found in the graph, or asked of a person."""
        facts = self._number_facts(ws)
        have = impact.numbers_of(rec)
        ops, notes = [], []
        for n in numbers:
            old = have.get(n["key"])
            if old and old["status"] in impact.KNOWN:
                continue
            new = {} if old else {"label": n["label"], "unit": n["unit"]}
            base = {"op": "set_number", "project": rec["id"], "key": n["key"], **new}
            hit, note = self._find(facts, n)
            if hit:
                notes.append(f"{n['key']}: {note}")
                ops.append({**base, "status": "found", "value": hit["value"],
                            "found_in": {"source": hit["source"], "quote": hit["quote"]}})
                continue
            who = self._who_to_ask(rec, n, names)
            question = n.get("question") or (old or {}).get("question") or \
                f"For {rec['title']}: what is the number of {n['label']}, in {n['unit']}?"
            if who and not (old and old["status"] == "asked" and old.get("ask") == who):
                ops.append({**base, "status": "asked", "ask": who, "question": question})
                notes.append(f"{n['key']}: {note}, so asked {who}")
            elif not who and not old:
                ops.append({**base, "status": "needed", "question": question})
                notes.append(f"{n['key']}: {note}, and no one to ask: name someone (ask) or answer it")
            else:
                notes.append(f"{n['key']}: {note}, still waiting on {who}")
        return ops, notes

    def _thesis_ops(self, ws, rec, draft, read=None) -> list:
        """set_thesis from a draft, with its because quote traced to the input that says it."""
        th = {k: draft.get(k) for k in ("change", "outcome", "direction", "unit", "formula", "reach")}
        because = draft.get("because") or {}
        if because.get("quote") and not because.get("source"):
            read = read or self._doc_reader(ws)
            src = next((s["doc"] for s in rec["sources"]
                        if plain(because["quote"]) in plain(read(s["doc"]) or "")), None)
            because = {"source": src, "quote": because["quote"]} if src else {}
        return [{"op": "set_thesis", "project": rec["id"], **{k: v for k, v in th.items() if v is not None},
                 **({"because": because} if because.get("source") else {})}]

    def _live_record(self, ws, pid) -> dict:
        rec = self._records(ws).get(pid)
        if rec is None or rec.get("deleted"):
            raise errors.NotFound(f"no project {pid}")
        return rec

    def propose_thesis(self, p, pid: str, body: dict, approve: bool = False) -> dict:
        """A thesis and the numbers it needs, researched at once: one change request."""
        ws = p.workspace_id
        rec = self._live_record(ws, pid)
        numbers = body.get("numbers") or []
        missing = [k for k in ("change", "outcome", "direction", "unit", "formula") if not body.get(k)]
        if missing:
            raise errors.Invalid(f"a thesis needs {', '.join(missing)}",
                                 problems=["see GET /v1/docs: change, outcome, direction (reduce, increase, "
                                           "improve), unit, formula (number keys), numbers [{key, label, unit}]"])
        keys = {n.get("key") for n in numbers} | {k for k in impact.numbers_of(rec)}
        unknown = [k for k in body["formula"] if isinstance(k, str) and k not in keys]
        if unknown:
            raise errors.Invalid(f"the formula names numbers it does not describe: {', '.join(unknown)}",
                                 problems=["give each one in numbers: {key, label, unit}"])
        ops = self._thesis_ops(ws, rec, body)
        research, notes = self._research_ops(ws, rec, numbers, self._names(ws))
        reason = body.get("reason") or "A thesis, with the numbers it rests on researched."
        return self.open_change_request(p, ops + research, reason + " Research: " + "; ".join(notes),
                                        title=f"Thesis for {pid}", approve=approve)

    def research(self, p, pid: str) -> dict:
        """Look again for the numbers still missing (a document may have arrived); ask for the rest."""
        p.need("projects:propose")
        return self._research(p.workspace_id, pid)

    def _research(self, ws, pid, draft_if_missing: bool = True) -> dict:
        rec = self._live_record(ws, pid)
        names = self._names(ws)
        ops, notes = [], []
        numbers = list(impact.numbers_of(rec).values())
        if not rec.get("thesis") and draft_if_missing:
            draft = self._draft(ws, rec)
            if not draft:
                return {"change_request": None, "notes": ["no thesis yet, and none could be drafted: "
                                                          "propose one (POST /v1/projects/{id}/thesis)"]}
            ops += self._thesis_ops(ws, rec, draft)
            numbers = draft.get("numbers") or []
        more, found_notes = self._research_ops(ws, rec, numbers, names)
        ops += more
        notes += found_notes
        if not ops:
            return {"change_request": None, "notes": notes or ["nothing new to find or ask"]}
        checked = self._dry_run(ws, ops, "", RESEARCHER[2])
        if checked["problems"]:
            return {"change_request": None, "notes": notes, "problems": checked["problems"]}
        title = f"{'Thesis and impact' if any(o['op'] == 'set_thesis' for o in ops) else 'Impact'} research for {pid}"
        cr = self._insert_cr(ws, title, ops, "Research: " + "; ".join(notes), checked, *RESEARCHER)
        return {"change_request": cr, "notes": notes}

    def _figures(self, ws) -> str:
        """The facts with figures a thesis may draw on, one per line: what a thesis call is given."""
        return self._figures_all(ws)[0]

    def _figures_all(self, ws) -> tuple:
        """(the figures a thesis call is given, whether they are all the graph holds: none left out past FACTS_SHOWN)."""
        facts = self._number_facts(ws)
        return "\n".join(f"{q} ({src})" for src, q, _, _, _ in facts[:FACTS_SHOWN]), len(facts) <= FACTS_SHOWN

    def _draft(self, ws, rec, read=None):
        draft_fn = getattr(self.extractor, "draft_thesis", None)
        if draft_fn is None:
            return None
        read = read or self._doc_reader(ws)
        sources = {s["doc"]: read(s["doc"]) for s in rec["sources"] if s.get("kind") != "research"}
        return draft_fn(rec, sources, self._figures(ws))

    def research_input(self, ws, input_path, text, kind, on, changes, draft=None) -> dict:
        """Research before review: the thesis and numbers of the project an input creates, opened as a change
        request beside the input's own and checked against the records as the input's would leave them, so the
        reviewer sees the projected impact while deciding. draft: a thesis the model already wrote with the
        change set (thesis_call merged or parallel); drafted from the proposed project when there is none."""
        created = [ch["project"] for ch in changes if ch.get("op") == "create_project" and ch.get("project")]
        if not created:
            return {"change_request": None, "notes": ["the input creates no project"]}
        with self.db.tx(ws) as c:
            if not self.ws_settings(c, ws).get("impact_research"):
                return {"change_request": None, "notes": ["impact research is off"]}
        pid = created[0]
        after = model.apply(self._records(ws), {"input": input_path, "kind": kind, "on": on, "changes": changes},
                            text)[0]
        rec = after[pid]
        read = self._doc_reader(ws, extra={input_path: text})
        if not draft or not draft.get("change"):
            draft = self._draft(ws, rec, read)
        if not draft or not draft.get("change"):
            return {"change_request": None, "notes": ["no thesis could be drafted"]}
        ops = self._thesis_ops(ws, rec, draft, read)
        more, notes = self._research_ops(ws, rec, draft.get("numbers") or [], self._names(ws))
        ops += more
        checked = self._dry_run(ws, ops, "", RESEARCHER[2], records=after)
        if checked["problems"]:
            with self.db.tx(ws) as c:
                self.log(c, ws, "impact_research.failed", {"project": pid, "problems": checked["problems"][:5]},
                         RESEARCHER[2])
            return {"change_request": None, "notes": notes, "problems": checked["problems"]}
        cr = self._insert_cr(ws, f"Thesis and impact research for {pid}", ops, "Research: " + "; ".join(notes),
                             checked, *RESEARCHER)
        return {"change_request": cr, "notes": notes}

    def _research_open(self, ws, pid) -> bool:
        """True when research on this project already waits for review (opened with its input's change request)."""
        with self.db.tx(ws) as c:
            rows = c.execute(sa.select(t.change_requests.c.targets).where(
                t.change_requests.c.workspace_id == ws, t.change_requests.c.state == "open",
                t.change_requests.c.proposer_kind == RESEARCHER[0],
                t.change_requests.c.proposer_id == RESEARCHER[1])).all()
        return any(pid in ((r[0] or {}).get("projects") or []) for r in rows)

    def _after_applied(self, ws, ops) -> list:
        """Research follows a new project: a draft thesis and its numbers, for a person to approve. None when its
        research was opened before review, with the input's change request."""
        created = [o["project"] for o in ops if o.get("op") == "create_project"]
        if not created:
            return []
        with self.db.tx(ws) as c:
            if not self.ws_settings(c, ws).get("impact_research"):
                return []
        out = []
        for pid in created:
            if self._research_open(ws, pid):
                continue
            try:
                out.append(self._research(ws, pid))
            except Exception as e:  # research is a help, never a reason an approval fails
                with self.db.tx(ws) as c:
                    self.log(c, ws, "impact_research.failed", {"project": pid, "error": str(e)[:300]}, RESEARCHER[2])
        return out

    # ---- answers and estimates -----------------------------------------------------------------

    def answer_number(self, p, pid: str, key: str, body: dict, approve: bool = False) -> dict:
        """A person gives a number: an answer, or an estimate that stays marked as one."""
        rec = self._live_record(p.workspace_id, pid)
        number = impact.numbers_of(rec).get(key)
        if number is None:
            raise errors.NotFound(f"{pid} has no number {key}")
        status = body.get("status") or ("estimated" if body.get("estimate") else "answered")
        if status not in ("answered", "estimated"):
            raise errors.Invalid("status is answered or estimated")
        op = {"op": "set_number", "project": pid, "key": key, "status": status, "value": body.get("value"),
              "unit": number["unit"], "by": body.get("by") or p.name, **{k: body[k] for k in ("answer", "basis") if body.get(k)}}
        return self.open_change_request(p, [op], body.get("reason", ""), approve=approve,
                                        title=f"{'Estimate' if status == 'estimated' else 'Answer'}: {pid} {key}")

    def estimate_effort(self, p, pid: str, body: dict, approve: bool = False) -> dict:
        self._live_record(p.workspace_id, pid)
        op = {"op": "set_effort", "project": pid, "days": body.get("days"), "by": body.get("by") or p.name,
              **({"basis": body["basis"]} if body.get("basis") else {})}
        return self.open_change_request(p, [op], body.get("reason", ""), approve=approve,
                                        title=f"Estimated effort: {pid}")

    # ---- figures and priorities ----------------------------------------------------------------

    def _evaluations(self, ws) -> dict:
        with self.db.tx(ws) as c:
            settings = self.ws_settings(c, ws)
        return {pid: impact.evaluate(rec, settings.get("unit_values") or {}, settings.get("currency") or "GBP")
                for pid, rec in self._records(ws).items() if not rec.get("deleted")}

    def project_impact(self, p, pid: str) -> dict:
        p.need("read") if p.kind != "run" else None
        rec = self._live_record(p.workspace_id, pid)
        ev = self._evaluations(p.workspace_id)
        e = ev[pid]
        prio = self._rank(p.workspace_id, ev)
        place = next((i for i, x in enumerate(prio["ranked"], 1) if x["project"] == pid), None)
        if place is None:
            place = next((i for u in prio["by_unit"].values() for i, x in enumerate(u, 1) if x["project"] == pid),
                         None)
        return {"project": pid, "title": rec["title"], **e, "thesis_record": rec.get("thesis"),
                "priority": {"basis": prio["basis"], "place": place,
                             "unranked": next((x["reason"] for x in prio["unranked"] if x["project"] == pid), None)}}

    def _rank(self, ws, ev=None) -> dict:
        ev = ev if ev is not None else self._evaluations(ws)
        recs = self._records(ws)
        items = [(pid, e) for pid, e in sorted(ev.items()) if model.status_of(recs[pid]) in OPEN]
        r = impact.rank(items)

        def row(pid, e, reason=None):
            out = {"project": pid, "title": recs[pid]["title"], "status": model.status_of(recs[pid]),
                   "thesis": e["thesis"], "projected_impact": e["value"], "unit": e["unit"],
                   "estimated_effort_days": e["effort_days"], "impact_per_day": e["per_day"],
                   "money": e["money"], "money_per_day": e["money_per_day"], "currency": e["currency"],
                   "estimated": e["estimated"], "due": (recs[pid].get("due") or {}).get("date")}
            if reason:
                out.update(reason=reason, missing=e["missing"])
            return out
        return {"basis": r["basis"], "ranked": [row(pid, e) for pid, e in r["ranked"]],
                "by_unit": {u: [row(pid, e) for pid, e in xs] for u, xs in r["by_unit"].items()},
                "unranked": [row(pid, e, why) for pid, e, why in r["unranked"]]}

    def priorities(self, p) -> dict:
        p.need("read")
        return self._rank(p.workspace_id)


__all__ = ["ImpactMixin", "stems", "digit_figures"]
