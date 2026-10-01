# querygraph

A company's own queries in the graph, beside the documents and the code. For now this
folder holds the cases; the indexer that reads them comes next.

A question about a company's database often has a right answer that the schema does not
give. "Net revenue for August" depends on which month boundary finance uses, which
customers are not revenue, and when a euro becomes a pound. Those rules live in a query
someone already wrote: in the code, in a BI tool's saved question, in a runbook, in a
Slack reply. A model that writes its own SQL from the schema gets a plausible number,
and the number is wrong. A model handed the right existing query only has to adjust it:
bind the parameters, or move the dates written into it.

## The cases

`cases/questions.json` asks five questions of four databases. Each case records:
- where the indexed query lives and how it is held: a parameterized query in code, a
  Metabase template in a Notion page, or a query with last month's dates written in;
- how to adjust it for the question (`adjust`, `params`, `how`);
- a query written from the schema alone, which gives a wrong answer;
- the rules the indexed query holds, each with a `without` that takes that one rule out,
  and where else a model could find it (`visible`: the schema, the data, the question's
  words, or `convention`: a choice the company made that only its own sources settle);
- decoys: queries nearby that share its tables and words but answer another question.

| # | Database | Question | The indexed query | How it is held |
|---|---|---|---|---|
| 01 | shop | What was our net revenue for August 2026, in pounds? | `shop/repo/finance/revenue.py`, `NET_REVENUE_SQL` | code, parameterized: `:start`, `:end` from `month_bounds()` |
| 02 | billing | What was our MRR at the end of August 2026? | `billing/notes/metrics-handbook.md`, the MRR section | Notion page, Metabase template: `{{as_of}}`, optional `[[...]]` |
| 03 | billing | What was our logo churn rate for August 2026? | `billing/notes/slack-data-help-2026-08-04.md`, the reply | Slack thread, July's dates written in, below a wrong first attempt |
| 04 | helpdesk | What share of urgent tickets missed the one-hour first-reply target in August 2026, across both desks? | `helpdesk/notes/support-ops-runbook.md`, the monthly report | runbook, July and the Enterprise desk written in |
| 05 | warehouse | How many blue enamel mugs can we still promise from Leeds? | `warehouse/repo/inventory/atp.py`, `ATP_SQL` | code, parameterized: `:sku`, `:warehouse`, `:now`, and `:safety_cases` from a constant beside it |

Each database is built by its folder's `seed.py`: months of ordinary rows from a seeded
generator, then the rows each rule needs, each marked in the seed with the rule it is
there for. The builds are deterministic, so the answers hold.

## Run

    python querygraph/cases/build.py        the four databases, into each case folder (git ignores them)
    python querygraph/cases/check.py        each case: the indexed query, the schema-only one, each rule taken out
    python -m unittest tests.test_query_cases
    python bench/query_eval.py              live: a model with the database, with and without the indexed query

The tests check that the indexed query, adjusted as recorded, gives the answer; that a
plain-Python reading of the source's rules over the raw rows gives it too; that the
schema-only query does not; and that taking out any one rule changes the answer.

## What the live runs showed

With read-only access to the database and its schema, Sonnet answered 0 of 15 runs
right. With the source file that holds the indexed query added, it answered 15 of 15
(`bench/query-report.md`). The schema-only runs got the structural rules right: history
tables, minor units, as-of exchange rates, the bot's acknowledgement, merged tickets. They
went wrong on the company's conventions: the London month, staff and QA orders, a pause
counting as churn, the clock starting at escalation, budget exchange rates, and the stock
held back for wholesale. In four of the five cases, all three runs gave the same wrong
number.

A first version of cases 02 and 05 held only rules that are common practice, and Sonnet
answered both right from the schema alone. An indexed query is worth most for its
conventions, because a strong model derives the rest.

The whole write-up, with each case's source, adjustments, rules and runs, is
`docs/query-index-cases.html`.

## What the index has to hold

These cases are what indexing a query has to get right before it helps:

- **The query and where it lives**: file and constant, or page and section, or message.
  One Slack thread holds the wrong query and the right one; the reply that settles it is
  the one to index.
- **What it answers**, in the words people ask with ("net revenue", "the board pack
  number", "logo churn"), and what its neighbours answer instead (contracted ARR is not
  MRR; the sales dashboard is not revenue).
- **Its parameters, and how to fill them**: `:start` is a London month turned into UTC by
  `month_bounds()`; `{{as_of}}` is a quoted date and `[[...]]` is dropped when unused;
  `:safety_stock` comes from a constant beside the query.
- **The literals that are parameters in disguise**: July's dates, the Enterprise desk.
  Moving the dates has an order: the end of the month first, or both ends land on the
  same day.
- **The rules it holds**, in words, tied to their clauses, from the comments and the
  prose around it, so the model can answer a question the query was not written for.
  The conventions matter most.
- **Its standing**: approved, used for the board pack, superseding the first attempt. The
  model should adjust an approved query's parameters and leave its rules alone; one
  indexed run rewrote a boundary test it judged a bug.
- **The tables and columns it reads**, linked to the schema, so a question about those
  tables finds it.
