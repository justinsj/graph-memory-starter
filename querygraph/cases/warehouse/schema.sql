-- Two warehouses' stock, from the warehouse management system. Timestamps are UTC.

CREATE TABLE products (
    sku             TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    units_per_case  INTEGER NOT NULL,
    unit_cost       INTEGER NOT NULL
);

CREATE TABLE locations (
    id         INTEGER PRIMARY KEY,
    warehouse  TEXT NOT NULL,          -- LDS (Leeds), MAN (Manchester)
    code       TEXT NOT NULL,
    kind       TEXT NOT NULL           -- dock, bulk, pick, quarantine, returns, transit
);

-- Every movement of stock. An empty from_location is stock arriving from outside
-- (a supplier, a customer's return, a count); an empty to_location is stock leaving.
CREATE TABLE stock_moves (
    id             INTEGER PRIMARY KEY,
    sku            TEXT NOT NULL REFERENCES products(sku),
    from_location  INTEGER REFERENCES locations(id),
    to_location    INTEGER REFERENCES locations(id),
    qty            INTEGER NOT NULL,
    uom            TEXT NOT NULL,      -- unit, case
    state          TEXT NOT NULL,      -- planned, done, cancelled
    moved_at       TEXT NOT NULL,
    reference      TEXT NOT NULL
);

-- Units on hand per location, taken nightly.
CREATE TABLE stock_snapshot (
    taken_at     TEXT NOT NULL,
    sku          TEXT NOT NULL REFERENCES products(sku),
    location_id  INTEGER NOT NULL REFERENCES locations(id),
    qty_units    INTEGER NOT NULL
);

-- Stock held for an order or a checkout in progress.
CREATE TABLE reservations (
    id           INTEGER PRIMARY KEY,
    order_ref    TEXT NOT NULL,
    sku          TEXT NOT NULL REFERENCES products(sku),
    warehouse    TEXT NOT NULL,
    qty_units    INTEGER NOT NULL,
    created_at   TEXT NOT NULL,
    expires_at   TEXT NOT NULL,
    released_at  TEXT
);

CREATE INDEX moves_sku ON stock_moves (sku, moved_at);
CREATE INDEX snapshot_taken ON stock_snapshot (taken_at, sku);
