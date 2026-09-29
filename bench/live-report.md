# Live eval: search vs graph

Run 2026-09-25 00:26 on Windows 11. Made by `python bench/live_eval.py --models haiku,sonnet --reps 1 --graph-docs corpus`. Prompt: “A customer wants an £800 refund in March. Who signs it off?”

Runs that searched the docs: search 1 of 2, graph 0 of 2.

Times are from the start of each `claude -p` run. Recall line = the graph hook's response. First answer word = the first text of the final model turn.

| Model | Condition | Answer | Tool calls | Tools ran | Doc text read | Recall line | First answer word | Total | First request tokens | Cost |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| haiku | search | wrong | 0 | 0.00 s | 0 | — | 4.19 s | 5.68 s | 9243 | $0.012 |
| haiku | graph | correct | 0 | 0.00 s | 0 | 0.90 s | 4.75 s | 5.50 s | 9887 | $0.013 |
| sonnet | search | correct | 6 | 0.12 s | 3,617 | — | 20.91 s | 22.81 s | 12074 | $0.052 |
| sonnet | graph | correct | 0 | 0.00 s | 0 | 0.93 s | 5.44 s | 6.25 s | 12910 | $0.033 |

## What the injection costs

- haiku, run 1: the graph hook added 644 input tokens to the first request.
- sonnet, run 1: the graph hook added 836 input tokens to the first request.
