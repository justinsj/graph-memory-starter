"""Files in: store, deduplicate, route, extract, check, commit.

A file is a document (identified by its external id, or its collection and
name), and each content it has had is a version. What happens to a file:

1. its bytes are stored, content-addressed;
2. it is turned into text, which quotes are checked against;
3. deduplication decides whether it is new, a new version, a copy of something
   already here, or a near copy;
4. it is routed by kind. A document is extracted into facts. A transcript or
   request becomes a proposed change request. Code and OpenSpec folders are
   indexed when the graph is built;
5. an extraction must quote the text word for word, and the graph must still
   build with it (a trial build). Otherwise the version is refused, or held
   for a person, with the reasons;
6. the version becomes current, the previous one superseded, and the graph is
   rebuilt from the log.
"""
import io
import re
import sys
import tempfile
import threading
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import sqlalchemy as sa

from . import db as t
from . import errors, ids, text as txt
from .core import jsonable
from .projection import ProjectionError, safe_name, unzip

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import build_graph  # noqa: E402

KINDS = ("document", "transcript", "request", "session", "code", "openspec")
INPUTS = ("transcript", "request", "session")  # what projects cite: routed to project changes
ZIPPED = ("code", "openspec")


def _clean_name(name: str) -> str:
    name = (name or "").replace("\\", "/").strip("/")
    parts = [p for p in name.split("/") if p not in ("", ".", "..")]
    if not parts:
        raise errors.Invalid("a source needs a name, e.g. refund-policy.md")
    return "/".join(re.sub(r"[^\w.\- ]+", "_", p) for p in parts)


class SourcesMixin:

    # ---- in -------------------------------------------------------------------------------------------

    def ingest(self, p, *, name: str, data: bytes = None, text: str = None, kind: str = "document",
               collection: str = "", external_id: str = None, uri: str = None, extraction: dict = None,
               changes: list = None, on: str = None, near_duplicates: str = None) -> dict:
        p.need("sources:write")
        if kind not in KINDS:
            raise errors.Invalid(f"kind must be one of {', '.join(KINDS)}")
        name = _clean_name(name)
        collection = _clean_name(collection) if collection else ""
        if text is not None:
            data = text.encode("utf-8")
        if data is None:
            raise errors.Invalid("send the file's bytes (content_base64 or a multipart file) or its text")
        if len(data) > self.settings.max_upload_bytes:
            raise errors.TooLarge(f"{len(data):,} bytes; the limit is {self.settings.max_upload_bytes:,}")
        ws = p.workspace_id
        if kind in ZIPPED:
            try:
                files = unzip(data)
            except zipfile.BadZipFile:
                raise errors.Invalid(f"a {kind} source is a zip of the folder") from None
            if not files:
                raise errors.Invalid("the zip is empty")
            norm = data
            sha_text = ids.sha256(data)
            mh = None
        else:
            try:
                norm = txt.normalise(data, name).encode("utf-8") if text is None else \
                    txt.normalise(text.encode("utf-8"), name).encode("utf-8")
            except txt.Unsupported as e:
                raise errors.Invalid(str(e)) from None
            sha_text = ids.sha256(norm)
            mh = txt.minhash(norm.decode("utf-8"))
        sha_bytes = ids.sha256(data)
        now = self.clock.stamp()
        job_id = ids.new("job")
        policy = near_duplicates
        with self.db.tx(ws) as c:
            settings = self.ws_settings(c, ws)
            policy = policy or settings["near_duplicates"]
            used = c.execute(sa.select(sa.func.coalesce(sa.func.sum(t.source_versions.c.size), 0)).where(
                t.source_versions.c.workspace_id == ws)).scalar_one()
            if used + len(norm) > settings["max_storage_bytes"]:
                raise errors.TooMany(f"the workspace's storage limit ({settings['max_storage_bytes']:,} bytes) "
                                     "would be passed")
            doc = self._find_document(c, ws, external_id, collection, name)
            c.execute(t.jobs.insert().values(id=job_id, workspace_id=ws, kind="ingest", status="running",
                                             stage="deduplicate", subject={"name": name, "collection": collection,
                                                                           "kind": kind},
                                             result={}, problems=[], created=now, updated=now))
            # 1. the same bytes, or the same text, already here
            same = c.execute(sa.select(t.source_versions, t.documents.c.path, t.documents.c.id.label("doc_id"))
                             .join(t.documents, t.documents.c.id == t.source_versions.c.document_id)
                             .where(t.source_versions.c.workspace_id == ws,
                                    t.source_versions.c.status.in_(("active", "awaiting_extraction")),
                                    t.documents.c.deleted_at.is_(None),
                                    sa.or_(t.source_versions.c.sha256_bytes == sha_bytes,
                                           t.source_versions.c.sha256_text == sha_text))).mappings().first()
            if same:
                dedup = "unchanged" if doc and same["doc_id"] == doc["id"] else "duplicate"
                c.execute(t.source_locations.insert().values(id=ids.new("loc"), workspace_id=ws,
                                                             version_id=same["id"], uri=uri, external_id=external_id,
                                                             name=name, created=now))
                result = {"dedup": dedup, "document_id": same["doc_id"], "version_id": same["id"],
                          "duplicate_of": {"document_id": same["doc_id"], "version_id": same["id"],
                                           "path": same["path"]}}
                self._job(c, ws, job_id, "done", "deduplicate", result)
                return {**result, "job": self._job_row(c, ws, job_id), "status": same["status"]}
            # 2. a new document, or a new version of one
            restored = False
            if doc is None:
                doc_id = ids.new("doc")
                path = self._free_path(c, ws, f"{collection}/{name}" if collection else name)
                c.execute(t.documents.insert().values(id=doc_id, workspace_id=ws, external_id=external_id,
                                                      collection=collection, name=name, path=path, kind=kind, uri=uri,
                                                      current_version_id=None, created=now, deleted_at=None))
                doc = c.execute(sa.select(t.documents).where(t.documents.c.id == doc_id)).mappings().first()
                dedup = "new"
            else:
                if doc["kind"] != kind:
                    raise errors.Conflict(f"{doc['path']} is a {doc['kind']}, not a {kind}")
                restored = doc["deleted_at"] is not None
                dedup = "new_version"
            # 3. a near copy of another document
            similar, best = None, 0.0
            if mh is not None and dedup == "new":
                rows = c.execute(sa.select(t.source_versions.c.id, t.source_versions.c.minhash,
                                           t.source_versions.c.document_id)
                                 .join(t.documents, t.documents.c.id == t.source_versions.c.document_id)
                                 .where(t.source_versions.c.workspace_id == ws,
                                        t.source_versions.c.status == "active",
                                        t.documents.c.deleted_at.is_(None),
                                        t.documents.c.kind == kind)).mappings().all()
                for r in rows:
                    s = txt.similarity(mh, r["minhash"] or [])
                    if s > best:
                        similar, best = r, s
                if best < self.settings.near_duplicate:
                    similar = None
            seq = (c.execute(sa.select(sa.func.max(t.source_versions.c.seq)).where(
                t.source_versions.c.document_id == doc["id"])).scalar() or 0) + 1
            vid = ids.new("ver")
            key = self.blobs.put(norm)
            status = "pending"
            if similar is not None:
                dedup = "near_duplicate"
                status = {"link": "duplicate", "review": "held", "ingest": "pending"}[policy]
            c.execute(t.source_versions.insert().values(
                id=vid, workspace_id=ws, document_id=doc["id"], seq=seq, sha256_bytes=sha_bytes, sha256_text=sha_text,
                minhash=mh, blob_key=key, size=len(norm), mime="application/zip" if kind in ZIPPED else "text/plain",
                status=status, dedup=dedup, duplicate_of=similar["id"] if similar is not None else None,
                similarity=round(best, 3) if similar is not None else None, problems=[], extraction=None,
                extraction_at=None, created=now))
            if restored:
                c.execute(t.documents.update().where(t.documents.c.id == doc["id"]).values(deleted_at=None))
            if status == "held":
                cr = self._open_system_cr(
                    c, ws, f"Near duplicate of another document: {doc['path']}",
                    [{"op": "activate_version", "version": vid}],
                    reason=f"{doc['path']} is {best:.0%} similar to a document already here. Approve to ingest it "
                           "anyway; reject to leave it out.", proposer=("job", job_id, f"ingest job {job_id}"))
                self._job(c, ws, job_id, "waiting", "review", {"change_request": cr})
            elif status == "duplicate":
                self._job(c, ws, job_id, "done", "deduplicate", {"linked_to": similar["id"]})
        base = {"document_id": doc["id"], "version_id": vid, "dedup": dedup, "path": doc["path"]}
        if dedup == "near_duplicate":
            base["duplicate_of"] = {"version_id": similar["id"], "document_id": similar["document_id"],
                                    "similarity": round(best, 3)}
        if status in ("held", "duplicate"):
            with self.db.tx(ws) as c:
                return {**base, "status": status, "job": self._job_row(c, ws, job_id)}

        def route():
            try:
                self._route(p, ws, job_id, doc, vid, kind, norm, extraction, changes, on)
            except errors.Problem:
                if self.settings.jobs_inline:
                    raise  # its reasons are already on the job and the version
            except Exception as e:  # noqa: BLE001  the job records it
                with self.db.tx(ws) as c:
                    self._job(c, ws, job_id, "failed", "error", {}, [f"{type(e).__name__}: {e}"])
                    c.execute(t.source_versions.update().where(t.source_versions.c.id == vid)
                              .values(status="failed", problems=[str(e)]))
                if self.settings.jobs_inline:
                    raise
        if self.settings.jobs_inline:
            try:
                route()
            except errors.Problem:
                pass  # recorded on the job and the version
        else:
            threading.Thread(target=route, daemon=True).start()
        with self.db.tx(ws) as c:
            v = c.execute(sa.select(t.source_versions).where(t.source_versions.c.id == vid)).mappings().first()
            return {**base, "status": v["status"], "problems": v["problems"], "job": self._job_row(c, ws, job_id)}

    def _route(self, p, ws, job_id, doc, vid, kind, norm: bytes, extraction, changes, on):
        text = norm.decode("utf-8") if kind not in ZIPPED else None
        if kind == "document":
            if extraction is None:
                with self.db.tx(ws) as c:
                    self._job(c, ws, job_id, "running", "extract", {})
                extraction = self.extractor.extract(text, doc["path"])
            if extraction is None:
                with self.db.tx(ws) as c:
                    c.execute(t.source_versions.update().where(t.source_versions.c.id == vid)
                              .values(status="awaiting_extraction"))
                    c.execute(t.documents.update().where(t.documents.c.id == doc["id"],
                                                         t.documents.c.current_version_id.is_(None))
                              .values(current_version_id=vid))
                    self._job(c, ws, job_id, "waiting", "extraction", {
                        "next": f"POST /v1/sources/{doc['id']}/extraction with the extraction JSON"})
                return
            self._commit_extraction(p, ws, job_id, doc, vid, text, extraction)
        elif kind in INPUTS:
            self._activate(ws, doc, vid, job_id, actor=p.label)
            on = on or self.clock.today().isoformat()
            draft = None
            if changes is None:
                changes, draft = self._propose(ws, doc, text, kind, on)
            result = {}
            if changes:
                cr = self.open_input_change_request(p, ws, doc, vid, text, kind, changes, on, job_id)
                result = {"change_request": cr["id"], "problems": cr["problems"]}
                if not cr["problems"] and self.settings.research_before_review:
                    try:  # the thesis and its numbers, for the reviewer to weigh with the changes
                        research = self.research_input(ws, f"inputs/{doc['path']}", text, kind, on, changes, draft)
                        if research.get("change_request"):
                            result["research"] = research["change_request"]["id"]
                    except Exception as e:  # noqa: BLE001  research is a help, never a reason the input fails
                        with self.db.tx(ws) as c:
                            self.log(c, ws, "impact_research.failed", {"input": doc["path"], "error": str(e)[:300]},
                                     "impact research")
            with self.db.tx(ws) as c:
                self._job(c, ws, job_id, "done", "done", result)
        else:
            problems = self.projector.trial(ws, {doc["id"]: self._version_for_trial(ws, vid)})
            if problems:
                with self.db.tx(ws) as c:
                    c.execute(t.source_versions.update().where(t.source_versions.c.id == vid)
                              .values(status="failed", problems=problems))
                    self._job(c, ws, job_id, "failed", "build", {}, problems)
                raise errors.Invalid("the graph would not build with this code", problems=problems)
            self._activate(ws, doc, vid, job_id, actor=p.label)
            with self.db.tx(ws) as c:
                self._job(c, ws, job_id, "done", "done", {})

    def _version_for_trial(self, ws, vid, extraction=None):
        with self.db.tx(ws) as c:
            v = dict(c.execute(sa.select(t.source_versions).where(t.source_versions.c.id == vid)).mappings().first())
        if extraction is not None:
            v["extraction"], v["extraction_at"] = extraction, v["extraction_at"] or self.clock.stamp()
        v["status"] = "active"
        return v

    def _check_extraction(self, doc, text, extraction) -> tuple:
        """(normalised extraction, problems) against the document's own text."""
        if not isinstance(extraction, dict):
            return None, ["the extraction is a JSON object with nodes, edges and aliases"]
        x = {"source_doc": doc["path"], "nodes": extraction.get("nodes") or [], "edges": extraction.get("edges") or [],
             "aliases": extraction.get("aliases") or []}
        problems = []
        for i, n in enumerate(x["nodes"]):
            if not isinstance(n, dict) or not n.get("name") or not n.get("type"):
                problems.append(f"node {i + 1}: needs a name and a type")
        if problems:
            return None, problems
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / doc["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
            problems = build_graph.problems([x], Path(tmp))
        return x, problems

    def _commit_extraction(self, p, ws, job_id, doc, vid, text, extraction):
        with self.db.tx(ws) as c:
            self._job(c, ws, job_id, "running", "check", {})
        x, problems = self._check_extraction(doc, text, extraction)
        if problems:
            with self.db.tx(ws) as c:
                c.execute(t.source_versions.update().where(t.source_versions.c.id == vid)
                          .values(status="failed", problems=problems))
                self._job(c, ws, job_id, "failed", "check", {}, problems)
            raise errors.Invalid("the extraction does not match the document", problems=problems)
        now = self.clock.stamp()
        with self.db.tx(ws) as c:
            c.execute(t.source_versions.update().where(t.source_versions.c.id == vid)
                      .values(extraction=x, extraction_at=now))
            review_all = self.ws_settings(c, ws)["review_extractions"]
        conflicts = self.projector.trial(ws, {doc["id"]: self._version_for_trial(ws, vid, x)})
        if conflicts or review_all:
            others = sorted({m for line in conflicts for m in re.findall(r"\(([^()]+)\)\s*$", line)} - {doc["path"]})
            with self.db.tx(ws) as c:
                other_docs = c.execute(sa.select(t.documents.c.id, t.documents.c.path).where(
                    t.documents.c.workspace_id == ws, t.documents.c.path.in_(others))).mappings().all() if others else []
                c.execute(t.source_versions.update().where(t.source_versions.c.id == vid)
                          .values(status="held", problems=conflicts))
                ops = [{"op": "activate_version", "version": vid}] + [
                    {"op": "retract_source", "document": o["id"]} for o in other_docs]
                title = (f"{doc['path']} disagrees with {', '.join(o['path'] for o in other_docs) or 'the graph'}"
                         if conflicts else f"Facts from {doc['path']}")
                reason = ("The graph will not hold both at once:\n" + "\n".join(conflicts) +
                          "\nApprove both operations to replace the other document with this one, or reject to keep "
                          "the graph as it is." if conflicts else
                          "This workspace reviews every extraction before it applies.")
                cr = self._open_system_cr(c, ws, title, ops, reason=reason,
                                          proposer=("job", job_id, f"ingest job {job_id}"))
                self._job(c, ws, job_id, "waiting", "review", {"change_request": cr}, conflicts)
            return
        self._activate(ws, doc, vid, job_id, actor=p.label)
        with self.db.tx(ws) as c:
            self._job(c, ws, job_id, "done", "done", {"nodes": len(x["nodes"]), "edges": len(x["edges"])})

    def _activate(self, ws, doc, vid, job_id=None, actor="system"):
        with self.db.tx(ws) as c:
            cur = c.execute(sa.select(t.documents.c.current_version_id).where(t.documents.c.id == doc["id"])).scalar()
            if cur and cur != vid:
                c.execute(t.source_versions.update().where(t.source_versions.c.id == cur,
                                                           t.source_versions.c.status.in_(("active", "awaiting_extraction")))
                          .values(status="superseded"))
            c.execute(t.source_versions.update().where(t.source_versions.c.id == vid).values(status="active", problems=[]))
            c.execute(t.documents.update().where(t.documents.c.id == doc["id"])
                      .values(current_version_id=vid, deleted_at=None))
            self.bump(c, ws)
            self.log(c, ws, "source.version", {"document": doc["id"], "version": vid, "path": doc["path"]}, actor)
            self.emit(c, ws, "source.ingested", {"document_id": doc["id"], "version_id": vid, "path": doc["path"],
                                                 "kind": doc["kind"], "superseded": cur if cur != vid else None})
        if self.settings.graph_updates == "deferred":  # noted for the graph; a document is taken in at the next read
            self.projector.defer(ws, {"change": "source", "kind": doc["kind"], "path": doc["path"],
                                      "source_version": vid})

    def _propose(self, ws, doc, text, kind, on) -> tuple:
        """(changes, thesis draft or None) for an input, from the extractor. With research before review, the
        thesis comes with the change set: in the same model call (thesis_call merged) or in a second call at the
        same time (parallel), when the extractor can; else it is drafted afterwards from the proposed project.
        preloaded (preload_note): the call is told that what it is given is all there is, when none of the graph's
        figures was left out; the change set's call also needs every project to fit (projects/ingest.py)."""
        ex = self.extractor
        records, entities = self._records(ws), self._entities(ws)
        args = (text, doc["path"], kind, on, records, entities)
        with self.db.tx(ws) as c:
            research = self.settings.research_before_review and self.ws_settings(c, ws).get("impact_research")
        mode, preload = self.settings.thesis_call, self.settings.preload_note
        if research and mode == "merged" and hasattr(ex, "propose_with_thesis"):
            figures, every = self._figures_all(ws)
            return ex.propose_with_thesis(*args, figures, preloaded=preload and every)
        if research and mode == "parallel" and hasattr(ex, "draft_thesis_from_input"):
            figures, every = self._figures_all(ws)
            with ThreadPoolExecutor(max_workers=2) as pool:
                changes = pool.submit(ex.propose_changes, *args, preloaded=preload)
                draft = pool.submit(ex.draft_thesis_from_input, text, f"inputs/{doc['path']}", figures,
                                    preloaded=preload and every)
                return changes.result(), draft.result()
        return ex.propose_changes(*args, preloaded=preload), None

    def submit_extraction(self, p, doc_id: str, extraction: dict, version_id: str = None) -> dict:
        p.need("sources:write")
        ws = p.workspace_id
        with self.db.tx(ws) as c:
            doc = self._document(c, ws, doc_id)
            q = sa.select(t.source_versions).where(t.source_versions.c.document_id == doc_id)
            q = q.where(t.source_versions.c.id == version_id) if version_id else \
                q.where(t.source_versions.c.status.in_(("awaiting_extraction", "failed", "active"))) \
                 .order_by(t.source_versions.c.seq.desc())
            v = c.execute(q).mappings().first()
            if not v:
                raise errors.NotFound("no version of that document waits for an extraction")
            job_id = ids.new("job")
            now = self.clock.stamp()
            c.execute(t.jobs.insert().values(id=job_id, workspace_id=ws, kind="extraction", status="running",
                                             stage="check", subject={"document": doc_id, "version": v["id"]},
                                             result={}, problems=[], created=now, updated=now))
        text = self.blobs.get(v["blob_key"]).decode("utf-8")
        try:
            self._commit_extraction(p, ws, job_id, doc, v["id"], text, extraction)
        except errors.Problem:
            pass
        with self.db.tx(ws) as c:
            vv = c.execute(sa.select(t.source_versions).where(t.source_versions.c.id == v["id"])).mappings().first()
            return {"document_id": doc_id, "version_id": v["id"], "status": vv["status"], "problems": vv["problems"],
                    "job": self._job_row(c, ws, job_id)}

    # ---- out ----------------------------------------------------------------------------------------

    def retract_source(self, p, doc_id: str, cr_id: str = None, c=None) -> dict:
        if c is None:
            p.need("sources:write")
            with self.db.tx(p.workspace_id) as c2:
                return self.retract_source(p, doc_id, cr_id, c2)
        ws = p.workspace_id
        doc = self._document(c, ws, doc_id)
        if doc["deleted_at"]:
            raise errors.Conflict(f"{doc['path']} is already retracted")
        now = self.clock.stamp()
        c.execute(t.documents.update().where(t.documents.c.id == doc_id).values(deleted_at=now))
        if doc["current_version_id"]:
            c.execute(t.source_versions.update().where(t.source_versions.c.id == doc["current_version_id"],
                                                       t.source_versions.c.status == "active")
                      .values(status="retracted"))
        self.bump(c, ws)
        self.log(c, ws, "source.retracted", {"document": doc_id, "path": doc["path"]}, p.label, cr_id)
        self.emit(c, ws, "source.retracted", {"document_id": doc_id, "path": doc["path"]})
        return {"document_id": doc_id, "path": doc["path"], "retracted": now}

    def restore_source(self, p, doc_id: str) -> dict:
        p.need("sources:write")
        ws = p.workspace_id
        with self.db.tx(ws) as c:
            doc = self._document(c, ws, doc_id)
            if not doc["deleted_at"]:
                raise errors.Conflict(f"{doc['path']} is not retracted")
            v = c.execute(sa.select(t.source_versions).where(t.source_versions.c.id == doc["current_version_id"])
                          ).mappings().first()
        if v is not None:
            problems = self.projector.trial(ws, {"__new__": [({**doc, "deleted_at": None}, {**v, "status": "active"})]})
            if problems:
                raise errors.Conflict("restoring it would clash with what the graph holds now", problems=problems)
        with self.db.tx(ws) as c:
            c.execute(t.documents.update().where(t.documents.c.id == doc_id).values(deleted_at=None))
            if v is not None:
                c.execute(t.source_versions.update().where(t.source_versions.c.id == v["id"]).values(status="active"))
            self.bump(c, ws)
            self.log(c, ws, "source.restored", {"document": doc_id}, p.label)
            self.emit(c, ws, "source.restored", {"document_id": doc_id, "path": doc["path"]})
        return self.get_source(p, doc_id)

    def activate_version(self, p, version_id: str, cr_id: str = None) -> dict:
        ws = p.workspace_id
        with self.db.tx(ws) as c:
            v = c.execute(sa.select(t.source_versions).where(t.source_versions.c.id == version_id,
                                                             t.source_versions.c.workspace_id == ws)).mappings().first()
            if not v:
                raise errors.NotFound(f"no version {version_id}")
            doc = self._document(c, ws, v["document_id"])
        if doc["kind"] == "document" and v["extraction"] is None:
            text = self.blobs.get(v["blob_key"]).decode("utf-8")
            x = self.extractor.extract(text, doc["path"])
            if x is None:
                with self.db.tx(ws) as c:
                    c.execute(t.source_versions.update().where(t.source_versions.c.id == version_id)
                              .values(status="awaiting_extraction"))
                return {"version_id": version_id, "status": "awaiting_extraction"}
            x, problems = self._check_extraction(doc, text, x)
            if problems:
                raise errors.Invalid("the extraction does not match the document", problems=problems)
            with self.db.tx(ws) as c:
                c.execute(t.source_versions.update().where(t.source_versions.c.id == version_id)
                          .values(extraction=x, extraction_at=self.clock.stamp()))
        return {"version_id": version_id, "document_id": doc["id"]}

    def trial_activation(self, ws, version_ids: list, retract_docs: list) -> list:
        """The build's problems if these versions became current and these documents were retracted together."""
        override = {}
        with self.db.tx(ws) as c:
            for vid in version_ids:
                v = dict(c.execute(sa.select(t.source_versions).where(t.source_versions.c.id == vid)).mappings().first())
                v["status"] = "active"
                override[v["document_id"]] = v
            for d in retract_docs:
                override[d] = None
        return self.projector.trial(ws, override)

    def commit_activation(self, c, p, version_id: str, cr_id: str = None) -> None:
        ws = p.workspace_id
        v = c.execute(sa.select(t.source_versions).where(t.source_versions.c.id == version_id)).mappings().first()
        doc = self._document(c, ws, v["document_id"])
        cur = doc["current_version_id"]
        if cur and cur != version_id:
            c.execute(t.source_versions.update().where(t.source_versions.c.id == cur,
                                                       t.source_versions.c.status.in_(("active", "awaiting_extraction")))
                      .values(status="superseded"))
        c.execute(t.source_versions.update().where(t.source_versions.c.id == version_id)
                  .values(status="active", problems=[]))
        c.execute(t.documents.update().where(t.documents.c.id == doc["id"])
                  .values(current_version_id=version_id, deleted_at=None))
        self.bump(c, ws)
        self.log(c, ws, "source.version", {"document": doc["id"], "version": version_id}, p.label, cr_id)
        self.emit(c, ws, "source.ingested", {"document_id": doc["id"], "version_id": version_id, "path": doc["path"],
                                             "kind": doc["kind"], "superseded": cur if cur != version_id else None})
        for j in c.execute(sa.select(t.jobs).where(t.jobs.c.workspace_id == ws, t.jobs.c.status == "waiting")).mappings():
            if j["result"].get("change_request") == cr_id:
                self._job(c, ws, j["id"], "done", "done", {**j["result"], "approved": True})

    # ---- sync ---------------------------------------------------------------------------------------

    def manifest(self, p, collection: str, items: list, retract_missing: bool = False) -> dict:
        p.need("sources:write")
        ws = p.workspace_id
        collection = _clean_name(collection)
        upload, unchanged, seen = [], [], set()
        with self.db.tx(ws) as c:
            docs = c.execute(sa.select(t.documents).where(t.documents.c.workspace_id == ws,
                                                          t.documents.c.collection == collection,
                                                          t.documents.c.deleted_at.is_(None))).mappings().all()
            by_ext = {d["external_id"]: d for d in docs if d["external_id"]}
            by_name = {d["name"]: d for d in docs}
            versions = {v["id"]: v for v in c.execute(sa.select(t.source_versions).where(
                t.source_versions.c.id.in_([d["current_version_id"] for d in docs if d["current_version_id"]] or [""]))
            ).mappings()}
            for it in items:
                d = by_ext.get(it.get("external_id")) if it.get("external_id") else by_name.get(_clean_name(it["name"]))
                label = it.get("external_id") or it["name"]
                if d is None:
                    upload.append({"item": label, "why": "new"})
                    continue
                seen.add(d["id"])
                v = versions.get(d["current_version_id"])
                if v is None or it.get("sha256") not in (v["sha256_bytes"], v["sha256_text"]):
                    upload.append({"item": label, "why": "changed", "document_id": d["id"]})
                else:
                    unchanged.append({"item": label, "document_id": d["id"]})
            missing = [d for d in docs if d["id"] not in seen]
        retracted = []
        if retract_missing:
            for d in missing:
                retracted.append(self.retract_source(p, d["id"]))
        return {"collection": collection, "upload": upload, "unchanged": unchanged,
                "retract": [{"document_id": d["id"], "path": d["path"]} for d in missing],
                "retracted": retracted}

    # ---- reading ----------------------------------------------------------------------------------

    def list_sources(self, p, collection: str = None, kind: str = None, include_deleted: bool = False,
                     limit: int = 100, cursor: str = None) -> dict:
        p.need("read")
        ws = p.workspace_id
        with self.db.tx(ws) as c:
            q = sa.select(t.documents).where(t.documents.c.workspace_id == ws)
            if collection is not None:
                q = q.where(t.documents.c.collection == collection)
            if kind:
                q = q.where(t.documents.c.kind == kind)
            if not include_deleted:
                q = q.where(t.documents.c.deleted_at.is_(None))
            if cursor:
                q = q.where(t.documents.c.id > cursor)
            rows = c.execute(q.order_by(t.documents.c.id).limit(limit + 1)).mappings().all()
            out = [self._doc_out(c, r) for r in rows[:limit]]
        return {"items": out, "next_cursor": rows[limit - 1]["id"] if len(rows) > limit else None}

    def get_source(self, p, doc_id: str) -> dict:
        p.need("read")
        ws = p.workspace_id
        with self.db.tx(ws) as c:
            doc = self._document(c, ws, doc_id)
            out = self._doc_out(c, doc)
            vs = c.execute(sa.select(t.source_versions).where(t.source_versions.c.document_id == doc_id)
                           .order_by(t.source_versions.c.seq)).mappings().all()
            locs = c.execute(sa.select(t.source_locations).where(
                t.source_locations.c.version_id.in_([v["id"] for v in vs] or [""]))).mappings().all()
            out["versions"] = [{
                "id": v["id"], "seq": v["seq"], "status": v["status"], "dedup": v["dedup"],
                "sha256": v["sha256_bytes"], "sha256_text": v["sha256_text"], "size": v["size"],
                "duplicate_of": v["duplicate_of"], "similarity": v["similarity"], "problems": v["problems"],
                "extracted": v["extraction_at"],
                "facts": ({"nodes": len(v["extraction"]["nodes"]), "edges": len(v["extraction"]["edges"])}
                          if v["extraction"] else None),
                "also_at": [{"name": lo["name"], "uri": lo["uri"], "external_id": lo["external_id"]}
                            for lo in locs if lo["version_id"] == v["id"]],
                "created": v["created"]} for v in vs]
        return out

    def get_source_text(self, p, doc_id: str) -> tuple:
        p.need("read")
        with self.db.tx(p.workspace_id) as c:
            doc = self._document(c, p.workspace_id, doc_id)
            v = c.execute(sa.select(t.source_versions).where(t.source_versions.c.id == doc["current_version_id"])
                          ).mappings().first()
        if not v:
            raise errors.NotFound("the document has no version yet")
        return self.blobs.get(v["blob_key"]), v["mime"]

    def get_job(self, p, job_id: str) -> dict:
        p.need("read")
        with self.db.tx(p.workspace_id) as c:
            return self._job_row(c, p.workspace_id, job_id)

    # ---- helpers ------------------------------------------------------------------------------------

    def _doc_out(self, c, d) -> dict:
        v = c.execute(sa.select(t.source_versions).where(t.source_versions.c.id == d["current_version_id"])
                      ).mappings().first() if d["current_version_id"] else None
        return {"id": d["id"], "name": d["name"], "collection": d["collection"], "path": d["path"], "kind": d["kind"],
                "external_id": d["external_id"], "uri": d["uri"], "created": d["created"], "deleted_at": d["deleted_at"],
                "current_version": ({"id": v["id"], "seq": v["seq"], "status": v["status"], "sha256": v["sha256_bytes"],
                                     "size": v["size"]} if v else None)}

    def _document(self, c, ws, doc_id):
        d = c.execute(sa.select(t.documents).where(t.documents.c.id == doc_id, t.documents.c.workspace_id == ws)
                      ).mappings().first()
        if not d:
            raise errors.NotFound(f"no source {doc_id}")
        return d

    def _find_document(self, c, ws, external_id, collection, name):
        q = sa.select(t.documents).where(t.documents.c.workspace_id == ws)
        if external_id:
            return c.execute(q.where(t.documents.c.external_id == external_id)).mappings().first()
        return c.execute(q.where(t.documents.c.collection == collection, t.documents.c.name == name,
                                 t.documents.c.external_id.is_(None))).mappings().first()

    def _free_path(self, c, ws, path):
        taken = {r[0] for r in c.execute(sa.select(t.documents.c.path).where(t.documents.c.workspace_id == ws))}
        if path not in taken:
            return path
        stem, dot, ext = path.rpartition(".")
        base, suffix = (stem, f".{ext}") if dot and "/" not in ext else (path, "")
        n = 2
        while f"{base}-{n}{suffix}" in taken:
            n += 1
        return f"{base}-{n}{suffix}"

    def _job(self, c, ws, job_id, status, stage, result, problems=None):
        row = c.execute(sa.select(t.jobs).where(t.jobs.c.id == job_id)).mappings().first()
        c.execute(t.jobs.update().where(t.jobs.c.id == job_id).values(
            status=status, stage=stage, result={**(row["result"] if row else {}), **result},
            problems=list(problems or (row["problems"] if row and status not in ("done",) else [])),
            updated=self.clock.stamp()))
        if status in ("done", "failed") and row and row["status"] not in ("done", "failed"):
            self.emit(c, ws, f"job.{status}", {"job_id": job_id, "kind": row["kind"], "subject": row["subject"]})

    def _job_row(self, c, ws, job_id):
        row = c.execute(sa.select(t.jobs).where(t.jobs.c.id == job_id, t.jobs.c.workspace_id == ws)).mappings().first()
        if not row:
            raise errors.NotFound(f"no job {job_id}")
        return jsonable(row)

    def zip_folder(self, folder: Path) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for f in sorted(Path(folder).rglob("*")):
                if f.is_file() and "__pycache__" not in f.parts:
                    z.write(f, f.relative_to(folder).as_posix())
        return buf.getvalue()


__all__ = ["SourcesMixin", "safe_name", "ProjectionError"]
