"""Tests for deep_thought.gdrive.db.schema — database initialization."""

from __future__ import annotations

import sqlite3

import pytest

from deep_thought.gdrive.db.schema import init_db


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
