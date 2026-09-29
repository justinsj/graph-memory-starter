# Live eval: questions about projects, search against graph

Run 2026-09-28 10:43. Made by `python bench/project_eval.py --regrade`. Today pinned to 2026-09-28. Both folders hold the repo's documents, the inputs the story's two projects were built from, and the CLAUDE.md rule; the graph condition adds the graph hook.

| Model | Condition | Correct | Runs that searched | Tool calls | Average time | First answer word | First-request tokens | Cost per question |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| haiku | search | 10 of 16 | 13 of 16 | 51 | 10.3 s | 9.4 s | 9,431 | $0.0127 |
| haiku | graph | 16 of 16 | 0 of 16 | 0 | 4.4 s | 3.6 s | 10,155 | $0.0048 |
| sonnet | search | 12 of 16 | 15 of 16 | 49 | 9.1 s | 7.9 s | 12,339 | $0.0236 |
| sonnet | graph | 16 of 16 | 0 of 16 | 0 | 3.6 s | 2.4 s | 13,274 | $0.0093 |

| # | Question | Expected | Condition | Model | Rep | Answer | Correct | Tool calls | Time |
| ---: | --- | --- | --- | --- | ---: | --- | --- | ---: | ---: |
| 1 | What's the status of the helpdesk migration? | blocked | search | haiku | 1 | Blocked pending founder's contract signature (returns 10/12) | yes | 5 | 14.4 s |
| 1 | What's the status of the helpdesk migration? | blocked | search | haiku | 2 | Blocked; awaiting founder's contract signature until October 12. | yes | 4 | 12.8 s |
| 1 | What's the status of the helpdesk migration? | blocked | search | sonnet | 1 | No information available on a helpdesk migration. | NO | 1 | 8.2 s |
| 1 | What's the status of the helpdesk migration? | blocked | search | sonnet | 2 | No information available on this. | NO | 0 | 3.6 s |
| 1 | What's the status of the helpdesk migration? | blocked | graph | haiku | 1 | Blocked at step 3 (Founder signature pending); 2 of 5 steps done; due January 4, 2027. | yes | 0 | 5.0 s |
| 1 | What's the status of the helpdesk migration? | blocked | graph | haiku | 2 | Blocked on Founder contract signature; 2 of 5 steps done | yes | 0 | 5.1 s |
| 1 | What's the status of the helpdesk migration? | blocked | graph | sonnet | 1 | Blocked — waiting on Founder Alex Doyle's contract sign-off (step 3 of 5). | yes | 0 | 4.0 s |
| 1 | What's the status of the helpdesk migration? | blocked | graph | sonnet | 2 | Blocked — waiting on Founder Alex Doyle to sign the contract (step 3 of 5). | yes | 0 | 3.4 s |
| 2 | Who has to sign off the helpdesk contract? | Alex Doyle, the Founder | search | haiku | 1 | Alex Doyle (the Founder) signs the contract | yes | 4 | 8.1 s |
| 2 | Who has to sign off the helpdesk contract? | Alex Doyle, the Founder | search | haiku | 2 | The founder (Alex Doyle) signs off the helpdesk contract. | yes | 2 | 5.8 s |
| 2 | Who has to sign off the helpdesk contract? | Alex Doyle, the Founder | search | sonnet | 1 | Alex Doyle (the founder) | yes | 3 | 10.5 s |
| 2 | Who has to sign off the helpdesk contract? | Alex Doyle, the Founder | search | sonnet | 2 | Alex Doyle (Founder) | yes | 2 | 8.7 s |
| 2 | Who has to sign off the helpdesk contract? | Alex Doyle, the Founder | graph | haiku | 1 | Alex Doyle, the Founder | yes | 0 | 3.8 s |
| 2 | Who has to sign off the helpdesk contract? | Alex Doyle, the Founder | graph | haiku | 2 | Alex Doyle (Founder) | yes | 0 | 4.3 s |
| 2 | Who has to sign off the helpdesk contract? | Alex Doyle, the Founder | graph | sonnet | 1 | Alex Doyle (the Founder) | yes | 0 | 2.9 s |
| 2 | Who has to sign off the helpdesk contract? | Alex Doyle, the Founder | graph | sonnet | 2 | Alex Doyle (the Founder) | yes | 0 | 2.6 s |
| 3 | What's the next step on the helpdesk migration, and who has it? | step 3, the contract: Alex Doyle | search | haiku | 1 | Founder contract signature (Alex Doyle); blocked until Oct 12 | yes | 4 | 16.2 s |
| 3 | What's the next step on the helpdesk migration, and who has it? | step 3, the contract: Alex Doyle | search | haiku | 2 | No helpdesk migration context found — need more details | NO | 1 | 6.8 s |
| 3 | What's the next step on the helpdesk migration, and who has it? | step 3, the contract: Alex Doyle | search | sonnet | 1 | Alex Doyle needs to sign the contract, blocked until he returns Oct 12 | yes | 6 | 12.2 s |
| 3 | What's the next step on the helpdesk migration, and who has it? | step 3, the contract: Alex Doyle | search | sonnet | 2 | Next step is Alex Doyle signing the contract, but it's blocked until he's back Oct 12. | yes | 5 | 9.5 s |
| 3 | What's the next step on the helpdesk migration, and who has it? | step 3, the contract: Alex Doyle | graph | haiku | 1 | Step 3 (Founder contract sign-off) belongs to Alex Doyle, but is blocked waiting for him. | yes | 0 | 5.6 s |
| 3 | What's the next step on the helpdesk migration, and who has it? | step 3, the contract: Alex Doyle | graph | haiku | 2 | Step 3 (contract signature) with Alex Doyle, currently blocked | yes | 0 | 5.9 s |
| 3 | What's the next step on the helpdesk migration, and who has it? | step 3, the contract: Alex Doyle | graph | sonnet | 1 | Step 3 (Founder signs contract) — Alex Doyle, currently blocked | yes | 0 | 5.3 s |
| 3 | What's the next step on the helpdesk migration, and who has it? | step 3, the contract: Alex Doyle | graph | sonnet | 2 | Next step: founder contract signature, blocked on Alex Doyle | yes | 0 | 5.5 s |
| 4 | Is anything blocked right now? | the helpdesk migration | search | haiku | 1 | No blockers detected | NO | 0 | 4.8 s |
| 4 | Is anything blocked right now? | the helpdesk migration | search | haiku | 2 | No blockers detected. | NO | 0 | 4.3 s |
| 4 | Is anything blocked right now? | the helpdesk migration | search | sonnet | 1 | No information available — nothing recorded as blocked. | NO | 1 | 4.0 s |
| 4 | Is anything blocked right now? | the helpdesk migration | search | sonnet | 2 | No blockers known — no data available. | NO | 1 | 4.0 s |
| 4 | Is anything blocked right now? | the helpdesk migration | graph | haiku | 1 | Helpdesk migration blocked; waiting for founder's contract signature | yes | 0 | 4.3 s |
| 4 | Is anything blocked right now? | the helpdesk migration | graph | haiku | 2 | Helpdesk migration blocked on founder signature from Alex Doyle | yes | 0 | 4.2 s |
| 4 | Is anything blocked right now? | the helpdesk migration | graph | sonnet | 1 | Helpdesk migration blocked on Alex Doyle's contract signature | yes | 0 | 3.0 s |
| 4 | Is anything blocked right now? | the helpdesk migration | graph | sonnet | 2 | Helpdesk migration blocked, awaiting Alex Doyle's contract signature. | yes | 0 | 3.0 s |
| 5 | What was the status of the helpdesk migration on 20 September? | active | search | haiku | 1 | Helpdesk migration shortlist was being prepared (due Sept 23). | yes | 7 | 17.6 s |
| 5 | What was the status of the helpdesk migration on 20 September? | active | search | haiku | 2 | Shortlist creation in progress, due Sept 23. | yes | 6 | 20.0 s |
| 5 | What was the status of the helpdesk migration on 20 September? | active | search | sonnet | 1 | Still in shortlisting phase; Marcus Webb working toward the 23 Sep shortlist deadline, no blockers yet. | yes | 7 | 18.4 s |
| 5 | What was the status of the helpdesk migration on 20 September? | active | search | sonnet | 2 | No entry for 20 Sept; migration was still in shortlisting phase (due 23 Sept, completed by 24 Sept) | yes | 5 | 14.5 s |
| 5 | What was the status of the helpdesk migration on 20 September? | active | graph | haiku | 1 | Active, with plan agreed to proceed. | yes | 0 | 4.3 s |
| 5 | What was the status of the helpdesk migration on 20 September? | active | graph | haiku | 2 | Active (ongoing between start on 15 Sept and end on 25 Sept) | yes | 0 | 3.9 s |
| 5 | What was the status of the helpdesk migration on 20 September? | active | graph | sonnet | 1 | Active/in progress (approved 15 Sep, running through 25 Sep, owned by Priya Patel) | yes | 0 | 3.1 s |
| 5 | What was the status of the helpdesk migration on 20 September? | active | graph | sonnet | 2 | Active/in progress (approved, owned by Priya Patel, running 2026-09-15 to 2026-09-25) | yes | 0 | 3.2 s |
| 6 | What does the refunds dashboard depend on? | the helpdesk migration | search | haiku | 1 | The new helpdesk and ticket data from it. | yes | 3 | 7.0 s |
| 6 | What does the refunds dashboard depend on? | the helpdesk migration | search | haiku | 2 | The new helpdesk system being live and ticket data from it. | yes | 6 | 14.5 s |
| 6 | What does the refunds dashboard depend on? | the helpdesk migration | search | sonnet | 1 | It depends on the new helpdesk going live (ticket data migration). | yes | 3 | 6.2 s |
| 6 | What does the refunds dashboard depend on? | the helpdesk migration | search | sonnet | 2 | It depends on the new helpdesk migration (ticket data moving to it) before the dashboard can be built. | yes | 2 | 10.7 s |
| 6 | What does the refunds dashboard depend on? | the helpdesk migration | graph | haiku | 1 | The Helpdesk migration | yes | 0 | 3.9 s |
| 6 | What does the refunds dashboard depend on? | the helpdesk migration | graph | haiku | 2 | Helpdesk migration | yes | 0 | 3.7 s |
| 6 | What does the refunds dashboard depend on? | the helpdesk migration | graph | sonnet | 1 | The Helpdesk migration (currently blocked) | yes | 0 | 3.3 s |
| 6 | What does the refunds dashboard depend on? | the helpdesk migration | graph | sonnet | 2 | The Helpdesk migration (currently blocked) | yes | 0 | 4.6 s |
| 7 | What did we decide about the old helpdesk? | read-only for 90 days, then closed | search | haiku | 1 | No prior memory found about helpdesk decision. | NO | 1 | 5.5 s |
| 7 | What did we decide about the old helpdesk? | read-only for 90 days, then closed | search | haiku | 2 | No memory exists of this decision. | NO | 1 | 5.6 s |
| 7 | What did we decide about the old helpdesk? | read-only for 90 days, then closed | search | sonnet | 1 | Keep it read-only for 90 days post-go-live, then close it. | yes | 2 | 7.1 s |
| 7 | What did we decide about the old helpdesk? | read-only for 90 days, then closed | search | sonnet | 2 | Keep old helpdesk read-only 90 days post go-live, then close it. | yes | 3 | 9.6 s |
| 7 | What did we decide about the old helpdesk? | read-only for 90 days, then closed | graph | haiku | 1 | Keep read-only for 90 days after go-live, then close. | yes | 0 | 3.6 s |
| 7 | What did we decide about the old helpdesk? | read-only for 90 days, then closed | graph | haiku | 2 | Keep read-only for 90 days after go-live, then close it. | yes | 0 | 4.1 s |
| 7 | What did we decide about the old helpdesk? | read-only for 90 days, then closed | graph | sonnet | 1 | Keep it read-only for 90 days post go-live, then close. | yes | 0 | 3.0 s |
| 7 | What did we decide about the old helpdesk? | read-only for 90 days, then closed | graph | sonnet | 2 | Keep it read-only for 90 days post go-live, then close it. | yes | 0 | 2.8 s |
| 8 | Which projects is Marcus working on? | the helpdesk migration | search | haiku | 1 | Helpdesk migration project and delegated operational approvals. | yes | 7 | 15.0 s |
| 8 | Which projects is Marcus working on? | the helpdesk migration | search | haiku | 2 | No information available without context or project tracking system access. | NO | 0 | 6.1 s |
| 8 | Which projects is Marcus working on? | the helpdesk migration | search | sonnet | 1 | Marcus Webb is working on the helpdesk migration (shortlisting/integration checks) and covering Sarah Chen's approvals during her March leave. | yes | 2 | 7.2 s |
| 8 | Which projects is Marcus working on? | the helpdesk migration | search | sonnet | 2 | Marcus Webb is working on the helpdesk migration (shortlisting/integration checks) and holds delegated approval authority during Sarah's leave. | yes | 6 | 10.6 s |
| 8 | Which projects is Marcus working on? | the helpdesk migration | graph | haiku | 1 | Helpdesk migration (2 of 5 steps complete) | yes | 0 | 4.0 s |
| 8 | Which projects is Marcus working on? | the helpdesk migration | graph | haiku | 2 | Helpdesk migration | yes | 0 | 4.8 s |
| 8 | Which projects is Marcus working on? | the helpdesk migration | graph | sonnet | 1 | Marcus is working on the Helpdesk migration project. | yes | 0 | 4.3 s |
| 8 | Which projects is Marcus working on? | the helpdesk migration | graph | sonnet | 2 | Helpdesk migration | yes | 0 | 3.4 s |
