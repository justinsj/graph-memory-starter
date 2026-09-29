# Live eval: questions about a codebase, search against graph

Run 2026-09-28 17:44. Made by `python bench/code_eval.py --regrade`. Every prompt starts "Our code and company docs are in this folder.". Both folders hold the shop's code, the company documents and the CLAUDE.md rule; the graph condition adds the graph hook.

| Model | Condition | Correct | Runs that searched | Tool calls | Average time | Median time | Average without service waits | First-request tokens | Cost per question |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| haiku | search | 20 of 22 | 22 of 22 | 114 | 11.3 s | 10.9 s | 11.3 s | 9,443 | $0.0148 |
| haiku | graph | 22 of 22 | 1 of 22 | 2 | 6.3 s | 5.6 s | 6.3 s | 10,293 | $0.0060 |
| sonnet | search | 22 of 22 | 22 of 22 | 92 | 136.0 s | 9.8 s | 10.0 s (4 waited) | 12,352 | $0.0259 |
| sonnet | graph | 22 of 22 | 0 of 22 | 0 | 4.9 s | 4.0 s | 4.9 s | 13,496 | $0.0110 |

| Case | Condition | Model | Rep | Answer | Correct | Tool calls | Time |
| --- | --- | --- | ---: | --- | --- | ---: | ---: |
| 01-reference-chain | search | haiku | 1 | Compares refund amount against APPROVAL_THRESHOLD_GBP config value | NO | 3 | 7.9 s |
| 01-reference-chain | search | haiku | 2 | Compares refund amount against APPROVAL_THRESHOLD_GBP config value | NO | 3 | 8.9 s |
| 01-reference-chain | search | sonnet | 1 | Compares refund amount to APPROVAL_THRESHOLD_GBP (£250); amounts over £250 require approval. | yes | 4 | 10.0 s |
| 01-reference-chain | search | sonnet | 2 | Compares refund amount to APPROVAL_THRESHOLD_GBP (£250) in config.py; amounts over that need approval. | yes | 4 | 13.9 s |
| 01-reference-chain | graph | haiku | 1 | needs_approval reads APPROVAL_THRESHOLD_GBP (250 GBP) | yes | 0 | 7.4 s |
| 01-reference-chain | graph | haiku | 2 | Calls needs_approval() which compares refund amount against APPROVAL_THRESHOLD_GBP (250 GBP) | yes | 0 | 6.4 s |
| 01-reference-chain | graph | sonnet | 1 | Compares refund amount to APPROVAL_THRESHOLD_GBP (currently 250 in code; policy doc says £500) | yes | 0 | 9.6 s |
| 01-reference-chain | graph | sonnet | 2 | needs_approval() checks amount > config.APPROVAL_THRESHOLD_GBP (currently 250), though policy doc says £500/Ops Manager. | yes | 0 | 10.6 s |
| 02-explicit-route | search | haiku | 1 | get_order | yes | 3 | 8.9 s |
| 02-explicit-route | search | haiku | 2 | get_order | yes | 4 | 9.8 s |
| 02-explicit-route | search | sonnet | 1 | `get_order` in backend/orders/views.py | yes | 3 | 6.2 s |
| 02-explicit-route | search | sonnet | 2 | `get_order` in `backend/orders/views.py` | yes | 3 | 5.6 s |
| 02-explicit-route | graph | haiku | 1 | backend.orders.views.get_order | yes | 0 | 4.2 s |
| 02-explicit-route | graph | haiku | 2 | `backend.orders.views.get_order` (in backend/orders/views.py) | yes | 0 | 4.8 s |
| 02-explicit-route | graph | sonnet | 1 | backend.orders.views.get_order (in backend/orders/views.py) | yes | 0 | 3.2 s |
| 02-explicit-route | graph | sonnet | 2 | backend.orders.views.get_order (backend/orders/views.py) | yes | 0 | 3.8 s |
| 03-variable-url | search | haiku | 1 | Validates the refund, checks approval threshold, queues for approval or processes immediately | yes | 8 | 13.8 s |
| 03-variable-url | search | haiku | 2 | Validates the refund, checks approval threshold, then either queues for approval or processes immediately | yes | 9 | 20.0 s |
| 03-variable-url | search | sonnet | 1 | `create_refund()` in backend/refunds/views.py validates the refund, then either queues it for approval or marks it refunded. | yes | 7 | 12.8 s |
| 03-variable-url | search | sonnet | 2 | POST /api/refunds → validate → approval-threshold check (£250) → queue or mark refunded (no payment call) | yes | 13 | 715.1 s |
| 03-variable-url | graph | haiku | 1 | backend.refunds.views.create_refund — validates the refund and either processes it or queues for approval | yes | 0 | 5.3 s |
| 03-variable-url | graph | haiku | 2 | backend.refunds.views.create_refund — validates and either processes or queues the refund for approval based on amount. | yes | 0 | 6.2 s |
| 03-variable-url | graph | sonnet | 1 | backend.refunds.views.create_refund validates, checks the £250 approval threshold, then refunds instantly or queues for approval. | yes | 0 | 7.0 s |
| 03-variable-url | graph | sonnet | 2 | Validates request, then auto-refunds or queues for approval if amount exceeds £250 threshold. | yes | 0 | 8.7 s |
| 04-conditional-route | search | haiku | 1 | cancel_order | yes | 9 | 17.4 s |
| 04-conditional-route | search | haiku | 2 | handle_action() in backend/orders/views.py (which calls cancel_order()) | yes | 6 | 16.4 s |
| 04-conditional-route | search | sonnet | 1 | `cancel_order()` in backend/orders/service.py (invoked via the `/api/actions` handler) | yes | 5 | 15.4 s |
| 04-conditional-route | search | sonnet | 2 | `cancel_order()` in backend/orders/service.py, invoked via the `/api/actions` handler | yes | 6 | 9.9 s |
| 04-conditional-route | graph | haiku | 1 | backend.orders.service.cancel_order (called via handle_action) | yes | 0 | 9.8 s |
| 04-conditional-route | graph | haiku | 2 | backend.orders.service.cancel_order (called via backend.orders.views.handle_action) | yes | 0 | 9.6 s |
| 04-conditional-route | graph | sonnet | 1 | backend.orders.service.cancel_order (dispatched via backend.orders.views.handle_action) | yes | 0 | 2.6 s |
| 04-conditional-route | graph | sonnet | 2 | backend.orders.service.cancel_order (dispatched via backend.orders.views.handle_action) | yes | 0 | 2.7 s |
| 05-impact | search | haiku | 1 | Orders service and refunds API endpoint both depend on it to determine when to queue refunds for approval. | yes | 4 | 11.2 s |
| 05-impact | search | haiku | 2 | Order service refund flow, refunds API endpoint, approval queue integration | yes | 4 | 10.5 s |
| 05-impact | search | sonnet | 1 | Changes both refunds/views.py's /api/refunds endpoint and orders/service.py's process_refund (order quick-refund action) — both share this one gate function. | yes | 2 | 8.6 s |
| 05-impact | search | sonnet | 2 | Affects refunds API endpoint and orders' process_refund quick-action flow (both call needs_approval before queue_for_approval). | yes | 2 | 9.7 s |
| 05-impact | graph | haiku | 1 | create_refund, process_refund, approval queueing, and both frontend refund flows (RefundForm and OrderPage) | yes | 0 | 8.4 s |
| 05-impact | graph | haiku | 2 | Two backend functions call it; affects both refund APIs and frontend buttons that trigger them. | yes | 0 | 8.5 s |
| 05-impact | graph | sonnet | 1 | Both refund flows (RefundForm and Quick refund) and the approval queue are affected. | yes | 0 | 5.1 s |
| 05-impact | graph | sonnet | 2 | Both refund paths (create_refund and process_refund) and the approval queue are affected. | yes | 0 | 4.6 s |
| 06-dead-code | search | haiku | 1 | No, legacy_refund is not used anywhere—only defined but unused. | yes | 3 | 8.7 s |
| 06-dead-code | search | haiku | 2 | No, legacy_refund is not used anywhere—it's defined but never called. | yes | 4 | 12.0 s |
| 06-dead-code | search | sonnet | 1 | No, it's unused (only defined, no callers). | yes | 3 | 5.9 s |
| 06-dead-code | search | sonnet | 2 | No — `legacy_refund` is defined but unused/unreferenced elsewhere. | yes | 4 | 704.7 s |
| 06-dead-code | graph | haiku | 1 | No, `legacy_refund` is unused. | yes | 2 | 9.4 s |
| 06-dead-code | graph | haiku | 2 | No, legacy_refund is unused. | yes | 0 | 4.5 s |
| 06-dead-code | graph | sonnet | 1 | No — legacy_refund is defined but never called anywhere in the code. | yes | 0 | 3.9 s |
| 06-dead-code | graph | sonnet | 2 | No, legacy_refund is unused/dead code. | yes | 0 | 3.8 s |
| 07-name-collision | search | haiku | 1 | validate (from refunds.rules) | yes | 2 | 5.8 s |
| 07-name-collision | search | haiku | 2 | The `validate` function from the rules module | yes | 2 | 6.1 s |
| 07-name-collision | search | sonnet | 1 | `validate` from backend/refunds/rules.py | yes | 2 | 6.2 s |
| 07-name-collision | search | sonnet | 2 | `validate` from `refunds/rules.py` | yes | 2 | 699.3 s |
| 07-name-collision | graph | haiku | 1 | backend.refunds.rules.validate | yes | 0 | 3.6 s |
| 07-name-collision | graph | haiku | 2 | backend.refunds.rules.validate | yes | 0 | 3.8 s |
| 07-name-collision | graph | sonnet | 1 | backend.refunds.rules.validate | yes | 0 | 2.1 s |
| 07-name-collision | graph | sonnet | 2 | backend.refunds.rules.validate | yes | 0 | 5.0 s |
| 08-code-against-policy | search | haiku | 1 | No, they don't match. Code has £250, policy requires £500. | yes | 8 | 13.8 s |
| 08-code-against-policy | search | haiku | 2 | No, code uses £250 but policy requires £500. | yes | 8 | 12.5 s |
| 08-code-against-policy | search | sonnet | 1 | No — code uses £250/Director (2024, superseded); current policy is £500/Ops Manager. | yes | 6 | 11.1 s |
| 08-code-against-policy | search | sonnet | 2 | No — code uses £250 threshold (old 2024 policy), but current policy requires £500. | yes | 6 | 701.7 s |
| 08-code-against-policy | graph | haiku | 1 | No, backend is £250 but policy requires £500; frontend correctly matches policy but backend doesn't. | yes | 0 | 6.8 s |
| 08-code-against-policy | graph | haiku | 2 | No, the backend threshold (250) contradicts the policy (500), though frontend matches. | yes | 0 | 7.3 s |
| 08-code-against-policy | graph | sonnet | 1 | No — backend uses £250 (and "Director"), policy/frontend use £500 (Ops Manager). | yes | 0 | 7.1 s |
| 08-code-against-policy | graph | sonnet | 2 | No — backend uses £250, policy requires £500 | yes | 0 | 7.2 s |
| 09-frontend-against-backend | search | haiku | 1 | No, they disagree (backend uses 250 GBP, frontend uses 500) | yes | 5 | 7.6 s |
| 09-frontend-against-backend | search | haiku | 2 | No, they disagree — frontend uses 500, backend uses 250. | yes | 7 | 14.3 s |
| 09-frontend-against-backend | search | sonnet | 1 | No — backend threshold is 250, frontend is 500 (mismatch). | yes | 1 | 7.6 s |
| 09-frontend-against-backend | search | sonnet | 2 | No — backend uses 250, frontend uses 500. | yes | 1 | 6.7 s |
| 09-frontend-against-backend | graph | haiku | 1 | No, backend is 250 GBP while frontend is 500. | yes | 0 | 5.3 s |
| 09-frontend-against-backend | graph | haiku | 2 | No, they disagree. Frontend uses 500, backend uses 250. | yes | 0 | 4.9 s |
| 09-frontend-against-backend | graph | sonnet | 1 | No — frontend threshold is 500, backend is 250 (mismatch) | yes | 0 | 4.1 s |
| 09-frontend-against-backend | graph | sonnet | 2 | No — frontend threshold is 500, backend threshold is 250. | yes | 0 | 4.4 s |
| 10-identifier-styles | search | haiku | 1 | REFUNDS_URL in frontend/src/api.ts holds `/api/refunds` | yes | 6 | 13.1 s |
| 10-identifier-styles | search | haiku | 2 | `frontend/src/api.ts` line 3; holds "/api/refunds" | yes | 7 | 12.0 s |
| 10-identifier-styles | search | sonnet | 1 | `frontend/src/api.ts:3` (as `REFUNDS_URL`) — value `/api/refunds` | yes | 5 | 8.6 s |
| 10-identifier-styles | search | sonnet | 2 | frontend/src/api.ts defines REFUNDS_URL = "/api/refunds" | yes | 4 | 17.3 s |
| 10-identifier-styles | graph | haiku | 1 | REFUNDS_URL is defined in frontend/src/api.ts and holds the value "/api/refunds" | yes | 0 | 5.4 s |
| 10-identifier-styles | graph | haiku | 2 | REFUNDS_URL is defined in frontend/src/api.ts and holds the URL /api/refunds | yes | 0 | 5.6 s |
| 10-identifier-styles | graph | sonnet | 1 | Defined in frontend/src/api.ts; holds "/api/refunds" | yes | 0 | 3.8 s |
| 10-identifier-styles | graph | sonnet | 2 | Defined in frontend/src/api.ts; holds "/api/refunds" | yes | 0 | 3.4 s |
| 11-claims-question | search | haiku | 1 | Any support agent can approve it (standard refunds under £500 are processed by any support agent within 48 hours) | yes | 5 | 8.6 s |
| 11-claims-question | search | haiku | 2 | Any support agent (standard refund under £500 threshold) | yes | 4 | 8.7 s |
| 11-claims-question | search | sonnet | 1 | No approval needed — any support agent processes it (under the £500 threshold). | yes | 4 | 7.7 s |
| 11-claims-question | search | sonnet | 2 | No approval needed — any support agent can process it (under the £500 threshold). | yes | 5 | 8.9 s |
| 11-claims-question | graph | haiku | 1 | Any support agent can approve a £300 refund | yes | 0 | 4.7 s |
| 11-claims-question | graph | haiku | 2 | Any support agent can process it (no manager approval needed) | yes | 0 | 5.6 s |
| 11-claims-question | graph | sonnet | 1 | No approval needed; any support agent processes it (under £500 threshold). | yes | 0 | 3.8 s |
| 11-claims-question | graph | sonnet | 2 | No approval needed; any support agent processes it directly (under £500 threshold) | yes | 0 | 2.1 s |
