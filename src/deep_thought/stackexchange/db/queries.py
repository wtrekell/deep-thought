"""
queries.py — Parameterized SQL query functions for the Stack Exchange Tool database layer.

All functions accept an open sqlite3.Connection as their first argument and
return plain Python types (dicts, lists, None). No business logic lives here —
these are thin wrappers over SQL that the application layer calls directly.

Callers are responsible for committing transactions. Write functions
(upsert_collected_question, delete_all_questions, delete_questions_by_rule,
upsert_quota_usage, set_key_value) execute SQL but do NOT call conn.commit().
The caller must commit after all writes for a logical unit of work are complete.
This allows multiple writes to be batched into a single transaction for atomicity
and performance.

Upsert strategy: INSERT ... ON CONFLICT(state_key) DO UPDATE SET is used so
that the original `created_at` timestamp is preserved across re-processing.

Timestamps:
- `updated_at` is set to now on every write, since every upsert reflects
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
# Collected questions
# ---------------------------------------------------------------------------


def upsert_collected_question(conn: sqlite3.Connection, question_dict: dict[str, Any]) -> None:
    """Insert or update a collected question row. Sets updated_at to now.

    Uses INSERT ... ON CONFLICT(state_key) DO UPDATE SET so that the original
    ``created_at`` timestamp is preserved across re-processing. All other
    mutable columns are overwritten with the incoming values.

    The state_key must be pre-constructed by the caller as:
        "{question_id}:{site}:{rule_name}"

    Args:
        conn: An open SQLite connection.
        question_dict: Dict with keys matching the collected_questions table columns.
                       Required keys: state_key, question_id, site, rule_name,
                       title, link, tags, score, answer_count, accepted_answer_id,
                       output_path, status, created_at.
    """
    now_iso = _now_utc_iso()
    conn.execute(
        """
        INSERT INTO collected_questions (
            state_key,
            question_id,
            site,
            rule_name,
            title,
            link,
            tags,
            score,
            answer_count,
            accepted_answer_id,
            output_path,
            status,
            created_at,
            updated_at
        ) VALUES (
            :state_key,
            :question_id,
            :site,
            :rule_name,
            :title,
            :link,
            :tags,
            :score,
            :answer_count,
            :accepted_answer_id,
            :output_path,
            :status,
            :created_at,
            :updated_at
        )
        ON CONFLICT(state_key) DO UPDATE SET
            question_id        = excluded.question_id,
            site               = excluded.site,
            rule_name          = excluded.rule_name,
            title              = excluded.title,
            link               = excluded.link,
            tags               = excluded.tags,
            score              = excluded.score,
            answer_count       = excluded.answer_count,
            accepted_answer_id = excluded.accepted_answer_id,
            output_path        = excluded.output_path,
            status             = excluded.status,
            updated_at         = excluded.updated_at;
        """,
        {**question_dict, "updated_at": now_iso},
    )


def get_collected_question(conn: sqlite3.Connection, state_key: str) -> dict[str, Any] | None:
    """Return a single collected question by its state_key, or None if not found.

    Args:
        conn: An open SQLite connection.
        state_key: The composite key "{question_id}:{site}:{rule_name}".

    Returns:
        A dict of column values, or None if no matching row exists.
    """
    cursor = conn.execute(
        "SELECT * FROM collected_questions WHERE state_key = ?;",
        (state_key,),
    )
    return _row_to_dict(cursor.fetchone())


def get_questions_by_rule(conn: sqlite3.Connection, rule_name: str) -> list[dict[str, Any]]:
    """Return all collected questions for a given rule, ordered by created_at ascending.

    Args:
        conn: An open SQLite connection.
        rule_name: The name of the collection rule to filter on.

    Returns:
        List of question dicts. Empty list if no questions exist for this rule.
    """
    cursor = conn.execute(
        "SELECT * FROM collected_questions WHERE rule_name = ? ORDER BY created_at ASC;",
        (rule_name,),
    )
    return _rows_to_dicts(cursor.fetchall())


def get_questions_by_site(conn: sqlite3.Connection, site: str) -> list[dict[str, Any]]:
    """Return all collected questions for a given site, ordered by created_at ascending.

    Args:
        conn: An open SQLite connection.
        site: The Stack Exchange site name to filter on (e.g., "stackoverflow").

    Returns:
        List of question dicts. Empty list if no questions exist for this site.
    """
    cursor = conn.execute(
        "SELECT * FROM collected_questions WHERE site = ? ORDER BY created_at ASC;",
        (site,),
    )
    return _rows_to_dicts(cursor.fetchall())


def get_all_collected_questions(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Return all collected questions ordered by created_at ascending.

    Args:
        conn: An open SQLite connection.

    Returns:
        List of question dicts. Empty list if the table is empty.
    """
    cursor = conn.execute("SELECT * FROM collected_questions ORDER BY created_at ASC;")
    return _rows_to_dicts(cursor.fetchall())


def delete_all_questions(conn: sqlite3.Connection) -> int:
    """Delete all rows from collected_questions. Used by the --force flag.

    Args:
        conn: An open SQLite connection.

    Returns:
        The number of rows deleted.
    """
    cursor = conn.execute("DELETE FROM collected_questions;")
    return cursor.rowcount


def delete_questions_by_rule(conn: sqlite3.Connection, rule_name: str) -> int:
    """Delete all collected questions for a given rule. Used by targeted --force.

    Args:
        conn: An open SQLite connection.
        rule_name: The name of the collection rule whose questions should be deleted.

    Returns:
        The number of rows deleted.
    """
    cursor = conn.execute(
        "DELETE FROM collected_questions WHERE rule_name = ?;",
        (rule_name,),
    )
    return cursor.rowcount


# ---------------------------------------------------------------------------
# Quota usage
# ---------------------------------------------------------------------------


def upsert_quota_usage(
    conn: sqlite3.Connection,
    date: str,
    requests_used: int,
    quota_remaining: int,
) -> None:
    """Insert or update daily API quota usage for the given date.

    On conflict with an existing date row, increments requests_used by the
    incoming value and overwrites quota_remaining with the latest observed value.

    Args:
        conn: An open SQLite connection.
        date: ISO date string (YYYY-MM-DD) identifying the day.
        requests_used: Number of API requests made in this batch (additive).
        quota_remaining: The latest quota_remaining value from the API response.
    """
    now_iso = _now_utc_iso()
    conn.execute(
        """
        INSERT INTO quota_usage (date, requests_used, quota_remaining, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(date) DO UPDATE SET
            requests_used   = quota_usage.requests_used + excluded.requests_used,
            quota_remaining = excluded.quota_remaining,
            updated_at      = excluded.updated_at;
        """,
        (date, requests_used, quota_remaining, now_iso, now_iso),
    )


def get_quota_usage(conn: sqlite3.Connection, date: str) -> dict[str, Any] | None:
    """Return quota usage for a specific date, or None if no record exists.

    Args:
        conn: An open SQLite connection.
        date: ISO date string (YYYY-MM-DD).

    Returns:
        A dict of column values, or None if no record exists for that date.
    """
    cursor = conn.execute(
        "SELECT * FROM quota_usage WHERE date = ?;",
        (date,),
    )
    return _row_to_dict(cursor.fetchone())


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
