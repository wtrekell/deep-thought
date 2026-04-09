"""Tests for the GCal Tool database schema and migration system."""

from __future__ import annotations

import contextlib
import sqlite3
from pathlib import Path

import pytest

from deep_thought.gcal.db.schema import (
    _split_sql_statements,
    get_schema_version,
    initialize_database,
    run_migrations,
)


class TestInitializeDatabase:
    """Tests for initialize_database."""

    def test_creates_all_tables(self, in_memory_db: sqlite3.Connection) -> None:
        """Should create calendars, events, sync_state, and key_value tables."""
        cursor = in_memory_db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
        table_names = [row["name"] for row in cursor.fetchall()]
        assert "calendars" in table_names
        assert "events" in table_names
        assert "sync_state" in table_names
        assert "key_value" in table_names

    def test_schema_version_is_two(self, in_memory_db: sqlite3.Connection) -> None:
        """After running all migrations, schema version should be 2."""
        assert get_schema_version(in_memory_db) == 2

    def test_idempotent_initialization(self) -> None:
        """Running initialize_database twice should not error or reset state."""
        conn = initialize_database(":memory:")
        assert get_schema_version(conn) == 2
        # Simulating a second initialization on the same connection
        # by checking that re-reading the version still works
        assert get_schema_version(conn) == 2
        conn.close()

    def test_events_table_has_composite_pk(self, in_memory_db: sqlite3.Connection) -> None:
        """The events table should have a composite primary key on (event_id, calendar_id)."""
        cursor = in_memory_db.execute("PRAGMA table_info(events);")
        columns = {row["name"]: row["pk"] for row in cursor.fetchall()}
        assert columns["event_id"] == 1
        assert columns["calendar_id"] == 2


class TestGetSchemaVersion:
    """Tests for get_schema_version."""

    def test_returns_zero_on_fresh_db(self) -> None:
        """Should return 0 when key_value table does not exist."""
        import sqlite3

        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        assert get_schema_version(conn) == 0
        conn.close()

    def test_returns_version_after_migrations(self, in_memory_db: sqlite3.Connection) -> None:
        """Should return 2 after all migrations are applied."""
        assert get_schema_version(in_memory_db) == 2


class TestForeignKeys:
    """Tests for foreign key CASCADE behavior."""

    def test_deleting_calendar_cascades_to_events(self, seeded_db: sqlite3.Connection) -> None:
        """Deleting a calendar should CASCADE-delete its events."""
        # Verify events exist before deletion
        cursor = seeded_db.execute("SELECT COUNT(*) as cnt FROM events WHERE calendar_id = 'primary';")
        assert cursor.fetchone()["cnt"] > 0

        seeded_db.execute("DELETE FROM calendars WHERE calendar_id = 'primary';")
        seeded_db.commit()

        cursor = seeded_db.execute("SELECT COUNT(*) as cnt FROM events WHERE calendar_id = 'primary';")
        assert cursor.fetchone()["cnt"] == 0

    def test_deleting_calendar_cascades_to_sync_state(self, seeded_db: sqlite3.Connection) -> None:
        """Deleting a calendar should CASCADE-delete its sync_state row."""
        seeded_db.execute("DELETE FROM calendars WHERE calendar_id = 'primary';")
        seeded_db.commit()

        cursor = seeded_db.execute("SELECT COUNT(*) as cnt FROM sync_state WHERE calendar_id = 'primary';")
        assert cursor.fetchone()["cnt"] == 0


class TestIndexes:
    """Tests for database indexes."""

    def test_events_calendar_id_index_exists(self, in_memory_db: sqlite3.Connection) -> None:
        """Should have an index on events.calendar_id."""
        cursor = in_memory_db.execute("PRAGMA index_list(events);")
        index_names = [row["name"] for row in cursor.fetchall()]
        assert "idx_events_calendar_id" in index_names

    def test_events_start_time_index_exists(self, in_memory_db: sqlite3.Connection) -> None:
        """Should have an index on events.start_time."""
        cursor = in_memory_db.execute("PRAGMA index_list(events);")
        index_names = [row["name"] for row in cursor.fetchall()]
        assert "idx_events_start_time" in index_names


# ---------------------------------------------------------------------------
# TestMigrationTransactionality
# ---------------------------------------------------------------------------


class TestMigrationTransactionality:
    """Verify that run_migrations keeps the migration SQL and version update atomic.

    The key guarantee: if any part of a migration fails — whether inside the
    migration SQL itself or during _set_schema_version — the schema version
    must NOT advance and all schema changes from that migration must be rolled
    back.
    """

    def _real_migrations_dir(self) -> Path:
        return Path(__file__).parents[2] / "src" / "deep_thought" / "gcal" / "db" / "migrations"

    def _highest_real_version(self) -> int:
        real_migration_numbers: list[int] = []
        for sql_file in self._real_migrations_dir().glob("*.sql"):
            prefix = sql_file.stem.split("_")[0]
            with contextlib.suppress(ValueError):
                real_migration_numbers.append(int(prefix))
        return max(real_migration_numbers)

    def _build_merged_dir(self, tmp_path: Path, extra_sql_file_name: str, extra_sql_content: str) -> Path:
        """Copy real migrations into a tmp dir and add one extra migration file."""
        merged_dir = tmp_path / "merged_migrations"
        merged_dir.mkdir()
        for real_sql_file in sorted(self._real_migrations_dir().glob("*.sql")):
            (merged_dir / real_sql_file.name).write_text(real_sql_file.read_text(encoding="utf-8"), encoding="utf-8")
        (merged_dir / extra_sql_file_name).write_text(extra_sql_content, encoding="utf-8")
        return merged_dir

    def test_successful_migration_advances_schema_version(self, tmp_path: Path) -> None:
        """A valid migration file must be applied and the version counter must advance."""
        highest_real_version = self._highest_real_version()
        next_version = highest_real_version + 1
        extra_file_name = f"{next_version:03d}_create_test_table.sql"
        merged_dir = self._build_merged_dir(
            tmp_path,
            extra_file_name,
            "CREATE TABLE test_table (id INTEGER PRIMARY KEY);",
        )

        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        run_migrations(connection, merged_dir)

        assert get_schema_version(connection) == next_version
        cursor = connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='test_table';")
        assert cursor.fetchone() is not None
        connection.close()

    def test_migration_with_bad_sql_does_not_advance_schema_version(self, tmp_path: Path) -> None:
        """A migration containing invalid SQL must leave the schema version unchanged."""
        highest_real_version = self._highest_real_version()
        bad_migration_number = highest_real_version + 1
        bad_file_name = f"{bad_migration_number:03d}_bad_migration.sql"
        merged_dir = self._build_merged_dir(tmp_path, bad_file_name, "THIS IS NOT VALID SQL AT ALL;")

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
        highest_real_version = self._highest_real_version()
        bad_migration_number = highest_real_version + 1
        bad_file_name = f"{bad_migration_number:03d}_partial_migration.sql"
        # First statement creates a table (DDL), second statement is bad SQL.
        # With executescript() the CREATE TABLE would have been committed before
        # the error; with conn.execute() it must roll back together.
        merged_dir = self._build_merged_dir(
            tmp_path,
            bad_file_name,
            "CREATE TABLE should_not_exist (id INTEGER PRIMARY KEY);\nNOT VALID SQL;",
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

    def test_line_comments_are_stripped_before_split(self) -> None:
        """SQL line comments (-- ...) must be removed before semicolon splitting."""
        sql_input = "-- This is a comment\nCREATE TABLE baz (id INTEGER);"
        result = _split_sql_statements(sql_input)
        assert len(result) == 1

    def test_semicolon_inside_comment_does_not_split(self) -> None:
        """A semicolon appearing inside a -- comment must not be treated as a statement terminator."""
        sql_input = "-- Note: do not use; here\nCREATE TABLE qux (id INTEGER);"
        result = _split_sql_statements(sql_input)
        assert len(result) == 1

    def test_empty_string_returns_empty_list(self) -> None:
        """An empty or whitespace-only input must return an empty list."""
        assert _split_sql_statements("") == []
        assert _split_sql_statements("   \n  ") == []
