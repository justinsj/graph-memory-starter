# Evidence: Bundle offer, July and August 2026

Period: 2026-07-01 to 2026-08-31, London days
Data: sales.db (Kettle & Kiln's sales ledger), extract of 2026-09-15
Supersedes: 2026-07-01-h1-sales-evidence, for daily-sales, lines-per-order, header-totals and order-value

## daily-sales: Daily sales

Claim: Daily sales for July and August 2026.
Verdict: measured
Keywords: daily sales, sales a day, revenue, takings, orders a day, order count
Tables: orders (placed_at, status, customer_id), customers (email), order_items (line_amount)

| Key | Number | Value | Unit |
|---|---|---|---|
| days | Days in the period | 62 | days |
| counted_orders | Counted orders, July and August 2026 | 2,359 | orders |
| sales | Sales, July and August 2026 | 178,905.30 | GBP |
| orders_a_day | Counted orders a day | 38.0 | orders a day |
| mean_daily_sales | Mean daily sales | 2,885.57 | GBP |
| median_daily_sales | Median daily sales | 2,684.78 | GBP |

```sql
WITH counted AS (
  SELECT o.id, date(datetime(o.placed_at, '+1 hour')) AS day, c.kind
  FROM orders o JOIN customers c ON c.id = o.customer_id
  WHERE o.status = 'completed'
    AND c.email NOT LIKE '%@kettleandkiln.example' AND c.email <> 'training@till.local'
)
SELECT day, COUNT(DISTINCT counted.id) AS orders, SUM(i.line_amount) / 100.0 AS sales
FROM counted JOIN order_items i ON i.order_id = counted.id
WHERE day BETWEEN '2026-07-01' AND '2026-08-31'
GROUP BY day ORDER BY day;
```

Notes:
- Sales are summed from order_items.line_amount, not orders.total_amount: 23 order headers are stale (see header-totals), and the headers give £178,187.80.
- A day is a London day. placed_at is UTC and July and August are on BST, so UTC days give £178,974.80 and 2,362 orders: orders just after midnight land on the wrong day.
- Counted orders leave out staff purchases (34 orders, £1,292.00) and the till's training transactions (24 orders, £793.50). Trade orders count. Cancelled orders are not sales.
- Every one of the 62 days had counted orders.

## days-ranked: Days ranked by sales

Claim: The days of the period, grouped and ordered by sales.
Verdict: measured
Keywords: best day, top days, busiest day, best retail day, lowest day, weekday, Saturday
Tables: orders, customers (kind), order_items (line_amount)

| Key | Number | Value | Unit |
|---|---|---|---|
| best_day | Best day | 2026-08-14 | date |
| best_day_sales | Sales on the best day | 9,185.90 | GBP |
| best_day_largest_order | Largest order on the best day | 6,791.40 | GBP |
| best_retail_day | Best day for retail sales | 2026-08-29 | date |
| best_retail_day_sales | Retail sales on the best retail day | 6,918.50 | GBP |
| best_weekday | Weekday with the highest mean sales | Saturday | weekday |
| saturday_mean_sales | Mean sales on a Saturday | 3,911.11 | GBP |
| lowest_day | Lowest day | 2026-07-27 | date |
| lowest_day_sales | Sales on the lowest day | 1,344.00 | GBP |

```sql
WITH days AS (
  SELECT counted.day, SUM(i.line_amount) AS sales,
         SUM(CASE WHEN counted.kind = 'retail' THEN i.line_amount ELSE 0 END) AS retail_sales
  FROM counted JOIN order_items i ON i.order_id = counted.id
  WHERE counted.day BETWEEN '2026-07-01' AND '2026-08-31'
  GROUP BY counted.day
)
SELECT day, sales / 100.0 AS sales, retail_sales / 100.0 AS retail_sales FROM days ORDER BY sales DESC;
```

Notes:
- 14 August is the best day only because of one trade order: £6,791.40 from Sea Salt Interiors, 74% of the day. Its retail sales were £2,394.50.
- The best day for retail is Saturday 29 August (£6,918.50, 98 orders), the bank holiday weekend sale.
- Top five days: 14 Aug £9,185.90, 29 Aug £6,918.50, 8 Aug £4,571.00, 31 Jul £4,564.60, 31 Aug £4,495.20.
- By weekday, Saturdays average £3,911.11 and Fridays £3,602.37; Tuesdays are lowest at £1,957.89.

## lines-per-order: Order lines per order

Claim: Each sale contains more than one order item.
Verdict: does not hold
Keywords: order lines, order items, basket size, single-line orders, items per order, units per order
Tables: order_items (order_id, quantity), orders (channel, status, item_count)

| Key | Number | Value | Unit |
|---|---|---|---|
| verdict | Verdict | does not hold | |
| single_line_orders | Counted orders with one order line | 556 | orders |
| single_line_share | Orders with one order line | 23.6 | % |
| single_line_share_web | Web orders with one order line | 11.7 | % |
| single_line_share_shop | Shop (till) orders with one order line | 47.1 | % |
| single_line_share_phone | Phone orders with one order line | 19.9 | % |
| single_unit_share | Orders of a single unit | 15.3 | % |
| mean_lines | Order lines per order, mean | 2.35 | lines |
| mean_units | Units per order, mean | 4.10 | units |
| cancelled_without_lines | Cancelled orders with no lines | 31 | orders |

```sql
WITH l AS (SELECT order_id, COUNT(*) AS n, SUM(quantity) AS units FROM order_items GROUP BY order_id)
SELECT o.channel, COUNT(*) AS orders, SUM(l.n = 1) AS single_line, ROUND(100.0 * SUM(l.n = 1) / COUNT(*), 1) AS share
FROM counted JOIN orders o ON o.id = counted.id JOIN l ON l.order_id = counted.id
WHERE counted.day BETWEEN '2026-07-01' AND '2026-08-31'
GROUP BY o.channel;
```

Notes:
- An order item here is an order line, a row in order_items. Counted in units instead, 15.3% of orders are a single unit, so the claim fails either way.
- The claim fails mostly at the till: 47.1% of shop orders have one line, against 11.7% on the web and 19.9% by phone.
- Count lines from order_items, not orders.item_count: amendments added lines to some orders, so the header gives 561 single-line orders, not 556.
- 31 cancelled orders in the period have no lines at all (released when cancelled). Every completed order has at least one line.
- Units per order (4.10) is pulled up by trade orders, which buy 6 to 60 of each product.

## header-totals: Order header totals

Claim: An order's quantity and amount are always the totals of its lines.
Verdict: holds with exceptions
Keywords: order header, total_quantity, total_amount, item_count, units sold, amendments, data quality
Tables: orders (item_count, total_quantity, total_amount), order_items (quantity, unit_price, line_amount), order_amendments

| Key | Number | Value | Unit |
|---|---|---|---|
| verdict | Verdict | holds with exceptions | |
| checked_orders | Orders checked | 2,359 | orders |
| quantity_mismatches | Orders whose total_quantity differs from their lines | 23 | orders |
| amount_mismatches | Orders whose total_amount differs from their lines | 23 | orders |
| item_count_mismatches | Orders whose item_count differs from their lines | 9 | orders |
| units_missing | Units the headers leave out | 36 | units |
| amount_missing | Sales the headers leave out | 717.50 | GBP |
| mismatches_amended | Mismatched orders that were amended after checkout | 23 | orders |
| first_amendment | First amendment | 2026-07-10 | date |
| lines_checked | Order lines checked for quantity times unit price | 5,548 | lines |
| line_arithmetic_exceptions | Lines whose amount is not quantity times unit price | 0 | lines |

```sql
WITH l AS (SELECT order_id, COUNT(*) AS n, SUM(quantity) AS units, SUM(line_amount) AS amount
           FROM order_items GROUP BY order_id)
SELECT o.id, o.channel, o.item_count, l.n, o.total_quantity, l.units, o.total_amount, l.amount,
       EXISTS (SELECT 1 FROM order_amendments a WHERE a.order_id = o.id) AS amended
FROM counted JOIN orders o ON o.id = counted.id JOIN l ON l.order_id = o.id
WHERE counted.day BETWEEN '2026-07-01' AND '2026-08-31'
  AND (o.total_quantity <> l.units OR o.total_amount <> l.amount OR o.item_count <> l.n);
```

Notes:
- All 23 mismatched orders are phone orders amended after checkout by the phone desk's back-office tool (order_amendments, by_user phone-desk), which writes the lines and leaves the header as it was at checkout.
- For units and sales use order_items. orders.total_quantity, total_amount and item_count are only as at checkout: the headers leave out 36 units and £717.50.
- This supersedes the first half's finding that the headers always match. It held then (0 of 5,853) because no order was amended before July; the first amendment was on 10 July 2026.
- Line arithmetic holds: line_amount is quantity times unit_price on all 5,548 lines, amended lines included.

## order-value: Order value

Claim: What a counted order is worth, and how order values spread.
Verdict: measured
Keywords: average order value, AOV, basket value, order value bands, median order, order line value
Tables: order_items (line_amount), customers (kind)

| Key | Number | Value | Unit |
|---|---|---|---|
| aov | Average order value | 75.84 | GBP |
| retail_aov | Average order value, retail only | 65.01 | GBP |
| median_order_value | Median order value | 55.50 | GBP |
| under_20_share | Orders under 20 pounds | 11.7 | % |
| from_20_to_50_share | Orders from 20 to 50 pounds | 32.1 | % |
| from_50_to_100_share | Orders from 50 to 100 pounds | 37.8 | % |
| over_100_share | Orders of 100 pounds or more | 18.4 | % |
| average_line_amount | Average order line | 32.25 | GBP |

```sql
WITH v AS (SELECT counted.id, counted.kind, SUM(i.line_amount) AS amount, COUNT(*) AS n
           FROM counted JOIN order_items i ON i.order_id = counted.id
           WHERE counted.day BETWEEN '2026-07-01' AND '2026-08-31' GROUP BY counted.id)
SELECT CASE WHEN amount < 2000 THEN 'under 20' WHEN amount < 5000 THEN '20 to 50'
            WHEN amount < 10000 THEN '50 to 100' ELSE '100 or more' END AS band,
       COUNT(*) AS orders, ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM v), 1) AS share
FROM v GROUP BY band ORDER BY MIN(amount);
```

Notes:
- Trade orders (15 in the period, £26,515.30, at 70% of the retail price) pull the average up: retail only, it is £65.01.
- The median, £55.50, is a fairer picture of a typical order than the mean.
- Bands are of counted orders by their line total: under £20, £20 to £50, £50 to £100, £100 or more.
- The average order line is sales divided by order lines (5,548): £32.25.
