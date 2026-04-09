"""Tests for deep_thought.gdrive.db.schema — database initialization."""

from __future__ import annotations

import contextlib
import sqlite3
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

import pytest

from deep_thought.gdrive.db.schema import (
    _get_schema_version,
    _run_migrations,
    _split_sql_statements,
    init_db,
)


def test_init_db_creates_backed_up_files_table() -> None:
    """init_db creates the backed_up_files table."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)

    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='backed_up_files';")
    assert cursor.fetchone() is not None


def test_init_db_creates_drive_folders_table() -> None:
    """init_db creates the drive_folders table."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)

    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='drive_folders';")
    assert cursor.fetchone() is not None


def test_init_db_creates_key_value_table() -> None:
    """init_db creates the key_value table."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)

    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='key_value';")
    assert cursor.fetchone() is not None


def test_init_db_sets_schema_version_to_current() -> None:
    """init_db sets schema_version to the latest migration number in key_value."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)

    cursor = conn.execute("SELECT value FROM key_value WHERE key = 'schema_version';")
    row = cursor.fetchone()
    assert row is not None
    assert row["value"] == "2"


def test_init_db_is_idempotent() -> None:
    """Calling init_db twice on the same connection does not raise or duplicate rows."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    # Second call should be a no-op (CREATE TABLE IF NOT EXISTS)
    init_db(conn)

    cursor = conn.execute("SELECT COUNT(*) as cnt FROM key_value WHERE key = 'schema_version';")
    row = cursor.fetchone()
    assert row["cnt"] == 1


@pytest.mark.parametrize(
    "table_name",
    ["backed_up_files", "drive_folders", "key_value"],
)
def test_all_expected_tables_present(table_name: str) -> None:
    """All three expected tables are created by init_db."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)

    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?;",
        (table_name,),
    )
    assert cursor.fetchone() is not None, f"Table '{table_name}' was not created."


# ---------------------------------------------------------------------------
# TestMigrationTransactionality
# ---------------------------------------------------------------------------


class TestMigrationTransactionality:
    """Verify that _run_migrations keeps migration SQL and version update atomic.

    The key guarantee: if any part of a migration fails — whether inside the
    migration SQL itself or during _set_schema_version — the schema version
    must NOT advance and all schema changes from that migration must be rolled
    back.
    """

    def test_successful_migration_advances_schema_version(self, tmp_path: Path) -> None:
        """A valid migration file must be applied and the version counter must advance."""
        import pathlib

        real_migrations_dir = (
            pathlib.Path(__file__).parents[2] / "src" / "deep_thought" / "gdrive" / "db" / "migrations"
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
        _run_migrations(connection, merged_dir)

        assert _get_schema_version(connection) == next_version
        cursor = connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='test_table';")
        assert cursor.fetchone() is not None
        connection.close()

    def test_migration_with_bad_sql_does_not_advance_schema_version(self, tmp_path: Path) -> None:
        """A migration containing invalid SQL must leave the schema version unchanged."""
        import pathlib

        real_migrations_dir = (
            pathlib.Path(__file__).parents[2] / "src" / "deep_thought" / "gdrive" / "db" / "migrations"
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
            _run_migrations(connection, merged_dir)

        # The schema version must not have advanced past the last good migration.
        assert _get_schema_version(connection) == highest_real_version
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
            pathlib.Path(__file__).parents[2] / "src" / "deep_thought" / "gdrive" / "db" / "migrations"
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
            _run_migrations(connection, merged_dir)

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
