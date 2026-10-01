# kl: the knowledge layer service

The graph as a hosted service, shared by teams in separate workspaces. It is
built for three kinds of client:
- **Input handlers** send any set of files. The service deduplicates them,
  extracts facts, and checks each quote against its file.
- **A task app** reads projects and proposes edits. A person approves every
  edit through a change request.
- **An execution platform** runs approved plans on its own machines. Any agent
  on any machine works through one run protocol, over REST or MCP.

    pip install -r requirements-service.txt
    python -m kl init --workspace acme --name "Acme Ltd" --admin-email you@acme.example --admin-name You
    python -m kl serve --port 8080          # REST at /v1, OpenAPI at /openapi.json, MCP at /mcp

- Client guide, with real requests and answers: `docs/api-guide.html`
- Every call: `docs/api-reference.html`
- The contract, machine-readable: `docs/openapi.json`

## How it is built

| Module | What it does |
|---|---|
| `db.py` | The log: SQLAlchemy Core on SQLite or Postgres. Every row carries its workspace; on Postgres, row-level security enforces that underneath the code. |
| `projection.py` | Each workspace's graph, a projection of the log. A snapshot folder rewritten only where files changed, compiled by `src/build_graph.py` into a versioned `graph-N.db`. Any node can rebuild it. |
| `sources.py` | Files in: content-addressed storage, deduplication (bytes, text, versions, MinHash near copies), routing by kind, extraction checked against the text, trial checks before anything becomes current. |
| `review.py` | Change requests. Every edit goes through `projects/model.py`'s `validate` and `apply`. Approval can be whole, per operation, or edited, and people only. A request made stale by another approval is caught. |
| `projects.py` | Projects: approved reads, and writes that open change requests. |
| `impact.py` | Each project's thesis ("if X, Y will fall by potentially Z"), where Z is the product of numbers found in the graph's documents, or asked of a person the graph knows (event `number.asked`) and then answered or estimated. It also holds the estimated effort, and the priorities: projected impact per person-day, within each unit, or in money with `settings.unit_values`. The maths is `projects/impact.py`. |
| `plans.py` | Plans per deliverable, as task graphs. OpenSpec change folders become plans. Approval mirrors the tasks into the record's steps. A new version holds the tasks it changes, and running executions move onto it when it is approved. |
| `runs.py` | The run protocol: leases, run tokens (expiry on the server, moving with the lease), briefs, artifacts, questions, proposals, idempotent completion, checks and people's gates, lost leases, acceptance. |
| `context.py` | Context (recall, with content ids and sessions), search, entities, claims, code impact with the requirements at stake. |
| `events.py` | The outbox: a cursor feed with long poll, server-sent events, signed webhooks retried in order. |
| `core.py` | Principals: people (OIDC or personal keys), service accounts, runs, root. Roles, scopes, workspaces, keys. |
| `openspec.py` | OpenSpec in code: specs dated by their archived changes, change folders to plans, tests linked to the scenarios they name. |
| `api.py`, `mcp_server.py` | The two doors: REST (FastAPI) and MCP (streamable HTTP), over the same `Service`. |
| `client.py`, `orchestrator.py`, `worker.py` | A Python SDK, a reference orchestrator (machines are local processes), and an example agent (scripted, or Claude over MCP). |

## Postgres

Create the schema as the database owner, then run the service as a role that is
not a superuser, so row-level security binds it:

    CREATE ROLE kl_app LOGIN PASSWORD '...';
    python -c "from kl.service import Service; from kl.config import from_env; \
               Service(from_env(database_url='postgresql+psycopg://owner@db/kl'), app_role='kl_app')"
    KL_DATABASE_URL=postgresql+psycopg://kl_app:...@db/kl python -m kl serve

## Tests

    python tests/run_parallel.py kl     # the service's suites, in parallel
    python tests/run_parallel.py        # everything: 305 tests, about 40 s on 8 cores

The Postgres suite starts an embedded PostgreSQL 16 (`pgserver`, in
`requirements-dev.txt`).
