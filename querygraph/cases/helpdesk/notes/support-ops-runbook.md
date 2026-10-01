# Support ops runbook

Owner: Priya Nair, support lead · last reviewed 3 August 2026

## Our promises

- **Urgent**: a first reply from a person within one hour, 24/7, on both desks.
- **Everything else**: a first reply within one business day.

## Monthly: urgent first-reply report

Goes to the ops review on the first Tuesday of the month. The Enterprise desk also
gets its own copy for the account managers.

How it's counted:

- A ticket is in the month it **became urgent**: when it was created as urgent, or when
  someone raised it to urgent. The hour runs from that moment, not from when the ticket
  was opened. The field history has both, because it records the values a ticket was
  created with.
- It counts even if triage took it down a level later. Its priority now doesn't matter.
- If someone had already replied before it became urgent, it's left out: the first reply
  has happened.
- The first reply is the first **public** comment from a **person** on the team. The
  Support Bot's "we've got your request" acknowledgement isn't a reply, even though it
  posts from an agent seat, and internal notes aren't either.
- No reply at all counts as missed. If you sort it out on the phone, put a public reply
  on the ticket saying so.
- Merged tickets are left out (the ticket they were merged into carries the clock), and
  so is deleted spam.

The query, as run for the July report for the Enterprise desk:

```sql
-- Urgent first reply, Enterprise desk, July 2026
WITH became_urgent AS (
    SELECT ticket_id, MIN(changed_at) AS urgent_at
    FROM ticket_field_changes
    WHERE field = 'priority' AND new_value = 'urgent'
    GROUP BY ticket_id
),
first_human_reply AS (
    SELECT c.ticket_id, MIN(c.created_at) AS replied_at
    FROM ticket_comments c
    JOIN users u ON u.id = c.author_id
    WHERE c.public = 1 AND u.role IN ('agent', 'admin') AND c.via != 'rule'
    GROUP BY c.ticket_id
),
report AS (
    SELECT t.id, t.created_at, b.urgent_at, r.replied_at
    FROM tickets t
    JOIN became_urgent b ON b.ticket_id = t.id
    LEFT JOIN first_human_reply r ON r.ticket_id = t.id
    WHERE t.brand = 'enterprise'
      AND t.merged_into IS NULL AND t.status != 'deleted'
      AND b.urgent_at >= '2026-07-01' AND b.urgent_at < '2026-08-01'
      AND (r.replied_at IS NULL OR r.replied_at > b.urgent_at)
)
SELECT COUNT(*) AS urgent_tickets,
       SUM(replied_at IS NULL OR replied_at > datetime(urgent_at, '+60 minutes')) AS missed,
       ROUND(100.0 * SUM(replied_at IS NULL OR replied_at > datetime(urgent_at, '+60 minutes'))
             / COUNT(*), 1) AS missed_pct
FROM report;
```

## Weekly: waiting on a first reply

Monday stand-up. Open tickets nobody on the team has answered yet, by desk and priority.

```sql
SELECT t.brand, t.priority, COUNT(*) AS waiting
FROM tickets t
WHERE t.status IN ('new', 'open')
  AND NOT EXISTS (
      SELECT 1 FROM ticket_comments c JOIN users u ON u.id = c.author_id
      WHERE c.ticket_id = t.id AND c.public = 1 AND u.role IN ('agent', 'admin') AND c.via != 'rule')
GROUP BY t.brand, t.priority
ORDER BY t.brand, t.priority;
```

## Rota

Out of hours, the on-call agent gets paged for urgent tickets on both desks. The rota is
in the shared calendar; swaps go in #support-rota.
