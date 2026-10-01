# #data-help, 4 August 2026

Exported from Slack. Times are London time.

---

**Priya Shah** (Finance) · 09:12

Board pack needs July logo churn. Is this right? It gives me 4.5%, which feels high.

```sql
SELECT ROUND(100.0 * COUNT(DISTINCT account_id)
       / (SELECT COUNT(DISTINCT account_id) FROM subscriptions WHERE status = 'active'), 1)
FROM subscriptions
WHERE canceled_at >= '2026-07-01' AND canceled_at < '2026-08-01';
```

---

**Tom Achebe** (Data) · 09:40

Not quite, a few things bite with that one:

1. `canceled_at` is when they clicked cancel. Most cancel at period end, so they keep
   paying for weeks. They churn when they stop paying.
2. We count logos, meaning accounts, not subscriptions. An account that drops its second
   office's subscription but keeps the first hasn't churned. Nor has one that moved from
   monthly to annual: billing does that as a cancel and a new subscription.
3. The rate is over the accounts that were paying on the 1st, not the ones active today.
   A trial that never converted wasn't paying, so it isn't churn. Past due is still
   paying (they're in dunning); paused is not, so a pause counts as churn that month and
   as a win-back if they come back.

So: accounts paying going into the month that aren't paying going out of it. This is
what I ran for the June and July packs, here with July's dates:

```sql
WITH paying_at_start AS (
    SELECT DISTINCT s.account_id
    FROM subscription_history h
    JOIN subscriptions s ON s.id = h.subscription_id
    WHERE h.status IN ('active', 'past_due')
      AND h.valid_from < '2026-07-01'
      AND (h.valid_to IS NULL OR h.valid_to >= '2026-07-01')
),
paying_at_end AS (
    SELECT DISTINCT s.account_id
    FROM subscription_history h
    JOIN subscriptions s ON s.id = h.subscription_id
    WHERE h.status IN ('active', 'past_due')
      AND h.valid_from < '2026-08-01'
      AND (h.valid_to IS NULL OR h.valid_to >= '2026-08-01')
)
SELECT COUNT(*) AS churned_logos,
       (SELECT COUNT(*) FROM paying_at_start) AS logos_at_start,
       ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM paying_at_start), 2) AS logo_churn_pct
FROM paying_at_start a
WHERE a.account_id NOT IN (SELECT account_id FROM paying_at_end);
```

---

**Priya Shah** (Finance) · 09:52

1.6%. That's more like it, and it matches what CS expected. Thanks! Using this one.

---

**Tom Achebe** (Data) · 09:53

👍 I'll put it in the metrics handbook when I get a minute.
