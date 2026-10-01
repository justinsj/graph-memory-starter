# Evidence cases, live (01 October 2026)

Made by `python bench/evidence_eval.py` (model sonnet). Stage 1 gathers the evidence and archives it as an OpenSpec change; stage 2 answers later questions from a store, without the database.

## Stage 1: gathering

| Run | Archived | Numbers right | Slips | Sets | Notes | Keywords | Tool calls | Time | Cost |
|---|---|---|---|---|---|---|---|---|---|
| 1 | yes | 44 of 44 | none | 5 | 19 | 39 | 27 | 107.1 s | $0.33 |
| 2 | yes | 44 of 44 | none | 5 | 17 | 39 | 21 | 121.7 s | $0.37 |

- run 1 wrong or missing: none
- run 2 wrong or missing: none

## Stage 2: answering from the store

| Condition | Right | headline | caveat | derived | period | by-number | out-of-scope | Median context | Cost |
|---|---|---|---|---|---|---|---|---|---|
| whole-gold | **20 of 20** | 4/4 | 6/6 | 3/3 | 3/3 | 2/2 | 2/2 | 14,786 chars | $0.60 |
| whole-bare | **16 of 20** | 3/4 | 3/6 | 3/3 | 3/3 | 2/2 | 2/2 | 5,003 chars | $0.27 |
| recall-gold | **13 of 20** | 2/4 | 4/6 | 2/3 | 1/3 | 2/2 | 2/2 | 2,378 chars | $0.16 |
| recall-bare | **7 of 20** | 2/4 | 0/6 | 0/3 | 1/3 | 2/2 | 2/2 | 1,276 chars | $0.11 |
| whole-own-1 | **20 of 20** | 4/4 | 6/6 | 3/3 | 3/3 | 2/2 | 2/2 | 17,684 chars | $0.73 |
| recall-own-1 | **13 of 20** | 2/4 | 4/6 | 2/3 | 1/3 | 2/2 | 2/2 | 2,368 chars | $0.17 |
| whole-own-2 | **19 of 20** | 4/4 | 5/6 | 3/3 | 3/3 | 2/2 | 2/2 | 16,316 chars | $0.68 |
| recall-own-2 | **13 of 20** | 2/4 | 4/6 | 2/3 | 2/3 | 1/2 | 2/2 | 2,423 chars | $0.16 |
| db | **8 of 15** | 1/4 | 4/4 | 1/3 | 1/3 |  | 1/1 | 0 chars | $0.45 |

| Question | Answer | whole-gold | whole-bare | recall-gold | recall-bare | whole-own-1 | recall-own-1 | whole-own-2 | recall-own-2 | db |
|---|---|---|---|---|---|---|---|---|---|---|
| q01-sales | 178905.3 | ok | ok | ok | ok | ok | ok | ok | ok | **181060.3** |
| q02-best-day | 2026-08-14 | ok | ok | **None** | **None** | ok | **None** | ok | **None** | ok |
| q03-one-line-share | 23.6 | ok | ok | **None** | **None** | ok | **None** | ok | **None** | **24.05** |
| q04-orders-a-day | 38.0 | ok | **33.8** | ok | ok | ok | ok | ok | ok | **34.8** |
| q05-best-retail-day | 2026-08-29 | ok | ok | **None** | **None** | ok | **None** | ok | ok | ok |
| q06-single-line-a-day | 9.0 | ok | ok | ok | **None** | ok | ok | ok | ok | ok |
| q07-bundle-uplift | 72.3 | ok | ok | ok | **None** | ok | ok | ok | ok | **65.07** |
| q08-orders-over-50 | 56.2 | ok | ok | **None** | **None** | ok | **None** | ok | **None** | **53.48** |
| q09-daily-growth | 536.29 | ok | ok | ok | ok | ok | ok | ok | ok | **534.95** |
| q10-units-from-header | no | ok | ok | ok | **None** | ok | ok | ok | ok | ok |
| q11-who-amends | the phone desk | ok | **None** | ok | **None** | ok | ok | **Amended orders: the 23 orders in order_amendments (July and August 2026) whose lines were amended without the header being updated** | **Order amendments (amended order lines where the header was not updated)** | ok |
| q12-staff-in-sales | no | ok | **None** | **None** | **None** | ok | **None** | ok | **None** |  |
| q13-day-boundary | London | ok | ok | ok | **None** | ok | ok | ok | ok |  |
| q14-best-day-order | trade | ok | **None** | ok | **None** | ok | ok | ok | ok | ok |
| q15-what-is-23-6 | orders with one order line | ok | ok | ok | ok | ok | ok | ok | **None** |  |
| q16-what-is-717-50 | sales the order headers leave out | ok | ok | ok | ok | ok | ok | ok | ok |  |
| q17-h1-one-line | 23.8 | ok | ok | **None** | **None** | ok | **None** | ok | **None** | **24.2** |
| q18-h1-headers | yes | ok | ok | **None** | **None** | ok | **no** | ok | ok | ok |
| q19-september | null | ok | ok | ok | ok | ok | ok | ok | ok |  |
| q20-margin | null | ok | ok | ok | ok | ok | ok | ok | ok | ok |

Total cost $4.06.
