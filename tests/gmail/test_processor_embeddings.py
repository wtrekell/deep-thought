"""Tests verifying that embedding failures in processor.py do not abort collection.

These tests exercise the guarded embedding call inside ``_process_single_email``
to confirm that a failing embedding never prevents the DB upsert from occurring.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

if TYPE_CHECKING:
    import sqlite3
    from pathlib import Path

from deep_thought.gmail.config import RuleConfig
from deep_thought.gmail.processor import process_rule

from .conftest import make_mock_message


def _make_rule_config(name: str = "test_rule") -> RuleConfig:
    """Build a permissive RuleConfig for embedding integration tests."""
    return RuleConfig(
        name=name,
        query="from:test@example.com",
        ai_instructions=None,
        actions=["archive"],
        save_mode="individual",
    )


# ---------------------------------------------------------------------------
# Embedding failure resilience
# ---------------------------------------------------------------------------


class TestProcessorEmbeddingFailureDoesNotAbort:
    @pytest.mark.error_handling
    def test_processor_embedding_failure_does_not_abort(self, in_memory_db: sqlite3.Connection, tmp_path: Path) -> None:
        """A failing embedding must not prevent the collection run from completing.

        When ``write_embedding`` raises an exception, the processor should log
        a warning and continue. The DB upsert must still be called for the email.
        """
        message = make_mock_message(message_id="embed_fail_msg", subject="Test Email")
        mock_gmail_client = MagicMock()
        mock_gmail_client.list_messages.return_value = [{"id": "embed_fail_msg"}]
        mock_gmail_client.get_message.return_value = message

        mock_embedding_model = MagicMock()
        mock_qdrant_client = MagicMock()

        with patch("deep_thought.embeddings.write_embedding", side_effect=Exception("conn refused")):
            rule_config = _make_rule_config()
            collection_result = process_rule(
                gmail_client=mock_gmail_client,
                rule_config=rule_config,
                db_conn=in_memory_db,
                extractor=None,
                output_dir=tmp_path,
                dry_run=False,
                force=False,
                clean_newsletters=False,
                decision_cache_ttl=3600,
                global_email_count=0,
                max_emails_per_run=100,
                embedding_model=mock_embedding_model,
                embedding_qdrant_client=mock_qdrant_client,
            )

        # The collection must have completed — the email must be counted as processed, not errored
        assert collection_result.processed == 1
        assert collection_result.errors == 0

    def test_processor_without_embedding_model_skips_embedding(
        self, in_memory_db: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """When no embedding model is provided, write_embedding must never be called."""
        message = make_mock_message(message_id="no_embed_msg", subject="Test Email")
        mock_gmail_client = MagicMock()
        mock_gmail_client.list_messages.return_value = [{"id": "no_embed_msg"}]
        mock_gmail_client.get_message.return_value = message

        with patch("deep_thought.embeddings.write_embedding") as mock_shared_write:
            rule_config = _make_rule_config()
            process_rule(
                gmail_client=mock_gmail_client,
                rule_config=rule_config,
                db_conn=in_memory_db,
                extractor=None,
                output_dir=tmp_path,
                dry_run=False,
                force=False,
                clean_newsletters=False,
                decision_cache_ttl=3600,
                global_email_count=0,
                max_emails_per_run=100,
                embedding_model=None,
                embedding_qdrant_client=None,
            )

        mock_shared_write.assert_not_called()
