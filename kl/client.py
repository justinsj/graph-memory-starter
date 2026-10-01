"""A thin Python client for the REST API.

    from kl.client import Client, RunClient
    kl = Client("https://kl.example.com", "kl_...")            # a person's or a service account's key
    cr = kl.create_project(id="refunds-dashboard", title="Refunds dashboard", description="...")
    kl.approve(cr["id"])                                        # a person with the approver role

    run = RunClient.from_env()                                  # inside a machine: KL_API_URL, KL_RUN_TOKEN, KL_RUN_ID
    brief = run.brief()
    run.complete(outputs={...}, check_results={"done": True})
"""
import base64
import os
import time

import httpx


class KLError(Exception):
    def __init__(self, status: int, problem: dict):
        self.status, self.problem = status, problem
        detail = problem.get("detail") or problem
        reasons = problem.get("problems") or []
        super().__init__(f"{status}: {detail}" + ("".join(f"\n  - {r}" for r in reasons)))


class Client:
    def __init__(self, url: str, token: str, workspace: str = None, timeout: float = 60, http=None):
        self.url = url.rstrip("/")
        self.headers = {"Authorization": f"Bearer {token}"}
        if workspace:
            self.headers["KL-Workspace"] = workspace
        self.http = http or httpx.Client(timeout=timeout)

    def _req(self, method, path, json=None, params=None, headers=None, raw=False):
        r = self.http.request(method, f"{self.url}{path}" if not path.startswith("http") else path, json=json,
                              params={k: v for k, v in (params or {}).items() if v is not None},
                              headers={**self.headers, **(headers or {})})
        if r.status_code >= 400:
            try:
                body = r.json()
            except ValueError:
                body = {"detail": r.text}
            raise KLError(r.status_code, body)
        if raw:
            return r
        return r.json() if r.content else None

    # ---- workspace ----------------------------------------------------------------------------------
    def whoami(self):
        return self._req("GET", "/v1/whoami")

    def add_member(self, email, name, role):
        return self._req("POST", "/v1/members", {"email": email, "name": name, "role": role})

    def create_service_account(self, name, scopes):
        return self._req("POST", "/v1/service-accounts", {"name": name, "scopes": list(scopes)})

    def create_key(self, name, scopes=None):
        return self._req("POST", "/v1/keys", {"name": name, "scopes": scopes})

    # ---- sources ------------------------------------------------------------------------------------
    def ingest(self, name, text=None, data: bytes = None, kind="document", collection="", external_id=None, uri=None,
               extraction=None, changes=None, on=None, near_duplicates=None):
        body = {"name": name, "kind": kind, "collection": collection, "external_id": external_id, "uri": uri,
                "extraction": extraction, "changes": changes, "on": on, "near_duplicates": near_duplicates}
        if data is not None:
            body["content_base64"] = base64.b64encode(data).decode()
        else:
            body["text"] = text
        return self._req("POST", "/v1/sources", {k: v for k, v in body.items() if v is not None})

    def manifest(self, collection, items, retract_missing=False):
        return self._req("PUT", f"/v1/collections/{collection}/manifest",
                         {"items": items, "retract_missing": retract_missing})

    def sources(self, **params):
        return self._req("GET", "/v1/sources", params=params)

    def source(self, doc_id):
        return self._req("GET", f"/v1/sources/{doc_id}")

    def submit_extraction(self, doc_id, extraction, version_id=None):
        return self._req("POST", f"/v1/sources/{doc_id}/extraction", {"extraction": extraction, "version_id": version_id})

    def retract(self, doc_id):
        return self._req("DELETE", f"/v1/sources/{doc_id}")

    def restore(self, doc_id):
        return self._req("POST", f"/v1/sources/{doc_id}:restore")

    def job(self, job_id):
        return self._req("GET", f"/v1/jobs/{job_id}")

    # ---- projects -----------------------------------------------------------------------------------
    def projects(self, **params):
        return self._req("GET", "/v1/projects", params=params)

    def project(self, pid, include=()):
        return self._req("GET", f"/v1/projects/{pid}", params={"include": ",".join(include) or None})

    def create_project(self, approve=False, **body):
        return self._req("POST", "/v1/projects", body, params={"approve": str(approve).lower()})

    def patch_project(self, pid, if_match=None, approve=False, **patch):
        return self._req("PATCH", f"/v1/projects/{pid}", patch, params={"approve": str(approve).lower()},
                         headers={"If-Match": f'"v{if_match}"'} if if_match is not None else None)

    def delete_project(self, pid, reason="", approve=False, if_match=None):
        return self._req("DELETE", f"/v1/projects/{pid}", params={"reason": reason, "approve": str(approve).lower()},
                         headers={"If-Match": f'"v{if_match}"'} if if_match is not None else None)

    def restore_project(self, pid, reason="", approve=False):
        return self._req("POST", f"/v1/projects/{pid}:restore", params={"reason": reason, "approve": str(approve).lower()})

    def add_deliverable(self, pid, key, title, approve=False, **extra):
        return self._req("POST", f"/v1/projects/{pid}/deliverables", {"key": key, "title": title, **extra},
                         params={"approve": str(approve).lower()})

    def propose_thesis(self, pid, approve=False, **thesis):
        return self._req("POST", f"/v1/projects/{pid}/thesis", thesis, params={"approve": str(approve).lower()})

    def research(self, pid):
        return self._req("POST", f"/v1/projects/{pid}:research")

    def answer_number(self, pid, key, value, approve=False, **extra):
        return self._req("POST", f"/v1/projects/{pid}/numbers/{key}", {"value": value, **extra},
                         params={"approve": str(approve).lower()})

    def estimate_effort(self, pid, days, approve=False, **extra):
        return self._req("POST", f"/v1/projects/{pid}/effort", {"days": days, **extra},
                         params={"approve": str(approve).lower()})

    def impact(self, pid):
        return self._req("GET", f"/v1/projects/{pid}/impact")

    def priorities(self):
        return self._req("GET", "/v1/priorities")

    def changes(self, ops, reason="", dry_run=False, approve=False, title=None):
        return self._req("POST", "/v1/changes", {"ops": ops, "reason": reason, "title": title},
                         params={"dry_run": str(dry_run).lower(), "approve": str(approve).lower()})

    # ---- review -------------------------------------------------------------------------------------
    def change_requests(self, **params):
        return self._req("GET", "/v1/change-requests", params=params)

    def change_request(self, cid):
        return self._req("GET", f"/v1/change-requests/{cid}")

    def approve(self, cid, ops=None, edits=None, note=""):
        return self._req("POST", f"/v1/change-requests/{cid}:approve", {"ops": ops, "edits": edits, "note": note})

    def reject(self, cid, note=""):
        return self._req("POST", f"/v1/change-requests/{cid}:reject", {"note": note})

    def update_change_request(self, cid, ops=None, reason=None):
        return self._req("PATCH", f"/v1/change-requests/{cid}", {"ops": ops, "reason": reason})

    # ---- plans and execution ----------------------------------------------------------------------------
    def propose_plan(self, pid, key, **plan):
        return self._req("POST", f"/v1/projects/{pid}/deliverables/{key}/plans", plan)

    def plan(self, plan_id):
        return self._req("GET", f"/v1/plans/{plan_id}")

    def start_execution(self, plan_id):
        return self._req("POST", f"/v1/plans/{plan_id}/executions")

    def execution(self, eid):
        return self._req("GET", f"/v1/executions/{eid}")

    def lease(self, eid, task, runner_id, offers=(), kind="agent", meta=None):
        return self._req("POST", f"/v1/executions/{eid}/tasks/{task}/runs",
                         {"runner": {"id": runner_id, "offers": list(offers), "meta": meta or {}}, "kind": kind})

    def run_event(self, rid, type_, message="", data=None):
        return self._req("POST", f"/v1/runs/{rid}/events", {"type": type_, "message": message, "data": data or {}})

    def cancel_run(self, rid):
        return self._req("POST", f"/v1/runs/{rid}:cancel")

    def run(self, rid):
        return self._req("GET", f"/v1/runs/{rid}")

    def questions(self, open_only=True):
        return self._req("GET", "/v1/questions", params={"open_only": str(open_only).lower()})

    def answer(self, qid, answer):
        return self._req("POST", f"/v1/questions/{qid}:answer", {"answer": answer})

    # ---- context ------------------------------------------------------------------------------------
    def context(self, question, as_of=None, project=None, budget_tokens=None, session_id=None):
        return self._req("POST", "/v1/context", {"question": question, "as_of": as_of, "project": project,
                                                 "budget_tokens": budget_tokens, "session_id": session_id})

    def search(self, q, types=None, limit=20):
        return self._req("GET", "/v1/search", params={"q": q, "types": ",".join(types) if types else None, "limit": limit})

    def entity(self, eid):
        return self._req("GET", f"/v1/entities/{eid}")

    def claim(self, cid):
        return self._req("GET", f"/v1/claims/{cid}")

    def code_impact(self, symbol):
        return self._req("GET", "/v1/code/impact", params={"symbol": symbol})

    # ---- events -------------------------------------------------------------------------------------
    def events(self, after=0, types=None, wait=0, limit=100):
        return self._req("GET", "/v1/events", params={"after": after, "types": ",".join(types) if types else None,
                                                     "wait": wait, "limit": limit})

    def create_webhook(self, url, types=(), secret=None):
        return self._req("POST", "/v1/webhooks", {"url": url, "types": list(types), "secret": secret})


class RunClient(Client):
    """The agent's side, for one run: everything acts on this run."""

    def __init__(self, url, token, run_id, **kw):
        super().__init__(url, token, **kw)
        self.run_id = run_id
        self._last_beat = 0.0

    @classmethod
    def from_env(cls, **kw):
        return cls(os.environ["KL_API_URL"], os.environ["KL_RUN_TOKEN"], os.environ["KL_RUN_ID"], **kw)

    def brief(self, budget_tokens=1500):
        return self._req("GET", f"/v1/runs/{self.run_id}/brief", params={"budget_tokens": budget_tokens})

    def event(self, type_, message="", data=None):
        self._last_beat = time.time()
        return self.run_event(self.run_id, type_, message, data)

    def heartbeat(self, message="", every=None):
        if every and time.time() - self._last_beat < every:
            return None
        return self.event("heartbeat", message)

    def log(self, message):
        return self.event("log", message)

    def attach(self, kind, name, text=None, data: bytes = None, uri=None, meta=None):
        body = {"kind": kind, "name": name, "text": text, "uri": uri, "meta": meta or {}}
        if data is not None:
            body["content_base64"] = base64.b64encode(data).decode()
        return self._req("POST", f"/v1/runs/{self.run_id}/artifacts", {k: v for k, v in body.items() if v is not None})

    def ask(self, text):
        return self._req("POST", f"/v1/runs/{self.run_id}/questions", {"text": text})

    def question(self, qid):
        return self._req("GET", f"/v1/questions/{qid}")

    def wait_for_answer(self, qid, poll=2.0, timeout=3600):
        end = time.time() + timeout
        while time.time() < end:
            q = self.question(qid)
            if q["answer"] is not None:
                return q
            time.sleep(poll)
        raise TimeoutError("no answer yet")

    def propose(self, ops, reason=""):
        return self._req("POST", f"/v1/runs/{self.run_id}/change-requests", {"ops": ops, "reason": reason})

    def complete(self, outputs=None, check_results=None, evidence=None, idempotency_key=None):
        return self._req("POST", f"/v1/runs/{self.run_id}:complete",
                         {"outputs": outputs or {}, "check_results": check_results or {}, "evidence": evidence or [],
                          "idempotency_key": idempotency_key})

    def fail(self, reason, idempotency_key=None):
        return self._req("POST", f"/v1/runs/{self.run_id}:fail", {"reason": reason, "idempotency_key": idempotency_key})
