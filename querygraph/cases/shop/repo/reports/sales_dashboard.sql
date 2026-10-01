-- Sales by day, for the marketing dashboard (Metabase, "Trading today").
-- Order value when the order is placed, in the order's own currency.
SELECT date(placed_at) AS day,
       currency,
       COUNT(*) AS orders,
       SUM(total) / 100.0 AS sales
FROM orders
WHERE status != 'cancelled'
  AND placed_at >= {{from}} AND placed_at < {{to}}
GROUP BY 1, 2
ORDER BY 1, 2;
