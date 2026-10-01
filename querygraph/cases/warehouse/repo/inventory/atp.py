"""Available to promise: how many units the storefront may still sell from one warehouse.

The storefront asks before it shows "In stock", and again before it takes a reservation.
"""

# Leeds holds two cases of every line back for wholesale call-offs. Wholesale orders
# (WS-) are allocated from that ring-fenced stock, so the storefront does not take
# their reservations off again.
SAFETY_STOCK_CASES = {"LDS": 2, "MAN": 0}

# On hand comes from the move ledger: stock_snapshot is the 02:00 valuation snapshot.
# Only bulk and pick stock can be promised. A move in cases is units_per_case units.
ATP_SQL = """
WITH ledger AS (
    SELECT m.to_location AS location_id,
           m.qty * CASE m.uom WHEN 'case' THEN p.units_per_case ELSE 1 END AS units
    FROM stock_moves m
    JOIN products p ON p.sku = m.sku
    WHERE m.sku = :sku AND m.state = 'done' AND m.moved_at <= :now AND m.to_location IS NOT NULL
    UNION ALL
    SELECT m.from_location,
           -m.qty * CASE m.uom WHEN 'case' THEN p.units_per_case ELSE 1 END
    FROM stock_moves m
    JOIN products p ON p.sku = m.sku
    WHERE m.sku = :sku AND m.state = 'done' AND m.moved_at <= :now AND m.from_location IS NOT NULL
),
sellable AS (
    SELECT COALESCE(SUM(g.units), 0) AS units
    FROM ledger g
    JOIN locations l ON l.id = g.location_id
    WHERE l.warehouse = :warehouse AND l.kind IN ('bulk', 'pick')
),
promised AS (
    SELECT COALESCE(SUM(r.qty_units), 0) AS units
    FROM reservations r
    WHERE r.sku = :sku AND r.warehouse = :warehouse
      AND r.released_at IS NULL AND r.expires_at > :now
      AND r.order_ref NOT LIKE 'WS-%'
)
SELECT sellable.units - promised.units
       - :safety_cases * (SELECT units_per_case FROM products WHERE sku = :sku) AS available_to_promise
FROM sellable, promised
"""


def available_to_promise(conn, sku: str, warehouse: str, now: str) -> int:
    """Units of one SKU the storefront may still sell from one warehouse (LDS, MAN)."""
    params = {"sku": sku, "warehouse": warehouse, "now": now, "safety_cases": SAFETY_STOCK_CASES[warehouse]}
    return conn.execute(ATP_SQL, params).fetchone()[0]
