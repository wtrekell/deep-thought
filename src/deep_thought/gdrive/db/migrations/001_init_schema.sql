-- Migration: 001_init_schema.sql
-- Description: Initial schema for the GDrive backup tool
-- Preconditions: None — this is the first migration
-- Note: PRAGMA statements (journal_mode, foreign_keys) are intentionally
-- absent here. They cannot run inside a transaction, and they are already
-- applied by init_db() before migrations execute.

-- ---------------------------------------------------------------------------
-- backed_up_files
-- Tracks every file that has been uploaded or updated on Google Drive.
--
-- `local_path` is relative to the parent of the configured source_dir,
-- so it includes the source directory name as the first path segment.
-- This is the canonical identifier used to detect new vs. updated files.
--
-- `mtime` is the POSIX modification timestamp of the file at the time it
-- was last backed up. Used to detect whether the file has changed.
--
-- `status` is one of: uploaded, updated, skipped, error.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS backed_up_files (
    local_path      TEXT    NOT NULL PRIMARY KEY,
    drive_file_id   TEXT    NOT NULL,
    drive_folder_id TEXT    NOT NULL,
    mtime           REAL    NOT NULL,
    size_bytes      INTEGER NOT NULL,
    status          TEXT    NOT NULL,
    uploaded_at     TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL
);

-- ---------------------------------------------------------------------------
-- drive_folders
-- Caches the mapping from local relative directory path to Drive folder ID.
-- Avoids redundant API calls to look up or create folders on every run.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS drive_folders (
    local_path      TEXT NOT NULL PRIMARY KEY,
    drive_folder_id TEXT NOT NULL
);

-- ---------------------------------------------------------------------------
-- key_value
-- General-purpose key/value store for tool metadata:
--   schema_version  — current migration number (integer stored as text)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS key_value (
    key   TEXT NOT NULL PRIMARY KEY,
    value TEXT NOT NULL
);

INSERT OR IGNORE INTO key_value (key, value) VALUES ('schema_version', '1');
