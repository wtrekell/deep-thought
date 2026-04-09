"""Tests for the web tool database layer: schema initialization and query functions.

All tests use in-memory SQLite (no disk writes). The in_memory_db fixture
from conftest.py is used throughout.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from deep_thought.web.db.queries import (
    delete_crawled_page,
    get_all_crawled_pages,
    get_crawled_page,
    get_crawled_pages_by_status,
    update_page_child_links,
    upsert_crawled_page,
)
from deep_thought.web.db.schema import get_schema_version, initialize_database

# ---------------------------------------------------------------------------
# Shared test data helper
# ---------------------------------------------------------------------------


def _page_data(
    url: str = "https://example.com/post-one",
    status: str = "success",
    title: str | None = "Post One",
    rule_name: str | None = None,
) -> dict[str, Any]:
    """Return a sample page_data dict matching all required crawled_pages columns."""
    return {
        "url": url,
        "rule_name": rule_name,
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
        expected_columns = {"url", "rule_name", "title", "status_code", "word_count", "output_path", "status"}
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
