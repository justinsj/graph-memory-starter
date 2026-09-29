"""Who turns a document into facts, and a transcript into proposed project changes.

The service never trusts an extractor's output: every quote is checked against
the document's text, and every change set goes through the project checks. So
an extractor is swappable: a model through the Claude CLI, a fixed set of
answers for tests, or none at all (callers then send the extraction
themselves, POST /v1/sources/{id}/extraction).
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROMPT = ROOT / "extract-prompt.md"


class NoExtractor:
    name = "none"

    def extract(self, text: str, path: str):
        return None  # the caller sends it

    def propose_changes(self, text: str, path: str, kind: str, on: str, records: dict, entities: list):
        return None


class FixtureExtractor:
    """Answers from a folder of extraction JSON (the repo's extraction/ by default), matched by file name."""
    name = "fixture"

    def __init__(self, folder: Path = None, changes: dict = None):
        self.by_name = {}
        for f in sorted(Path(folder or ROOT / "extraction").glob("*.json")):
            doc = json.loads(f.read_text(encoding="utf-8"))
            self.by_name[Path(doc["source_doc"]).name] = doc
        self.changes = changes or {}  # file name -> change set changes

    def extract(self, text: str, path: str):
        doc = self.by_name.get(Path(path).name)
        return json.loads(json.dumps(doc)) if doc else None

    def propose_changes(self, text, path, kind, on, records, entities):
        return self.changes.get(Path(path).name)


class ClaudeCliExtractor:
    """extract-prompt.md and the document, through `claude -p`; the reply's JSON is the extraction."""

    def __init__(self, model: str = "claude-sonnet-5"):
        self.model = model
        self.name = f"claude-cli:{model}"

    def _ask(self, prompt: str, body: str) -> str:
        claude = shutil.which("claude")
        if not claude:
            raise RuntimeError("the claude CLI is not on the PATH")
        out = subprocess.run([claude, "-p", "--model", self.model, "--output-format", "text"],
                             input=f"{prompt}\n\n---\n\n{body}", capture_output=True, text=True, encoding="utf-8",
                             timeout=600)
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

    def propose_changes(self, text, path, kind, on, records, entities):
        sys.path.insert(0, str(ROOT / "projects"))
        import ingest  # projects/ingest.py: its prompt, parsing and one repair round
        diff = ingest.propose(path, text, records, entities, kind=kind, on=on,
                              llm=lambda prompt, body: self._ask(prompt, body))
        return diff["changes"]


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
