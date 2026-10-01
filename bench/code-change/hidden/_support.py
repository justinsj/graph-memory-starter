"""What the hidden tests share: the shop's backend with every route registered, fresh state, the frontend's source.

The runner runs from the shop's backend folder, so the backend's modules import as the shop's own code does.
"""
import importlib
import re
from pathlib import Path

BACKEND = Path.cwd()
FRONTEND = BACKEND.parent / "frontend" / "src"


def client():
    """A Flask test client with every backend module imported (so every route is registered), and no refund pending."""
    for f in sorted(BACKEND.rglob("*.py")):
        rel = f.relative_to(BACKEND)
        if rel.parts[0] == "tests":
            continue
        parts = list(rel.with_suffix("").parts)
        if parts[-1] == "__init__":
            parts = parts[:-1]
        if parts:
            importlib.import_module(".".join(parts))
    import approvals
    from app import app
    approvals.PENDING.clear()
    app.testing = True
    return app.test_client()


def ts(path):
    """A frontend source file's text."""
    return (FRONTEND / path).read_text(encoding="utf-8")


def ts_function(source, name):
    """The whole of `export [async] function name(...) {...}`, or of `export const name = ...`, in TypeScript; '' if none."""
    m = re.search(r"export\s+(?:async\s+)?function\s+" + re.escape(name) + r"\b", source) or \
        re.search(r"export\s+const\s+" + re.escape(name) + r"\s*=", source)
    if not m:
        return ""
    i = source.find("{", source.find(")", m.end()) if "function" in m.group(0) else m.end())
    depth = 0
    for j in range(i, len(source)):
        depth += {"{": 1, "}": -1}.get(source[j], 0)
        if depth == 0:
            return source[m.start():j + 1]
    return source[m.start():]


def raises(fn, *args, match=""):
    """True when fn(*args) raises ValueError whose message holds match."""
    try:
        fn(*args)
    except ValueError as e:
        return match in str(e)
    return False
