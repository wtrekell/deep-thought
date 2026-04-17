-- Migration: 003_backfill_schema_version_updated_at.sql
-- Description: Backfill updated_at on the schema_version row in key_value for
--              databases where migration 002 left it NULL.
-- Preconditions: Migration 002 has been applied (updated_at column exists).

UPDATE key_value
SET updated_at = datetime('now')
WHERE key = 'schema_version'
  AND updated_at IS NULL;
