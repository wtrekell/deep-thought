"""Parameterized SQL query functions for the GCal Tool database layer.

All functions accept an open sqlite3.Connection as their first argument and
return plain Python types (dicts, lists, None). No business logic lives here —
these are thin wrappers over SQL that the application layer calls directly.

Upsert strategy: INSERT ... ON CONFLICT DO UPDATE SET is used so that the
original `created_at` timestamp is preserved across re-syncing.

Timestamps:
- `synced_at` is set to the current UTC time at the moment of the write,
  marking when the local database last received data from the Calendar API.
- `updated_at` is also set to now on every write, since every upsert reflects
  a change in the locally stored state.
- `created_at` is set on first insertion and excluded from the ON CONFLICT
  UPDATE clause so it is never overwritten by subsequent upserts.
"""

from __future__ import annotations

import sqlite3  # noqa: TC003 — sqlite3.Row is used at runtime in _row_to_dict/_rows_to_dicts
from datetime import UTC, datetime
from typing import Any

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _now_utc_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(UTC).isoformat()


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    """Convert a sqlite3.Row to a plain dict, or return None if the row is None."""
    if row is None:
        return None
    return dict(row)


def _rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    """Convert a list of sqlite3.Row objects to a list of plain dicts."""
    return [dict(row) for row in rows]


# ---------------------------------------------------------------------------
# Calendars
# ---------------------------------------------------------------------------


def upsert_calendar(conn: sqlite3.Connection, calendar_dict: dict[str, Any]) -> None:
    """Insert or update a calendar row. Sets updated_at and synced_at to now.

    Uses INSERT ... ON CONFLICT(calendar_id) DO UPDATE SET so that the original
    ``created_at`` timestamp is preserved across re-syncing.

    Args:
        conn: An open SQLite connection.
        calendar_dict: Dict with keys matching the calendars table columns.
                       Required keys: calendar_id, summary, time_zone, created_at.
    """
    now_iso = _now_utc_iso()
    conn.execute(
        """
        INSERT INTO calendars (
            calendar_id, summary, description, time_zone,
            primary_calendar, created_at, updated_at, synced_at
        ) VALUES (
            :calendar_id, :summary, :description, :time_zone,
            :primary_calendar, :created_at, :updated_at, :synced_at
        )
        ON CONFLICT(calendar_id) DO UPDATE SET
            summary          = excluded.summary,
            description      = excluded.description,
            time_zone        = excluded.time_zone,
            primary_calendar = excluded.primary_calendar,
            updated_at       = excluded.updated_at,
            synced_at        = excluded.synced_at;
        """,
        {**calendar_dict, "updated_at": now_iso, "synced_at": now_iso},
    )


def get_calendar(conn: sqlite3.Connection, calendar_id: str) -> dict[str, Any] | None:
    """Return a single calendar by its calendar_id, or None if not found.

    Args:
        conn: An open SQLite connection.
        calendar_id: The Google Calendar ID to look up.

    Returns:
        A dict of column values, or None if no matching row exists.
    """
    cursor = conn.execute("SELECT * FROM calendars WHERE calendar_id = ?;", (calendar_id,))
    return _row_to_dict(cursor.fetchone())


def get_all_calendars(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Return all calendars, ordered by primary_calendar DESC then summary ASC.

    Args:
        conn: An open SQLite connection.

    Returns:
        List of calendar dicts. Empty list if the table is empty.
    """
    cursor = conn.execute("SELECT * FROM calendars ORDER BY primary_calendar DESC, summary ASC;")
    return _rows_to_dicts(cursor.fetchall())


def delete_calendar(conn: sqlite3.Connection, calendar_id: str) -> int:
    """Delete a calendar row. CASCADE removes its events and sync_state.

    Args:
        conn: An open SQLite connection.
        calendar_id: The Google Calendar ID to delete.

    Returns:
        The number of rows deleted (0 or 1).
    """
    cursor = conn.execute("DELETE FROM calendars WHERE calendar_id = ?;", (calendar_id,))
    return cursor.rowcount


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------


def upsert_event(conn: sqlite3.Connection, event_dict: dict[str, Any]) -> None:
    """Insert or update an event row. Sets synced_at to now.

    Uses INSERT ... ON CONFLICT(event_id, calendar_id) DO UPDATE SET so that
    the original ``created_at`` timestamp is preserved across re-syncing.
    The ``updated_at`` field comes from the Google API response, not from now.

    Args:
        conn: An open SQLite connection.
        event_dict: Dict with keys matching the events table columns.
                    Required keys: event_id, calendar_id, summary, start_time,
                    end_time, created_at, updated_at.
    """
    now_iso = _now_utc_iso()
    conn.execute(
        """
        INSERT INTO events (
            event_id, calendar_id, summary, description, location,
            start_time, end_time, all_day, status, organizer,
            attendees, recurrence, html_link,
            created_at, updated_at, synced_at
        ) VALUES (
            :event_id, :calendar_id, :summary, :description, :location,
            :start_time, :end_time, :all_day, :status, :organizer,
            :attendees, :recurrence, :html_link,
            :created_at, :updated_at, :synced_at
        )
        ON CONFLICT(event_id, calendar_id) DO UPDATE SET
            summary     = excluded.summary,
            description = excluded.description,
            location    = excluded.location,
            start_time  = excluded.start_time,
            end_time    = excluded.end_time,
            all_day     = excluded.all_day,
            status      = excluded.status,
            organizer   = excluded.organizer,
            attendees   = excluded.attendees,
            recurrence  = excluded.recurrence,
            html_link   = excluded.html_link,
            updated_at  = excluded.updated_at,
            synced_at   = excluded.synced_at;
        """,
        {**event_dict, "synced_at": now_iso},
    )


def get_event(conn: sqlite3.Connection, event_id: str, calendar_id: str) -> dict[str, Any] | None:
    """Return a single event by its composite primary key, or None if not found.

    Args:
        conn: An open SQLite connection.
        event_id: The Google Calendar event ID.
        calendar_id: The calendar the event belongs to.

    Returns:
        A dict of column values, or None if no matching row exists.
    """
    cursor = conn.execute(
        "SELECT * FROM events WHERE event_id = ? AND calendar_id = ?;",
        (event_id, calendar_id),
    )
    return _row_to_dict(cursor.fetchone())


def get_events_by_calendar(conn: sqlite3.Connection, calendar_id: str) -> list[dict[str, Any]]:
    """Return all events for a given calendar, ordered by start_time ascending.

    Args:
        conn: An open SQLite connection.
        calendar_id: The calendar to filter on.

    Returns:
        List of event dicts. Empty list if no events exist for this calendar.
    """
    cursor = conn.execute(
        "SELECT * FROM events WHERE calendar_id = ? ORDER BY start_time ASC;",
        (calendar_id,),
    )
    return _rows_to_dicts(cursor.fetchall())


def get_events_in_range(
    conn: sqlite3.Connection, calendar_id: str, start_time: str, end_time: str
) -> list[dict[str, Any]]:
    """Return events within a time window for a calendar, ordered by start_time.

    Args:
        conn: An open SQLite connection.
        calendar_id: The calendar to filter on.
        start_time: ISO 8601 lower bound (inclusive).
        end_time: ISO 8601 upper bound (exclusive).

    Returns:
        List of event dicts within the range.
    """
    cursor = conn.execute(
        "SELECT * FROM events WHERE calendar_id = ? AND start_time >= ? AND start_time < ? ORDER BY start_time ASC;",
        (calendar_id, start_time, end_time),
    )
    return _rows_to_dicts(cursor.fetchall())


def get_all_events(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Return all events across all calendars, ordered by start_time ascending.

    Args:
        conn: An open SQLite connection.

    Returns:
        List of event dicts. Empty list if the table is empty.
    """
    cursor = conn.execute("SELECT * FROM events ORDER BY start_time ASC;")
    return _rows_to_dicts(cursor.fetchall())


def delete_event(conn: sqlite3.Connection, event_id: str, calendar_id: str) -> int:
    """Delete a single event by its composite primary key.

    Args:
        conn: An open SQLite connection.
        event_id: The Google Calendar event ID.
        calendar_id: The calendar the event belongs to.

    Returns:
        The number of rows deleted (0 or 1).
    """
    cursor = conn.execute(
        "DELETE FROM events WHERE event_id = ? AND calendar_id = ?;",
        (event_id, calendar_id),
    )
    return cursor.rowcount


def delete_events_by_calendar(conn: sqlite3.Connection, calendar_id: str) -> int:
    """Delete all events for a given calendar.

    Args:
        conn: An open SQLite connection.
        calendar_id: The calendar whose events should be deleted.

    Returns:
        The number of rows deleted.
    """
    cursor = conn.execute("DELETE FROM events WHERE calendar_id = ?;", (calendar_id,))
    return cursor.rowcount


def get_cancelled_events(conn: sqlite3.Connection, calendar_id: str) -> list[dict[str, Any]]:
    """Return all cancelled events for a calendar.

    Args:
        conn: An open SQLite connection.
        calendar_id: The calendar to filter on.

    Returns:
        List of event dicts with status 'cancelled'.
    """
    cursor = conn.execute(
        "SELECT * FROM events WHERE calendar_id = ? AND status = 'cancelled' ORDER BY start_time ASC;",
        (calendar_id,),
    )
    return _rows_to_dicts(cursor.fetchall())


# ---------------------------------------------------------------------------
# Sync state
# ---------------------------------------------------------------------------


def upsert_sync_state(conn: sqlite3.Connection, calendar_id: str, sync_token: str | None, last_sync_time: str) -> None:
    """Insert or update the sync state for a calendar.

    Args:
        conn: An open SQLite connection.
        calendar_id: The calendar this sync state belongs to.
        sync_token: The nextSyncToken from the Calendar API, or None.
        last_sync_time: ISO 8601 timestamp of when the sync completed.
    """
    conn.execute(
        """
        INSERT INTO sync_state (calendar_id, sync_token, last_sync_time)
        VALUES (?, ?, ?)
        ON CONFLICT(calendar_id) DO UPDATE SET
            sync_token     = excluded.sync_token,
            last_sync_time = excluded.last_sync_time;
        """,
        (calendar_id, sync_token, last_sync_time),
    )


def get_sync_state(conn: sqlite3.Connection, calendar_id: str) -> dict[str, Any] | None:
    """Return the sync state for a calendar, or None if not found.

    Args:
        conn: An open SQLite connection.
        calendar_id: The calendar to look up.

    Returns:
        A dict with sync_token and last_sync_time, or None.
    """
    cursor = conn.execute("SELECT * FROM sync_state WHERE calendar_id = ?;", (calendar_id,))
    return _row_to_dict(cursor.fetchone())


def clear_sync_token(conn: sqlite3.Connection, calendar_id: str) -> None:
    """Clear the sync token for a calendar (e.g., on HTTP 410 Gone).

    Args:
        conn: An open SQLite connection.
        calendar_id: The calendar whose sync token should be cleared.
    """
    conn.execute(
        "UPDATE sync_state SET sync_token = NULL WHERE calendar_id = ?;",
        (calendar_id,),
    )


def clear_all_sync_tokens(conn: sqlite3.Connection) -> None:
    """Clear all sync tokens. Used by the --force flag.

    Args:
        conn: An open SQLite connection.
    """
    conn.execute("UPDATE sync_state SET sync_token = NULL;")


# ---------------------------------------------------------------------------
# Key/value store
# ---------------------------------------------------------------------------


def get_key_value(conn: sqlite3.Connection, key: str) -> str | None:
    """Read a value from the key_value store.

    Args:
        conn: An open SQLite connection.
        key: The key to look up (e.g., 'schema_version').

    Returns:
        The stored string value, or None if the key does not exist.
    """
    cursor = conn.execute("SELECT value FROM key_value WHERE key = ?;", (key,))
    row = cursor.fetchone()
    return row["value"] if row is not None else None


def set_key_value(conn: sqlite3.Connection, key: str, value: str) -> None:
    """Write or overwrite a value in the key_value store.

    Args:
        conn: An open SQLite connection.
        key: The key to write.
        value: The string value to store.
    """
    conn.execute(
        """
        INSERT INTO key_value (key, value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT (key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at;
        """,
        (key, value, _now_utc_iso()),
    )
