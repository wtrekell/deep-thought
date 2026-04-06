-- Migration: 002_add_timestamps.sql
-- Description: Add created_at, updated_at, synced_at columns to drive_folders
--              and key_value tables to comply with the shared SQLite convention
--              documented in src/CLAUDE.md.
-- Preconditions: Migration 001 has been applied.

-- SQLite does not allow non-constant defaults in ALTER TABLE ADD COLUMN.
-- Existing rows receive NULL for these columns; new rows should set them
-- explicitly in application code (as all other tools do on insert/upsert).
ALTER TABLE drive_folders ADD COLUMN created_at TEXT;
ALTER TABLE drive_folders ADD COLUMN updated_at TEXT;
ALTER TABLE drive_folders ADD COLUMN synced_at  TEXT;

ALTER TABLE key_value ADD COLUMN created_at TEXT;
ALTER TABLE key_value ADD COLUMN updated_at TEXT;
ALTER TABLE key_value ADD COLUMN synced_at  TEXT;

UPDATE key_value SET value = '2' WHERE key = 'schema_version';
