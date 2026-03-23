"""Tests for the Gmail Tool post-fetch filters."""

from __future__ import annotations

from typing import TYPE_CHECKING

from deep_thought.gmail.db.queries import upsert_processed_email

if TYPE_CHECKING:
    import sqlite3
from deep_thought.gmail.filters import is_already_processed, is_within_max_emails


class TestIsAlreadyProcessed:
    """Tests for is_already_processed."""

    def test_returns_false_for_new_message(self, in_memory_db: sqlite3.Connection) -> None:
        """Should return False when the message has not been processed."""
        assert is_already_processed("new_msg", in_memory_db) is False

    def test_returns_true_for_processed_message(self, in_memory_db: sqlite3.Connection) -> None:
        """Should return True when the message exists with status 'ok'."""
        upsert_processed_email(
            in_memory_db,
            {
                "message_id": "msg_001",
                "rule_name": "test",
                "subject": "Test",
                "from_address": "sender@example.com",
                "output_path": "/tmp/test.md",
                "actions_taken": "[]",
                "status": "ok",
                "created_at": "2026-03-23T00:00:00+00:00",
            },
        )
        assert is_already_processed("msg_001", in_memory_db) is True

    def test_returns_false_for_errored_message(self, in_memory_db: sqlite3.Connection) -> None:
        """Should return False when the message exists but has status 'error'."""
        upsert_processed_email(
            in_memory_db,
            {
                "message_id": "msg_err",
                "rule_name": "test",
                "subject": "Test",
                "from_address": "sender@example.com",
                "output_path": "/tmp/test.md",
                "actions_taken": "[]",
                "status": "error",
                "created_at": "2026-03-23T00:00:00+00:00",
            },
        )
        assert is_already_processed("msg_err", in_memory_db) is False


class TestIsWithinMaxEmails:
    """Tests for is_within_max_emails."""

    def test_under_limit(self) -> None:
        """Should return True when current count is below the max."""
        assert is_within_max_emails(5, 10) is True

    def test_at_limit(self) -> None:
        """Should return False when current count equals the max."""
        assert is_within_max_emails(10, 10) is False

    def test_over_limit(self) -> None:
        """Should return False when current count exceeds the max."""
        assert is_within_max_emails(11, 10) is False

    def test_zero_count(self) -> None:
        """Should return True when no emails have been processed yet."""
        assert is_within_max_emails(0, 100) is True
