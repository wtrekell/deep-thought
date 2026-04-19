"""Tests for deep_thought.gmail.embeddings.

All tests mock ``deep_thought.embeddings.write_embedding`` at the module
boundary so no real MLX model or Qdrant connection is required.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock, patch

from deep_thought.gmail.models import ProcessedEmailLocal

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_processed_email() -> ProcessedEmailLocal:
    """Return a ProcessedEmailLocal with realistic test values."""
    now_iso = datetime.now(tz=UTC).isoformat()
    return ProcessedEmailLocal(
        message_id="msg_abc123",
        rule_name="test_rule",
        subject="Weekly Newsletter Digest",
        from_address="sender@example.com",
        output_path="/data/gmail/export/test_rule/260409-weekly-newsletter-digest.md",
        actions_taken='["archive"]',
        status="ok",
        created_at=now_iso,
        updated_at=now_iso,
        synced_at=now_iso,
    )


def _call_write_embedding(
    email: ProcessedEmailLocal,
    content: str = "Subject: Weekly Newsletter Digest\n\nSome body text.",
) -> Any:
    """Invoke the module under test with a mock model and client, returning the mock."""
    mock_model = MagicMock()
    mock_client = MagicMock()

    with patch("deep_thought.embeddings.write_embedding") as mock_shared_write:
        from deep_thought.gmail.embeddings import write_embedding

        write_embedding(content=content, email=email, model=mock_model, qdrant_client=mock_client)
        return mock_shared_write


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestWriteEmbeddingCallsSharedFunction:
    def test_write_embedding_calls_shared_write_embedding(self) -> None:
        """The gmail write_embedding must call the shared write_embedding exactly once."""
        email = _make_processed_email()
        mock_shared = _call_write_embedding(email)
        mock_shared.assert_called_once()

    def test_write_embedding_payload_source_tool(self) -> None:
        """The payload passed to the shared function must have source_tool='gmail'."""
        email = _make_processed_email()
        mock_shared = _call_write_embedding(email)
        call_kwargs = mock_shared.call_args.kwargs
        assert call_kwargs["payload"]["source_tool"] == "gmail"

    def test_write_embedding_payload_required_fields(self) -> None:
        """The payload must contain the four fields required by every tool."""
        email = _make_processed_email()
        mock_shared = _call_write_embedding(email)
        payload = mock_shared.call_args.kwargs["payload"]
        assert "source_tool" in payload
        assert "source_type" in payload
        assert "rule_name" in payload
        assert "collected_date" in payload

    def test_write_embedding_output_path_passed(self) -> None:
        """The output_path kwarg must match the email's output_path field."""
        email = _make_processed_email()
        mock_shared = _call_write_embedding(email)
        call_kwargs = mock_shared.call_args.kwargs
        assert call_kwargs["output_path"] == email.output_path

    def test_write_embedding_canonical_id_is_message_id(self) -> None:
        """The canonical_id kwarg must be the Gmail message-id — stable across file moves."""
        email = _make_processed_email()
        mock_shared = _call_write_embedding(email)
        call_kwargs = mock_shared.call_args.kwargs
        assert call_kwargs["canonical_id"] == email.message_id

    def test_source_type_is_email(self) -> None:
        """Gmail always uses source_type='email'."""
        email = _make_processed_email()
        mock_shared = _call_write_embedding(email)
        payload = mock_shared.call_args.kwargs["payload"]
        assert payload["source_type"] == "email"

    def test_rule_name_in_payload(self) -> None:
        """The payload's rule_name must match the email's rule_name."""
        email = _make_processed_email()
        mock_shared = _call_write_embedding(email)
        payload = mock_shared.call_args.kwargs["payload"]
        assert payload["rule_name"] == "test_rule"

    def test_subject_in_payload_as_title(self) -> None:
        """The payload must carry the email subject as the title field."""
        email = _make_processed_email()
        mock_shared = _call_write_embedding(email)
        payload = mock_shared.call_args.kwargs["payload"]
        assert payload["title"] == "Weekly Newsletter Digest"

    def test_message_id_in_payload(self) -> None:
        """The payload must include the Gmail message ID."""
        email = _make_processed_email()
        mock_shared = _call_write_embedding(email)
        payload = mock_shared.call_args.kwargs["payload"]
        assert payload["message_id"] == "msg_abc123"

    def test_from_address_in_payload(self) -> None:
        """The payload must include the sender address."""
        email = _make_processed_email()
        mock_shared = _call_write_embedding(email)
        payload = mock_shared.call_args.kwargs["payload"]
        assert payload["from_address"] == "sender@example.com"

    def test_word_count_in_payload(self) -> None:
        """The payload must include a word_count derived from the content."""
        email = _make_processed_email()
        content = "Subject: Test\n\nOne two three four five"
        mock_shared = _call_write_embedding(email, content=content)
        payload = mock_shared.call_args.kwargs["payload"]
        assert payload["word_count"] == 7  # "Subject:" "Test" "One" "two" "three" "four" "five"

    def test_content_passed_through(self) -> None:
        """The content string must be forwarded unchanged to the shared function."""
        email = _make_processed_email()
        expected_content = "Subject: Weekly Newsletter Digest\n\nUnique body text for assertion."
        mock_shared = _call_write_embedding(email, content=expected_content)
        assert mock_shared.call_args.kwargs["content"] == expected_content
