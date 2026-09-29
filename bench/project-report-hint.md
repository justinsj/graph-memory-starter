# Live eval: questions about projects, search against graph

Run 2026-09-28 10:45. Made by `python bench/project_eval.py --hint --models haiku,sonnet --reps 2 --jobs 4`. Every prompt starts "Our company docs are in this folder.". Today pinned to 2026-09-28. Both folders hold the repo's documents, the inputs the story's two projects were built from, and the CLAUDE.md rule; the graph condition adds the graph hook.

| Model | Condition | Correct | Runs that searched | Tool calls | Average time | First answer word | First-request tokens | Cost per question |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| haiku | search | 13 of 16 | 16 of 16 | 70 | 12.5 s | 11.4 s | 9,442 | $0.0158 |
| haiku | graph | 16 of 16 | 0 of 16 | 0 | 5.1 s | 4.2 s | 10,163 | $0.0052 |
| sonnet | search | 16 of 16 | 16 of 16 | 72 | 11.5 s | 9.7 s | 12,350 | $0.0312 |
| sonnet | graph | 16 of 16 | 0 of 16 | 0 | 4.0 s | 2.7 s | 13,284 | $0.0099 |

| # | Question | Expected | Condition | Model | Rep | Answer | Correct | Tool calls | Time |
| ---: | --- | --- | --- | --- | ---: | --- | --- | ---: | ---: |
| 1 | What's the status of the helpdesk migration? | blocked | search | haiku | 1 | Blocked, waiting for founder to return and sign contract (Oct 12) | yes | 3 | 10.2 s |
| 1 | What's the status of the helpdesk migration? | blocked | search | haiku | 2 | Step 2 in progress; on track. | NO | 3 | 8.8 s |
| 1 | What's the status of the helpdesk migration? | blocked | search | sonnet | 1 | Blocked on contract sign-off (Alex back 12 Oct); shortlist/integration check done, go-live still pending. | yes | 4 | 11.7 s |
| 1 | What's the status of the helpdesk migration? | blocked | search | sonnet | 2 | Blocked on contract sign-off (Alex back 2026-10-12); shortlist and integration checks are done. | yes | 6 | 9.6 s |
| 1 | What's the status of the helpdesk migration? | blocked | graph | haiku | 1 | Blocked at step 3, waiting for Founder's contract signature. 2 of 5 steps done. | yes | 0 | 5.2 s |
| 1 | What's the status of the helpdesk migration? | blocked | graph | haiku | 2 | Blocked on Founder contract signature; 2/5 steps done | yes | 0 | 6.2 s |
| 1 | What's the status of the helpdesk migration? | blocked | graph | sonnet | 1 | Blocked — waiting on Founder Alex Doyle to sign the contract (step 3/5). | yes | 0 | 6.2 s |
| 1 | What's the status of the helpdesk migration? | blocked | graph | sonnet | 2 | Blocked — waiting on Founder's contract signature (step 3 of 5) | yes | 0 | 4.8 s |
| 2 | Who has to sign off the helpdesk contract? | Alex Doyle, the Founder | search | haiku | 1 | The founder (Alex Doyle) has to sign off the helpdesk contract. | yes | 4 | 7.7 s |
| 2 | Who has to sign off the helpdesk contract? | Alex Doyle, the Founder | search | haiku | 2 | Alex Doyle (Founder) | yes | 5 | 11.3 s |
| 2 | Who has to sign off the helpdesk contract? | Alex Doyle, the Founder | search | sonnet | 1 | Alex Doyle (the founder) | yes | 2 | 10.8 s |
| 2 | Who has to sign off the helpdesk contract? | Alex Doyle, the Founder | search | sonnet | 2 | Alex Doyle (Founder) — required for contracts over £2,000 | yes | 3 | 12.5 s |
| 2 | Who has to sign off the helpdesk contract? | Alex Doyle, the Founder | graph | haiku | 1 | Alex Doyle, the Founder | yes | 0 | 4.6 s |
| 2 | Who has to sign off the helpdesk contract? | Alex Doyle, the Founder | graph | haiku | 2 | Alex Doyle, the Founder | yes | 0 | 4.6 s |
| 2 | Who has to sign off the helpdesk contract? | Alex Doyle, the Founder | graph | sonnet | 1 | Alex Doyle (Founder) must sign off the helpdesk contract. | yes | 0 | 4.0 s |
| 2 | Who has to sign off the helpdesk contract? | Alex Doyle, the Founder | graph | sonnet | 2 | Alex Doyle (the Founder) | yes | 0 | 4.2 s |
| 3 | What's the next step on the helpdesk migration, and who has it? | step 3, the contract: Alex Doyle | search | haiku | 1 | Contract signature by Alex Doyle, blocked until they return October 12 | yes | 3 | 11.8 s |
| 3 | What's the next step on the helpdesk migration, and who has it? | step 3, the contract: Alex Doyle | search | haiku | 2 | Step 2 (check options against tooling inventory) is currently underway; Marcus Webb has it, due by 2 October. | NO | 3 | 9.4 s |
| 3 | What's the next step on the helpdesk migration, and who has it? | step 3, the contract: Alex Doyle | search | sonnet | 1 | Next step is contract sign-off, owned by Alex Doyle, blocked until he returns Oct 12 | yes | 4 | 10.8 s |
| 3 | What's the next step on the helpdesk migration, and who has it? | step 3, the contract: Alex Doyle | search | sonnet | 2 | Contract signing (Alex Doyle) — blocked until he returns Oct 12. | yes | 3 | 11.4 s |
| 3 | What's the next step on the helpdesk migration, and who has it? | step 3, the contract: Alex Doyle | graph | haiku | 1 | Step 3 is blocked on Alex Doyle; next available step is Step 4 (migration plan) for Priya Patel. | yes | 0 | 6.6 s |
| 3 | What's the next step on the helpdesk migration, and who has it? | step 3, the contract: Alex Doyle | graph | haiku | 2 | Step 3 (Founder contract signature) with Alex Doyle—currently blocked. | yes | 0 | 8.2 s |
| 3 | What's the next step on the helpdesk migration, and who has it? | step 3, the contract: Alex Doyle | graph | sonnet | 1 | Blocked on Alex Doyle signing the contract (step 3); Priya Patel owns the migration overall. | yes | 0 | 3.9 s |
| 3 | What's the next step on the helpdesk migration, and who has it? | step 3, the contract: Alex Doyle | graph | sonnet | 2 | Next step is the Founder's contract sign-off (Alex Doyle), currently blocked; overall owner is Priya Patel. | yes | 0 | 4.8 s |
| 4 | Is anything blocked right now? | the helpdesk migration | search | haiku | 1 | Helpdesk migration blocked (awaiting Alex's contract signature until 10/12) | yes | 4 | 10.1 s |
| 4 | Is anything blocked right now? | the helpdesk migration | search | haiku | 2 | Helpdesk migration blocked—waiting for Alex to sign contract (returns Oct 12) | yes | 4 | 12.5 s |
| 4 | Is anything blocked right now? | the helpdesk migration | search | sonnet | 1 | Yes — helpdesk migration blocked until Alex returns Oct 12. | yes | 4 | 9.7 s |
| 4 | Is anything blocked right now? | the helpdesk migration | search | sonnet | 2 | Helpdesk migration blocked — awaiting Alex's contract signature, back Oct 12. | yes | 4 | 9.1 s |
| 4 | Is anything blocked right now? | the helpdesk migration | graph | haiku | 1 | Helpdesk migration is blocked waiting for founder signature (Alex Doyle). | yes | 0 | 5.5 s |
| 4 | Is anything blocked right now? | the helpdesk migration | graph | haiku | 2 | Helpdesk migration blocked on founder's contract signature (Alex Doyle) | yes | 0 | 4.8 s |
| 4 | Is anything blocked right now? | the helpdesk migration | graph | sonnet | 1 | Helpdesk migration blocked on Alex Doyle's contract signature | yes | 0 | 4.0 s |
| 4 | Is anything blocked right now? | the helpdesk migration | graph | sonnet | 2 | Helpdesk migration blocked, awaiting Alex Doyle's contract signature. | yes | 0 | 2.7 s |
| 5 | What was the status of the helpdesk migration on 20 September? | active | search | haiku | 1 | In progress on shortlist (due Sept 23), no specific update from that date | yes | 14 | 44.2 s |
| 5 | What was the status of the helpdesk migration on 20 September? | active | search | haiku | 2 | Shortlist creation in progress, due Sept 23 | yes | 8 | 21.2 s |
| 5 | What was the status of the helpdesk migration on 20 September? | active | search | sonnet | 1 | Still in shortlisting phase (Marcus's shortlist wasn't due until 23 Sept, delivered 24 Sept) | yes | 7 | 18.3 s |
| 5 | What was the status of the helpdesk migration on 20 September? | active | search | sonnet | 2 | No record for 20 Sep; as of then the shortlist step (due 23 Sep) was still in progress, no blockers yet. | yes | 6 | 13.8 s |
| 5 | What was the status of the helpdesk migration on 20 September? | active | graph | haiku | 1 | Active (in progress from 2026-09-15 to 2026-09-25) | yes | 0 | 5.0 s |
| 5 | What was the status of the helpdesk migration on 20 September? | active | graph | haiku | 2 | Active (approved and underway) | yes | 0 | 4.1 s |
| 5 | What was the status of the helpdesk migration on 20 September? | active | graph | sonnet | 1 | Active/in progress (approved 15 Sep, running through 25 Sep, owned by Priya Patel) | yes | 0 | 3.6 s |
| 5 | What was the status of the helpdesk migration on 20 September? | active | graph | sonnet | 2 | Active (in progress), owned by Priya Patel | yes | 0 | 5.0 s |
| 6 | What does the refunds dashboard depend on? | the helpdesk migration | search | haiku | 1 | The new helpdesk being live (ticket data migration) | yes | 2 | 6.5 s |
| 6 | What does the refunds dashboard depend on? | the helpdesk migration | search | haiku | 2 | The new helpdesk system and ticket data from it | yes | 4 | 10.3 s |
| 6 | What does the refunds dashboard depend on? | the helpdesk migration | search | sonnet | 1 | The new helpdesk being live (ticket data migration); currently blocked on contract signature, due back 12 Oct, go-live 4 Jan 2027. | yes | 4 | 10.5 s |
| 6 | What does the refunds dashboard depend on? | the helpdesk migration | search | sonnet | 2 | The refunds dashboard depends on the new helpdesk migration (ticket data), which is currently blocked pending Alex's contract signature (back 12 Oct). | yes | 5 | 10.9 s |
| 6 | What does the refunds dashboard depend on? | the helpdesk migration | graph | haiku | 1 | Helpdesk migration | yes | 0 | 4.1 s |
| 6 | What does the refunds dashboard depend on? | the helpdesk migration | graph | haiku | 2 | Helpdesk migration | yes | 0 | 4.5 s |
| 6 | What does the refunds dashboard depend on? | the helpdesk migration | graph | sonnet | 1 | Helpdesk migration (currently blocked), which itself depends on the Tooling inventory. | yes | 0 | 4.9 s |
| 6 | What does the refunds dashboard depend on? | the helpdesk migration | graph | sonnet | 2 | Depends on the Helpdesk migration (currently blocked), which itself depends on the Tooling inventory. | yes | 0 | 3.4 s |
| 7 | What did we decide about the old helpdesk? | read-only for 90 days, then closed | search | haiku | 1 | Decision deferred; to be decided later whether to keep old helpdesk read-only after migration. | NO | 3 | 8.6 s |
| 7 | What did we decide about the old helpdesk? | read-only for 90 days, then closed | search | haiku | 2 | Keep read-only for 90 days after migration, then close. | yes | 4 | 9.5 s |
| 7 | What did we decide about the old helpdesk? | read-only for 90 days, then closed | search | sonnet | 1 | Keep it read-only 90 days after go-live, then close it. | yes | 6 | 10.5 s |
| 7 | What did we decide about the old helpdesk? | read-only for 90 days, then closed | search | sonnet | 2 | Keep it read-only for 90 days after go-live, then close it. | yes | 6 | 10.5 s |
| 7 | What did we decide about the old helpdesk? | read-only for 90 days, then closed | graph | haiku | 1 | Keep read-only for 90 days post-launch, then close. | yes | 0 | 4.6 s |
| 7 | What did we decide about the old helpdesk? | read-only for 90 days, then closed | graph | haiku | 2 | Keep old helpdesk read-only for 90 days after migration, then close it. | yes | 0 | 4.6 s |
| 7 | What did we decide about the old helpdesk? | read-only for 90 days, then closed | graph | sonnet | 1 | Keep it read-only 90 days post-launch, then close it. | yes | 0 | 2.3 s |
| 7 | What did we decide about the old helpdesk? | read-only for 90 days, then closed | graph | sonnet | 2 | Keep old helpdesk read-only 90 days post-go-live, then close it. | yes | 0 | 3.5 s |
| 8 | Which projects is Marcus working on? | the helpdesk migration | search | haiku | 1 | Helpdesk migration evaluation (shortlisting options and checking integrations) | yes | 3 | 9.4 s |
| 8 | Which projects is Marcus working on? | the helpdesk migration | search | haiku | 2 | Helpdesk migration project | yes | 3 | 8.9 s |
| 8 | Which projects is Marcus working on? | the helpdesk migration | search | sonnet | 1 | Marcus Webb is working on the helpdesk migration (shortlisting + tooling integration checks) | yes | 3 | 13.7 s |
| 8 | Which projects is Marcus working on? | the helpdesk migration | search | sonnet | 2 | Marcus Webb is leading the helpdesk migration (vendor shortlist + tooling integration check), now blocked on contract sign-off. | yes | 5 | 10.1 s |
| 8 | Which projects is Marcus working on? | the helpdesk migration | graph | haiku | 1 | Helpdesk migration (steps 1-2 complete, blocked on step 3) | yes | 0 | 4.2 s |
| 8 | Which projects is Marcus working on? | the helpdesk migration | graph | haiku | 2 | Helpdesk migration (steps 1-2 complete, currently blocked) | yes | 0 | 4.5 s |
| 8 | Which projects is Marcus working on? | the helpdesk migration | graph | sonnet | 1 | Marcus Webb is working on the Helpdesk migration project. | yes | 0 | 3.4 s |
| 8 | Which projects is Marcus working on? | the helpdesk migration | graph | sonnet | 2 | Marcus is working on the Helpdesk migration project. | yes | 0 | 3.4 s |
