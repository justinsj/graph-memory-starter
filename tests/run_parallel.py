"""Every test module in its own process, several at once.

    python tests/run_parallel.py            all of tests/test_*.py, one process per CPU (at most 8)
    python tests/run_parallel.py -j 4 kl    four at a time, only modules whose name contains "kl"

The modules share nothing (each makes its own temporary folders and databases),
so the wall time is about the slowest module's rather than the sum. Prints each
module's count and time, slowest first, and exits 1 if any failed.
"""
import argparse
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(module: str) -> dict:
    t0 = time.time()
    out = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", f"{module}.py"], cwd=ROOT, capture_output=True,
                         text=True, encoding="utf-8", errors="replace", env={**os.environ, "PYTHONUTF8": "1"})
    tail = out.stderr.strip().splitlines()
    ran = re.search(r"Ran (\d+) tests? in ([\d.]+)s", out.stderr)
    return {"module": module, "ok": out.returncode == 0, "tests": int(ran.group(1)) if ran else 0,
            "seconds": time.time() - t0, "last": tail[-1] if tail else "", "log": out.stderr}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("-j", type=int, default=min(8, os.cpu_count() or 2))
    ap.add_argument("match", nargs="?", default="")
    args = ap.parse_args()
    modules = sorted(p.stem for p in (ROOT / "tests").glob("test_*.py") if args.match in p.stem)
    t0 = time.time()
    with ThreadPoolExecutor(args.j) as pool:
        results = list(pool.map(run, modules))
    wall = time.time() - t0
    for r in sorted(results, key=lambda r: -r["seconds"]):
        print(f"{'ok  ' if r['ok'] else 'FAIL'} {r['module']:<32} {r['tests']:>4} tests {r['seconds']:6.1f} s  {r['last']}")
    failed = [r for r in results if not r["ok"]]
    for r in failed:
        print(f"\n===== {r['module']} =====\n{r['log'][-6000:]}")
    total = sum(r["tests"] for r in results)
    print(f"\n{total} tests in {len(results)} modules: {wall:.1f} s wall, {sum(r['seconds'] for r in results):.1f} s "
          f"if run one after another; {len(failed)} module(s) failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
