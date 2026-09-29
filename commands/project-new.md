---
description: Turn a request or a meeting transcript into proposed project changes
argument-hint: <the request in your words, or the path of a transcript>
allowed-tools: Bash(python:*), Write
---
Paths below are relative to the memory starter's folder (the one holding
projects/ and src/); from anywhere else, put that folder in front of them.

What I gave you: $ARGUMENTS

1. If it is the path of a transcript or notes file, use that file as it is,
   with --kind transcript.
   Otherwise it is a request: save it word for word as
   inputs/requests/<today, YYYY-MM-DD>-<a short slug>.md, under a first line
   "# Request from <who asked>, <today, e.g. 25 September 2026>". Ask me who it
   is from if you cannot tell. Use --kind request.

2. Run: `python projects/ingest.py <the file> --kind <kind>`

3. Show me the review it prints, as it is. Apply nothing. If I agree, run
   `python projects/review.py <name> --apply`, adding --yes only when I have
   confirmed the changes it lists under "Needs your confirmation".
