"""Tests for deep_thought.reddit.embeddings.

All tests mock ``deep_thought.embeddings.write_embedding`` at the module
boundary so no real MLX model or Qdrant connection is required.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock, patch

from deep_thought.reddit.models import CollectedPostLocal

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_collected_post(flair: str | None = "Discussion") -> CollectedPostLocal:
    """Return a CollectedPostLocal with realistic test values."""
    now_iso = datetime.now(tz=UTC).isoformat()
    return CollectedPostLocal(
        state_key="abc123:python:test_rule",
        post_id="abc123",
        subreddit="python",
        rule_name="test_rule",
        title="A Great Python Post",
        author="test_user",
        score=500,
        comment_count=42,
        url="https://www.reddit.com/r/python/comments/abc123/",
        is_video=0,
        flair=flair,
        word_count=350,
        output_path="/data/reddit/test_rule/260402-abc123_a-great-python-post.md",
        status="ok",
        created_at=now_iso,
        updated_at=now_iso,
        synced_at=now_iso,
    )


def _call_write_embedding(
    post: CollectedPostLocal,
    content: str = "Title: A Great Python Post\n\nSome body text.",
) -> Any:
    """Invoke the module under test with a mock model and client, returning the mock."""
    mock_model = MagicMock()
    mock_client = MagicMock()

    with patch("deep_thought.embeddings.write_embedding") as mock_shared_write:
        from deep_thought.reddit.embeddings import write_embedding

        write_embedding(content=content, post=post, model=mock_model, qdrant_client=mock_client)
        return mock_shared_write


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestWriteEmbeddingCallsSharedFunction:
    def test_write_embedding_calls_shared_write_embedding(self) -> None:
        """The reddit write_embedding must call the shared write_embedding exactly once."""
        post = _make_collected_post()
        mock_shared = _call_write_embedding(post)
        mock_shared.assert_called_once()

    def test_write_embedding_payload_source_tool(self) -> None:
        """The payload passed to the shared function must have source_tool='reddit'."""
        post = _make_collected_post()
        mock_shared = _call_write_embedding(post)
        call_kwargs = mock_shared.call_args.kwargs
        assert call_kwargs["payload"]["source_tool"] == "reddit"

    def test_write_embedding_payload_required_fields(self) -> None:
        """The payload must contain the four fields required by every tool."""
        post = _make_collected_post()
        mock_shared = _call_write_embedding(post)
        payload = mock_shared.call_args.kwargs["payload"]
        assert "source_tool" in payload
        assert "source_type" in payload
        assert "rule_name" in payload
        assert "collected_date" in payload

    def test_write_embedding_output_path_passed(self) -> None:
        """The output_path kwarg must match the post's output_path field."""
        post = _make_collected_post()
        mock_shared = _call_write_embedding(post)
        call_kwargs = mock_shared.call_args.kwargs
        assert call_kwargs["output_path"] == post.output_path

    def test_source_type_is_forum_post(self) -> None:
        """Reddit always uses source_type='forum_post'."""
        post = _make_collected_post()
        mock_shared = _call_write_embedding(post)
        payload = mock_shared.call_args.kwargs["payload"]
        assert payload["source_type"] == "forum_post"

    def test_flair_included_when_present(self) -> None:
        """When flair is set, the payload must include the flair field."""
        post = _make_collected_post(flair="Jobs")
        mock_shared = _call_write_embedding(post)
        payload = mock_shared.call_args.kwargs["payload"]
        assert "flair" in payload
        assert payload["flair"] == "Jobs"

    def test_flair_omitted_when_none(self) -> None:
        """When post.flair is None, the payload must not contain the 'flair' key."""
        post = _make_collected_post(flair=None)
        mock_shared = _call_write_embedding(post)
        payload = mock_shared.call_args.kwargs["payload"]
        assert "flair" not in payload

    def test_rule_name_in_payload(self) -> None:
        """The payload's rule_name must match the post's rule_name."""
        post = _make_collected_post()
        mock_shared = _call_write_embedding(post)
        payload = mock_shared.call_args.kwargs["payload"]
        assert payload["rule_name"] == "test_rule"

    def test_subreddit_in_payload(self) -> None:
        """The payload must carry the subreddit field."""
        post = _make_collected_post()
        mock_shared = _call_write_embedding(post)
        payload = mock_shared.call_args.kwargs["payload"]
        assert payload["subreddit"] == "python"

    def test_content_passed_through(self) -> None:
        """The content string must be forwarded unchanged to the shared function."""
        post = _make_collected_post()
        expected_content = "Title: A Great Python Post\n\nUnique body text for assertion."
        mock_shared = _call_write_embedding(post, content=expected_content)
        assert mock_shared.call_args.kwargs["content"] == expected_content
