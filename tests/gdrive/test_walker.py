"""Tests for deep_thought.gdrive.walker."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from deep_thought.gdrive.walker import walk_tree

if TYPE_CHECKING:
    from pathlib import Path


def test_walk_tree_finds_all_files_in_nested_dirs(temp_source_dir: Path) -> None:
    """walk_tree returns an entry for every file in the fixture tree."""
    results = walk_tree(str(temp_source_dir))
    relative_paths = {entry[0] for entry in results}

    assert "source/top_level.txt" in relative_paths
    assert "source/notes/meeting.md" in relative_paths
    assert "source/notes/todo.md" in relative_paths
    assert "source/data/report.csv" in relative_paths
    assert len(results) == 4


def test_walk_tree_returns_correct_relative_paths(temp_source_dir: Path) -> None:
    """Relative paths start with the source directory name, not its parent."""
    results = walk_tree(str(temp_source_dir))

    for relative_path, _mtime, _size in results:
        # All paths should start with "source/" (the directory name)
        assert relative_path.startswith("source/"), f"Path {relative_path!r} does not start with 'source/'"
        # No path should be absolute
        assert not relative_path.startswith("/"), f"Path {relative_path!r} is absolute"


def test_walk_tree_skips_hidden_files(tmp_path: Path) -> None:
    """walk_tree skips files whose names start with '.'."""
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "visible.txt").write_text("visible")
    (source_dir / ".hidden").write_text("hidden")
    (source_dir / ".DS_Store").write_text("macos junk")

    results = walk_tree(str(source_dir))
    relative_paths = {entry[0] for entry in results}

    assert "source/visible.txt" in relative_paths
    assert "source/.hidden" not in relative_paths
    assert "source/.DS_Store" not in relative_paths


def test_walk_tree_skips_hidden_directories(tmp_path: Path) -> None:
    """walk_tree does not descend into directories starting with '.'."""
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    hidden_dir = source_dir / ".git"
    hidden_dir.mkdir()
    (hidden_dir / "config").write_text("git config")
    (source_dir / "visible.txt").write_text("visible")

    results = walk_tree(str(source_dir))
    relative_paths = {entry[0] for entry in results}

    assert "source/visible.txt" in relative_paths
    assert not any(".git" in path for path in relative_paths)


@pytest.mark.parametrize(
    "excluded_dir_name",
    ["__pycache__", ".git", ".venv", "node_modules", ".mypy_cache"],
)
def test_walk_tree_skips_excluded_directories(tmp_path: Path, excluded_dir_name: str) -> None:
    """walk_tree does not descend into known excluded directories."""
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    excluded_dir = source_dir / excluded_dir_name
    excluded_dir.mkdir()
    (excluded_dir / "some_file.py").write_text("content")
    (source_dir / "real_file.txt").write_text("real content")

    results = walk_tree(str(source_dir))
    relative_paths = {entry[0] for entry in results}

    assert "source/real_file.txt" in relative_paths
    assert not any(excluded_dir_name in path for path in relative_paths)


@pytest.mark.parametrize(
    "sqlite_sidecar_file_name",
    ["app.db-wal", "app.db-shm", "app.db-journal", "gdrive.db-wal", "gdrive.db-shm"],
)
def test_walk_tree_skips_sqlite_sidecar_files(tmp_path: Path, sqlite_sidecar_file_name: str) -> None:
    """walk_tree skips ephemeral SQLite sidecar files (-wal, -shm, -journal)."""
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "app.db").write_text("primary database")
    (source_dir / sqlite_sidecar_file_name).write_text("ephemeral sqlite state")
    (source_dir / "keep.md").write_text("regular file")

    results = walk_tree(str(source_dir))
    relative_paths = {entry[0] for entry in results}

    assert "source/app.db" in relative_paths
    assert "source/keep.md" in relative_paths
    assert f"source/{sqlite_sidecar_file_name}" not in relative_paths


def test_walk_tree_returns_mtime_and_size(temp_source_dir: Path) -> None:
    """walk_tree entries include mtime (float) and size_bytes (int)."""
    results = walk_tree(str(temp_source_dir))

    for relative_path, mtime, size_bytes in results:
        assert isinstance(mtime, float), f"mtime for {relative_path} is not float"
        assert isinstance(size_bytes, int), f"size_bytes for {relative_path} is not int"
        assert mtime > 0
        assert size_bytes >= 0


def test_walk_tree_detects_mtime_change(tmp_path: Path) -> None:
    """Modifying a file causes walk_tree to return a different mtime for it."""
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    test_file = source_dir / "changeable.txt"
    test_file.write_text("original content")

    first_results = {entry[0]: entry[1] for entry in walk_tree(str(source_dir))}
    original_mtime = first_results["source/changeable.txt"]

    # Ensure filesystem mtime advances by at least 0.01 seconds
    time.sleep(0.05)
    test_file.write_text("modified content")

    second_results = {entry[0]: entry[1] for entry in walk_tree(str(source_dir))}
    new_mtime = second_results["source/changeable.txt"]

    assert new_mtime > original_mtime


def test_walk_tree_returns_empty_list_for_empty_directory(tmp_path: Path) -> None:
    """walk_tree returns an empty list when the source directory has no files."""
    source_dir = tmp_path / "source"
    source_dir.mkdir()

    results = walk_tree(str(source_dir))
    assert results == []


def test_walk_tree_logs_warning_on_permission_error(tmp_path: Path) -> None:
    """walk_tree logs WARNING for OSError other than FileNotFoundError."""
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    target_file = source_dir / "unreadable.txt"
    target_file.write_text("content")

    permission_error = PermissionError("Permission denied")

    with (
        patch("deep_thought.gdrive.walker.Path.stat", side_effect=permission_error),
        patch("deep_thought.gdrive.walker.logger") as mock_logger,
    ):
        results = walk_tree(str(source_dir))

    # The file is skipped — no entries returned
    assert results == []
    # A WARNING must have been emitted (not silently dropped)
    mock_logger.warning.assert_called_once()
    warning_call_args = mock_logger.warning.call_args
    assert "unreadable.txt" in str(warning_call_args) or "Could not stat" in str(warning_call_args[0])


def test_walk_tree_logs_info_when_symlinked_directory_is_skipped(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """walk_tree emits an INFO log when a symlinked directory is encountered and skipped.

    os.walk(followlinks=False) silently omits symlink subtrees; we expect at
    least one INFO-level message from the deep_thought.gdrive.walker logger
    that contains the absolute path of the symlinked directory.
    """
    # Build a real target directory with a file in it.
    target_directory = tmp_path / "link_target"
    target_directory.mkdir()
    (target_directory / "inside.txt").write_text("content inside symlinked directory")

    # Build the source tree and place a symlink to target_directory inside it.
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "real_file.txt").write_text("real content")

    symlinked_dir = source_dir / "external_link"
    symlinked_dir.symlink_to(target_directory)

    with caplog.at_level(logging.INFO, logger="deep_thought.gdrive.walker"):
        results = walk_tree(str(source_dir))

    # The file inside the symlinked directory must NOT appear in results.
    result_paths = {entry[0] for entry in results}
    assert "source/real_file.txt" in result_paths
    assert not any("inside.txt" in path for path in result_paths), (
        "Files inside a symlinked directory must not be collected"
    )

    # An INFO log must have been emitted that contains the symlink path.
    symlink_log_records = [
        record
        for record in caplog.records
        if record.levelno == logging.INFO and str(symlinked_dir) in record.getMessage()
    ]
    assert len(symlink_log_records) >= 1, (
        f"Expected at least one INFO log mentioning {symlinked_dir!s}; "
        f"got records: {[r.getMessage() for r in caplog.records]}"
    )
