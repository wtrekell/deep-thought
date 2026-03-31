"""Tests for the Gmail Tool data models."""

from __future__ import annotations

from typing import Any

from deep_thought.gmail.models import (
    CollectResult,
    DecisionCacheLocal,
    ProcessedEmailLocal,
    SendResult,
    _extract_header,
    _parse_email_address,
    _slugify_subject,
)

from .conftest import make_mock_message

# ---------------------------------------------------------------------------
# Slug helpers
# ---------------------------------------------------------------------------


class TestSlugifySubject:
    """Tests for the _slugify_subject helper."""

    def test_basic_subject(self) -> None:
        """Should lowercase and replace spaces with hyphens."""
        assert _slugify_subject("Weekly Digest") == "weekly-digest"

    def test_special_characters(self) -> None:
        """Should replace non-alphanumeric characters with hyphens."""
        assert _slugify_subject("Re: Invoice #1234 — Paid!") == "re-invoice-1234-paid"

    def test_collapses_consecutive_hyphens(self) -> None:
        """Should collapse multiple consecutive hyphens into one."""
        assert _slugify_subject("a---b---c") == "a-b-c"

    def test_strips_leading_trailing_hyphens(self) -> None:
        """Should strip hyphens from start and end."""
        assert _slugify_subject("---hello---") == "hello"

    def test_truncates_to_max_length(self) -> None:
        """Should truncate long slugs to the max length."""
        long_subject = "a" * 100
        result = _slugify_subject(long_subject, max_length=80)
        assert len(result) == 80

    def test_empty_subject(self) -> None:
        """Should return empty string for empty subject."""
        assert _slugify_subject("") == ""

    def test_unicode_characters(self) -> None:
        """Should replace unicode characters with hyphens."""
        assert _slugify_subject("Café résumé") == "caf-r-sum"


# ---------------------------------------------------------------------------
# Header extraction
# ---------------------------------------------------------------------------


class TestExtractHeader:
    """Tests for the _extract_header helper."""

    def test_extracts_subject(self) -> None:
        """Should extract the Subject header value."""
        message = make_mock_message(subject="Test Subject")
        assert _extract_header(message, "Subject") == "Test Subject"

    def test_extracts_from(self) -> None:
        """Should extract the From header value."""
        message = make_mock_message(from_address="Sender <sender@example.com>")
        assert _extract_header(message, "From") == "Sender <sender@example.com>"

    def test_case_insensitive(self) -> None:
        """Should match headers regardless of case."""
        message = make_mock_message(subject="Test")
        assert _extract_header(message, "subject") == "Test"
        assert _extract_header(message, "SUBJECT") == "Test"

    def test_returns_none_for_missing(self) -> None:
        """Should return None when the header does not exist."""
        message = make_mock_message()
        assert _extract_header(message, "X-Custom-Header") is None

    def test_handles_empty_payload(self) -> None:
        """Should return None for a message with no payload."""
        message: dict[str, Any] = {"id": "test", "payload": {}}
        assert _extract_header(message, "Subject") is None


# ---------------------------------------------------------------------------
# Email address parsing
# ---------------------------------------------------------------------------


class TestParseEmailAddress:
    """Tests for the _parse_email_address helper."""

    def test_name_and_email_format(self) -> None:
        """Should extract email from 'Name <email>' format."""
        assert _parse_email_address("John Doe <john@example.com>") == "john@example.com"

    def test_bare_email(self) -> None:
        """Should return the email as-is when no angle brackets."""
        assert _parse_email_address("john@example.com") == "john@example.com"

    def test_quoted_name(self) -> None:
        """Should handle quoted display names."""
        assert _parse_email_address('"John Doe" <john@example.com>') == "john@example.com"

    def test_strips_whitespace(self) -> None:
        """Should strip surrounding whitespace from bare emails."""
        assert _parse_email_address("  john@example.com  ") == "john@example.com"


# ---------------------------------------------------------------------------
# ProcessedEmailLocal
# ---------------------------------------------------------------------------


class TestProcessedEmailLocal:
    """Tests for the ProcessedEmailLocal dataclass."""

    def test_from_message(self) -> None:
        """Should extract fields from a Gmail API message dict."""
        message = make_mock_message(
            message_id="msg_001",
            subject="Important Update",
            from_address="Sender <sender@example.com>",
        )
        email = ProcessedEmailLocal.from_message(
            message=message,
            rule_name="newsletters",
            output_path="data/gmail/export/newsletters/test.md",
            actions=["archive", "label:Processed"],
        )
        assert email.message_id == "msg_001"
        assert email.subject == "Important Update"
        # _parse_email_address extracts the bare email address from the From header
        assert email.from_address == "sender@example.com"
        assert email.rule_name == "newsletters"
        assert email.status == "ok"
        assert '"archive"' in email.actions_taken

    def test_from_message_missing_subject(self) -> None:
        """Should use '(no subject)' when Subject header is missing."""
        message: dict[str, Any] = {
            "id": "msg_002",
            "payload": {"headers": [{"name": "From", "value": "sender@example.com"}]},
        }
        email = ProcessedEmailLocal.from_message(
            message=message, rule_name="test", output_path="/tmp/test.md", actions=[]
        )
        assert email.subject == "(no subject)"

    def test_to_dict_has_all_keys(self) -> None:
        """to_dict should return a dict with all expected column names."""
        message = make_mock_message()
        email = ProcessedEmailLocal.from_message(
            message=message, rule_name="test", output_path="/tmp/test.md", actions=[]
        )
        result = email.to_dict()
        expected_keys = {
            "message_id",
            "rule_name",
            "subject",
            "from_address",
            "output_path",
            "actions_taken",
            "status",
            "created_at",
            "updated_at",
            "synced_at",
        }
        assert set(result.keys()) == expected_keys


# ---------------------------------------------------------------------------
# DecisionCacheLocal
# ---------------------------------------------------------------------------


class TestDecisionCacheLocal:
    """Tests for the DecisionCacheLocal dataclass."""

    def test_to_dict(self) -> None:
        """to_dict should return a dict with all expected column names."""
        entry = DecisionCacheLocal(
            cache_key="key_001",
            decision='{"extracted": "content"}',
            ttl_seconds=3600,
            created_at="2026-03-23T00:00:00+00:00",
            updated_at="2026-03-23T00:00:00+00:00",
        )
        result = entry.to_dict()
        expected_keys = {"cache_key", "decision", "ttl_seconds", "created_at", "updated_at"}
        assert set(result.keys()) == expected_keys
        assert result["ttl_seconds"] == 3600


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


class TestCollectResult:
    """Tests for the CollectResult dataclass."""

    def test_default_values(self) -> None:
        """Default CollectResult should have zero counts and empty collections."""
        result = CollectResult()
        assert result.processed == 0
        assert result.skipped == 0
        assert result.errors == 0
        assert result.actions_taken == {}
        assert result.error_messages == []


class TestSendResult:
    """Tests for the SendResult dataclass."""

    def test_default_values(self) -> None:
        """Default SendResult should have empty strings."""
        result = SendResult()
        assert result.message_id == ""
        assert result.thread_id == ""
