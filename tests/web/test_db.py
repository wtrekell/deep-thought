"""Tests for the web tool database layer: schema initialization and query functions.

All tests use in-memory SQLite (no disk writes). The in_memory_db fixture
from conftest.py is used throughout.
"""

from __future__ import annotations

import contextlib
import sqlite3
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from deep_thought.web.db.queries import (
    delete_crawled_page,
    get_all_crawled_pages,
    get_crawled_page,
    get_crawled_pages_by_status,
    update_page_child_links,
    upsert_crawled_page,
)
from deep_thought.web.db.schema import (
    _split_sql_statements,
    get_schema_version,
    initialize_database,
    run_migrations,
)

# ---------------------------------------------------------------------------
# Shared test data helper
# ---------------------------------------------------------------------------


def _page_data(
    url: str = "https://example.com/post-one",
    status: str = "success",
    title: str | None = "Post One",
) -> dict[str, Any]:
    """Return a sample page_data dict matching all required crawled_pages columns."""
    return {
        "url": url,
        "title": title,
        "status_code": 200,
        "word_count": 150,
        "output_path": "data/web/export/example.com/post-one.md",
        "status": status,
        "created_at": "2026-03-22T00:00:00+00:00",
        "updated_at": "2026-03-22T00:00:00+00:00",
        "synced_at": "2026-03-22T00:00:00+00:00",
    }


# ---------------------------------------------------------------------------
# TestInitializeDatabase
# ---------------------------------------------------------------------------


class TestInitializeDatabase:
    def test_creates_crawled_pages_table(self, in_memory_db: Any) -> None:
        """initialize_database must create the crawled_pages table."""
        cursor = in_memory_db.execute("SELECT name FROM sqlite_master WHERE type='table';")
        table_names = {row["name"] for row in cursor.fetchall()}
        assert "crawled_pages" in table_names

    def test_creates_web_schema_version_table(self, in_memory_db: Any) -> None:
        """initialize_database must create the web_schema_version table."""
        cursor = in_memory_db.execute("SELECT name FROM sqlite_master WHERE type='table';")
        table_names = {row["name"] for row in cursor.fetchall()}
        assert "web_schema_version" in table_names

    def test_schema_version_is_nonzero_after_init(self, in_memory_db: Any) -> None:
        """After initialization, the schema version must be at least 1."""
        version = get_schema_version(in_memory_db)
        assert version >= 1

    def test_schema_version_returns_zero_on_empty_connection(self) -> None:
        """get_schema_version on a raw connection with no tables must return 0."""
        raw_conn = sqlite3.connect(":memory:")
        raw_conn.row_factory = sqlite3.Row
        version = get_schema_version(raw_conn)
        raw_conn.close()
        assert version == 0

    def test_running_init_twice_is_idempotent(self) -> None:
        """Calling initialize_database twice on the same connection must not fail or duplicate tables."""
        conn = initialize_database(":memory:")
        # Run migrations a second time against the already-initialized connection.
        # All migrations should be skipped (already applied) and the schema version must be unchanged.
        version_after_first_init = get_schema_version(conn)
        import pathlib

        from deep_thought.web.db.schema import run_migrations

        migrations_dir = pathlib.Path(__file__).parents[2] / "src" / "deep_thought" / "web" / "db" / "migrations"
        run_migrations(conn, migrations_dir)
        version_after_second_run = get_schema_version(conn)
        assert version_after_first_init == version_after_second_run
        conn.close()

    def test_crawled_pages_has_expected_columns(self, in_memory_db: Any) -> None:
        """The crawled_pages table must contain all required columns."""
        cursor = in_memory_db.execute("PRAGMA table_info(crawled_pages);")
        column_names = {row["name"] for row in cursor.fetchall()}
        expected_columns = {"url", "title", "status_code", "word_count", "output_path", "status"}
        assert expected_columns.issubset(column_names)


# ---------------------------------------------------------------------------
# TestUpsertCrawledPage
# ---------------------------------------------------------------------------


class TestUpsertCrawledPage:
    def test_inserts_a_new_row(self, in_memory_db: Any) -> None:
        """upsert_crawled_page must insert a row that can be retrieved."""
        upsert_crawled_page(in_memory_db, _page_data())
        in_memory_db.commit()
        result = get_crawled_page(in_memory_db, "https://example.com/post-one")
        assert result is not None

    def test_row_has_correct_url(self, in_memory_db: Any) -> None:
        """The inserted row must have the URL from page_data."""
        page_url = "https://example.com/my-article"
        upsert_crawled_page(in_memory_db, _page_data(url=page_url))
        in_memory_db.commit()
        result = get_crawled_page(in_memory_db, page_url)
        assert result is not None
        assert result["url"] == page_url

    def test_replaces_existing_row_on_conflict(self, in_memory_db: Any) -> None:
        """A second upsert with the same URL must replace the existing row."""
        page_url = "https://example.com/post-one"
        upsert_crawled_page(in_memory_db, _page_data(url=page_url, title="Original Title"))
        in_memory_db.commit()
        upsert_crawled_page(in_memory_db, _page_data(url=page_url, title="Updated Title"))
        in_memory_db.commit()
        result = get_crawled_page(in_memory_db, page_url)
        assert result is not None
        assert result["title"] == "Updated Title"

    def test_synced_at_is_set_automatically(self, in_memory_db: Any) -> None:
        """upsert_crawled_page must set synced_at to the current UTC time."""
        upsert_crawled_page(in_memory_db, _page_data())
        in_memory_db.commit()
        result = get_crawled_page(in_memory_db, "https://example.com/post-one")
        assert result is not None
        assert result["synced_at"] is not None

    def test_null_title_is_stored_correctly(self, in_memory_db: Any) -> None:
        """A page with a None title must be stored and retrieved as None."""
        page_url = "https://example.com/notitle"
        upsert_crawled_page(in_memory_db, _page_data(url=page_url, title=None))
        in_memory_db.commit()
        result = get_crawled_page(in_memory_db, page_url)
        assert result is not None
        assert result["title"] is None


# ---------------------------------------------------------------------------
# TestGetCrawledPage
# ---------------------------------------------------------------------------


class TestGetCrawledPage:
    def test_returns_dict_for_existing_url(self, in_memory_db: Any) -> None:
        """get_crawled_page must return a dict for a URL that has been inserted."""
        upsert_crawled_page(in_memory_db, _page_data())
        in_memory_db.commit()
        result = get_crawled_page(in_memory_db, "https://example.com/post-one")
        assert isinstance(result, dict)

    def test_returns_none_for_nonexistent_url(self, in_memory_db: Any) -> None:
        """get_crawled_page must return None when the URL has not been crawled."""
        result = get_crawled_page(in_memory_db, "https://example.com/does-not-exist")
        assert result is None

    def test_returned_dict_contains_status_field(self, in_memory_db: Any) -> None:
        """The returned dict must contain the 'status' field."""
        upsert_crawled_page(in_memory_db, _page_data(status="success"))
        in_memory_db.commit()
        result = get_crawled_page(in_memory_db, "https://example.com/post-one")
        assert result is not None
        assert result["status"] == "success"


# ---------------------------------------------------------------------------
# TestGetCrawledPagesByStatus
# ---------------------------------------------------------------------------


class TestGetCrawledPagesByStatus:
    def test_filters_by_status_success(self, in_memory_db: Any) -> None:
        """get_crawled_pages_by_status must return only rows with the given status."""
        upsert_crawled_page(in_memory_db, _page_data(url="https://example.com/ok", status="success"))
        upsert_crawled_page(in_memory_db, _page_data(url="https://example.com/fail", status="error"))
        in_memory_db.commit()
        results = get_crawled_pages_by_status(in_memory_db, "success")
        assert len(results) == 1
        assert results[0]["url"] == "https://example.com/ok"

    def test_filters_by_status_error(self, in_memory_db: Any) -> None:
        """get_crawled_pages_by_status must return rows with 'error' status."""
        upsert_crawled_page(in_memory_db, _page_data(url="https://example.com/page1", status="success"))
        upsert_crawled_page(in_memory_db, _page_data(url="https://example.com/page2", status="error"))
        in_memory_db.commit()
        results = get_crawled_pages_by_status(in_memory_db, "error")
        assert len(results) == 1
        assert results[0]["status"] == "error"

    def test_returns_empty_list_when_no_match(self, in_memory_db: Any) -> None:
        """get_crawled_pages_by_status must return an empty list when no rows match."""
        upsert_crawled_page(in_memory_db, _page_data(status="success"))
        in_memory_db.commit()
        results = get_crawled_pages_by_status(in_memory_db, "skipped")
        assert results == []

    def test_returns_multiple_matching_rows(self, in_memory_db: Any) -> None:
        """Multiple rows with the same status must all be returned."""
        upsert_crawled_page(in_memory_db, _page_data(url="https://example.com/page1", status="success"))
        upsert_crawled_page(in_memory_db, _page_data(url="https://example.com/page2", status="success"))
        in_memory_db.commit()
        results = get_crawled_pages_by_status(in_memory_db, "success")
        assert len(results) == 2


# ---------------------------------------------------------------------------
# TestGetAllCrawledPages
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# TestDeleteCrawledPage
# ---------------------------------------------------------------------------


class TestDeleteCrawledPage:
    def test_deleted_page_is_no_longer_retrievable(self, in_memory_db: Any) -> None:
        """After delete_crawled_page, get_crawled_page must return None for that URL."""
        page_url = "https://example.com/to-delete"
        upsert_crawled_page(in_memory_db, _page_data(url=page_url))
        in_memory_db.commit()

        delete_crawled_page(in_memory_db, page_url)
        in_memory_db.commit()

        result = get_crawled_page(in_memory_db, page_url)
        assert result is None

    def test_delete_leaves_other_pages_intact(self, in_memory_db: Any) -> None:
        """delete_crawled_page must not remove rows for other URLs."""
        url_to_delete = "https://example.com/delete-me"
        url_to_keep = "https://example.com/keep-me"
        upsert_crawled_page(in_memory_db, _page_data(url=url_to_delete))
        upsert_crawled_page(in_memory_db, _page_data(url=url_to_keep))
        in_memory_db.commit()

        delete_crawled_page(in_memory_db, url_to_delete)
        in_memory_db.commit()

        assert get_crawled_page(in_memory_db, url_to_keep) is not None

    def test_delete_nonexistent_url_does_not_raise(self, in_memory_db: Any) -> None:
        """Calling delete_crawled_page for a URL that does not exist must not raise."""
        delete_crawled_page(in_memory_db, "https://example.com/never-existed")
        in_memory_db.commit()


# ---------------------------------------------------------------------------
# TestUpdatePageChildLinks
# ---------------------------------------------------------------------------


class TestUpdatePageChildLinks:
    def test_child_links_stored_and_retrieved(self, in_memory_db: Any) -> None:
        """update_page_child_links must persist the JSON string so it can be read back."""
        import json

        page_url = "https://example.com/parent"
        upsert_crawled_page(in_memory_db, _page_data(url=page_url))
        in_memory_db.commit()

        child_urls = ["https://example.com/child-a", "https://example.com/child-b"]
        child_links_json = json.dumps(child_urls)
        update_page_child_links(in_memory_db, page_url, child_links_json)
        in_memory_db.commit()

        result = get_crawled_page(in_memory_db, page_url)
        assert result is not None
        assert result["child_links"] == child_links_json

    def test_child_links_round_trip_as_list(self, in_memory_db: Any) -> None:
        """The stored child_links JSON must deserialise back to the original list."""
        import json

        page_url = "https://example.com/round-trip"
        upsert_crawled_page(in_memory_db, _page_data(url=page_url))
        in_memory_db.commit()

        original_child_urls = ["https://example.com/alpha", "https://example.com/beta"]
        update_page_child_links(in_memory_db, page_url, json.dumps(original_child_urls))
        in_memory_db.commit()

        result = get_crawled_page(in_memory_db, page_url)
        assert result is not None
        retrieved_urls = json.loads(result["child_links"])
        assert retrieved_urls == original_child_urls

    def test_empty_child_links_list_stored_correctly(self, in_memory_db: Any) -> None:
        """An empty child links list must be stored as the JSON string '[]'."""
        import json

        page_url = "https://example.com/leaf"
        upsert_crawled_page(in_memory_db, _page_data(url=page_url))
        in_memory_db.commit()

        update_page_child_links(in_memory_db, page_url, json.dumps([]))
        in_memory_db.commit()

        result = get_crawled_page(in_memory_db, page_url)
        assert result is not None
        assert json.loads(result["child_links"]) == []


# ---------------------------------------------------------------------------
# TestGetAllCrawledPages
# ---------------------------------------------------------------------------


class TestGetAllCrawledPages:
    def test_returns_all_rows(self, in_memory_db: Any) -> None:
        """get_all_crawled_pages must return all inserted rows."""
        upsert_crawled_page(in_memory_db, _page_data(url="https://example.com/page1", status="success"))
        upsert_crawled_page(in_memory_db, _page_data(url="https://example.com/page2", status="error"))
        upsert_crawled_page(in_memory_db, _page_data(url="https://example.com/page3", status="skipped"))
        in_memory_db.commit()
        results = get_all_crawled_pages(in_memory_db)
        assert len(results) == 3

    def test_returns_empty_list_for_empty_table(self, in_memory_db: Any) -> None:
        """get_all_crawled_pages must return an empty list when no pages exist."""
        results = get_all_crawled_pages(in_memory_db)
        assert results == []

    def test_results_are_ordered_by_url(self, in_memory_db: Any) -> None:
        """get_all_crawled_pages must return rows ordered alphabetically by URL."""
        upsert_crawled_page(in_memory_db, _page_data(url="https://example.com/z-page"))
        upsert_crawled_page(in_memory_db, _page_data(url="https://example.com/a-page"))
        in_memory_db.commit()
        results = get_all_crawled_pages(in_memory_db)
        assert results[0]["url"] == "https://example.com/a-page"
        assert results[1]["url"] == "https://example.com/z-page"


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

    def test_successful_migration_advances_schema_version(self, tmp_path: Path) -> None:
        """A valid migration file must be applied and the version counter must advance."""
        import pathlib

        migrations_dir = tmp_path / "migrations"
        migrations_dir.mkdir()
        migration_file = migrations_dir / "001_create_test_table.sql"
        migration_file.write_text("CREATE TABLE test_table (id INTEGER PRIMARY KEY);", encoding="utf-8")

        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row

        # First we need web_schema_version to exist so get_schema_version works.
        # We do that by running the real migrations first, then layer on ours.
        real_migrations_dir = pathlib.Path(__file__).parents[2] / "src" / "deep_thought" / "web" / "db" / "migrations"
        run_migrations(connection, real_migrations_dir)
        version_before = get_schema_version(connection)

        # Now add a fake migration numbered beyond current version.
        next_version = version_before + 1
        custom_migration_file = migrations_dir / f"{next_version:03d}_create_test_table.sql"
        custom_migration_file.write_text("CREATE TABLE test_table (id INTEGER PRIMARY KEY);", encoding="utf-8")

        # Merge the real migrations dir contents into tmp so run_migrations sees both.
        merged_dir = tmp_path / "merged_migrations"
        merged_dir.mkdir()
        for real_sql_file in sorted(real_migrations_dir.glob("*.sql")):
            (merged_dir / real_sql_file.name).write_text(real_sql_file.read_text(encoding="utf-8"), encoding="utf-8")
        (merged_dir / custom_migration_file.name).write_text(
            "CREATE TABLE test_table (id INTEGER PRIMARY KEY);", encoding="utf-8"
        )

        connection2 = sqlite3.connect(":memory:")
        connection2.row_factory = sqlite3.Row
        run_migrations(connection2, merged_dir)

        assert get_schema_version(connection2) == next_version
        cursor = connection2.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='test_table';")
        assert cursor.fetchone() is not None
        connection.close()
        connection2.close()

    def test_migration_with_bad_sql_does_not_advance_schema_version(self, tmp_path: Path) -> None:
        """A migration containing invalid SQL must leave the schema version unchanged."""
        import pathlib

        real_migrations_dir = pathlib.Path(__file__).parents[2] / "src" / "deep_thought" / "web" / "db" / "migrations"

        # Find the current highest migration number from real files.
        real_migration_numbers = []
        for real_sql_file in real_migrations_dir.glob("*.sql"):
            prefix = real_sql_file.stem.split("_")[0]
            with contextlib.suppress(ValueError):
                real_migration_numbers.append(int(prefix))
        highest_real_version = max(real_migration_numbers)

        # Build a merged directory with real migrations + one bad migration.
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

        real_migrations_dir = pathlib.Path(__file__).parents[2] / "src" / "deep_thought" / "web" / "db" / "migrations"
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

        # Migration that first creates a table (DDL), then contains bad SQL.
        # With executescript() the CREATE TABLE would be committed before the
        # error; with conn.execute() it must roll back together.
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
