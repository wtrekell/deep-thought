"""Tests verifying that embedding failures in web/processor.py do not abort collection.

These tests exercise the guarded embedding call inside ``_process_page``
to confirm that a failing embedding never prevents the DB upsert from occurring.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from deep_thought.web.processor import _process_page


def _make_page_result(
    url: str = "https://example.com/article",
    html: str = "<html><body><h1>Title</h1><p>Some body content here.</p></body></html>",
    title: str = "Article Title",
    status_code: int = 200,
) -> MagicMock:
    """Return a mock PageResult with configurable attributes."""
    result = MagicMock()
    result.url = url
    result.html = html
    result.title = title
    result.status_code = status_code
    return result


def _make_web_config(mode: str = "blog") -> MagicMock:
    """Return a mock WebConfig with minimal crawl settings for _process_page."""
    config = MagicMock()
    config.crawl.mode = mode
    config.crawl.min_article_words = 1
    config.crawl.strip_boilerplate = []
    config.crawl.unwrap_tags = []
    config.crawl.extract_images = False
    config.crawl.strip_path_prefix = ""
    config.crawl.strip_domain = False
    return config


# ---------------------------------------------------------------------------
# Embedding failure resilience
# ---------------------------------------------------------------------------


class TestProcessorEmbeddingFailureDoesNotAbort:
    @pytest.mark.error_handling
    def test_processor_embedding_failure_does_not_abort(self, output_root: Path) -> None:
        """A failing embedding must not prevent _process_page from returning a model.

        When ``write_embedding`` raises, the function should log a warning and
        continue, returning the page model with status='success'.
        """
        page_result = _make_page_result()
        config = _make_web_config(mode="blog")

        mock_embedding_model = MagicMock()
        mock_qdrant_client = MagicMock()

        with (
            patch("deep_thought.web.processor.extract_title", return_value="Article Title"),
            patch("deep_thought.web.processor.unwrap_html_tags", return_value=page_result.html),
            patch(
                "deep_thought.web.processor.convert_html_to_markdown",
                return_value="# Article Title\n\n" + "word " * 30,
            ),
            patch("deep_thought.web.processor.apply_boilerplate_patterns", side_effect=lambda md, _: md),
            patch("deep_thought.web.processor.count_words", return_value=30),
            patch("deep_thought.web.processor.write_page") as mock_write_page,
            patch("deep_thought.embeddings.write_embedding", side_effect=Exception("conn refused")),
        ):
            written_path = output_root / "example-com" / "article.md"
            written_path.parent.mkdir(parents=True, exist_ok=True)
            written_path.write_text("---\ntitle: Test\n---\n\n# Article Title\n\n" + "word " * 30, encoding="utf-8")
            mock_write_page.return_value = written_path

            page_model, page_summary = _process_page(
                page_result=page_result,
                config=config,
                output_root=output_root,
                rule_name=None,
                dry_run=False,
                embedding_model=mock_embedding_model,
                embedding_qdrant_client=mock_qdrant_client,
            )

        # Even with embedding failure the page model must be returned with success status
        assert page_model.status == "success"
        assert page_model.url == "https://example.com/article"

    def test_processor_without_embedding_model_skips_embedding(self, output_root: Path) -> None:
        """When no embedding model is provided, write_embedding must never be called."""
        page_result = _make_page_result()
        config = _make_web_config(mode="blog")

        with (
            patch("deep_thought.web.processor.extract_title", return_value="Article Title"),
            patch("deep_thought.web.processor.unwrap_html_tags", return_value=page_result.html),
            patch(
                "deep_thought.web.processor.convert_html_to_markdown",
                return_value="# Article Title\n\n" + "word " * 30,
            ),
            patch("deep_thought.web.processor.apply_boilerplate_patterns", side_effect=lambda md, _: md),
            patch("deep_thought.web.processor.count_words", return_value=30),
            patch("deep_thought.web.processor.write_page") as mock_write_page,
            patch("deep_thought.embeddings.write_embedding") as mock_shared_write,
        ):
            written_path = output_root / "example-com" / "article.md"
            written_path.parent.mkdir(parents=True, exist_ok=True)
            written_path.write_text("# content", encoding="utf-8")
            mock_write_page.return_value = written_path

            _process_page(
                page_result=page_result,
                config=config,
                output_root=output_root,
                rule_name=None,
                dry_run=False,
                embedding_model=None,
                embedding_qdrant_client=None,
            )

        mock_shared_write.assert_not_called()
