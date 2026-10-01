"""Run the shop's tests: every test_* function in each file, one after another. No pytest needed.

    python run_tests.py                    the shop's own tests (backend/tests), from the shop's folder
    python runner.py --json FILE...        the given files, a JSON summary on stdout (the grader's use)

Run from the shop's folder or its backend folder; the backend is what the tests import from.
"""
import importlib.util
import json
import os
import sys
import traceback
from pathlib import Path


def backend_dir() -> Path:
    here = Path.cwd()
    return here if (here / "app.py").is_file() else here / "backend"


def run(files):
    backend = backend_dir()
    os.chdir(backend)
    sys.path[:0] = [str(backend)] + sorted({str(Path(f).resolve().parent) for f in files})
    results = []
    for f in files:
        f = Path(f).resolve()
        spec = importlib.util.spec_from_file_location(f"t_{f.stem}", f)
        mod = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)
        except Exception as e:  # noqa: BLE001  a test file that does not import fails as a whole
            results.append({"file": f.name, "test": "(import)", "ok": False, "error": f"{type(e).__name__}: {e}"})
            continue
        for name in sorted(n for n in vars(mod) if n.startswith("test_") and callable(getattr(mod, n))):
            try:
                getattr(mod, name)()
                results.append({"file": f.name, "test": name, "ok": True})
            except Exception as e:  # noqa: BLE001
                tb = traceback.extract_tb(e.__traceback__)[-1]
                results.append({"file": f.name, "test": name, "ok": False,
                                "error": f"{type(e).__name__}: {e}"[:300], "at": f"{Path(tb.filename).name}:{tb.lineno}"})
    return results


def main():
    args = sys.argv[1:]
    as_json = "--json" in args
    files = [a for a in args if a != "--json"] or sorted(str(p) for p in (backend_dir() / "tests").glob("test_*.py"))
    results = run(files)
    if as_json:
        print(json.dumps(results))
        return
    for r in results:
        print(f"{'ok  ' if r['ok'] else 'FAIL'} {r['file']}::{r['test']}" + ("" if r["ok"] else f"  {r['error']}"))
    failed = sum(not r["ok"] for r in results)
    print(f"{len(results) - failed} passed, {failed} failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
