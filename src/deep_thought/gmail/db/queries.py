"""Parameterized SQL query functions for the Gmail Tool database layer.

All functions accept an open sqlite3.Connection as their first argument and
return plain Python types (dicts, lists, None). No business logic lives here —
these are thin wrappers over SQL that the application layer calls directly.

Transaction boundaries:
    These functions execute SQL statements but do NOT call conn.commit().
    Callers are responsible for transaction management — commit after a logical
    batch of operations (e.g., end of a collection run) or rollback on error.
    Forgetting to commit means writes will be lost when the connection closes.

Upsert strategy: INSERT ... ON CONFLICT DO UPDATE SET is used so that the
original `created_at` timestamp is preserved across re-processing.

Timestamps:
- `synced_at` is set to the current UTC time at the moment of the write,
  marking when the local database last received data from the Gmail API.
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
# Processed emails
# ---------------------------------------------------------------------------


def upsert_processed_email(conn: sqlite3.Connection, email_dict: dict[str, Any]) -> None:
    """Insert or update a processed email row. Sets updated_at and synced_at to now.

    Uses INSERT ... ON CONFLICT(message_id) DO UPDATE SET so that the original
    ``created_at`` timestamp is preserved across re-processing. All other
    mutable columns are overwritten with the incoming values.

    Args:
        conn: An open SQLite connection.
        email_dict: Dict with keys matching the processed_emails table columns.
                    Required keys: message_id, rule_name, subject, from_address,
                    output_path, created_at.
                    Optional keys: actions_taken, status.
    """
    now_iso = _now_utc_iso()
    conn.execute(
        """
        INSERT INTO processed_emails (
            message_id,
            rule_name,
            subject,
            from_address,
            output_path,
            actions_taken,
            status,
            created_at,
            updated_at,
            synced_at
        ) VALUES (
            :message_id,
            :rule_name,
            :subject,
            :from_address,
            :output_path,
            :actions_taken,
            :status,
            :created_at,
            :updated_at,
            :synced_at
        )
        ON CONFLICT(message_id) DO UPDATE SET
            rule_name     = excluded.rule_name,
            subject       = excluded.subject,
            from_address  = excluded.from_address,
            output_path   = excluded.output_path,
            actions_taken = excluded.actions_taken,
            status        = excluded.status,
            updated_at    = excluded.updated_at,
            synced_at     = excluded.synced_at;
        """,
        {**email_dict, "updated_at": now_iso, "synced_at": now_iso},
    )


def get_processed_email(conn: sqlite3.Connection, message_id: str) -> dict[str, Any] | None:
    """Return a single processed email by its message_id, or None if not found.

    Args:
        conn: An open SQLite connection.
        message_id: The Gmail message ID to look up.

    Returns:
        A dict of column values, or None if no matching row exists.
    """
    cursor = conn.execute(
        "SELECT * FROM processed_emails WHERE message_id = ?;",
        (message_id,),
    )
    return _row_to_dict(cursor.fetchone())


def get_emails_by_rule(conn: sqlite3.Connection, rule_name: str) -> list[dict[str, Any]]:
    """Return all processed emails for a given rule, ordered by created_at ascending.

    Args:
        conn: An open SQLite connection.
        rule_name: The name of the collection rule to filter on.

    Returns:
        List of email dicts. Empty list if no emails exist for this rule.
    """
    cursor = conn.execute(
        "SELECT * FROM processed_emails WHERE rule_name = ? ORDER BY created_at ASC;",
        (rule_name,),
    )
    return _rows_to_dicts(cursor.fetchall())


def get_all_processed_emails(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Return all processed emails ordered by created_at ascending.

    Args:
        conn: An open SQLite connection.

    Returns:
        List of email dicts. Empty list if the table is empty.
    """
    cursor = conn.execute("SELECT * FROM processed_emails ORDER BY created_at ASC;")
    return _rows_to_dicts(cursor.fetchall())


def delete_all_emails(conn: sqlite3.Connection) -> int:
    """Delete all rows from processed_emails. Used by the --force flag.

    Args:
        conn: An open SQLite connection.

    Returns:
        The number of rows deleted.
    """
    cursor = conn.execute("DELETE FROM processed_emails;")
    return cursor.rowcount


def delete_emails_by_rule(conn: sqlite3.Connection, rule_name: str) -> int:
    """Delete all processed emails for a given rule. Used by targeted --force.

    Args:
        conn: An open SQLite connection.
        rule_name: The name of the collection rule whose emails should be deleted.

    Returns:
        The number of rows deleted.
    """
    cursor = conn.execute(
        "DELETE FROM processed_emails WHERE rule_name = ?;",
        (rule_name,),
    )
    return cursor.rowcount


# ---------------------------------------------------------------------------
# Decision cache
# ---------------------------------------------------------------------------


def upsert_decision_cache(conn: sqlite3.Connection, cache_dict: dict[str, Any]) -> None:
    """Insert or update a decision cache entry. Sets updated_at to now.

    Uses INSERT ... ON CONFLICT(cache_key) DO UPDATE SET so that the original
    ``created_at`` timestamp is preserved.

    Args:
        conn: An open SQLite connection.
        cache_dict: Dict with keys matching the decision_cache table columns.
                    Required keys: cache_key, decision, ttl_seconds, created_at.
    """
    now_iso = _now_utc_iso()
    conn.execute(
        """
        INSERT INTO decision_cache (
            cache_key,
            decision,
            ttl_seconds,
            created_at,
            updated_at
        ) VALUES (
            :cache_key,
            :decision,
            :ttl_seconds,
            :created_at,
            :updated_at
        )
        ON CONFLICT(cache_key) DO UPDATE SET
            decision    = excluded.decision,
            ttl_seconds = excluded.ttl_seconds,
            updated_at  = excluded.updated_at;
        """,
        {**cache_dict, "updated_at": now_iso},
    )


def get_decision_cache(conn: sqlite3.Connection, cache_key: str) -> dict[str, Any] | None:
    """Return a single decision cache entry by its cache_key, or None if not found.

    Does NOT check TTL expiry — the caller is responsible for comparing
    created_at + ttl_seconds against the current time.

    Args:
        conn: An open SQLite connection.
        cache_key: The cache key to look up.

    Returns:
        A dict of column values, or None if no matching row exists.
    """
    cursor = conn.execute(
        "SELECT * FROM decision_cache WHERE cache_key = ?;",
        (cache_key,),
    )
    return _row_to_dict(cursor.fetchone())


def get_expired_cache_entries(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Return all decision cache entries whose TTL has expired.

    An entry is expired when the current UTC time exceeds
    created_at + ttl_seconds. SQLite's datetime functions handle
    the ISO-8601 string arithmetic.

    Args:
        conn: An open SQLite connection.

    Returns:
        List of expired cache entry dicts.
    """
    now_iso = _now_utc_iso()
    cursor = conn.execute(
        """
        SELECT * FROM decision_cache
        WHERE datetime(created_at, '+' || ttl_seconds || ' seconds') < datetime(?);
        """,
        (now_iso,),
    )
    return _rows_to_dicts(cursor.fetchall())


def delete_expired_cache(conn: sqlite3.Connection) -> int:
    """Delete all decision cache entries whose TTL has expired.

    Args:
        conn: An open SQLite connection.

    Returns:
        The number of rows deleted.
    """
    now_iso = _now_utc_iso()
    cursor = conn.execute(
        """
        DELETE FROM decision_cache
        WHERE datetime(created_at, '+' || ttl_seconds || ' seconds') < datetime(?);
        """,
        (now_iso,),
    )
    return cursor.rowcount


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
