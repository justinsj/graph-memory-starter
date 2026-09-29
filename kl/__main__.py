"""python -m kl <command>

    serve [--host 127.0.0.1] [--port 8080]      run the API and MCP server (settings from KL_* variables)
    init --workspace SLUG --name NAME --admin-email EMAIL --admin-name NAME
                                                a workspace, its first admin, and the admin's key
    service-account --workspace SLUG --name NAME --scopes a,b,c
                                                a service account and its key (e.g. an orchestrator)
    openapi [FILE]                              the OpenAPI document (to FILE, or stdout)
"""
import argparse
import json
import sys


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(prog="python -m kl", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8080)
    i = sub.add_parser("init")
    i.add_argument("--workspace", required=True)
    i.add_argument("--name", required=True)
    i.add_argument("--admin-email", required=True)
    i.add_argument("--admin-name", required=True)
    a = sub.add_parser("service-account")
    a.add_argument("--workspace", required=True)
    a.add_argument("--name", required=True)
    a.add_argument("--scopes", required=True)
    o = sub.add_parser("openapi")
    o.add_argument("file", nargs="?")
    args = ap.parse_args(argv)

    from .service import Service
    if args.cmd == "openapi":
        import tempfile
        from pathlib import Path
        from .api import create_app
        from .config import Settings
        svc = Service(Settings(data_dir=Path(tempfile.mkdtemp())))
        doc = json.dumps(create_app(svc).openapi(), indent=1, ensure_ascii=False)
        if args.file:
            Path(args.file).write_text(doc + "\n", encoding="utf-8")
            print(f"wrote {args.file}")
        else:
            print(doc)
        return
    svc = Service()
    if args.cmd == "serve":
        import uvicorn
        from .api import create_app
        svc.start_background()
        uvicorn.run(create_app(svc), host=args.host, port=args.port)
    elif args.cmd == "init":
        out = svc.bootstrap(args.workspace, args.name, args.admin_email, args.admin_name)
        print(json.dumps(out, indent=1))
    elif args.cmd == "service-account":
        import sqlalchemy as sa
        from . import db as t
        from .core import Principal
        with svc.db.tx(system=True) as c:
            ws = c.execute(sa.select(t.workspaces.c.id).where(t.workspaces.c.slug == args.workspace)).scalar()
        if not ws:
            sys.exit(f"no workspace {args.workspace}")
        admin = Principal("root", "root", ws, "operator", "admin", frozenset({"root"}))
        print(json.dumps(svc.create_service_account(admin, args.name, args.scopes.split(",")), indent=1))


if __name__ == "__main__":
    main()
