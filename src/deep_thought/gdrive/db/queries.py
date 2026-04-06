"""Parameterized SQL query functions for the GDrive Tool database layer.

All functions accept an open sqlite3.Connection as their first argument and
return plain Python types. No business logic lives here — these are thin
wrappers over SQL that the application layer calls directly.

Upsert strategy: INSERT ... ON CONFLICT DO UPDATE SET is used throughout so
that the original upload timestamp is preserved across re-runs.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from deep_thought.gdrive.models import BackedUpFile

if TYPE_CHECKING:
    import sqlite3


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _now_utc_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(UTC).isoformat()


def _row_to_backed_up_file(row: sqlite3.Row) -> BackedUpFile:
    """Convert a sqlite3.Row from backed_up_files to a BackedUpFile dataclass."""
    return BackedUpFile(
        local_path=row["local_path"],
        drive_file_id=row["drive_file_id"],
        drive_folder_id=row["drive_folder_id"],
        mtime=float(row["mtime"]),
        size_bytes=int(row["size_bytes"]),
        status=row["status"],
        uploaded_at=row["uploaded_at"],
        updated_at=row["updated_at"],
    )


# ---------------------------------------------------------------------------
# backed_up_files
# ---------------------------------------------------------------------------


def upsert_backed_up_file(conn: sqlite3.Connection, file: BackedUpFile) -> None:
    """Insert or update a backed_up_files row.

    On conflict (local_path already exists), all fields except uploaded_at
    are updated. uploaded_at is preserved from the original insertion.

    Args:
        conn: An open SQLite connection.
        file: The BackedUpFile to persist.
    """
    file_dict = file.to_dict()
    conn.execute(
        """
        INSERT INTO backed_up_files (
            local_path, drive_file_id, drive_folder_id,
            mtime, size_bytes, status, uploaded_at, updated_at
        ) VALUES (
            :local_path, :drive_file_id, :drive_folder_id,
            :mtime, :size_bytes, :status, :uploaded_at, :updated_at
        )
        ON CONFLICT(local_path) DO UPDATE SET
            drive_file_id   = excluded.drive_file_id,
            drive_folder_id = excluded.drive_folder_id,
            mtime           = excluded.mtime,
            size_bytes      = excluded.size_bytes,
            status          = excluded.status,
            updated_at      = excluded.updated_at;
        """,
        file_dict,
    )


def get_backed_up_file(conn: sqlite3.Connection, local_path: str) -> BackedUpFile | None:
    """Return a single BackedUpFile by local_path, or None if not found.

    Args:
        conn: An open SQLite connection.
        local_path: The relative local path (primary key).

    Returns:
        A BackedUpFile, or None if no matching row exists.
    """
    cursor = conn.execute(
        "SELECT * FROM backed_up_files WHERE local_path = :local_path;",
        {"local_path": local_path},
    )
    row: sqlite3.Row | None = cursor.fetchone()
    if row is None:
        return None
    return _row_to_backed_up_file(row)


def mark_file_status(conn: sqlite3.Connection, local_path: str, status: str) -> None:
    """Update the status field for an existing backed_up_files row.

    Also updates updated_at to the current UTC time.

    Args:
        conn: An open SQLite connection.
        local_path: The relative local path (primary key).
        status: The new status string (e.g. 'error', 'skipped').
    """
    conn.execute(
        """
        UPDATE backed_up_files
        SET status = :status, updated_at = :updated_at
        WHERE local_path = :local_path;
        """,
        {"local_path": local_path, "status": status, "updated_at": _now_utc_iso()},
    )


def get_all_backed_up_files(conn: sqlite3.Connection) -> list[BackedUpFile]:
    """Return all rows from backed_up_files.

    Args:
        conn: An open SQLite connection.

    Returns:
        A list of all BackedUpFile records. Empty list if the table is empty.
    """
    cursor = conn.execute("SELECT * FROM backed_up_files;")
    rows: list[Any] = cursor.fetchall()
    return [_row_to_backed_up_file(row) for row in rows]


def delete_backed_up_file(conn: sqlite3.Connection, local_path: str) -> None:
    """Delete a single row from backed_up_files by local_path.

    Args:
        conn: An open SQLite connection.
        local_path: The relative local path (primary key) to delete.
    """
    conn.execute(
        "DELETE FROM backed_up_files WHERE local_path = :local_path;",
        {"local_path": local_path},
    )


def clear_backed_up_files(conn: sqlite3.Connection) -> None:
    """Delete all rows from backed_up_files (used by --force).

    Args:
        conn: An open SQLite connection.
    """
    conn.execute("DELETE FROM backed_up_files;")


def count_by_status(conn: sqlite3.Connection) -> dict[str, int]:
    """Return a dict mapping status string to count of rows with that status.

    Args:
        conn: An open SQLite connection.

    Returns:
        Dict of {status: count}. Only statuses that exist in the table are
        included; missing statuses are not represented with a zero count.
    """
    cursor = conn.execute("SELECT status, COUNT(*) as count FROM backed_up_files GROUP BY status;")
    rows: list[Any] = cursor.fetchall()
    return {row["status"]: int(row["count"]) for row in rows}


# ---------------------------------------------------------------------------
# drive_folders
# ---------------------------------------------------------------------------


def upsert_drive_folder(conn: sqlite3.Connection, local_path: str, drive_folder_id: str) -> None:
    """Insert or update a drive_folders row (folder ID cache).

    Args:
        conn: An open SQLite connection.
        local_path: The relative local directory path (primary key).
        drive_folder_id: The Drive folder ID to cache.
    """
    conn.execute(
        """
        INSERT INTO drive_folders (local_path, drive_folder_id)
        VALUES (:local_path, :drive_folder_id)
        ON CONFLICT(local_path) DO UPDATE SET
            drive_folder_id = excluded.drive_folder_id;
        """,
        {"local_path": local_path, "drive_folder_id": drive_folder_id},
    )


def get_drive_folder(conn: sqlite3.Connection, local_path: str) -> str | None:
    """Return the cached Drive folder ID for a local path, or None.

    Args:
        conn: An open SQLite connection.
        local_path: The relative local directory path to look up.

    Returns:
        The Drive folder ID string, or None if not cached.
    """
    cursor = conn.execute(
        "SELECT drive_folder_id FROM drive_folders WHERE local_path = :local_path;",
        {"local_path": local_path},
    )
    row: sqlite3.Row | None = cursor.fetchone()
    if row is None:
        return None
    folder_id: str = row["drive_folder_id"]
    return folder_id


def clear_drive_folders(conn: sqlite3.Connection) -> None:
    """Delete all rows from drive_folders (used by --force).

    Args:
        conn: An open SQLite connection.
    """
    conn.execute("DELETE FROM drive_folders;")
