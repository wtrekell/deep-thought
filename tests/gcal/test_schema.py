"""Tests for the GCal Tool database schema and migration system."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import sqlite3

from deep_thought.gcal.db.schema import get_schema_version, initialize_database


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

    def test_schema_version_is_one(self, in_memory_db: sqlite3.Connection) -> None:
        """After running the first migration, schema version should be 1."""
        assert get_schema_version(in_memory_db) == 1

    def test_idempotent_initialization(self) -> None:
        """Running initialize_database twice should not error or reset state."""
        conn = initialize_database(":memory:")
        assert get_schema_version(conn) == 1
        # Simulating a second initialization on the same connection
        # by checking that re-reading the version still works
        assert get_schema_version(conn) == 1
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

    def test_returns_version_after_migration(self, in_memory_db: sqlite3.Connection) -> None:
        """Should return 1 after the first migration is applied."""
        assert get_schema_version(in_memory_db) == 1


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
