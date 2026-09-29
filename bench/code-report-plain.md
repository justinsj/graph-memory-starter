# Live eval: questions about a codebase, search against graph

Run 2026-09-28 17:44. Made by `python bench/code_eval.py --plain --regrade`. Asked plainly. Both folders hold the shop's code, the company documents and the CLAUDE.md rule; the graph condition adds the graph hook.

| Model | Condition | Correct | Runs that searched | Tool calls | Average time | Median time | Average without service waits | First-request tokens | Cost per question |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| haiku | search | 9 of 11 | 11 of 11 | 48 | 9.9 s | 10.8 s | 9.9 s | 9,430 | $0.0154 |
| haiku | graph | 11 of 11 | 0 of 11 | 0 | 6.3 s | 5.7 s | 6.3 s | 10,280 | $0.0081 |
| sonnet | search | 10 of 11 | 11 of 11 | 52 | 10.9 s | 10.1 s | 10.9 s | 12,339 | $0.0314 |
| sonnet | graph | 11 of 11 | 0 of 11 | 0 | 4.4 s | 3.6 s | 4.4 s | 13,483 | $0.0152 |

| Case | Condition | Model | Rep | Answer | Correct | Tool calls | Time |
| --- | --- | --- | ---: | --- | --- | ---: | ---: |
| 01-reference-chain | search | haiku | 1 | Compares refund amount against APPROVAL_THRESHOLD_GBP from config | NO | 3 | 9.3 s |
| 01-reference-chain | search | sonnet | 1 | It checks needs_approval(amount) > APPROVAL_THRESHOLD_GBP (250 GBP) from config.py. | yes | 5 | 10.1 s |
| 01-reference-chain | graph | haiku | 1 | Calls `needs_approval()` which compares refund amount against `APPROVAL_THRESHOLD_GBP` (currently 250). | yes | 0 | 5.7 s |
| 01-reference-chain | graph | sonnet | 1 | Compares refund amount to APPROVAL_THRESHOLD_GBP (=250) via needs_approval; note this conflicts with the current policy's £500/Ops Manager threshold. | yes | 0 | 9.6 s |
| 02-explicit-route | search | haiku | 1 | get_order | yes | 3 | 8.1 s |
| 02-explicit-route | search | sonnet | 1 | `get_order` in backend/orders/views.py | yes | 4 | 6.0 s |
| 02-explicit-route | graph | haiku | 1 | backend.orders.views.get_order | yes | 0 | 4.5 s |
| 02-explicit-route | graph | sonnet | 1 | backend.orders.views.get_order | yes | 0 | 2.2 s |
| 03-variable-url | search | haiku | 1 | Validates the refund, checks if approval is needed, then either queues it or processes it immediately. | yes | 5 | 11.8 s |
| 03-variable-url | search | sonnet | 1 | POST /api/refunds validates the amount, then either queues it for approval (if over threshold) or marks it refunded immediately. | yes | 11 | 17.6 s |
| 03-variable-url | graph | haiku | 1 | backend.refunds.views.create_refund validates and processes the refund request | yes | 0 | 6.2 s |
| 03-variable-url | graph | sonnet | 1 | Validates request, checks amount vs. £250 threshold, either refunds immediately or queues for approval. | yes | 0 | 5.3 s |
| 04-conditional-route | search | haiku | 1 | cancel_order (in backend/orders/service.py) | yes | 1 | 6.3 s |
| 04-conditional-route | search | sonnet | 1 | `cancel_order()` in backend/orders/service.py (invoked via the `/api/actions` handler) | yes | 5 | 15.2 s |
| 04-conditional-route | graph | haiku | 1 | backend.orders.service.cancel_order (dispatched by handle_action) | yes | 0 | 10.7 s |
| 04-conditional-route | graph | sonnet | 1 | backend.orders.service.cancel_order | yes | 0 | 3.6 s |
| 05-impact | search | haiku | 1 | The `process_refund()` function in orders/service.py and the `/api/refunds` endpoint in refunds/views.py—both use it to gate refund approval queueing. | yes | 4 | 10.8 s |
| 05-impact | search | sonnet | 1 | Affects refunds API and orders.service.process_refund, both branching on approval threshold. | yes | 2 | 7.3 s |
| 05-impact | graph | haiku | 1 | Direct callers (create_refund, process_refund), both refund flows (form and quick action), approval queueing logic. | yes | 0 | 9.6 s |
| 05-impact | graph | sonnet | 1 | Both refund flows' approval-queuing behavior (create_refund and process_refund → PENDING queue) | yes | 0 | 7.3 s |
| 06-dead-code | search | haiku | 1 | No, legacy_refund is not used anywhere in the codebase. | yes | 5 | 11.0 s |
| 06-dead-code | search | sonnet | 1 | No, it's defined but never called/imported elsewhere. | yes | 2 | 5.8 s |
| 06-dead-code | graph | haiku | 1 | No, legacy_refund is unused. | yes | 0 | 4.0 s |
| 06-dead-code | graph | sonnet | 1 | No, it's unused (dead code). | yes | 0 | 3.6 s |
| 07-name-collision | search | haiku | 1 | validate | NO | 2 | 5.8 s |
| 07-name-collision | search | sonnet | 1 | validate from refunds/rules.py | yes | 2 | 4.5 s |
| 07-name-collision | graph | haiku | 1 | backend.refunds.rules.validate | yes | 0 | 4.7 s |
| 07-name-collision | graph | sonnet | 1 | backend.refunds.rules.validate | yes | 0 | 2.1 s |
| 08-code-against-policy | search | haiku | 1 | No, threshold is £250 in code but policy requires £500. | yes | 8 | 13.0 s |
| 08-code-against-policy | search | sonnet | 1 | No — code uses £250/Director (old 2024 policy), current policy requires £500/Ops Manager. | yes | 6 | 14.9 s |
| 08-code-against-policy | graph | haiku | 1 | No, backend threshold (£250) doesn't match policy (£500) | yes | 0 | 6.3 s |
| 08-code-against-policy | graph | sonnet | 1 | No — backend uses £250 (stale), policy/frontend use £500. | yes | 0 | 6.6 s |
| 09-frontend-against-backend | search | haiku | 1 | No, they disagree. Backend uses 250, frontend uses 500. | yes | 6 | 9.9 s |
| 09-frontend-against-backend | search | sonnet | 1 | No — frontend uses 500, backend enforces £250. | yes | 4 | 9.0 s |
| 09-frontend-against-backend | graph | haiku | 1 | No, they disagree (frontend 500 vs backend 250) | yes | 0 | 5.2 s |
| 09-frontend-against-backend | graph | sonnet | 1 | No — frontend is £500, backend is £250 | yes | 0 | 2.8 s |
| 10-identifier-styles | search | haiku | 1 | frontend/src/api.ts line 3; holds `/api/refunds` | yes | 5 | 11.9 s |
| 10-identifier-styles | search | sonnet | 1 | Not found — no `refundsUrl` definition exists in this codebase. | NO | 4 | 13.0 s |
| 10-identifier-styles | graph | haiku | 1 | Defined in frontend/src/api.ts; holds `/api/refunds` | yes | 0 | 8.5 s |
| 10-identifier-styles | graph | sonnet | 1 | Defined in frontend/src/api.ts; holds "/api/refunds" | yes | 0 | 2.3 s |
| 11-claims-question | search | haiku | 1 | Any support agent (no approval required — under £500 threshold) | yes | 6 | 11.1 s |
| 11-claims-question | search | sonnet | 1 | No approval needed (under £500 threshold, processed directly by a support agent) — but note code still uses stale £250/Director threshold | yes | 7 | 16.0 s |
| 11-claims-question | graph | haiku | 1 | Any support agent (no Ops Manager approval needed) | yes | 0 | 4.2 s |
| 11-claims-question | graph | sonnet | 1 | No approval needed; any support agent processes it directly | yes | 0 | 2.7 s |
