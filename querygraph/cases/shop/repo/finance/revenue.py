"""Net revenue: the figure finance closes each month on, and the one the board pack shows."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

LONDON = ZoneInfo("Europe/London")

# Captures less refunds, each in the month it happened: a July order refunded in
# August comes off August. Amounts are in minor units. Euro amounts become pounds
# at the reference rate of that day, or of the last business day before it.
# Staff orders (@shop.example) and QA's test purchases on production
# (@mailinator.com) are not revenue: see the month-end close checklist.
NET_REVENUE_SQL = """
WITH ledger AS (
    SELECT p.captured_at AS happened_at, p.currency, p.amount
    FROM payments p
    JOIN orders o ON o.id = p.order_id
    JOIN customers c ON c.id = o.customer_id
    WHERE p.status = 'captured'
      AND p.captured_at >= :start AND p.captured_at < :end
      AND c.email NOT LIKE '%@shop.example'
      AND c.email NOT LIKE '%@mailinator.com'
    UNION ALL
    SELECT r.created_at, p.currency, -r.amount
    FROM refunds r
    JOIN payments p ON p.id = r.payment_id
    JOIN orders o ON o.id = p.order_id
    JOIN customers c ON c.id = o.customer_id
    WHERE r.status = 'succeeded'
      AND r.created_at >= :start AND r.created_at < :end
      AND c.email NOT LIKE '%@shop.example'
      AND c.email NOT LIKE '%@mailinator.com'
)
SELECT ROUND(SUM(
         l.amount * CASE l.currency WHEN 'GBP' THEN 1.0 ELSE (
             SELECT fx.gbp_per_unit FROM fx_rates fx
             WHERE fx.currency = l.currency AND fx.rate_date <= date(l.happened_at)
             ORDER BY fx.rate_date DESC LIMIT 1) END
       ) / 100.0, 2) AS net_revenue_gbp
FROM ledger l
"""


def month_bounds(year: int, month: int) -> tuple[str, str]:
    """A London month as UTC instants, the way the ledger writes them.

    The books close on London months. While the clocks are on BST, August starts
    at 2026-07-31 23:00 UTC.
    """
    start = datetime(year, month, 1, tzinfo=LONDON)
    end = datetime(year + month // 12, month % 12 + 1, 1, tzinfo=LONDON)
    fmt = "%Y-%m-%d %H:%M:%S"
    return start.astimezone(timezone.utc).strftime(fmt), end.astimezone(timezone.utc).strftime(fmt)


def net_revenue_gbp(conn, year: int, month: int) -> float:
    """Net revenue for one London month, in pounds."""
    start, end = month_bounds(year, month)
    return conn.execute(NET_REVENUE_SQL, {"start": start, "end": end}).fetchone()[0]
