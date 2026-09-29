"""The service's own store: the log everything else is computed from.

One schema on SQLite or Postgres (SQLAlchemy Core). Every table but the
workspace and user tables carries a workspace_id. The service filters by it,
and on Postgres row-level security enforces it underneath: each transaction
says which workspace it is for (set_config('kl.workspace_id', ...)), and a
query that forgot to filter still sees only that workspace. A few system paths
(finding the key a request presents, delivering webhooks) run with
kl.system on.

What arrived (documents, their versions, extractions), what was decided
(change requests, approvals), and what was applied (project records and their
events, the change log) are kept here. The graph each workspace is answered
from is a projection of it (kl.projection), rebuilt anywhere from these rows.
"""
from contextlib import contextmanager

import sqlalchemy as sa

md = sa.MetaData()
S, T, J, I, B = sa.String, sa.Text, sa.JSON, sa.Integer, sa.Boolean
F = sa.Float


def _ws():
    return sa.Column("workspace_id", S(40), nullable=False, index=True)


workspaces = sa.Table(
    "workspaces", md,
    sa.Column("id", S(40), primary_key=True),
    sa.Column("slug", S(80), nullable=False, unique=True),
    sa.Column("name", T, nullable=False),
    sa.Column("settings", J, nullable=False),
    sa.Column("state_version", I, nullable=False, default=0),  # bumped by every change the graph shows
    sa.Column("cr_counter", I, nullable=False, default=0),
    sa.Column("created", S(32), nullable=False))

users = sa.Table(
    "users", md,
    sa.Column("id", S(40), primary_key=True),
    sa.Column("issuer", T, nullable=False, default=""),  # OIDC issuer and subject, or "" for key-only users
    sa.Column("subject", T, nullable=False, default=""),
    sa.Column("email", T, nullable=False),
    sa.Column("name", T, nullable=False),
    sa.Column("created", S(32), nullable=False),
    sa.UniqueConstraint("issuer", "subject", "email", name="users_identity"))

members = sa.Table(
    "members", md, _ws(),
    sa.Column("user_id", S(40), nullable=False),
    sa.Column("role", S(20), nullable=False),  # viewer | editor | approver | admin
    sa.Column("created", S(32), nullable=False),
    sa.PrimaryKeyConstraint("workspace_id", "user_id"))

service_accounts = sa.Table(
    "service_accounts", md,
    sa.Column("id", S(40), primary_key=True), _ws(),
    sa.Column("name", T, nullable=False),
    sa.Column("created", S(32), nullable=False))

api_keys = sa.Table(
    "api_keys", md,
    sa.Column("id", S(40), primary_key=True), _ws(),
    sa.Column("principal_kind", S(20), nullable=False),  # user | service
    sa.Column("principal_id", S(40), nullable=False),
    sa.Column("name", T, nullable=False),
    sa.Column("hash", S(64), nullable=False, unique=True),
    sa.Column("scopes", J, nullable=False),
    sa.Column("created", S(32), nullable=False),
    sa.Column("revoked_at", S(32)))

documents = sa.Table(
    "documents", md,
    sa.Column("id", S(40), primary_key=True), _ws(),
    sa.Column("external_id", T),
    sa.Column("collection", T, nullable=False, default=""),
    sa.Column("name", T, nullable=False),
    sa.Column("path", T, nullable=False),  # where it sits in the graph's snapshot: what quotes cite
    sa.Column("kind", S(20), nullable=False),  # document | transcript | request | code | openspec
    sa.Column("uri", T),
    sa.Column("current_version_id", S(40)),
    sa.Column("created", S(32), nullable=False),
    sa.Column("deleted_at", S(32)))

source_versions = sa.Table(
    "source_versions", md,
    sa.Column("id", S(40), primary_key=True), _ws(),
    sa.Column("document_id", S(40), nullable=False, index=True),
    sa.Column("seq", I, nullable=False),
    sa.Column("sha256_bytes", S(64), nullable=False, index=True),
    sa.Column("sha256_text", S(64), nullable=False, index=True),
    sa.Column("minhash", J),
    sa.Column("blob_key", T, nullable=False),
    sa.Column("size", I, nullable=False),
    sa.Column("mime", T, nullable=False, default="text/plain"),
    sa.Column("status", S(24), nullable=False),  # active | held | duplicate | superseded | retracted | failed | awaiting_extraction
    sa.Column("dedup", S(24), nullable=False),  # new | new_version | duplicate | near_duplicate | unchanged
    sa.Column("duplicate_of", S(40)),
    sa.Column("similarity", F),
    sa.Column("problems", J, nullable=False),
    sa.Column("extraction", J),  # the checked extraction the graph is built from
    sa.Column("extraction_at", S(32)),
    sa.Column("created", S(32), nullable=False))

source_locations = sa.Table(
    "source_locations", md,
    sa.Column("id", S(40), primary_key=True), _ws(),
    sa.Column("version_id", S(40), nullable=False, index=True),
    sa.Column("uri", T), sa.Column("external_id", T), sa.Column("name", T),
    sa.Column("created", S(32), nullable=False))

jobs = sa.Table(
    "jobs", md,
    sa.Column("id", S(40), primary_key=True), _ws(),
    sa.Column("kind", S(24), nullable=False),
    sa.Column("status", S(20), nullable=False),  # queued | running | done | failed | waiting
    sa.Column("stage", S(40), nullable=False),
    sa.Column("subject", J, nullable=False),
    sa.Column("result", J, nullable=False),
    sa.Column("problems", J, nullable=False),
    sa.Column("created", S(32), nullable=False),
    sa.Column("updated", S(32), nullable=False))

change_requests = sa.Table(
    "change_requests", md,
    sa.Column("id", S(40), primary_key=True), _ws(),
    sa.Column("number", I, nullable=False),
    sa.Column("title", T, nullable=False),
    sa.Column("ops", J, nullable=False),
    sa.Column("reason", T, nullable=False, default=""),
    sa.Column("input_version_id", S(40)),  # a transcript's changes quote it; an API edit's quote its request text
    sa.Column("proposer_kind", S(20), nullable=False),  # user | service | run | job | system
    sa.Column("proposer_id", S(40), nullable=False),
    sa.Column("proposer_name", T, nullable=False),
    sa.Column("run_id", S(40)),
    sa.Column("state", S(20), nullable=False),  # open | applied | rejected | stale | failed
    sa.Column("problems", J, nullable=False),
    sa.Column("notes", J, nullable=False),
    sa.Column("diff", J, nullable=False),
    sa.Column("targets", J, nullable=False),  # what it touches: [project ids], [plan ids], [versions]
    sa.Column("base", J, nullable=False),  # their versions when it was opened
    sa.Column("created", S(32), nullable=False),
    sa.Column("updated", S(32), nullable=False))

approvals = sa.Table(
    "approvals", md,
    sa.Column("id", S(40), primary_key=True), _ws(),
    sa.Column("cr_id", S(40), nullable=False, index=True),
    sa.Column("user_id", S(40), nullable=False),
    sa.Column("decision", S(20), nullable=False),  # approve | reject
    sa.Column("ops", J, nullable=False),  # the indexes approved
    sa.Column("edits", J, nullable=False),
    sa.Column("note", T, nullable=False, default=""),
    sa.Column("at", S(32), nullable=False))

project_records = sa.Table(
    "project_records", md, _ws(),
    sa.Column("project_id", S(80), nullable=False),
    sa.Column("version", I, nullable=False),
    sa.Column("record", J, nullable=False),
    sa.Column("updated", S(32), nullable=False),
    sa.PrimaryKeyConstraint("workspace_id", "project_id"))

project_events = sa.Table(
    "project_events", md,
    sa.Column("id", I, primary_key=True, autoincrement=True), _ws(),
    sa.Column("project_id", S(80), nullable=False, index=True),
    sa.Column("event", J, nullable=False),
    sa.Column("cr_id", S(40)),
    sa.Column("actor", T, nullable=False),
    sa.Column("at", S(32), nullable=False))

change_log = sa.Table(
    "change_log", md,
    sa.Column("seq", I, primary_key=True, autoincrement=True), _ws(),
    sa.Column("cr_id", S(40)),
    sa.Column("kind", S(40), nullable=False),
    sa.Column("data", J, nullable=False),
    sa.Column("actor", T, nullable=False),
    sa.Column("at", S(32), nullable=False))

plans = sa.Table(
    "plans", md,
    sa.Column("id", S(40), primary_key=True), _ws(),
    sa.Column("project_id", S(80), nullable=False),
    sa.Column("deliverable_key", S(40), nullable=False),
    sa.Column("version", I, nullable=False),
    sa.Column("kind", S(20), nullable=False),  # general | openspec
    sa.Column("state", S(20), nullable=False),  # in_review | approved | rejected | superseded
    sa.Column("title", T, nullable=False),
    sa.Column("summary", T, nullable=False, default=""),
    sa.Column("design", T, nullable=False, default=""),
    sa.Column("checks", J, nullable=False),  # the deliverable's acceptance checks
    sa.Column("openspec", J),  # the change folder it came from
    sa.Column("created", S(32), nullable=False),
    sa.Column("created_by", T, nullable=False),
    sa.Column("approved_by", S(40)),
    sa.Column("approved_at", S(32)))

tasks = sa.Table(
    "tasks", md,
    sa.Column("id", S(40), primary_key=True), _ws(),
    sa.Column("plan_id", S(40), nullable=False, index=True),
    sa.Column("key", S(40), nullable=False),
    sa.Column("n", I, nullable=False),
    sa.Column("title", T, nullable=False),
    sa.Column("instructions", T, nullable=False, default=""),
    sa.Column("after", J, nullable=False),  # keys
    sa.Column("needs", J, nullable=False),
    sa.Column("checks", J, nullable=False),
    sa.Column("gate", B, nullable=False, default=False),
    sa.Column("outputs", J, nullable=False),
    sa.Column("retries", I, nullable=False, default=2),
    sa.Column("digest", S(64), nullable=False))  # its definition, to tell a changed task from the same one

executions = sa.Table(
    "executions", md,
    sa.Column("id", S(40), primary_key=True), _ws(),
    sa.Column("plan_id", S(40), nullable=False),
    sa.Column("state", S(20), nullable=False),  # running | done | failed | cancelled
    sa.Column("created", S(32), nullable=False),
    sa.Column("created_by", T, nullable=False),
    sa.Column("finished", S(32)))

execution_tasks = sa.Table(
    "execution_tasks", md, _ws(),
    sa.Column("execution_id", S(40), nullable=False),
    sa.Column("task_key", S(40), nullable=False),
    sa.Column("state", S(20), nullable=False),  # waiting | ready | leased | running | awaiting_review | done | failed
    sa.Column("attempts", I, nullable=False, default=0),
    sa.Column("outputs", J, nullable=False),
    sa.Column("updated", S(32), nullable=False),
    sa.PrimaryKeyConstraint("execution_id", "task_key"))

runs = sa.Table(
    "runs", md,
    sa.Column("id", S(40), primary_key=True), _ws(),
    sa.Column("execution_id", S(40), nullable=False, index=True),
    sa.Column("task_key", S(40), nullable=False),
    sa.Column("kind", S(20), nullable=False),  # agent | script | person: one table for every kind of run
    sa.Column("runner", J, nullable=False),
    sa.Column("state", S(20), nullable=False),  # leased | provisioning | running | waiting | succeeded | failed | lost | cancelled
    sa.Column("token_hash", S(64), nullable=False, unique=True),
    sa.Column("lease_expires", F, nullable=False),  # epoch seconds: the token lives exactly as long
    sa.Column("created", S(32), nullable=False),
    sa.Column("started", S(32)),
    sa.Column("ended", S(32)),
    sa.Column("outcome", J, nullable=False),
    sa.Column("idempotency_key", T))

run_events = sa.Table(
    "run_events", md,
    sa.Column("id", I, primary_key=True, autoincrement=True), _ws(),
    sa.Column("run_id", S(40), nullable=False, index=True),
    sa.Column("type", S(24), nullable=False),
    sa.Column("data", J, nullable=False),
    sa.Column("at", S(32), nullable=False))

artifacts = sa.Table(
    "artifacts", md,
    sa.Column("id", S(40), primary_key=True), _ws(),
    sa.Column("run_id", S(40), nullable=False, index=True),
    sa.Column("kind", S(24), nullable=False),  # file | pull_request | test_report | text | link
    sa.Column("name", T, nullable=False),
    sa.Column("blob_key", T), sa.Column("uri", T),
    sa.Column("size", I, nullable=False, default=0),
    sa.Column("meta", J, nullable=False),
    sa.Column("created", S(32), nullable=False))

questions = sa.Table(
    "questions", md,
    sa.Column("id", S(40), primary_key=True), _ws(),
    sa.Column("run_id", S(40), nullable=False, index=True),
    sa.Column("text", T, nullable=False),
    sa.Column("answer", T),
    sa.Column("answered_by", S(40)),
    sa.Column("created", S(32), nullable=False),
    sa.Column("answered", S(32)))

outbox = sa.Table(
    "outbox", md,
    sa.Column("seq", I, primary_key=True, autoincrement=True), _ws(),
    sa.Column("type", S(40), nullable=False),
    sa.Column("data", J, nullable=False),
    sa.Column("created", S(32), nullable=False))

webhooks = sa.Table(
    "webhooks", md,
    sa.Column("id", S(40), primary_key=True), _ws(),
    sa.Column("url", T, nullable=False),
    sa.Column("secret", T, nullable=False),
    sa.Column("types", J, nullable=False),
    sa.Column("after_seq", I, nullable=False, default=0),  # delivered up to here
    sa.Column("failures", I, nullable=False, default=0),
    sa.Column("last_error", T),
    sa.Column("active", B, nullable=False, default=True),
    sa.Column("created", S(32), nullable=False))

sessions = sa.Table(
    "sessions", md,
    sa.Column("id", S(120), nullable=False), _ws(),
    sa.Column("sent", J, nullable=False),
    sa.Column("updated", S(32), nullable=False),
    sa.PrimaryKeyConstraint("workspace_id", "id"))

GLOBAL = {"workspaces", "users"}  # the only tables without a workspace_id


class Database:
    """An engine, and transactions that know their workspace."""

    def __init__(self, url: str):
        self.url = url
        self.postgres = url.startswith("postgresql")
        if self.postgres:
            self.engine = sa.create_engine(url, pool_pre_ping=True, future=True)
        else:
            self.engine = sa.create_engine(url, future=True, connect_args={"check_same_thread": False, "timeout": 30})

            @sa.event.listens_for(self.engine, "connect")
            def _pragmas(conn, _):
                cur = conn.cursor()
                cur.execute("PRAGMA journal_mode=WAL")  # readers never wait for the writer
                cur.execute("PRAGMA busy_timeout=30000")
                cur.close()

    def create(self, app_role: str = None) -> None:
        """Create the tables; on Postgres also the row-level security policies, and grants for app_role."""
        md.create_all(self.engine)
        if not self.postgres:
            return
        with self.engine.begin() as c:
            for t in md.sorted_tables:
                if t.name in GLOBAL:
                    continue
                c.execute(sa.text(f'ALTER TABLE "{t.name}" ENABLE ROW LEVEL SECURITY'))
                c.execute(sa.text(f'ALTER TABLE "{t.name}" FORCE ROW LEVEL SECURITY'))
                c.execute(sa.text(f'DROP POLICY IF EXISTS workspace_isolation ON "{t.name}"'))
                c.execute(sa.text(
                    f'CREATE POLICY workspace_isolation ON "{t.name}" '
                    "USING (workspace_id = current_setting('kl.workspace_id', true) "
                    "OR current_setting('kl.system', true) = 'on') "
                    "WITH CHECK (workspace_id = current_setting('kl.workspace_id', true) "
                    "OR current_setting('kl.system', true) = 'on')"))
            if app_role:
                c.execute(sa.text(f'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO "{app_role}"'))
                c.execute(sa.text(f'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO "{app_role}"'))

    @contextmanager
    def tx(self, workspace_id: str = None, system: bool = False):
        """One transaction, for one workspace (or the system paths). Commits on success."""
        with self.engine.begin() as c:
            if self.postgres:
                c.execute(sa.text("SELECT set_config('kl.workspace_id', :w, true), set_config('kl.system', :s, true)"),
                          {"w": workspace_id or "", "s": "on" if system else "off"})
            yield c

    def dispose(self):
        self.engine.dispose()
