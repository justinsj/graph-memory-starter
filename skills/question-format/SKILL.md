---
name: question-format
description: |
  Format every question asked of the user as a block: a `### Q<n>. <Short name>` heading, the question itself, then Context, Example, Options and Reply with, in that order. Use this whenever you are about to ask the user anything that needs a decision or a fact from them: a clarifying question in chat, an AskUserQuestion tool call, an AI-DLC `*-questions.md` file, a plan's open questions, or an "Open questions" section in a report or explainer. Triggers on "ask me", "clarify", "open questions", "which option", "need a decision", and any point where you are blocked on the user's input. Not for rhetorical questions inside prose, and not for questions the user asked you.
allowed-tools:
  - Read
  - Write
  - Edit
  - AskUserQuestion
---

# Question Format

The reader of these questions switches between many projects and will not remember the details of this one. Each question must stand on its own: someone opening it cold should understand what is being decided, why it matters, and what each answer would change, without scrolling back through the conversation.

Questions use the same block shape as decisions and problems (the `response-format` skill): an ID and a short name as the heading, then plain labeled bullets in a fixed order. A reader scanning a response finds the short name, the question, the options and how to reply in the same place every time.

## Before you ask: settle it yourself when you can

Most questions should not reach the user. Before you draft one, look for the answer in the order of authority that the preferences file gives (`preferences.md`, the file your CLAUDE.md names; in a standard install it sits next to the OpenSpec rules). Stop at the first source that settles it:

1. What the user said in the request or the conversation.
2. The project: AGENTS.md, convention docs, decision records, and what the code already does.
3. The user's standing rules: the CLAUDE.md files in scope and the user profile.
4. The preferences (P1, P2 and onward).
5. If it is still open: the option that is cheapest to reverse.

Ask only when one of these is true:

- The decision is one of the "Needs your yes" kinds in the OpenSpec `rules.md`: a production write, backfill, migration or DDL change; deleting or overwriting; notifying people or publishing, including a deploy to prod; a new recurring cost; a breaking change another team consumes; a change to permissions, grants, IAM roles or secrets.
- No source settles it, and you cannot rank the options.
- It needs a fact only the user knows.

Record every question you settle as a decision block (`response-format` skill) with `Source:` naming what settled it, such as `P1 Workaround instead of full refactor`, and show it under `## Decisions` so the user can override it with `D<n>: <other option>`. Never invent a fact to settle a question. When the code or data that would settle it cannot be read, say so in the decision and pick the option that is cheapest to reverse.

Some workflows keep their own question files, and the user's CLAUDE.md can exclude them from this step (for example AI-DLC `*-questions.md` files). Follow that exclusion.

## The parts (always in this order)

1. **Heading**: `### Q<n>. <Short name>`. The short name has two to five words. It is a noun phrase that names what is being decided (`Backfill scope`, `Retry limit`, `Auth method`), not the question. Use it every time the question is mentioned: `Q2 (Backfill scope)`.
2. **Question**: the next line. One sentence ending in a question mark. Ask one thing. If you need two decisions, write two questions.
3. **Context**: two to five sentences. Say what you are working on, what you found that raised the question, and what happens next depending on the answer. Name the file, table, ticket, client or number involved. Do not assume the reader remembers earlier messages.
4. **Example**: at least one concrete case that makes the question tangible. Use real data from the task when you have it (a client id, a row, a dollar amount, a file path, a code snippet). When options lead to different outcomes, show the same example under each option, as sub-bullets, so the reader can see the difference.
5. **Options**: two to five meaningful choices, lettered A, B, C... Each option gets a one-line consequence (what you will do, and the trade-off). Put your recommendation first and mark it "(Recommended)" with a short reason. The recommendation is the option the order of authority above picks, and its reason names the source or preference (`P2 Additive, not breaking`), not your own taste. End with an "Other" option. Do not invent filler options to reach a count.
6. **Reply with**: the short reply that answers it, such as `Q1: A`.
7. **Recorded in** (optional): the file that records the question, when the project keeps one file per question (for example under `docs/decisions/`).

## Layout in chat (plain markdown)

Labels are plain text, not bold, one per bullet.

```markdown
### Q1. Backfill scope

Should the revenue backfill include customers who closed their accounts before September?

- Context: The revenue backfill job reads `monthly_revenue` for every customer in `customers`. 37 of the 178 rows belong to customers who closed their accounts before 2026-09-01, so their data stops mid-year. Including them changes the benchmark averages; excluding them shrinks the sample.
- Example: Acme Widgets closed its account on 2026-08-02.
  - Under A, Acme Widgets is absent from August onward.
  - Under B, its August row shows 2 days of revenue ($4,120) and drags the August median down.
- Options:
  - A. Exclude closed accounts (Recommended): cleaner averages, sample drops from 178 to 141.
  - B. Include them as-is: full sample, partial months distort the medians.
  - C. Include them but drop their partial months: full sample for complete months, needs an extra filter.
  - D. Other: describe it in your reply.
- Reply with: `Q1: A`, or the letter you choose.
```

Several questions go under one `## Questions for you` section, at the end of the response (`response-format` skill), with the questions that block work first. Number them Q1, Q2... and keep the batch small (four or fewer) unless the user asked for a full questionnaire.

## Answers become decisions

When the user answers, record the answer as a decision block that keeps the question's short name:

```markdown
### D3. Backfill scope

- Decision: The backfill leaves out the 37 customers who closed their accounts before 2026-09-01.
- Reason: Their partial months pulled the August median down.
- Source: your answer to Q1 (Backfill scope) on 2026-10-22
```

Show it under `## Decisions` in the next response, and add it to any decisions file the work keeps (for example an OpenSpec `decisions.md`).

## Every reference stands on its own

A question block runs from the heading to the last line of Reply with. Everything inside it must make sense to a reader who sees only that block.

- **Labels carry a description.** Any id, number or label that points somewhere else (a task, step, ticket, question, unit, option, file section, PR) gets a short description in parentheses or beside it, every time it appears. Write `Task 1.1 (add the read-only DB connection helper)`, not `Task 1.1`. Write `TICKET-12 (invoice totals tie to the statement)`, not `TICKET-12`. Write `PR #102 (date parser fix)`, not `#102`. Write `Q2 (Backfill scope)`, not `Q2`.
- **"This", "that", "it", "these", "the above" must point inside the block.** The thing they refer to must be named earlier within the same question block. If the referent lives in an earlier message, another question, a plan file, or a previous turn, name it explicitly instead of using the pronoun.
  - Bad: `Should we ship this before the release?` (what is "this"?)
  - Good: `Should we ship the retry limit change (3→5) for the nightly import queue before the release?` Later lines in the block may then say "this change".
  - Bad Context: `As discussed above, this breaks the backfill.`
  - Good Context: `Raising the limit to 5 lets the nightly import finish before messages move to the dead-letter queue; without it, this import leaves about 1,200 messages there.`
- **No "see above", "as mentioned", "per the plan" without the content.** If the reader needs a fact, put the fact in the block.

## Layout with the AskUserQuestion tool

The tool only has fields for the question, a short header, and option label/description/preview. Fit the parts into it like this:

- Write the block in your chat message immediately before the tool call: the `### Q1. <Short name>` heading, the question, Context and Example. Leave out Options and Reply with, because the tool shows the options.
- `header`: the short name. The chip allows 12 characters, so shorten it if needed (`Backfill`, `Retry limit`), and keep the same word at the start as the chat heading.
- `question`: the one-sentence question.
- `options[].label`: the short choice name; the recommended one first with "(Recommended)".
- `options[].description`: the consequence and trade-off.
- `options[].preview`: use it to show the example under that option (a sample row, a snippet, a before/after) when options differ visibly.
- Do not add an "Other" option; the tool provides one.

## Layout in AI-DLC question files

AI-DLC files (`aidlc-docs/**/*-questions.md`) keep the structure from `common/question-format-guide.md` (lettered options as `A)` lines separated by blank lines, "Other" last, an `[Answer]:` tag). Add the short name to the heading, and put Context and Example between the question text and the options, as plain-label bullets:

```markdown
## Question 1: Auth method
Which authentication method should the onboarding portal use?

- Context: The portal is new and sits beside the existing company login. Whichever method we pick decides whether customers need a second password and whether IT must register a new single sign-on (SSO) app.
- Example: A customer who already signs in to the company site with SSO would, under A, create a second username and password; under B, they click "Sign in with your company account" and land on the portal.

A) Username and password: no IT work, but a second credential for customers.

B) Single Sign-On (Recommended): one login, needs an SSO app registration.

C) Multi-factor on top of username and password: stronger, more friction at sign-up.

X) Other (please describe after [Answer]: tag below)

[Answer]: 
```

## Checks before you send

- Does every question have a `### Q<n>. <Short name>` heading (or `## Question <n>: <Short name>` in an AI-DLC file), with the question on the next line?
- Are the labels plain, one per bullet, in the order Context, Example, Options, Reply with, Recorded in?
- Can someone read this question with no prior context and answer it? If not, add context.
- Does every label (Task 1.1, Q2, TICKET-12, PR #102, Unit 3) carry a short description next to it?
- Does every "this", "that", "it" or "the above" point to something named inside the same block?
- Is there a concrete example with real names or numbers from the task? Placeholder examples ("e.g. some value") do not count.
- Does each option say what will happen if chosen?
- Is the recommendation marked and justified in a few words?
- Did you run "Before you ask" first? If a source or a preference settles the question, do not ask. Record it as a decision block instead.
- For chat blocks saved to a file, run `python <response-format skill folder>/scripts/check_format.py --blocks-only <file>`.
- Writing follows the writing rules in your CLAUDE.md, if it has any.
