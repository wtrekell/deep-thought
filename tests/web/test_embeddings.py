"""Tests for deep_thought.web.embeddings.

All tests mock ``deep_thought.embeddings.write_embedding`` at the module
boundary so no real MLX model or Qdrant connection is required.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock, patch

from deep_thought.web.models import CrawledPageLocal

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_crawled_page(
    title: str | None = "An Interesting Article",
    rule_name: str | None = "tech_blogs",
    status_code: int | None = 200,
    output_path: str = "/data/web/blog/260402-example-com-an-interesting-article.md",
) -> CrawledPageLocal:
    """Return a CrawledPageLocal with configurable test values."""
    now_iso = datetime.now(tz=UTC).isoformat()
    return CrawledPageLocal(
        url="https://example.com/an-interesting-article",
        rule_name=rule_name,
        title=title,
        status_code=status_code,
        word_count=800,
        output_path=output_path,
        status="success",
        created_at=now_iso,
        updated_at=now_iso,
        synced_at=now_iso,
    )


def _call_write_embedding(
    page: CrawledPageLocal,
    mode: str = "blog",
    content: str = "Title: An Interesting Article\n\nBody text here.",
) -> Any:
    """Invoke the module under test with a mock model and client, returning the mock."""
    mock_model = MagicMock()
    mock_client = MagicMock()

    with patch("deep_thought.embeddings.write_embedding") as mock_shared_write:
        from deep_thought.web.embeddings import write_embedding

        write_embedding(
            content=content,
            page=page,
            mode=mode,
            model=mock_model,
            qdrant_client=mock_client,
        )
        return mock_shared_write


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestWriteEmbeddingCallsSharedFunction:
    def test_write_embedding_calls_shared_write_embedding(self) -> None:
        """The web write_embedding must call the shared write_embedding exactly once."""
        page = _make_crawled_page()
        mock_shared = _call_write_embedding(page)
        mock_shared.assert_called_once()

    def test_write_embedding_payload_source_tool(self) -> None:
        """The payload passed to the shared function must have source_tool='web'."""
        page = _make_crawled_page()
        mock_shared = _call_write_embedding(page)
        call_kwargs = mock_shared.call_args.kwargs
        assert call_kwargs["payload"]["source_tool"] == "web"

    def test_write_embedding_payload_required_fields(self) -> None:
        """The payload must contain the four fields required by every tool."""
        page = _make_crawled_page()
        mock_shared = _call_write_embedding(page)
        payload = mock_shared.call_args.kwargs["payload"]
        assert "source_tool" in payload
        assert "source_type" in payload
        assert "rule_name" in payload
        assert "collected_date" in payload

    def test_write_embedding_output_path_passed(self) -> None:
        """The output_path kwarg must match the page's output_path field."""
        page = _make_crawled_page()
        mock_shared = _call_write_embedding(page)
        call_kwargs = mock_shared.call_args.kwargs
        assert call_kwargs["output_path"] == page.output_path

    def test_write_embedding_canonical_id_is_url(self) -> None:
        """The canonical_id kwarg must be the page URL — stable across file moves."""
        page = _make_crawled_page()
        mock_shared = _call_write_embedding(page)
        call_kwargs = mock_shared.call_args.kwargs
        assert call_kwargs["canonical_id"] == page.url

    def test_source_type_blog(self) -> None:
        """Mode 'blog' must map to source_type='blog_post'."""
        page = _make_crawled_page()
        mock_shared = _call_write_embedding(page, mode="blog")
        payload = mock_shared.call_args.kwargs["payload"]
        assert payload["source_type"] == "blog_post"

    def test_source_type_documentation(self) -> None:
        """Mode 'documentation' must map to source_type='documentation'."""
        page = _make_crawled_page()
        mock_shared = _call_write_embedding(page, mode="documentation")
        payload = mock_shared.call_args.kwargs["payload"]
        assert payload["source_type"] == "documentation"

    def test_source_type_direct(self) -> None:
        """Mode 'direct' must map to source_type='article'."""
        page = _make_crawled_page()
        mock_shared = _call_write_embedding(page, mode="direct")
        payload = mock_shared.call_args.kwargs["payload"]
        assert payload["source_type"] == "article"

    def test_source_type_unknown_mode_defaults_to_article(self) -> None:
        """An unrecognised mode must fall back to source_type='article'."""
        page = _make_crawled_page()
        mock_shared = _call_write_embedding(page, mode="unknown")
        payload = mock_shared.call_args.kwargs["payload"]
        assert payload["source_type"] == "article"

    def test_title_included_when_present(self) -> None:
        """When title is not None, the payload must include the title field with its value."""
        page = _make_crawled_page(title="My Blog Post")
        mock_shared = _call_write_embedding(page)
        payload = mock_shared.call_args.kwargs["payload"]
        assert "title" in payload
        assert payload["title"] == "My Blog Post"

    def test_write_embedding_title_always_present(self) -> None:
        """When page.title is None, the payload must still contain 'title' as an empty string."""
        page = _make_crawled_page(title=None)
        mock_shared = _call_write_embedding(page)
        payload = mock_shared.call_args.kwargs["payload"]
        assert "title" in payload
        assert payload["title"] == ""

    def test_status_code_included_when_present(self) -> None:
        """When status_code is not None, it should appear in the payload."""
        page = _make_crawled_page(status_code=200)
        mock_shared = _call_write_embedding(page)
        payload = mock_shared.call_args.kwargs["payload"]
        assert payload["status_code"] == 200

    def test_status_code_omitted_when_none(self) -> None:
        """When status_code is None, the payload must not contain 'status_code'."""
        page = _make_crawled_page(status_code=None)
        mock_shared = _call_write_embedding(page)
        payload = mock_shared.call_args.kwargs["payload"]
        assert "status_code" not in payload

    def test_domain_extracted_from_url(self) -> None:
        """The domain field must be the netloc extracted from page.url."""
        page = _make_crawled_page()
        mock_shared = _call_write_embedding(page)
        payload = mock_shared.call_args.kwargs["payload"]
        assert payload["domain"] == "example.com"

    def test_rule_name_empty_string_when_none(self) -> None:
        """When page.rule_name is None, the payload rule_name must be an empty string."""
        page = _make_crawled_page(rule_name=None)
        mock_shared = _call_write_embedding(page)
        payload = mock_shared.call_args.kwargs["payload"]
        assert payload["rule_name"] == ""

    def test_content_passed_through(self) -> None:
        """The content string must be forwarded unchanged to the shared function."""
        page = _make_crawled_page()
        expected_content = "Title: Test\n\nDistinctive content for assertion purposes."
        mock_shared = _call_write_embedding(page, content=expected_content)
        assert mock_shared.call_args.kwargs["content"] == expected_content
