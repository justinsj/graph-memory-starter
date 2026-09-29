# Graph recall benchmark

Run 2026-09-23 23:16 on Windows 11, Python 3.12.7, SQLite 3.45.3. Made by `python bench/recall_bench.py`.

## Recall as the graph grows

The refund question: “A customer wants an £800 refund in March. Who signs it off?”. Time is `recall()` alone, median of 15 warm calls.

| Graph | Entities | recall() | Facts | Injection chars | Answer in the facts | Build |
| --- | ---: | ---: | ---: | ---: | --- | ---: |
| Demo graph | 14 | 2.56 ms | 8 | 1,455 | yes | 124 ms |
| +1,000 policies elsewhere | 3,014 | 2.95 ms | 8 | 1,321 | yes | 266 ms |
| +10,000 policies elsewhere | 30,014 | 3.48 ms | 8 | 1,321 | yes | 1,723 ms |
| +100 policies on the Ops Manager | 114 | 3.25 ms | 8 | 1,322 | yes | 124 ms |
| +1,000 policies on the Ops Manager | 1,014 | 7.42 ms | 8 | 1,404 | yes | 156 ms |
| +10,000 policies on the Ops Manager | 10,014 | 47.78 ms | 8 | 1,405 | yes | 542 ms |

## The hook as a process

| Measure | Median of 25 |
| --- | ---: |
| Python starting, doing nothing | 27 ms |
| `src/recall_hook.py`, refund question, demo graph | 77 ms |

Inside Claude Code the hook takes longer: Claude Code has to launch it.

## Injection size by question, demo graph

| Question | Facts | Characters |
| --- | ---: | ---: |
| A customer wants an £800 refund in March. Who signs it off? | 8 | 1,455 |
| Who approves supplier payments over £2,000? | 7 | 1,536 |
| What is the onboarding process? | 7 | 1,522 |
| What does Priya do? | 5 | 514 |
| Who is in charge when the boss is away? | 0 | 88 |
