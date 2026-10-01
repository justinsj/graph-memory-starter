# evidence

Findings from a company's database, stored for later: the numbers a thesis rests on, and the evidence
behind a claim about the data. This folder holds a test set for the knowledge layer's part in that. Its
cases measure what to store with each finding, how to index it, and what a later reader gets back.

A thesis says "if we offer a bundle at checkout, sales rise by potentially Z", and Z is the product of
numbers such as orders a day, the share of orders with one line, and what an order line is worth. An
analyst gets those from the database once: aggregate the daily sales, group and order the days by
amount, test that each sale has more than one order item, test that an order's quantity is always the
total of its lines. Then the numbers are needed again, by people planning and by the thesis research,
without the database, and they are only as good as what was stored with them. A count of mismatched
order headers is little use without the note that says the phone desk causes them, and that order_items
is the table to use instead.

## The cases

- `cases/sales/`: Kettle & Kiln's sales ledger, January to mid-September 2026: web, till and phone
  orders, their lines, and the amendments the phone desk makes. `seed.py` is deterministic, and each row
  that matters is marked with the finding it is there for: orders just after midnight (a London day is not
  a UTC day), staff purchases and till training (not sales), one trade order that makes the best day,
  single-line orders mostly at the till, cancelled orders with no lines, and 23 orders amended after
  checkout from 10 July whose header totals were never updated.
- `cases/evidence.json`: the brief an analyst is given (the thesis, the period, the definitions, and the
  numbers to establish, by key), and two archives of evidence: the first half of 2026, archived on 1 July,
  and July and August, archived on 15 September, which supersedes it. Each set has a claim, a verdict, and
  numbers, each with the SQL that gives it and the slips that give another value (UTC days, the order
  headers instead of the lines, staff left in).
- `cases/questions.json`: 20 questions asked after the archive, each worked out from the numbers it
  names. Six kinds: headline (a stated number), derived (arithmetic on stated numbers), caveat (needs what
  a note says), by-number (quotes a figure and asks what it is), period (the older archive, or both), and
  out-of-scope (nothing answers it, so the answer is to say so).
- `openspec/`: an OpenSpec root with an `evidence` schema (proposal → evidence → tasks) and the two
  archived changes as a careful analyst would write them: numbers, keywords, the query, and notes. The
  schema's instruction for `evidence.md` is the storage policy under test. It leaves the notes to the
  analyst's judgement.
- `evidence_index.py`: archived evidence into graph facts, no model needed. Each set is an EVIDENCE entity
  aliased by its keywords. Each number is a claim with its figure and unit. Each note is a claim quoting
  itself. A later archive repeating a set's id ends the earlier claims on its date. Two layouts: `set`
  (all claims on the set's entity) and `number` (each number its own FINDING entity, aliased by its key,
  its label and its figure, so a question naming or quoting it starts there).
- `score.py`: the knowledge layer holding a store, scored with no model. The thesis numbers are looked up
  as the service's research looks them up. Each question's recall is checked for the numbers and caveat
  its answer needs.

## Run

    python evidence/cases/build.py            the database, into evidence/cases/sales/ (git ignores it)
    python evidence/cases/check.py            every number and answer against a fresh build
    python evidence/evidence_index.py         the archives' facts; --number for the number layout
    python evidence/score.py                  gold and bare stores, both layouts, in the knowledge layer
    python -m unittest tests.test_evidence_cases
    python bench/evidence_eval.py             live: gather and archive, then answer from each store

The tests check that every recorded number is what its SQL gives. The headline numbers also come out of
a plain-Python reading of the raw rows. Every slip gives another value. The gold archives state every
number as recorded, and the figures in their notes are the data's. Both archives index into facts the
graph accepts, the first half's sets ending when the later change repeats them. The knowledge layer
finds this period's numbers, not the superseded ones, for the thesis and for an undated question.

The write-up, with the scorecard and the live runs, is `docs/evidence-findings-cases.html`.
