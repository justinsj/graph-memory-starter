# Evidence: Sales, first half of 2026

Period: 2026-01-01 to 2026-06-30, London days
Data: sales.db (Kettle & Kiln's sales ledger), extract of 2026-07-01
Supersedes: none

## daily-sales: Daily sales

Claim: Daily sales for the first half of 2026.
Verdict: measured
Keywords: daily sales, sales a day, revenue, takings, orders a day, order count
Tables: orders (placed_at, status, customer_id), customers (email), order_items (line_amount)

| Key | Number | Value | Unit |
|---|---|---|---|
| days | Days in the period | 181 | days |
| counted_orders | Counted orders, first half of 2026 | 5,853 | orders |
| sales | Sales, first half of 2026 | 425,219.95 | GBP |
| orders_a_day | Counted orders a day, first half of 2026 | 32.3 | orders a day |
| mean_daily_sales | Mean daily sales, first half of 2026 | 2,349.28 | GBP |

```sql
WITH counted AS (
  SELECT o.id,
         date(CASE WHEN o.placed_at >= '2026-03-29 01:00:00' THEN datetime(o.placed_at, '+1 hour')
                   ELSE o.placed_at END) AS day
  FROM orders o JOIN customers c ON c.id = o.customer_id
  WHERE o.status = 'completed'
    AND c.email NOT LIKE '%@kettleandkiln.example' AND c.email <> 'training@till.local'
)
SELECT day, COUNT(DISTINCT counted.id) AS orders, SUM(i.line_amount) / 100.0 AS sales
FROM counted JOIN order_items i ON i.order_id = counted.id
WHERE day BETWEEN '2026-01-01' AND '2026-06-30'
GROUP BY day ORDER BY day;
```

Notes:
- A day is a London day: placed_at is UTC, and from 29 March 2026 the clocks are an hour ahead of it.
- Counted orders leave out staff purchases (99 orders, £3,666.50) and the till's training transactions (78 orders, £2,565.50). Trade orders count.

## lines-per-order: Order lines per order

Claim: Each sale contains more than one order item.
Verdict: does not hold
Keywords: order lines, order items, basket size, single-line orders, items per order
Tables: order_items (order_id), orders (channel)

| Key | Number | Value | Unit |
|---|---|---|---|
| verdict | Verdict | does not hold | |
| single_line_share | Orders with one order line, first half of 2026 | 23.8 | % |
| mean_lines | Order lines per order, mean, first half of 2026 | 2.34 | lines |

```sql
SELECT ROUND(100.0 * SUM(n = 1) / COUNT(*), 1) AS single_line_share, ROUND(AVG(n), 2) AS mean_lines
FROM (SELECT i.order_id, COUNT(*) AS n FROM order_items i GROUP BY i.order_id) l
WHERE l.order_id IN (SELECT id FROM counted WHERE day BETWEEN '2026-01-01' AND '2026-06-30');
```

Notes:
- Most single-line orders are at the till: 47.9% of shop orders have one line, 11.4% of web orders and 24.1% of phone orders.

## header-totals: Order header totals

Claim: An order's quantity and amount are always the totals of its lines.
Verdict: holds
Keywords: order header, total_quantity, total_amount, item_count, units sold, data quality
Tables: orders (item_count, total_quantity, total_amount), order_items (quantity, line_amount)

| Key | Number | Value | Unit |
|---|---|---|---|
| verdict | Verdict | holds | |
| checked_orders | Orders checked, first half of 2026 | 5,853 | orders |
| quantity_mismatches | Orders whose total_quantity differs from their lines, first half of 2026 | 0 | orders |
| amount_mismatches | Orders whose total_amount differs from their lines, first half of 2026 | 0 | orders |

```sql
SELECT COUNT(*) AS checked,
       SUM(l.units <> o.total_quantity) AS quantity_mismatches,
       SUM(l.amount <> o.total_amount) AS amount_mismatches
FROM orders o
JOIN (SELECT order_id, SUM(quantity) AS units, SUM(line_amount) AS amount FROM order_items GROUP BY order_id) l
  ON l.order_id = o.id
WHERE o.id IN (SELECT id FROM counted WHERE day BETWEEN '2026-01-01' AND '2026-06-30');
```

Notes:
- The header totals match the lines on every counted order, so orders.total_quantity and orders.total_amount can be used for units and sales.

## order-value: Order value

Claim: What a counted order is worth.
Verdict: measured
Keywords: average order value, AOV, basket value, order line value
Tables: order_items (line_amount)

| Key | Number | Value | Unit |
|---|---|---|---|
| aov | Average order value, first half of 2026 | 72.65 | GBP |
| average_line_amount | Average order line, first half of 2026 | 31.10 | GBP |

```sql
SELECT ROUND(SUM(i.line_amount) / 100.0 / COUNT(DISTINCT i.order_id), 2) AS aov,
       ROUND(SUM(i.line_amount) / 100.0 / COUNT(*), 2) AS average_line_amount
FROM order_items i
WHERE i.order_id IN (SELECT id FROM counted WHERE day BETWEEN '2026-01-01' AND '2026-06-30');
```

Notes:
- Trade orders (43 in the half, £55,365.45, at 70% of the retail price) pull the average up.
