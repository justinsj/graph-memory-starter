-- The help desk, exported nightly. Timestamps are UTC.

CREATE TABLE users (
    id     INTEGER PRIMARY KEY,
    name   TEXT NOT NULL,
    email  TEXT NOT NULL,
    role   TEXT NOT NULL              -- end-user, agent, admin
);

CREATE TABLE tickets (
    id            INTEGER PRIMARY KEY,
    requester_id  INTEGER NOT NULL REFERENCES users(id),
    brand         TEXT NOT NULL,      -- standard, enterprise
    subject       TEXT NOT NULL,
    channel       TEXT NOT NULL,      -- email, web, chat, api
    priority      TEXT NOT NULL,      -- low, normal, high, urgent
    status        TEXT NOT NULL,      -- new, open, pending, solved, closed, deleted
    created_at    TEXT NOT NULL,
    merged_into   INTEGER REFERENCES tickets(id)
);

CREATE TABLE ticket_comments (
    id          INTEGER PRIMARY KEY,
    ticket_id   INTEGER NOT NULL REFERENCES tickets(id),
    author_id   INTEGER NOT NULL REFERENCES users(id),
    public      INTEGER NOT NULL,     -- 1 seen by the requester, 0 an internal note
    via         TEXT NOT NULL,        -- email, web, chat, api, rule
    body        TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

-- Every change to a ticket's fields, including the values it was created with.
CREATE TABLE ticket_field_changes (
    ticket_id   INTEGER NOT NULL REFERENCES tickets(id),
    field       TEXT NOT NULL,        -- priority, status
    old_value   TEXT,
    new_value   TEXT NOT NULL,
    changed_at  TEXT NOT NULL
);

CREATE INDEX comments_ticket ON ticket_comments (ticket_id, created_at);
CREATE INDEX changes_ticket ON ticket_field_changes (ticket_id, field);
