# Live eval: a transcript to a full project and thesis, graph against search

Run 2026-09-30 09:58. Made by `python bench/project_create_eval.py`. Case 01, in the workspace of docs/project-creation-example.html (the nine corpus documents and support-metrics.md, no projects). Today pinned to 2026-09-28. Approvals are instant: a person's review time is left out of both.

| Model | Condition | Runs | Correct | Median total | Range | Model time (median) | Other time (median) | Model calls | Tool calls | Cost per run |
| --- | --- | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: |
| haiku | graph | 5 | 3 of 5 | 120.5 s | 100.2 s to 155.9 s | 119.9 s | 0.6 s | 2.2 | 0.0 | $0.100 |
| haiku | search | 5 | 0 of 5 | 127.3 s | 74.1 s to 243.4 s | 127.3 s | 0.0 s | 1.0 | 8.6 | $0.100 |
| haiku-nothink | graph | 5 | 0 of 5 | 19.9 s | 14.0 s to 54.1 s | 19.3 s | 0.3 s | 2.2 | 0.0 | $0.043 |
| haiku-nothink | search | 5 | 0 of 5 | 25.1 s | 18.9 s to 50.2 s | 25.1 s | 0.0 s | 1.0 | 9.0 | $0.033 |
| sonnet | graph | 5 | 5 of 5 | 14.8 s | 11.3 s to 17.3 s | 14.2 s | 0.6 s | 2.0 | 0.0 | $0.078 |
| sonnet | search | 5 | 5 of 5 | 16.1 s | 15.2 s to 18.6 s | 16.1 s | 0.0 s | 1.0 | 6.6 | $0.057 |

## Each run

| Model | Condition | Rep | Total | Calls (label: wall, first token, turns, tools) | Stages | Outcome |
| --- | --- | ---: | ---: | --- | --- | --- |
| haiku | graph | 1 | 124.5 s | extract: 85.2 s, 2.3 s, 1, 0; repair: 11.8 s, 2.9 s, 1, 0; thesis: 26.8 s, 2.2 s, 1, 0 | change request 1 open 97.4 s; project created, research done 124.5 s; change request 2 applied 124.5 s | ok: 0 check problems; 0 expectations missed; thesis yes; numbers found 3 of 3, asked 1 |
| haiku | search | 1 | 127.0 s | search: 127.0 s, 5.8 s, 3, 7 | — | NOT OK: 0 check problems; 2 expectations missed; thesis yes; numbers found 2 of 3, asked 1 |
| sonnet | graph | 1 | 14.8 s | extract: 7.1 s, 2.5 s, 1, 0; thesis: 7.1 s, 2.3 s, 1, 0 | change request 1 open 7.4 s; project created, research done 14.8 s; change request 2 applied 14.8 s | ok: 0 check problems; 0 expectations missed; thesis yes; numbers found 3 of 3, asked 1 |
| sonnet | search | 1 | 18.3 s | search: 18.3 s, 2.5 s, 3, 6 | — | ok: 0 check problems; 0 expectations missed; thesis yes; numbers found 3 of 3, asked 1 |
| haiku | search | 2 | 74.1 s | search: 74.1 s, 3.7 s, 5, 7 | — | NOT OK: 0 check problems; 2 expectations missed; thesis yes; numbers found 3 of 3, asked 1 |
| haiku | graph | 2 | 108.2 s | extract: 83.2 s, 2.3 s, 1, 0; thesis: 24.4 s, 2.5 s, 1, 0 | change request 1 open 83.5 s; project created, research done 108.2 s; change request 2 applied 108.2 s | ok: 0 check problems; 0 expectations missed; thesis yes; numbers found 3 of 3, asked 1 |
| sonnet | search | 2 | 15.2 s | search: 15.2 s, 1.7 s, 3, 6 | — | ok: 0 check problems; 0 expectations missed; thesis yes; numbers found 3 of 3, asked 1 |
| sonnet | graph | 2 | 13.7 s | extract: 6.9 s, 2.1 s, 1, 0; thesis: 6.2 s, 2.1 s, 1, 0 | change request 1 open 7.2 s; project created, research done 13.7 s; change request 2 applied 13.7 s | ok: 0 check problems; 0 expectations missed; thesis yes; numbers found 3 of 3, asked 1 |
| haiku | graph | 3 | 100.2 s | extract: 64.7 s, 2.4 s, 1, 0; thesis: 34.8 s, 7.9 s, 1, 0 | change request 1 open 65.0 s; project created, research done 100.2 s; change request 2 applied 100.2 s | NOT OK: 0 check problems; 1 expectations missed; thesis yes; numbers found 1 of 3, asked 1 |
| haiku | search | 3 | 243.4 s | search: 243.4 s, 2.5 s, 5, 9 | — | NOT OK: 0 check problems; 1 expectations missed; thesis yes; numbers found 3 of 3, asked 1 |
| sonnet | graph | 3 | 15.2 s | extract: 8.6 s, 4.2 s, 1, 0; thesis: 6.0 s, 2.3 s, 1, 0 | change request 1 open 8.9 s; project created, research done 15.2 s; change request 2 applied 15.2 s | ok: 0 check problems; 0 expectations missed; thesis yes; numbers found 3 of 3, asked 1 |
| sonnet | search | 3 | 16.1 s | search: 16.1 s, 1.7 s, 4, 7 | — | ok: 0 check problems; 0 expectations missed; thesis yes; numbers found 3 of 3, asked 1 |
| haiku | search | 4 | 137.2 s | search: 137.2 s, 2.0 s, 4, 10 | — | NOT OK: 0 check problems; 1 expectations missed; thesis yes; numbers found 3 of 3, asked 1 |
| haiku | graph | 4 | 155.9 s | extract: 129.9 s, 2.6 s, 1, 0; thesis: 25.4 s, 2.6 s, 1, 0 | change request 1 open 130.2 s; project created, research done 155.9 s; change request 2 applied 155.9 s | ok: 0 check problems; 0 expectations missed; thesis yes; numbers found 3 of 3, asked 1 |
| sonnet | search | 4 | 15.2 s | search: 15.2 s, 1.7 s, 3, 7 | — | ok: 0 check problems; 0 expectations missed; thesis yes; numbers found 3 of 3, asked 1 |
| sonnet | graph | 4 | 17.3 s | extract: 6.5 s, 1.8 s, 1, 0; thesis: 10.2 s, 8.0 s, 1, 0 | change request 1 open 6.8 s; project created, research done 17.3 s; change request 2 applied 17.3 s | ok: 0 check problems; 0 expectations missed; thesis yes; numbers found 3 of 3, asked 1 |
| haiku | graph | 5 | 120.5 s | extract: 94.1 s, 2.3 s, 1, 0; thesis: 25.9 s, 2.5 s, 1, 0 | change request 1 open 94.4 s; project created, research done 120.5 s; change request 2 applied 120.5 s | NOT OK: 0 check problems; 1 expectations missed; thesis yes; numbers found 3 of 3, asked 1 |
| haiku | search | 5 | 127.3 s | search: 127.3 s, 3.6 s, 4, 10 | — | NOT OK: 0 check problems; 2 expectations missed; thesis yes; numbers found 3 of 3, asked 1 |
| sonnet | graph | 5 | 11.3 s | extract: 6.2 s, 1.9 s, 1, 0; thesis: 4.4 s, 2.0 s, 1, 0 | change request 1 open 6.5 s; project created, research done 11.2 s; change request 2 applied 11.3 s | ok: 0 check problems; 0 expectations missed; thesis yes; numbers found 3 of 3, asked 1 |
| sonnet | search | 5 | 18.6 s | search: 18.6 s, 2.6 s, 3, 7 | — | ok: 0 check problems; 0 expectations missed; thesis yes; numbers found 3 of 3, asked 1 |
| haiku-nothink | graph | 1 | 23.4 s | extract: 10.8 s, 6.1 s, 1, 0; repair: 12.3 s, 7.1 s, 1, 0 | change request 1 open 23.4 s | NOT OK: 1 check problems; 4 expectations missed; thesis NO (because quote not in transcript); numbers found 0 of 3, asked 0 |
| haiku-nothink | search | 1 | 27.2 s | search: 27.2 s, 3.4 s, 6, 12 | — | NOT OK: 11 check problems; 1 expectations missed; thesis yes; numbers found 3 of 3, asked 1 |
| haiku-nothink | search | 2 | 18.9 s | search: 18.9 s, 1.7 s, 4, 7 | — | NOT OK: 8 check problems; 1 expectations missed; thesis yes; numbers found 0 of 3, asked 0 |
| haiku-nothink | graph | 2 | 14.0 s | extract: 7.0 s, 1.9 s, 1, 0; repair: 6.7 s, 1.9 s, 1, 0 | change request 1 open 14.0 s | NOT OK: 1 check problems; 3 expectations missed; thesis NO (because quote not in transcript); numbers found 0 of 3, asked 0 |
| haiku-nothink | graph | 3 | 19.9 s | extract: 6.0 s, 1.5 s, 1, 0; repair: 6.6 s, 1.8 s, 1, 0; thesis: 6.7 s, 2.9 s, 1, 0 | change request 1 open 12.9 s; project created, research done 19.9 s; change request 2 applied 19.9 s | NOT OK: 0 check problems; 3 expectations missed; thesis yes; numbers found 3 of 3, asked 1 |
| haiku-nothink | search | 3 | 50.2 s | search: 50.2 s, 24.4 s, 3, 8 | — | NOT OK: 9 check problems; 1 expectations missed; thesis yes; numbers found 3 of 3, asked 1 |
| haiku-nothink | search | 4 | 25.1 s | search: 25.1 s, 4.3 s, 5, 9 | — | NOT OK: 9 check problems; 1 expectations missed; thesis yes; numbers found 0 of 3, asked 0 |
| haiku-nothink | graph | 4 | 14.7 s | extract: 6.5 s, 1.6 s, 1, 0; repair: 7.9 s, 3.2 s, 1, 0 | change request 1 open 14.7 s | NOT OK: 1 check problems; 3 expectations missed; thesis NO (because quote not in transcript); numbers found 0 of 3, asked 0 |
| haiku-nothink | graph | 5 | 54.1 s | extract: 47.2 s, 42.2 s, 1, 0; repair: 6.6 s, 1.9 s, 1, 0 | change request 1 open 54.1 s | NOT OK: 1 check problems; 3 expectations missed; thesis NO (because quote not in transcript); numbers found 0 of 3, asked 0 |
| haiku-nothink | search | 5 | 24.7 s | search: 24.7 s, 1.8 s, 4, 9 | — | NOT OK: 0 check problems; 2 expectations missed; thesis yes; numbers found 3 of 3, asked 1 |

## Building the graph's facts (once, before any project)

| Model | Documents | Sum of calls | Longest call | Cost | Replies with JSON |
| --- | ---: | ---: | ---: | ---: | ---: |
| sonnet | 10 | 115.8 s | 17.0 s | $0.339 | 10 of 10 |
