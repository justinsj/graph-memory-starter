CREATE TABLE entities  (id TEXT PRIMARY KEY,   -- uuid5(type + normalised name)
                        name TEXT NOT NULL, type TEXT NOT NULL,
                        source_doc TEXT);      -- the first doc that named it
CREATE TABLE claims    (id INTEGER PRIMARY KEY,
                        entity_id TEXT NOT NULL REFERENCES entities(id),
                        kind TEXT NOT NULL,    -- threshold, deadline, availability,
                                               -- unknown, responsibility, rule, note
                        text TEXT NOT NULL,    -- one sentence: what the model reads
                        quote TEXT,            -- the source's own words, checked
                        amount REAL, unit TEXT,
                        valid_from TEXT,       -- ISO date it starts; NULL = not stated
                        valid_to TEXT,         -- ISO date it stops; NULL = in force
                        source_doc TEXT NOT NULL);
CREATE TABLE relations (source_id TEXT NOT NULL REFERENCES entities(id),
                        target_id TEXT NOT NULL REFERENCES entities(id),
                        predicate TEXT NOT NULL, source_doc TEXT,
                        valid_from TEXT, valid_to TEXT);  -- as for claims
CREATE TABLE names     (norm TEXT NOT NULL,             -- a name or alias, split the
                                                        -- way questions are
                        entity_id TEXT NOT NULL REFERENCES entities(id),
                        kind TEXT NOT NULL,             -- 'name' or 'alias'
                        text TEXT NOT NULL);            -- as the extraction wrote it

-- The access layer recall.py reads. build_graph.py fills it with the graph.
CREATE INDEX claims_entity ON claims(entity_id);        -- an entity's claims
CREATE INDEX relations_source ON relations(source_id);  -- the walk reads a node's
CREATE INDEX relations_target ON relations(target_id);  -- links by index, both ways
CREATE INDEX names_norm ON names(norm);                 -- what a question mentions
CREATE VIRTUAL TABLE entity_fts USING fts5(             -- relevance: BM25, so rare
    entity_id UNINDEXED, name, claims,                  -- words weigh more; porter
    tokenize = 'porter unicode61');                     -- stems "signs" to "sign"
CREATE TABLE meta      (key TEXT PRIMARY KEY, value TEXT);

-- Projects, from projects/records/*.json. A project is an entity (type PROJECT),
-- so names, full-text search and the walk all find it; its status, due date,
-- decisions and open questions are claims, its owner and dependencies links.
-- These tables hold only what needs order, state or provenance.
CREATE TABLE projects     (entity_id TEXT PRIMARY KEY REFERENCES entities(id),
                           slug TEXT NOT NULL UNIQUE,       -- the record's id
                           status TEXT NOT NULL,            -- the open status claim's
                           status_from TEXT,
                           plan_state TEXT NOT NULL,        -- none | agreed
                           plan_version INTEGER NOT NULL,
                           plan_agreed_on TEXT,
                           owner_id TEXT REFERENCES entities(id),
                           created TEXT, updated TEXT,      -- first and last activity
                           due TEXT, due_text TEXT);        -- a date only when one was stated
CREATE TABLE deliverables (entity_id TEXT PRIMARY KEY REFERENCES entities(id),  -- DELIVERABLE
                           project_id TEXT NOT NULL REFERENCES projects(entity_id),
                           key TEXT NOT NULL, title TEXT NOT NULL, status TEXT NOT NULL,
                           due TEXT, on_date TEXT, owner_id TEXT REFERENCES entities(id),
                           UNIQUE (project_id, key));
CREATE TABLE steps        (id INTEGER PRIMARY KEY,
                           project_id TEXT NOT NULL REFERENCES projects(entity_id),
                           n INTEGER NOT NULL, title TEXT NOT NULL, status TEXT NOT NULL,
                           due TEXT, on_date TEXT, owner_id TEXT REFERENCES entities(id),
                           deliverable_id TEXT REFERENCES deliverables(entity_id),
                           source_doc TEXT, quote TEXT, UNIQUE (project_id, n));
CREATE TABLE step_after   (step_id INTEGER NOT NULL REFERENCES steps(id),
                           after_id INTEGER NOT NULL REFERENCES steps(id));
CREATE TABLE sources      (project_id TEXT NOT NULL REFERENCES projects(entity_id),
                           doc TEXT NOT NULL, kind TEXT NOT NULL,  -- transcript, request,
                           read_on TEXT NOT NULL, sha256 TEXT NOT NULL,  -- discussion, ...
                           used_for TEXT NOT NULL,                 -- JSON list
                           PRIMARY KEY (project_id, doc, sha256));
CREATE TABLE events       (id INTEGER PRIMARY KEY,                 -- <id>.log.jsonl, loaded
                           project_id TEXT NOT NULL REFERENCES projects(entity_id),
                           on_date TEXT NOT NULL, op TEXT NOT NULL,
                           subject TEXT,                           -- step 2, D1, owner, Q1 ...
                           old TEXT, new TEXT, by TEXT, source_doc TEXT, quote TEXT);
CREATE INDEX projects_status ON projects(status, due);  -- "what is blocked", "due this month"
CREATE INDEX steps_project  ON steps(project_id, n);
CREATE INDEX events_project ON events(project_id, on_date);
CREATE INDEX sources_doc    ON sources(doc);            -- "which projects came from this meeting"

-- Code, from codegraph/index.py: functions, constants, routes, route cases and
-- buttons are entities, what reaches what their links (calls, reads, requests,
-- handled_by, dispatches_to, triggers, part_of), each line quoted as a claim.
-- This table holds only where a symbol is, and a constant's value.
CREATE TABLE code_symbols (entity_id TEXT PRIMARY KEY REFERENCES entities(id),
                           file TEXT NOT NULL, line INTEGER NOT NULL, language TEXT NOT NULL,
                           value TEXT,        -- a constant's value as written
                           resolved TEXT);    -- and as a string, template strings worked out
CREATE TABLE call_sites   (source_id TEXT NOT NULL REFERENCES entities(id),  -- where each link happens:
                           target_id TEXT NOT NULL REFERENCES entities(id),  -- each call, read, reference,
                           predicate TEXT NOT NULL,                          -- import, request, dispatch,
                           file TEXT NOT NULL, line INTEGER NOT NULL,        -- and each body field a
                           quote TEXT NOT NULL,                              -- handler reads (reads_body)
                           detail TEXT);                                     -- body fields, sent or read
CREATE INDEX call_sites_target ON call_sites(target_id, predicate);  -- "every call to it"
CREATE INDEX call_sites_source ON call_sites(source_id, predicate);
