# Proposal: Sales evidence, first half of 2026

## Why

The half-year review needs the shape of our sales: how much we sell a day, how big an order is, and
whether the order headers can be trusted for the stock report.

## What to establish

- `daily-sales`: sales and counted orders, by day.
- `lines-per-order`: whether each sale contains more than one order item.
- `header-totals`: whether an order's quantity and amount are always the totals of its lines.
- `order-value`: the average order and the average order line.

## Period and definitions

- 1 January to 30 June 2026.
- A day is a London calendar day. orders.placed_at is UTC; the clocks went forward on 29 March 2026.
- Counted orders are completed orders, leaving out staff purchases (customers whose email ends
  @kettleandkiln.example) and the till's training transactions (training@till.local). Trade orders count.
- Sales are the line amounts (order_items.line_amount) of counted orders, in pounds.

## Data

The sales ledger (sales.db), extract of 1 July 2026. No earlier evidence change.
