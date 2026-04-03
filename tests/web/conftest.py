"""Shared pytest fixtures for the web tool test suite.

All database fixtures use in-memory SQLite so no disk I/O occurs.
"""

from __future__ import annotations

from pathlib import Path  # noqa: TC003
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import sqlite3
    from collections.abc import Generator

import pytest

from deep_thought.web.db.schema import initialize_database

# ---------------------------------------------------------------------------
# Database fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def in_memory_db() -> Generator[sqlite3.Connection, None, None]:
    """Return a fully initialized in-memory SQLite connection.

    The connection has WAL mode enabled, foreign keys enforced, and all
    migrations applied. Closes automatically after each test.
    """
    connection = initialize_database(":memory:")
    yield connection
    connection.close()


# ---------------------------------------------------------------------------
# Output directory fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def output_root(tmp_path: Path) -> Path:
    """Return a temporary output root directory for write_page tests."""
    return tmp_path / "output"
