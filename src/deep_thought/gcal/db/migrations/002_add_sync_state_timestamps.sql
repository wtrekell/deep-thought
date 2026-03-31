-- Migration: 002_add_sync_state_timestamps.sql
-- Description: Add updated_at and synced_at columns to sync_state
-- Preconditions: Migration 001 must have been applied

-- Add updated_at column with a default of the current timestamp placeholder.
-- SQLite does not support DEFAULT (strftime(...)) as a dynamic expression in
-- ALTER TABLE, so we default to the epoch and let application writes fill in
-- the real value going forward. Existing rows get the epoch placeholder.
ALTER TABLE sync_state ADD COLUMN updated_at TEXT NOT NULL DEFAULT '1970-01-01T00:00:00+00:00';
ALTER TABLE sync_state ADD COLUMN synced_at  TEXT NOT NULL DEFAULT '1970-01-01T00:00:00+00:00';
