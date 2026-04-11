"""Tests for deep_thought.stackexchange.db.schema.

Tests cover database initialization, migration runner idempotency, and data directory
path resolution.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from deep_thought.stackexchange.db.schema import (
    get_data_dir,
    initialize_database,
    run_migrations,
)

# ---------------------------------------------------------------------------
# TestInitializeDatabase
# ---------------------------------------------------------------------------


class TestInitializeDatabase:
    def test_creates_collected_questions_table(self) -> None:
        """initialize_database should create the collected_questions table."""
        connection = initialize_database(":memory:")
        try:
            cursor = connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='collected_questions';"
            )
            assert cursor.fetchone() is not None
        finally:
            connection.close()

    def test_creates_quota_usage_table(self) -> None:
        """initialize_database should create the quota_usage table."""
        connection = initialize_database(":memory:")
        try:
            cursor = connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='quota_usage';")
            assert cursor.fetchone() is not None
        finally:
            connection.close()

    def test_creates_key_value_table(self) -> None:
        """initialize_database should create the key_value table."""
        connection = initialize_database(":memory:")
        try:
            cursor = connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='key_value';")
            assert cursor.fetchone() is not None
        finally:
            connection.close()

    def test_in_memory_mode_works(self) -> None:
        """initialize_database(':memory:') should return a usable SQLite connection."""
        connection = initialize_database(":memory:")
        try:
            assert isinstance(connection, sqlite3.Connection)
            # Verify the connection is actually usable
            result = connection.execute("SELECT 1;").fetchone()
            assert result is not None
        finally:
            connection.close()

    def test_returns_connection_with_row_factory(self) -> None:
        """The returned connection should use sqlite3.Row as the row factory."""
        connection = initialize_database(":memory:")
        try:
            assert connection.row_factory == sqlite3.Row
        finally:
            connection.close()

    def test_accepts_string_path(self, tmp_path: Path) -> None:
        """initialize_database should accept a string path as well as a Path object."""
        db_path = tmp_path / "test.db"
        connection = initialize_database(str(db_path))
        try:
            assert isinstance(connection, sqlite3.Connection)
            assert db_path.exists()
        finally:
            connection.close()


# ---------------------------------------------------------------------------
# TestRunMigrations
# ---------------------------------------------------------------------------


class TestRunMigrations:
    def test_idempotent_running_twice_is_safe(self) -> None:
        """Running run_migrations twice on the same database should not raise any errors."""
        connection = initialize_database(":memory:")
        migrations_dir = (
            Path(__file__).parent.parent.parent / "src" / "deep_thought" / "stackexchange" / "db" / "migrations"
        )
        try:
            # Running a second time should be a no-op
            run_migrations(connection, migrations_dir)
            run_migrations(connection, migrations_dir)
            # Verify the database is still functional
            cursor = connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='collected_questions';"
            )
            assert cursor.fetchone() is not None
        finally:
            connection.close()

    @pytest.mark.error_handling
    def test_raises_file_not_found_for_missing_migrations_dir(self) -> None:
        """run_migrations should raise FileNotFoundError if the migrations directory is missing."""
        connection = sqlite3.connect(":memory:")
        try:
            with pytest.raises(FileNotFoundError, match="Migrations directory not found"):
                run_migrations(connection, Path("/nonexistent/migrations"))
        finally:
            connection.close()


# ---------------------------------------------------------------------------
# TestGetDataDir
# ---------------------------------------------------------------------------


class TestGetDataDir:
    def test_default_path_contains_stackexchange(self) -> None:
        """get_data_dir() without env override should return a path containing 'stackexchange'."""
        with patch.dict(os.environ, {}, clear=False):
            if "DEEP_THOUGHT_DATA_DIR" in os.environ:
                del os.environ["DEEP_THOUGHT_DATA_DIR"]
            result = get_data_dir()
        assert "stackexchange" in str(result)

    def test_env_override_appends_stackexchange(self, tmp_path: Path) -> None:
        """DEEP_THOUGHT_DATA_DIR override should be joined with 'stackexchange'."""
        custom_data_dir = str(tmp_path / "custom_data")
        with patch.dict(os.environ, {"DEEP_THOUGHT_DATA_DIR": custom_data_dir}):
            result = get_data_dir()
        assert result == Path(custom_data_dir) / "stackexchange"

    def test_returns_path_object(self) -> None:
        """get_data_dir() should return a Path object."""
        result = get_data_dir()
        assert isinstance(result, Path)
