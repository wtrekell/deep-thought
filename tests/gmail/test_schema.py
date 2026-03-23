"""Tests for the Gmail Tool database schema initialization and migrations."""

from __future__ import annotations

import sqlite3

from deep_thought.gmail.db.schema import get_schema_version, initialize_database


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
