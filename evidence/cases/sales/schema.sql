-- Kettle & Kiln's sales ledger. The web shop, the till in the Bath shop and the phone desk all
-- write here. Timestamps are UTC. Money is in pence.

CREATE TABLE customers (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    email       TEXT NOT NULL,
    kind        TEXT NOT NULL,          -- retail, trade
    created_at  TEXT NOT NULL
);

CREATE TABLE products (
    id          INTEGER PRIMARY KEY,
    sku         TEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL,
    category    TEXT NOT NULL,
    unit_price  INTEGER NOT NULL        -- the retail price; trade accounts pay 70% of it
);

CREATE TABLE orders (
    id              INTEGER PRIMARY KEY,
    customer_id     INTEGER NOT NULL REFERENCES customers(id),
    channel         TEXT NOT NULL,      -- web, shop, phone
    placed_at       TEXT NOT NULL,
    status          TEXT NOT NULL,      -- completed, cancelled
    item_count      INTEGER NOT NULL,   -- order lines
    total_quantity  INTEGER NOT NULL,   -- units
    total_amount    INTEGER NOT NULL
);

CREATE TABLE order_items (
    id           INTEGER PRIMARY KEY,
    order_id     INTEGER NOT NULL REFERENCES orders(id),
    product_id   INTEGER NOT NULL REFERENCES products(id),
    quantity     INTEGER NOT NULL,
    unit_price   INTEGER NOT NULL,
    line_amount  INTEGER NOT NULL
);

CREATE TABLE order_amendments (
    id             INTEGER PRIMARY KEY,
    order_id       INTEGER NOT NULL REFERENCES orders(id),
    order_item_id  INTEGER NOT NULL REFERENCES order_items(id),
    amended_at     TEXT NOT NULL,
    change         TEXT NOT NULL,       -- item_added, quantity_changed
    by_user        TEXT NOT NULL
);

CREATE INDEX orders_customer ON orders(customer_id);
CREATE INDEX orders_placed ON orders(placed_at);
CREATE INDEX order_items_order ON order_items(order_id);
CREATE INDEX order_amendments_order ON order_amendments(order_id);
