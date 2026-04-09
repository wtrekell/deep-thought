import contextlib
import sqlite3
from pathlib import Path

import pytest

from deep_thought.todoist.db.schema import (
    _split_sql_statements,
    get_data_dir,
    get_database_path,
    get_schema_version,
    run_migrations,
)


class TestGetDataDir:
    def test_returns_default_path_when_env_not_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DEEP_THOUGHT_DATA_DIR", raising=False)
        result = get_data_dir()
        assert result.parts[-2:] == ("data", "todoist")

    def test_returns_env_override_with_todoist_subdirectory(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """DEEP_THOUGHT_DATA_DIR points to the shared data root; get_data_dir must append 'todoist/'."""
        monkeypatch.setenv("DEEP_THOUGHT_DATA_DIR", str(tmp_path))
        result = get_data_dir()
        assert result == tmp_path / "todoist"

    def test_database_path_uses_env_override_with_todoist_subdirectory(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """DB file must live inside the todoist/ subdirectory of the env-var-specified root."""
        monkeypatch.setenv("DEEP_THOUGHT_DATA_DIR", str(tmp_path))
        db_path = get_database_path()
        assert db_path == tmp_path / "todoist" / "todoist.db"


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
        return Path(__file__).parents[2] / "src" / "deep_thought" / "todoist" / "db" / "migrations"

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
