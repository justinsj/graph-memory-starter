## Memory

When a `memory:` block arrives with a prompt, answer from its facts and quoted
lines. The quoted lines are the documents' own words, checked against the files
when the prompt was sent. Open a document only when its line says it changed or
is missing, or when the facts do not cover the question.
