# Live eval: a transcript to a full project and thesis, graph against search

Run 2026-09-30 10:26. Made by `python bench/project_create_eval.py`. Case 01, in the workspace of docs/project-creation-example.html (the nine corpus documents and support-metrics.md, no projects). Today pinned to 2026-09-28. Approvals are instant: a person's review time is left out of both.

| Model | Condition | Runs | Correct | Median total | Range | Model time (median) | Other time (median) | Model calls | Tool calls | Cost per run |
| --- | --- | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: |
| sonnet | graph | 20 | 20 of 20 | 14.5 s | 10.8 s to 114.7 s | 13.9 s | 0.6 s | 2.0 | 0.0 | $0.078 |
| sonnet | search | 20 | 19 of 20 | 16.8 s | 15.5 s to 47.9 s | 16.8 s | 0.0 s | 1.0 | 6.5 | $0.056 |

## Each run

| Model | Condition | Rep | Total | Calls (label: wall, first token, turns, tools) | Stages | Outcome |
| --- | --- | ---: | ---: | --- | --- | --- |
| sonnet | graph | 1 | 42.1 s | extract: 13.4 s, 9.3 s, 1, 0; thesis: 28.1 s, 25.9 s, 1, 0 | change request 1 open 13.7 s; project created, research done 42.1 s; change request 2 applied 42.1 s | ok: 0 check problems; 0 expectations missed; thesis yes; numbers found 3 of 3, asked 1 |
| sonnet | search | 1 | 19.6 s | search: 19.6 s, 3.3 s, 3, 7 | — | ok: 0 check problems; 0 expectations missed; thesis yes; numbers found 3 of 3, asked 1 |
| sonnet | search | 2 | 16.1 s | search: 16.1 s, 2.3 s, 3, 6 | — | ok: 0 check problems; 0 expectations missed; thesis yes; numbers found 3 of 3, asked 1 |
| sonnet | graph | 2 | 19.8 s | extract: 9.7 s, 4.7 s, 1, 0; thesis: 9.5 s, 5.8 s, 1, 0 | change request 1 open 9.9 s; project created, research done 19.7 s; change request 2 applied 19.8 s | ok: 0 check problems; 0 expectations missed; thesis yes; numbers found 3 of 3, asked 1 |
| sonnet | graph | 3 | 17.1 s | extract: 7.6 s, 3.2 s, 1, 0; thesis: 8.8 s, 6.8 s, 1, 0 | change request 1 open 7.9 s; project created, research done 17.1 s; change request 2 applied 17.1 s | ok: 0 check problems; 0 expectations missed; thesis yes; numbers found 3 of 3, asked 1 |
| sonnet | search | 3 | 15.6 s | search: 15.6 s, 2.3 s, 4, 7 | — | ok: 0 check problems; 0 expectations missed; thesis yes; numbers found 3 of 3, asked 1 |
| sonnet | search | 4 | 20.7 s | search: 20.7 s, 3.1 s, 3, 7 | — | ok: 0 check problems; 0 expectations missed; thesis yes; numbers found 3 of 3, asked 1 |
| sonnet | graph | 4 | 13.0 s | extract: 6.5 s, 2.0 s, 1, 0; thesis: 5.9 s, 2.2 s, 1, 0 | change request 1 open 6.8 s; project created, research done 13.0 s; change request 2 applied 13.0 s | ok: 0 check problems; 0 expectations missed; thesis yes; numbers found 3 of 3, asked 1 |
| sonnet | graph | 5 | 10.8 s | extract: 6.3 s, 1.8 s, 1, 0; thesis: 3.9 s, 1.7 s, 1, 0 | change request 1 open 6.6 s; project created, research done 10.8 s; change request 2 applied 10.8 s | ok: 0 check problems; 0 expectations missed; thesis yes; numbers found 3 of 3, asked 1 |
| sonnet | search | 5 | 16.0 s | search: 16.0 s, 2.0 s, 3, 7 | — | ok: 0 check problems; 0 expectations missed; thesis yes; numbers found 3 of 3, asked 1 |
| sonnet | search | 6 | 17.2 s | search: 17.2 s, 3.3 s, 3, 6 | — | NOT OK: 11 check problems; 1 expectations missed; thesis yes; numbers found 3 of 3, asked 1 |
| sonnet | graph | 6 | 16.9 s | extract: 10.4 s, 2.7 s, 1, 0; thesis: 5.9 s, 2.6 s, 1, 0 | change request 1 open 10.7 s; project created, research done 16.9 s; change request 2 applied 16.9 s | ok: 0 check problems; 0 expectations missed; thesis yes; numbers found 3 of 3, asked 1 |
| sonnet | graph | 7 | 14.6 s | extract: 9.0 s, 2.8 s, 1, 0; thesis: 5.0 s, 2.4 s, 1, 0 | change request 1 open 9.3 s; project created, research done 14.6 s; change request 2 applied 14.6 s | ok: 0 check problems; 0 expectations missed; thesis yes; numbers found 3 of 3, asked 1 |
| sonnet | search | 7 | 15.7 s | search: 15.7 s, 1.9 s, 3, 7 | — | ok: 0 check problems; 0 expectations missed; thesis yes; numbers found 3 of 3, asked 1 |
| sonnet | search | 8 | 20.3 s | search: 20.3 s, 3.2 s, 3, 6 | — | ok: 0 check problems; 0 expectations missed; thesis yes; numbers found 3 of 3, asked 1 |
| sonnet | graph | 8 | 12.8 s | extract: 6.4 s, 1.8 s, 1, 0; thesis: 5.7 s, 2.4 s, 1, 0 | change request 1 open 6.8 s; project created, research done 12.8 s; change request 2 applied 12.8 s | ok: 0 check problems; 0 expectations missed; thesis yes; numbers found 3 of 3, asked 1 |
| sonnet | graph | 9 | 13.9 s | extract: 7.2 s, 2.8 s, 1, 0; thesis: 6.1 s, 2.6 s, 1, 0 | change request 1 open 7.5 s; project created, research done 13.9 s; change request 2 applied 13.9 s | ok: 0 check problems; 0 expectations missed; thesis yes; numbers found 3 of 3, asked 1 |
| sonnet | search | 9 | 15.5 s | search: 15.5 s, 1.7 s, 3, 7 | — | ok: 0 check problems; 0 expectations missed; thesis yes; numbers found 3 of 3, asked 1 |
| sonnet | search | 10 | 19.1 s | search: 19.1 s, 2.7 s, 3, 6 | — | ok: 0 check problems; 0 expectations missed; thesis yes; numbers found 3 of 3, asked 1 |
| sonnet | graph | 10 | 16.4 s | extract: 10.1 s, 2.6 s, 1, 0; thesis: 5.7 s, 3.4 s, 1, 0 | change request 1 open 10.4 s; project created, research done 16.4 s; change request 2 applied 16.4 s | ok: 0 check problems; 0 expectations missed; thesis yes; numbers found 3 of 3, asked 1 |
| sonnet | graph | 11 | 38.2 s | extract: 30.4 s, 23.5 s, 1, 0; thesis: 7.3 s, 3.7 s, 1, 0 | change request 1 open 30.6 s; project created, research done 38.2 s; change request 2 applied 38.2 s | ok: 0 check problems; 0 expectations missed; thesis yes; numbers found 3 of 3, asked 1 |
| sonnet | search | 11 | 15.9 s | search: 15.9 s, 2.2 s, 3, 6 | — | ok: 0 check problems; 0 expectations missed; thesis yes; numbers found 3 of 3, asked 1 |
| sonnet | search | 12 | 47.9 s | search: 47.9 s, 23.9 s, 3, 6 | — | ok: 0 check problems; 0 expectations missed; thesis yes; numbers found 3 of 3, asked 1 |
| sonnet | graph | 12 | 37.1 s | extract: 10.6 s, 6.1 s, 1, 0; thesis: 25.8 s, 22.0 s, 1, 0 | change request 1 open 10.9 s; project created, research done 37.0 s; change request 2 applied 37.1 s | ok: 0 check problems; 0 expectations missed; thesis yes; numbers found 3 of 3, asked 1 |
| sonnet | graph | 13 | 20.4 s | extract: 7.5 s, 2.3 s, 1, 0; thesis: 12.2 s, 9.1 s, 1, 0 | change request 1 open 7.8 s; project created, research done 20.3 s; change request 2 applied 20.4 s | ok: 0 check problems; 0 expectations missed; thesis yes; numbers found 3 of 3, asked 1 |
| sonnet | search | 13 | 20.8 s | search: 20.8 s, 5.6 s, 3, 7 | — | ok: 0 check problems; 0 expectations missed; thesis yes; numbers found 3 of 3, asked 1 |
| sonnet | search | 14 | 24.7 s | search: 24.7 s, 2.9 s, 3, 6 | — | ok: 0 check problems; 0 expectations missed; thesis yes; numbers found 3 of 3, asked 1 |
| sonnet | graph | 14 | 13.5 s | extract: 6.4 s, 2.1 s, 1, 0; thesis: 6.5 s, 2.4 s, 1, 0 | change request 1 open 6.7 s; project created, research done 13.5 s; change request 2 applied 13.5 s | ok: 0 check problems; 0 expectations missed; thesis yes; numbers found 3 of 3, asked 1 |
| sonnet | graph | 15 | 14.4 s | extract: 8.0 s, 3.6 s, 1, 0; thesis: 5.7 s, 2.1 s, 1, 0 | change request 1 open 8.3 s; project created, research done 14.4 s; change request 2 applied 14.4 s | ok: 0 check problems; 0 expectations missed; thesis yes; numbers found 3 of 3, asked 1 |
| sonnet | search | 15 | 15.9 s | search: 15.9 s, 1.6 s, 3, 6 | — | ok: 0 check problems; 0 expectations missed; thesis yes; numbers found 3 of 3, asked 1 |
| sonnet | search | 16 | 18.1 s | search: 18.1 s, 2.3 s, 3, 7 | — | ok: 0 check problems; 0 expectations missed; thesis yes; numbers found 3 of 3, asked 1 |
| sonnet | graph | 16 | 13.6 s | extract: 6.7 s, 2.1 s, 1, 0; thesis: 6.2 s, 2.5 s, 1, 0 | change request 1 open 7.0 s; project created, research done 13.6 s; change request 2 applied 13.6 s | ok: 0 check problems; 0 expectations missed; thesis yes; numbers found 3 of 3, asked 1 |
| sonnet | graph | 17 | 11.2 s | extract: 6.4 s, 1.8 s, 1, 0; thesis: 4.3 s, 1.7 s, 1, 0 | change request 1 open 6.7 s; project created, research done 11.2 s; change request 2 applied 11.2 s | ok: 0 check problems; 0 expectations missed; thesis yes; numbers found 3 of 3, asked 1 |
| sonnet | search | 17 | 15.9 s | search: 15.9 s, 1.8 s, 4, 7 | — | ok: 0 check problems; 0 expectations missed; thesis yes; numbers found 3 of 3, asked 1 |
| sonnet | search | 18 | 18.4 s | search: 18.4 s, 4.6 s, 3, 6 | — | ok: 0 check problems; 0 expectations missed; thesis yes; numbers found 3 of 3, asked 1 |
| sonnet | graph | 18 | 114.7 s | extract: 16.2 s, 6.5 s, 1, 0; thesis: 97.9 s, 36.9 s, 1, 0 | change request 1 open 16.5 s; project created, research done 114.7 s; change request 2 applied 114.7 s | ok: 0 check problems; 0 expectations missed; thesis yes; numbers found 3 of 3, asked 1 |
| sonnet | graph | 19 | 12.0 s | extract: 6.4 s, 1.9 s, 1, 0; thesis: 4.9 s, 2.3 s, 1, 0 | change request 1 open 6.7 s; project created, research done 12.0 s; change request 2 applied 12.0 s | ok: 0 check problems; 0 expectations missed; thesis yes; numbers found 3 of 3, asked 1 |
| sonnet | search | 19 | 16.0 s | search: 16.0 s, 2.1 s, 3, 6 | — | ok: 0 check problems; 0 expectations missed; thesis yes; numbers found 3 of 3, asked 1 |
| sonnet | search | 20 | 16.3 s | search: 16.3 s, 2.1 s, 3, 6 | — | ok: 0 check problems; 0 expectations missed; thesis yes; numbers found 3 of 3, asked 1 |
| sonnet | graph | 20 | 14.0 s | extract: 6.4 s, 1.8 s, 1, 0; thesis: 7.0 s, 3.1 s, 1, 0 | change request 1 open 6.7 s; project created, research done 14.0 s; change request 2 applied 14.0 s | ok: 0 check problems; 0 expectations missed; thesis yes; numbers found 3 of 3, asked 1 |
