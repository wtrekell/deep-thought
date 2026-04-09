"""Tests for the Gmail Tool database schema initialization and migrations."""

from __future__ import annotations

import contextlib
import sqlite3
from pathlib import Path

import pytest

from deep_thought.gmail.db.schema import (
    _split_sql_statements,
    get_schema_version,
    initialize_database,
    run_migrations,
)


class TestInitializeDatabase:
    """Tests for the initialize_database entry point."""

    def test_creates_tables_in_memory(self) -> None:
        """In-memory database should have all three tables after initialization."""
        conn = initialize_database(":memory:")
        try:
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
            table_names = [row["name"] for row in cursor.fetchall()]
            assert "decision_cache" in table_names
            assert "key_value" in table_names
            assert "processed_emails" in table_names
        finally:
            conn.close()

    def test_schema_version_set_to_one(self) -> None:
        """After running the initial migration, schema version should be 1."""
        conn = initialize_database(":memory:")
        try:
            version = get_schema_version(conn)
            assert version == 1
        finally:
            conn.close()

    def test_idempotent_initialization(self) -> None:
        """Running initialize_database twice should not fail or change schema version."""
        conn = initialize_database(":memory:")
        try:
            # Simulate a second call by re-running migrations on the same connection
            from pathlib import Path

            from deep_thought.gmail.db.schema import run_migrations

            migrations_dir = (
                Path(__file__).parent.parent.parent / "src" / "deep_thought" / "gmail" / "db" / "migrations"
            )
            run_migrations(conn, migrations_dir)
            assert get_schema_version(conn) == 1
        finally:
            conn.close()


class TestGetSchemaVersion:
    """Tests for the get_schema_version function."""

    def test_returns_zero_on_fresh_database(self) -> None:
        """A fresh connection with no key_value table should return version 0."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        try:
            version = get_schema_version(conn)
            assert version == 0
        finally:
            conn.close()

    def test_returns_one_after_migration(self, in_memory_db: sqlite3.Connection) -> None:
        """After initialization with migration 001, version should be 1."""
        assert get_schema_version(in_memory_db) == 1


class TestConnectionPragmas:
    """Tests for connection pragma settings."""

    def test_row_factory_is_sqlite_row(self) -> None:
        """Connection should use sqlite3.Row as the row factory."""
        conn = initialize_database(":memory:")
        try:
            assert conn.row_factory is sqlite3.Row
        finally:
            conn.close()

    def test_foreign_keys_enabled(self) -> None:
        """Foreign key enforcement should be active."""
        conn = initialize_database(":memory:")
        try:
            cursor = conn.execute("PRAGMA foreign_keys;")
            row = cursor.fetchone()
            assert row[0] == 1
        finally:
            conn.close()


class TestProcessedEmailsTable:
    """Tests for the processed_emails table schema."""

    def test_insert_and_select(self, in_memory_db: sqlite3.Connection) -> None:
        """Should accept a valid row and return it by primary key."""
        in_memory_db.execute(
            """
            INSERT INTO processed_emails (
                message_id, rule_name, subject, from_address, output_path,
                actions_taken, status, created_at, updated_at, synced_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                "msg_001",
                "newsletters",
                "Test Subject",
                "sender@example.com",
                "data/gmail/export/newsletters/test.md",
                '["archive"]',
                "ok",
                "2026-03-23T00:00:00+00:00",
                "2026-03-23T00:00:00+00:00",
                "2026-03-23T00:00:00+00:00",
            ),
        )
        cursor = in_memory_db.execute("SELECT * FROM processed_emails WHERE message_id = ?;", ("msg_001",))
        row = cursor.fetchone()
        assert row is not None
        assert row["rule_name"] == "newsletters"

    def test_rule_name_index_exists(self, in_memory_db: sqlite3.Connection) -> None:
        """The rule_name index should exist for query performance."""
        cursor = in_memory_db.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_processed_emails_rule_name';"
        )
        assert cursor.fetchone() is not None


class TestDecisionCacheTable:
    """Tests for the decision_cache table schema."""

    def test_insert_and_select(self, in_memory_db: sqlite3.Connection) -> None:
        """Should accept a valid row and return it by primary key."""
        in_memory_db.execute(
            """
            INSERT INTO decision_cache (cache_key, decision, ttl_seconds, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?);
            """,
            ("key_001", '{"extracted": "content"}', 3600, "2026-03-23T00:00:00+00:00", "2026-03-23T00:00:00+00:00"),
        )
        cursor = in_memory_db.execute("SELECT * FROM decision_cache WHERE cache_key = ?;", ("key_001",))
        row = cursor.fetchone()
        assert row is not None
        assert row["ttl_seconds"] == 3600

    def test_created_at_index_exists(self, in_memory_db: sqlite3.Connection) -> None:
        """The created_at index should exist for expiry queries."""
        cursor = in_memory_db.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_decision_cache_created_at';"
        )
        assert cursor.fetchone() is not None

    def test_no_synced_at_column(self, in_memory_db: sqlite3.Connection) -> None:
        """The decision_cache table should NOT have a synced_at column (local-only)."""
        cursor = in_memory_db.execute("PRAGMA table_info(decision_cache);")
        column_names = [row["name"] for row in cursor.fetchall()]
        assert "synced_at" not in column_names


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
        return Path(__file__).parents[2] / "src" / "deep_thought" / "gmail" / "db" / "migrations"

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
