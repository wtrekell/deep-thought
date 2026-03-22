-- Migration: 001_init_schema.sql
-- Description: Initial schema for the web crawl tool
-- Preconditions: None — this is the first migration
-- Note: PRAGMA statements (journal_mode, foreign_keys) are intentionally
-- absent here. They cannot run inside a transaction, and they are already
-- applied by get_connection() before migrations execute.

-- ---------------------------------------------------------------------------
-- crawled_pages
-- Tracks each URL that has been fetched. `url` is the primary key.
-- `rule_name` identifies the batch config rule that triggered the crawl,
-- or NULL for direct CLI invocations.
-- `status` is one of: success, error, skipped.
-- `created_at` and `updated_at` are ISO-8601 timestamps set locally.
-- `synced_at` is set to UTC now on every write by queries.py.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS crawled_pages (
    url          TEXT    NOT NULL PRIMARY KEY,
    rule_name    TEXT,
    title        TEXT,
    status_code  INTEGER,
    word_count   INTEGER NOT NULL DEFAULT 0,
    output_path  TEXT,
    status       TEXT    NOT NULL DEFAULT 'success',
    created_at   TEXT    NOT NULL,
    updated_at   TEXT    NOT NULL,
    synced_at    TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_crawled_pages_status    ON crawled_pages (status);
CREATE INDEX IF NOT EXISTS idx_crawled_pages_rule_name ON crawled_pages (rule_name);

-- ---------------------------------------------------------------------------
-- web_schema_version
-- General-purpose key/value store for migration version tracking.
-- `key` is always 'schema_version'; `value` is the integer migration number
-- stored as text.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS web_schema_version (
    key        TEXT NOT NULL PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
