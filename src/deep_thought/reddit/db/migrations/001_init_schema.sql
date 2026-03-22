-- Migration: 001_init_schema.sql
-- Description: Initial schema for the Reddit Tool
-- Preconditions: None — this is the first migration
-- Note: PRAGMA statements (journal_mode, foreign_keys) are intentionally
-- absent here. They cannot run inside a transaction, and they are already
-- applied by get_connection() before migrations execute.

-- ---------------------------------------------------------------------------
-- collected_posts
-- Tracks every Reddit post collected by a rule. The primary key is a
-- composite state key of the form "{post_id}:{subreddit}:{rule_name}",
-- which allows the same post to be independently collected by multiple
-- rules without collision.
--
-- `created_at` records when the post was first collected locally.
-- `updated_at` records when any field on this row was last changed locally.
-- `synced_at` records when the Reddit API was last consulted for this post.
-- `comment_count` is stored at sync time so that the application can detect
-- new comment activity by comparing it against the live count on the next run.
-- `is_video` stores 1 if the post is a video, 0 otherwise (SQLite boolean).
-- `flair` is nullable because not all posts carry a flair.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS collected_posts (
    state_key      TEXT    NOT NULL PRIMARY KEY,  -- "{post_id}:{subreddit}:{rule_name}"
    post_id        TEXT    NOT NULL,
    subreddit      TEXT    NOT NULL,
    rule_name      TEXT    NOT NULL,
    title          TEXT    NOT NULL,
    author         TEXT    NOT NULL,
    score          INTEGER NOT NULL DEFAULT 0,
    comment_count  INTEGER NOT NULL DEFAULT 0,
    url            TEXT    NOT NULL,
    is_video       INTEGER NOT NULL DEFAULT 0,    -- BOOLEAN (0/1)
    flair          TEXT,                          -- nullable: not all posts have flair
    word_count     INTEGER NOT NULL DEFAULT 0,
    output_path    TEXT    NOT NULL,
    status         TEXT    NOT NULL DEFAULT 'ok',
    created_at     TEXT    NOT NULL,              -- ISO-8601, set on first collection
    updated_at     TEXT    NOT NULL,              -- ISO-8601, updated on every write
    synced_at      TEXT    NOT NULL               -- ISO-8601, set locally on each API sync
);

CREATE INDEX IF NOT EXISTS idx_collected_posts_rule_name  ON collected_posts (rule_name);
CREATE INDEX IF NOT EXISTS idx_collected_posts_subreddit  ON collected_posts (subreddit);
CREATE INDEX IF NOT EXISTS idx_collected_posts_post_id    ON collected_posts (post_id);

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
