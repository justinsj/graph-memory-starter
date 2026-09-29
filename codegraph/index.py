"""Index a codebase into the graph: what each symbol is, and everything that depends on it.

    python codegraph/index.py codegraph/cases/shop           what it finds, as text
    python src/build_graph.py --code codegraph/cases/shop     built into graph.db beside the documents

No model and no network. Python is read with the ast module. TypeScript and
JavaScript are read with a small scanner that knows the common shapes:
top-level functions and arrow functions, const strings and template strings,
named imports, fetch() calls, and JSX buttons with onClick.

What it records, in the graph's own format (the nodes, claims, edges and
aliases of extraction/*.json), so build_graph loads code as it loads documents
and checks every quoted line against its file:

    FUNCTION, COMPONENT, TEST  calls FUNCTION; reads VARIABLE; references FUNCTION (passed,
                               not called: a callback); requests ROUTE or ROUTE_CASE; looks_up
                               a lookup table it runs one entry of (followed back, not forward)
    VARIABLE                   a module-level constant; reads the constants it is built from;
                               references the functions a lookup table holds
    MODULE                     a source file; imports the symbols it names in an import
    ROUTE                      METHOD /path; handled_by the function behind it
    ROUTE_CASE                 METHOD /path when <body key> = <value>: part_of its ROUTE,
                               handled_by the handler, dispatches_to what that value runs
    UI_ACTION                  a button; triggers what its onClick runs; part_of its component

Every link also keeps where it happens: each call, read, reference, import,
request and dispatch is a site, with its file, line and the line itself (the
"sites" of each doc, the graph's call_sites table). A request keeps the body
fields it sends; a handler, the body fields it reads. So a change to a
function's arguments can be answered with every call that passes them, and a
change to what a handler reads with every client that builds that body.

Routes are matched across languages. The client's URL is resolved through
constants and template strings, and path parameters match whatever their
syntax (/api/orders/${id} and /api/orders/<order_id> are one route). A value
the client puts in the body, like action: "cancel", is matched to the server
branch that tests it, whether an if/elif or a lookup table
(BULK_ACTIONS[payload["action"]]), so the cancel button reaches cancel_order
and not the other branches behind the same URL. What a branch runs belongs to
its case, not to the handler.

Names are qualified by the codebase's top folder and the module
(backend.refunds.rules.needs_approval, frontend.api.submitRefund); a module is
its file path. The bare name is an alias, and src/tokens.py splits both into
words, so a question can say needs_approval, needsApproval or "needs approval".
"""
import ast
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

PY = (".py",)
TS = (".ts", ".tsx", ".js", ".jsx")
SKIP = {"node_modules", ".git", "__pycache__", "dist", "build", ".venv", "venv"}
ROUTE_ATTRS = {"get", "post", "put", "patch", "delete", "route"}
KEYWORDS = {"if", "for", "while", "switch", "return", "function", "catch", "typeof", "new", "await", "import",
            "export", "const", "let", "var", "async", "from", "as", "default", "of", "in", "true", "false", "null",
            "undefined", "this"}
CONSTANT = re.compile(r"[A-Z][A-Z0-9_]*")
CALLABLE = ("FUNCTION", "COMPONENT", "TEST")


def is_test_file(path: Path) -> bool:
    n = path.name
    return n.startswith("test_") or n.endswith(("_test.py", ".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx",
                                                ".test.js", ".spec.js"))


@dataclass
class Sym:
    name: str
    type: str
    file: str
    line: int
    language: str
    quote: str
    text: str
    kind: str = "note"
    value: str = None
    resolved: str = None
    aliases: list = field(default_factory=list)
    claims: list = field(default_factory=list)  # more (kind, text, quote)


class Index:
    def __init__(self, root: Path):
        self.root = root
        self.syms = {}
        self.edges = []  # (source, predicate, target, file)
        self.sites = []  # (source, predicate, target, file, line, quote, detail)
        self.lines = {}  # file -> its lines

    def add(self, sym: Sym) -> Sym:
        self.syms.setdefault(sym.name, sym)
        return self.syms[sym.name]

    def link(self, source, predicate, target, file, line=None, detail=None):
        if source == target:
            return
        edge = (source, predicate, target, file)
        if edge not in self.edges:
            self.edges.append(edge)
        if line:
            self.site(source, predicate, target, file, line, detail)

    def site(self, source, predicate, target, file, line, detail=None):
        """Where a link happens; also detail with no link of its own (a handler's body reads)."""
        site = (source, predicate, target, file, line, self.line(file, line), detail)
        if site not in self.sites:
            self.sites.append(site)

    def line(self, file, n) -> str:
        return self.lines[file][n - 1].strip()

    def module(self, file, language):
        """A file as an entity: what its imports depend on."""
        return self.add(Sym(file, "MODULE", file, 1, language, self.line(file, 1) or file, f"The file {file}")).name


def rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def files(root: Path, suffixes) -> list:
    return sorted(p for p in root.rglob("*") if p.suffix in suffixes and p.is_file()
                  and not any(part in SKIP for part in p.relative_to(root).parts))


def qualify(prefix: str, module: str, name: str = "") -> str:
    parts = [prefix] + (module.split(".") if module else [])
    if name and (not parts or parts[-1] != name):
        parts.append(name)
    return ".".join(p for p in parts if p)


# ---- Python ------------------------------------------------------------------------------------

def py_root(path: Path) -> Path:
    """The folder a module's absolute imports start from: above its outermost package."""
    folder = path.parent
    while (folder / "__init__.py").is_file():
        folder = folder.parent
    return folder


def py_module(path: Path, base: Path) -> tuple:
    parts = list(path.relative_to(base).with_suffix("").parts)
    is_pkg = parts[-1] == "__init__"
    return ".".join(parts[:-1] if is_pkg else parts), is_pkg


def resolve_from(module: str, is_pkg: bool, level: int, target: str) -> str:
    parts = module.split(".") if module else []
    pkg = parts if is_pkg else parts[:-1]
    base = (pkg[:len(pkg) - (level - 1)] if level > 1 else pkg) if level else []
    return ".".join(base + (target.split(".") if target else []))


def index_python(ix: Index, paths: list):
    mods = {}
    for path in paths:
        base = py_root(path)
        module, is_pkg = py_module(path, base)
        prefix = base.relative_to(ix.root).parts[0] if base != ix.root else ""
        src = path.read_text(encoding="utf-8")
        f = rel(path, ix.root)
        ix.lines[f] = src.splitlines()
        mods[module] = {"tree": ast.parse(src), "prefix": prefix, "is_pkg": is_pkg, "f": f, "src": src,
                        "test": is_test_file(path)}

    # pass 1: what each module defines
    local = {m: {} for m in mods}
    tables = {}  # lookup-table constant -> {key: function}
    for module, m in mods.items():
        f, src = m["f"], m["src"]
        for node in m["tree"].body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                q = qualify(m["prefix"], module, node.name)
                kind = "TEST" if m["test"] and node.name.startswith("test") else "FUNCTION"
                sym = ix.add(Sym(q, kind, f, node.lineno, "python", ix.line(f, node.lineno), f"Defined in {f}",
                                 aliases=[node.name]))
                doc = ast.get_docstring(node)
                if doc:
                    first = doc.strip().splitlines()[0].strip()
                    sym.claims.append(("note", first, first))
                local[module][node.name] = q
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for t in targets:
                    if isinstance(t, ast.Name) and CONSTANT.fullmatch(t.id) and node.value is not None:
                        q = qualify(m["prefix"], module, t.id)
                        value = ast.get_source_segment(src, node.value)
                        resolved = node.value.value if isinstance(node.value, ast.Constant) and \
                            isinstance(node.value.value, str) else None
                        ix.add(Sym(q, "VARIABLE", f, node.lineno, "python", ix.line(f, node.lineno),
                                   f"{t.id} = {value}", kind="value", value=value, resolved=resolved,
                                   aliases=[t.id]))
                        local[module][t.id] = q

    # imports, followed through re-exports (from refunds import needs_approval, where
    # refunds/__init__.py imports it from .rules)
    raw = {m: {} for m in mods}  # module -> local name -> (target module, name or None, line)
    for module, m in mods.items():
        for node in ast.walk(m["tree"]):
            if isinstance(node, ast.ImportFrom):
                target = resolve_from(module, m["is_pkg"], node.level, node.module or "")
                for a in node.names:
                    sub = f"{target}.{a.name}".strip(".")
                    raw[module][a.asname or a.name] = (sub, None, node.lineno) if sub in mods else \
                        (target, a.name, node.lineno)
            elif isinstance(node, ast.Import):
                for a in node.names:
                    if a.name in mods:
                        raw[module][a.asname or a.name] = (a.name, None, node.lineno)

    def lookup(module, name, depth=0):
        if name in local.get(module, {}):
            return local[module][name]
        got = raw.get(module, {}).get(name)
        if got and got[1] and depth < 5:
            return lookup(got[0], got[1], depth + 1)
        return None

    for module, m in mods.items():
        names = dict(local[module])
        for alias, (target, name, line) in raw[module].items():
            if name is None:
                names[alias] = ("module", target)
            elif (q := lookup(target, name)) is not None:
                names[alias] = q
                ix.link(ix.module(m["f"], "python"), "imports", q, m["f"], line)
        m["names"] = names

    # pass 2: constants built from constants, lookup tables, and each function's body
    for module, m in mods.items():
        names, f = m["names"], m["f"]
        for node in m["tree"].body:
            if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None:
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for t in targets:
                    q = names.get(getattr(t, "id", None))
                    if not isinstance(q, str) or ix.syms[q].type != "VARIABLE":
                        continue
                    for n in ast.walk(node.value):
                        other = names.get(n.id) if isinstance(n, ast.Name) else None
                        if isinstance(other, str) and ix.syms[other].type == "VARIABLE":
                            ix.link(q, "reads", other, f, n.lineno)
                        elif isinstance(other, str) and ix.syms[other].type in CALLABLE:
                            ix.link(q, "references", other, f, n.lineno)
                    if isinstance(node.value, ast.Dict):  # a lookup table of functions
                        table = {}
                        for k, v in zip(node.value.keys, node.value.values):
                            got = names.get(v.id) if isinstance(v, ast.Name) else None
                            if isinstance(k, ast.Constant) and isinstance(got, str) and ix.syms[got].type in CALLABLE:
                                table[k.value] = got
                        if table:
                            tables[q] = table
        for node in m["tree"].body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                _python_function(ix, node, names, m["names"][node.name], f, tables)


def _python_function(ix: Index, fn, names: dict, q: str, f: str, tables: dict):
    routes = []
    for dec in fn.decorator_list:
        if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute) and dec.func.attr in ROUTE_ATTRS \
                and dec.args and isinstance(dec.args[0], ast.Constant) and isinstance(dec.args[0].value, str):
            if dec.func.attr == "route":
                kw = next((k.value for k in dec.keywords if k.arg == "methods"), None)
                methods = [e.value.upper() for e in getattr(kw, "elts", []) if isinstance(e, ast.Constant)] or ["GET"]
            else:
                methods = [dec.func.attr.upper()]
            path = re.sub(r"<(?:[^:>]+:)?([^>]+)>", r"{\1}", dec.args[0].value)
            for method in methods:
                route = ix.add(Sym(f"{method} {path}", "ROUTE", f, dec.lineno, "python", ix.line(f, dec.lineno),
                                   f"{method} {path} is handled by {q}"))
                ix.link(route.name, "handled_by", q, f, dec.lineno)
                routes.append(route.name)

    def resolve(node):
        if isinstance(node, ast.Name):
            got = names.get(node.id)
            return got if isinstance(got, str) else None
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            got = names.get(node.value.id)
            if isinstance(got, tuple):
                return next((s for s in ix.syms if s.endswith(f"{got[1]}.{node.attr}")), None)
        return None

    body_vars, key_vars = set(), {}
    for node in ast.walk(fn):  # the request body, and names holding one of its values
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            v, name = node.value, node.targets[0].id
            if isinstance(v, ast.Call) and isinstance(v.func, ast.Attribute) and v.func.attr == "get_json" or \
                    isinstance(v, ast.Attribute) and v.attr == "json":
                body_vars.add(name)
            elif (key := _body_key(v, body_vars)) is not None:
                key_vars[name] = key

    def key_of(expr):
        return key_vars.get(expr.id) if isinstance(expr, ast.Name) else _body_key(expr, body_vars)

    def case_of(test):
        if isinstance(test, ast.Compare) and len(test.ops) == 1 and isinstance(test.ops[0], ast.Eq) and \
                isinstance(test.comparators[0], ast.Constant) and isinstance(test.comparators[0].value, str):
            key = key_of(test.left)
            return (key, test.comparators[0].value) if key else None
        return None

    cases = {}  # (key, value, line) -> [(target, line)]
    fields = {}  # body field -> first line it is read

    def visit(node, case):
        if isinstance(node, ast.If) and routes and (kv := case_of(node.test)):
            branch = (kv[0], kv[1], node.lineno, None)
            cases.setdefault(branch, [])
            visit(node.test, case)
            for s in node.body:
                visit(s, branch)
            for s in node.orelse:
                visit(s, case)
            return
        if isinstance(node, ast.Subscript) and routes and isinstance(node.value, ast.Name):
            table = resolve(node.value)
            key = key_of(node.slice)
            if table in tables and key:  # BULK_ACTIONS[payload["action"]]: one case per key
                ix.link(q, "looks_up", table, f, node.lineno)  # depends on the table; runs one entry, not all
                for value, target in tables[table].items():
                    cases.setdefault((key, value, node.lineno, table), []).append((target, node.lineno))
                visit(node.slice, case)
                return
        if (field_name := _body_key(node, body_vars)) and field_name not in fields:
            fields[field_name] = node.lineno
        if isinstance(node, ast.Call):
            target = resolve(node.func)
            if target and ix.syms[target].type in CALLABLE:
                if case:
                    cases[case].append((target, node.lineno))
                else:
                    ix.link(q, "calls", target, f, node.lineno)
            if isinstance(node.func, ast.Name):  # the name called is not also a reference to it
                for child in node.args + [k.value for k in node.keywords]:
                    visit(child, case)
                return
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            target = resolve(node)
            if target and ix.syms[target].type == "VARIABLE":
                ix.link(q, "reads", target, f, node.lineno)
            elif target and ix.syms[target].type in CALLABLE:
                ix.link(q, "references", target, f, node.lineno)  # passed on, not called: a callback
        for child in ast.iter_child_nodes(node):
            visit(child, case)

    for stmt in fn.body:
        visit(stmt, None)
    for route in routes:
        for name, line in fields.items():
            ix.site(q, "reads_body", route, f, line, detail=name)
    for (key, value, line, table), targets in cases.items():
        for route in routes:
            runs = ", ".join(dict.fromkeys(t for t, _ in targets)) or "nothing else"
            via = f" (from {table.rsplit('.', 1)[-1]})" if table else ""
            case = ix.add(Sym(f"{route} when {key} = {value}", "ROUTE_CASE", f, line, "python", ix.line(f, line),
                              f'When the request body\'s {key} is "{value}", {q} runs {runs}{via}', kind="rule"))
            ix.link(case.name, "part_of", route, f)
            ix.link(case.name, "handled_by", q, f, line)
            for target, at in targets:
                ix.link(case.name, "dispatches_to", target, f, at)


def _body_key(node, body_vars):
    """"action" for body["action"] or body.get("action"), where body is the request's JSON."""
    if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) and node.value.id in body_vars:
        s = node.slice
        return s.value if isinstance(s, ast.Constant) and isinstance(s.value, str) else None
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "get" and \
            isinstance(node.func.value, ast.Name) and node.func.value.id in body_vars and node.args and \
            isinstance(node.args[0], ast.Constant):
        return node.args[0].value
    return None


# ---- TypeScript and JavaScript -----------------------------------------------------------------

def mask(src: str) -> str:
    """The source with comments, strings and template literals blanked, lines kept: braces
    and parentheses can then be matched on the code alone."""
    out, i, n = list(src), 0, len(src)
    while i < n:
        c = src[i]
        if c == "/" and src[i + 1:i + 2] == "/":
            while i < n and src[i] != "\n":
                out[i] = " "
                i += 1
        elif c == "/" and src[i + 1:i + 2] == "*":
            while i < n and src[i:i + 2] != "*/":
                out[i] = " " if src[i] != "\n" else "\n"
                i += 1
            out[i:i + 2] = "  "
            i += 2
        elif c in "\"'`":
            i += 1
            while i < n and src[i] != c:
                if src[i] == "\\":
                    out[i] = " "
                    i += 1
                if i < n and src[i] != "\n":
                    out[i] = " "
                i += 1
            i += 1
        else:
            i += 1
    return "".join(out)


def match(masked: str, start: int, open_c: str, close_c: str) -> int:
    """The index of the bracket closing the one at start."""
    depth = 0
    for i in range(start, len(masked)):
        if masked[i] == open_c:
            depth += 1
        elif masked[i] == close_c:
            depth -= 1
            if depth == 0:
                return i
    return len(masked) - 1


def split_args(masked: str, raw: str, start: int, end: int) -> list:
    """(start offset, raw text) of each top-level argument between start and end."""
    out, depth, begin = [], 0, start
    for i in range(start, end):
        c = masked[i]
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        elif c == "," and depth == 0:
            out.append((begin, raw[begin:i].strip()))
            begin = i + 1
    if raw[begin:end].strip():
        out.append((begin, raw[begin:end].strip()))
    return out


def literal_fields(obj: str) -> tuple:
    """The keys of an object literal, and those whose value is a string literal."""
    keys = re.findall(r"(?:^|[{,])\s*([A-Za-z_$][\w$]*)\s*(?=[:,}])", obj)
    strings = re.findall(r"([A-Za-z_$][\w$]*)\s*:\s*[\"']([^\"']*)[\"']", obj)
    return list(dict.fromkeys(keys)), strings


def ts_root(path: Path, root: Path) -> Path:
    for parent in path.parents:
        if parent.name == "src" and parent.is_relative_to(root):
            return parent
        if parent == root:
            break
    return path.parent


def _expr_end(masked: str, start: int) -> int:
    """Where an expression starting at start ends: a ; or line end outside brackets."""
    depth = 0
    for i in range(start, len(masked)):
        c = masked[i]
        if c in "([{":
            depth += 1
        elif c in ")]}":
            if depth == 0:
                return i
            depth -= 1
        elif c in ";\n" and depth == 0:
            return i
    return len(masked)


def index_typescript(ix: Index, paths: list):
    mods = {}
    for path in paths:
        base = ts_root(path, ix.root)
        module = ".".join(path.relative_to(base).with_suffix("").parts)
        prefix = base.relative_to(ix.root).parts[0] if base != ix.root else ""
        raw = path.read_text(encoding="utf-8")
        f = rel(path, ix.root)
        ix.lines[f] = raw.splitlines()
        mods[module] = {"path": path, "base": base, "prefix": prefix, "raw": raw, "masked": mask(raw), "f": f,
                        "names": {}, "funcs": [], "test": is_test_file(path)}

    def line_of(m, offset):
        return m["raw"].count("\n", 0, offset) + 1

    # pass 1: top-level functions and constants
    decl = re.compile(r"\b(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(|"
                      r"\b(?:export\s+)?const\s+([A-Za-z_$][\w$]*)\s*(?::[^=\n]+)?=\s*")
    for module, m in mods.items():
        masked, raw, f = m["masked"], m["raw"], m["f"]
        depth = [0] * (len(masked) + 1)
        d = 0
        for i, c in enumerate(masked):
            depth[i] = d
            d += (c == "{") - (c == "}")
        for hit in decl.finditer(masked):
            if depth[hit.start()] != 0:
                continue
            name = hit.group(1) or hit.group(2)
            line = line_of(m, hit.start())
            is_tsx = m["path"].suffix in (".tsx", ".jsx")
            kind = "TEST" if m["test"] else "COMPONENT" if is_tsx and name[:1].isupper() else "FUNCTION"
            if hit.group(1):
                p_open = hit.end() - 1
                p_close = match(masked, p_open, "(", ")")
                b_open = masked.index("{", p_close)
                span = (b_open, match(masked, b_open, "{", "}"))
                params = raw[p_open + 1:p_close]
            else:
                rest = masked[hit.end():]
                arrow = re.match(r"(?:async\s*)?(\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>\s*", rest)
                if arrow:
                    start = hit.end() + arrow.end()
                    span = (start, match(masked, start, "{", "}")) if masked[start] == "{" else \
                        (start, _expr_end(masked, start))
                    params = arrow.group(1).strip("()")
                else:
                    end = _expr_end(masked, hit.end())
                    value = raw[hit.end():end].strip().rstrip(";")
                    if not re.fullmatch(r"(['\"`]).*\1|-?\d+(\.\d+)?", value, re.S):
                        continue
                    q = qualify(m["prefix"], module, name)
                    ix.add(Sym(q, "VARIABLE", f, line, "typescript", ix.line(f, line), f"{name} = {value}",
                               kind="value", value=value, aliases=[name]))
                    m["names"][name] = q
                    continue
            q = qualify(m["prefix"], module, name)
            ix.add(Sym(q, kind, f, line, "typescript", ix.line(f, line), f"Defined in {f}", aliases=[name]))
            m["names"][name] = q
            m["funcs"].append((name, q, span, [a.split(":")[0].split("=")[0].strip()
                                               for _, a in split_args(mask(params), params, 0, len(params))]))

    # imports: each named import of a project symbol is a site of its file
    imported = {}  # module -> {local name: (qualified, line)}
    for module, m in mods.items():
        imported[module] = {}
        for hit in re.finditer(r"import\s*\{([^}]*)\}\s*from\s*[\"']([^\"']+)[\"']", m["raw"]):
            names, target = hit.group(1), hit.group(2)
            if not target.startswith("."):
                continue
            path = (m["path"].parent / target).resolve()
            try:
                other = ".".join(path.relative_to(m["base"].resolve()).parts)
            except ValueError:
                continue
            if other not in mods:
                continue
            for part in names.split(","):
                bits = part.split(" as ")
                if bits[0].strip() in mods[other]["names"]:
                    q = mods[other]["names"][bits[0].strip()]
                    m["names"][bits[-1].strip()] = q
                    imported[module][bits[-1].strip()] = (q, line_of(m, hit.start()))
    for module, m in mods.items():
        for local_name, (q, line) in imported[module].items():
            ix.link(ix.module(m["f"], "typescript"), "imports", q, m["f"], line)

    def resolve_value(m, text, seen=()):
        text = text.strip().rstrip(";")
        if re.fullmatch(r"([\"']).*\1", text, re.S):
            return text[1:-1]
        if text.startswith("`") and text.endswith("`"):
            def sub(g):
                got = const_string(m, g.group(1).strip(), seen)
                return got if got is not None else "{}"
            return re.sub(r"\$\{([^}]*)\}", sub, text[1:-1])
        return const_string(m, text, seen)

    def const_string(m, name, seen=()):
        q = m["names"].get(name)
        if not q or q in seen or ix.syms[q].type != "VARIABLE":
            return None
        owner = next(mm for mm in mods.values() if mm["f"] == ix.syms[q].file)
        return resolve_value(owner, ix.syms[q].value, seen + (q,))

    for m in mods.values():
        for name, q in list(m["names"].items()):
            sym = ix.syms[q]
            if sym.type == "VARIABLE" and sym.file == m["f"]:
                sym.resolved = resolve_value(m, sym.value)
                if sym.resolved is not None and sym.resolved != sym.value.strip("\"'"):
                    sym.text += f', which is "{sym.resolved}"'
                for ref in re.findall(r"\$\{\s*([A-Za-z_$][\w$]*)\s*\}", sym.value):
                    if ref in m["names"]:
                        ix.link(q, "reads", m["names"][ref], m["f"], sym.line)

    # pass 2: inside each function
    requests, wrappers, pending = [], {}, []
    call = re.compile(r"(?<![\w$.])([A-Za-z_$][\w$]*)\s*\(")
    ident = re.compile(r"(?<![\w$.])([A-Za-z_$][\w$]*)(?![\w$])")
    for module, m in mods.items():
        masked, raw, f = m["masked"], m["raw"], m["f"]
        for name, q, (b0, b1), params in m["funcs"]:
            body_m = masked[b0:b1]
            claimed, handlers = [], {}
            for h in re.finditer(r"\bconst\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)"
                                 r"\s*=>\s*", body_m):
                s = b0 + h.end()
                handlers[h.group(1)] = (s, match(masked, s, "{", "}") if masked[s] == "{" else _expr_end(masked, s))
            for btn in re.finditer(r"<button\b", body_m):
                start = b0 + btn.start()
                tag_end = masked.index(">", start)
                on = re.search(r"onClick=\{", masked[start:tag_end + 1])
                while on and tag_end < match(masked, start + on.end() - 1, "{", "}"):
                    tag_end = masked.index(">", match(masked, start + on.end() - 1, "{", "}"))
                if not on:
                    continue
                e0 = start + on.end()
                e1 = match(masked, e0 - 1, "{", "}")
                expr = raw[e0:e1].strip()
                label = " ".join(raw[tag_end + 1:raw.index("</button>", tag_end)].split())
                span = handlers.get(expr, (e0, e1))
                claimed += [span, (e0, e1)]
                line = line_of(m, start)
                ui = ix.add(Sym(f"'{label}' button in {name}", "UI_ACTION", f, line, "typescript",
                                ix.line(f, line), f"The '{label}' button in {name}",
                                aliases=[label, f"{label} button"]))
                ix.link(ui.name, "part_of", q, f)
                for c in call.finditer(masked[span[0]:span[1]]):
                    target = m["names"].get(c.group(1))
                    if target and ix.syms[target].type in CALLABLE:
                        ix.link(ui.name, "triggers", target, f, line_of(m, span[0] + c.start()))

            def free(pos):
                return not any(a <= pos < b for a, b in claimed)

            called = set()
            for c in call.finditer(body_m):
                pos = b0 + c.start()
                target = m["names"].get(c.group(1))
                if c.group(1) in KEYWORDS or not free(pos) or not target:
                    continue
                if ix.syms[target].type in CALLABLE:
                    called.add(pos)
                    ix.link(q, "calls", target, f, line_of(m, pos))
                    p_close = match(masked, b0 + c.end() - 1, "(", ")")
                    pending.append((q, target, split_args(masked, raw, b0 + c.end(), p_close), f, line_of(m, pos)))
            for r in ident.finditer(body_m):
                pos = b0 + r.start()
                target = m["names"].get(r.group(1))
                if not target or not free(pos) or pos in called or r.group(1) in KEYWORDS:
                    continue
                if ix.syms[target].type == "VARIABLE":
                    ix.link(q, "reads", target, f, line_of(m, pos))
                elif ix.syms[target].type in CALLABLE and target != q and not re.match(r"\s*\(", masked[pos + len(r.group(1)):]):
                    ix.link(q, "references", target, f, line_of(m, pos))  # passed on, not called
            for fetch in re.finditer(r"(?<![\w$.])fetch\s*\(", body_m):
                a0 = b0 + fetch.end()
                args = split_args(masked, raw, a0, match(masked, a0 - 1, "(", ")"))
                url_expr = args[0][1] if args else ""
                url = resolve_value(m, url_expr) if args else None
                for ref in re.findall(r"\$\{\s*([A-Za-z_$][\w$]*)\s*\}", url_expr):
                    if ref in m["names"] and ix.syms[m["names"][ref]].type == "VARIABLE":
                        ix.link(q, "reads", m["names"][ref], f, line_of(m, b0 + fetch.start()))
                options_at, options = args[1] if len(args) > 1 else (a0, "")
                method = (re.search(r"method\s*:\s*[\"'](\w+)[\"']", options) or [None, "GET"])[1].upper()
                body = re.search(r"body\s*:\s*JSON\.stringify\(\s*([A-Za-z_$][\w$]*|\{.*?\})\s*\)", options, re.S)
                line = line_of(m, b0 + fetch.start())
                body_line, body_fields, strings = line, None, []
                if body and body.group(1).startswith("{"):
                    body_line = line_of(m, options_at + raw[options_at:].index(body.group(0)))
                    body_fields, strings = literal_fields(body.group(1))
                requests.append((q, method, url, url_expr, f, line, body_line, body_fields, strings))
                if body and body.group(1) in params:
                    wrappers[q] = (params.index(body.group(1)), body.group(1))

    # routes, matched across languages
    def norm(path):
        return re.sub(r"\{[^}]*\}", "{}", path or "").rstrip("/") or "/"

    server = {(s.name.split(" ", 1)[0], norm(s.name.split(" ", 1)[1])): s.name
              for s in ix.syms.values() if s.type == "ROUTE"}
    cases = {}
    for s in ix.syms.values():
        if s.type == "ROUTE_CASE":
            route, cond = s.name.split(" when ", 1)
            key, value = cond.split(" = ", 1)
            cases[(route, key, value)] = s.name

    def case_for(route, strings):
        return next((cases[(route, k, v)] for k, v in strings if (route, k, v) in cases), None)

    requested = {}
    for q, method, url, expr, f, line, body_line, body_fields, strings in requests:
        if url is None:
            continue
        route = server.get((method, norm(url)))
        if route is None:
            route = ix.add(Sym(f"{method} {url}", "ROUTE", f, line, "typescript", ix.line(f, line),
                               f"{method} {url} is requested by {q}; nothing in this codebase handles it")).name
        target = case_for(route, strings) or route  # a literal body value picks its branch, not the whole route
        ix.link(q, "requests", target, f, body_line, detail=", ".join(body_fields) if body_fields else None)
        requested[q] = route
        how = f" (the URL is {expr})" if not re.fullmatch(r"[\"'].*[\"']", expr) else ""
        if q in wrappers:
            how += f", with its {wrappers[q][1]} as the body"
        ix.syms[q].claims.append(("note", f"Sends {method} {route.split(' ', 1)[1]}{how}", ix.line(f, line)))
    for caller, callee, args, f, line in pending:  # a literal body passed to a request wrapper
        if callee not in wrappers or callee not in requested:
            continue
        i = wrappers[callee][0]
        if i >= len(args) or not args[i][1].startswith("{"):
            continue
        route = requested[callee]
        keys, strings = literal_fields(args[i][1])
        case = case_for(route, strings)
        if case:
            ix.link(caller, "requests", case, f, line, detail=", ".join(keys))
            k, v = next((k, v) for k, v in strings if (route, k, v) in cases)
            ix.syms[caller].claims.append(("rule", f'Sends {k} "{v}" to {route}', ix.line(f, line)))
        for k, v in strings:
            if (route, k, v) not in cases and any(key == k for (r, key, _) in cases if r == route):
                ix.syms[caller].claims.append(
                    ("note", f'Sends {k} "{v}" to {route}; the server has no branch for it', ix.line(f, line)))


# ---- the graph's format --------------------------------------------------------------------------

def index(root) -> dict:
    """Everything the codebase at root says, as extraction-format docs, one per file, with
    each doc's link sites, plus each symbol's place and value for the code_symbols table."""
    root = Path(root).resolve()
    ix = Index(root)
    py_files, ts_files = files(root, PY), files(root, TS)
    index_python(ix, py_files)
    index_typescript(ix, ts_files)
    docs = {}

    def doc(f):
        return docs.setdefault(f, {"source_doc": f, "nodes": [], "edges": [], "aliases": [], "sites": []})

    for s in ix.syms.values():
        claims = [{"kind": s.kind, "text": s.text, "quote": s.quote}]
        claims += [{"kind": k, "text": t, "quote": qt} for k, t, qt in dict.fromkeys(s.claims)]
        doc(s.file)["nodes"].append({"name": s.name, "type": s.type, "claims": claims})
        doc(s.file)["aliases"] += [{"entity": s.name, "alias": a} for a in dict.fromkeys(s.aliases) if a != s.name]
    for source, predicate, target, f in ix.edges:
        if source in ix.syms and target in ix.syms:
            doc(f)["edges"].append({"source": source, "predicate": predicate, "target": target})
    for source, predicate, target, f, line, quote, detail in ix.sites:
        if source in ix.syms and target in ix.syms:
            site = {"source": source, "predicate": predicate, "target": target, "line": line, "quote": quote}
            if detail:
                site["detail"] = detail
            doc(f)["sites"].append(site)
    newest = max((p.stat().st_mtime for p in py_files + ts_files), default=None)
    return {"docs": [docs[k] for k in sorted(docs)],
            "symbols": {s.name: {"type": s.type, "file": s.file, "line": s.line, "language": s.language,
                                 "value": s.value, "resolved": s.resolved} for s in ix.syms.values()},
            "files": len(py_files) + len(ts_files),
            "indexed": date.fromtimestamp(newest).isoformat() if newest else ""}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) < 2:
        sys.exit("usage: python codegraph/index.py <codebase folder> [--json]")
    result = index(sys.argv[1])
    if "--json" in sys.argv:
        print(json.dumps(result, indent=1, ensure_ascii=False))
        return
    kinds = {}
    for s in result["symbols"].values():
        kinds[s["type"]] = kinds.get(s["type"], 0) + 1
    sites = sum(len(d["sites"]) for d in result["docs"])
    print(f"{result['files']} files: " + ", ".join(f"{n} {k.lower()}" for k, n in sorted(kinds.items()))
          + f"; {sites} sites")
    for d in result["docs"]:
        for e in d["edges"]:
            print(f"  {e['source']} {e['predicate']} {e['target']}")


if __name__ == "__main__":
    main()
