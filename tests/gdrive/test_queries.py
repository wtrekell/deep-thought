"""Tests for deep_thought.gdrive.db.queries."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    import sqlite3

from deep_thought.gdrive.db.queries import (
    clear_backed_up_files,
    clear_drive_folders,
    count_by_status,
    get_backed_up_file,
    get_drive_folder,
    mark_file_status,
    upsert_backed_up_file,
    upsert_drive_folder,
)
from deep_thought.gdrive.models import BackedUpFile


def _make_backed_up_file(**overrides: object) -> BackedUpFile:
    """Factory for BackedUpFile with sensible defaults."""
    defaults: dict[str, object] = {
        "local_path": "source/notes/todo.md",
        "drive_file_id": "abc123",
        "drive_folder_id": "folder456",
        "mtime": 1712345678.0,
        "size_bytes": 1024,
        "status": "uploaded",
        "uploaded_at": "2026-04-04T12:00:00+00:00",
        "updated_at": "2026-04-04T12:00:00+00:00",
    }
    defaults.update(overrides)
    return BackedUpFile(**defaults)  # type: ignore[arg-type]


@pytest.fixture
def db(in_memory_db: sqlite3.Connection) -> sqlite3.Connection:
    """Alias for the in_memory_db fixture for local readability."""
    return in_memory_db


# ---------------------------------------------------------------------------
# backed_up_files
# ---------------------------------------------------------------------------


def test_upsert_and_get_backed_up_file_round_trip(db: sqlite3.Connection) -> None:
    """upsert then get returns a BackedUpFile matching the inserted values."""
    original_file = _make_backed_up_file()
    upsert_backed_up_file(db, original_file)

    retrieved_file = get_backed_up_file(db, "source/notes/todo.md")

    assert retrieved_file is not None
    assert retrieved_file.local_path == "source/notes/todo.md"
    assert retrieved_file.drive_file_id == "abc123"
    assert retrieved_file.mtime == 1712345678.0
    assert retrieved_file.status == "uploaded"


def test_get_backed_up_file_returns_none_for_missing_path(db: sqlite3.Connection) -> None:
    """get_backed_up_file returns None when the path does not exist."""
    result = get_backed_up_file(db, "nonexistent/path.txt")
    assert result is None


def test_upsert_backed_up_file_updates_on_conflict(db: sqlite3.Connection) -> None:
    """A second upsert updates mtime and status while preserving uploaded_at."""
    original_file = _make_backed_up_file()
    upsert_backed_up_file(db, original_file)

    updated_file = _make_backed_up_file(
        mtime=9999999999.0,
        status="updated",
        updated_at="2026-04-05T10:00:00+00:00",
    )
    upsert_backed_up_file(db, updated_file)

    retrieved = get_backed_up_file(db, "source/notes/todo.md")
    assert retrieved is not None
    assert retrieved.mtime == 9999999999.0
    assert retrieved.status == "updated"
    # uploaded_at from the first insert must be preserved
    assert retrieved.uploaded_at == "2026-04-04T12:00:00+00:00"


def test_mark_file_status_updates_status(db: sqlite3.Connection) -> None:
    """mark_file_status changes the status field for an existing record."""
    backed_up_file = _make_backed_up_file(status="uploaded")
    upsert_backed_up_file(db, backed_up_file)

    mark_file_status(db, "source/notes/todo.md", "error")

    retrieved = get_backed_up_file(db, "source/notes/todo.md")
    assert retrieved is not None
    assert retrieved.status == "error"


def test_clear_backed_up_files_removes_all_rows(db: sqlite3.Connection) -> None:
    """clear_backed_up_files deletes all rows from the table."""
    for index in range(3):
        upsert_backed_up_file(db, _make_backed_up_file(local_path=f"source/file{index}.txt"))

    clear_backed_up_files(db)

    cursor = db.execute("SELECT COUNT(*) as cnt FROM backed_up_files;")
    row = cursor.fetchone()
    assert row["cnt"] == 0


def test_count_by_status_returns_correct_counts(db: sqlite3.Connection) -> None:
    """count_by_status returns a dict with status → count."""
    upsert_backed_up_file(db, _make_backed_up_file(local_path="source/a.txt", status="uploaded"))
    upsert_backed_up_file(db, _make_backed_up_file(local_path="source/b.txt", status="uploaded"))
    upsert_backed_up_file(db, _make_backed_up_file(local_path="source/c.txt", status="updated"))
    upsert_backed_up_file(db, _make_backed_up_file(local_path="source/d.txt", status="error"))

    status_counts = count_by_status(db)

    assert status_counts["uploaded"] == 2
    assert status_counts["updated"] == 1
    assert status_counts["error"] == 1


def test_count_by_status_returns_empty_dict_when_no_rows(db: sqlite3.Connection) -> None:
    """count_by_status returns an empty dict when the table is empty."""
    status_counts = count_by_status(db)
    assert status_counts == {}


# ---------------------------------------------------------------------------
# drive_folders
# ---------------------------------------------------------------------------


def test_upsert_and_get_drive_folder_round_trip(db: sqlite3.Connection) -> None:
    """upsert_drive_folder then get_drive_folder returns the cached folder ID."""
    upsert_drive_folder(db, "source/notes", "drive-folder-notes-id")

    retrieved_id = get_drive_folder(db, "source/notes")
    assert retrieved_id == "drive-folder-notes-id"


def test_get_drive_folder_returns_none_for_missing_path(db: sqlite3.Connection) -> None:
    """get_drive_folder returns None when the path is not cached."""
    result = get_drive_folder(db, "source/nonexistent")
    assert result is None


def test_upsert_drive_folder_updates_on_conflict(db: sqlite3.Connection) -> None:
    """A second upsert_drive_folder call updates the cached folder ID."""
    upsert_drive_folder(db, "source/notes", "old-folder-id")
    upsert_drive_folder(db, "source/notes", "new-folder-id")

    retrieved_id = get_drive_folder(db, "source/notes")
    assert retrieved_id == "new-folder-id"


def test_clear_drive_folders_removes_all_rows(db: sqlite3.Connection) -> None:
    """clear_drive_folders deletes all rows from the drive_folders table."""
    upsert_drive_folder(db, "source/notes", "folder-id-1")
    upsert_drive_folder(db, "source/data", "folder-id-2")

    clear_drive_folders(db)

    cursor = db.execute("SELECT COUNT(*) as cnt FROM drive_folders;")
    row = cursor.fetchone()
    assert row["cnt"] == 0
