"""The graph's hooks. additionalContext is the injection.

    python src/recall_hook.py            UserPromptSubmit: prompt in, injection out
    python src/recall_hook.py --forget   PreCompact and SessionStart: forget which
                                         source quotes this conversation was shown

Source quotes are not repeated within a conversation. The ones already sent
are remembered per session in a small file in the temp folder, forgotten when
the conversation is compacted or cleared (it no longer holds them), and after
SESSION_HOURS in any case. A resumed conversation keeps them.

When the prompt names nothing the graph knows, the injection still says so,
and adds the best passages from the RAG index, labelled as search results
rather than checked facts. No index, no passages: the loud line stays alone.

With KL_API_URL and a key (KL_API_KEY, or KL_RUN_TOKEN inside a run) set, the
facts come from the knowledge layer service instead (POST /v1/context), which
remembers per session which quotes it already sent. If the service cannot be
reached within KL_HOOK_TIMEOUT seconds (3), the hook answers in-process as
before, so a prompt is never held up by it.
"""
import json
import os
import re
import sqlite3
import sys
import tempfile
import time
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from recall import recall  # noqa: E402

RAG = Path(__file__).resolve().parents[1] / "rag"
SESSION_HOURS = 12  # a conversation idle longer than this is shown its quotes afresh
FALLBACK_HITS = 3  # passages when the graph has no match
FALLBACK_CHARS = 300  # per passage
FALLBACK_BUDGET = 1500  # in all, as the RAG hook's own budget


def state_file(session: str) -> Path:
    folder = os.environ.get("GRAPH_MEMORY_STATE") or Path(tempfile.gettempdir()) / "graph-memory"
    return Path(folder) / f"{re.sub(r'[^A-Za-z0-9_-]', '', session)[:80] or 'default'}.json"


def sent_before(session: str) -> set:
    path = state_file(session)
    try:
        if time.time() - path.stat().st_mtime > SESSION_HOURS * 3600:
            return set()
        return set(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return set()


def remember(session: str, keys: set) -> None:
    path = state_file(session)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(sorted(keys), ensure_ascii=False), encoding="utf-8")
        for old in path.parent.glob("*.json"):  # tidy away finished conversations
            if time.time() - old.stat().st_mtime > SESSION_HOURS * 3600:
                old.unlink(missing_ok=True)
    except OSError:
        pass  # an unwritable temp folder costs repeated quotes, never the prompt


def passages(prompt: str) -> list:
    """The RAG index's best passages for a prompt, trimmed to the budget; [] on any trouble."""
    db_path = Path(os.environ.get("GRAPH_MEMORY_RAG_DB") or RAG / "rag.db")
    if not db_path.is_file():
        return []
    try:
        sys.path.insert(0, str(RAG))
        import search  # rag/search.py: the keyword leg, the meaning leg, rank fusion

        with closing(sqlite3.connect(db_path)) as db:
            legs = {"keyword": search.keyword_leg(db, prompt)}
            meaning = search.meaning_leg(db, prompt)
            if meaning is not None:
                legs["meaning"] = meaning
            ranked, _ = search.fuse(legs)
            out, used = [], 0
            for rowid in ranked[:FALLBACK_HITS]:
                file, section, text = db.execute(
                    "SELECT file, section, text FROM chunks WHERE id = ?", (rowid,)).fetchone()
                body = " ".join(text.split())
                entry = f"[{file} § {section}] {body[:FALLBACK_CHARS]}" + (
                    "..." if len(body) > FALLBACK_CHARS else "")
                if out and used + len(entry) > FALLBACK_BUDGET:
                    break
                out.append(entry)
                used += len(entry)
        return out
    except Exception:  # the fallback never costs the prompt
        return []


def from_service(prompt: str, session: str):
    """The service's answer for a prompt, or None when there is no service or it cannot be reached."""
    url = os.environ.get("KL_API_URL")
    key = os.environ.get("KL_API_KEY") or os.environ.get("KL_RUN_TOKEN")
    if not url or not key:
        return None
    import urllib.request
    body = json.dumps({"question": prompt or " ", "session_id": f"claude-code:{session}" if session else None}).encode()
    req = urllib.request.Request(url.rstrip("/") + "/v1/context", data=body, method="POST",
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=float(os.environ.get("KL_HOOK_TIMEOUT", "3"))) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:  # noqa: BLE001  the in-process answer stands in
        return None


def main() -> None:
    sys.stdin.reconfigure(encoding="utf-8")  # Claude Code sends UTF-8; Windows would read cp1252
    payload = json.load(sys.stdin)
    session = str(payload.get("session_id") or "")
    if "--forget" in sys.argv:
        if payload.get("source") != "resume":  # a resumed conversation still has its quotes
            state_file(session).unlink(missing_ok=True)
        return
    prompt = payload.get("prompt", "")
    served = from_service(prompt, session)
    if served is not None:
        print(json.dumps({
            "systemMessage": f"memory: {len(served['facts'])} facts from the knowledge layer in {served['ms']:.1f} ms",
            "hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": served["text"]}}))
        return
    sent = sent_before(session) if session else set()
    facts = recall(prompt, sent=frozenset(sent))
    if session and facts.excerpt_keys:
        remember(session, sent | set(facts.excerpt_keys))
    status, context = facts.header(), facts.as_text()
    if not facts.triples and not facts.projects and not facts.code and not facts.problem and not facts.stopped:
        found = passages(prompt)
        if found:
            status += f"; {len(found)} passages from your notes"
            context += ("\nPassages from your notes that may help. These are search results, "
                        "not checked facts:\n" + "\n".join(found))
    print(json.dumps({
        "systemMessage": status,  # shown to the user at submit
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": context,
        }
    }))


if __name__ == "__main__":
    main()
