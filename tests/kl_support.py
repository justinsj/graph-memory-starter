"""What the knowledge-layer tests share: a service on SQLite or Postgres, a workspace, the corpus, HTTP clients.

Postgres is a real server (pgserver's embedded PostgreSQL 16), started once per
test process. Each service gets its own database. The schema is created by the
owner, and the service connects as kl_app, a role that is not a superuser, so
row-level security applies to it as it would in production.
"""
import atexit
import itertools
import json
import os
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src"), str(ROOT / "tests")]
os.environ.setdefault("GRAPH_MEMORY_TODAY", "2026-09-28")

import graphs  # noqa: E402,F401  pins today, puts src/ on the path
from kl.config import Settings  # noqa: E402
from kl.extractors import FixtureExtractor  # noqa: E402
from kl.service import Service  # noqa: E402

CORPUS = ROOT / "corpus"
_pg = {"server": None, "n": itertools.count(1), "lock": threading.Lock()}


def postgres_available() -> bool:
    try:
        import pgserver  # noqa: F401
        import psycopg  # noqa: F401
        return True
    except ImportError:
        return False


def _server():
    with _pg["lock"]:
        if _pg["server"] is None:
            import pgserver
            srv = pgserver.get_server(tempfile.mkdtemp(prefix="kl-pg-"), cleanup_mode="stop")
            srv.psql("DO $$ BEGIN CREATE ROLE kl_app LOGIN; EXCEPTION WHEN duplicate_object THEN NULL; END $$;")
            _pg["server"] = srv
            atexit.register(srv.cleanup)
        return _pg["server"]


def postgres_urls() -> tuple:
    """(owner url, app url) for a fresh database."""
    srv = _server()
    name = f"kl_test_{os.getpid()}_{next(_pg['n'])}"
    srv.psql(f"CREATE DATABASE {name};")
    uri = srv.get_uri()  # postgresql://postgres:@127.0.0.1:port/postgres
    base = uri.rsplit("/", 1)[0].replace("postgresql://", "postgresql+psycopg://")
    owner = f"{base}/{name}"
    app = owner.replace("postgres:@", "kl_app:@", 1)
    return owner, app


def make_service(tmp: Path, backend: str = "sqlite", extractor=None, **settings) -> Service:
    tmp = Path(tmp)
    ex = extractor if extractor is not None else FixtureExtractor()
    base = {"data_dir": tmp / "data", "public_url": "http://testserver", **settings}
    if backend == "postgres":
        owner, app = postgres_urls()
        Service(Settings(database_url=owner, **base), extractor=ex, create=True, app_role="kl_app").close()
        svc = Service(Settings(database_url=app, **base), extractor=ex, create=False)
    else:
        svc = Service(Settings(**base), extractor=ex)
    return svc


def workspace(svc: Service, slug: str = "acme", role: str = "admin") -> tuple:
    """(bootstrap result, principal) for a new workspace with an admin."""
    boot = svc.bootstrap(slug, slug.title(), f"admin@{slug}.example", f"{slug.title()} Admin")
    return boot, svc.authenticate("Bearer " + boot["key"])


def person(svc: Service, admin, email: str, name: str, role: str):
    m = svc.add_member(admin, email, name, role)
    key = svc.create_user_key(admin, f"{name} key", user_id=m["user_id"])
    return svc.authenticate("Bearer " + key["key"]), key["key"]


def service_account(svc, admin, name="orchestrator", scopes=("read", "context:read", "runs:lease")):
    out = svc.create_service_account(admin, name, list(scopes))
    return svc.authenticate("Bearer " + out["key"]), out["key"]


def ingest_corpus(svc: Service, p, names=None) -> list:
    out = []
    for f in sorted(CORPUS.glob("*.md")):
        if names and f.name not in names:
            continue
        out.append(svc.ingest(p, name=f.name, data=f.read_bytes()))
    return out


_seeds = {}


def seeded(tmp: Path, **settings) -> tuple:
    """(service, bootstrap, admin principal): a workspace with the corpus ingested and its graph built,
    copied from a template made once per process, so a test that needs a fresh one pays for a copy only."""
    import shutil
    key = json.dumps(settings, sort_keys=True, default=str)
    if key not in _seeds:
        base = Path(tempfile.mkdtemp(prefix="kl-seed-"))
        svc = make_service(base, **settings)
        boot, p = workspace(svc)
        ingest_corpus(svc, p)
        svc.projector.ensure(p.workspace_id)
        svc.close()
        _seeds[key] = (base, boot)
        atexit.register(shutil.rmtree, base, True)
    base, boot = _seeds[key]
    shutil.copytree(base / "data", Path(tmp) / "data")
    svc = make_service(tmp, **settings)
    return svc, boot, svc.authenticate("Bearer " + boot["key"])


def zip_dir(folder: Path) -> bytes:
    import io
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for f in sorted(Path(folder).rglob("*")):
            if f.is_file() and "__pycache__" not in f.parts:
                z.write(f, f.relative_to(folder).as_posix())
    return buf.getvalue()


def without_extracted(text: str) -> str:
    """Context text less the extraction date, which is the day the service extracted, not the files' mtime."""
    import re
    return re.sub(r"extracted \d{4}-\d{2}-\d{2}", "extracted <date>", text)


def serve(app, port: int = None):
    """Run the app on a real port in a thread (for MCP clients, subprocess workers, the hook). Returns (url, stop)."""
    import socket
    import time

    import uvicorn
    if port is None:
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", lifespan="on")
    server = uvicorn.Server(config)
    th = threading.Thread(target=server.run, daemon=True)
    th.start()
    deadline = time.time() + 20
    while not server.started and time.time() < deadline:
        time.sleep(0.05)

    def stop():
        server.should_exit = True
        th.join(timeout=10)
    return f"http://127.0.0.1:{port}", stop


def dumps(x) -> str:
    return json.dumps(x, indent=1, ensure_ascii=False, default=str)
