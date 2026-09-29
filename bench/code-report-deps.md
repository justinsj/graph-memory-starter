# Live eval: questions about a codebase, search against graph

Run 2026-09-28 18:24. Made by `python bench/code_eval.py --tag deps --regrade`. Every prompt starts "Our code and company docs are in this folder.". Both folders hold the shop's code, the company documents and the CLAUDE.md rule; the graph condition adds the graph hook. Cases marked * are graded on the whole reply: it must name every call site that has to change.

| Model | Condition | Correct | Runs that searched | Tool calls | Average time | Median time | Average without service waits | First-request tokens | Cost per question |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| haiku | search | 26 of 32 | 32 of 32 | 195 | 13.5 s | 11.4 s | 13.5 s | 9,445 | $0.0178 |
| haiku | graph | 29 of 32 | 5 of 32 | 48 | 9.7 s | 7.0 s | 9.7 s | 10,669 | $0.0103 |
| sonnet | search | 31 of 32 | 32 of 32 | 149 | 9.1 s | 7.8 s | 9.1 s | 5,334 | $0.0250 |
| sonnet | graph | 32 of 32 | 8 of 32 | 18 | 5.8 s | 4.9 s | 5.8 s | 6,962 | $0.0136 |

| Case | Condition | Model | Rep | Answer | Correct | Tool calls | Time |
| --- | --- | --- | ---: | --- | --- | ---: | ---: |
| 01-reference-chain | search | haiku | 1 | Compares refund amount against APPROVAL_THRESHOLD_GBP threshold value | NO | 3 | 8.3 s |
| 01-reference-chain | search | haiku | 2 | Compares refund amount against APPROVAL_THRESHOLD_GBP from config | NO | 3 | 8.4 s |
| 01-reference-chain | search | sonnet | 1 | It compares the refund amount with APPROVAL_THRESHOLD_GBP (250 GBP), and refunds strictly over that go to approval. | yes | 5 | 13.0 s |
| 01-reference-chain | search | sonnet | 2 | It compares the refund amount to APPROVAL_THRESHOLD_GBP (250 GBP) and requires approval when the amount is strictly greater. | yes | 5 | 7.8 s |
| 01-reference-chain | graph | haiku | 1 | Calls `needs_approval(amount)`, compares against APPROVAL_THRESHOLD_GBP = 250 GBP | yes | 0 | 7.6 s |
| 01-reference-chain | graph | haiku | 2 | Calls `needs_approval()` function, compares refund amount against `APPROVAL_THRESHOLD_GBP` (250) | yes | 0 | 7.3 s |
| 01-reference-chain | graph | sonnet | 1 | It calls needs_approval(amount), which compares the amount to APPROVAL_THRESHOLD_GBP = 250. The policy says £500, so they don't match. | yes | 0 | 6.8 s |
| 01-reference-chain | graph | sonnet | 2 | It queues the refund for approval when amount > APPROVAL_THRESHOLD_GBP, which is £250 in config.py. The policy says £500. | yes | 2 | 8.5 s |
| 02-explicit-route | search | haiku | 1 | get_order | yes | 5 | 9.3 s |
| 02-explicit-route | search | haiku | 2 | get_order function in backend/orders/views.py | yes | 3 | 8.9 s |
| 02-explicit-route | search | sonnet | 1 | get_order in backend/orders/views.py (GET /api/orders/<order_id>) | yes | 4 | 7.7 s |
| 02-explicit-route | search | sonnet | 2 | get_order in backend/orders/views.py | yes | 5 | 5.1 s |
| 02-explicit-route | graph | haiku | 1 | backend.orders.views.get_order | yes | 0 | 4.2 s |
| 02-explicit-route | graph | haiku | 2 | backend.orders.views.get_order | yes | 0 | 3.8 s |
| 02-explicit-route | graph | sonnet | 1 | backend.orders.views.get_order | yes | 0 | 3.3 s |
| 02-explicit-route | graph | sonnet | 2 | backend.orders.views.get_order | yes | 0 | 2.1 s |
| 03-variable-url | search | haiku | 1 | Validates refund and either queues for approval or processes immediately based on amount | yes | 6 | 14.1 s |
| 03-variable-url | search | haiku | 2 | Validates the refund, checks approval threshold, and queues for approval if needed. | yes | 5 | 11.2 s |
| 03-variable-url | search | sonnet | 1 | `create_refund()` in `backend/refunds/views.py` (POST /api/refunds): validates the request, then queues the refund for approval or returns "refunded" | yes | 7 | 10.3 s |
| 03-variable-url | search | sonnet | 2 | POST /api/refunds → create_refund() in backend/refunds/views.py (validate, then queue for approval or return "refunded") | yes | 8 | 12.9 s |
| 03-variable-url | graph | haiku | 1 | create_refund view runs, which validates the refund and queues it for approval if over threshold. | yes | 0 | 4.6 s |
| 03-variable-url | graph | haiku | 2 | backend.refunds.views.create_refund runs, which validates the refund and queues it for approval if it exceeds the 250 GBP threshold. | yes | 0 | 6.7 s |
| 03-variable-url | graph | sonnet | 1 | `create_refund` in backend/refunds/views.py, via POST /api/refunds (validate, needs_approval, queue_for_approval) | yes | 0 | 4.6 s |
| 03-variable-url | graph | sonnet | 2 | `create_refund` in backend/refunds/views.py (POST /api/refunds): validate, needs_approval check (£250 threshold), then queue_for_approval | yes | 0 | 4.4 s |
| 04-conditional-route | search | haiku | 1 | cancel_order | yes | 7 | 14.2 s |
| 04-conditional-route | search | haiku | 2 | handle_action() endpoint, which calls cancel_order() from service | yes | 6 | 15.6 s |
| 04-conditional-route | search | sonnet | 1 | cancel_order (backend/orders/service.py), called via handle_action at POST /api/actions | yes | 3 | 7.0 s |
| 04-conditional-route | search | sonnet | 2 | cancel_order (backend/orders/service.py), via handle_action at POST /api/actions | yes | 3 | 5.0 s |
| 04-conditional-route | graph | haiku | 1 | backend.orders.service.cancel_order | yes | 0 | 7.3 s |
| 04-conditional-route | graph | haiku | 2 | `backend.orders.service.cancel_order` | yes | 0 | 8.6 s |
| 04-conditional-route | graph | sonnet | 1 | backend.orders.service.cancel_order, called via handle_action on POST /api/actions | yes | 0 | 4.2 s |
| 04-conditional-route | graph | sonnet | 2 | backend.orders.service.cancel_order (via handle_action) | yes | 0 | 3.1 s |
| 05-impact * | search | haiku | 1 | Order processing flow, refund API endpoint, monthly reports, and tests are affected. | yes | 2 | 10.4 s |
| 05-impact * | search | haiku | 2 | Refund approval flow (2 endpoints), reporting metrics, and tests | yes | 7 | 15.8 s |
| 05-impact * | search | sonnet | 1 | views.py, orders/service.py, reports.py, tests, config threshold, frontend form, and policy docs | yes | 7 | 13.2 s |
| 05-impact * | search | sonnet | 2 | views.py, orders/service.py, reports.py, tests, the frontend threshold, and the policy docs. The backend £250 disagrees with the frontend and the current £500 policy. | yes | 3 | 10.2 s |
| 05-impact * | graph | haiku | 1 | Two API endpoints, two frontend buttons, approval queue behavior, reports, and four test cases. | NO | 0 | 8.2 s |
| 05-impact * | graph | haiku | 2 | Two API endpoints, reports, tests, and two frontend buttons that trigger refunds | yes | 0 | 9.8 s |
| 05-impact * | graph | sonnet | 1 | Both refund endpoints (create_refund and process_refund), count_large report, two tests, and the config threshold. | yes | 0 | 7.5 s |
| 05-impact * | graph | sonnet | 2 | create_refund, process_refund, count_large, tests, the `refunds/__init__` re-export, and the threshold config | yes | 0 | 7.4 s |
| 06-dead-code | search | haiku | 1 | No, legacy_refund is not used anywhere (dead function). | yes | 4 | 10.5 s |
| 06-dead-code | search | haiku | 2 | No, legacy_refund is not used anywhere. | yes | 4 | 10.1 s |
| 06-dead-code | search | sonnet | 1 | No, only defined in backend/refunds/legacy.py, never referenced | yes | 2 | 5.3 s |
| 06-dead-code | search | sonnet | 2 | No — only defined in backend\refunds\legacy.py, never referenced. | yes | 2 | 6.8 s |
| 06-dead-code | graph | haiku | 1 | No, legacy_refund is unused | yes | 0 | 3.9 s |
| 06-dead-code | graph | haiku | 2 | No, legacy_refund is unused. | yes | 0 | 4.4 s |
| 06-dead-code | graph | sonnet | 1 | No, only its definition exists; nothing calls or references it. | yes | 1 | 6.0 s |
| 06-dead-code | graph | sonnet | 2 | No, it's defined in backend/refunds/legacy.py but nothing uses it. | yes | 1 | 5.6 s |
| 07-name-collision | search | haiku | 1 | validate (from backend.refunds.rules) | yes | 3 | 7.2 s |
| 07-name-collision | search | haiku | 2 | validate (from .rules module) | yes | 2 | 5.6 s |
| 07-name-collision | search | sonnet | 1 | validate from backend/refunds/rules.py (imported via `.rules`) | yes | 2 | 6.5 s |
| 07-name-collision | search | sonnet | 2 | `validate(refund)` from `backend/refunds/rules.py` | yes | 3 | 5.1 s |
| 07-name-collision | graph | haiku | 1 | backend.refunds.rules.validate | yes | 0 | 6.0 s |
| 07-name-collision | graph | haiku | 2 | backend.refunds.rules.validate | yes | 0 | 4.8 s |
| 07-name-collision | graph | sonnet | 1 | backend.refunds.rules.validate | yes | 0 | 2.8 s |
| 07-name-collision | graph | sonnet | 2 | backend.refunds.rules.validate | yes | 0 | 5.6 s |
| 08-code-against-policy | search | haiku | 1 | No, they don't match. Code has £250 threshold, policy requires £500. | yes | 6 | 10.2 s |
| 08-code-against-policy | search | haiku | 2 | No, they don't match. Code uses £250 but policy requires £500. | yes | 7 | 11.5 s |
| 08-code-against-policy | search | sonnet | 1 | No. Backend uses £250 (old 2024 policy), current policy says £500. | yes | 3 | 7.6 s |
| 08-code-against-policy | search | sonnet | 2 | No — backend uses £250 (old Director policy); policy and frontend use £500 (Ops Manager) | yes | 3 | 6.7 s |
| 08-code-against-policy | graph | haiku | 1 | No, the backend threshold (£250) is misaligned with the policy (£500), while the frontend matches the policy. | yes | 0 | 8.4 s |
| 08-code-against-policy | graph | haiku | 2 | No, backend threshold (£250) doesn't match policy (£500). Also mismatches frontend (£500). | yes | 0 | 8.4 s |
| 08-code-against-policy | graph | sonnet | 1 | No — backend threshold is £250, policy (and frontend) say £500 | yes | 0 | 5.4 s |
| 08-code-against-policy | graph | sonnet | 2 | No — backend threshold is £250; policy and frontend say £500. | yes | 0 | 4.7 s |
| 09-frontend-against-backend | search | haiku | 1 | No, they disagree — backend is 250 GBP, frontend is 500 | yes | 5 | 13.2 s |
| 09-frontend-against-backend | search | haiku | 2 | No, frontend uses 500, backend uses 250. | yes | 8 | 14.3 s |
| 09-frontend-against-backend | search | sonnet | 1 | No — backend uses £250 (outdated), frontend uses £500 (matches current policy) | yes | 1 | 5.3 s |
| 09-frontend-against-backend | search | sonnet | 2 | No — frontend uses £500 (current policy), backend still uses £250 (superseded 2024 policy) | yes | 2 | 6.8 s |
| 09-frontend-against-backend | graph | haiku | 1 | No, they disagree—frontend uses 500, backend uses 250. | yes | 0 | 6.4 s |
| 09-frontend-against-backend | graph | haiku | 2 | No, frontend (500) and backend (250 GBP) disagree. | yes | 0 | 6.0 s |
| 09-frontend-against-backend | graph | sonnet | 1 | No — frontend 500, backend 250 GBP | yes | 0 | 4.1 s |
| 09-frontend-against-backend | graph | sonnet | 2 | No. The frontend uses 500 and the backend uses 250. | yes | 0 | 4.5 s |
| 10-identifier-styles | search | haiku | 1 | Defined in frontend/src/api.ts, holds `/api/refunds` | yes | 7 | 13.0 s |
| 10-identifier-styles | search | haiku | 2 | frontend/src/api.ts line 3; URL is `/api/refunds` | yes | 5 | 13.1 s |
| 10-identifier-styles | search | sonnet | 1 | `REFUNDS_URL` in `frontend/src/api.ts:3`, which holds `/api/refunds` | yes | 5 | 8.1 s |
| 10-identifier-styles | search | sonnet | 2 | `REFUNDS_URL` in frontend/src/api.ts:3 = `/api/refunds` | yes | 5 | 6.3 s |
| 10-identifier-styles | graph | haiku | 1 | REFUNDS_URL is in frontend/src/api.ts and holds `/api/refunds` | yes | 0 | 5.9 s |
| 10-identifier-styles | graph | haiku | 2 | REFUNDS_URL is in frontend/src/api.ts and holds "/api/refunds" | yes | 0 | 5.2 s |
| 10-identifier-styles | graph | sonnet | 1 | `REFUNDS_URL` in `frontend/src/api.ts`, equal to `/api/refunds` | yes | 0 | 3.3 s |
| 10-identifier-styles | graph | sonnet | 2 | `REFUNDS_URL` in frontend/src/api.ts, holding `/api/refunds` (`${API_BASE}/refunds`) | yes | 0 | 2.7 s |
| 11-claims-question | search | haiku | 1 | Any support agent (no manager approval needed for amounts under £500) | yes | 5 | 11.1 s |
| 11-claims-question | search | haiku | 2 | Any support agent (no special approval needed for amounts under £500) | yes | 4 | 9.7 s |
| 11-claims-question | search | sonnet | 1 | No approval needed; any support agent (approval is only for refunds over £500, by the Ops Manager) | yes | 1 | 5.9 s |
| 11-claims-question | search | sonnet | 2 | No one special. A support agent can process it, because it's under the £500 Ops Manager threshold. | yes | 1 | 3.5 s |
| 11-claims-question | graph | haiku | 1 | Any support agent can process a £300 refund directly (no manager approval needed). | yes | 0 | 4.3 s |
| 11-claims-question | graph | haiku | 2 | Any support agent can process it (no manager approval needed) | yes | 0 | 4.5 s |
| 11-claims-question | graph | sonnet | 1 | No approval needed. Any support agent can process it, because it's under £500. | yes | 0 | 2.9 s |
| 11-claims-question | graph | sonnet | 2 | No approval needed; any support agent can process it, since it's under £500. | yes | 0 | 3.1 s |
| 12-add-argument * | search | haiku | 1 | All 4 call sites and 2 tests need currency passed; reports.py needs refactoring for filter usage. | yes | 7 | 17.8 s |
| 12-add-argument * | search | haiku | 2 | Update 3 call sites, fix the filter usage in reports, update tests, and add currency-specific threshold logic to the function. | yes | 7 | 15.0 s |
| 12-add-argument * | search | sonnet | 1 | Update the callers in views.py, service.py and reports.py (which passes it to `filter`), the tests, and the frontend. Add currency conversion, and fix the stale 250 threshold. | yes | 7 | 13.3 s |
| 12-add-argument * | search | sonnet | 2 | Update the callers in views.py, orders/service.py, reports.py and the tests, plus rules.py, config.py, the frontend and the docs. | yes | 8 | 15.6 s |
| 12-add-argument * | graph | haiku | 1 | Config needs dict by currency, 4 call sites need currency arg, reports needs filter refactoring. | yes | 6 | 18.4 s |
| 12-add-argument * | graph | haiku | 2 | Update 6 files—rules.py function signature, config thresholds dict, 4 call sites (orders/service, refunds/views, both tests), and reports.py filter refactoring | yes | 7 | 18.8 s |
| 12-add-argument * | graph | sonnet | 1 | Update callers in views.py, orders/service.py, reports.py (filter call), tests, plus config threshold and frontend payloads | yes | 0 | 11.0 s |
| 12-add-argument * | graph | sonnet | 2 | Update the 3 callers (create_refund, process_refund, count_large's filter), the tests, the two frontend API calls, and convert to GBP inside needs_approval. | yes | 0 | 9.9 s |
| 13-rename * | search | haiku | 1 | 6 files need to change: backend\orders\service.py, backend\reports.py, backend\tests\test_rules.py, backend\refunds\__init__.py, backend\refunds\views.py, and backend\refunds\rules.py | yes | 1 | 4.9 s |
| 13-rename * | search | haiku | 2 | 6 files need to change: backend\orders\service.py, backend\reports.py, backend\tests\test_rules.py, backend\refunds\__init__.py, backend\refunds\views.py, backend\refunds\rules.py | yes | 1 | 4.9 s |
| 13-rename * | search | sonnet | 1 | 6 files: refunds/rules.py, refunds/__init__.py, refunds/views.py, orders/service.py, reports.py, tests/test_rules.py | yes | 3 | 7.9 s |
| 13-rename * | search | sonnet | 2 | 7 backend files: refunds/rules.py, refunds/__init__.py, reports.py, refunds/views.py, orders/service.py, tests/test_rules.py (plus none in frontend) | yes | 3 | 10.4 s |
| 13-rename * | graph | haiku | 1 | 6 files (rules.py, orders/service.py, refunds/__init__.py, refunds/views.py, reports.py, tests/test_rules.py) | yes | 0 | 7.1 s |
| 13-rename * | graph | haiku | 2 | 6 files (rules definition + 5 files that import/call it) | yes | 0 | 7.6 s |
| 13-rename * | graph | sonnet | 1 | 6 files: refunds/rules.py, refunds/__init__.py, refunds/views.py, orders/service.py, reports.py, tests/test_rules.py | yes | 1 | 9.7 s |
| 13-rename * | graph | sonnet | 2 | rules.py, refunds/__init__.py, refunds/views.py, orders/service.py, reports.py, tests/test_rules.py | yes | 1 | 7.2 s |
| 14-body-contract * | search | haiku | 1 | RefundForm.tsx and api.ts (add reason input and pass it in the request) | yes | 6 | 12.9 s |
| 14-body-contract * | search | haiku | 2 | RefundForm.tsx (add reason input) and api.ts (pass reason to request body) | yes | 11 | 21.9 s |
| 14-body-contract * | search | sonnet | 1 | `frontend/src/api.ts` (`submitRefund`) and `frontend/src/components/RefundForm.tsx` | yes | 7 | 13.8 s |
| 14-body-contract * | search | sonnet | 2 | `frontend/src/api.ts` (`submitRefund`) and `frontend/src/components/RefundForm.tsx` | yes | 12 | 18.7 s |
| 14-body-contract * | graph | haiku | 1 | frontend/src/api.ts (submitRefund function) and frontend/src/components/RefundForm.tsx (RefundForm component) | yes | 0 | 6.9 s |
| 14-body-contract * | graph | haiku | 2 | frontend/src/api.ts (submitRefund function) and frontend/src/components/RefundForm.tsx (add reason input) | yes | 12 | 38.7 s |
| 14-body-contract * | graph | sonnet | 1 | frontend/src/api.ts (submitRefund body) and frontend/src/components/RefundForm.tsx (reason input) | yes | 0 | 5.1 s |
| 14-body-contract * | graph | sonnet | 2 | frontend/src/api.ts (submitRefund) and frontend/src/components/RefundForm.tsx | yes | 7 | 14.9 s |
| 15-callee-side * | search | haiku | 1 | Added `is_staff` check to skip approval for staff refunds | NO | 20 | 36.2 s |
| 15-callee-side * | search | haiku | 2 | Added is_staff check to skip approval queue | NO | 26 | 48.0 s |
| 15-callee-side * | search | sonnet | 1 | No change made yet; need a trusted way to identify staff and confirmation of the policy exception. | yes | 9 | 14.6 s |
| 15-callee-side * | search | sonnet | 2 | Not changed (Edit disabled); proposed skipping the approval check on an `is_staff` flag, which needs real auth. | NO | 11 | 15.7 s |
| 15-callee-side * | graph | haiku | 1 | Modified process_refund to check payload.get("is_staff") and skip approval if true | NO | 9 | 28.6 s |
| 15-callee-side * | graph | haiku | 2 | Added is_staff check to skip approval for staff refunds. | NO | 14 | 35.4 s |
| 15-callee-side * | graph | sonnet | 1 | Not changed yet; need to know how staff is identified and whether there's an amount cap | yes | 2 | 8.3 s |
| 15-callee-side * | graph | sonnet | 2 | Not changed; no server-side staff identity exists, so I need to know where to get it. | yes | 3 | 11.0 s |
| 16-lookup-table | search | haiku | 1 | handle_bulk | NO | 4 | 11.1 s |
| 16-lookup-table | search | haiku | 2 | handle_bulk() | NO | 5 | 13.4 s |
| 16-lookup-table | search | sonnet | 1 | `cancel_order` (from `backend/orders/service`), called per order by `handle_bulk` at POST `/api/bulk` | yes | 4 | 6.7 s |
| 16-lookup-table | search | sonnet | 2 | `cancel_order`, called from `handle_bulk` (POST /api/bulk) in `backend/orders/views.py` | yes | 5 | 8.5 s |
| 16-lookup-table | graph | haiku | 1 | backend.orders.service.cancel_order | yes | 0 | 5.8 s |
| 16-lookup-table | graph | haiku | 2 | backend.orders.views.handle_bulk dispatches to backend.orders.service.cancel_order | yes | 0 | 8.2 s |
| 16-lookup-table | graph | sonnet | 1 | backend.orders.service.cancel_order (via handle_bulk) | yes | 0 | 3.1 s |
| 16-lookup-table | graph | sonnet | 2 | cancel_order (backend/orders/service.py), dispatched via handle_bulk | yes | 0 | 2.6 s |
