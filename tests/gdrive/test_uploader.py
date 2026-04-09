"""Tests for deep_thought.gdrive.uploader — run_backup orchestration."""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from deep_thought.gdrive.config import GDriveConfig
from deep_thought.gdrive.db.queries import get_backed_up_file, upsert_backed_up_file
from deep_thought.gdrive.db.schema import init_db
from deep_thought.gdrive.models import BackedUpFile
from deep_thought.gdrive.uploader import run_backup, run_prune

if TYPE_CHECKING:
    from pathlib import Path


def _make_db() -> sqlite3.Connection:
    """Return an in-memory SQLite connection with the GDrive schema applied."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return conn


def _make_config(source_dir: str, exclude_patterns: list[str] | None = None) -> GDriveConfig:
    """Return a GDriveConfig pointing at source_dir with a non-empty folder ID."""
    return GDriveConfig(
        credentials_file="/fake/credentials.json",
        token_file="/fake/token.json",
        scopes=["https://www.googleapis.com/auth/drive.file"],
        source_dir=source_dir,
        drive_folder_id="root-folder-id",
        exclude_patterns=exclude_patterns if exclude_patterns is not None else [],
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

    record = get_backed_up_file(db, "source/notes.md")
    assert record is not None
    assert record.status == "skipped"


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


def test_force_and_dry_run_together_does_not_clear_db(tmp_path: Path) -> None:
    """--force --dry-run does not clear the database (dry-run takes precedence)."""
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "doc.txt").write_text("content")

    db = _make_db()
    config = _make_config(str(source_dir))
    mock_client = _make_mock_client()

    # First run to populate the DB
    run_backup(config, mock_client, db)
    mock_client.reset_mock()

    # Force + dry-run: DB is not cleared, so mtime still matches → file is skipped.
    result = run_backup(config, mock_client, db, force=True, dry_run=True)

    # DB was preserved (not cleared), mtime unchanged → counted as skipped, not uploaded.
    assert result.skipped == 1
    assert result.uploaded == 0
    mock_client.upload_file.assert_not_called()
    record = get_backed_up_file(db, "source/doc.txt")
    assert record is not None, "DB record should be preserved — force must not clear in dry-run mode."


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


def test_excluded_file_is_not_uploaded(tmp_path: Path) -> None:
    """A file matching an exclude_pattern is not uploaded and not recorded in the DB."""
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "keep.md").write_text("keep this")
    (source_dir / "ignore.db").write_text("skip this")

    db = _make_db()
    config = _make_config(str(source_dir), exclude_patterns=["*.db"])
    mock_client = _make_mock_client()

    result = run_backup(config, mock_client, db)

    assert result.uploaded == 1
    assert result.errors == 0
    mock_client.upload_file.assert_called_once()
    call_args = mock_client.upload_file.call_args
    assert "keep.md" in call_args.kwargs.get("local_path", "")
    assert get_backed_up_file(db, "source/ignore.db") is None


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


# ---------------------------------------------------------------------------
# run_prune tests
# ---------------------------------------------------------------------------


def _insert_backed_up_file(
    db: sqlite3.Connection,
    local_path: str,
    drive_file_id: str = "drive-id-placeholder",
) -> None:
    """Insert a BackedUpFile row directly into the DB without going through a backup run."""
    upsert_backed_up_file(
        db,
        BackedUpFile(
            local_path=local_path,
            drive_file_id=drive_file_id,
            drive_folder_id="folder-id",
            mtime=1712345678.0,
            size_bytes=512,
            status="uploaded",
            uploaded_at="2026-04-04T12:00:00+00:00",
            updated_at="2026-04-04T12:00:00+00:00",
        ),
    )


def test_run_prune_deletes_matching_files_and_removes_db_rows() -> None:
    """run_prune calls client.delete_file for matching files and removes their DB rows."""
    db = _make_db()
    # DB paths use the source-dir name as the first component
    _insert_backed_up_file(db, "source/cache/temp.tmp", drive_file_id="drive-tmp-id")
    _insert_backed_up_file(db, "source/notes/keep.md", drive_file_id="drive-md-id")

    mock_client = _make_mock_client()
    # Source dir name is "source"; exclude_patterns applies to path relative to source
    config = _make_config("/fake/parent/source", exclude_patterns=["*.tmp"])

    prune_result = run_prune(config=config, client=mock_client, db_conn=db)

    # Only the .tmp file should be deleted
    mock_client.delete_file.assert_called_once_with("drive-tmp-id")

    # The .tmp row must be gone; the .md row must remain
    assert get_backed_up_file(db, "source/cache/temp.tmp") is None
    assert get_backed_up_file(db, "source/notes/keep.md") is not None

    assert prune_result.deleted == 1
    assert prune_result.errors == 0


def test_run_prune_dry_run_does_not_call_api_or_modify_db() -> None:
    """run_prune with dry_run=True counts matched files but makes no API calls or DB changes."""
    db = _make_db()
    _insert_backed_up_file(db, "source/logs/debug.log", drive_file_id="drive-log-id")
    _insert_backed_up_file(db, "source/docs/readme.md", drive_file_id="drive-doc-id")

    mock_client = _make_mock_client()
    config = _make_config("/fake/parent/source", exclude_patterns=["*.log"])

    prune_result = run_prune(config=config, client=mock_client, db_conn=db, dry_run=True)

    # No Drive API calls in dry-run mode
    mock_client.delete_file.assert_not_called()

    # Both DB rows must still exist
    assert get_backed_up_file(db, "source/logs/debug.log") is not None
    assert get_backed_up_file(db, "source/docs/readme.md") is not None

    # The count still reflects what would have been pruned
    assert prune_result.deleted == 1
    assert prune_result.errors == 0


def test_run_prune_excludes_files_not_matching_patterns() -> None:
    """run_prune does not touch files whose paths do not match any exclude_pattern."""
    db = _make_db()
    _insert_backed_up_file(db, "source/archive/old.zip", drive_file_id="drive-zip-id")
    _insert_backed_up_file(db, "source/docs/report.pdf", drive_file_id="drive-pdf-id")
    _insert_backed_up_file(db, "source/docs/notes.md", drive_file_id="drive-notes-id")

    mock_client = _make_mock_client()
    # Pattern only matches .zip files
    config = _make_config("/fake/parent/source", exclude_patterns=["*.zip"])

    prune_result = run_prune(config=config, client=mock_client, db_conn=db)

    mock_client.delete_file.assert_called_once_with("drive-zip-id")

    # .pdf and .md files must be untouched
    assert get_backed_up_file(db, "source/docs/report.pdf") is not None
    assert get_backed_up_file(db, "source/docs/notes.md") is not None
    assert get_backed_up_file(db, "source/archive/old.zip") is None

    assert prune_result.deleted == 1


def test_run_prune_returns_early_when_no_exclude_patterns() -> None:
    """run_prune returns an empty PruneResult immediately when exclude_patterns is empty."""
    db = _make_db()
    _insert_backed_up_file(db, "source/notes/todo.md", drive_file_id="drive-todo-id")

    mock_client = _make_mock_client()
    config = _make_config("/fake/parent/source", exclude_patterns=[])

    prune_result = run_prune(config=config, client=mock_client, db_conn=db)

    mock_client.delete_file.assert_not_called()
    assert prune_result.deleted == 0
    assert prune_result.errors == 0
