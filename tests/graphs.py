"""Test graphs: the repo's extraction plus made-up docs, built into a temp folder.

Not a test file itself; the test files import it.

The tests run as of 23 September 2026 (GRAPH_MEMORY_TODAY), so a question
about "March" means March 2026 whatever day they run, and dated facts in the
extraction never expire under them. Hook subprocesses inherit the setting.
"""
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TODAY = "2026-09-23"
os.environ["GRAPH_MEMORY_TODAY"] = TODAY
sys.path.insert(0, str(ROOT / "src"))
import build_graph  # noqa: E402
import recall  # noqa: E402

REFUND = "A customer wants an £800 refund in March. Who signs it off?"
POLICY_TEXT = "Needs sign-off before money moves; reviewed each quarter by finance"


def _claims(text: str) -> list:
    return [{"kind": "rule", "text": text}] if text else []


def policies(n: int, text: str = POLICY_TEXT) -> dict:
    """n policies, each approved by the Ops Manager: one busy node, next to the question."""
    return {"source_doc": "synthetic-policies.md",
            "nodes": [{"name": f"Policy {k}", "type": "POLICY", "claims": _claims(text)}
                      for k in range(n)],
            "edges": [{"source": f"Policy {k}", "predicate": "approved_by",
                       "target": "Ops Manager"} for k in range(n)]}


def clusters(n: int) -> dict:
    """n separate policy -> role -> person chains, nowhere near the question."""
    nodes, edges = [], []
    for k in range(n):
        nodes += [{"name": f"Policy {k}", "type": "POLICY", "claims": _claims(POLICY_TEXT)},
                  {"name": f"Role {k}", "type": "ROLE", "claims": _claims(POLICY_TEXT)},
                  {"name": f"Person {k}", "type": "PERSON", "claims": _claims(POLICY_TEXT)}]
        edges += [{"source": f"Policy {k}", "predicate": "approved_by", "target": f"Role {k}"},
                  {"source": f"Role {k}", "predicate": "held_by", "target": f"Person {k}"}]
    return {"source_doc": "synthetic-clusters.md", "nodes": nodes, "edges": edges}


def build(folder: Path, *extra: dict, docs: Path = None, records: Path = None,
          records_root: Path = None, code: Path = None) -> Path:
    """The repo's extraction plus the extra docs, built into folder/graph.db.

    Quotes are checked against `docs`, the repo's corpus/ unless given. No
    project records unless `records` names a folder of them (their sources
    resolve against `records_root`), so records of your own never leak in.
    """
    folder = Path(folder)
    ext = folder / "extraction"
    shutil.copytree(ROOT / "extraction", ext)
    for i, doc in enumerate(extra):
        (ext / f"zz-extra-{i}.json").write_text(json.dumps(doc, ensure_ascii=False),
                                                encoding="utf-8")
    db = folder / "graph.db"
    build_graph.build(extraction=ext, db_path=db, docs_root=docs,
                      records=records or folder / "records", records_root=records_root, code=code)
    return db


def edges(facts) -> set:
    return {(f.source, f.predicate, f.target) for f in facts.triples}


def claims(facts) -> set:
    return {(name, text) for name, text, _, _ in facts.notes}
