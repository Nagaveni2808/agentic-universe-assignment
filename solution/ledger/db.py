"""Database tables. SQLite."""
import sqlite3

SCHEMA = """
-- One row per file we have ingested. This is what makes re-runs safe.
-- The counters are per file, and reports add them up.
CREATE TABLE IF NOT EXISTS ingested_files (
    file_key        TEXT PRIMARY KEY,
    kind            TEXT NOT NULL,
    sha256          TEXT NOT NULL,
    rows_total      INTEGER NOT NULL DEFAULT 0,
    rows_rejected   INTEGER NOT NULL DEFAULT 0,
    rows_merged     INTEGER NOT NULL DEFAULT 0,
    field_warnings  INTEGER NOT NULL DEFAULT 0,
    events_total    INTEGER NOT NULL DEFAULT 0,
    events_malformed INTEGER NOT NULL DEFAULT 0,
    events_duplicate INTEGER NOT NULL DEFAULT 0
);

-- A lead is identified by (workflow, phone token). No plain phone or name here.
CREATE TABLE IF NOT EXISTS leads (
    workflow_id  TEXT NOT NULL,
    phone_hash   TEXT NOT NULL,
    phone_last4  TEXT NOT NULL,
    batch_id     TEXT NOT NULL,
    external_ref TEXT NOT NULL,
    data_json    TEXT NOT NULL,
    PRIMARY KEY (workflow_id, phone_hash)
);

CREATE TABLE IF NOT EXISTS lead_rejections (
    workflow_id TEXT NOT NULL,
    batch_id    TEXT NOT NULL,
    row_number  INTEGER NOT NULL,
    reason      TEXT NOT NULL,
    PRIMARY KEY (workflow_id, batch_id, row_number)
);

-- The interaction ledger: append-only.
CREATE TABLE IF NOT EXISTS events (
    event_id     TEXT PRIMARY KEY,
    event_type   TEXT NOT NULL,
    workflow_id  TEXT,
    call_id      TEXT,
    occurred_at  TEXT,
    phone_hash   TEXT,
    payload_json TEXT NOT NULL,
    source_file  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_link ON events (workflow_id, phone_hash);
CREATE INDEX IF NOT EXISTS idx_events_call ON events (call_id);

CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON events
BEGIN SELECT RAISE(ABORT, 'ledger is append-only'); END;
CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON events
BEGIN SELECT RAISE(ABORT, 'ledger is append-only'); END;
"""


def connect(db_path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn