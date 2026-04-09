"""Shared pytest fixtures for the Gmail Tool test suite.

All database fixtures use in-memory SQLite so no disk I/O occurs.
API client fixtures use MagicMock so no real network calls are made.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock

if TYPE_CHECKING:
    import sqlite3
    from collections.abc import Generator

import pytest

from deep_thought.gmail.db.schema import initialize_database

# Path to the fixtures directory, used by tests that load files from disk
FIXTURES_DIR = Path(__file__).parent / "fixtures"


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
# Mock message factory
# ---------------------------------------------------------------------------


def make_mock_message(
    message_id: str = "18d4a3b2c1e0f9a8",
    subject: str = "Test Email Subject",
    from_address: str = "Sender Name <sender@example.com>",
    to_address: str = "recipient@example.com",
    date: str = "Mon, 15 Mar 2026 09:00:00 +0000",
    body_text: str = "This is the email body.",
    body_html: str | None = None,
    labels: list[str] | None = None,
) -> dict[str, Any]:
    """Return a dict mimicking a Gmail API message response.

    Builds a message structure matching the Gmail API v1 'full' format
    with payload headers and body parts.

    Args:
        message_id: The Gmail message ID string.
        subject: The email subject line.
        from_address: The From header value.
        to_address: The To header value.
        date: The Date header value.
        body_text: Plain text body content.
        body_html: HTML body content, or None for plain-text-only messages.
        labels: List of Gmail label IDs (e.g., ["INBOX", "UNREAD"]).

    Returns:
        A dict matching the Gmail API message format.
    """
    import base64

    headers = [
        {"name": "Subject", "value": subject},
        {"name": "From", "value": from_address},
        {"name": "To", "value": to_address},
        {"name": "Date", "value": date},
    ]

    if body_html is not None:
        # Multipart message with text and HTML
        text_part = {
            "mimeType": "text/plain",
            "body": {"data": base64.urlsafe_b64encode(body_text.encode()).decode(), "size": len(body_text)},
        }
        html_part = {
            "mimeType": "text/html",
            "body": {"data": base64.urlsafe_b64encode(body_html.encode()).decode(), "size": len(body_html)},
        }
        payload = {
            "mimeType": "multipart/alternative",
            "headers": headers,
            "parts": [text_part, html_part],
            "body": {"size": 0},
        }
    else:
        # Plain text only
        payload = {
            "mimeType": "text/plain",
            "headers": headers,
            "body": {"data": base64.urlsafe_b64encode(body_text.encode()).decode(), "size": len(body_text)},
        }

    return {
        "id": message_id,
        "threadId": f"thread_{message_id}",
        "labelIds": labels if labels is not None else ["INBOX", "UNREAD"],
        "snippet": body_text[:100],
        "payload": payload,
        "sizeEstimate": len(body_text),
        "internalDate": "1742025600000",
    }


# ---------------------------------------------------------------------------
# Mock client fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_gmail_client() -> MagicMock:
    """Return a mock GmailClient with all methods returning empty defaults."""
    client = MagicMock()
    client.list_messages.return_value = []
    client.get_message.return_value = {}
    client.get_raw_message.return_value = b""
    client.send_message.return_value = {"id": "sent_123", "threadId": "thread_sent_123"}
    client.modify_message.return_value = {}
    client.delete_message.return_value = None
    client.trash_message.return_value = None
    client.get_label.return_value = "Label_123"
    client.get_or_create_label.return_value = "Label_123"
    return client


# ---------------------------------------------------------------------------
# Fixture-based versions of the factory
# ---------------------------------------------------------------------------


@pytest.fixture()
def sample_message() -> dict[str, Any]:
    """Return a Gmail API message dict with default realistic attributes."""
    return make_mock_message()


@pytest.fixture()
def sample_html_message() -> dict[str, Any]:
    """Return a Gmail API multipart message with HTML content."""
    return make_mock_message(
        message_id="18d4a3b2c1e0f9a9",
        subject="Newsletter: Weekly Digest",
        from_address="Newsletter <news@example.com>",
        body_text="This is the plain text version.",
        body_html="<html><body><h1>Weekly Digest</h1><p>Content here.</p></body></html>",
        labels=["INBOX", "UNREAD", "Label_newsletter"],
    )
