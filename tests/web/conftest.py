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
# HTML fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def sample_html() -> str:
    """Return a simple HTML string with title, links, and image tags."""
    return """<!DOCTYPE html>
<html>
<head><title>Sample Page</title></head>
<body>
<h1>Main Heading</h1>
<p>Some paragraph text here.</p>
<a href="https://example.com/page-one">Internal Link</a>
<a href="https://other.com/page">External Link</a>
<img src="/images/photo.jpg" alt="A photo">
</body>
</html>"""


@pytest.fixture()
def blog_index_html() -> str:
    """Return HTML for a blog index page with 3 article links."""
    return (Path(__file__).parent / "fixtures" / "blog_index.html").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Output directory fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def output_root(tmp_path: Path) -> Path:
    """Return a temporary output root directory for write_page tests."""
    return tmp_path / "output"
