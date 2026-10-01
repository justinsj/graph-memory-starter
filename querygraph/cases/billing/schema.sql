-- Subscription billing, synced nightly from the billing provider. Timestamps are UTC.

CREATE TABLE accounts (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

CREATE TABLE plans (
    id                TEXT PRIMARY KEY,
    name              TEXT NOT NULL,
    billing_interval  TEXT NOT NULL,       -- month, year
    unit_amount       INTEGER NOT NULL,    -- per seat, per billing interval
    currency          TEXT NOT NULL
);

-- One row per subscription, as it stands now.
CREATE TABLE subscriptions (
    id                    INTEGER PRIMARY KEY,
    account_id            INTEGER NOT NULL REFERENCES accounts(id),
    plan_id               TEXT NOT NULL REFERENCES plans(id),
    status                TEXT NOT NULL,   -- trialing, active, past_due, paused, canceled
    quantity              INTEGER NOT NULL,
    created_at            TEXT NOT NULL,
    trial_end             TEXT,
    canceled_at           TEXT,
    cancel_at_period_end  INTEGER NOT NULL DEFAULT 0,
    cancel_at             TEXT,
    ended_at              TEXT
);

-- Every state a subscription has been in: [valid_from, valid_to), valid_to empty while current.
CREATE TABLE subscription_history (
    subscription_id  INTEGER NOT NULL REFERENCES subscriptions(id),
    plan_id          TEXT NOT NULL REFERENCES plans(id),
    quantity         INTEGER NOT NULL,
    status           TEXT NOT NULL,
    valid_from       TEXT NOT NULL,
    valid_to         TEXT
);

CREATE TABLE discounts (
    id               INTEGER PRIMARY KEY,
    subscription_id  INTEGER NOT NULL REFERENCES subscriptions(id),
    percent_off      REAL NOT NULL,
    starts_at        TEXT NOT NULL,
    ends_at          TEXT
);

CREATE INDEX history_subscription ON subscription_history (subscription_id, valid_from);
