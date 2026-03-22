"""
queries.py — Parameterized SQL query functions for the Audio Tool database layer.

All functions accept an open sqlite3.Connection as their first argument and
return plain Python types (dicts, lists, None, bool). No business logic lives
here — these are thin wrappers over SQL that the application layer calls directly.

Upsert strategy: INSERT OR REPLACE replaces the entire row when the primary
key conflicts. This is safe because we always provide all columns.

Timestamps: `updated_at` is always set to the current UTC time at the moment
of the write. `created_at` is sourced from the caller's data dict so that it
reflects when the record was first created (even across upserts).
"""

from __future__ import annotations

import logging
import sqlite3  # noqa: TC003 — sqlite3.Row is used at runtime in dict(row) conversions
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

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
# Processed files
# ---------------------------------------------------------------------------


def upsert_processed_file(conn: sqlite3.Connection, data: dict[str, Any]) -> None:
    """Insert or replace a processed file record. Sets updated_at to now.

    Uses INSERT OR REPLACE, which replaces the entire row on primary key
    conflict (file_path). The caller must supply created_at in data; it is
    passed through unchanged so the original creation timestamp is preserved
    across updates.

    Args:
        conn: An open SQLite connection.
        data: Dict with keys matching the processed_files table columns.
              Required keys: file_path, file_hash, engine, model, created_at.
              Optional keys: duration_seconds, speaker_count, output_path, status.
    """
    updated_at = _now_utc_iso()
    conn.execute(
        """
        INSERT OR REPLACE INTO processed_files (
            file_path,
            file_hash,
            engine,
            model,
            duration_seconds,
            speaker_count,
            output_path,
            status,
            created_at,
            updated_at
        ) VALUES (
            :file_path,
            :file_hash,
            :engine,
            :model,
            :duration_seconds,
            :speaker_count,
            :output_path,
            :status,
            :created_at,
            :updated_at
        );
        """,
        {**data, "updated_at": updated_at},
    )


def get_processed_file(conn: sqlite3.Connection, file_path: str) -> dict[str, Any] | None:
    """Look up a processed file by its path. Returns a dict or None.

    Args:
        conn: An open SQLite connection.
        file_path: The absolute or relative path used as the primary key.

    Returns:
        A dict of column values, or None if no matching row exists.
    """
    cursor = conn.execute(
        "SELECT * FROM processed_files WHERE file_path = ?;",
        (file_path,),
    )
    return _row_to_dict(cursor.fetchone())


def get_processed_files_by_status(conn: sqlite3.Connection, status: str) -> list[dict[str, Any]]:
    """Return all processed files with the given status.

    Args:
        conn: An open SQLite connection.
        status: The status value to filter on (e.g., 'pending', 'success', 'error').

    Returns:
        List of processed file dicts. Empty list if none match.
    """
    cursor = conn.execute(
        "SELECT * FROM processed_files WHERE status = ? ORDER BY created_at ASC;",
        (status,),
    )
    return _rows_to_dicts(cursor.fetchall())


def get_file_hash_with_success(conn: sqlite3.Connection, file_hash: str) -> dict[str, Any] | None:
    """Look up a successfully processed file by its content hash.

    Used for duplicate detection: if a file with the same content hash has
    already been transcribed successfully, there is no need to reprocess it.

    Args:
        conn: An open SQLite connection.
        file_hash: The content hash (e.g., SHA-256 hex digest) to look up.

    Returns:
        A dict of column values for the first matching success row, or None
        if no successfully processed file with that hash exists.
    """
    cursor = conn.execute(
        "SELECT * FROM processed_files WHERE file_hash = ? AND status = 'success' LIMIT 1;",
        (file_hash,),
    )
    return _row_to_dict(cursor.fetchone())


def delete_processed_file(conn: sqlite3.Connection, file_path: str) -> bool:
    """Delete a processed file record by path.

    Args:
        conn: An open SQLite connection.
        file_path: The path of the record to delete.

    Returns:
        True if a row was deleted, False if no matching row existed.
    """
    cursor = conn.execute(
        "DELETE FROM processed_files WHERE file_path = ?;",
        (file_path,),
    )
    return cursor.rowcount > 0


def get_all_processed_files(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Return all processed file records ordered by created_at ascending.

    Args:
        conn: An open SQLite connection.

    Returns:
        List of processed file dicts. Empty list if the table is empty.
    """
    cursor = conn.execute("SELECT * FROM processed_files ORDER BY created_at ASC;")
    return _rows_to_dicts(cursor.fetchall())
