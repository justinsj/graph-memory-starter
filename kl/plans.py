"""Plans: how a deliverable gets made, as a graph of tasks a person approves.

A plan belongs to one deliverable and is versioned. Its kind is general
(tasks sent as JSON) or openspec (an OpenSpec change folder, imported by
kl.openspec). Proposing one opens a change request (approve_plan). Approving
it:
- makes it the deliverable's current plan, superseding the last one;
- mirrors every approved plan's tasks into the project record's steps (an
  agree_plan written by the service, quoting a short approval note), so recall
  and the board show the plan;
- moves any running execution of the old version onto the new one. Finished
  tasks whose definition did not change stay finished.

While a new version waits for review, the tasks it would change or remove are
held: they are not leased until the request is decided.
"""
import json
import sys
from collections import defaultdict, deque
from pathlib import Path

import sqlalchemy as sa

from . import db as t
from . import errors, ids, openspec
from .core import jsonable
from .review import render

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "projects"))
import model  # noqa: E402

CHECK_KINDS = ("auto", "person")


def task_digest(task: dict) -> str:
    keep = {k: task.get(k) for k in ("key", "title", "instructions", "after", "needs", "checks", "gate", "outputs")}
    return ids.sha256(json.dumps(keep, sort_keys=True))


def check_tasks(tasks: list) -> list:
    problems = []
    if not isinstance(tasks, list) or not tasks:
        return ["a plan needs at least one task"]
    keys = [str(x.get("key", "")).strip() for x in tasks]
    for i, (k, task) in enumerate(zip(keys, tasks), 1):
        if not k:
            problems.append(f"task {i}: needs a key")
        if not task.get("title"):
            problems.append(f"task {k or i}: needs a title")
        for a in task.get("after") or []:
            if a not in keys:
                problems.append(f"task {k}: waits on {a!r}, which is not a task of this plan")
            elif a == k:
                problems.append(f"task {k}: cannot wait on itself")
        if not isinstance(task.get("needs") or [], list):
            problems.append(f"task {k}: needs is a list of what a runner must offer")
        for ch in task.get("checks") or []:
            if not ch.get("id") or ch.get("kind", "auto") not in CHECK_KINDS:
                problems.append(f"task {k}: each check has an id and a kind ({' or '.join(CHECK_KINDS)})")
        r = task.get("retries", 2)
        if not isinstance(r, int) or not 0 <= r <= 10:
            problems.append(f"task {k}: retries is 0 to 10")
    dup = sorted({k for k in keys if keys.count(k) > 1 and k})
    if dup:
        problems.append(f"task keys must be unique: {', '.join(dup)}")
    if not problems:
        order = topo(tasks)
        if order is None:
            problems.append("the tasks wait on each other in a circle")
    return problems


def topo(tasks: list):
    after = {x["key"]: list(x.get("after") or []) for x in tasks}
    indeg = {k: len(v) for k, v in after.items()}
    users = defaultdict(list)
    for k, v in after.items():
        for a in v:
            users[a].append(k)
    position = {x["key"]: i for i, x in enumerate(tasks)}
    queue = deque(sorted((k for k, d in indeg.items() if d == 0), key=position.get))
    out = []
    while queue:
        k = queue.popleft()
        out.append(k)
        for u in sorted(users[k], key=position.get):
            indeg[u] -= 1
            if indeg[u] == 0:
                queue.append(u)
    return out if len(out) == len(tasks) else None


class PlansMixin:

    def _plan_summary(self, pl) -> dict:
        return {"id": pl["id"], "project": pl["project_id"], "deliverable": pl["deliverable_key"], "version": pl["version"],
                "kind": pl["kind"], "state": pl["state"], "title": pl["title"], "created": pl["created"],
                "approved_by": pl["approved_by"], "approved_at": pl["approved_at"]}

    def propose_plan(self, p, pid: str, key: str, body: dict) -> dict:
        if p.kind == "run":
            pass
        else:
            p.need("plans:propose")
        ws = p.workspace_id
        kind = body.get("kind", "general")
        if kind == "openspec":
            files = body.get("files") or {}
            name = body.get("change") or body.get("title") or "change"
            plan, problems = openspec.change_to_plan(name, files, bool(body.get("parallel_sections")))
            for override in ("needs",):  # what every task's runner must offer, e.g. ["repo:acme/shop"]
                if body.get(override):
                    for task in plan["tasks"]:
                        task[override] = list(body[override])
        elif kind == "general":
            plan = {"kind": "general", "title": body.get("title") or f"Plan for {key}", "summary": body.get("summary", ""),
                    "design": body.get("design", ""), "tasks": body.get("tasks") or [], "checks": body.get("checks") or [],
                    "openspec": None}
            problems = []
        else:
            raise errors.Invalid("kind is general or openspec")
        problems += check_tasks(plan["tasks"])
        with self.db.tx(ws) as c:
            row = self._record(c, ws, pid)
            rec = row["record"]
            if rec.get("deleted"):
                problems.append(f"{pid} is deleted")
            if key not in {d["key"] for d in rec["deliverables"]}:
                problems.append(f"{pid} has no deliverable {key}: add it first")
        if problems:
            raise errors.Invalid("the plan cannot be proposed", problems=problems)
        plan_id = ids.new("pln")
        now = self.clock.stamp()
        with self.db.tx(ws) as c:
            version = (c.execute(sa.select(sa.func.max(t.plans.c.version)).where(
                t.plans.c.workspace_id == ws, t.plans.c.project_id == pid, t.plans.c.deliverable_key == key)).scalar() or 0) + 1
            c.execute(t.plans.insert().values(
                id=plan_id, workspace_id=ws, project_id=pid, deliverable_key=key, version=version, kind=plan["kind"],
                state="in_review", title=plan["title"], summary=plan["summary"], design=plan["design"],
                checks=plan["checks"], openspec=plan.get("openspec"), created=now, created_by=p.label,
                approved_by=None, approved_at=None))
            for n, task in enumerate(plan["tasks"], 1):
                task = {"after": [], "needs": [], "checks": [], "gate": False, "outputs": [], "instructions": "", **task}
                c.execute(t.tasks.insert().values(
                    id=ids.new("tsk"), workspace_id=ws, plan_id=plan_id, key=str(task["key"]), n=n, title=task["title"],
                    instructions=task.get("instructions") or "", after=[str(a) for a in task["after"]],
                    needs=list(task["needs"]), checks=list(task["checks"]), gate=bool(task["gate"]),
                    outputs=list(task["outputs"]), retries=int(task.get("retries", 2)), digest=task_digest(task)))
            self.emit(c, ws, "plan.proposed", {"plan_id": plan_id, "project": pid, "deliverable": key, "version": version})
        cr = self.open_change_request(p, [{"op": "approve_plan", "plan": plan_id}],
                                      body.get("reason", "") or f"Plan v{version} for {pid} {key}: {plan['title']}",
                                      title=f"Plan v{version} for {pid} {key}", run_id=p.run_id if p.kind == "run" else None)
        return {**self.get_plan(p, plan_id), "change_request": cr}

    def get_plan(self, p, plan_id: str) -> dict:
        if p.kind != "run":
            p.need("read")
        ws = p.workspace_id
        with self.db.tx(ws) as c:
            pl = c.execute(sa.select(t.plans).where(t.plans.c.id == plan_id, t.plans.c.workspace_id == ws)).mappings().first()
            if not pl:
                raise errors.NotFound(f"no plan {plan_id}")
            ts = c.execute(sa.select(t.tasks).where(t.tasks.c.plan_id == plan_id).order_by(t.tasks.c.n)).mappings().all()
        out = {**self._plan_summary(pl), "summary": pl["summary"], "design": pl["design"], "checks": pl["checks"],
               "openspec": pl["openspec"],
               "tasks": [{k: x[k] for k in ("key", "n", "title", "instructions", "after", "needs", "checks", "gate",
                                            "outputs", "retries")} for x in ts]}
        return out

    def list_plans(self, p, pid: str = None, state: str = None) -> list:
        p.need("read")
        ws = p.workspace_id
        with self.db.tx(ws) as c:
            q = sa.select(t.plans).where(t.plans.c.workspace_id == ws)
            if pid:
                q = q.where(t.plans.c.project_id == pid)
            if state:
                q = q.where(t.plans.c.state == state)
            return [self._plan_summary(pl) for pl in c.execute(q.order_by(t.plans.c.created)).mappings()]

    # ---- approval --------------------------------------------------------------------------------

    def _approve_plan(self, c, p, plan_id, cr):
        ws = p.workspace_id
        pl = c.execute(sa.select(t.plans).where(t.plans.c.id == plan_id)).mappings().first()
        if pl["state"] != "in_review":
            raise errors.Conflict(f"the plan is {pl['state']}")
        now = self.clock.stamp()
        old = c.execute(sa.select(t.plans).where(t.plans.c.workspace_id == ws, t.plans.c.project_id == pl["project_id"],
                                                 t.plans.c.deliverable_key == pl["deliverable_key"],
                                                 t.plans.c.state == "approved")).mappings().first()
        if old:
            c.execute(t.plans.update().where(t.plans.c.id == old["id"]).values(state="superseded"))
        c.execute(t.plans.update().where(t.plans.c.id == plan_id).values(state="approved", approved_by=p.id,
                                                                          approved_at=now))
        if old:
            self._migrate_executions(c, ws, old["id"], plan_id)
        self._mirror_plans(c, p, pl["project_id"], cr)
        self.emit(c, ws, "plan.approved", {"plan_id": plan_id, "project": pl["project_id"],
                                           "deliverable": pl["deliverable_key"], "version": pl["version"],
                                           "supersedes": old["id"] if old else None})

    def _mirror_plans(self, c, p, pid, cr=None):
        """The project record's steps: every approved plan's tasks, numbered, as an agreed plan."""
        ws = p.workspace_id
        steps, number = [], {}
        plans = c.execute(sa.select(t.plans).where(t.plans.c.workspace_id == ws, t.plans.c.project_id == pid,
                                                   t.plans.c.state == "approved").order_by(t.plans.c.deliverable_key)
                          ).mappings().all()
        for pl in plans:
            ts = c.execute(sa.select(t.tasks).where(t.tasks.c.plan_id == pl["id"]).order_by(t.tasks.c.n)).mappings().all()
            order = topo([dict(x) for x in ts]) or [x["key"] for x in ts]
            by_key = {x["key"]: x for x in ts}
            states = self._latest_task_states(c, ws, pl["id"])
            for k in order:
                x = by_key[k]
                n = len(steps) + 1
                number[(pl["id"], k)] = n
                status = {"done": "done", "running": "doing", "leased": "doing", "awaiting_review": "doing",
                          "failed": "blocked"}.get(states.get(k), "todo")
                steps.append({"n": n, "title": f"{pl['deliverable_key']} {k}: {x['title']}"[:200],
                              "after": [number[(pl["id"], a)] for a in x["after"] if (pl["id"], a) in number],
                              "delivers": pl["deliverable_key"], "status": status})
        if not steps or len(steps) > model.MAX_STEPS:
            return number  # too many to mirror: the plans themselves stay the record of what is planned
        lines = [f"Step {s['n']}: {s['title']}" for s in steps]
        text = "\n".join([f"# Plans approved for {pid}", "",
                          f"Approved by {p.label} on {self.clock.today().isoformat()}.", "",
                          *lines]) + "\n"
        for s, line in zip(steps, lines):
            s["quote"] = line[:model.MAX_QUOTE]
        path = self._request_document(c, ws, f"plans-{pid}-{ids.new('p', 5)[2:]}.md", text, p.label)
        names = self._plan_names(ws)
        records = self._records(ws, c)
        diff = {"input": path, "kind": "discussion", "on": self.clock.today().isoformat(), "by": p.label,
                "changes": [{"op": "agree_plan", "project": pid, "steps": steps, "quote": lines[0][:model.MAX_QUOTE]}]}
        problems, _ = model.validate(records, diff, text, names)
        if problems:
            return number  # the record keeps its last plan; the approved plans still run
        self.apply_record_ops(c, p, ws, diff["changes"], text, path, "discussion", p.label, cr["id"] if cr else None,
                              names=names)
        return number

    def _plan_names(self, ws):
        cached = getattr(self._tls, "names", None)
        return cached if cached is not None else self._names(ws)

    def _latest_task_states(self, c, ws, plan_id) -> dict:
        ex = c.execute(sa.select(t.executions.c.id).where(t.executions.c.workspace_id == ws,
                                                          t.executions.c.plan_id == plan_id)
                       .order_by(t.executions.c.created.desc())).scalar()
        if not ex:
            return {}
        return {r["task_key"]: r["state"] for r in c.execute(sa.select(t.execution_tasks).where(
            t.execution_tasks.c.execution_id == ex)).mappings()}

    def _step_number(self, c, ws, pid, plan_id, key):
        n = 0
        for pl in c.execute(sa.select(t.plans).where(t.plans.c.workspace_id == ws, t.plans.c.project_id == pid,
                                                     t.plans.c.state == "approved").order_by(t.plans.c.deliverable_key)
                            ).mappings():
            ts = c.execute(sa.select(t.tasks).where(t.tasks.c.plan_id == pl["id"]).order_by(t.tasks.c.n)).mappings().all()
            order = topo([dict(x) for x in ts]) or [x["key"] for x in ts]
            for k in order:
                n += 1
                if pl["id"] == plan_id and k == key:
                    return n
        return None

    # ---- executions ------------------------------------------------------------------------------

    def start_execution(self, p, plan_id: str) -> dict:
        p.need("runs:lease")
        ws = p.workspace_id
        with self.db.tx(ws) as c:
            pl = c.execute(sa.select(t.plans).where(t.plans.c.id == plan_id, t.plans.c.workspace_id == ws)).mappings().first()
            if not pl:
                raise errors.NotFound(f"no plan {plan_id}")
            if pl["state"] != "approved":
                raise errors.Conflict(f"only an approved plan runs; this one is {pl['state']}")
            running = c.execute(sa.select(t.executions.c.id).where(t.executions.c.plan_id == plan_id,
                                                                   t.executions.c.state == "running")).scalar()
            if running:
                raise errors.Conflict(f"execution {running} is already running this plan", execution_id=running)
            eid = ids.new("exe")
            now = self.clock.stamp()
            c.execute(t.executions.insert().values(id=eid, workspace_id=ws, plan_id=plan_id, state="running", created=now,
                                                   created_by=p.label, finished=None))
            ts = c.execute(sa.select(t.tasks).where(t.tasks.c.plan_id == plan_id)).mappings().all()
            for x in ts:
                c.execute(t.execution_tasks.insert().values(workspace_id=ws, execution_id=eid, task_key=x["key"],
                                                            state="waiting" if x["after"] else "ready", attempts=0,
                                                            outputs={}, updated=now))
            self.emit(c, ws, "execution.started", {"execution_id": eid, "plan_id": plan_id})
            for x in ts:
                if not x["after"]:
                    self.emit(c, ws, "task.ready", {"execution_id": eid, "task": x["key"], "plan_id": plan_id})
            self._operational_deliverable(c, p, pl, "in_progress", f"execution {eid} started")
        return self.get_execution(p, eid)

    def _operational_deliverable(self, c, p, pl, status, why):
        """Move a deliverable along as its approved plan runs: in_progress, delivered. Acceptance is a person's."""
        ws = p.workspace_id
        rec = self._records(ws, c).get(pl["project_id"])
        if not rec or rec.get("deleted"):
            return
        d = next((x for x in rec["deliverables"] if x["key"] == pl["deliverable_key"]), None)
        order = ["planned", "in_progress", "delivered", "accepted"]
        if not d or d["status"] not in order or order.index(d["status"]) >= order.index(status):
            return
        op = {"op": "set_deliverable", "project": pl["project_id"], "key": pl["deliverable_key"], "status": status}
        body, quoted = render(f"Plan {pl['id']} update", [op], why, "the service", self.clock.today().isoformat())
        path = self._request_document(c, ws, f"run-report-{ids.new('r', 6)[2:]}.md", body, "the service")
        self.apply_record_ops(c, p, ws, quoted, body, path, "request", f"the service ({why})", names={})

    def held_tasks(self, c, ws, plan_id) -> dict:
        """{task key: change request number} for tasks a proposed new plan version would change or remove."""
        pl = c.execute(sa.select(t.plans).where(t.plans.c.id == plan_id)).mappings().first()
        pending = c.execute(sa.select(t.plans).where(t.plans.c.workspace_id == ws, t.plans.c.project_id == pl["project_id"],
                                                     t.plans.c.deliverable_key == pl["deliverable_key"],
                                                     t.plans.c.state == "in_review", t.plans.c.version > pl["version"])
                            ).mappings().all()
        if not pending:
            return {}
        mine = {x["key"]: x["digest"] for x in c.execute(sa.select(t.tasks).where(t.tasks.c.plan_id == plan_id)).mappings()}
        held = {}
        for new in pending:
            theirs = {x["key"]: x["digest"] for x in c.execute(sa.select(t.tasks).where(t.tasks.c.plan_id == new["id"])
                                                               ).mappings()}
            cr = None
            for r in c.execute(sa.select(t.change_requests.c.number, t.change_requests.c.ops).where(
                    t.change_requests.c.workspace_id == ws, t.change_requests.c.state == "open")).mappings():
                if any(o.get("plan") == new["id"] for o in r["ops"]):
                    cr = r["number"]
            for k, dg in mine.items():
                if theirs.get(k) != dg:
                    held[k] = cr
        return held

    def get_execution(self, p, eid: str) -> dict:
        if p.kind != "run":
            p.need("read")
        ws = p.workspace_id
        self.sweep(ws)
        with self.db.tx(ws) as c:
            ex = c.execute(sa.select(t.executions).where(t.executions.c.id == eid, t.executions.c.workspace_id == ws)
                           ).mappings().first()
            if not ex:
                raise errors.NotFound(f"no execution {eid}")
            rows = {r["task_key"]: r for r in c.execute(sa.select(t.execution_tasks).where(
                t.execution_tasks.c.execution_id == eid)).mappings()}
            ts = c.execute(sa.select(t.tasks).where(t.tasks.c.plan_id == ex["plan_id"]).order_by(t.tasks.c.n)).mappings().all()
            held = self.held_tasks(c, ws, ex["plan_id"]) if ex["state"] == "running" else {}
            rs = c.execute(sa.select(t.runs).where(t.runs.c.execution_id == eid).order_by(t.runs.c.created)).mappings().all()
        return {"id": eid, "plan_id": ex["plan_id"], "state": ex["state"], "created": ex["created"],
                "finished": ex["finished"],
                "tasks": [{"key": x["key"], "title": x["title"], "after": x["after"], "needs": x["needs"],
                           "state": rows[x["key"]]["state"] if x["key"] in rows else "waiting",
                           "held_by_change_request": held.get(x["key"]) if x["key"] in held else None,
                           "attempts": rows[x["key"]]["attempts"] if x["key"] in rows else 0,
                           "outputs": rows[x["key"]]["outputs"] if x["key"] in rows else {}} for x in ts],
                "runs": [{"id": r["id"], "task": r["task_key"], "state": r["state"], "kind": r["kind"],
                          "runner": r["runner"], "created": r["created"], "ended": r["ended"]} for r in rs]}

    def ready_tasks(self, p, eid: str) -> list:
        ex = self.get_execution(p, eid)
        return [x for x in ex["tasks"] if x["state"] == "ready" and not x["held_by_change_request"]]

    def cancel_execution(self, p, eid: str) -> dict:
        p.need("runs:lease")
        ws = p.workspace_id
        with self.db.tx(ws) as c:
            ex = c.execute(sa.select(t.executions).where(t.executions.c.id == eid, t.executions.c.workspace_id == ws)
                           ).mappings().first()
            if not ex:
                raise errors.NotFound(f"no execution {eid}")
            if ex["state"] != "running":
                raise errors.Conflict(f"the execution is {ex['state']}")
            now = self.clock.stamp()
            c.execute(t.executions.update().where(t.executions.c.id == eid).values(state="cancelled", finished=now))
            c.execute(t.runs.update().where(t.runs.c.execution_id == eid,
                                            t.runs.c.state.in_(("leased", "provisioning", "running", "waiting")))
                      .values(state="cancelled", ended=now))
            self.emit(c, ws, "execution.cancelled", {"execution_id": eid})
        return self.get_execution(p, eid)

    def _migrate_executions(self, c, ws, old_plan, new_plan):
        """Running executions of the old version continue on the new one; unchanged finished tasks stay finished."""
        old_t = {x["key"]: x for x in c.execute(sa.select(t.tasks).where(t.tasks.c.plan_id == old_plan)).mappings()}
        new_t = {x["key"]: x for x in c.execute(sa.select(t.tasks).where(t.tasks.c.plan_id == new_plan)).mappings()}
        now = self.clock.stamp()
        for ex in c.execute(sa.select(t.executions).where(t.executions.c.plan_id == old_plan,
                                                          t.executions.c.state == "running")).mappings().all():
            rows = {r["task_key"]: r for r in c.execute(sa.select(t.execution_tasks).where(
                t.execution_tasks.c.execution_id == ex["id"])).mappings()}
            c.execute(t.executions.update().where(t.executions.c.id == ex["id"]).values(plan_id=new_plan))
            for k, r in rows.items():
                if k not in new_t:
                    c.execute(t.execution_tasks.delete().where(t.execution_tasks.c.execution_id == ex["id"],
                                                               t.execution_tasks.c.task_key == k))
            for k, x in new_t.items():
                same = k in old_t and old_t[k]["digest"] == x["digest"]
                r = rows.get(k)
                if r and same:
                    continue
                if r and r["state"] in ("leased", "running"):
                    c.execute(t.runs.update().where(t.runs.c.execution_id == ex["id"], t.runs.c.task_key == k,
                                                    t.runs.c.state.in_(("leased", "provisioning", "running", "waiting")))
                              .values(state="cancelled", ended=now))
                values = {"state": "waiting", "attempts": 0, "outputs": {}, "updated": now}
                if r:
                    c.execute(t.execution_tasks.update().where(t.execution_tasks.c.execution_id == ex["id"],
                                                               t.execution_tasks.c.task_key == k).values(**values))
                else:
                    c.execute(t.execution_tasks.insert().values(workspace_id=ws, execution_id=ex["id"], task_key=k, **values))
            self._promote(c, ws, ex["id"])
            self.emit(c, ws, "execution.migrated", {"execution_id": ex["id"], "from_plan": old_plan, "to_plan": new_plan})

    def _release_held(self, c, ws, rejected_plan):
        pl = c.execute(sa.select(t.plans).where(t.plans.c.id == rejected_plan)).mappings().first()
        for ex in c.execute(sa.select(t.executions).join(t.plans, t.plans.c.id == t.executions.c.plan_id).where(
                t.plans.c.project_id == pl["project_id"], t.plans.c.deliverable_key == pl["deliverable_key"],
                t.executions.c.state == "running")).mappings().all():
            self.emit(c, ws, "execution.resumed", {"execution_id": ex["id"], "reason": "the proposed plan was rejected"})

    def _promote(self, c, ws, eid):
        """Waiting tasks whose tasks-waited-on are all done become ready."""
        ex = c.execute(sa.select(t.executions).where(t.executions.c.id == eid)).mappings().first()
        ts = {x["key"]: x for x in c.execute(sa.select(t.tasks).where(t.tasks.c.plan_id == ex["plan_id"])).mappings()}
        rows = {r["task_key"]: r for r in c.execute(sa.select(t.execution_tasks).where(
            t.execution_tasks.c.execution_id == eid)).mappings()}
        now = self.clock.stamp()
        for k, r in rows.items():
            if r["state"] == "waiting" and all(rows.get(a, {}).get("state") == "done" for a in ts[k]["after"]):
                c.execute(t.execution_tasks.update().where(t.execution_tasks.c.execution_id == eid,
                                                           t.execution_tasks.c.task_key == k)
                          .values(state="ready", updated=now))
                self.emit(c, ws, "task.ready", {"execution_id": eid, "task": k, "plan_id": ex["plan_id"]})


__all__ = ["PlansMixin", "check_tasks", "topo", "task_digest", "jsonable"]
