---
name: script-preflight
description: Before running any script that gathers data, queries a database, runs a backtest or runs a test suite, make one optimization pass, estimate its cost, choose a time budget and run it through run_bounded.py with database access through safe_db. Use whenever you are about to run python some_script.py, pytest, a notebook, sqlcmd, mysql, psql or aws redshift-data; when the runguard hook says a command was unwrapped, overran or imports a raw database driver; and when a run comes back SLOW or BUDGET EXCEEDED.
---

# Script preflight

A script that runs for an hour when it could run for two minutes wastes the
user's time, and against a database it can hold locks that other work queues
behind. This checklist runs before the script does. The runguard hook enforces
the last two steps; the first four are on you.

`<runguard>` below is the folder holding `run_bounded.py`, `ledger.py` and
`safe_db.py`. Find it from the hook's message or the user's settings.

## 1. Read the script for the usual causes

Check each, and fix what you find before the first run:

- one query per row inside a loop (fetch the set in one query, join in SQL)
- filtering or aggregating in pandas what SQL could filter or aggregate
- `SELECT *`, or columns the script never uses
- `OFFSET` pagination over a large table (use keyset pagination: `WHERE id > last ORDER BY id`)
- the same data pulled again on every run (cache it to parquet once, read the cache)
- a date window wider than the question needs
- the whole test suite when one module answers the question (`pytest -x -k <target>`)
- work done in series that is independent (a thread pool for I/O, not for CPU)

## 2. Estimate before the full run

- For each query, get the row count or `EXPLAIN` first.
- Run on a slice: one client, one week, `TOP 1000` / `LIMIT 1000`. Time it.
- Extrapolate: slice time multiplied by (full size / slice size). Say the
  estimate to the user in one line, with the numbers.

## 3. Choose a budget

The budget is about twice the estimate, rounded up, with these defaults when
there is nothing to estimate from: tests 5 minutes, data pulls 10 minutes,
backtests 30 minutes. The defaults live in `<runguard>/config.json`.

A budget over `max_budget_seconds` (30 minutes by default) needs the user's
approval before you pass `--approved`. Ask, with the estimate and what the
run is for.

## 4. Open database connections through safe_db

Never import `pyodbc`, `pymysql`, `psycopg2` or `redshift_connector` and
connect directly. Use `safe_db.connect_sqlserver`, `connect_mysql`,
`connect_postgres` or `redshift_data_query`, and `read_query` /
`read_in_chunks` for the reads. They refuse a host or login that does not
look read-only, set lock and statement timeouts, keep autocommit on so no
transaction stays open, and refuse anything but a read. Point at the
read-only replica where one exists.

## 5. Run it bounded

```
python <runguard>/run_bounded.py --budget 10m --label <short-name> -- <command>
```

Run long jobs in the background with the same wrapper. The budget is the
only thing that stops a background run.

## 6. Act on the result

- `runguard: ... took Ns, P% of its budget`: done.
- `SLOW`: the run used most of its budget. Before running it again, go back
  to step 1 and say what you changed.
- `BUDGET EXCEEDED` (exit 124): the process tree was killed. The hook will
  refuse to run the same file again until it changes. Find where the time
  went (the slice from step 2, a profile, or `EXPLAIN`), fix that, and run
  again. Do not just raise the budget. If the user decides the script should
  run as it is, they clear it themselves:
  `python <runguard>/ledger.py clear <script> --reason "..."`.

`python <runguard>/ledger.py report` lists every run that overran or ran
slow, worst first. Check it at the start of work on a project that runs
scripts often.
