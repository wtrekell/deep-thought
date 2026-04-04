"""Tests verifying that embedding failures in processor.py do not abort collection.

These tests exercise the guarded embedding call inside ``_process_single_post``
to confirm that a failing embedding never prevents the DB upsert from occurring.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

if TYPE_CHECKING:
    import sqlite3
    from pathlib import Path

from deep_thought.reddit.config import RuleConfig
from deep_thought.reddit.processor import process_rule
from tests.reddit.conftest import make_mock_submission


def _make_rule_config(name: str = "test_rule", subreddit: str = "python") -> RuleConfig:
    """Build a permissive RuleConfig for embedding integration tests."""
    return RuleConfig(
        name=name,
        subreddit=subreddit,
        sort="top",
        time_filter="week",
        limit=10,
        min_score=0,
        min_comments=0,
        max_age_days=30,
        include_keywords=[],
        exclude_keywords=[],
        include_flair=[],
        exclude_flair=[],
        search_comments=False,
        max_comment_depth=2,
        max_comments=50,
        include_images=False,
        exclude_stickied=False,
        exclude_locked=False,
        replace_more_limit=0,
    )


# ---------------------------------------------------------------------------
# Embedding failure resilience
# ---------------------------------------------------------------------------


class TestProcessorEmbeddingFailureDoesNotAbort:
    @pytest.mark.error_handling
    def test_processor_embedding_failure_does_not_abort(self, in_memory_db: sqlite3.Connection, tmp_path: Path) -> None:
        """A failing embedding must not prevent the collection run from completing.

        When ``write_embedding`` raises an exception, the processor should log
        a warning and continue. The DB upsert must still be called for the post.
        """
        submission = make_mock_submission(score=200, num_comments=15)
        mock_reddit_client = MagicMock()
        mock_reddit_client.get_submissions.return_value = [submission]
        mock_reddit_client.get_comments.return_value = []

        mock_embedding_model = MagicMock()
        mock_qdrant_client = MagicMock()

        with (
            patch("deep_thought.reddit.processor.apply_rule_filters", return_value=True),
            patch("deep_thought.reddit.db.queries.get_collected_post", return_value=None),
            patch("deep_thought.reddit.processor.generate_markdown", return_value="# Test content"),
            patch("deep_thought.reddit.processor.write_post_file") as mock_write_file,
            patch("deep_thought.reddit.db.queries.upsert_collected_post") as mock_upsert,
            patch("deep_thought.embeddings.write_embedding", side_effect=Exception("conn refused")),
        ):
            # write_post_file must return a real path so the embedding code can attempt a read
            written_path = tmp_path / "test_rule" / "260402-abc123_test-post.md"
            written_path.parent.mkdir(parents=True, exist_ok=True)
            written_path.write_text("---\ntitle: Test\n---\n\n# Test content", encoding="utf-8")
            mock_write_file.return_value = written_path

            rule_config = _make_rule_config()
            collection_result = process_rule(
                reddit_client=mock_reddit_client,
                rule_config=rule_config,
                db_conn=in_memory_db,
                output_dir=tmp_path,
                dry_run=False,
                force=False,
                global_post_count=0,
                max_posts_per_run=100,
                embedding_model=mock_embedding_model,
                embedding_qdrant_client=mock_qdrant_client,
            )

        # The collection must have completed and the DB upsert must have been called
        assert mock_upsert.called, "DB upsert must be called even when embedding fails"
        # The post must be counted as collected, not errored
        assert collection_result.posts_collected == 1
        assert collection_result.posts_errored == 0

    def test_processor_without_embedding_model_skips_embedding(
        self, in_memory_db: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """When no embedding model is provided, write_embedding must never be called."""
        submission = make_mock_submission(score=200, num_comments=15)
        mock_reddit_client = MagicMock()
        mock_reddit_client.get_submissions.return_value = [submission]
        mock_reddit_client.get_comments.return_value = []

        with (
            patch("deep_thought.reddit.processor.apply_rule_filters", return_value=True),
            patch("deep_thought.reddit.db.queries.get_collected_post", return_value=None),
            patch("deep_thought.reddit.processor.generate_markdown", return_value="# content"),
            patch("deep_thought.reddit.processor.write_post_file") as mock_write_file,
            patch("deep_thought.reddit.db.queries.upsert_collected_post"),
            patch("deep_thought.embeddings.write_embedding") as mock_shared_write,
        ):
            written_path = tmp_path / "test_rule" / "260402-abc123_test.md"
            written_path.parent.mkdir(parents=True, exist_ok=True)
            written_path.write_text("# content", encoding="utf-8")
            mock_write_file.return_value = written_path

            rule_config = _make_rule_config()
            process_rule(
                reddit_client=mock_reddit_client,
                rule_config=rule_config,
                db_conn=in_memory_db,
                output_dir=tmp_path,
                dry_run=False,
                force=False,
                global_post_count=0,
                max_posts_per_run=100,
                embedding_model=None,
                embedding_qdrant_client=None,
            )

        mock_shared_write.assert_not_called()
