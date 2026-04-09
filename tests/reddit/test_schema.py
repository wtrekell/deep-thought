"""Tests for db/schema.py — database initialisation and migration runner.

All tests that touch the database use in-memory SQLite; tests for path helpers
use monkeypatching so no disk state is created.
"""

from __future__ import annotations

import contextlib
import sqlite3
from pathlib import Path

import pytest

from deep_thought.reddit.db.schema import (
    _split_sql_statements,
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

        real_migrations_dir = (
            pathlib.Path(__file__).parents[2] / "src" / "deep_thought" / "reddit" / "db" / "migrations"
        )

        # Find the highest migration number from the real migration files.
        real_migration_numbers = []
        for real_sql_file in real_migrations_dir.glob("*.sql"):
            prefix = real_sql_file.stem.split("_")[0]
            with contextlib.suppress(ValueError):
                real_migration_numbers.append(int(prefix))
        highest_real_version = max(real_migration_numbers)

        # Build a merged migrations dir: real migrations + one additional valid migration.
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

        real_migrations_dir = (
            pathlib.Path(__file__).parents[2] / "src" / "deep_thought" / "reddit" / "db" / "migrations"
        )

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

        real_migrations_dir = (
            pathlib.Path(__file__).parents[2] / "src" / "deep_thought" / "reddit" / "db" / "migrations"
        )

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
