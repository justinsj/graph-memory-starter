---
description: Review the project changes waiting, and apply or reject each
allowed-tools: Bash(python:*)
---
Paths below are relative to the memory starter's folder (the one holding
projects/ and src/); from anywhere else, put that folder in front of them.

1. Run `python projects/review.py`. It lists what is waiting.
2. For each, run `python projects/review.py <name>` and show me the review as
   it prints it.
3. Ask me: apply, reject, or leave it for later.
   - apply: `python projects/review.py <name> --apply`, adding --yes only when
     I have confirmed the changes listed under "Needs your confirmation"
   - reject: `python projects/review.py <name> --reject`
4. Never edit projects/records/ yourself. If a change is nearly right, reject
   it and tell me what the input would need to say.
