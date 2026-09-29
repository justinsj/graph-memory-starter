"""OpenSpec, read in code: no model is needed, the format is strict enough.

Three uses:
- specs_to_extraction: openspec/specs/ and the archived changes become graph
  facts. Each capability, requirement and scenario is an entity; each
  requirement's SHALL sentence and each scenario is a claim quoting its own
  line. Archived changes carry their date in the folder name, so a MODIFIED
  requirement ends the old claim that day and starts the new one, and a
  REMOVED one ends it.
- change_to_plan: an open change folder becomes a plan. tasks.md gives the
  tasks, in order (it has no graph of its own); the scenarios in its spec
  deltas become the deliverable's acceptance checks.
- link_tests: a test whose name says a scenario's name verifies it
  (test_code_required and "Scenario: Code required").
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import tokens  # noqa: E402  the graph's own word splitting

MAX_QUOTE = 300
REQ = re.compile(r"^###\s+Requirement:\s*(.+?)\s*$")
SCN = re.compile(r"^####\s+Scenario:\s*(.+?)\s*$")
SECTION = re.compile(r"^##\s+(.+?)\s*$")
BULLET = re.compile(r"^\s*[-*]\s+\*\*(WHEN|THEN|AND|GIVEN)\*\*\s*(.+?)\s*$", re.I)
TASK = re.compile(r"^\s*[-*]\s+\[( |x|X)\]\s+(?:(\d+(?:\.\d+)*)\.?\s+)?(.+?)\s*$")
TASK_SECTION = re.compile(r"^##\s+(\d+)\.?\s+(.+?)\s*$")
ARCHIVED = re.compile(r"(?:^|/)changes/archive/(\d{4}-\d{2}-\d{2})-([^/]+)/specs/([^/]+)/spec\.md$")
CURRENT = re.compile(r"(?:^|/)specs/([^/]+)/spec\.md$")


def _requirements(lines, start=0, end=None):
    """[(name, first line, body lines [(n, text)], scenarios)] between two line numbers."""
    end = len(lines) if end is None else end
    out, cur, scn = [], None, None
    for n in range(start, end):
        line = lines[n]
        m = REQ.match(line)
        if m:
            cur = {"name": m.group(1), "line": n + 1, "body": [], "scenarios": [], "fields": {}}
            out.append(cur)
            scn = None
            continue
        if cur is None:
            continue
        m = SCN.match(line)
        if m:
            scn = {"name": m.group(1), "line": n + 1, "steps": []}
            cur["scenarios"].append(scn)
            continue
        if SECTION.match(line) and not line.startswith("###"):
            cur, scn = None, None
            continue
        b = BULLET.match(line)
        if scn is not None and b:
            scn["steps"].append((b.group(1).upper(), b.group(2), n + 1))
        elif scn is None and line.strip():
            f = re.match(r"^\*\*(Reason|Migration)\*\*:\s*(.+)$", line.strip())
            if f:
                cur["fields"][f.group(1).lower()] = f.group(2)
            else:
                cur["body"].append((n + 1, line.strip()))
    return out


def parse_spec(text: str) -> dict:
    lines = text.split("\n")
    purpose = None
    for i, line in enumerate(lines):
        if re.match(r"^##\s+Purpose\s*$", line):
            for j in range(i + 1, len(lines)):
                if lines[j].strip() and not lines[j].startswith("#"):
                    purpose = (j + 1, lines[j].strip())
                    break
            break
    return {"purpose": purpose, "requirements": _requirements(lines)}


def parse_delta(text: str) -> dict:
    lines = text.split("\n")
    marks = [(i, m.group(1).strip().upper()) for i, line in enumerate(lines) if (m := SECTION.match(line))]
    out = {"ADDED": [], "MODIFIED": [], "REMOVED": [], "RENAMED": [], "purpose": None}
    for k, (i, title) in enumerate(marks):
        end = marks[k + 1][0] if k + 1 < len(marks) else len(lines)
        kind = title.split()[0]
        if kind in ("ADDED", "MODIFIED", "REMOVED"):
            out[kind] = _requirements(lines, i, end)
        elif kind == "RENAMED":
            pairs, frm = [], None
            for n in range(i, end):
                m = re.search(r"FROM:\s*`?###\s*Requirement:\s*(.+?)`?\s*$", lines[n])
                t = re.search(r"TO:\s*`?###\s*Requirement:\s*(.+?)`?\s*$", lines[n])
                if m:
                    frm = m.group(1)
                elif t and frm:
                    pairs.append((frm, t.group(1)))
                    frm = None
            out["RENAMED"] = pairs
        elif kind == "PURPOSE":
            for n in range(i + 1, end):
                if lines[n].strip():
                    out["purpose"] = (n + 1, lines[n].strip())
                    break
    return out


def _shall(req) -> tuple:
    """The requirement's statement: its first line with SHALL or MUST, else its first line."""
    for n, line in req["body"]:
        if re.search(r"\b(SHALL|MUST)\b", line):
            return n, line
    return req["body"][0] if req["body"] else (req["line"], req["name"])


def _clip(text: str) -> str:
    return text if len(text) <= MAX_QUOTE else text[:MAX_QUOTE].rsplit(" ", 1)[0]


def _scenario_claim(s) -> dict:
    when = " ".join(t for k, t, _ in s["steps"] if k in ("WHEN", "GIVEN"))
    then = " ".join(t for k, t, _ in s["steps"] if k in ("THEN", "AND"))
    first_when = next(((k, t) for k, t, _ in s["steps"] if k in ("WHEN", "GIVEN")), None)
    first_then = next(((k, t) for k, t, _ in s["steps"] if k == "THEN"), None)
    quote = None
    if first_when and first_then:
        quote = f"{first_when[0]} {first_when[1]} - {first_then[0]} {first_then[1]}"
        if len(quote) > MAX_QUOTE:
            quote = f"{first_then[0]} {first_then[1]}"
    elif s["steps"]:
        k, t, _ = s["steps"][0]
        quote = f"{k} {t}"
    text = f"When {when}, then {then}." if when and then else (then or when or s["name"])
    return {"kind": "rule", "text": text[:600], "quote": _clip(quote) if quote else None}


def _problems_of(req, where, removed=False) -> list:
    out = []
    if removed:
        for f in ("reason", "migration"):
            if f not in req["fields"]:
                out.append(f"{where}: a REMOVED requirement needs a **{f.title()}**")
        return out
    if not any(re.search(r"\b(SHALL|MUST)\b", line) for _, line in req["body"]):
        out.append(f"{where}: a requirement says SHALL or MUST")
    if not req["scenarios"]:
        out.append(f"{where}: a requirement has at least one #### Scenario:")
    for s in req["scenarios"]:
        kinds = {k for k, _, _ in s["steps"]}
        if "WHEN" not in kinds or "THEN" not in kinds:
            out.append(f"{where}, scenario {s['name']}: needs a WHEN line and a THEN line")
    return out


# ---- specs into the graph -------------------------------------------------------------------------

def specs_to_extraction(files: dict, prefix: str = "") -> tuple:
    """(extraction docs, problems) for the openspec files of one repository.

    files: {path relative to the repository: text}. prefix: where those files sit
    in the graph's documents folder, so each claim's source_doc resolves there.
    """
    problems, docs = [], {}
    history = {}  # (cap, requirement) -> [{"req", "doc", "from", "to"}]

    def doc_for(path):
        src = f"{prefix}{path}"
        return docs.setdefault(src, {"source_doc": src, "nodes": [], "edges": [], "aliases": []})

    archived = sorted((m.group(1), m.group(2), m.group(3), path) for path in files
                      if (m := ARCHIVED.search(path)))
    for day, change, cap, path in archived:
        delta = parse_delta(files[path])
        for frm, to in delta["RENAMED"]:
            if (cap, frm) in history:
                history[(cap, to)] = history.pop((cap, frm))
        for kind in ("ADDED", "MODIFIED"):
            for req in delta[kind]:
                problems += _problems_of(req, f"{path}: {req['name']}")
                versions = history.setdefault((cap, req["name"]), [])
                if versions and versions[-1]["to"] is None:
                    versions[-1]["to"] = day
                versions.append({"req": req, "path": path, "from": day, "to": None})
        for req in delta["REMOVED"]:
            problems += _problems_of(req, f"{path}: {req['name']}", removed=True)
            versions = history.get((cap, req["name"]))
            if versions and versions[-1]["to"] is None:
                versions[-1]["to"] = day

    current = {m.group(1): path for path in files if (m := CURRENT.search(path)) and "/changes/" not in f"/{path}"}
    for cap, path in sorted(current.items()):
        spec = parse_spec(files[path])
        d = doc_for(path)
        cap_node = {"name": cap, "type": "CAPABILITY", "claims": []}
        if spec["purpose"]:
            cap_node["claims"].append({"kind": "note", "text": spec["purpose"][1][:600], "quote": _clip(spec["purpose"][1])})
        d["nodes"].append(cap_node)
        for req in spec["requirements"]:
            problems += _problems_of(req, f"{path}: {req['name']}")
            versions = history.get((cap, req["name"]))
            latest = versions[-1] if versions else None
            if latest and latest["to"] is None and _shall(latest["req"])[1] == _shall(req)[1]:
                continue  # the archive already says it, dated
            history.setdefault((cap, req["name"]), []).append({"req": req, "path": path, "from": None, "to": None})

    for (cap, name), versions in sorted(history.items()):
        for v in versions:
            d = doc_for(v["path"])
            rname = f"{cap}: {name}"
            dates = {k: val for k, val in (("valid_from", v["from"]), ("valid_to", v["to"])) if val}
            n, line = _shall(v["req"])
            d["nodes"].append({"name": rname, "type": "REQUIREMENT",
                               "claims": [{"kind": "rule", "text": line[:600], "quote": _clip(line), **dates}]})
            d["edges"].append({"source": rname, "predicate": "part_of", "target": cap, **dates})
            for s in v["req"]["scenarios"]:
                sname = f"{rname}: {s['name']}"
                claim = _scenario_claim(s)
                d["nodes"].append({"name": sname, "type": "SCENARIO",
                                   "claims": [{**claim, **dates}] if claim["quote"] else []})
                d["edges"].append({"source": sname, "predicate": "part_of", "target": rname, **dates})
    for cap in {c for c, _ in history} - set(current):  # capabilities only the archive knows
        first = next(v for (c, _), vs in sorted(history.items()) if c == cap for v in vs)
        doc_for(first["path"])["nodes"].append({"name": cap, "type": "CAPABILITY", "claims": []})
    return [docs[k] for k in sorted(docs)], problems


def scenarios(files: dict) -> list:
    """Every scenario entity name the specs give, for linking tests to them."""
    docs, _ = specs_to_extraction(files)
    return sorted({n["name"] for d in docs for n in d["nodes"] if n["type"] == "SCENARIO"})


def link_tests(test_names: list, scenario_names: list) -> list:
    """Edges TEST verifies SCENARIO, where the test's name, less 'test', is the scenario's name."""
    by_words = {}
    for s in scenario_names:
        by_words.setdefault(tuple(tokens.words(s.rsplit(": ", 1)[-1])), []).append(s)
    edges = []
    for t in test_names:
        w = tokens.words(t.rsplit(".", 1)[-1])
        if w and w[0] == "test":
            w = w[1:]
        for s in by_words.get(tuple(w), []):
            edges.append({"source": t, "predicate": "verifies", "target": s})
    return edges


# ---- a change folder into a plan ------------------------------------------------------------------

def change_to_plan(name: str, files: dict, parallel_sections: bool = False) -> tuple:
    """(plan, problems) for one change folder. files: {path within the change folder: text}."""
    problems = []
    proposal = files.get("proposal.md", "")
    design = files.get("design.md", "")
    tasks_md = files.get("tasks.md")
    if not proposal.strip():
        problems.append("the change has no proposal.md")
    if tasks_md is None:
        problems.append("the change has no tasks.md, so there is nothing to run")
        tasks_md = ""
    tasks, section, sections = [], None, {}
    for line in tasks_md.split("\n"):
        m = TASK_SECTION.match(line)
        if m:
            section = m.group(1)
            continue
        t = TASK.match(line)
        if t:
            key = t.group(2) or f"{section or len(sections) + 1}.{sum(1 for x in tasks if x['section'] == section) + 1}"
            tasks.append({"key": key, "title": t.group(3), "done": t.group(1).lower() == "x", "section": section})
    if not tasks and tasks_md:
        problems.append("tasks.md has no tasks (- [ ] 1.1 ...)")
    for i, t in enumerate(tasks):
        if parallel_sections:
            prev = [x["key"] for x in tasks if x["section"] is not None and t["section"] is not None
                    and int(x["section"]) == int(t["section"]) - 1]
        else:
            prev = [tasks[i - 1]["key"]] if i else []
        t["after"] = prev
    checks, caps = [], []
    for path, text in sorted(files.items()):
        m = re.match(r"^specs/([^/]+)/spec\.md$", path)
        if not m:
            continue
        cap = m.group(1)
        caps.append(cap)
        delta = parse_delta(text)
        if not any(delta[k] for k in ("ADDED", "MODIFIED", "REMOVED", "RENAMED")):
            problems.append(f"{path}: no ## ADDED, MODIFIED, REMOVED or RENAMED Requirements")
        for kind in ("ADDED", "MODIFIED"):
            for req in delta[kind]:
                problems += _problems_of(req, f"{path}: {req['name']}")
                for s in req["scenarios"]:
                    claim = _scenario_claim(s)
                    checks.append({"id": f"{cap}/{req['name']}/{s['name']}", "kind": "auto",
                                   "description": claim["text"], "requirement": f"{cap}: {req['name']}",
                                   "scenario": s["name"], "delta": kind})
        for req in delta["REMOVED"]:
            problems += _problems_of(req, f"{path}: {req['name']}", removed=True)
    why = re.search(r"(?is)##\s*Why\s*\n(.+?)(?=\n##|\Z)", proposal)
    what = re.search(r"(?is)##\s*What Changes\s*\n(.+?)(?=\n##|\Z)", proposal)
    summary = "\n\n".join(x.group(1).strip() for x in (why, what) if x) or proposal.strip()[:2000]
    plan = {"kind": "openspec", "title": name, "summary": summary, "design": design.strip(),
            "tasks": [{"key": t["key"], "title": t["title"], "instructions": t["title"], "after": t["after"],
                       "needs": [], "checks": [{"id": "done", "kind": "auto", "description": "the task is done"}],
                       "gate": False} for t in tasks],
            "checks": checks,
            "openspec": {"change": name, "capabilities": caps, "files": sorted(files)}}
    return plan, problems
