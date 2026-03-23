"""Tests for processor.py: index_depth crawling, changelog re-crawl, and content quality gating."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

if TYPE_CHECKING:
    import sqlite3
    from pathlib import Path

from deep_thought.web.config import CrawlConfig, WebConfig
from deep_thought.web.crawler import PageResult, WebCrawler
from deep_thought.web.processor import (
    _collect_article_urls,
    _get_changelog_changed_urls,
    _is_article_content,
    _process_page,
)

# ---------------------------------------------------------------------------
# HTML fixtures
# ---------------------------------------------------------------------------

# A sparse index page linking to three blog posts
_SPARSE_INDEX_HTML = """<!DOCTYPE html>
<html>
<head><title>Blog Index</title></head>
<body>
<h1>Blog Posts</h1>
<ul>
  <li><a href="https://example.com/blog/post-one">Post One</a></li>
  <li><a href="https://example.com/blog/post-two">Post Two</a></li>
  <li><a href="https://example.com/blog/post-three">Post Three</a></li>
</ul>
</body>
</html>"""

# A rich article page with enough words to pass the min_article_words gate
_RICH_ARTICLE_HTML = (
    "<!DOCTYPE html><html><head><title>Post One</title></head><body>"
    "<h1>Post One</h1><p>" + " ".join(["content"] * 300) + "</p></body></html>"
)

# A changelog page linking to two updated docs pages
_CHANGELOG_HTML = """<!DOCTYPE html>
<html>
<head><title>Changelog</title></head>
<body>
<h1>What Changed</h1>
<ul>
  <li><a href="/docs/guide">Updated Guide</a></li>
  <li><a href="/docs/api">Updated API Reference</a></li>
</ul>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_page_result(url: str, html: str, status_code: int = 200) -> PageResult:
    """Create a PageResult for use in tests."""
    return PageResult(url=url, html=html, status_code=status_code, title=None)


def _make_web_config(
    mode: str = "blog",
    min_article_words: int = 200,
    index_depth: int = 1,
    changelog_url: str | None = None,
    include_patterns: list[str] | None = None,
    exclude_patterns: list[str] | None = None,
) -> WebConfig:
    """Create a minimal WebConfig for use in tests."""
    return WebConfig(
        crawl=CrawlConfig(
            mode=mode,
            input_url=None,
            max_depth=3,
            max_pages=100,
            js_wait=0.0,
            browser_channel=None,
            stealth=False,
            include_patterns=include_patterns or [],
            exclude_patterns=exclude_patterns or [],
            retry_attempts=1,
            retry_delay=0.0,
            output_dir="data/web/export/",
            extract_images=False,
            generate_llms_files=False,
            index_depth=index_depth,
            min_article_words=min_article_words,
            changelog_url=changelog_url,
        )
    )


# ---------------------------------------------------------------------------
# TestIsArticleContent
# ---------------------------------------------------------------------------


class TestIsArticleContent:
    def test_returns_true_at_exact_threshold(self) -> None:
        """_is_article_content must return True when word_count equals min_words."""
        assert _is_article_content(200, 200) is True

    def test_returns_true_above_threshold(self) -> None:
        """_is_article_content must return True when word_count exceeds min_words."""
        assert _is_article_content(500, 200) is True

    def test_returns_false_below_threshold(self) -> None:
        """_is_article_content must return False when word_count is less than min_words."""
        assert _is_article_content(50, 200) is False

    def test_returns_false_for_zero_words(self) -> None:
        """_is_article_content must return False for a page with no words."""
        assert _is_article_content(0, 200) is False


# ---------------------------------------------------------------------------
# TestCollectArticleUrls
# ---------------------------------------------------------------------------


class TestCollectArticleUrls:
    def test_depth_zero_returns_url_without_fetching(self) -> None:
        """At remaining_depth=0, the URL itself is returned and no fetch calls are made."""
        mock_crawler = MagicMock(spec=WebCrawler)

        result = _collect_article_urls(
            crawler=mock_crawler,
            url="https://example.com/blog/post-one",
            include_patterns=[],
            exclude_patterns=[],
            remaining_depth=0,
            visited=set(),
        )

        mock_crawler.fetch_page.assert_not_called()
        assert result == ["https://example.com/blog/post-one"]

    def test_depth_one_fetches_index_and_returns_child_links(self) -> None:
        """At remaining_depth=1, the index URL is fetched and its internal links are returned."""
        mock_crawler = MagicMock(spec=WebCrawler)
        mock_crawler.fetch_page.return_value = _make_page_result(
            url="https://example.com/blog/",
            html=_SPARSE_INDEX_HTML,
        )

        result = _collect_article_urls(
            crawler=mock_crawler,
            url="https://example.com/blog/",
            include_patterns=[],
            exclude_patterns=[],
            remaining_depth=1,
            visited={"https://example.com/blog/"},
        )

        assert "https://example.com/blog/post-one" in result
        assert "https://example.com/blog/post-two" in result
        assert "https://example.com/blog/post-three" in result

    def test_excluded_urls_are_not_collected(self) -> None:
        """Links matching an exclude_pattern must not appear in the collected article URLs."""
        mock_crawler = MagicMock(spec=WebCrawler)
        mock_crawler.fetch_page.return_value = _make_page_result(
            url="https://example.com/blog/",
            html=_SPARSE_INDEX_HTML,
        )

        result = _collect_article_urls(
            crawler=mock_crawler,
            url="https://example.com/blog/",
            include_patterns=[],
            exclude_patterns=[r".*/post-one$"],
            remaining_depth=1,
            visited={"https://example.com/blog/"},
        )

        assert "https://example.com/blog/post-one" not in result
        assert "https://example.com/blog/post-two" in result

    def test_already_visited_urls_are_skipped(self) -> None:
        """URLs already present in the visited set must not be collected or re-fetched."""
        mock_crawler = MagicMock(spec=WebCrawler)
        mock_crawler.fetch_page.return_value = _make_page_result(
            url="https://example.com/blog/",
            html=_SPARSE_INDEX_HTML,
        )

        visited = {"https://example.com/blog/", "https://example.com/blog/post-one"}
        result = _collect_article_urls(
            crawler=mock_crawler,
            url="https://example.com/blog/",
            include_patterns=[],
            exclude_patterns=[],
            remaining_depth=1,
            visited=visited,
        )

        assert "https://example.com/blog/post-one" not in result
        assert "https://example.com/blog/post-two" in result

    def test_fetch_error_returns_empty_list(self) -> None:
        """A network error fetching an index page must return an empty list, not raise."""
        mock_crawler = MagicMock(spec=WebCrawler)
        mock_crawler.fetch_page.side_effect = ConnectionError("Network unreachable")

        result = _collect_article_urls(
            crawler=mock_crawler,
            url="https://example.com/blog/",
            include_patterns=[],
            exclude_patterns=[],
            remaining_depth=1,
            visited=set(),
        )

        assert result == []


# ---------------------------------------------------------------------------
# TestGetChangelogChangedUrls
# ---------------------------------------------------------------------------


class TestGetChangelogChangedUrls:
    def test_returns_set_of_internal_links_from_changelog(self) -> None:
        """_get_changelog_changed_urls must return the set of internal links found on the changelog page."""
        mock_crawler = MagicMock(spec=WebCrawler)
        mock_crawler.fetch_page.return_value = _make_page_result(
            url="https://docs.example.com/changelog",
            html=_CHANGELOG_HTML,
        )

        result = _get_changelog_changed_urls(
            crawler=mock_crawler,
            changelog_url="https://docs.example.com/changelog",
            root_url="https://docs.example.com/",
        )

        assert "https://docs.example.com/docs/guide" in result
        assert "https://docs.example.com/docs/api" in result

    def test_returns_empty_set_on_fetch_failure(self) -> None:
        """A network error fetching the changelog must return an empty set, not raise."""
        mock_crawler = MagicMock(spec=WebCrawler)
        mock_crawler.fetch_page.side_effect = ConnectionError("Timeout")

        result = _get_changelog_changed_urls(
            crawler=mock_crawler,
            changelog_url="https://docs.example.com/changelog",
            root_url="https://docs.example.com/",
        )

        assert result == set()


# ---------------------------------------------------------------------------
# TestProcessPageQualityGate
# ---------------------------------------------------------------------------


class TestProcessPageQualityGate:
    def test_sparse_page_is_returned_with_skipped_status(
        self, in_memory_db: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """A page below min_article_words must be returned with status='skipped' and no PageSummary."""
        page_result = _make_page_result(url="https://example.com/blog/", html=_SPARSE_INDEX_HTML)
        # Set threshold extremely high so the sparse index page definitely falls below it
        config = _make_web_config(min_article_words=10_000)

        page_model, summary = _process_page(
            page_result=page_result,
            config=config,
            conn=in_memory_db,
            output_root=tmp_path,
            rule_name=None,
            dry_run=True,
        )

        assert page_model.status == "skipped"
        assert summary is None

    def test_page_above_threshold_is_returned_with_success_status(
        self, in_memory_db: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """A page with sufficient word count must be returned with status='success'."""
        page_result = _make_page_result(url="https://example.com/blog/post-one", html=_RICH_ARTICLE_HTML)
        # Set threshold low so the rich article passes comfortably
        config = _make_web_config(min_article_words=50)

        page_model, summary = _process_page(
            page_result=page_result,
            config=config,
            conn=in_memory_db,
            output_root=tmp_path,
            rule_name=None,
            dry_run=True,
        )

        assert page_model.status == "success"

    def test_sparse_page_is_not_written_to_disk(self, in_memory_db: sqlite3.Connection, tmp_path: Path) -> None:
        """A skipped page must not create any output files on disk."""
        page_result = _make_page_result(url="https://example.com/blog/", html=_SPARSE_INDEX_HTML)
        config = _make_web_config(min_article_words=10_000)

        _process_page(
            page_result=page_result,
            config=config,
            conn=in_memory_db,
            output_root=tmp_path,
            rule_name=None,
            dry_run=False,
        )

        # No markdown files should exist in the output directory
        md_files = list(tmp_path.rglob("*.md"))
        assert md_files == []
