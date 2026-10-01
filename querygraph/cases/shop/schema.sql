-- The shop's order ledger, as the payments sync writes it. Timestamps are UTC.

CREATE TABLE customers (
    id          INTEGER PRIMARY KEY,
    email       TEXT NOT NULL,
    name        TEXT NOT NULL,
    country     TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

CREATE TABLE orders (
    id           INTEGER PRIMARY KEY,
    customer_id  INTEGER NOT NULL REFERENCES customers(id),
    placed_at    TEXT NOT NULL,
    status       TEXT NOT NULL,        -- placed, shipped, refunded, cancelled
    currency     TEXT NOT NULL,        -- GBP, EUR
    total        INTEGER NOT NULL
);

CREATE TABLE payments (
    id           INTEGER PRIMARY KEY,
    order_id     INTEGER NOT NULL REFERENCES orders(id),
    amount       INTEGER NOT NULL,
    currency     TEXT NOT NULL,
    status       TEXT NOT NULL,        -- authorized, captured, voided, failed
    created_at   TEXT NOT NULL,
    captured_at  TEXT
);

CREATE TABLE refunds (
    id          INTEGER PRIMARY KEY,
    payment_id  INTEGER NOT NULL REFERENCES payments(id),
    amount      INTEGER NOT NULL,
    status      TEXT NOT NULL,         -- pending, succeeded, failed
    created_at  TEXT NOT NULL
);

CREATE TABLE fx_rates (
    currency      TEXT NOT NULL,
    rate_date     TEXT NOT NULL,
    gbp_per_unit  REAL NOT NULL,
    PRIMARY KEY (currency, rate_date)
);

CREATE INDEX payments_captured ON payments (captured_at);
CREATE INDEX refunds_created ON refunds (created_at);
