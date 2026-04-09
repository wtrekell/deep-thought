"""Tests for the Audio Tool database schema: initialization, migrations, and pragma settings.

All tests use in-memory SQLite (no disk writes).
"""

from __future__ import annotations

import contextlib
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from deep_thought.audio.db.schema import (
    _split_sql_statements,
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


# ---------------------------------------------------------------------------
# TestMigrationTransactionality
# ---------------------------------------------------------------------------


class TestMigrationTransactionality:
    """Verify that run_migrations keeps migration SQL and version update atomic.

    The key guarantee: if any part of a migration fails — whether inside the
    migration SQL itself or during _set_schema_version — the schema version
    must NOT advance and all schema changes from that migration must be rolled
    back.
    """

    def test_successful_migration_advances_schema_version(self, tmp_path: Path) -> None:
        """A valid migration file must be applied and the version counter must advance."""
        import pathlib

        real_migrations_dir = pathlib.Path(__file__).parents[2] / "src" / "deep_thought" / "audio" / "db" / "migrations"

        # Find the highest migration number from the real migration files.
        real_migration_numbers = []
        for real_sql_file in real_migrations_dir.glob("*.sql"):
            prefix = real_sql_file.stem.split("_")[0]
            with contextlib.suppress(ValueError):
                real_migration_numbers.append(int(prefix))
        highest_real_version = max(real_migration_numbers)

        # Build a merged migrations dir containing the real migrations plus one
        # additional valid migration numbered just beyond the current highest.
        merged_dir = tmp_path / "merged_migrations"
        merged_dir.mkdir()
        for real_sql_file in sorted(real_migrations_dir.glob("*.sql")):
            (merged_dir / real_sql_file.name).write_text(real_sql_file.read_text(encoding="utf-8"), encoding="utf-8")

        next_version = highest_real_version + 1
        extra_migration_file = merged_dir / f"{next_version:03d}_create_test_table.sql"
        extra_migration_file.write_text("CREATE TABLE test_table (id INTEGER PRIMARY KEY);", encoding="utf-8")

        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        run_migrations(connection, merged_dir)

        assert get_schema_version(connection) == next_version
        cursor = connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='test_table';")
        assert cursor.fetchone() is not None
        connection.close()

    def test_migration_with_bad_sql_does_not_advance_schema_version(self, tmp_path: Path) -> None:
        """A migration containing invalid SQL must leave the schema version unchanged."""
        import pathlib

        real_migrations_dir = pathlib.Path(__file__).parents[2] / "src" / "deep_thought" / "audio" / "db" / "migrations"

        real_migration_numbers = []
        for real_sql_file in real_migrations_dir.glob("*.sql"):
            prefix = real_sql_file.stem.split("_")[0]
            with contextlib.suppress(ValueError):
                real_migration_numbers.append(int(prefix))
        highest_real_version = max(real_migration_numbers)

        # Build a merged migrations dir: real migrations + one bad migration.
        merged_dir = tmp_path / "merged_migrations"
        merged_dir.mkdir()
        for real_sql_file in sorted(real_migrations_dir.glob("*.sql")):
            (merged_dir / real_sql_file.name).write_text(real_sql_file.read_text(encoding="utf-8"), encoding="utf-8")

        bad_migration_number = highest_real_version + 1
        bad_migration_file = merged_dir / f"{bad_migration_number:03d}_bad_migration.sql"
        bad_migration_file.write_text("THIS IS NOT VALID SQL AT ALL;", encoding="utf-8")

        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row

        with pytest.raises(sqlite3.Error):
            run_migrations(connection, merged_dir)

        # The schema version must not have advanced past the last good migration.
        assert get_schema_version(connection) == highest_real_version
        connection.close()

    def test_tables_created_in_bad_migration_are_rolled_back(self, tmp_path: Path) -> None:
        """Schema changes from a failed migration must not persist after rollback.

        This is the core regression test: previously executescript() committed
        the DDL before _set_schema_version ran, making rollback impossible.
        Now, a CREATE TABLE that is part of a migration which subsequently
        fails must be absent from the schema after the error.
        """
        import pathlib

        real_migrations_dir = pathlib.Path(__file__).parents[2] / "src" / "deep_thought" / "audio" / "db" / "migrations"

        real_migration_numbers = []
        for real_sql_file in real_migrations_dir.glob("*.sql"):
            prefix = real_sql_file.stem.split("_")[0]
            with contextlib.suppress(ValueError):
                real_migration_numbers.append(int(prefix))
        highest_real_version = max(real_migration_numbers)

        merged_dir = tmp_path / "merged_migrations"
        merged_dir.mkdir()
        for real_sql_file in sorted(real_migrations_dir.glob("*.sql")):
            (merged_dir / real_sql_file.name).write_text(real_sql_file.read_text(encoding="utf-8"), encoding="utf-8")

        # Migration that creates a table then contains bad SQL.
        # With executescript() the CREATE TABLE would be committed before the error;
        # with conn.execute() it must roll back together.
        bad_migration_number = highest_real_version + 1
        bad_migration_file = merged_dir / f"{bad_migration_number:03d}_partial_migration.sql"
        bad_migration_file.write_text(
            "CREATE TABLE should_not_exist (id INTEGER PRIMARY KEY);\nNOT VALID SQL;",
            encoding="utf-8",
        )

        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row

        with pytest.raises(sqlite3.Error):
            run_migrations(connection, merged_dir)

        # The table created in the first statement of the failed migration must
        # not exist — the transaction must have been rolled back in full.
        cursor = connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='should_not_exist';")
        assert cursor.fetchone() is None, "CREATE TABLE from the failed migration must be rolled back, not committed"
        connection.close()


# ---------------------------------------------------------------------------
# TestSplitSqlStatements
# ---------------------------------------------------------------------------


class TestSplitSqlStatements:
    def test_single_statement_without_comment(self) -> None:
        """A single statement with no comments must be returned as one entry."""
        sql_input = "CREATE TABLE foo (id INTEGER PRIMARY KEY);"
        result = _split_sql_statements(sql_input)
        assert result == ["CREATE TABLE foo (id INTEGER PRIMARY KEY)"]

    def test_multiple_statements_are_split_correctly(self) -> None:
        """Two statements separated by a semicolon must each appear as one entry."""
        sql_input = "CREATE TABLE foo (id INTEGER);\nCREATE TABLE bar (id INTEGER);"
        result = _split_sql_statements(sql_input)
        assert len(result) == 2
        assert "CREATE TABLE foo (id INTEGER)" in result
        assert "CREATE TABLE bar (id INTEGER)" in result

    def test_line_comments_are_stripped_before_split(self) -> None:
        """SQL line comments (-- ...) must be removed before semicolon splitting."""
        sql_input = "-- This is a comment\nCREATE TABLE baz (id INTEGER);"
        result = _split_sql_statements(sql_input)
        assert len(result) == 1
        assert result[0] == "CREATE TABLE baz (id INTEGER)"

    def test_semicolon_inside_comment_does_not_split(self) -> None:
        """A semicolon appearing inside a -- comment must not be treated as a statement terminator."""
        sql_input = "-- Note: do not use; here\nCREATE TABLE qux (id INTEGER);"
        result = _split_sql_statements(sql_input)
        assert len(result) == 1
        assert "CREATE TABLE qux" in result[0]

    def test_blank_statements_after_trailing_semicolon_are_excluded(self) -> None:
        """Trailing semicolons must not produce empty string entries in the result."""
        sql_input = "CREATE TABLE foo (id INTEGER);\n"
        result = _split_sql_statements(sql_input)
        assert all(statement for statement in result), "All returned statements must be non-empty"

    def test_empty_string_returns_empty_list(self) -> None:
        """An empty or whitespace-only input must return an empty list."""
        assert _split_sql_statements("") == []
        assert _split_sql_statements("   \n  ") == []

    def test_comment_only_input_returns_empty_list(self) -> None:
        """A file that contains only SQL comments must produce no runnable statements."""
        sql_input = "-- Just a comment\n-- Another comment\n"
        result = _split_sql_statements(sql_input)
        assert result == []
