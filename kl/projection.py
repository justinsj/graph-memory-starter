"""Each workspace's graph: a projection of the log, rebuilt anywhere from its rows.

The log (kl.db) says which document versions are active, what each one's
checked extraction is, and what every project record holds. From it, a
workspace's snapshot folder is written: the documents' text, their
extractions, the code, the OpenSpec files, the project records and the inputs
they quote. Only files whose content changed are rewritten, so a new version of
one document touches one document's files. The existing build
(src/build_graph.py) then compiles the folder into graph-<version>.db. That is
the file recall reads. The answers stay exactly the ones the tests pin.

A graph file is never replaced in place. A new one is written beside it, and
the old one stays readable for requests already using it.

Any node can rebuild a workspace's graph from the log, so the files under the
data folder are a cache. A version counter on the workspace row says whether
the cache is current.
"""
import contextlib
import io
import json
import os
import re
import shutil
import sys
import tempfile
import threading
import zipfile
from pathlib import Path

import fasteners
import sqlalchemy as sa

from . import db as t
from . import ids, openspec

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "codegraph")]
import build_graph  # noqa: E402

_locks: dict = {}
_guard = threading.Lock()


DEFERRED_KINDS = ("transcript", "request", "session")  # sources the project process may leave out of the graph for now


def _lock(key: str) -> threading.Lock:
    with _guard:
        return _locks.setdefault(key, threading.Lock())


def safe_name(path: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", path).strip("_") or "doc"


def unzip(data: bytes) -> dict:
    """{path: bytes} for a zip, with any single top folder the archive adds taken off."""
    out = {}
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for info in z.infolist():
            if info.is_dir():
                continue
            name = info.filename.replace("\\", "/")
            if name.startswith("/") or ".." in name.split("/"):
                continue
            out[name] = z.read(info)
    tops = {p.split("/", 1)[0] for p in out if "/" in p}
    if len(tops) == 1 and all("/" in p for p in out):
        top = tops.pop()
        out = {p[len(top) + 1:]: v for p, v in out.items()}
    return out


def openspec_files(files: dict) -> dict:
    """The openspec/ part of a repository, as text, keyed by path within the repository."""
    return {p: v.decode("utf-8", "replace") for p, v in files.items()
            if p.startswith("openspec/") and p.endswith(".md")}


class ProjectionError(RuntimeError):
    pass


class Projector:
    def __init__(self, db: t.Database, blobs, data_dir: Path, clock):
        self.db, self.blobs, self.clock = db, blobs, clock
        self.root = Path(data_dir) / "workspaces"

    def folder(self, ws: str) -> Path:
        return self.root / ws

    # ---- what the snapshot should hold ---------------------------------------------------------

    def desired(self, c, ws: str, override: dict = None) -> dict:
        """{relative path: (bytes, mtime or None)} for the workspace's snapshot.

        override: {document id: version row or None}, to try a change before it is
        committed (a trial build)."""
        override = override or {}
        out = {}
        docs = c.execute(sa.select(t.documents).where(t.documents.c.workspace_id == ws,
                                                      t.documents.c.deleted_at.is_(None))).mappings().all()
        versions = {}
        cur_ids = [d["current_version_id"] for d in docs if d["current_version_id"]]
        if cur_ids:
            for v in c.execute(sa.select(t.source_versions).where(t.source_versions.c.workspace_id == ws,
                                                                  t.source_versions.c.id.in_(cur_ids))).mappings():
                versions[v["id"]] = v
        chosen = []
        for d in docs:
            if d["id"] in override:
                v = override[d["id"]]
            else:
                v = versions.get(d["current_version_id"])
            if v is not None and (v["status"] == "active" or d["id"] in override):
                chosen.append((d, v))
        for extra_doc, v in override.get("__new__", []):
            chosen.append((extra_doc, v))
        code_files, spec_sets = {}, []
        for d, v in chosen:
            data = self.blobs.get(v["blob_key"])
            when = ids.parse(v["extraction_at"]).timestamp() if v.get("extraction_at") else None
            if d["kind"] == "document":
                out[f"docs/{d['path']}"] = (data, None)
                if v.get("extraction"):
                    out[f"extraction/{safe_name(d['path'])}.json"] = (
                        json.dumps({**v["extraction"], "source_doc": d["path"]}, ensure_ascii=False, indent=1).encode(),
                        when)
            elif d["kind"] in ("transcript", "request", "session"):
                out[f"inputs/{d['path']}"] = (data, None)
            elif d["kind"] in ("code", "openspec"):
                files = unzip(data)
                if d["kind"] == "code":
                    for p, b in files.items():
                        code_files[f"code/{d['name']}/{p}"] = b
                specs = openspec_files(files) if d["kind"] == "code" else \
                    {p: b.decode("utf-8", "replace") for p, b in files.items() if p.endswith(".md")}
                if specs:
                    spec_sets.append((d, specs, when))
        for p, b in code_files.items():
            out[p] = (b, None)
        for d, specs, when in spec_sets:
            for p, text in specs.items():
                out[f"docs/{d['path']}/{p}"] = (text.encode("utf-8"), None)
            docs_x, _ = openspec.specs_to_extraction(specs, prefix=f"{d['path']}/")
            for x in docs_x:
                out[f"extraction/{safe_name(x['source_doc'])}.json"] = (
                    json.dumps(x, ensure_ascii=False, indent=1).encode(), when)
        for r in c.execute(sa.select(t.project_records).where(t.project_records.c.workspace_id == ws)).mappings():
            out[f"records/{r['project_id']}.json"] = (
                (json.dumps(r["record"], indent=1, ensure_ascii=False) + "\n").encode("utf-8"), None)
        logs = {}
        for e in c.execute(sa.select(t.project_events).where(t.project_events.c.workspace_id == ws)
                           .order_by(t.project_events.c.id)).mappings():
            logs.setdefault(e["project_id"], []).append(json.dumps(e["event"], ensure_ascii=False))
        for pid, lines in logs.items():
            out[f"records/{pid}.log.jsonl"] = (("\n".join(lines) + "\n").encode("utf-8"), None)
        if code_files and spec_sets:  # tests that name a scenario verify it
            out.update(self._links(code_files, spec_sets))
        return out

    def _links(self, code_files: dict, spec_sets: list) -> dict:
        import index  # codegraph/index.py
        with tempfile.TemporaryDirectory() as tmp:
            for p, b in code_files.items():
                target = Path(tmp) / p
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(b)
            found = index.index(Path(tmp) / "code")
        tests = [name for name, s in found["symbols"].items() if s["type"] == "TEST"]
        names = [s for _, specs, _ in spec_sets for s in openspec.scenarios(specs)]
        edges = openspec.link_tests(tests, names)
        if not edges:
            return {}
        doc = {"source_doc": "links", "nodes": [], "edges": edges, "aliases": []}
        return {"extraction/zz-links.json": (json.dumps(doc, indent=1).encode(), None)}

    # ---- writing and building --------------------------------------------------------------------

    @staticmethod
    def write(folder: Path, desired: dict) -> dict:
        """Make folder hold exactly desired, rewriting only what changed. Returns counts."""
        folder.mkdir(parents=True, exist_ok=True)
        manifest_path = folder / ".manifest.json"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            manifest = {}
        written = removed = 0
        new_manifest = {}
        for rel, (data, mtime) in desired.items():
            digest = ids.sha256(data) + (f"@{mtime}" if mtime else "")
            new_manifest[rel] = digest
            path = folder / rel
            if manifest.get(rel) != digest or not path.is_file():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
                written += 1
            if mtime:
                os.utime(path, (mtime, mtime))
        for rel in set(manifest) - set(desired):
            with contextlib.suppress(OSError):
                (folder / rel).unlink()
                removed += 1
        for sub in ("docs", "extraction", "records", "inputs", "code"):
            (folder / sub).mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(new_manifest, indent=0), encoding="utf-8")
        return {"written": written, "removed": removed, "files": len(desired)}

    def build(self, snapshot: Path, db_path: Path) -> dict:
        code = snapshot / "code"
        has_code = code.is_dir() and any(p.is_file() for p in code.rglob("*"))
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out):
                return build_graph.build(extraction=snapshot / "extraction", db_path=db_path,
                                         docs_root=snapshot / "docs", records=snapshot / "records",
                                         records_root=snapshot, now=self.clock.today(),
                                         code=code if has_code else None)
        except SystemExit as e:
            raise ProjectionError(str(e)) from None

    @staticmethod
    def check(snapshot: Path) -> list:
        """What the build would refuse, without building: the four checks it stops on.

        A name given two types, an extraction the documents do not bear out, a code
        index that does not match the code, a project record whose quotes are not in
        its inputs. Past these the build does not fail, so a trial needs only them."""
        files = sorted((snapshot / "extraction").glob("*.json"))
        docs = [json.loads(f.read_text(encoding="utf-8")) for f in files]
        code = snapshot / "code"
        coded = build_graph.index_code(code) if code.is_dir() and any(p.is_file() for p in code.rglob("*"))             else {"docs": []}
        out = []
        clash = build_graph.clashes(docs + coded["docs"])
        if clash:
            out.append("same name, different types - rename one of each:")
            out += [f"{name}: " + ", ".join(f"{t} in {d}" for t, d in seen.items()) for name, seen in clash.items()]
        for label, found in (("the extraction needs fixing first:", build_graph.problems(docs, snapshot / "docs")),
                             ("the code index does not match the code:",
                              build_graph.problems(coded["docs"], code) if coded["docs"] else []),
                             ("the project records need fixing first:",
                              build_graph.record_problems(build_graph.load_records(snapshot / "records")[0], snapshot))):
            if found:
                out.append(label)
                out += [line.strip() for p in found for line in p.splitlines() if line.strip()]
        return out

    def trial(self, ws: str, override: dict) -> list:
        """The build's problems if override were committed; [] when it would build."""
        with self.db.tx(ws) as c:
            desired = self.desired(c, ws, override)
        with tempfile.TemporaryDirectory() as tmp:
            snap = Path(tmp) / "snapshot"
            self.write(snap, desired)
            return self.check(snap)

    def ensure(self, ws: str) -> tuple:
        """(graph path, version, snapshot folder) for the workspace, current with the log."""
        with self.db.tx(ws) as c:
            version = c.execute(sa.select(t.workspaces.c.state_version).where(t.workspaces.c.id == ws)).scalar_one()
        folder = self.folder(ws)
        current = folder / "current.json"

        def cached():
            try:
                got = json.loads(current.read_text(encoding="utf-8"))
                path = folder / "graphs" / got["graph"]
                if got["version"] >= version and path.is_file():
                    return path, got["version"], folder / "snapshot"
            except (OSError, ValueError, KeyError):
                pass
            return None

        hit = cached()
        if hit:
            return hit
        folder.mkdir(parents=True, exist_ok=True)
        with _lock(ws), fasteners.InterProcessLock(str(folder / ".lock")):
            hit = cached()
            if hit:
                return hit
            with self.db.engine.connect() as raw:
                if self.db.postgres:
                    raw = raw.execution_options(isolation_level="REPEATABLE READ")
                with raw.begin():
                    if self.db.postgres:
                        raw.execute(sa.text("SELECT set_config('kl.workspace_id', :w, true)"), {"w": ws})
                    version = raw.execute(sa.select(t.workspaces.c.state_version)
                                          .where(t.workspaces.c.id == ws)).scalar_one()
                    desired = self.desired(raw, ws)
            self.write(folder / "snapshot", desired)
            graphs = folder / "graphs"
            graphs.mkdir(exist_ok=True)
            name = f"graph-{version}-{ids.new('b', 6)[2:]}.db"
            tmp = graphs / (name + ".part")
            self.build(folder / "snapshot", tmp)
            tmp.replace(graphs / name)
            current.write_text(json.dumps({"version": version, "graph": name, "built": self.clock.stamp()}),
                               encoding="utf-8")
            self._prune_pending(ws, version)
            keep = {name}
            for old in sorted(graphs.glob("graph-*.db"), key=lambda p: p.stat().st_mtime, reverse=True)[2:]:
                if old.name in keep:
                    continue
                with contextlib.suppress(OSError):  # in use on Windows: removed next time
                    old.unlink()
            return graphs / name, version, folder / "snapshot"

    # ---- deferred updates: the project process reads the graph as built, and notes what it changes ----------

    PENDING = "pending-diff.jsonl"

    def current(self, ws: str) -> tuple:
        """(graph path, version, snapshot folder) as last built, even if the log has moved on since; built only
        when there is none yet. What turning an input into a project reads (graph_updates=deferred), so it never
        waits on a rebuild; what it changes waits in the pending diff."""
        folder = self.folder(ws)
        if any(e.get("change") == "source" and e.get("kind") not in DEFERRED_KINDS for e in self.pending(ws)):
            return self.ensure(ws)  # a document is what the graph is for: never read without it
        try:
            got = json.loads((folder / "current.json").read_text(encoding="utf-8"))
            path = folder / "graphs" / got["graph"]
            if path.is_file():
                return path, got["version"], folder / "snapshot"
        except (OSError, ValueError, KeyError):
            pass
        return self.ensure(ws)

    def defer(self, ws: str, entry: dict) -> None:
        """Note a change the graph does not hold yet: one line of the pending diff, applied later."""
        with self.db.tx(ws) as c:
            version = c.execute(sa.select(t.workspaces.c.state_version).where(t.workspaces.c.id == ws)).scalar_one()
        folder = self.folder(ws)
        folder.mkdir(parents=True, exist_ok=True)
        with _lock(ws), open(folder / self.PENDING, "a", encoding="utf-8") as f:
            f.write(json.dumps({**entry, "version": version, "at": self.clock.stamp()}, ensure_ascii=False) + "\n")

    def pending(self, ws: str) -> list:
        """The changes the graph does not hold yet, oldest first."""
        try:
            text = (self.folder(ws) / self.PENDING).read_text(encoding="utf-8")
        except OSError:
            return []
        return [json.loads(line) for line in text.splitlines() if line.strip()]

    def apply_pending(self, ws: str) -> dict:
        """Bring the graph up to date with everything noted, and clear the pending diff."""
        entries = self.pending(ws)
        _, version, _ = self.ensure(ws)
        return {"applied": len(entries), "version": version}

    def _prune_pending(self, ws: str, built: int) -> None:
        """A rebuild takes in everything up to its version: those lines of the pending diff are done."""
        path = self.folder(ws) / self.PENDING
        left = [e for e in self.pending(ws) if e.get("version", 0) > built]
        with contextlib.suppress(OSError):
            if left:
                path.write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in left), encoding="utf-8")
            else:
                path.unlink()

    def drop(self, ws: str) -> None:
        shutil.rmtree(self.folder(ws), ignore_errors=True)
