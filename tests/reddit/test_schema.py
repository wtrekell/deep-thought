"""Tests for db/schema.py — database initialisation and migration runner.

All tests that touch the database use in-memory SQLite; tests for path helpers
use monkeypatching so no disk state is created.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from deep_thought.reddit.db.schema import (
    get_data_dir,
    get_database_path,
    get_schema_version,
    initialize_database,
    run_migrations,
)

# ---------------------------------------------------------------------------
# get_data_dir
# ---------------------------------------------------------------------------


class TestGetDataDir:
    def test_uses_env_var_with_reddit_suffix(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When DEEP_THOUGHT_DATA_DIR is set, returned path must end with /reddit."""
        monkeypatch.setenv("DEEP_THOUGHT_DATA_DIR", "/tmp/custom_data")
        result = get_data_dir()
        assert result == Path("/tmp/custom_data/reddit")

    def test_falls_back_to_project_root_data_dir(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Without the env var, the path should be <project_root>/data/reddit."""
        monkeypatch.delenv("DEEP_THOUGHT_DATA_DIR", raising=False)
        result = get_data_dir()
        assert result.parts[-2:] == ("data", "reddit")

    def test_env_var_path_is_a_path_object(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The return type must always be a Path instance."""
        monkeypatch.setenv("DEEP_THOUGHT_DATA_DIR", "/some/path")
        result = get_data_dir()
        assert isinstance(result, Path)


# ---------------------------------------------------------------------------
# get_database_path
# ---------------------------------------------------------------------------


class TestGetDatabasePath:
    def test_database_path_ends_with_reddit_db(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """The database path must end with reddit.db."""
        monkeypatch.setenv("DEEP_THOUGHT_DATA_DIR", str(tmp_path))
        result = get_database_path()
        assert result.name == "reddit.db"

    def test_creates_parent_directory(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """The parent directory must be created if it doesn't already exist."""
        data_dir = tmp_path / "new_dir"
        monkeypatch.setenv("DEEP_THOUGHT_DATA_DIR", str(data_dir))
        db_path = get_database_path()
        assert db_path.parent.exists()


# ---------------------------------------------------------------------------
# initialize_database
# ---------------------------------------------------------------------------


class TestInitializeDatabase:
    def test_returns_sqlite_connection(self) -> None:
        """initialize_database(':memory:') must return an sqlite3.Connection."""
        conn = initialize_database(":memory:")
        try:
            assert isinstance(conn, sqlite3.Connection)
        finally:
            conn.close()

    def test_collected_posts_table_exists(self) -> None:
        """The collected_posts table must exist after initialization."""
        conn = initialize_database(":memory:")
        try:
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='collected_posts';")
            row = cursor.fetchone()
            assert row is not None
        finally:
            conn.close()

    def test_key_value_table_exists(self) -> None:
        """The key_value table must exist after initialization."""
        conn = initialize_database(":memory:")
        try:
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='key_value';")
            row = cursor.fetchone()
            assert row is not None
        finally:
            conn.close()

    def test_schema_version_is_set_after_migration(self) -> None:
        """After initialization, the schema version must be >= 1."""
        conn = initialize_database(":memory:")
        try:
            version = get_schema_version(conn)
            assert version >= 1
        finally:
            conn.close()

    def test_row_factory_is_sqlite_row(self) -> None:
        """The connection row_factory must be sqlite3.Row for column-by-name access."""
        conn = initialize_database(":memory:")
        try:
            assert conn.row_factory is sqlite3.Row
        finally:
            conn.close()

    def test_accepts_path_object(self, tmp_path: Path) -> None:
        """initialize_database must accept a Path object, not just a string."""
        db_path = tmp_path / "test.db"
        conn = initialize_database(db_path)
        try:
            assert isinstance(conn, sqlite3.Connection)
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# run_migrations
# ---------------------------------------------------------------------------


class TestRunMigrations:
    def test_raises_if_migrations_dir_missing(self) -> None:
        """A missing migrations directory must raise FileNotFoundError."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        try:
            with pytest.raises(FileNotFoundError):
                run_migrations(conn, Path("/nonexistent/migrations/"))
        finally:
            conn.close()

    def test_applies_sql_file_in_order(self, tmp_path: Path) -> None:
        """A valid migration SQL file should be applied successfully."""
        migrations_dir = tmp_path / "migrations"
        migrations_dir.mkdir()
        migration_file = migrations_dir / "001_create_test_table.sql"
        kv_ddl = (
            "CREATE TABLE IF NOT EXISTS key_value "
            "(key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL);"
        )
        migration_file.write_text(kv_ddl, encoding="utf-8")

        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        try:
            run_migrations(conn, migrations_dir)
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='key_value';")
            assert cursor.fetchone() is not None
        finally:
            conn.close()

    def test_skips_already_applied_migration(self, tmp_path: Path) -> None:
        """A migration whose number is <= the current schema version must be skipped."""
        migrations_dir = tmp_path / "migrations"
        migrations_dir.mkdir()
        migration_file = migrations_dir / "001_init.sql"
        kv_ddl = (
            "CREATE TABLE IF NOT EXISTS key_value "
            "(key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL);"
        )
        migration_file.write_text(kv_ddl, encoding="utf-8")

        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        try:
            # Apply migration once
            run_migrations(conn, migrations_dir)
            version_after_first = get_schema_version(conn)
            assert version_after_first == 1

            # Running again must not error (idempotent)
            run_migrations(conn, migrations_dir)
            assert get_schema_version(conn) == 1
        finally:
            conn.close()

    def test_non_numeric_filename_is_skipped(self, tmp_path: Path) -> None:
        """Migration files without a numeric prefix must be silently ignored."""
        migrations_dir = tmp_path / "migrations"
        migrations_dir.mkdir()
        bad_file = migrations_dir / "no_prefix.sql"
        bad_file.write_text("CREATE TABLE bad_table (id INTEGER);", encoding="utf-8")

        # Also create a minimal key_value table so we can check schema version
        valid_file = migrations_dir / "001_init.sql"
        kv_ddl = (
            "CREATE TABLE IF NOT EXISTS key_value "
            "(key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL);"
        )
        valid_file.write_text(kv_ddl, encoding="utf-8")

        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        try:
            run_migrations(conn, migrations_dir)
            # Only the numeric migration should have been applied
            assert get_schema_version(conn) == 1
            # The non-numeric file's table must not exist
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='bad_table';")
            assert cursor.fetchone() is None
        finally:
            conn.close()
