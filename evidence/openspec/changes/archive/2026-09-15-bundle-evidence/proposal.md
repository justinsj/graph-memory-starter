# Proposal: Evidence for the bundle offer

## Why

If we offer a 'complete the set' bundle at checkout, some single-line orders become two-line orders,
and sales rise. The thesis needs today's numbers: orders a day, how many orders have one line, and what
an order line is worth.

## What to establish

- `daily-sales`: aggregate sales by day over the period.
- `days-ranked`: group the days, order them by sales, and say what drives the top of the list.
- `lines-per-order`: test the claim that each sale contains more than one order item.
- `header-totals`: test the claim that an order's quantity and amount are always the totals of its lines.
- `order-value`: the average and the spread of order values, and the average order line.

## Period and definitions

- 1 July to 31 August 2026.
- A day is a London calendar day. orders.placed_at is UTC, and July and August are on British Summer
  Time (UTC+1).
- Counted orders are completed orders, leaving out staff purchases (customers whose email ends
  @kettleandkiln.example) and the till's training transactions (training@till.local). Trade orders count.
- Sales are the line amounts (order_items.line_amount) of counted orders, in pounds.

## Data

The sales ledger (sales.db), extract of 15 September 2026. Updates 2026-07-01-h1-sales-evidence for the
sets it repeats.
