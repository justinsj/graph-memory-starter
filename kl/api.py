"""The REST API: /v1, described by the OpenAPI document it serves at /openapi.json.

Every request carries Authorization: Bearer <key or token>. Errors are RFC 9457
problems (application/problem+json) with a list of reasons. Writes that change
a project return 202 and the change request they opened; nothing applies until
a person approves it.
"""
import asyncio
import base64
import contextlib
import json
from typing import Any, Literal, Optional, Union

from fastapi import Body, Depends, FastAPI, File, Form, Header, Query, Request, Response, UploadFile
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from . import __version__, errors
from .core import Principal

TAGS = [
    {"name": "workspaces", "description": "Workspaces, members, service accounts and keys."},
    {"name": "sources", "description": "Files in: any set of files, deduplicated, extracted, checked. For input handlers."},
    {"name": "projects", "description": "Projects, read as approved; every write opens a change request. For task apps."},
    {"name": "impact", "description": "Each project's thesis, the numbers behind it (found, asked, answered, estimated), "
                                      "estimated effort, and the priorities they give."},
    {"name": "review", "description": "Change requests: approve (all, some, or edited) or reject. Only people approve."},
    {"name": "plans", "description": "A deliverable's plan: a graph of tasks, general or imported from an OpenSpec change."},
    {"name": "execution", "description": "The orchestrator's side of the run protocol: executions and leases."},
    {"name": "runs", "description": "The agent's side of the run protocol: brief, events, artifacts, questions, complete."},
    {"name": "context", "description": "Reading the graph: context for a question, search, entities, code impact."},
    {"name": "events", "description": "Every change, once, in order: a cursor feed, a stream, and signed webhooks."},
]


def _b64(value: Optional[str]) -> Optional[bytes]:
    if value is None:
        return None
    try:
        return base64.b64decode(value, validate=True)
    except Exception:  # noqa: BLE001
        raise errors.Invalid("content_base64 is not valid base64") from None


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Open(BaseModel):
    model_config = ConfigDict(extra="allow")


# ---- request bodies ------------------------------------------------------------------------------

class WorkspaceIn(Model):
    slug: str = Field(examples=["acme"])
    name: str = Field(examples=["Acme Ltd"])
    settings: dict = {}


class MemberIn(Model):
    email: str
    name: str
    role: Literal["viewer", "editor", "approver", "admin"]


class ServiceAccountIn(Model):
    name: str = Field(examples=["orchestrator"])
    scopes: list[str] = Field(examples=[["read", "context:read", "runs:lease"]])


class KeyIn(Model):
    name: str
    scopes: Optional[list[str]] = None


class SourceIn(Model):
    name: str = Field(description="File name, e.g. refund-policy.md; with the collection, what identifies the document "
                                  "when there is no external_id", examples=["refund-policy.md"])
    text: Optional[str] = Field(None, description="The file's text")
    content_base64: Optional[str] = Field(None, description="Or its bytes, base64 (zips for code and openspec)")
    kind: Literal["document", "transcript", "request", "session", "code", "openspec"] = "document"
    collection: str = Field("", description="A folder, drive or connector the file belongs to")
    external_id: Optional[str] = Field(None, description="The file's id in the system it came from")
    uri: Optional[str] = None
    extraction: Optional[dict] = Field(None, description="Your own extraction (nodes, edges, aliases); checked like any other")
    changes: Optional[list[dict]] = Field(None, description="For a transcript or request: the change-set operations it "
                                                           "supports, each quoting it; opened as a change request")
    on: Optional[str] = Field(None, description="The input's date, YYYY-MM-DD (transcripts)")
    near_duplicates: Optional[Literal["link", "ingest", "review"]] = None


class BatchIn(Model):
    items: list[SourceIn]


class ManifestItem(Model):
    name: str
    external_id: Optional[str] = None
    sha256: str = Field(description="SHA-256 of the file's bytes")


class ManifestIn(Model):
    items: list[ManifestItem]
    retract_missing: bool = False


class ExtractionIn(Model):
    extraction: dict
    version_id: Optional[str] = None


class DeliverableIn(Model):
    key: str = Field(examples=["D1"])
    title: str
    owner: Optional[str] = None
    due: Optional[str] = None
    reason: str = ""


class ProjectIn(Model):
    id: str = Field(description="lowercase words joined by hyphens", examples=["refunds-dashboard"])
    title: str
    description: str
    owner: Optional[str] = None
    requested_by: Optional[str] = None
    due: Optional[Any] = Field(None, description='"end of October", or {"text": "...", "date": "YYYY-MM-DD"}')
    status: Optional[str] = None
    aliases: Optional[list[str]] = None
    deliverables: Optional[list[DeliverableIn]] = None
    reason: str = ""


class ProjectPatch(Model):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    status_from: Optional[str] = None
    owner: Optional[str] = None
    requested_by: Optional[str] = None
    due: Optional[Any] = None
    reason: str = ""


class NumberSpec(Model):
    key: str = Field(description="lowercase words joined by underscores", examples=["failures_a_year"])
    label: str = Field(description="The words a document stating it would use: the research looks for a fact with "
                                   "every one of them", examples=["tagging report failures"])
    unit: str = Field(examples=["failures a year"])
    ask: Optional[str] = Field(None, description="Who to ask if no document holds it (a name the graph knows); "
                                                 "default the project's owner, else whoever asked for it")
    question: Optional[str] = None


class ThesisIn(Model):
    change: str = Field(description="What is done", examples=["support moves to a new helpdesk"])
    outcome: str = Field(description="What gets better, countably",
                         examples=["the support hours lost to broken tagging reports"])
    direction: Literal["reduce", "increase", "improve"]
    unit: str = Field(description="The outcome's unit", examples=["hours a year"])
    formula: list[Union[str, dict]] = Field(description="Number keys multiplied together; a constant as "
                                                        '{"value": 52, "label": "weeks a year"}',
                                            examples=[["failures_a_year", "support_agents", "hours_per_failure"]])
    reach: Optional[str] = Field(None, description="A number key: the clients or people the change touches")
    because: Optional[dict] = Field(None, description='{"quote": ...}: a line from the project\'s inputs that shows '
                                                      "why it matters (its source is found for you)")
    numbers: list[NumberSpec] = []
    reason: str = ""


class NumberIn(Model):
    value: Union[int, float]
    status: Literal["answered", "estimated"] = "answered"
    answer: Optional[str] = Field(None, description="The answer in the person's words; it is quoted, so it should "
                                                    "state the figure", examples=["About 6 hours per agent."])
    basis: Optional[str] = Field(None, description="For an estimate: what it rests on")
    by: Optional[str] = Field(None, description="Who gave it, if not the caller")
    reason: str = ""


class EffortIn(Model):
    days: Union[int, float] = Field(description="Person-days", examples=[15])
    basis: Optional[str] = None
    by: Optional[str] = Field(None, description="Who estimated it, if not the caller")
    reason: str = ""


class ChangesIn(Model):
    ops: list[dict] = Field(description="Operations: projects/model.py's (create_project, set_status, set_field, "
                                        "add_dependency, add_deliverable, set_deliverable, set_step, add_question, "
                                        "close_question, add_decision, delete_project, restore_project, "
                                        "set_thesis, set_number, set_effort), or "
                                        "activate_version, retract_source")
    reason: str = ""
    title: Optional[str] = None


class ApproveIn(Model):
    ops: Optional[list[int]] = Field(None, description="Which operations (1-based); all when left out")
    edits: Optional[dict[str, dict]] = Field(None, description='{"2": {"value": "on_hold"}}: change values before approving')
    note: str = ""


class RejectIn(Model):
    note: str = ""


class CRPatch(Model):
    ops: Optional[list[dict]] = None
    reason: Optional[str] = None


class CheckIn(Model):
    id: str
    kind: Literal["auto", "person"] = "auto"
    description: str = ""


class TaskIn(Model):
    key: str
    title: str
    instructions: str = ""
    after: list[str] = []
    needs: list[str] = Field([], description="What a runner must offer, e.g. repo:acme/shop, browser, python")
    checks: list[CheckIn] = []
    gate: bool = Field(False, description="A person looks before the task counts as done")
    outputs: list[str] = []
    retries: int = 2


class PlanIn(Model):
    kind: Literal["general", "openspec"] = "general"
    title: Optional[str] = None
    summary: str = ""
    design: str = ""
    tasks: Optional[list[TaskIn]] = None
    checks: list[CheckIn] = []
    change: Optional[str] = Field(None, description="openspec: the change's name")
    files: Optional[dict[str, str]] = Field(None, description="openspec: {path in the change folder: text}")
    parallel_sections: bool = False
    needs: Optional[list[str]] = None
    reason: str = ""


class RunnerIn(Model):
    id: str
    offers: list[str] = []
    meta: dict = {}


class LeaseIn(Model):
    runner: RunnerIn
    kind: Literal["agent", "script", "person"] = "agent"


class RunEventIn(Model):
    type: str = Field(description="orchestrator: provisioning | heartbeat | log; agent: started | heartbeat | log | progress")
    message: str = ""
    data: dict = {}


class ArtifactIn(Model):
    kind: Literal["file", "pull_request", "test_report", "text", "link"]
    name: str
    text: Optional[str] = None
    content_base64: Optional[str] = None
    uri: Optional[str] = None
    meta: dict = {}


class QuestionIn(Model):
    text: str


class AnswerIn(Model):
    answer: str


class CompleteIn(Model):
    outputs: dict = {}
    check_results: dict = Field({}, description='{"check id": true} or {"check id": {"passed": true, "evidence": "..."}}')
    evidence: list = []
    idempotency_key: Optional[str] = None


class FailIn(Model):
    reason: str = ""
    idempotency_key: Optional[str] = None


class ContextIn(Model):
    question: str = Field(examples=["A customer wants an £800 refund in March. Who signs it off?"])
    as_of: Optional[str] = Field(None, description="YYYY-MM-DD; today when left out")
    project: Optional[str] = Field(None, description="A project to lean towards")
    budget_tokens: Optional[int] = None
    session_id: Optional[str] = Field(None, description="Quotes already given in this session are not repeated")


class WebhookIn(Model):
    url: str
    types: list[str] = []
    secret: Optional[str] = None


# ---- the app ----------------------------------------------------------------------------------------

DOCS = {  # route: (summary, description), so the OpenAPI document explains each call
    "health": ("Health", "Whether the service is up, and its version."),
    "create_workspace": ("Create a workspace", "The operator's root key only."),
    "get_workspace": ("This workspace", "The caller's workspace and its settings."),
    "update_settings": ("Change settings", "Admins: self_approval, review_extractions, near_duplicates, "
                                           "max_concurrent_runs, max_storage_bytes, impact_research, unit_values, "
                                           "currency."),
    "whoami": ("Who am I", "The caller: kind (user, service, run, root), role, scopes, workspace."),
    "list_members": ("Members", "People in the workspace and their roles."),
    "add_member": ("Add a person", "Admins. The person signs in with the OIDC issuer, matched by email the first time."),
    "create_service_account": ("Create a service account", "Admins. Returns its key once. Never review:approve."),
    "create_key": ("Create a personal key", "A person's own key, with their role's scopes or fewer. Shown once."),
    "revoke_key": ("Revoke a key", "Admins. The key stops working at once."),
    "create_source": ("Send a file", "Text or base64 bytes. Deduplicated, extracted (or awaiting your extraction), "
                                     "checked against its text, and in the graph when its job is done. Transcripts "
                                     "and requests open a change request."),
    "upload_source": ("Send a file (multipart)", "The same as POST /v1/sources, as a multipart upload."),
    "batch_sources": ("Send many files", "One answer per file; one failing does not stop the others."),
    "manifest": ("Sync a collection", "Send a folder's full listing: the answer says what to upload, and what is gone "
                                      "(retracted with retract_missing)."),
    "list_sources": ("Sources", "Documents, by collection or kind, with their current version."),
    "get_source": ("One source", "Its versions, what deduplication decided, other places it was seen, its facts."),
    "get_source_content": ("A source's text", "The current version's text, as stored and quoted."),
    "submit_extraction": ("Send an extraction", "Nodes, edges and aliases for a document awaiting one. Checked like "
                                                "any other."),
    "retract_source": ("Retract a source", "Soft: its facts leave the graph; restore brings them back."),
    "restore_source": ("Restore a source", "Its current version is back in the graph, if the graph still builds."),
    "get_job": ("A job", "An ingestion or extraction: stage, status, problems, result."),
    "list_projects": ("Projects", "Approved state. Filters: status, owner, due_before, due_after, q. include=pending "
                                  "adds open change requests; include=impact adds each thesis and its figures. "
                                  "sort=priority: ranked projects first, by projected impact per person-day."),
    "propose_thesis": ("Propose a thesis", "If <change>, <outcome> will <reduce|increase|improve> by potentially "
                                           "<amount> <unit>. The amount is the product of the formula's numbers, "
                                           "researched at once: each is found in the graph (quoted from its document) "
                                           "or asked of a person. One change request."),
    "research": ("Research the numbers", "Look again for a project's missing numbers, and ask people for the rest; "
                                         "drafts a thesis first if there is none. Opens a change request, or says "
                                         "there is nothing new."),
    "answer_number": ("Give a number", "An answer, or an estimate (status=estimated) that stays marked as one. "
                                       "Opens a change request; approve=true applies it at once."),
    "estimate_effort": ("Estimate the effort", "Person-days, and what the estimate rests on. Through a change "
                                               "request."),
    "project_impact": ("A project's impact", "The thesis as a sentence, projected impact with its working, each "
                                             "number with where it came from, estimated effort, impact per "
                                             "person-day, and its place in the priorities."),
    "priorities": ("Priorities", "Open projects ranked by projected impact per person-day: within each unit, or in "
                                 "money across units when settings.unit_values prices them. Projects still missing "
                                 "numbers or an effort are listed apart, with what they lack."),
    "get_project": ("One project", "The record and its summary; the ETag is its version. include=events,plans,pending."),
    "create_project": ("Create a project", "Opens a change request (202). approve=true: a person who may approve "
                                           "applies it at once (200)."),
    "patch_project": ("Edit a project", "Title, description, status, owner, requested_by, due. Send If-Match. Opens a "
                                        "change request; a move the rules forbid is refused (422)."),
    "delete_project": ("Delete a project", "Soft, through a change request: it leaves recall, search and the list."),
    "restore_project": ("Restore a project", "Through a change request."),
    "add_deliverable": ("Add a deliverable", "Through a change request."),
    "changes": ("Propose operations", "Any change-set operations, in one change request. dry_run=true returns the "
                                      "diff and problems and opens nothing."),
    "project_events": ("A project's history", "Every applied change: what, when, who proposed and approved it, and "
                                              "the source it quotes."),
    "list_crs": ("Change requests", "The review queue: by state (open, applied, rejected, stale), project, proposer."),
    "get_cr": ("One change request", "Its operations, diff, problems, and every decision on it."),
    "patch_cr": ("Edit a change request", "Its proposer or an approver; checked again. Brings a stale request up to "
                                          "date."),
    "approve_cr": ("Approve", "People only. All operations, some (ops), or edited values (edits). Checked again "
                              "against what changed since; a request that no longer applies becomes stale (409)."),
    "reject_cr": ("Reject", "People only, with a note."),
    "propose_plan": ("Propose a plan", "For one deliverable: general (tasks as JSON) or openspec (a change folder's "
                                       "files). Opens a change request; approval is the go-ahead."),
    "list_plans": ("Plans", "By project and state."),
    "get_plan": ("One plan", "Its tasks, checks, and the OpenSpec change it came from."),
    "start_execution": ("Run a plan", "An approved plan. Tasks with nothing to wait on are ready."),
    "get_execution": ("An execution", "Each task's state (and whether a proposed plan change holds it), and every run."),
    "cancel_execution": ("Cancel an execution", "Its active runs are cancelled."),
    "lease": ("Lease a task", "To a runner offering what the task needs. Returns the run id, a run token, and the env "
                              "to inject into the machine."),
    "cancel_run": ("Cancel a run", "The task goes back to ready."),
    "get_run": ("A run", "State, lease, events, artifacts, questions, outcome."),
    "brief": ("The run's brief", "The task, its checks, upstream outputs, project, requirements, and context. "
                                 "Fetching it renews the lease: the agent has started."),
    "run_event": ("Run events", "Orchestrator: provisioning, heartbeat, log. Agent: started, heartbeat, log, "
                                "progress. Each renews the lease."),
    "attach": ("Hand in an artifact", "A file, pull request, test report, text or link."),
    "get_artifact": ("Download an artifact", "Its bytes."),
    "ask": ("Ask a person", "The run waits (its lease is paused) until a person answers."),
    "list_questions": ("Questions", "Agents' questions, open ones by default."),
    "get_question": ("One question", "And its answer, once given."),
    "answer": ("Answer a question", "People only. The run carries on."),
    "run_propose": ("Propose from a run", "A change request with the run as proposer; a person decides."),
    "complete": ("Complete a run", "Outputs, check results, evidence. Checks decide the task; a task marked for a "
                                   "person waits for one. Idempotent with idempotency_key."),
    "fail": ("Fail a run", "The task goes back to ready while retries remain."),
    "context": ("Context for a question", "What the hook injects, as text and JSON, with each claim's content id and "
                                          "source. as_of, project, budget_tokens, session_id."),
    "search": ("Search", "Entities by words: people, roles, policies, projects, code, requirements."),
    "get_entity": ("One entity", "Every claim with its sources, every link; for code, where it is; for a "
                                 "requirement, the tests that verify it."),
    "get_claim": ("One claim", "A fact by content id, with every source that states it."),
    "code_impact": ("Code impact", "Everything that depends on a symbol and that it depends on, each call site, and "
                                   "the requirements its tests verify."),
    "list_events": ("Events", "In order, after a cursor. wait long-polls."),
    "stream_events": ("Event stream", "Server-sent events from a cursor; max_events closes it."),
    "create_webhook": ("Subscribe a webhook", "Signed deliveries (KL-Signature), in order, retried until 2xx. The "
                                              "secret is shown once."),
    "list_webhooks": ("Webhooks", "And how far each has delivered."),
    "delete_webhook": ("Unsubscribe", "Deliveries stop."),
}


def create_app(svc, mcp: bool = True) -> FastAPI:
    mcp_server = None
    if mcp:
        from .mcp_server import build as build_mcp
        mcp_server = build_mcp(svc)

    @contextlib.asynccontextmanager
    async def lifespan(app):
        if mcp_server is not None:
            async with mcp_server.session_manager.run():
                yield
        else:
            yield

    app = FastAPI(title="Knowledge layer API", version=__version__, lifespan=lifespan, openapi_tags=TAGS,
                  description="The graph as a hosted service: files in, projects edited through change requests a "
                              "person approves, and a run protocol any agent can work through. Guide: "
                              "docs/api-guide.html. MCP: the same agent operations at /mcp.")
    app.state.svc = svc

    @app.exception_handler(errors.Problem)
    async def problem(_req, exc: errors.Problem):
        return JSONResponse(exc.body(), status_code=exc.status, media_type="application/problem+json")

    def principal(authorization: Optional[str] = Header(None), kl_workspace: Optional[str] = Header(None)) -> Principal:
        return svc.authenticate(authorization or "", kl_workspace)

    P = Depends(principal)

    def run_sync(fn, *a, **kw):
        return asyncio.to_thread(fn, *a, **kw)

    def cr_response(cr: dict, response: Response) -> dict:
        response.status_code = 200 if cr.get("state") == "applied" else 202
        return cr

    # ---- workspaces -----------------------------------------------------------------------------
    @app.get("/v1/health", tags=["workspaces"])
    def health():
        return {"ok": True, "version": __version__}

    @app.post("/v1/workspaces", tags=["workspaces"], status_code=201)
    def create_workspace(body: WorkspaceIn, p: Principal = P):
        return svc.create_workspace(p, body.slug, body.name, body.settings)

    @app.get("/v1/workspace", tags=["workspaces"])
    def get_workspace(p: Principal = P):
        if p.kind == "root":
            raise errors.Invalid("the root key belongs to no workspace")
        return svc.get_workspace(p.workspace_id)

    @app.patch("/v1/workspace/settings", tags=["workspaces"])
    def update_settings(body: dict = Body(...), p: Principal = P):
        return svc.update_settings(p, body)

    @app.get("/v1/whoami", tags=["workspaces"])
    def whoami(p: Principal = P):
        return {"kind": p.kind, "id": p.id, "workspace_id": p.workspace_id, "name": p.name, "role": p.role,
                "scopes": sorted(p.scopes), "run_id": p.run_id}

    @app.get("/v1/members", tags=["workspaces"])
    def list_members(p: Principal = P):
        return svc.list_members(p)

    @app.post("/v1/members", tags=["workspaces"], status_code=201)
    def add_member(body: MemberIn, p: Principal = P):
        return svc.add_member(p, body.email, body.name, body.role)

    @app.post("/v1/service-accounts", tags=["workspaces"], status_code=201)
    def create_service_account(body: ServiceAccountIn, p: Principal = P):
        return svc.create_service_account(p, body.name, body.scopes)

    @app.post("/v1/keys", tags=["workspaces"], status_code=201)
    def create_key(body: KeyIn, p: Principal = P):
        return svc.create_user_key(p, body.name, body.scopes)

    @app.delete("/v1/keys/{key_id}", tags=["workspaces"])
    def revoke_key(key_id: str, p: Principal = P):
        return svc.revoke_key(p, key_id)

    # ---- sources --------------------------------------------------------------------------------
    def _ingest(p, s: SourceIn):
        return svc.ingest(p, name=s.name, data=_b64(s.content_base64), text=s.text, kind=s.kind, collection=s.collection,
                          external_id=s.external_id, uri=s.uri, extraction=s.extraction, changes=s.changes, on=s.on,
                          near_duplicates=s.near_duplicates)

    @app.post("/v1/sources", tags=["sources"], status_code=202)
    async def create_source(body: SourceIn, p: Principal = P):
        return await run_sync(_ingest, p, body)

    @app.post("/v1/sources/upload", tags=["sources"], status_code=202)
    async def upload_source(file: UploadFile = File(...), kind: str = Form("document"), collection: str = Form(""),
                            external_id: Optional[str] = Form(None), uri: Optional[str] = Form(None),
                            extraction: Optional[str] = Form(None, description="JSON"), p: Principal = P):
        data = await file.read()
        x = json.loads(extraction) if extraction else None
        return await run_sync(lambda: svc.ingest(p, name=file.filename, data=data, kind=kind, collection=collection,
                                                 external_id=external_id, uri=uri, extraction=x))

    @app.post("/v1/sources:batch", tags=["sources"], status_code=202)
    async def batch_sources(body: BatchIn, p: Principal = P):
        out = []
        for s in body.items:
            try:
                out.append(await run_sync(_ingest, p, s))
            except errors.Problem as e:
                out.append({"name": s.name, "error": e.body()})
        return {"items": out}

    @app.put("/v1/collections/{collection}/manifest", tags=["sources"])
    async def manifest(collection: str, body: ManifestIn, p: Principal = P):
        return await run_sync(svc.manifest, p, collection, [i.model_dump() for i in body.items], body.retract_missing)

    @app.get("/v1/sources", tags=["sources"])
    def list_sources(collection: Optional[str] = None, kind: Optional[str] = None, include_deleted: bool = False,
                     limit: int = Query(100, le=500), cursor: Optional[str] = None, p: Principal = P):
        return svc.list_sources(p, collection, kind, include_deleted, limit, cursor)

    @app.get("/v1/sources/{doc_id}", tags=["sources"])
    def get_source(doc_id: str, p: Principal = P):
        return svc.get_source(p, doc_id)

    @app.get("/v1/sources/{doc_id}/content", tags=["sources"])
    def get_source_content(doc_id: str, p: Principal = P):
        data, mime = svc.get_source_text(p, doc_id)
        return Response(content=data, media_type=mime)

    @app.post("/v1/sources/{doc_id}/extraction", tags=["sources"], status_code=202)
    async def submit_extraction(doc_id: str, body: ExtractionIn, p: Principal = P):
        return await run_sync(svc.submit_extraction, p, doc_id, body.extraction, body.version_id)

    @app.delete("/v1/sources/{doc_id}", tags=["sources"])
    async def retract_source(doc_id: str, p: Principal = P):
        return await run_sync(svc.retract_source, p, doc_id)

    @app.post("/v1/sources/{doc_id}:restore", tags=["sources"])
    async def restore_source(doc_id: str, p: Principal = P):
        return await run_sync(svc.restore_source, p, doc_id)

    @app.get("/v1/jobs/{job_id}", tags=["sources"])
    def get_job(job_id: str, p: Principal = P):
        return svc.get_job(p, job_id)

    # ---- projects -------------------------------------------------------------------------------
    @app.get("/v1/projects", tags=["projects"])
    def list_projects(status: Optional[str] = None, owner: Optional[str] = None, due_before: Optional[str] = None,
                      due_after: Optional[str] = None, q: Optional[str] = None, include_deleted: bool = False,
                      include: Optional[str] = Query(None, description="pending,impact"),
                      sort: Optional[Literal["id", "priority"]] = None, limit: int = Query(100, le=500),
                      cursor: Optional[str] = None, p: Principal = P):
        return svc.list_projects(p, status, owner, due_before, due_after, q, include_deleted,
                                 "pending" in (include or ""), limit, cursor, sort=sort,
                                 include_impact="impact" in (include or ""))

    @app.get("/v1/projects/{pid}", tags=["projects"])
    async def get_project(pid: str, response: Response,
                          include: Optional[str] = Query(None, description="events,plans,pending"), p: Principal = P):
        inc = set((include or "").split(",")) - {""}
        out = await run_sync(svc.get_project, p, pid, inc, "pending" in inc)
        response.headers["ETag"] = f'"v{out["version"]}"'
        return out

    @app.post("/v1/projects", tags=["projects"], status_code=202)
    async def create_project(body: ProjectIn, response: Response, approve: bool = False, p: Principal = P):
        data = body.model_dump(exclude_none=True)
        if data.get("deliverables"):
            data["deliverables"] = [{k: v for k, v in d.items() if k != "reason"} for d in data["deliverables"]]
        return cr_response(await run_sync(svc.create_project, p, data, approve), response)

    @app.patch("/v1/projects/{pid}", tags=["projects"], status_code=202)
    async def patch_project(pid: str, body: ProjectPatch, response: Response, approve: bool = False,
                            if_match: Optional[str] = Header(None), p: Principal = P):
        return cr_response(await run_sync(svc.patch_project, p, pid, body.model_dump(exclude_none=True), if_match, approve),
                           response)

    @app.delete("/v1/projects/{pid}", tags=["projects"], status_code=202)
    async def delete_project(pid: str, response: Response, approve: bool = False, reason: str = "",
                             if_match: Optional[str] = Header(None), p: Principal = P):
        return cr_response(await run_sync(svc.delete_project, p, pid, if_match, reason, approve), response)

    @app.post("/v1/projects/{pid}:restore", tags=["projects"], status_code=202)
    async def restore_project(pid: str, response: Response, approve: bool = False, reason: str = "", p: Principal = P):
        return cr_response(await run_sync(svc.restore_project, p, pid, reason, approve), response)

    @app.post("/v1/projects/{pid}/deliverables", tags=["projects"], status_code=202)
    async def add_deliverable(pid: str, body: DeliverableIn, response: Response, approve: bool = False,
                              p: Principal = P):
        return cr_response(await run_sync(svc.add_deliverable, p, pid, body.model_dump(exclude_none=True), approve),
                           response)

    @app.post("/v1/changes", tags=["projects"], status_code=202)
    async def changes(body: ChangesIn, response: Response, dry_run: bool = False, approve: bool = False,
                      p: Principal = P):
        out = await run_sync(svc.propose_changes, p, body.ops, body.reason, dry_run, approve, body.title)
        if dry_run:
            response.status_code = 200
            return out
        return cr_response(out, response)

    @app.post("/v1/projects/{pid}/thesis", tags=["impact"], status_code=202)
    async def propose_thesis(pid: str, body: ThesisIn, response: Response, approve: bool = False, p: Principal = P):
        return cr_response(await run_sync(svc.propose_thesis, p, pid, body.model_dump(exclude_none=True), approve),
                           response)

    @app.post("/v1/projects/{pid}:research", tags=["impact"])
    async def research(pid: str, response: Response, p: Principal = P):
        out = await run_sync(svc.research, p, pid)
        response.status_code = 202 if out.get("change_request") else 200
        return out

    @app.post("/v1/projects/{pid}/numbers/{key}", tags=["impact"], status_code=202)
    async def answer_number(pid: str, key: str, body: NumberIn, response: Response, approve: bool = False,
                            p: Principal = P):
        return cr_response(await run_sync(svc.answer_number, p, pid, key, body.model_dump(exclude_none=True), approve),
                           response)

    @app.post("/v1/projects/{pid}/effort", tags=["impact"], status_code=202)
    async def estimate_effort(pid: str, body: EffortIn, response: Response, approve: bool = False, p: Principal = P):
        return cr_response(await run_sync(svc.estimate_effort, p, pid, body.model_dump(exclude_none=True), approve),
                           response)

    @app.get("/v1/projects/{pid}/impact", tags=["impact"])
    async def project_impact(pid: str, p: Principal = P):
        return await run_sync(svc.project_impact, p, pid)

    @app.get("/v1/priorities", tags=["impact"])
    async def priorities(p: Principal = P):
        return await run_sync(svc.priorities, p)

    @app.get("/v1/projects/{pid}/events", tags=["projects"])
    async def project_events(pid: str, p: Principal = P):
        return await run_sync(svc.project_events, p, pid)

    # ---- review ---------------------------------------------------------------------------------
    @app.get("/v1/change-requests", tags=["review"])
    async def list_crs(state: Optional[str] = None, project: Optional[str] = None, proposer: Optional[str] = None,
                       limit: int = Query(100, le=500), cursor: Optional[str] = None, p: Principal = P):
        return await run_sync(svc.list_change_requests, p, state, project, proposer, limit, cursor)

    @app.get("/v1/change-requests/{cid}", tags=["review"])
    async def get_cr(cid: str, p: Principal = P):
        return await run_sync(svc.get_change_request, p, cid)

    @app.patch("/v1/change-requests/{cid}", tags=["review"])
    async def patch_cr(cid: str, body: CRPatch, p: Principal = P):
        return await run_sync(svc.update_change_request, p, cid, body.ops, body.reason)

    @app.post("/v1/change-requests/{cid}:approve", tags=["review"])
    async def approve_cr(cid: str, body: ApproveIn = Body(ApproveIn()), p: Principal = P):
        return await run_sync(svc.approve_change_request, p, cid, body.ops, body.edits, body.note)

    @app.post("/v1/change-requests/{cid}:reject", tags=["review"])
    async def reject_cr(cid: str, body: RejectIn = Body(RejectIn()), p: Principal = P):
        return await run_sync(svc.reject_change_request, p, cid, body.note)

    # ---- plans and execution ----------------------------------------------------------------------
    @app.post("/v1/projects/{pid}/deliverables/{key}/plans", tags=["plans"], status_code=202)
    async def propose_plan(pid: str, key: str, body: PlanIn, p: Principal = P):
        data = body.model_dump(exclude_none=True)
        if body.tasks is not None:
            data["tasks"] = [tk.model_dump() for tk in body.tasks]
        data["checks"] = [ch.model_dump() for ch in body.checks]
        return await run_sync(svc.propose_plan, p, pid, key, data)

    @app.get("/v1/plans", tags=["plans"])
    def list_plans(project: Optional[str] = None, state: Optional[str] = None, p: Principal = P):
        return svc.list_plans(p, project, state)

    @app.get("/v1/plans/{plan_id}", tags=["plans"])
    def get_plan(plan_id: str, p: Principal = P):
        return svc.get_plan(p, plan_id)

    @app.post("/v1/plans/{plan_id}/executions", tags=["execution"], status_code=201)
    async def start_execution(plan_id: str, p: Principal = P):
        return await run_sync(svc.start_execution, p, plan_id)

    @app.get("/v1/executions/{eid}", tags=["execution"])
    async def get_execution(eid: str, p: Principal = P):
        return await run_sync(svc.get_execution, p, eid)

    @app.post("/v1/executions/{eid}:cancel", tags=["execution"])
    async def cancel_execution(eid: str, p: Principal = P):
        return await run_sync(svc.cancel_execution, p, eid)

    @app.post("/v1/executions/{eid}/tasks/{task_key}/runs", tags=["execution"], status_code=201)
    async def lease(eid: str, task_key: str, body: LeaseIn, p: Principal = P):
        return await run_sync(svc.lease, p, eid, task_key, body.runner.model_dump(), body.kind)

    @app.post("/v1/runs/{rid}:cancel", tags=["execution"])
    async def cancel_run(rid: str, p: Principal = P):
        return await run_sync(svc.cancel_run, p, rid)

    # ---- runs (the agent's side) --------------------------------------------------------------------
    @app.get("/v1/runs/{rid}", tags=["runs"])
    async def get_run(rid: str, p: Principal = P):
        return await run_sync(svc.get_run, p, rid)

    @app.get("/v1/runs/{rid}/brief", tags=["runs"])
    async def brief(rid: str, budget_tokens: int = 1500, p: Principal = P):
        return await run_sync(svc.brief, p, rid, budget_tokens)

    @app.post("/v1/runs/{rid}/events", tags=["runs"])
    async def run_event(rid: str, body: RunEventIn, p: Principal = P):
        return await run_sync(svc.run_event, p, rid, body.type, body.message, body.data)

    @app.post("/v1/runs/{rid}/artifacts", tags=["runs"], status_code=201)
    async def attach(rid: str, body: ArtifactIn, p: Principal = P):
        return await run_sync(svc.attach, p, rid, body.kind, body.name, _b64(body.content_base64), body.text, body.uri,
                              body.meta)

    @app.get("/v1/artifacts/{aid}", tags=["runs"])
    async def get_artifact(aid: str, p: Principal = P):
        data, name = await run_sync(svc.get_artifact, p, aid)
        return Response(content=data, media_type="application/octet-stream",
                        headers={"Content-Disposition": f'attachment; filename="{name}"'})

    @app.post("/v1/runs/{rid}/questions", tags=["runs"], status_code=201)
    async def ask(rid: str, body: QuestionIn, p: Principal = P):
        return await run_sync(svc.ask, p, rid, body.text)

    @app.get("/v1/questions", tags=["runs"])
    async def list_questions(open_only: bool = True, p: Principal = P):
        return await run_sync(svc.list_questions, p, open_only)

    @app.get("/v1/questions/{qid}", tags=["runs"])
    async def get_question(qid: str, p: Principal = P):
        return await run_sync(svc.get_question, p, qid)

    @app.post("/v1/questions/{qid}:answer", tags=["runs"])
    async def answer(qid: str, body: AnswerIn, p: Principal = P):
        return await run_sync(svc.answer, p, qid, body.answer)

    @app.post("/v1/runs/{rid}/change-requests", tags=["runs"], status_code=202)
    async def run_propose(rid: str, body: ChangesIn, p: Principal = P):
        return await run_sync(svc.run_propose, p, rid, body.ops, body.reason)

    @app.post("/v1/runs/{rid}:complete", tags=["runs"])
    async def complete(rid: str, body: CompleteIn = Body(CompleteIn()),
                       idempotency_key: Optional[str] = Header(None), p: Principal = P):
        return await run_sync(svc.complete, p, rid, body.outputs, body.check_results, body.evidence,
                              body.idempotency_key or idempotency_key)

    @app.post("/v1/runs/{rid}:fail", tags=["runs"])
    async def fail(rid: str, body: FailIn = Body(FailIn()), idempotency_key: Optional[str] = Header(None),
                   p: Principal = P):
        return await run_sync(svc.fail, p, rid, body.reason, body.idempotency_key or idempotency_key)

    # ---- context --------------------------------------------------------------------------------
    @app.post("/v1/context", tags=["context"])
    async def context(body: ContextIn, format: Literal["json", "text"] = "json", p: Principal = P):
        out = await run_sync(svc.context, p, body.question, body.as_of, body.project, body.budget_tokens, body.session_id)
        if format == "text":
            return PlainTextResponse(out["text"])
        return out

    @app.get("/v1/search", tags=["context"])
    async def search(q: str, types: Optional[str] = None, limit: int = Query(20, le=100), p: Principal = P):
        return await run_sync(svc.search, p, q, types.split(",") if types else None, limit)

    @app.get("/v1/entities/{eid}", tags=["context"])
    async def get_entity(eid: str, p: Principal = P):
        return await run_sync(svc.get_entity, p, eid)

    @app.get("/v1/claims/{cid}", tags=["context"])
    async def get_claim(cid: str, p: Principal = P):
        return await run_sync(svc.get_claim, p, cid)

    @app.get("/v1/code/impact", tags=["context"])
    async def code_impact(symbol: str, p: Principal = P):
        return await run_sync(svc.code_impact, p, symbol)

    # ---- events ---------------------------------------------------------------------------------
    @app.get("/v1/events", tags=["events"])
    async def list_events(after: int = 0, types: Optional[str] = None, limit: int = Query(100, le=500),
                          wait: float = Query(0, le=60, description="seconds to wait for new events (long poll)"),
                          p: Principal = P):
        return await run_sync(svc.list_events, p, after, types.split(",") if types else None, limit, wait)

    @app.get("/v1/events/stream", tags=["events"], response_class=StreamingResponse)
    async def stream_events(request: Request, after: int = 0, types: Optional[str] = None,
                            max_events: Optional[int] = Query(None, description="close the stream after this many"),
                            p: Principal = P):
        kinds = types.split(",") if types else None

        async def gen():
            cursor, sent = after, 0
            while not await request.is_disconnected():
                page = await run_sync(svc.list_events, p, cursor, kinds, 100, 10)
                for e in page["items"]:
                    yield f"id: {e['seq']}\nevent: {e['type']}\ndata: {json.dumps(e)}\n\n"
                    sent += 1
                    if max_events and sent >= max_events:
                        return
                cursor = page["next_after"]
                if not page["items"]:
                    yield ": keep-alive\n\n"
        return StreamingResponse(gen(), media_type="text/event-stream")

    @app.post("/v1/webhooks", tags=["events"], status_code=201)
    def create_webhook(body: WebhookIn, p: Principal = P):
        return svc.create_webhook(p, body.url, body.types, body.secret)

    @app.get("/v1/webhooks", tags=["events"])
    def list_webhooks(p: Principal = P):
        return svc.list_webhooks(p)

    @app.delete("/v1/webhooks/{wid}", tags=["events"])
    def delete_webhook(wid: str, p: Principal = P):
        return svc.delete_webhook(p, wid)

    from fastapi.routing import APIRoute
    for route in app.routes:
        if isinstance(route, APIRoute) and route.name in DOCS:
            route.summary, route.description = DOCS[route.name]
    if mcp_server is not None:
        app.mount("/", mcp_server.streamable_http_app())
    return app
