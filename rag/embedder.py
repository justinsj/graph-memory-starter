"""A warm embedding model, so a search does not load it every time. Optional.

    python embedder.py --start    start one in the background, if none is running
    python embedder.py --stop     stop it

Loading the model is most of a search's time (about 1.4 s a prompt in the
recall hook). With this running, search.py asks it for the query vector
instead and falls back to loading the model itself when it is not there.
rag/hooks.json starts it at the beginning of a session, and so does the graph's
hooks.json, for its fallback to your notes. With no index to search it does not
start.

It listens on 127.0.0.1 only, answers only requests carrying a random key kept
in your temp folder, and exits after IDLE_MINUTES without a request.
"""
import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

IDLE_MINUTES = 30
INDEX = Path(os.environ.get("GRAPH_MEMORY_RAG_DB") or Path(__file__).resolve().parent / "rag.db")
STATE = Path(os.environ.get("GRAPH_MEMORY_STATE") or Path(tempfile.gettempdir()) / "graph-memory") \
    / "embedder.json"


def _state():
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _ask(request: dict, timeout: float):
    """One request to the running embedder, or None when there is none."""
    state = _state()
    if not state:
        return None
    try:
        with socket.create_connection(("127.0.0.1", state["port"]), timeout=timeout) as s:
            s.settimeout(timeout)
            s.sendall((json.dumps({**request, "key": state["key"]}) + "\n").encode("utf-8"))
            data = b""
            while not data.endswith(b"\n"):
                chunk = s.recv(65536)
                if not chunk:
                    break
                data += chunk
        return json.loads(data.decode("utf-8"))
    except (OSError, ValueError, KeyError):
        return None


def embed(texts: list):
    """Vectors from the warm model, or None when it is not running."""
    reply = _ask({"texts": texts}, timeout=5.0)
    return reply.get("vectors") if isinstance(reply, dict) else None


def running() -> bool:
    return isinstance(_ask({"ping": True}, timeout=0.5), dict)


def serve() -> None:
    from fastembed import TextEmbedding

    model = TextEmbedding()  # the same default model build_index.py uses
    key = secrets.token_hex(16)
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(8)
    server.settimeout(IDLE_MINUTES * 60)
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps({"port": server.getsockname()[1], "key": key,
                                 "pid": os.getpid()}), encoding="utf-8")
    try:
        while True:
            try:
                conn, _ = server.accept()
            except socket.timeout:
                return  # idle: nobody needs it any more
            with conn:
                conn.settimeout(10)
                data = b""
                while not data.endswith(b"\n"):
                    chunk = conn.recv(65536)
                    if not chunk:
                        break
                    data += chunk
                try:
                    request = json.loads(data.decode("utf-8"))
                except ValueError:
                    continue
                if request.get("key") != key:
                    continue
                if request.get("stop"):
                    conn.sendall(b"{}\n")
                    return
                reply = {"ok": True} if request.get("ping") else {
                    "vectors": [[float(x) for x in v] for v in model.embed(request.get("texts", []))]}
                conn.sendall((json.dumps(reply) + "\n").encode("utf-8"))
    finally:
        server.close()
        state = _state()
        if state and state.get("key") == key:
            STATE.unlink(missing_ok=True)


def start() -> None:
    """Start one in the background and return at once; the model loads there."""
    if not INDEX.is_file() or running():  # no index, nothing will ask it
        return
    try:
        import fastembed  # noqa: F401  nothing to warm without it
    except ImportError:
        return
    flags = {"creationflags": subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP} \
        if sys.platform == "win32" else {"start_new_session": True}
    subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--serve"],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, **flags)


if __name__ == "__main__":
    if "--serve" in sys.argv:
        serve()
    elif "--stop" in sys.argv:
        _ask({"stop": True}, timeout=2.0)
    else:
        start()
