# codegraph

A codebase in the graph, beside the documents and the projects. `index.py`
reads the code with no model and no network, and writes what it finds in the
graph's own format. The build loads it like extraction files and checks every
quoted line against its file, and the recall hook answers code questions from
it before the model starts.

    python codegraph/index.py path/to/repo           what it finds
    python src/build_graph.py --code path/to/repo    into graph.db, with the documents

## What it records

| Entity | What it is | Its links |
|---|---|---|
| FUNCTION, COMPONENT | a top-level function; a component is a PascalCase one in a .tsx or .jsx file | calls, reads, requests; references a function it passes without calling (a callback); looks_up a lookup table it runs one entry of |
| TEST | a function named `test…` in a test file (`test_*.py`, `*.test.ts`, `*.spec.ts`) | as a function |
| VARIABLE | a module-level constant, with its value (template strings worked out) | reads the constants it is built from; references the functions it holds |
| MODULE | a file, by its path | imports each symbol it imports, followed through re-exports to where it is defined |
| ROUTE | `METHOD /path` | handled_by the function behind it |
| ROUTE_CASE | `METHOD /path when <body key> = <value>` | part_of its route, handled_by the handler, dispatches_to what that branch runs |
| UI_ACTION | a button | triggers what its onClick runs, part_of its component |

Each entity has claims that quote its own line: the `def` or `function` line,
the docstring, the constant's assignment, the route decorator, the `if` that
picks a branch, the `fetch` call, the button. `code_symbols` keeps each one's
file, line and value.

`call_sites` keeps the line where each link happens: each call with its
arguments, each import, reference, request and dispatch, and each field a
handler reads from the request body. A request's row lists the body fields the
client sends, when the body is written out. The build refuses a site whose line
is not in its file. When a file changes after indexing, the hook marks the line
as changed, as it does for documents.

## What it works out

- **Routes across languages.** The client's URL is resolved through constants
  and template strings, even across files: `REFUNDS_URL = \`${API_BASE}/refunds\``
  with `API_BASE = "/api"` in another file gives `POST /api/refunds`. Path
  parameters match whatever their syntax: `/api/orders/${orderId}` is
  `/api/orders/<order_id>`. A URL nothing in the codebase serves becomes a
  route that says so.
- **A branch picked by a value in the body.** When a handler tests the request
  body (`if action == "cancel":`, with `action = payload["action"]`), each
  branch is its own ROUTE_CASE. The calls inside it belong to the case, not to
  the handler. When a client passes a literal body (`postAction({ action:
  "cancel" })`, even through a wrapper that does the `fetch`), it requests that
  case. So the cancel button reaches `cancel_order`, never the refund branch
  behind the same URL.
- **A branch picked from a lookup table.** `BULK_ACTIONS[payload["action"]]`,
  with `BULK_ACTIONS = {"cancel": cancel_order, "hold": hold_order}`, gives one
  case per key. `bulkCancel`, which sends `action: "cancel"` in the `fetch`
  itself, reaches `cancel_order` and not `hold_order`.
- **Uses that are not calls.** A function passed without being called
  (`filter(needs_approval, refunds)`) is referenced. One held in a table is
  referenced by the table. An import is a link from the file, even when the
  file calls nothing. Tests are their own kind, left out of answers unless the
  question is about tests, and always among a function's dependents.
- **Re-exports.** `from refunds import needs_approval`, where
  `refunds/__init__.py` imports it from `.rules`, is followed to
  `refunds.rules.needs_approval`, up to five packages deep.
- **Which of two same-named functions.** Calls are resolved through imports, so
  `create_refund` calls `refunds.rules.validate`, not `orders.service.validate`.
- **Buttons own their onClick.** A component's calls leave out what its buttons
  do; each button triggers its own.

Names are qualified by the codebase's top folder and the module
(`backend.refunds.rules.needs_approval`, `frontend.api.submitRefund`); the bare
name is an alias.

## Names in any style

`src/tokens.py` splits names and questions alike, so these all name one
symbol:
- `needs_approval`
- `needsApproval`
- `NeedsApproval`
- `NEEDS_APPROVAL`
- `needs-approval`
- "needs approval"

How it splits:
- a run of capitals is one word (`parseHTTPResponse` → parse http response);
- digits stay with the letters before them (`sha256Hash`);
- any alphabet works (`créerRemboursement`);
- prose splits exactly as before.

Any two words in a row name code as well: "approval threshold" finds
`APPROVAL_THRESHOLD_GBP`. When words name a symbol, the shorter words inside
them name nothing else, so `legacy_refund` is the function, not also the refund
policy.

## What the hook adds

For code the question names, a `code:` block follows the facts. It holds both
directions, whatever the wording: "add an argument to", "rename", "what calls"
and "what does it call" all get the same lines. The wording only decides which
comes first.

- **What depends on it:** callers, references, importing files, tests, the
  routes and branches that run it, and the clients and buttons behind them.
  Grouped by link, so thirty callers are one line.
- **Where each use is:** each direct dependent's line, with its arguments:
  `backend/refunds/views.py:14, backend.refunds.views.create_refund calls it:
  if needs_approval(refund["amount"]):`.
- **For a handler, the request:** each client's line that builds the body, with
  the fields it sends, and each field the handler reads.
- **What it depends on:** what it calls and reads, the routes and branches it
  reaches, the functions behind them, and the constants they read, with values.
- **Neither:** a symbol nothing reaches is said to be unreached.

Both traces follow links to the end, up to 8: a button to the constant its
refund compares against is five. When two named symbols share links, each link
is listed once, and the second symbol's heading says where the rest are. No
dependent is ever left out for space. Past 6,000 characters, the call-site
lines go first, and a note says how many went.

A handler that looks up a table depends on the table. Its forward trace does
not run every entry, since one request runs only one.

## The cases

`cases/shop/` is a small shop: a Flask-style Python API and a TypeScript
frontend. `cases/questions.json` asks it sixteen questions. Each question lists
what the injection must say, what it must not say, and the words a right answer
contains. For the change requests (05 and 12 to 15, marked *), the whole reply
is graded: it must name every call site or file that has to change, by its
function, its call, its line, or the file that holds it.

| # | Kind | Question |
|---|---|---|
| 01 | reference chain to a variable | How does create_refund decide whether a refund needs approval, and what value does it compare against? |
| 02 | explicit API route | Which backend function serves the order page's request for an order? |
| 03 | API route in a variable | What runs on the server when someone clicks 'Request refund'? |
| 04 | conditional API route (a value in the body) | Which server function runs when the user clicks 'Cancel order'? |
| 05* | impact of a change | If I change needs_approval, what else is affected? |
| 06 | dead code | Is legacy_refund still used anywhere? |
| 07 | two functions, one name | Which validate function does create_refund call? |
| 08 | code against a document | Does the refund approval threshold in the code match the refund policy? |
| 09 | two layers that disagree | Do the frontend and the backend agree on the approval threshold? |
| 10 | one name in any style | Where is refundsUrl defined, and what URL does it hold? |
| 11 | a document question stays one | Who approves a £300 refund? |
| 12* | a change to a function's arguments | Add a required currency argument to needs_approval. What else has to change? |
| 13* | a rename | Rename needs_approval to requires_approval. Which files have to change? |
| 14* | a change to what a handler reads | Make create_refund require a reason in the request body. Where does the frontend have to change? |
| 15* | a change inside a function | Change process_refund so staff refunds skip the approval check. |
| 16 | a route picked from a lookup table | Which server function runs when bulkCancel is called? |

The cases list lines by hand. `tests/test_code.py` also checks completeness
without them:
- It works out every symbol's dependents and dependencies from the index's own
  links, with no depth limit.
- It asks a change request about each of the shop's 35 functions, tests,
  constants and routes.
- It requires every name, every direct use's line and, for a handler, every
  request line.
- It asks nine wordings for `needs_approval`, in every naming style, and each
  must bring both directions.
- It builds a function with 30 callers in three files, and requires all 30 and
  every call line.
- It shrinks the budget, and requires every dependent still named and the note
  to count what went.
- It changes a caller's line after indexing, and requires the mark.

    python -m unittest tests.test_code          # no model: tokens, the index, every case, dependents, freshness
    python bench/code_eval.py                    # live: the model searching the code against the graph
    python bench/code_eval.py --plain --reps 1   # the same, not told where the code is
    python bench/code_eval.py --cases 12,13      # some of the cases

## What it does not read yet

- **Python:** module-level functions and constants. Methods inside classes and
  nested functions are counted as part of the function around them.
- **Routes:** Flask-style decorators only (`@app.get`, `@app.post`,
  `@app.route(..., methods=[...])`).
- **Branches:** `if`/`elif` on a body value, and a module-level dict of
  functions indexed by one. `match` is not read yet.
- **Request fields:** only those the handler reads itself. When it passes the
  body on (`validate(refund)`), what `validate` reads is not counted as a read
  of the request.
- **Other indirect calls:** a function reached through `getattr`, a registry
  filled at run time, or an attribute set elsewhere is not linked. It is
  referenced only where its name appears. `from x import *` is not followed.
- **HTTP calls:** `fetch()` only. axios and other clients are not read yet.
- **TypeScript:** named imports only, and re-exports (`export { x } from`) are
  not followed. A JSX text containing an apostrophe can confuse the scanner.
- **Scope:** one codebase at a time, alongside the documents.
