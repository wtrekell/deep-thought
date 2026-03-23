-- Migration: 001_init_schema.sql
-- Description: Initial schema for the Gmail Tool
-- Preconditions: None — this is the first migration
-- Note: PRAGMA statements (journal_mode, foreign_keys) are intentionally
-- absent here. They cannot run inside a transaction, and they are already
-- applied by get_connection() before migrations execute.

-- ---------------------------------------------------------------------------
-- processed_emails
-- Tracks every email collected by a rule. The primary key is the Gmail
-- message ID, which is unique across all messages in a mailbox.
--
-- `rule_name` records which collection rule matched this email.
-- `actions_taken` is a JSON-serialized list of actions applied (e.g.,
--   '["archive", "label:Processed"]').
-- `status` records the processing outcome: 'ok' or 'error'.
-- `created_at` records when the email was first collected locally.
-- `updated_at` records when any field on this row was last changed.
-- `synced_at` records when the Gmail API was last consulted for this message.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS processed_emails (
    message_id    TEXT NOT NULL PRIMARY KEY,
    rule_name     TEXT NOT NULL,
    subject       TEXT NOT NULL,
    from_address  TEXT NOT NULL,
    output_path   TEXT NOT NULL,
    actions_taken TEXT NOT NULL DEFAULT '[]',
    status        TEXT NOT NULL DEFAULT 'ok',
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    synced_at     TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_processed_emails_rule_name ON processed_emails (rule_name);

-- ---------------------------------------------------------------------------
-- decision_cache
-- Local cache for Gemini AI extraction decisions. Entries expire after
-- `ttl_seconds` from `created_at`. This table is purely local state —
-- it is never synced from an external API.
--
-- `cache_key` is a hash or composite key identifying the email + rule.
-- `decision` is the JSON-serialized extraction result from Gemini.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS decision_cache (
    cache_key    TEXT    NOT NULL PRIMARY KEY,
    decision     TEXT    NOT NULL,
    ttl_seconds  INTEGER NOT NULL,
    created_at   TEXT    NOT NULL,
    updated_at   TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_decision_cache_created_at ON decision_cache (created_at);

-- ---------------------------------------------------------------------------
-- key_value
-- General-purpose key/value store for tool metadata:
--   schema_version  — current migration number (integer stored as text)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS key_value (
    key        TEXT NOT NULL PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
