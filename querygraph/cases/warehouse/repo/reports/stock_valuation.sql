-- Stock valuation for the month-end close: every unit we own, wherever it sits
-- (damaged and returned stock included; finance writes it down separately), at cost.
SELECT l.warehouse,
       s.sku,
       SUM(s.qty_units) AS units,
       SUM(s.qty_units * p.unit_cost) / 100.0 AS value_gbp
FROM stock_snapshot s
JOIN locations l ON l.id = s.location_id
JOIN products p ON p.sku = s.sku
WHERE s.taken_at = :taken_at
GROUP BY l.warehouse, s.sku
ORDER BY l.warehouse, s.sku;
