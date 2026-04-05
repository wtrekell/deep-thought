"""Tests for deep_thought.gdrive.models."""

from __future__ import annotations

from deep_thought.gdrive.models import BackedUpFile, BackupResult


def _make_backed_up_file(**overrides: object) -> BackedUpFile:
    """Factory for BackedUpFile with sensible defaults."""
    defaults = {
        "local_path": "source/notes/todo.md",
        "drive_file_id": "abc123",
        "drive_folder_id": "folder456",
        "mtime": 1712345678.123456,
        "size_bytes": 1024,
        "status": "uploaded",
        "uploaded_at": "2026-04-04T12:00:00+00:00",
        "updated_at": "2026-04-04T12:00:00+00:00",
    }
    defaults.update(overrides)  # type: ignore[arg-type]
    return BackedUpFile(**defaults)  # type: ignore[arg-type]


def test_to_dict_returns_all_expected_keys() -> None:
    """to_dict() returns a dict with all eight expected keys."""
    backed_up_file = _make_backed_up_file()
    file_dict = backed_up_file.to_dict()

    expected_keys = {
        "local_path",
        "drive_file_id",
        "drive_folder_id",
        "mtime",
        "size_bytes",
        "status",
        "uploaded_at",
        "updated_at",
    }
    assert set(file_dict.keys()) == expected_keys


def test_to_dict_preserves_float_mtime() -> None:
    """to_dict() preserves the full float precision of mtime."""
    precise_mtime = 1712345678.987654
    backed_up_file = _make_backed_up_file(mtime=precise_mtime)
    file_dict = backed_up_file.to_dict()

    assert file_dict["mtime"] == precise_mtime
    assert isinstance(file_dict["mtime"], float)


def test_to_dict_values_match_fields() -> None:
    """to_dict() values match the dataclass field values."""
    backed_up_file = _make_backed_up_file(
        local_path="source/data/report.csv",
        drive_file_id="xyz789",
        drive_folder_id="folder999",
        mtime=1700000000.5,
        size_bytes=2048,
        status="updated",
        uploaded_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-04-04T15:30:00+00:00",
    )
    file_dict = backed_up_file.to_dict()

    assert file_dict["local_path"] == "source/data/report.csv"
    assert file_dict["drive_file_id"] == "xyz789"
    assert file_dict["drive_folder_id"] == "folder999"
    assert file_dict["mtime"] == 1700000000.5
    assert file_dict["size_bytes"] == 2048
    assert file_dict["status"] == "updated"
    assert file_dict["uploaded_at"] == "2026-01-01T00:00:00+00:00"
    assert file_dict["updated_at"] == "2026-04-04T15:30:00+00:00"


def test_backup_result_defaults_to_zero() -> None:
    """BackupResult initialises all counts to zero and error_paths to empty list."""
    result = BackupResult()

    assert result.uploaded == 0
    assert result.updated == 0
    assert result.skipped == 0
    assert result.errors == 0
    assert result.error_paths == []


def test_backup_result_error_paths_are_independent() -> None:
    """Two BackupResult instances have independent error_paths lists."""
    result_a = BackupResult()
    result_b = BackupResult()

    result_a.error_paths.append("some/path.txt")

    assert result_b.error_paths == []
