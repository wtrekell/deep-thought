"""Shared pytest fixtures for the GDrive tool tests."""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

from deep_thought.gdrive.config import GDriveConfig
from deep_thought.gdrive.db.schema import init_db

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def in_memory_db() -> sqlite3.Connection:
    """Return an in-memory SQLite connection with the GDrive schema applied."""
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    init_db(connection)
    return connection


@pytest.fixture
def mock_drive_service() -> MagicMock:
    """Return a MagicMock representing the Google Drive API service object."""
    service = MagicMock()
    return service


@pytest.fixture
def mock_credentials() -> MagicMock:
    """Return a MagicMock representing google.oauth2.credentials.Credentials."""
    credentials = MagicMock()
    credentials.valid = True
    credentials.expired = False
    credentials.refresh_token = "fake-refresh-token"
    credentials.to_json.return_value = '{"token": "fake"}'
    return credentials


@pytest.fixture
def temp_source_dir(tmp_path: Path) -> Path:
    """Create a small directory tree with 4 files across 2 subdirectories.

    Tree structure:
        source/
            top_level.txt
            notes/
                meeting.md
                todo.md
            data/
                report.csv
    """
    source_dir = tmp_path / "source"
    source_dir.mkdir()

    # Top-level file
    (source_dir / "top_level.txt").write_text("top level content")

    # notes/ subdirectory
    notes_dir = source_dir / "notes"
    notes_dir.mkdir()
    (notes_dir / "meeting.md").write_text("# Meeting notes")
    (notes_dir / "todo.md").write_text("# To-do list")

    # data/ subdirectory
    data_dir = source_dir / "data"
    data_dir.mkdir()
    (data_dir / "report.csv").write_text("col1,col2\nval1,val2")

    return source_dir


@pytest.fixture
def sample_config(tmp_path: Path) -> GDriveConfig:
    """Return a GDriveConfig instance with test-safe values."""
    return GDriveConfig(
        credentials_file=str(tmp_path / "credentials.json"),
        token_file=str(tmp_path / "token.json"),
        scopes=["https://www.googleapis.com/auth/drive.file"],
        source_dir=str(tmp_path / "source"),
        drive_folder_id="test-root-folder-id",
        exclude_patterns=[],
        api_rate_limit_rpm=100,
        retry_max_attempts=3,
        retry_base_delay_seconds=2.0,
    )
