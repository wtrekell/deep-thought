"""Tests for the Audio Tool database schema: initialization, migrations, and pragma settings.

All tests use in-memory SQLite (no disk writes).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest

from deep_thought.audio.db.schema import (
    get_connection,
    get_data_dir,
    get_database_path,
    get_schema_version,
    initialize_database,
    run_migrations,
)

# ---------------------------------------------------------------------------
# initialize_database
# ---------------------------------------------------------------------------


class TestInitializeDatabase:
    def test_creates_processed_files_table(self, in_memory_db: Any) -> None:
        """processed_files table must exist after initialization."""
        cursor = in_memory_db.execute("SELECT name FROM sqlite_master WHERE type='table';")
        table_names = {row["name"] for row in cursor.fetchall()}
        assert "processed_files" in table_names

    def test_creates_key_value_table(self, in_memory_db: Any) -> None:
        """key_value table must exist after initialization."""
        cursor = in_memory_db.execute("SELECT name FROM sqlite_master WHERE type='table';")
        table_names = {row["name"] for row in cursor.fetchall()}
        assert "key_value" in table_names

    def test_schema_version_is_nonzero_after_init(self, in_memory_db: Any) -> None:
        """After initialization, schema version must be at least 1."""
        version = get_schema_version(in_memory_db)
        assert version >= 1

    def test_schema_version_returns_zero_on_empty_connection(self) -> None:
        """get_schema_version on a raw connection with no tables must return 0."""
        raw_conn = sqlite3.connect(":memory:")
        raw_conn.row_factory = sqlite3.Row
        version = get_schema_version(raw_conn)
        raw_conn.close()
        assert version == 0

    def test_accepts_memory_string(self) -> None:
        """initialize_database(':memory:') must succeed without raising."""
        conn = initialize_database(":memory:")
        conn.close()

    def test_accepts_path_object(self, tmp_path: Path) -> None:
        """initialize_database(Path(...)) must succeed and create the file."""
        db_file = tmp_path / "audio.db"
        conn = initialize_database(db_file)
        conn.close()
        assert db_file.exists()


# ---------------------------------------------------------------------------
# run_migrations (idempotency)
# ---------------------------------------------------------------------------


class TestRunMigrations:
    def test_applying_migrations_sets_schema_version(self) -> None:
        """run_migrations must record a non-zero schema version in key_value."""
        conn = initialize_database(":memory:")
        version = get_schema_version(conn)
        conn.close()
        assert version >= 1

    def test_run_migrations_is_idempotent(self) -> None:
        """Running run_migrations twice on the SAME connection must not raise or duplicate work."""
        conn = initialize_database(":memory:")
        migrations_dir = Path(__file__).parents[2] / "src" / "deep_thought" / "audio" / "db" / "migrations"
        version_before_second_run = get_schema_version(conn)
        # A second call must be a no-op — no errors, no version change
        run_migrations(conn, migrations_dir)
        version_after_second_run = get_schema_version(conn)
        conn.close()
        assert version_before_second_run == version_after_second_run

    def test_run_migrations_does_not_reapply_applied_migrations(self) -> None:
        """Running run_migrations a second time on the same connection must be a no-op."""
        conn = initialize_database(":memory:")
        migrations_dir = Path(__file__).parents[2] / "src" / "deep_thought" / "audio" / "db" / "migrations"
        version_before = get_schema_version(conn)
        run_migrations(conn, migrations_dir)
        version_after = get_schema_version(conn)
        conn.close()
        assert version_before == version_after

    def test_run_migrations_raises_for_missing_directory(self) -> None:
        """run_migrations must raise FileNotFoundError for a non-existent directory."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        with pytest.raises(FileNotFoundError):
            run_migrations(conn, Path("/nonexistent/migrations/path"))
        conn.close()


# ---------------------------------------------------------------------------
# Connection pragma settings
# ---------------------------------------------------------------------------


class TestConnectionSettings:
    def test_wal_mode_is_enabled(self, tmp_path: Path) -> None:
        """WAL journal mode must be active on a file-backed connection.

        SQLite silently ignores the WAL pragma for in-memory databases and
        keeps them in 'memory' mode, so this test uses a temporary file.
        """
        db_file = tmp_path / "audio.db"
        conn = initialize_database(db_file)
        cursor = conn.execute("PRAGMA journal_mode;")
        journal_mode = cursor.fetchone()[0]
        conn.close()
        assert journal_mode == "wal"

    def test_foreign_keys_are_enabled(self, in_memory_db: Any) -> None:
        """Foreign key enforcement must be ON."""
        cursor = in_memory_db.execute("PRAGMA foreign_keys;")
        foreign_keys_enabled = cursor.fetchone()[0]
        assert foreign_keys_enabled == 1

    def test_row_factory_is_sqlite_row(self, in_memory_db: Any) -> None:
        """row_factory must be set to sqlite3.Row so columns are name-accessible."""
        assert in_memory_db.row_factory is sqlite3.Row


# ---------------------------------------------------------------------------
# get_data_dir
# ---------------------------------------------------------------------------


class TestGetDataDir:
    def test_returns_default_path_ending_in_data_audio(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Default data dir must end with data/audio when env var is not set."""
        monkeypatch.delenv("DEEP_THOUGHT_DATA_DIR", raising=False)
        result = get_data_dir()
        assert result.parts[-2:] == ("data", "audio")

    def test_returns_env_override_when_set(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """When DEEP_THOUGHT_DATA_DIR is set, get_data_dir must return that path with /audio appended."""
        monkeypatch.setenv("DEEP_THOUGHT_DATA_DIR", str(tmp_path))
        result = get_data_dir()
        assert result == tmp_path / "audio"


# ---------------------------------------------------------------------------
# get_connection / get_database_path (T-07)
# ---------------------------------------------------------------------------


class TestGetConnection:
    def test_returns_connection_with_row_factory(self, tmp_path: Path) -> None:
        """get_connection must return a connection with sqlite3.Row as row_factory."""
        db_path = tmp_path / "test.db"
        conn = get_connection(db_path)
        assert conn.row_factory is sqlite3.Row
        conn.close()

    def test_row_accessible_by_column_name(self, tmp_path: Path) -> None:
        """Rows returned via the connection must support column-name access."""
        db_path = tmp_path / "test.db"
        conn = get_connection(db_path)
        conn.execute("CREATE TABLE t (id INTEGER, name TEXT)")
        conn.execute("INSERT INTO t VALUES (1, 'hello')")
        conn.commit()
        row = conn.execute("SELECT id, name FROM t").fetchone()
        conn.close()
        assert row is not None
        assert row["name"] == "hello"

    def test_foreign_keys_pragma_is_on(self, tmp_path: Path) -> None:
        """get_connection must enable foreign key enforcement."""
        db_path = tmp_path / "test.db"
        conn = get_connection(db_path)
        cursor = conn.execute("PRAGMA foreign_keys;")
        foreign_keys_value = cursor.fetchone()[0]
        conn.close()
        assert foreign_keys_value == 1

    def test_defaults_to_database_path_when_none(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """get_connection() with no argument must open the canonical database path."""
        monkeypatch.setenv("DEEP_THOUGHT_DATA_DIR", str(tmp_path))
        conn = get_connection()
        # The connection must be usable — execute a no-op statement without error
        conn.execute("SELECT 1;")
        conn.close()


class TestGetDatabasePath:
    def test_returns_path_ending_in_audio_db(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """get_database_path() must return a path ending in audio.db."""
        monkeypatch.setenv("DEEP_THOUGHT_DATA_DIR", str(tmp_path))
        db_path = get_database_path()
        assert db_path.name == "audio.db"

    def test_creates_parent_directory(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """get_database_path() must create the parent directory if it does not exist."""
        monkeypatch.setenv("DEEP_THOUGHT_DATA_DIR", str(tmp_path / "new_data"))
        db_path = get_database_path()
        assert db_path.parent.exists()

    def test_path_is_inside_data_dir(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """The database path must reside inside the configured data directory."""
        monkeypatch.setenv("DEEP_THOUGHT_DATA_DIR", str(tmp_path))
        db_path = get_database_path()
        data_dir = get_data_dir()
        assert db_path.parent == data_dir
