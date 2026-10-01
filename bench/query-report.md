# Query cases, live (30 September 2026)

Made by `python bench/query_eval.py --models sonnet --reps 3`.

Both conditions: the question, the schema, and read-only SQL through `python query.py`. Indexed: also the source file holding the company's query for it. Graded by running the answer's last SQL block.

| Case | Model | Schema only | Indexed |
|---|---|---|---|
| 01-net-revenue | sonnet | 0 of 3 (8323.02, 8323.02, 8323.02) | 3 of 3 (7238.02, 7238.02, 7238.02) |
| 02-mrr | sonnet | 0 of 3 (17291.3, 17291.3, 17291.3) | 3 of 3 (22771.9, 22771.9, 22771.9) |
| 03-logo-churn | sonnet | 0 of 3 (4.545454545454546, 4.55, 4.545454545454546) | 3 of 3 (7.69, 7.69, 7.69) |
| 04-urgent-first-reply | sonnet | 0 of 3 (81.8, 81.82, 30.77) | 3 of 3 (36.4, 36.4, 36.4) |
| 05-available-to-promise | sonnet | 0 of 3 (700, 700, 700) | 3 of 3 (694, 694, 694) |

| Condition | Model | Correct | Median time | Median queries run | Cost |
|---|---|---|---|---|---|
| schema | sonnet | 0 of 15 | 25.8 s | 5 | $1.05 |
| indexed | sonnet | 15 of 15 | 20.3 s | 4 | $0.99 |

Answers: 01-net-revenue 7238.02; 02-mrr 22771.9; 03-logo-churn 7.69; 04-urgent-first-reply 36.4; 05-available-to-promise 694
