Read the document below. Extract a knowledge graph using ONLY this vocabulary.

Entity types: PERSON, ROLE, POLICY, PROCESS, DOCUMENT
Relationships: approved_by, held_by, delegates_to, part_of, references
Claim kinds: threshold, deadline, availability, unknown, responsibility, rule, note

Return JSON:
{"source_doc": "...",
 "nodes": [{"name", "type",
            "claims": [{"kind", "text", "quote", "amount"?, "unit"?, "valid_from"?, "valid_to"?}]}],
 "edges": [{"source", "predicate", "target", "valid_from"?, "valid_to"?}],
 "aliases": [{"entity", "alias"}]}

Rules:
- Use the most complete form of each name. Add short forms as aliases.
- Each claim is one fact about its node, as one plain sentence: conditions,
  amounts, time windows. A money limit is a threshold claim with its amount
  and unit ("GBP").
- Each claim has a quote: the shortest passage of the document that states
  it, copied word for word (markdown such as ** may be left out), at most 300
  characters. The build checks every quote against the document.
- When the document leaves something open that a reader would ask about, say
  so in an unknown claim, e.g. a role it names but no person for:
  "The 2024 refund policy names no person for the Director role".
- Dates are YYYY-MM-DD. valid_from is the first day a claim or link holds;
  valid_to is the first day it no longer holds. "Superseded on 1 January 2026"
  gives valid_to 2026-01-01; "on leave 1 to 31 March 2026" gives valid_from
  2026-03-01 and valid_to 2026-04-01. Leave out a date the document does not
  state; never guess a year.
- Extract only facts stated in the document.
- Every edge endpoint must appear in nodes, or in another document's nodes.
