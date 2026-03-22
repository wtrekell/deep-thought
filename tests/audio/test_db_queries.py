"""Tests for the Audio Tool database query functions.

All tests use in-memory SQLite (no disk writes). The in_memory_db fixture
initializes a fresh database for each test.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    import sqlite3

from deep_thought.audio.db.queries import (
    delete_processed_file,
    get_all_processed_files,
    get_file_hash_with_success,
    get_processed_file,
    get_processed_files_by_status,
    upsert_processed_file,
)
from deep_thought.audio.db.schema import initialize_database

# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


@pytest.fixture()
def in_memory_db() -> sqlite3.Connection:
    """Return a fully initialized in-memory SQLite connection.

    All migrations are applied. Closes automatically after each test.
    """
    connection = initialize_database(":memory:")
    yield connection
    connection.close()


def _file_data(
    file_path: str = "/audio/meeting.mp3",
    file_hash: str = "abc123",
    status: str = "pending",
) -> dict[str, Any]:
    """Return a minimal processed_files data dict for use in tests."""
    return {
        "file_path": file_path,
        "file_hash": file_hash,
        "engine": "whisper",
        "model": "base",
        "duration_seconds": 120.5,
        "speaker_count": 2,
        "output_path": None,
        "status": status,
        "created_at": "2026-01-01T00:00:00+00:00",
    }


# ---------------------------------------------------------------------------
# upsert_processed_file
# ---------------------------------------------------------------------------


class TestUpsertProcessedFile:
    def test_inserts_new_record(self, in_memory_db: Any) -> None:
        """upsert_processed_file must insert a row that is retrievable afterward."""
        upsert_processed_file(in_memory_db, _file_data())
        row = get_processed_file(in_memory_db, "/audio/meeting.mp3")
        assert row is not None
        assert row["file_path"] == "/audio/meeting.mp3"
        assert row["engine"] == "whisper"

    def test_sets_updated_at_on_insert(self, in_memory_db: Any) -> None:
        """upsert_processed_file must populate updated_at with a non-null timestamp."""
        upsert_processed_file(in_memory_db, _file_data())
        row = get_processed_file(in_memory_db, "/audio/meeting.mp3")
        assert row is not None
        assert row["updated_at"] is not None

    def test_updates_existing_record_on_same_file_path(self, in_memory_db: Any) -> None:
        """A second upsert on the same file_path must update the row, not insert a duplicate."""
        upsert_processed_file(in_memory_db, _file_data(status="pending"))
        updated_data = {**_file_data(status="success"), "output_path": "/output/meeting.txt"}
        upsert_processed_file(in_memory_db, updated_data)

        row = get_processed_file(in_memory_db, "/audio/meeting.mp3")
        assert row is not None
        assert row["status"] == "success"
        assert row["output_path"] == "/output/meeting.txt"

        all_rows = get_all_processed_files(in_memory_db)
        assert len(all_rows) == 1

    def test_preserves_created_at_from_data_dict(self, in_memory_db: Any) -> None:
        """created_at must reflect what the caller passed in, not be overwritten."""
        original_created_at = "2026-01-01T00:00:00+00:00"
        upsert_processed_file(in_memory_db, _file_data())
        upsert_processed_file(in_memory_db, {**_file_data(status="success"), "created_at": original_created_at})
        row = get_processed_file(in_memory_db, "/audio/meeting.mp3")
        assert row is not None
        assert row["created_at"] == original_created_at


# ---------------------------------------------------------------------------
# get_processed_file
# ---------------------------------------------------------------------------


class TestGetProcessedFile:
    def test_returns_record_for_existing_path(self, in_memory_db: Any) -> None:
        """get_processed_file must return a dict for a path that exists."""
        upsert_processed_file(in_memory_db, _file_data())
        row = get_processed_file(in_memory_db, "/audio/meeting.mp3")
        assert row is not None
        assert row["file_hash"] == "abc123"

    def test_returns_none_for_missing_path(self, in_memory_db: Any) -> None:
        """get_processed_file must return None for a path that has no record."""
        result = get_processed_file(in_memory_db, "/audio/does_not_exist.mp3")
        assert result is None


# ---------------------------------------------------------------------------
# get_processed_files_by_status
# ---------------------------------------------------------------------------


class TestGetProcessedFilesByStatus:
    def test_returns_only_matching_status_records(self, in_memory_db: Any) -> None:
        """get_processed_files_by_status must filter by status correctly."""
        upsert_processed_file(in_memory_db, _file_data("/audio/a.mp3", "hash-a", status="pending"))
        upsert_processed_file(in_memory_db, _file_data("/audio/b.mp3", "hash-b", status="success"))
        upsert_processed_file(in_memory_db, _file_data("/audio/c.mp3", "hash-c", status="pending"))

        pending_rows = get_processed_files_by_status(in_memory_db, "pending")
        assert len(pending_rows) == 2
        assert all(row["status"] == "pending" for row in pending_rows)

    def test_returns_empty_list_when_no_matches(self, in_memory_db: Any) -> None:
        """get_processed_files_by_status must return [] when no rows match."""
        upsert_processed_file(in_memory_db, _file_data(status="pending"))
        result = get_processed_files_by_status(in_memory_db, "error")
        assert result == []

    def test_returns_empty_list_on_empty_table(self, in_memory_db: Any) -> None:
        """get_processed_files_by_status must return [] when the table has no rows."""
        result = get_processed_files_by_status(in_memory_db, "pending")
        assert result == []


# ---------------------------------------------------------------------------
# get_file_hash_with_success
# ---------------------------------------------------------------------------


class TestGetFileHashWithSuccess:
    def test_finds_matching_hash_with_success_status(self, in_memory_db: Any) -> None:
        """get_file_hash_with_success must return the row when hash matches a success record."""
        upsert_processed_file(in_memory_db, _file_data(file_hash="deadbeef", status="success"))
        result = get_file_hash_with_success(in_memory_db, "deadbeef")
        assert result is not None
        assert result["file_hash"] == "deadbeef"
        assert result["status"] == "success"

    def test_returns_none_for_hash_with_non_success_status(self, in_memory_db: Any) -> None:
        """get_file_hash_with_success must return None when the hash exists but status is not 'success'."""
        upsert_processed_file(in_memory_db, _file_data(file_hash="deadbeef", status="pending"))
        result = get_file_hash_with_success(in_memory_db, "deadbeef")
        assert result is None

    def test_returns_none_for_unknown_hash(self, in_memory_db: Any) -> None:
        """get_file_hash_with_success must return None when the hash does not exist."""
        result = get_file_hash_with_success(in_memory_db, "no-such-hash")
        assert result is None


# ---------------------------------------------------------------------------
# delete_processed_file
# ---------------------------------------------------------------------------


class TestDeleteProcessedFile:
    def test_removes_existing_record(self, in_memory_db: Any) -> None:
        """delete_processed_file must remove the row from the table."""
        upsert_processed_file(in_memory_db, _file_data())
        delete_processed_file(in_memory_db, "/audio/meeting.mp3")
        assert get_processed_file(in_memory_db, "/audio/meeting.mp3") is None

    def test_returns_true_when_row_was_deleted(self, in_memory_db: Any) -> None:
        """delete_processed_file must return True when a row was actually removed."""
        upsert_processed_file(in_memory_db, _file_data())
        result = delete_processed_file(in_memory_db, "/audio/meeting.mp3")
        assert result is True

    def test_returns_false_for_missing_path(self, in_memory_db: Any) -> None:
        """delete_processed_file must return False when no row matched the path."""
        result = delete_processed_file(in_memory_db, "/audio/nonexistent.mp3")
        assert result is False


# ---------------------------------------------------------------------------
# get_all_processed_files
# ---------------------------------------------------------------------------


class TestGetAllProcessedFiles:
    def test_returns_all_records(self, in_memory_db: Any) -> None:
        """get_all_processed_files must return every row in the table."""
        upsert_processed_file(in_memory_db, _file_data("/audio/a.mp3", "hash-a"))
        upsert_processed_file(in_memory_db, _file_data("/audio/b.mp3", "hash-b"))
        upsert_processed_file(in_memory_db, _file_data("/audio/c.mp3", "hash-c"))

        all_rows = get_all_processed_files(in_memory_db)
        assert len(all_rows) == 3

    def test_returns_empty_list_on_empty_table(self, in_memory_db: Any) -> None:
        """get_all_processed_files must return [] when the table has no rows."""
        result = get_all_processed_files(in_memory_db)
        assert result == []

    def test_returns_dicts_not_sqlite_rows(self, in_memory_db: Any) -> None:
        """get_all_processed_files must return plain dicts, not sqlite3.Row objects."""
        upsert_processed_file(in_memory_db, _file_data())
        rows = get_all_processed_files(in_memory_db)
        assert isinstance(rows[0], dict)
