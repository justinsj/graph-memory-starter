"""Projects: read the approved records; every write opens a change request.

A project is the record projects/model.py defines (title, description, status
history, owner, due date, dependencies, deliverables, plan, questions,
decisions, sources). The service adds a version (the ETag), a soft delete, and
the overlay of what is proposed but not yet approved.
"""
import sys
from pathlib import Path

import sqlalchemy as sa

from . import db as t
from . import errors
from .core import jsonable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "projects"))
import model  # noqa: E402
sys.path.insert(0, str(ROOT / "src"))
import tokens  # noqa: E402

PATCHABLE = {"title", "description", "status", "status_from", "owner", "requested_by", "due"}


def summary(pid: str, rec: dict, version: int) -> dict:
    due = rec.get("due") or {}
    return {"id": pid, "title": rec["title"], "status": model.status_of(rec), "owner": (rec.get("owner") or {}).get("entity"),
            "requested_by": (rec.get("requested_by") or {}).get("entity"),
            "due": {"text": due.get("text"), "date": due.get("date")} if due else None,
            "deliverables": [{"key": d["key"], "title": d["title"], "status": d["status"]} for d in rec["deliverables"]],
            "plan": {"state": rec["plan"]["state"], "version": rec["plan"]["version"], "steps": len(rec["plan"]["steps"])},
            "open_questions": len(model.open_questions(rec)), "updated": model.last_activity(rec),
            "deleted": bool(rec.get("deleted")), "version": version}


class ProjectsMixin:

    def _record(self, c, ws, pid):
        row = c.execute(sa.select(t.project_records).where(t.project_records.c.workspace_id == ws,
                                                           t.project_records.c.project_id == pid)).mappings().first()
        if not row:
            raise errors.NotFound(f"no project {pid}")
        return row

    def _pending_for(self, ws, pid) -> list:
        with self.db.tx(ws) as c:
            rows = c.execute(sa.select(t.change_requests).where(t.change_requests.c.workspace_id == ws,
                                                                t.change_requests.c.state.in_(("open", "stale")))
                             .order_by(t.change_requests.c.number)).mappings().all()
        return [{"change_request": r["id"], "number": r["number"], "title": r["title"], "state": r["state"],
                 "diff": [d for d, o in zip(r["diff"], r["ops"]) if o.get("project") == pid] or r["diff"],
                 "proposer": r["proposer_name"]}
                for r in rows if pid in (r["targets"] or {}).get("projects", [])]

    def list_projects(self, p, status: str = None, owner: str = None, due_before: str = None, due_after: str = None,
                      q: str = None, include_deleted: bool = False, include_pending: bool = False,
                      limit: int = 100, cursor: str = None) -> dict:
        p.need("read")
        ws = p.workspace_id
        with self.db.tx(ws) as c:
            rows = c.execute(sa.select(t.project_records).where(t.project_records.c.workspace_id == ws)
                             .order_by(t.project_records.c.project_id)).mappings().all()
        want = set(tokens.words(q)) if q else set()
        out = []
        for r in rows:
            rec, s = r["record"], summary(r["project_id"], r["record"], r["version"])
            if s["deleted"] and not include_deleted:
                continue
            if status and s["status"] not in status.split(","):
                continue
            if owner and (s["owner"] or "").lower() != owner.lower():
                continue
            d = (s["due"] or {}).get("date")
            if due_before and not (d and d < due_before):
                continue
            if due_after and not (d and d > due_after):
                continue
            if want:
                hay = " ".join([rec["title"], rec["description"]["text"], *rec.get("aliases", []),
                                *(x["text"] for x in rec["decisions"]), *(x["text"] for x in rec["questions"]),
                                *(x["title"] for x in rec["deliverables"])])
                if not want <= set(tokens.words(hay)):
                    continue
            if cursor and r["project_id"] <= cursor:
                continue
            if include_pending:
                s["pending"] = self._pending_for(ws, r["project_id"])
            out.append(s)
        page = out[:limit]
        return {"items": page, "next_cursor": page[-1]["id"] if len(out) > limit else None}

    def get_project(self, p, pid: str, include: set = frozenset(), include_pending: bool = False) -> dict:
        p.need("read") if p.kind != "run" else None
        ws = p.workspace_id
        with self.db.tx(ws) as c:
            row = self._record(c, ws, pid)
            out = {"id": pid, "version": row["version"], "updated": row["updated"],
                   "summary": summary(pid, row["record"], row["version"]), "record": row["record"]}
            if "events" in include:
                out["events"] = [{"at": e["at"], "actor": e["actor"], "change_request": e["cr_id"], **e["event"]}
                                 for e in c.execute(sa.select(t.project_events).where(
                                     t.project_events.c.workspace_id == ws, t.project_events.c.project_id == pid)
                                     .order_by(t.project_events.c.id)).mappings()]
            if "plans" in include:
                out["plans"] = [self._plan_summary(pl) for pl in c.execute(
                    sa.select(t.plans).where(t.plans.c.workspace_id == ws, t.plans.c.project_id == pid)
                    .order_by(t.plans.c.deliverable_key, t.plans.c.version)).mappings()]
        if include_pending or "pending" in include:
            out["pending"] = self._pending_for(ws, pid)
        return out

    def _if_match(self, ws, pid, if_match):
        if if_match is None:
            return
        with self.db.tx(ws) as c:
            row = self._record(c, ws, pid)
        want = str(if_match).strip('W/"')
        if want.lstrip("v") != str(row["version"]):
            raise errors.Conflict(f"{pid} is at version {row['version']}, not {want}: read it again and retry",
                                  current_version=row["version"])

    def create_project(self, p, body: dict, approve: bool = False) -> dict:
        pid = body.get("id")
        if not pid or not body.get("title") or not body.get("description"):
            raise errors.Invalid("a project needs an id (lowercase words joined by hyphens), a title and a description")
        ops = [{"op": "create_project", "project": pid, "title": body["title"], "description": body["description"],
                **({"aliases": body["aliases"]} if body.get("aliases") else {})}]
        for field in ("owner", "requested_by"):
            if body.get(field):
                ops.append({"op": "set_field", "project": pid, "field": field, "value": body[field]})
        if body.get("due"):
            due = body["due"] if isinstance(body["due"], dict) else {"text": body["due"]}
            ops.append({"op": "set_field", "project": pid, "field": "due", "value": due.get("text") or due.get("date"),
                        **({"date": due["date"]} if due.get("date") else {})})
        ops.append({"op": "set_status", "project": pid, "value": body.get("status") or "proposed"})
        for d in body.get("deliverables") or []:
            ops.append({"op": "add_deliverable", "project": pid, "key": d["key"], "title": d["title"],
                        **{k: d[k] for k in ("owner", "due") if d.get(k)}})
        return self.open_change_request(p, ops, body.get("reason", ""), title=f"Create project {pid}", approve=approve)

    def patch_project(self, p, pid: str, patch: dict, if_match=None, approve: bool = False) -> dict:
        ws = p.workspace_id
        bad = sorted(set(patch) - PATCHABLE - {"reason"})
        if bad:
            raise errors.Invalid(f"these cannot be patched: {', '.join(bad)}",
                                 problems=[f"patchable: {sorted(PATCHABLE)}; deliverables, steps, questions and "
                                           "decisions have their own calls, or send operations to /changes"])
        self._if_match(ws, pid, if_match)
        ops = []
        for field in ("title", "description", "owner", "requested_by"):
            if field in patch:
                ops.append({"op": "set_field", "project": pid, "field": field, "value": patch[field]})
        if "due" in patch:
            due = patch["due"] if isinstance(patch["due"], dict) else {"text": patch["due"]}
            ops.append({"op": "set_field", "project": pid, "field": "due", "value": due.get("text") or due.get("date"),
                        **({"date": due["date"]} if due.get("date") else {})})
        if "status" in patch:
            ops.append({"op": "set_status", "project": pid, "value": patch["status"],
                        **({"from": patch["status_from"]} if patch.get("status_from") else {})})
        if not ops:
            raise errors.Invalid("nothing to change")
        return self.open_change_request(p, ops, patch.get("reason", ""), approve=approve)

    def delete_project(self, p, pid: str, if_match=None, reason: str = "", approve: bool = False) -> dict:
        self._if_match(p.workspace_id, pid, if_match)
        return self.open_change_request(p, [{"op": "delete_project", "project": pid}], reason,
                                        title=f"Delete project {pid}", approve=approve)

    def restore_project(self, p, pid: str, reason: str = "", approve: bool = False) -> dict:
        return self.open_change_request(p, [{"op": "restore_project", "project": pid}], reason,
                                        title=f"Restore project {pid}", approve=approve)

    def add_deliverable(self, p, pid: str, body: dict, approve: bool = False) -> dict:
        if not body.get("key") or not body.get("title"):
            raise errors.Invalid("a deliverable needs a key (e.g. D1) and a title")
        return self.open_change_request(p, [{"op": "add_deliverable", "project": pid, "key": body["key"],
                                             "title": body["title"], **{k: body[k] for k in ("owner", "due")
                                                                        if body.get(k)}}],
                                        body.get("reason", ""), approve=approve)

    def propose_changes(self, p, ops: list, reason: str = "", dry_run: bool = False, approve: bool = False,
                        title: str = None) -> dict:
        if dry_run:
            p.need("read")
            bad = self._classify(ops)
            if bad:
                return {"dry_run": True, "diff": [], "problems": bad, "notes": []}
            clean = [{k: v for k, v in o.items() if k != "quote"} for o in ops]
            return {"dry_run": True, **self._dry_run(p.workspace_id, clean, reason, p.label)}
        return self.open_change_request(p, ops, reason, title=title, approve=approve)

    def project_events(self, p, pid: str) -> list:
        return self.get_project(p, pid, include={"events"})["events"]


__all__ = ["ProjectsMixin", "summary", "jsonable"]
