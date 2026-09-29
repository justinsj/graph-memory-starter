"""Events: every change, once, in order. Read by cursor, streamed, or delivered to webhooks.

Each change writes its events into the outbox in the same transaction, so an
event exists exactly when its change does. Clients read them three ways:
- GET /v1/events?after=<seq>: a page, optionally waiting (long poll) for new ones;
- GET /v1/events/stream: server-sent events;
- webhooks: POSTed to a URL with a signature, retried until delivered, in order.

Signature: header KL-Signature: t=<unix seconds>,v1=<hex HMAC-SHA256 of
"<t>.<body>" with the webhook's secret>. Check it, and that t is recent.
"""
import hashlib
import hmac
import json
import threading
import time

import httpx
import sqlalchemy as sa

from . import db as t
from . import errors, ids

TYPES = ("source.ingested", "source.retracted", "source.restored", "job.done", "job.failed",
         "change_request.opened", "change_request.updated", "change_request.applied", "change_request.rejected",
         "change_request.stale", "project.updated", "plan.proposed", "plan.approved", "plan.rejected",
         "execution.started", "execution.migrated", "execution.resumed", "execution.done", "execution.failed",
         "execution.cancelled", "task.ready", "task.done", "task.failed", "run.leased", "run.provisioning",
         "run.running", "run.progress", "run.artifact", "run.succeeded", "run.failed", "run.lost", "run.cancelled",
         "question.asked", "question.answered", "deliverable.accepted")


def sign(secret: str, body: bytes, when: int = None) -> str:
    when = int(when or time.time())
    mac = hmac.new(secret.encode(), f"{when}.".encode() + body, hashlib.sha256).hexdigest()
    return f"t={when},v1={mac}"


def verify(secret: str, body: bytes, header: str, tolerance: int = 300, now: int = None) -> bool:
    try:
        parts = dict(x.split("=", 1) for x in header.split(","))
        when = int(parts["t"])
    except (ValueError, KeyError):
        return False
    if abs(int(now or time.time()) - when) > tolerance:
        return False
    return hmac.compare_digest(sign(secret, body, when).split("v1=")[1], parts.get("v1", ""))


class EventsMixin:

    def _event_out(self, r) -> dict:
        return {"seq": r["seq"], "type": r["type"], "data": r["data"], "created": r["created"]}

    def list_events(self, p, after: int = 0, types: list = None, limit: int = 100, wait: float = 0) -> dict:
        if p.kind != "run":
            p.need("read")
        ws = p.workspace_id
        deadline = time.time() + min(max(wait or 0, 0), 60)
        while True:
            with self.db.tx(ws) as c:
                q = sa.select(t.outbox).where(t.outbox.c.workspace_id == ws, t.outbox.c.seq > int(after or 0))
                if types:
                    q = q.where(t.outbox.c.type.in_(types))
                rows = c.execute(q.order_by(t.outbox.c.seq).limit(limit)).mappings().all()
            if rows or time.time() >= deadline:
                break
            with self._events_cond:
                self._events_cond.wait(timeout=min(0.5, max(0.01, deadline - time.time())))
        items = [self._event_out(r) for r in rows]
        if p.kind == "run":  # a run sees what concerns its own run
            items = [e for e in items if e["data"].get("run_id") == p.run_id]
        return {"items": items, "next_after": rows[-1]["seq"] if rows else int(after or 0)}

    # ---- webhooks --------------------------------------------------------------------------------

    def create_webhook(self, p, url: str, types: list = None, secret: str = None, from_now: bool = True) -> dict:
        p.need("webhooks:manage")
        if not url.startswith(("http://", "https://")):
            raise errors.Invalid("a webhook URL starts with http:// or https://")
        bad = sorted(set(types or []) - set(TYPES))
        if bad:
            raise errors.Invalid(f"unknown event types: {', '.join(bad)}", problems=[f"known: {', '.join(TYPES)}"])
        ws = p.workspace_id
        wid = ids.new("whk")
        secret = secret or ids.token("whsec")
        with self.db.tx(ws) as c:
            start = c.execute(sa.select(sa.func.max(t.outbox.c.seq)).where(t.outbox.c.workspace_id == ws)).scalar() or 0
            c.execute(t.webhooks.insert().values(id=wid, workspace_id=ws, url=url, secret=secret, types=list(types or []),
                                                 after_seq=start if from_now else 0, failures=0, last_error=None,
                                                 active=True, created=self.clock.stamp()))
        return {"id": wid, "url": url, "types": list(types or []), "secret": secret,
                "note": "the secret signs every delivery (KL-Signature); it is shown once"}

    def list_webhooks(self, p) -> list:
        p.need("webhooks:manage")
        with self.db.tx(p.workspace_id) as c:
            return [{"id": w["id"], "url": w["url"], "types": w["types"], "active": w["active"],
                     "delivered_up_to": w["after_seq"], "failures": w["failures"], "last_error": w["last_error"]}
                    for w in c.execute(sa.select(t.webhooks).where(t.webhooks.c.workspace_id == p.workspace_id)).mappings()]

    def delete_webhook(self, p, wid: str) -> dict:
        p.need("webhooks:manage")
        with self.db.tx(p.workspace_id) as c:
            n = c.execute(t.webhooks.delete().where(t.webhooks.c.id == wid,
                                                    t.webhooks.c.workspace_id == p.workspace_id)).rowcount
        if not n:
            raise errors.NotFound(f"no webhook {wid}")
        return {"id": wid, "deleted": True}

    def deliver_webhooks(self, timeout: float = 5.0) -> dict:
        """One delivery round for every workspace: each webhook gets its next events, in order."""
        sent = failed = 0
        with self.db.tx(system=True) as c:
            hooks = c.execute(sa.select(t.webhooks).where(t.webhooks.c.active.is_(True))).mappings().all()
        for w in hooks:
            with self.db.tx(w["workspace_id"]) as c:
                q = sa.select(t.outbox).where(t.outbox.c.workspace_id == w["workspace_id"],
                                              t.outbox.c.seq > w["after_seq"])
                if w["types"]:
                    q = q.where(t.outbox.c.type.in_(w["types"]))
                rows = c.execute(q.order_by(t.outbox.c.seq).limit(50)).mappings().all()
            upto, error = w["after_seq"], None
            for r in rows:
                body = json.dumps({"id": f"evt_{r['workspace_id']}_{r['seq']}", **self._event_out(r)}).encode()
                try:
                    resp = httpx.post(w["url"], content=body, timeout=timeout, headers={
                        "Content-Type": "application/json", "KL-Event": r["type"], "KL-Delivery": f"{w['id']}:{r['seq']}",
                        "KL-Signature": sign(w["secret"], body)})
                    if resp.status_code >= 300:
                        raise RuntimeError(f"HTTP {resp.status_code}")
                except Exception as e:  # noqa: BLE001  retried next round, in order
                    error = f"{type(e).__name__}: {e}"
                    failed += 1
                    break
                upto = r["seq"]
                sent += 1
            with self.db.tx(w["workspace_id"]) as c:
                c.execute(t.webhooks.update().where(t.webhooks.c.id == w["id"]).values(
                    after_seq=upto, failures=(w["failures"] + 1) if error else 0, last_error=error))
        return {"sent": sent, "failed": failed}

    def start_background(self, every: float = 2.0):
        """Deliver webhooks and sweep lost runs until stop_background()."""
        self._bg_stop = threading.Event()

        def loop():
            while not self._bg_stop.wait(every):
                try:
                    self.sweep()
                    self.deliver_webhooks()
                except Exception:  # noqa: BLE001, S110  next round tries again
                    pass
        th = threading.Thread(target=loop, daemon=True, name="kl-background")
        th.start()
        return th

    def stop_background(self):
        if getattr(self, "_bg_stop", None):
            self._bg_stop.set()
