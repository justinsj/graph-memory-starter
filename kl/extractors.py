"""Who turns a document into facts, a transcript into proposed project changes, and a
project into a draft thesis (projects/impact.py) with the numbers it needs.

The service never trusts an extractor's output: every quote is checked against
the document's text, and every change set goes through the project checks. So
an extractor is swappable: a model through the Claude CLI, a fixed set of
answers for tests, or none at all (callers then send the extraction
themselves, POST /v1/sources/{id}/extraction).
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROMPT = ROOT / "extract-prompt.md"
THESIS_PROMPT = ROOT / "projects" / "thesis-prompt.md"


def _child_env() -> dict:
    """The environment for a claude -p child: Claude Code's own session markers left out, so it starts afresh."""
    return {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE")}


class NoExtractor:
    name = "none"

    def extract(self, text: str, path: str):
        return None  # the caller sends it

    def propose_changes(self, text: str, path: str, kind: str, on: str, records: dict, entities: list,
                        preloaded=False):
        return None

    def draft_thesis(self, record: dict, sources: dict, facts: str):
        return None  # a thesis comes from whoever proposes one, POST /v1/projects/{id}/thesis


class FixtureExtractor:
    """Answers from a folder of extraction JSON (the repo's extraction/ by default), matched by file name."""
    name = "fixture"

    def __init__(self, folder: Path = None, changes: dict = None, theses: dict = None):
        self.by_name = {}
        for f in sorted(Path(folder or ROOT / "extraction").glob("*.json")):
            doc = json.loads(f.read_text(encoding="utf-8"))
            self.by_name[Path(doc["source_doc"]).name] = doc
        self.changes = changes or {}  # file name -> change set changes
        self.theses = theses or {}  # project id -> draft thesis

    def extract(self, text: str, path: str):
        doc = self.by_name.get(Path(path).name)
        return json.loads(json.dumps(doc)) if doc else None

    def propose_changes(self, text, path, kind, on, records, entities, preloaded=False):
        return self.changes.get(Path(path).name)

    def draft_thesis(self, record, sources, facts):
        draft = self.theses.get(record["id"])
        return json.loads(json.dumps(draft)) if draft else None


class ClaudeCliExtractor:
    """extract-prompt.md and the document, through `claude -p`; the reply's JSON is the extraction.

    lean (the default): each call is a plain completion. The instructions go in as the system prompt and the
    payload as the one message; no tools, no settings, no MCP servers, no CLAUDE.md (an empty folder), so the
    model is not sent Claude Code's own prompt and tool definitions (about 20,000 tokens) it has no use for.
    lean=False sends instructions and payload together as the message, in Claude Code's own session."""

    def __init__(self, model: str = "claude-sonnet-5", lean: bool = True):
        self.model = model
        self.lean = lean
        self.name = f"claude-cli:{model}"

    def _argv(self, prompt: str) -> list:
        claude = shutil.which("claude")
        if not claude:
            raise RuntimeError("the claude CLI is not on the PATH")
        argv = [claude, "-p", "--model", self.model, "--output-format", "text"]
        if self.lean:
            argv += ["--tools", "", "--system-prompt", prompt, "--setting-sources", "local", "--strict-mcp-config",
                     "--no-session-persistence"]
        return argv

    def _ask(self, prompt: str, body: str) -> str:
        with tempfile.TemporaryDirectory(prefix="kl-ask-") as empty:
            out = subprocess.run(self._argv(prompt), input=body if self.lean else f"{prompt}\n\n---\n\n{body}",
                                 capture_output=True, text=True, encoding="utf-8", timeout=600,
                                 cwd=empty if self.lean else None, env=_child_env() if self.lean else None)
        if out.returncode:
            raise RuntimeError(f"claude -p failed: {out.stderr.strip()[:400]}")
        return out.stdout

    def extract(self, text: str, path: str):
        reply = self._ask(PROMPT.read_text(encoding="utf-8"), f"source_doc: {path}\n\n{text}")
        m = re.search(r"\{.*\}", reply, re.S)
        if not m:
            raise ValueError("the model's reply held no JSON")
        doc = json.loads(m.group(0))
        doc["source_doc"] = path
        return doc

    def propose_changes(self, text, path, kind, on, records, entities, preloaded=False):
        sys.path.insert(0, str(ROOT / "projects"))
        import ingest  # projects/ingest.py: its prompt, parsing and one repair round
        diff = ingest.propose(path, text, records, entities, kind=kind, on=on, preloaded=preloaded,
                              llm=lambda prompt, body: self._ask(prompt, body))
        return diff["changes"]

    def propose_with_thesis(self, text, path, kind, on, records, entities, figures, preloaded=False):
        """(changes, thesis draft or None): the change set and the new project's thesis in one call."""
        sys.path.insert(0, str(ROOT / "projects"))
        import ingest
        diff = ingest.propose(path, text, records, entities, kind=kind, on=on, figures=figures, preloaded=preloaded,
                              llm=lambda prompt, body: self._ask(prompt, body))
        thesis = diff.get("thesis")
        return diff["changes"], thesis if isinstance(thesis, dict) and thesis.get("change") else None

    def draft_thesis(self, record, sources, facts):
        body = json.dumps({"project": {k: record.get(k) for k in ("id", "title", "description", "deliverables",
                                                                   "dependencies", "questions")},
                           "sources": sources, "facts": facts}, ensure_ascii=False, indent=1)
        return self._thesis(body)

    def draft_thesis_from_input(self, text, path, facts, preloaded=False):
        """A thesis from the input alone, for the project it is about to create: run beside the change set's call.
        preloaded: facts are every figure the graph holds, and the call is told so."""
        body = json.dumps({"project": None, "sources": {path: text}, "facts": facts}, ensure_ascii=False, indent=1)
        if preloaded:
            sys.path.insert(0, str(ROOT / "projects"))
            import ingest
            body = ingest.preload_note("the input and every fact with a figure the graph holds") + body
        return self._thesis(body)

    def _thesis(self, body):
        reply = self._ask(THESIS_PROMPT.read_text(encoding="utf-8"), body)
        m = re.search(r"\{.*\}", reply, re.S)
        if not m:
            return None
        draft = json.loads(m.group(0))
        return draft if draft.get("change") else None


def from_setting(value: str):
    if not value or value == "none":
        return NoExtractor()
    if value.startswith("claude-cli"):
        _, _, model = value.partition(":")
        return ClaudeCliExtractor(model or "claude-sonnet-5")
    if value.startswith("fixture"):
        _, _, folder = value.partition(":")
        return FixtureExtractor(Path(folder) if folder else None)
    raise ValueError(f"unknown extractor {value!r}")
