# Metrics handbook

Finance and Data · exported from Notion · last edited 12 August 2026 by Tom Achebe

The numbers in the board pack, what each one means, and the query behind it. If a
number here disagrees with a dashboard, this page wins. Ask in #data-help.

## MRR

Monthly recurring revenue on a date: what every paying subscription would bill in a
month, as it stood at the end of that day (UTC).

- **Paying** means `active` or `past_due`. A past-due subscription is a customer whose
  renewal failed and who is in dunning; they are still a customer until dunning ends it.
  Trials and paused subscriptions are not paying.
- **As it stood**: from `subscription_history`, not `subscriptions`, which only shows
  today. A customer who added seats in September had fewer on 31 August.
- **Annual plans** count a twelfth of the annual price.
- **Seats**: the price is per seat, so multiply by the quantity.
- **Discounts** count while they run: a discount that started or ended on another day
  does not change MRR on this one.
- **In dollars, at the budget rates.** Euro and sterling plans convert at the rates
  finance fixed for the year, not the day's rate, so a currency swing doesn't move MRR.
  For 2026: €1 = $1.10 and £1 = $1.30.

The saved question in Metabase is "MRR on a date" (card 112):

```sql
SELECT ROUND(SUM(
         h.quantity * p.unit_amount
         / CASE p.billing_interval WHEN 'year' THEN 12.0 ELSE 1.0 END
         * (1 - COALESCE(d.percent_off, 0) / 100.0)
         * CASE p.currency WHEN 'EUR' THEN 1.10 WHEN 'GBP' THEN 1.30 ELSE 1.0 END
       ) / 100.0, 2) AS mrr_usd
FROM subscription_history h
JOIN plans p ON p.id = h.plan_id
LEFT JOIN discounts d
  ON d.subscription_id = h.subscription_id
 AND d.starts_at < date({{as_of}}, '+1 day')
 AND (d.ends_at IS NULL OR d.ends_at >= date({{as_of}}, '+1 day'))
WHERE h.status IN ('active', 'past_due')
  AND h.valid_from < date({{as_of}}, '+1 day')
  AND (h.valid_to IS NULL OR h.valid_to >= date({{as_of}}, '+1 day'))
  [[AND p.id = {{plan}}]]
```

`{{as_of}}` is a date; `{{plan}}` is optional and filters to one plan.

## Contracted ARR (sales)

Sales quote contracted ARR in the pipeline review. It is not MRR × 12: it takes every
subscription that has not ended, at list price, trials included, because sales count a
trial with a card on file as committed.

```sql
SELECT SUM(s.quantity * p.unit_amount
           * CASE p.billing_interval WHEN 'month' THEN 12 ELSE 1 END) / 100.0 AS contracted_arr_usd
FROM subscriptions s
JOIN plans p ON p.id = s.plan_id
WHERE s.ended_at IS NULL;
```

## Logo churn

The June and July board packs used Tom's query from #data-help (4 August). It is not
a saved question yet.
