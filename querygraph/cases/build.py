"""Build the case databases from each folder's schema.sql and seed.py.

    python querygraph/cases/build.py              every database, into querygraph/cases/<name>/<name>.db
    python querygraph/cases/build.py --out DIR    into DIR/<name>.db instead

The seeds are deterministic, so the answers in questions.json hold on every build.
"""
import argparse
import importlib.util
import sqlite3
from contextlib import closing
from pathlib import Path

CASES = Path(__file__).resolve().parent
DATABASES = ["shop", "billing", "helpdesk", "warehouse"]


def build(name, out_dir=None):
    """One database, rebuilt from scratch. Returns its path."""
    path = Path(out_dir or CASES / name) / f"{name}.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    spec = importlib.util.spec_from_file_location(f"seed_{name}", CASES / name / "seed.py")
    seed = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(seed)
    with closing(sqlite3.connect(path)) as conn:
        conn.executescript((CASES / name / "schema.sql").read_text(encoding="utf-8"))
        for table, rows in seed.rows().items():
            if rows:
                conn.executemany(f"INSERT INTO {table} VALUES ({','.join('?' * len(rows[0]))})", rows)
        conn.commit()
    return path


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", help="folder for the .db files (default: each case's own folder)")
    args = ap.parse_args()
    for name in DATABASES:
        path = build(name, args.out)
        with closing(sqlite3.connect(path)) as conn:
            tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name")]
            counts = ", ".join(f"{t} {conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]}" for t in tables)
        print(f"{path}: {counts}")


if __name__ == "__main__":
    main()
