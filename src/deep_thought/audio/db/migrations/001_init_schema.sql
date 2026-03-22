-- Migration: 001_init_schema
-- Audio tool: tracks processed files and their transcription state

CREATE TABLE IF NOT EXISTS processed_files (
    file_path         TEXT    NOT NULL PRIMARY KEY,
    file_hash         TEXT    NOT NULL,
    engine            TEXT    NOT NULL,
    model             TEXT    NOT NULL,
    duration_seconds  REAL,
    speaker_count     INTEGER DEFAULT 0,
    output_path       TEXT,
    status            TEXT    NOT NULL DEFAULT 'pending',
    created_at        TEXT    NOT NULL,
    updated_at        TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_processed_files_status ON processed_files (status);
CREATE INDEX IF NOT EXISTS idx_processed_files_file_hash ON processed_files (file_hash);

CREATE TABLE IF NOT EXISTS key_value (
    key        TEXT NOT NULL PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
