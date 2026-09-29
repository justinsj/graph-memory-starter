---
description: Agree a step-by-step plan for a project with me, then record it
argument-hint: <project id>
allowed-tools: Bash(python:*), Read, Grep, Glob, Write
---
We are going to agree a plan for the project $ARGUMENTS. Paths below are
relative to the memory starter's folder (the one holding projects/ and src/);
from anywhere else, put that folder in front of them.

1. Load it: `python projects/board.py $ARGUMENTS`. That prints the project as
   it stands, its open questions and what needs a look.

2. Research before you ask me anything, so you only ask what you cannot find.
   - Memory first: `python src/recall.py "<question>"` for each owner,
     dependency and policy the project names, and `python rag/search.py
     "<question>"` over my notes.
   - Then documents and code, read only (Read, Grep, Glob), for what memory
     does not cover: what the work touches, what it depends on, who has done it
     before.
   - At most 20 tool calls. If you stop short, say what you did not check.
   - Keep each finding as a file path and a quote copied word for word.

3. Ask me every open question in one message: the project's own, and what
   research left open. Say what you found in a line or two. Wait for my answer.

4. Draft the plan and show it to me: numbered steps, each with an owner (a full
   name the project or the graph already uses, or one I give you), a due date
   only when one was agreed, the earlier steps it waits for, and the deliverable
   (D1, D2 ...) it produces, if any. Change it until I say it is agreed. Do not
   treat silence or "looks fine so far" as agreement.

5. Only once I have agreed it, write discussion.json in a scratch folder, in
   the format at the top of projects/plan.py:
   - asked: your questions; answered: my answers, word for word
   - found: your findings (doc and quote); steps: the plan as agreed
   - approved: my words agreeing it, word for word
   - changes: what my answers settle, each quoting my words: owner and due
     (set_field), questions answered (close_question and add_decision)

6. Run `python projects/plan.py $ARGUMENTS <that file>`. If it refuses, fix
   what it names and run it again; if the fix changes the plan, ask me first.
   Show me what it recorded, in a few lines.
