"""Change requests: every edit, from anyone, applied only when a person approves it.

A change request is a list of operations with a reason and a proposer:
- project operations: the change-set engine's own (projects/model.py:
  create_project, set_status, set_field, ..., delete_project, restore_project);
- source operations: activate_version, retract_source (a held or near-duplicate
  file, or two files that disagree);
- plan operations: approve_plan, accept_task, accept_deliverable.

It is checked when it is opened (validate, as a dry run: the diff and any
problems), and refused at once if the rules forbid it. It is checked again when
approved, against whatever changed since. If another approved request changed a
project it touches and it no longer applies cleanly, it is marked stale. A
person may approve all of it, some of its operations, or an edited version;
each approval records who, when and exactly what.

Every project change quotes the text it came from, as projects/model.py
requires. A transcript's changes quote the transcript. An edit made through
the API quotes its request, a short document the service writes when the edit
is applied: who proposed it, who approved it, and one line per operation.
That document is a source like any other, so the record cites it and the build
checks the quote against it.
"""
import copy
import sys
from pathlib import Path

import sqlalchemy as sa

from . import db as t
from . import errors, ids
from .core import jsonable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "projects"))
import model  # noqa: E402  projects/model.py: the change-set engine

RECORD_OPS = set(model.OPS)
SOURCE_OPS = {"activate_version", "retract_source"}
PLAN_OPS = {"approve_plan", "accept_task", "accept_deliverable"}
SYSTEM_ONLY = {"agree_plan"}  # written by the service when a plan is approved
MAX_QUOTE = model.MAX_QUOTE


def _clip(line: str) -> str:
    return line if len(line) <= MAX_QUOTE else line[:MAX_QUOTE].rsplit(" ", 1)[0]


def op_line(op: dict) -> str:
    """The sentence a project operation is quoted by, in its request."""
    k, pid = op["op"], op.get("project")
    if k == "create_project":
        return f"Create project {pid}, titled {op['title']}."
    if k == "set_status":
        return f"Set the status of {pid} to {op['value']}" + (f" from {op['from']}" if op.get("from") else "") + "."
    if k == "set_field":
        extra = f" ({op['date']})" if op.get("date") else ""
        return f"Set the {op['field']} of {pid} to {op['value']}{extra}."
    if k == "add_dependency":
        return f"{pid} {str(op['kind']).replace('_', ' ')} {op['on']}."
    if k == "add_deliverable":
        extra = "".join(f" {x}" for x in (op.get("owner") and f"Owner: {op['owner']}.",
                                          op.get("due") and f"Due: {op['due']}.") if x)
        return f"Add deliverable {op['key']} to {pid}: {op['title']}.{extra}"
    if k == "set_deliverable":
        return f"Set deliverable {op['key']} of {pid} to {op['status']}" + (f" on {op['on']}" if op.get("on") else "") + "."
    if k == "set_step":
        bits = [x for x in (op.get("status") and f"to {op['status']}", op.get("due") and f"due {op['due']}") if x]
        return f"Set step {op['n']} of {pid} {' and '.join(bits)}."
    if k == "add_question":
        return f"Add question {op['key']} to {pid}: {op['text']}"
    if k == "close_question":
        return f"Close question {op['key']} of {pid}."
    if k == "add_decision":
        return f"Record a decision on {pid}: {op['text']}"
    if k == "delete_project":
        return f"Delete project {pid}."
    if k == "restore_project":
        return f"Restore project {pid}."
    return f"{k} {pid}"


def describe(op: dict) -> str:
    k = op.get("op")
    if k in RECORD_OPS:
        return model.describe(op).strip()
    if k == "activate_version":
        return f"+ source       make version {op.get('version')} current"
    if k == "retract_source":
        return f"- source       retract {op.get('document')}"
    if k == "approve_plan":
        return f"+ plan         approve {op.get('plan')}"
    if k == "accept_task":
        return f"✓ task         accept {op.get('task')} of execution {op.get('execution')}"
    if k == "accept_deliverable":
        return f"✓ deliverable  accept {op.get('project')} {op.get('key')}"
    return f"! {k}"


def render(title: str, ops: list, reason: str, proposer: str, on: str, approver: str = None, edits=None,
           notes=()) -> tuple:
    """(text, ops with quotes) for an API edit: the request document the operations quote."""
    lines = [f"# {title}", "", f"Proposed by {proposer} on {on}."]
    if approver:
        lines.append(f"Approved by {approver} on {on}.")
    if reason:
        lines += ["", f"Reason: {' '.join(reason.split())}"]
    lines.append("")
    out = []
    for i, op in enumerate(ops, 1):
        line = op_line(op)
        lines.append(f"{i}. {line}")
        if op["op"] == "create_project" and op.get("description"):
            lines.append(f"   Description: {' '.join(op['description'].split())}")
        out.append({**op, "quote": _clip(line)})
    for n in notes:
        lines += ["", n]
    if edits:
        lines += ["", "Edited when approved:"] + [f"- operation {i}: {e}" for i, e in edits]
    return "\n".join(lines) + "\n", out


class ReviewMixin:

    # ---- records ----------------------------------------------------------------------------------

    def _records(self, ws, c=None) -> dict:
        if c is None:
            with self.db.tx(ws) as c2:
                return self._records(ws, c2)
        return {r["project_id"]: r["record"] for r in c.execute(
            sa.select(t.project_records).where(t.project_records.c.workspace_id == ws)).mappings()}

    def _record_versions(self, c, ws, pids) -> dict:
        if not pids:
            return {}
        return {r["project_id"]: r["version"] for r in c.execute(
            sa.select(t.project_records.c.project_id, t.project_records.c.version).where(
                t.project_records.c.workspace_id == ws, t.project_records.c.project_id.in_(list(pids)))).mappings()}

    def _entities(self, ws) -> list:
        graph, _, _ = self.projector.ensure(ws)
        return model.entities_from_db(graph, today=self.clock.today())

    def _names(self, ws) -> dict:
        return model.name_map(self._entities(ws))

    # ---- opening --------------------------------------------------------------------------------

    def _classify(self, ops: list) -> list:
        problems = []
        if not isinstance(ops, list) or not ops:
            return ["a change request needs at least one operation"]
        for i, op in enumerate(ops, 1):
            k = op.get("op") if isinstance(op, dict) else None
            if k in SYSTEM_ONLY:
                problems.append(f"operation {i}: {k} is written by the service when a plan is approved")
            elif k not in RECORD_OPS | SOURCE_OPS | PLAN_OPS:
                problems.append(f"operation {i}: unknown operation {k!r}")
        return problems

    def _dry_run(self, ws, ops, reason, proposer_label, input_text=None, input_path=None, kind="request",
                 on=None) -> dict:
        """Check a list of operations against the records as they stand: diff, problems, notes.
        on: the input's own date (a transcript's); today for an API edit."""
        on = on or self.clock.today().isoformat()
        rec_ops = [o for o in ops if o["op"] in RECORD_OPS]
        problems, notes = [], []
        if rec_ops:
            records = self._records(ws)
            names = self._names(ws)
            if input_text is None:
                text, quoted = render("Change request", rec_ops, reason, proposer_label, on)
                diff = {"input": "inputs/requests/draft.md", "kind": "request", "on": on, "by": proposer_label,
                        "changes": quoted}
            else:
                text = input_text
                diff = {"input": input_path, "kind": kind, "on": on, "by": proposer_label, "changes": rec_ops}
            found, confirm = model.validate(records, diff, text, names)
            index = [i for i, o in enumerate(ops, 1) if o["op"] in RECORD_OPS]
            for f in found:  # "change 2 (set_status): ..." counted within the record operations
                head, _, rest = f.partition(" (")
                try:
                    n = int(head.split()[1])
                    problems.append(f"operation {index[n - 1]} ({rest}")
                except (ValueError, IndexError):
                    problems.append(f)
            notes += [f"needs a careful look: {c.split(': ', 1)[-1]}" for c in confirm]
        with self.db.tx(ws) as c:
            for i, op in enumerate(ops, 1):
                k = op["op"]
                if k == "activate_version":
                    v = c.execute(sa.select(t.source_versions.c.status).where(
                        t.source_versions.c.id == op.get("version"), t.source_versions.c.workspace_id == ws)).scalar()
                    if v is None:
                        problems.append(f"operation {i}: no version {op.get('version')}")
                elif k == "retract_source":
                    d = c.execute(sa.select(t.documents.c.deleted_at).where(
                        t.documents.c.id == op.get("document"), t.documents.c.workspace_id == ws)).first()
                    if d is None:
                        problems.append(f"operation {i}: no source {op.get('document')}")
                elif k == "approve_plan":
                    pl = c.execute(sa.select(t.plans.c.state).where(t.plans.c.id == op.get("plan"),
                                                                    t.plans.c.workspace_id == ws)).scalar()
                    if pl is None:
                        problems.append(f"operation {i}: no plan {op.get('plan')}")
                    elif pl != "in_review":
                        problems.append(f"operation {i}: the plan is {pl}, not in review")
        return {"diff": [describe(o) for o in ops], "problems": problems, "notes": notes}

    def _targets(self, ops) -> dict:
        return {"projects": sorted({o["project"] for o in ops if o.get("project")}),
                "plans": sorted({o["plan"] for o in ops if o.get("plan")}),
                "versions": sorted({o["version"] for o in ops if o.get("version")}),
                "documents": sorted({o["document"] for o in ops if o.get("document")}),
                "executions": sorted({o["execution"] for o in ops if o.get("execution")})}

    def open_change_request(self, p, ops: list, reason: str = "", title: str = None, approve: bool = False,
                            run_id: str = None) -> dict:
        if p.kind == "run":
            if run_id != p.run_id:
                raise errors.Forbidden("a run proposes only through its own run")
        else:
            p.need("projects:propose")
        if approve and not (p.is_person and p.can("review:approve")):
            raise errors.Forbidden("approve=true is for people who may approve; this opens the request only if "
                                   "you leave it out")
        ws = p.workspace_id
        bad = self._classify(ops)
        if bad:
            raise errors.Invalid("the change request cannot be opened", problems=bad)
        ops = [{k: v for k, v in o.items() if k != "quote"} for o in ops]
        checked = self._dry_run(ws, ops, reason, p.label)
        if checked["problems"]:
            raise errors.Invalid("the rules refuse this change, so it was not opened", problems=checked["problems"],
                                 diff=checked["diff"])
        cr = self._insert_cr(ws, title or self._title(ops), ops, reason, checked, p.kind, p.id, p.name, run_id=run_id)
        if approve:
            return self.approve_change_request(p, cr["id"])
        return cr

    def open_input_change_request(self, p, ws, doc, vid, text, kind, changes, on, job_id) -> dict:
        """A transcript's or request's proposed changes, quoting it. Opened with its problems if it has any."""
        ops = [dict(ch) for ch in changes]
        bad = self._classify(ops)
        path = f"inputs/{doc['path']}"
        checked = {"diff": [describe(o) for o in ops if isinstance(o, dict)], "problems": bad, "notes": []}
        if not bad:
            checked = self._dry_run(ws, ops, "", p.label, input_text=text, input_path=path, kind=kind, on=on)
        return self._insert_cr(ws, f"Changes from {doc['path']}", ops, f"Proposed from {doc['path']} ({kind}).",
                               checked, "job", job_id, f"ingest job {job_id}", input_version_id=vid, input_on=on)

    def _open_system_cr(self, c, ws, title, ops, reason, proposer) -> str:
        kind, pid, name = proposer
        number = self._next_number(c, ws)
        cid = ids.new("cr")
        now = self.clock.stamp()
        c.execute(t.change_requests.insert().values(
            id=cid, workspace_id=ws, number=number, title=title, ops=ops, reason=reason, input_version_id=None,
            proposer_kind=kind, proposer_id=pid, proposer_name=name, run_id=None, state="open", problems=[],
            notes=[], diff=[describe(o) for o in ops], targets=self._targets(ops), base={}, created=now, updated=now))
        self.emit(c, ws, "change_request.opened", {"id": cid, "number": number, "title": title,
                                                   "proposer": {"kind": kind, "id": pid}})
        return cid

    def _next_number(self, c, ws) -> int:
        c.execute(t.workspaces.update().where(t.workspaces.c.id == ws)
                  .values(cr_counter=t.workspaces.c.cr_counter + 1))
        return c.execute(sa.select(t.workspaces.c.cr_counter).where(t.workspaces.c.id == ws)).scalar_one()

    def _insert_cr(self, ws, title, ops, reason, checked, pkind, pid, pname, run_id=None, input_version_id=None,
                   input_on=None):
        cid = ids.new("cr")
        now = self.clock.stamp()
        with self.db.tx(ws) as c:
            number = self._next_number(c, ws)
            targets = self._targets(ops)
            c.execute(t.change_requests.insert().values(
                id=cid, workspace_id=ws, number=number, title=title, ops=ops, reason=reason or "",
                input_version_id=input_version_id, proposer_kind=pkind, proposer_id=pid, proposer_name=pname,
                run_id=run_id, state="open", problems=checked["problems"], notes=checked["notes"], diff=checked["diff"],
                targets=targets, base={"projects": self._record_versions(c, ws, targets["projects"]),
                                       **({"on": input_on} if input_on else {})},
                created=now, updated=now))
            self.emit(c, ws, "change_request.opened", {"id": cid, "number": number, "title": title,
                                                       "proposer": {"kind": pkind, "id": pid}, "run_id": run_id})
        return self.get_change_request_internal(ws, cid)

    @staticmethod
    def _title(ops) -> str:
        first = describe(ops[0]).split(None, 1)[-1].strip()
        return first + (f" (+{len(ops) - 1} more)" if len(ops) > 1 else "")

    # ---- reading --------------------------------------------------------------------------------

    def get_change_request_internal(self, ws, cid) -> dict:
        with self.db.tx(ws) as c:
            cr = c.execute(sa.select(t.change_requests).where(t.change_requests.c.id == cid,
                                                              t.change_requests.c.workspace_id == ws)).mappings().first()
            if not cr:
                raise errors.NotFound(f"no change request {cid}")
            aps = c.execute(sa.select(t.approvals).where(t.approvals.c.cr_id == cid).order_by(t.approvals.c.at)
                            ).mappings().all()
        out = jsonable(cr)
        out.pop("workspace_id", None)
        out["proposer"] = {"kind": out.pop("proposer_kind"), "id": out.pop("proposer_id"), "name": out.pop("proposer_name")}
        out["decisions"] = [{k: v for k, v in jsonable(a).items() if k not in ("workspace_id", "cr_id")} for a in aps]
        return out

    def get_change_request(self, p, cid) -> dict:
        if p.kind != "run":
            p.need("read")
        cr = self.get_change_request_internal(p.workspace_id, cid)
        if p.kind == "run" and cr["run_id"] != p.run_id:
            raise errors.NotFound(f"no change request {cid}")
        return cr

    def list_change_requests(self, p, state: str = None, project: str = None, proposer: str = None,
                             limit: int = 100, cursor: str = None) -> dict:
        p.need("read")
        ws = p.workspace_id
        with self.db.tx(ws) as c:
            q = sa.select(t.change_requests.c.id, t.change_requests.c.number, t.change_requests.c.targets,
                          t.change_requests.c.proposer_id).where(t.change_requests.c.workspace_id == ws)
            if state:
                q = q.where(t.change_requests.c.state == state)
            if proposer:
                q = q.where(t.change_requests.c.proposer_id == proposer)
            if cursor:
                q = q.where(t.change_requests.c.number < int(cursor))
            rows = c.execute(q.order_by(t.change_requests.c.number.desc())).mappings().all()
        if project:
            rows = [r for r in rows if project in (r["targets"] or {}).get("projects", [])]
        page = rows[:limit]
        return {"items": [self.get_change_request_internal(ws, r["id"]) for r in page],
                "next_cursor": str(page[-1]["number"]) if len(rows) > limit else None}

    # ---- deciding -------------------------------------------------------------------------------

    def _may_decide(self, p, cr, ws):
        if not p.is_person:
            raise errors.Forbidden("only people approve or reject change requests")
        p.need("review:approve")
        with self.db.tx(ws) as c:
            settings = self.ws_settings(c, ws)
        if not settings["self_approval"] and cr["proposer"]["id"] == p.id:
            raise errors.Forbidden("this workspace does not let proposers approve their own requests")

    def update_change_request(self, p, cid, ops: list = None, reason: str = None) -> dict:
        ws = p.workspace_id
        cr = self.get_change_request_internal(ws, cid)
        if cr["state"] not in ("open", "stale"):
            raise errors.Conflict(f"change request {cr['number']} is {cr['state']}")
        if not (cr["proposer"]["id"] == p.id or (p.is_person and p.can("review:approve"))):
            raise errors.Forbidden("only its proposer or an approver may edit a change request")
        ops = cr["ops"] if ops is None else [{k: v for k, v in o.items() if k != "quote"} for o in ops]
        bad = self._classify(ops)
        if bad:
            raise errors.Invalid("the change request cannot be changed that way", problems=bad)
        if cr["input_version_id"]:
            raise errors.Invalid("changes proposed from a transcript are edited when approved (edits=...)")
        checked = self._dry_run(ws, ops, reason if reason is not None else cr["reason"], cr["proposer"]["name"])
        if checked["problems"]:
            raise errors.Invalid("the rules refuse this change", problems=checked["problems"])
        with self.db.tx(ws) as c:
            targets = self._targets(ops)
            c.execute(t.change_requests.update().where(t.change_requests.c.id == cid).values(
                ops=ops, reason=reason if reason is not None else cr["reason"], state="open", problems=[],
                notes=checked["notes"], diff=checked["diff"], targets=targets,
                base={"projects": self._record_versions(c, ws, targets["projects"])}, updated=self.clock.stamp()))
            self.emit(c, ws, "change_request.updated", {"id": cid, "number": cr["number"]})
        return self.get_change_request_internal(ws, cid)

    def reject_change_request(self, p, cid, note: str = "") -> dict:
        ws = p.workspace_id
        cr = self.get_change_request_internal(ws, cid)
        self._may_decide(p, cr, ws)
        if cr["state"] not in ("open", "stale"):
            raise errors.Conflict(f"change request {cr['number']} is {cr['state']}")
        with self.db.tx(ws) as c:
            now = self.clock.stamp()
            c.execute(t.approvals.insert().values(id=ids.new("apv"), workspace_id=ws, cr_id=cid, user_id=p.id,
                                                  decision="reject", ops=[], edits={}, note=note or "", at=now))
            c.execute(t.change_requests.update().where(t.change_requests.c.id == cid)
                      .values(state="rejected", updated=now))
            for op in cr["ops"]:
                self._on_reject(c, p, op, cr)
            self.log(c, ws, "change_request.rejected", {"id": cid, "note": note}, p.label, cid)
            self.emit(c, ws, "change_request.rejected", {"id": cid, "number": cr["number"], "by": p.id})
        return self.get_change_request_internal(ws, cid)

    def _on_reject(self, c, p, op, cr):
        ws = p.workspace_id
        if op["op"] == "activate_version":
            c.execute(t.source_versions.update().where(t.source_versions.c.id == op["version"],
                                                       t.source_versions.c.status.in_(("held", "duplicate")))
                      .values(status="rejected"))
            for j in c.execute(sa.select(t.jobs).where(t.jobs.c.workspace_id == ws, t.jobs.c.status == "waiting")
                               ).mappings():
                if j["result"].get("change_request") == cr["id"]:
                    self._job(c, ws, j["id"], "done", "done", {**j["result"], "approved": False})
        elif op["op"] == "approve_plan":
            c.execute(t.plans.update().where(t.plans.c.id == op["plan"]).values(state="rejected"))
            self.emit(c, ws, "plan.rejected", {"plan_id": op["plan"]})
            self._release_held(c, ws, op["plan"])
        elif op["op"] == "accept_task":
            self._task_rejected(c, ws, op["execution"], op["task"])

    def approve_change_request(self, p, cid, ops: list = None, edits: dict = None, note: str = "") -> dict:
        ws = p.workspace_id
        cr = self.get_change_request_internal(ws, cid)
        self._may_decide(p, cr, ws)
        if cr["state"] == "stale":
            raise errors.Conflict("the change request is stale: bring it up to date first (PATCH it)",
                                  problems=cr["problems"])
        if cr["state"] != "open":
            raise errors.Conflict(f"change request {cr['number']} is {cr['state']}")
        if cr["problems"]:
            raise errors.Invalid("the change request has problems, so it cannot be applied as it is; edit it "
                                 "or reject it", problems=cr["problems"])
        n = len(cr["ops"])
        chosen = sorted(set(ops)) if ops else list(range(1, n + 1))
        if any(not 1 <= i <= n for i in chosen):
            raise errors.Invalid(f"operations are numbered 1 to {n}")
        edits = {int(k): v for k, v in (edits or {}).items()}
        if any(i not in chosen for i in edits):
            raise errors.Invalid("an edited operation must also be approved")
        final, edit_notes = [], []
        for i in chosen:
            op = copy.deepcopy(cr["ops"][i - 1])
            if i in edits:
                if "op" in edits[i]:
                    raise errors.Invalid("an edit may change an operation's values, not what it is")
                before = {k: op.get(k) for k in edits[i]}
                op.update(edits[i])
                edit_notes.append((i, ", ".join(f"{k}: {before[k]!r} → {v!r}" for k, v in edits[i].items())))
            final.append((i, op, i in edits))
        # stale? another approved request changed a project this one touches
        with self.db.tx(ws) as c:
            now_versions = self._record_versions(c, ws, cr["targets"].get("projects", []))
        moved = {k for k, v in (cr["base"].get("projects") or {}).items() if now_versions.get(k) != v}
        moved |= {k for k in now_versions if k not in (cr["base"].get("projects") or {})}
        if moved or edits:
            recheck = self._recheck(ws, cr, final)
            if recheck:
                if moved and not edits:
                    with self.db.tx(ws) as c:
                        c.execute(t.change_requests.update().where(t.change_requests.c.id == cid)
                                  .values(state="stale", problems=recheck, updated=self.clock.stamp()))
                        self.emit(c, ws, "change_request.stale", {"id": cid, "number": cr["number"]})
                    raise errors.Conflict(f"{', '.join(sorted(moved))} changed since this was opened, and it no "
                                          "longer applies cleanly: it is now stale", problems=recheck)
                raise errors.Invalid("with those edits the rules refuse it", problems=recheck)
        # source operations are tried together before anything is written
        activations = [op["version"] for _, op, _ in final if op["op"] == "activate_version"]
        retractions = [op["document"] for _, op, _ in final if op["op"] == "retract_source"]
        for vid in activations:
            self.activate_version(p, vid, cid)
        if activations or retractions:
            problems = self.trial_activation(ws, activations, retractions)
            if problems:
                raise errors.Invalid("the graph would not build with these sources together; approve the "
                                     "retraction too, or reject", problems=problems)
        self._apply(p, ws, cr, final, edit_notes, note)
        return self.get_change_request_internal(ws, cid)

    def _recheck(self, ws, cr, final) -> list:
        rec_ops = [op for _, op, _ in final if op["op"] in RECORD_OPS]
        if not rec_ops:
            return []
        if cr["input_version_id"]:
            text, path, kind = self._input_of(ws, cr["input_version_id"])
            plain_ops = [op for _, op, edited in final if op["op"] in RECORD_OPS and not edited]
            edited = [op for _, op, e in final if op["op"] in RECORD_OPS and e]
            problems = self._dry_run(ws, plain_ops, "", "recheck", input_text=text, input_path=path,
                                     kind=kind, on=cr["base"].get("on"))["problems"] if plain_ops else []
            if edited:
                problems += self._dry_run(ws, edited, "", "recheck")["problems"]
            return problems
        return self._dry_run(ws, rec_ops, cr["reason"], cr["proposer"]["name"])["problems"]

    def _input_of(self, ws, vid) -> tuple:
        with self.db.tx(ws) as c:
            v = c.execute(sa.select(t.source_versions).where(t.source_versions.c.id == vid)).mappings().first()
            d = c.execute(sa.select(t.documents).where(t.documents.c.id == v["document_id"])).mappings().first()
        return self.blobs.get(v["blob_key"]).decode("utf-8"), f"inputs/{d['path']}", d["kind"]

    def _request_document(self, c, ws, name: str, text: str, actor: str) -> str:
        """Store a request the service wrote as a source: kind request, collection requests. Returns its path."""
        data = text.encode("utf-8")
        key = self.blobs.put(data)
        now = self.clock.stamp()
        doc_id, vid = ids.new("doc"), ids.new("ver")
        path = self._free_path(c, ws, f"requests/{name}")
        c.execute(t.documents.insert().values(id=doc_id, workspace_id=ws, external_id=None, collection="requests",
                                              name=path.split("/", 1)[1], path=path, kind="request", uri=None,
                                              current_version_id=vid, created=now, deleted_at=None))
        c.execute(t.source_versions.insert().values(
            id=vid, workspace_id=ws, document_id=doc_id, seq=1, sha256_bytes=ids.sha256(data), sha256_text=ids.sha256(data),
            minhash=None, blob_key=key, size=len(data), mime="text/markdown", status="active", dedup="new",
            duplicate_of=None, similarity=None, problems=[], extraction=None, extraction_at=None, created=now))
        return f"inputs/{path}"

    def apply_record_ops(self, c, p, ws, ops, text, input_path, kind, by, cr_id=None, names=None, on=None) -> list:
        """Check and apply project operations inside transaction c; save the records and their history.
        names: the graph's names, for the owner checks (read before the transaction, since reading may rebuild)."""
        if not ops:
            return []
        records = self._records(ws, c)
        if names is None:
            names = getattr(self._tls, "names", None)
        if names is None:
            names = self._names(ws)
        diff = {"input": input_path, "kind": kind, "on": on or self.clock.today().isoformat(), "by": by, "changes": ops}
        problems, _ = model.validate(records, diff, text, names)
        if problems:
            raise errors.Invalid("the change no longer passes the project checks", problems=problems)
        after, events = model.apply(records, diff, text)
        now = self.clock.stamp()
        versions = self._record_versions(c, ws, list(after))
        for pid, rec in after.items():
            if records.get(pid) == rec:
                continue
            if pid in versions:
                c.execute(t.project_records.update().where(t.project_records.c.workspace_id == ws,
                                                           t.project_records.c.project_id == pid)
                          .values(record=rec, version=versions[pid] + 1, updated=now))
            else:
                c.execute(t.project_records.insert().values(workspace_id=ws, project_id=pid, version=1, record=rec,
                                                            updated=now))
        for ev in events:
            c.execute(t.project_events.insert().values(workspace_id=ws, project_id=ev["project"], event=ev, cr_id=cr_id,
                                                       actor=by, at=now))
        for pid in sorted({ev["project"] for ev in events}):
            self.emit(c, ws, "project.updated", {"project": pid, "change_request": cr_id,
                                                 "ops": [e["op"] for e in events if e["project"] == pid]})
        return events

    def _apply(self, p, ws, cr, final, edit_notes, note):
        rec_final = [(i, op, e) for i, op, e in final if op["op"] in RECORD_OPS]
        needs_names = rec_final or any(op["op"] == "approve_plan" for _, op, _ in final)
        self._tls.names = self._names(ws) if needs_names else None
        try:
            self._apply_now(p, ws, cr, final, edit_notes, note, rec_final)
        finally:
            self._tls.names = None

    def _apply_now(self, p, ws, cr, final, edit_notes, note, rec_final):
        by = f"{cr['proposer']['name']}, approved by {p.name}"
        proposer = f"{cr['proposer']['name']} ({cr['proposer']['kind']} {cr['proposer']['id']})"
        now = self.clock.stamp()
        with self.db.tx(ws) as c:
            if rec_final:
                if cr["input_version_id"]:
                    text, path, kind = self._input_of(ws, cr["input_version_id"])
                    self.apply_record_ops(c, p, ws, [op for _, op, e in rec_final if not e], text, path, kind, by,
                                          cr["id"], on=cr["base"].get("on"))
                    edited = [op for _, op, e in rec_final if e]
                    if edited:
                        body, quoted = render(f"Change request {cr['number']}: edits", edited, cr["reason"],
                                              cr["proposer"]["name"], self.clock.today().isoformat(), approver=p.label,
                                              edits=edit_notes)
                        path2 = self._request_document(c, ws, f"cr-{cr['number']}-edits.md", body, p.label)
                        self.apply_record_ops(c, p, ws, quoted, body, path2, "request", by, cr["id"])
                else:
                    body, quoted = render(f"Change request {cr['number']}: {cr['title']}", [op for _, op, _ in rec_final],
                                          cr["reason"], proposer, self.clock.today().isoformat(), approver=p.label,
                                          edits=edit_notes)
                    path = self._request_document(c, ws, f"cr-{cr['number']}.md", body, p.label)
                    self.apply_record_ops(c, p, ws, quoted, body, path, "request", by, cr["id"])
            for _, op, _ in final:
                k = op["op"]
                if k == "activate_version":
                    self.commit_activation(c, p, op["version"], cr["id"])
                elif k == "retract_source":
                    self.retract_source(p, op["document"], cr["id"], c)
                elif k == "approve_plan":
                    self._approve_plan(c, p, op["plan"], cr)
                elif k == "accept_task":
                    self._accept_task(c, p, op["execution"], op["task"], cr)
                elif k == "accept_deliverable":
                    self._accept_deliverable(c, p, op["project"], op["key"], op.get("execution"), cr)
            c.execute(t.approvals.insert().values(id=ids.new("apv"), workspace_id=ws, cr_id=cr["id"], user_id=p.id,
                                                  decision="approve", ops=[i for i, _, _ in final],
                                                  edits={str(i): e for i, e in edit_notes}, note=note or "", at=now))
            c.execute(t.change_requests.update().where(t.change_requests.c.id == cr["id"]).values(
                state="applied", updated=now, problems=[],
                ops=[op for _, op, _ in final] + [dict(o, skipped=True) for j, o in enumerate(cr["ops"], 1)
                                                  if j not in {i for i, _, _ in final}]))
            if rec_final:
                self.bump(c, ws)
            self.log(c, ws, "change_request.applied", {"id": cr["id"], "ops": [i for i, _, _ in final],
                                                       "edits": dict(edit_notes)}, p.label, cr["id"])
            self.emit(c, ws, "change_request.applied", {"id": cr["id"], "number": cr["number"], "by": p.id,
                                                        "ops": [i for i, _, _ in final],
                                                        "partial": len(final) < len(cr["ops"])})
