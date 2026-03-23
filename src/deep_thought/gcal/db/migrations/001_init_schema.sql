-- Migration: 001_init_schema.sql
-- Description: Initial schema for the GCal Tool
-- Preconditions: None — this is the first migration
-- Note: PRAGMA statements (journal_mode, foreign_keys) are intentionally
-- absent here. They cannot run inside a transaction, and they are already
-- applied by get_connection() before migrations execute.

-- ---------------------------------------------------------------------------
-- calendars
-- Tracks each Google Calendar the user has configured for sync.
--
-- `calendar_id` is the Google Calendar ID (e.g., "primary" or a full email).
-- `primary_calendar` is 1 if this is the user's main calendar, 0 otherwise.
-- `time_zone` is the IANA time zone string (e.g., "America/Chicago").
-- `created_at` records when this calendar was first synced locally.
-- `updated_at` records when any field on this row was last changed.
-- `synced_at` records when the Calendar API was last consulted.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS calendars (
    calendar_id      TEXT    NOT NULL PRIMARY KEY,
    summary          TEXT    NOT NULL,
    description      TEXT,
    time_zone        TEXT    NOT NULL,
    primary_calendar INTEGER NOT NULL DEFAULT 0,
    created_at       TEXT    NOT NULL,
    updated_at       TEXT    NOT NULL,
    synced_at        TEXT    NOT NULL
);

-- ---------------------------------------------------------------------------
-- events
-- Tracks every calendar event pulled from Google Calendar.
--
-- Composite primary key: (event_id, calendar_id) because the same event_id
-- could theoretically appear in different calendars (e.g., shared events).
--
-- `all_day` is 1 for all-day events (using date), 0 for timed events (using dateTime).
-- `attendees` is a JSON-serialized list of attendee objects.
-- `recurrence` is a JSON-serialized list of RRULE strings.
-- `created_at` records when this event was first synced locally.
-- `updated_at` records the Google-provided `updated` timestamp.
-- `synced_at` records when the Calendar API was last consulted for this event.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS events (
    event_id    TEXT    NOT NULL,
    calendar_id TEXT    NOT NULL,
    summary     TEXT    NOT NULL,
    description TEXT,
    location    TEXT,
    start_time  TEXT    NOT NULL,
    end_time    TEXT    NOT NULL,
    all_day     INTEGER NOT NULL DEFAULT 0,
    status      TEXT    NOT NULL DEFAULT 'confirmed',
    organizer   TEXT,
    attendees   TEXT,
    recurrence  TEXT,
    html_link   TEXT,
    created_at  TEXT    NOT NULL,
    updated_at  TEXT    NOT NULL,
    synced_at   TEXT    NOT NULL,
    PRIMARY KEY (event_id, calendar_id),
    FOREIGN KEY (calendar_id) REFERENCES calendars (calendar_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_events_calendar_id ON events (calendar_id);
CREATE INDEX IF NOT EXISTS idx_events_start_time ON events (start_time);

-- ---------------------------------------------------------------------------
-- sync_state
-- Stores the Calendar API sync token per calendar for incremental pulls.
--
-- `sync_token` is the nextSyncToken from the last successful events.list call.
-- `last_sync_time` records when the last sync completed.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sync_state (
    calendar_id    TEXT NOT NULL PRIMARY KEY,
    sync_token     TEXT,
    last_sync_time TEXT,
    FOREIGN KEY (calendar_id) REFERENCES calendars (calendar_id) ON DELETE CASCADE
);

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
