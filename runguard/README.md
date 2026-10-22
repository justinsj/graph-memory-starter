# runguard

Every script that gathers data or runs tests gets an optimization pass first,
a time budget while it runs, and database connections that cannot hold locks
for long. Four Python files, one hook, one skill. Standard library only;
`safe_db` loads a database driver only when you connect.

    run_bounded.py      runs a command inside a budget, kills the whole process
                        tree when it runs out, logs the run to ledger.jsonl
    preflight_gate.py   PreToolUse hook on Bash and PowerShell: data and test
                        commands must run through run_bounded, a script that
                        overran may not run again unchanged, and a script that
                        imports a database driver must import safe_db too
    ledger.py           report: the runs to revisit; clear: let one unchanged
                        script run once more (for the user, with a reason)
    safe_db.py          read-only connections for SQL Server, MySQL, Postgres
                        and Redshift, plus the Redshift Data API
    skill/              /script-preflight, copy into .claude/skills/
    config.json         mode, default budgets, the 30-minute approval line
    hooks.json          the hook, merge into .claude/settings.json

## Run

    python runguard/run_bounded.py --budget 10m --label pull-orders -- python scripts/pull_orders.py
    python runguard/run_bounded.py --budget 5m -- "pytest -x tests/test_rules.py | tail -20"
    python runguard/ledger.py report

One word after `--` runs through the shell, so pipes work. The exit code is
the command's own, or 124 when the budget ran out. Budgets over
`max_budget_seconds` need `--approved`, which the skill tells the model to
pass only after asking you.

## The two modes

    warn    the command runs, and the model is told what was wrong
    block   the command is denied, with the same text as the reason

It ships as `warn`. Run it that way for a week, read `ledger.py report --all`
to see what it flagged and whether the budgets fit, then set `"mode": "block"`
in `config.json`.

## Why a long read blocks a database

    SQL Server   a long read on a readable secondary holds a schema lock that
                 stalls redo of DDL, and grows the version store and replica lag
    MySQL        a SELECT takes no row locks but holds a metadata lock: an ALTER
                 waits on it, then every query on the table queues behind the ALTER
    Postgres,    a SELECT holds an AccessShareLock, which blocks materialized
    Redshift     view refreshes, TRUNCATE, VACUUM and DDL

So `safe_db` sets, per connection:

    SQL Server   ApplicationIntent=ReadOnly, autocommit, query timeout,
                 LOCK_TIMEOUT 5000, DEADLOCK_PRIORITY LOW; host must contain "readonly"
    MySQL        autocommit, TRANSACTION READ ONLY, MAX_EXECUTION_TIME,
                 lock_wait_timeout and innodb_lock_wait_timeout 5 s;
                 CURRENT_USER() must contain "read-only"
    Postgres     autocommit, read-only session, statement_timeout, lock_timeout,
                 idle_in_transaction_session_timeout
    Redshift     autocommit, statement_timeout; the Data API call is cancelled
                 at its deadline

`read_query` refuses anything but one read: no INSERT, UPDATE, DDL, SET,
`SELECT ... INTO`, `FOR UPDATE`, or a second statement. The markers are
arguments; pass `None` to skip a check you have no marker for.

## Limits

The hook reads the command text. A script started by another script, or a
`.bat` file that runs Python, gets past it, and so does a model that passes
`--approved` without asking. It is a guard against habits, not a sandbox. The
driver check is a grep for import lines, so a driver loaded through
`importlib` is not seen.

## Test

    python -m unittest discover -s tests -p test_runguard.py

Covers budgets, the tree kill (a child that starts a grandchild), the ledger,
each hook decision in both modes, the re-run block and its clear, the driver
check, every engine's guard statements against a fake connection, the read
check, and the Data API deadline.
