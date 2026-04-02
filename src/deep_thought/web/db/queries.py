"""Parameterized SQL query functions for the web crawl tool database layer.

All functions accept an open sqlite3.Connection as their first argument and
return plain Python types (dicts, lists, None). No business logic lives here —
these are thin wrappers over SQL that the application layer calls directly.

Upsert strategy: INSERT ... ON CONFLICT(url) DO UPDATE SET updates all columns
except created_at when the URL already exists, preserving the original crawl
timestamp across re-crawls.

Transaction responsibility: Callers are responsible for committing transactions.
Write functions (upsert_crawled_page, delete_crawled_page) do not call
conn.commit() themselves. Call conn.commit() after one or more writes, or use
conn.rollback() to discard changes on error.

Note: The crawled_pages table and web_schema_version table are created by the
DB agent via migration files in db/migrations/. The DB agent should create:
  - crawled_pages table with columns: url (PRIMARY KEY), rule_name, title,
    status_code, word_count, output_path, status, child_links, created_at,
    updated_at, synced_at
  - web_schema_version table with columns: key (PRIMARY KEY), value, updated_at
"""

from __future__ import annotations

import sqlite3  # noqa: TC003 — sqlite3.Row is used at runtime in _row_to_dict
from datetime import UTC, datetime
from typing import Any

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _now_utc_iso() -> str:
    """Return the current UTC time as an ISO-8601 string.

    Returns:
        ISO-8601 formatted UTC timestamp string.
    """
    return datetime.now(UTC).isoformat()


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    """Convert a sqlite3.Row to a plain dict, or return None if the row is None.

    Args:
        row: A sqlite3.Row object or None.

    Returns:
        A plain dict, or None if row is None.
    """
    if row is None:
        return None
    return dict(row)


def _rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    """Convert a list of sqlite3.Row objects to a list of plain dicts.

    Args:
        rows: A list of sqlite3.Row objects.

    Returns:
        A list of plain dicts.
    """
    return [dict(row) for row in rows]


# ---------------------------------------------------------------------------
# Crawled pages
# ---------------------------------------------------------------------------


def upsert_crawled_page(conn: sqlite3.Connection, page_data: dict[str, Any]) -> None:
    """Insert or update a crawled_pages row from page data.

    On first insert all columns are written. On conflict (same URL), all columns
    are updated except ``created_at``, which is preserved from the original row
    so that the initial crawl timestamp is never overwritten.

    ``synced_at`` is always set to the current UTC time.

    Args:
        conn: An open SQLite connection.
        page_data: Dict with keys matching the crawled_pages table columns.
                   Required key: 'url'.
    """
    synced_at = _now_utc_iso()
    conn.execute(
        """
        INSERT INTO crawled_pages (
            url, rule_name, title, status_code, word_count,
            output_path, status, created_at, updated_at, synced_at
        ) VALUES (
            :url, :rule_name, :title, :status_code, :word_count,
            :output_path, :status, :created_at, :updated_at, :synced_at
        )
        ON CONFLICT(url) DO UPDATE SET
            rule_name = excluded.rule_name,
            title = excluded.title,
            status_code = excluded.status_code,
            word_count = excluded.word_count,
            output_path = excluded.output_path,
            status = excluded.status,
            updated_at = excluded.updated_at,
            synced_at = excluded.synced_at;
        """,
        {**page_data, "synced_at": synced_at},
    )


def get_crawled_page(conn: sqlite3.Connection, url: str) -> dict[str, Any] | None:
    """Return a single crawled_pages row by URL, or None if not found.

    Args:
        conn: An open SQLite connection.
        url: The URL primary key to look up.

    Returns:
        A dict of the row's columns, or None if no matching row exists.
    """
    cursor = conn.execute(
        "SELECT * FROM crawled_pages WHERE url = ?;",
        (url,),
    )
    row: sqlite3.Row | None = cursor.fetchone()
    return _row_to_dict(row)


def get_all_crawled_pages(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Return all rows from crawled_pages ordered by url.

    Args:
        conn: An open SQLite connection.

    Returns:
        A list of dicts, one per row in crawled_pages.
    """
    cursor = conn.execute("SELECT * FROM crawled_pages ORDER BY url;")
    rows: list[sqlite3.Row] = cursor.fetchall()
    return _rows_to_dicts(rows)


def update_page_child_links(conn: sqlite3.Connection, url: str, child_links_json: str) -> None:
    """Store the JSON-encoded list of child links discovered from a crawled page.

    Called after child links are extracted from a freshly-fetched page so that
    subsequent cache-hit BFS traversals can re-enqueue children without
    re-fetching the page HTML.

    Args:
        conn: An open SQLite connection.
        url: The URL primary key of the crawled page row to update.
        child_links_json: JSON-encoded list of child URL strings
                          (e.g. ``'["https://example.com/a", "https://example.com/b"]'``).
    """
    conn.execute(
        "UPDATE crawled_pages SET child_links = ? WHERE url = ?;",
        (child_links_json, url),
    )


def delete_crawled_page(conn: sqlite3.Connection, url: str) -> None:
    """Delete a single crawled_pages row by URL.

    Args:
        conn: An open SQLite connection.
        url: The URL primary key of the row to delete.
    """
    conn.execute("DELETE FROM crawled_pages WHERE url = ?;", (url,))


def get_crawled_pages_by_status(conn: sqlite3.Connection, status: str) -> list[dict[str, Any]]:
    """Return all crawled_pages rows with the given status.

    Args:
        conn: An open SQLite connection.
        status: The status value to filter on (e.g., 'success', 'error', 'skipped').

    Returns:
        A list of dicts for all matching rows.
    """
    cursor = conn.execute(
        "SELECT * FROM crawled_pages WHERE status = ? ORDER BY url;",
        (status,),
    )
    rows: list[sqlite3.Row] = cursor.fetchall()
    return _rows_to_dicts(rows)


def get_successful_pages_since(conn: sqlite3.Connection, since_iso: str) -> list[dict[str, Any]]:
    """Return all successful crawled_pages rows updated at or after *since_iso*.

    Uses ``updated_at`` so that re-crawled pages remain in the window even if
    they were originally created outside it.

    Args:
        conn: An open SQLite connection.
        since_iso: ISO-8601 timestamp string.  Only rows with ``updated_at``
            at or after this value are returned.

    Returns:
        A list of dicts for all matching rows, ordered by URL.
    """
    cursor = conn.execute(
        "SELECT * FROM crawled_pages WHERE status = 'success' AND updated_at >= ? ORDER BY url;",
        (since_iso,),
    )
    rows: list[sqlite3.Row] = cursor.fetchall()
    return _rows_to_dicts(rows)
