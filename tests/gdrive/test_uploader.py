"""Tests for deep_thought.gdrive.uploader — run_backup orchestration."""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from deep_thought.gdrive.config import GDriveConfig
from deep_thought.gdrive.db.queries import get_backed_up_file
from deep_thought.gdrive.db.schema import init_db
from deep_thought.gdrive.uploader import run_backup

if TYPE_CHECKING:
    from pathlib import Path


def _make_db() -> sqlite3.Connection:
    """Return an in-memory SQLite connection with the GDrive schema applied."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return conn


def _make_config(source_dir: str) -> GDriveConfig:
    """Return a GDriveConfig pointing at source_dir with a non-empty folder ID."""
    return GDriveConfig(
        credentials_file="/fake/credentials.json",
        token_file="/fake/token.json",
        scopes=["https://www.googleapis.com/auth/drive.file"],
        source_dir=source_dir,
        drive_folder_id="root-folder-id",
        api_rate_limit_rpm=0,
        retry_max_attempts=1,
        retry_base_delay_seconds=0.0,
    )


def _make_mock_client() -> MagicMock:
    """Return a DriveClient mock with sensible upload/update defaults."""
    mock_client = MagicMock()
    mock_client.upload_file.return_value = "new-drive-file-id"
    mock_client.update_file.return_value = None
    mock_client.ensure_folder.return_value = "folder-id"
    return mock_client


# ---------------------------------------------------------------------------
# New file — upload path
# ---------------------------------------------------------------------------


def test_new_file_is_uploaded_and_recorded(tmp_path: Path) -> None:
    """A file with no DB record is uploaded and stored in backed_up_files."""
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "notes.md").write_text("# Notes")

    db = _make_db()
    config = _make_config(str(source_dir))
    mock_client = _make_mock_client()

    result = run_backup(config, mock_client, db)

    assert result.uploaded == 1
    assert result.updated == 0
    assert result.skipped == 0
    assert result.errors == 0

    mock_client.upload_file.assert_called_once()
    record = get_backed_up_file(db, "source/notes.md")
    assert record is not None
    assert record.status == "uploaded"
    assert record.drive_file_id == "new-drive-file-id"


# ---------------------------------------------------------------------------
# Unchanged mtime — skip path
# ---------------------------------------------------------------------------


def test_unchanged_mtime_is_skipped(tmp_path: Path) -> None:
    """A file whose mtime matches the DB record is skipped without an API call."""
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    test_file = source_dir / "notes.md"
    test_file.write_text("# Notes")

    db = _make_db()
    config = _make_config(str(source_dir))
    mock_client = _make_mock_client()

    # First run — upload the file
    run_backup(config, mock_client, db)
    mock_client.reset_mock()

    # Second run — mtime unchanged, should skip
    result = run_backup(config, mock_client, db)

    assert result.skipped == 1
    assert result.uploaded == 0
    assert result.updated == 0
    mock_client.upload_file.assert_not_called()
    mock_client.update_file.assert_not_called()


# ---------------------------------------------------------------------------
# Changed mtime — update path
# ---------------------------------------------------------------------------


def test_changed_mtime_triggers_update(tmp_path: Path) -> None:
    """A file whose mtime changed since last backup is updated in-place on Drive."""
    import time

    source_dir = tmp_path / "source"
    source_dir.mkdir()
    test_file = source_dir / "notes.md"
    test_file.write_text("original content")

    db = _make_db()
    config = _make_config(str(source_dir))
    mock_client = _make_mock_client()

    # First run — upload
    run_backup(config, mock_client, db)
    mock_client.reset_mock()
    mock_client.upload_file.return_value = "new-drive-file-id"

    # Modify the file so mtime changes
    time.sleep(0.05)
    test_file.write_text("modified content")

    result = run_backup(config, mock_client, db)

    assert result.updated == 1
    assert result.uploaded == 0
    mock_client.update_file.assert_called_once()

    record = get_backed_up_file(db, "source/notes.md")
    assert record is not None
    assert record.status == "updated"


# ---------------------------------------------------------------------------
# --force clears state
# ---------------------------------------------------------------------------


def test_force_flag_clears_existing_state_and_re_uploads(tmp_path: Path) -> None:
    """--force deletes all cached records and re-uploads all files from scratch."""
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "doc.txt").write_text("content")

    db = _make_db()
    config = _make_config(str(source_dir))
    mock_client = _make_mock_client()

    # First run
    run_backup(config, mock_client, db)
    assert mock_client.upload_file.call_count == 1
    mock_client.reset_mock()
    mock_client.upload_file.return_value = "new-drive-file-id"

    # Force run — should upload again even though mtime unchanged
    result = run_backup(config, mock_client, db, force=True)

    assert result.uploaded == 1
    assert result.skipped == 0
    mock_client.upload_file.assert_called_once()


# ---------------------------------------------------------------------------
# Per-file error handling
# ---------------------------------------------------------------------------


def test_per_file_error_is_recorded_without_halting_backup(tmp_path: Path) -> None:
    """A file that raises during upload is marked as error; backup continues."""
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "good.txt").write_text("good content")
    (source_dir / "bad.txt").write_text("bad content")

    db = _make_db()
    config = _make_config(str(source_dir))
    mock_client = _make_mock_client()

    call_count = 0

    def upload_side_effect(**kwargs: object) -> str:
        nonlocal call_count
        call_count += 1
        if "bad.txt" in str(kwargs.get("local_path", "")):
            raise OSError("Simulated upload failure")
        return "good-file-id"

    mock_client.upload_file.side_effect = upload_side_effect

    result = run_backup(config, mock_client, db)

    assert result.errors == 1
    assert result.uploaded == 1
    assert len(result.error_paths) == 1
    assert any("bad.txt" in path for path in result.error_paths)


# ---------------------------------------------------------------------------
# BackupResult counts
# ---------------------------------------------------------------------------


def test_backup_result_counts_are_correct_for_mixed_run(tmp_path: Path) -> None:
    """BackupResult tallies uploaded, updated, skipped, errors correctly."""
    import time

    source_dir = tmp_path / "source"
    source_dir.mkdir()

    # Three files: one will be new, one will be updated, one stays unchanged
    (source_dir / "new_file.txt").write_text("new")
    (source_dir / "changed_file.txt").write_text("original")
    (source_dir / "unchanged_file.txt").write_text("static")

    db = _make_db()
    config = _make_config(str(source_dir))
    mock_client = _make_mock_client()

    # First run — all three uploaded
    run_backup(config, mock_client, db)
    mock_client.reset_mock()
    mock_client.upload_file.return_value = "new-drive-file-id"

    # Modify only changed_file.txt
    time.sleep(0.05)
    (source_dir / "changed_file.txt").write_text("modified")
    # Delete new_file.txt — it no longer exists, so it should be skipped (not walked)
    (source_dir / "new_file.txt").unlink()

    result = run_backup(config, mock_client, db)

    # changed_file is updated, unchanged_file is skipped
    assert result.updated == 1
    assert result.skipped == 1
    assert result.uploaded == 0
    assert result.errors == 0


# ---------------------------------------------------------------------------
# Dry-run mode
# ---------------------------------------------------------------------------


def test_dry_run_does_not_call_api_or_write_db(tmp_path: Path) -> None:
    """--dry-run logs what would happen but makes no API calls or DB writes."""
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "doc.md").write_text("content")

    db = _make_db()
    config = _make_config(str(source_dir))
    mock_client = _make_mock_client()

    result = run_backup(config, mock_client, db, dry_run=True)

    assert result.uploaded == 1
    mock_client.upload_file.assert_not_called()

    # DB should have no records
    record = get_backed_up_file(db, "source/doc.md")
    assert record is None
