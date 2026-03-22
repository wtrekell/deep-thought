"""
queries.py — Parameterized SQL query functions for the Reddit Tool database layer.

All functions accept an open sqlite3.Connection as their first argument and
return plain Python types (dicts, lists, None). No business logic lives here —
these are thin wrappers over SQL that the application layer calls directly.

Upsert strategy: INSERT OR REPLACE replaces the entire row when the primary
key conflicts. This is safe because we always provide all columns.

Timestamps:
- `synced_at` is always set to the current UTC time at the moment of the write,
  marking when the local database last received data from the Reddit API.
- `updated_at` is also set to now on every write, since every upsert reflects
  a change in the locally stored state.
- `created_at` is passed in from the caller's data dict on first insertion.
  INSERT OR REPLACE will overwrite it on subsequent upserts, so callers must
  supply the original created_at value when updating an existing post.
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
# Collected posts
# ---------------------------------------------------------------------------


def upsert_collected_post(conn: sqlite3.Connection, post_dict: dict[str, Any]) -> None:
    """Insert or replace a collected post row. Sets updated_at and synced_at to now.

    Uses INSERT OR REPLACE, which replaces the entire row on primary key
    conflict (state_key). The caller must supply created_at in post_dict so
    that the original collection timestamp is preserved across updates.

    The state_key must be pre-constructed by the caller as:
        "{post_id}:{subreddit}:{rule_name}"

    Args:
        conn: An open SQLite connection.
        post_dict: Dict with keys matching the collected_posts table columns.
                   Required keys: state_key, post_id, subreddit, rule_name,
                   title, author, url, output_path, created_at.
                   Optional keys: score, comment_count, is_video, flair,
                   word_count, status.
    """
    now_iso = _now_utc_iso()
    conn.execute(
        """
        INSERT OR REPLACE INTO collected_posts (
            state_key,
            post_id,
            subreddit,
            rule_name,
            title,
            author,
            score,
            comment_count,
            url,
            is_video,
            flair,
            word_count,
            output_path,
            status,
            created_at,
            updated_at,
            synced_at
        ) VALUES (
            :state_key,
            :post_id,
            :subreddit,
            :rule_name,
            :title,
            :author,
            :score,
            :comment_count,
            :url,
            :is_video,
            :flair,
            :word_count,
            :output_path,
            :status,
            :created_at,
            :updated_at,
            :synced_at
        );
        """,
        {**post_dict, "updated_at": now_iso, "synced_at": now_iso},
    )


def get_collected_post(conn: sqlite3.Connection, state_key: str) -> dict[str, Any] | None:
    """Return a single collected post by its state_key, or None if not found.

    Args:
        conn: An open SQLite connection.
        state_key: The composite key "{post_id}:{subreddit}:{rule_name}".

    Returns:
        A dict of column values, or None if no matching row exists.
    """
    cursor = conn.execute(
        "SELECT * FROM collected_posts WHERE state_key = ?;",
        (state_key,),
    )
    return _row_to_dict(cursor.fetchone())


def get_posts_by_rule(conn: sqlite3.Connection, rule_name: str) -> list[dict[str, Any]]:
    """Return all collected posts for a given rule, ordered by created_at ascending.

    Args:
        conn: An open SQLite connection.
        rule_name: The name of the collection rule to filter on.

    Returns:
        List of post dicts. Empty list if no posts exist for this rule.
    """
    cursor = conn.execute(
        "SELECT * FROM collected_posts WHERE rule_name = ? ORDER BY created_at ASC;",
        (rule_name,),
    )
    return _rows_to_dicts(cursor.fetchall())


def get_posts_by_subreddit(conn: sqlite3.Connection, subreddit: str) -> list[dict[str, Any]]:
    """Return all collected posts for a given subreddit, ordered by created_at ascending.

    Args:
        conn: An open SQLite connection.
        subreddit: The subreddit name to filter on.

    Returns:
        List of post dicts. Empty list if no posts exist for this subreddit.
    """
    cursor = conn.execute(
        "SELECT * FROM collected_posts WHERE subreddit = ? ORDER BY created_at ASC;",
        (subreddit,),
    )
    return _rows_to_dicts(cursor.fetchall())


def get_all_collected_posts(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Return all collected posts ordered by created_at ascending.

    Args:
        conn: An open SQLite connection.

    Returns:
        List of post dicts. Empty list if the table is empty.
    """
    cursor = conn.execute("SELECT * FROM collected_posts ORDER BY created_at ASC;")
    return _rows_to_dicts(cursor.fetchall())


def get_posts_needing_update(conn: sqlite3.Connection, rule_name: str) -> list[dict[str, Any]]:
    """Return all posts for a rule that may have new comment activity since last sync.

    Returns every post collected by the given rule that has a status of 'ok'.
    The application layer is responsible for comparing the stored comment_count
    against the live Reddit API count to determine which posts actually have
    new activity. All 'ok' posts are returned so the caller has full latitude
    to decide the update strategy (e.g., only re-fetch posts older than N hours,
    or posts above a score threshold).

    Args:
        conn: An open SQLite connection.
        rule_name: The name of the collection rule to filter on.

    Returns:
        List of post dicts where status = 'ok', ordered by synced_at ascending
        (oldest synced first, so the most stale posts are prioritized).
    """
    cursor = conn.execute(
        """
        SELECT * FROM collected_posts
        WHERE rule_name = ? AND status = 'ok'
        ORDER BY synced_at ASC;
        """,
        (rule_name,),
    )
    return _rows_to_dicts(cursor.fetchall())


def delete_all_posts(conn: sqlite3.Connection) -> int:
    """Delete all rows from collected_posts. Used by the --force flag.

    Args:
        conn: An open SQLite connection.

    Returns:
        The number of rows deleted.
    """
    cursor = conn.execute("DELETE FROM collected_posts;")
    return cursor.rowcount


def delete_posts_by_rule(conn: sqlite3.Connection, rule_name: str) -> int:
    """Delete all collected posts for a given rule. Used by targeted --force.

    Args:
        conn: An open SQLite connection.
        rule_name: The name of the collection rule whose posts should be deleted.

    Returns:
        The number of rows deleted.
    """
    cursor = conn.execute(
        "DELETE FROM collected_posts WHERE rule_name = ?;",
        (rule_name,),
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
