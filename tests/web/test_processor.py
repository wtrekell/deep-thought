"""Tests for processor.py: index_depth crawling, changelog re-crawl, and content quality gating."""

from __future__ import annotations

import sqlite3  # noqa: TC003
from pathlib import Path  # noqa: TC003
from unittest.mock import MagicMock

from deep_thought.web.config import CrawlConfig, WebConfig
from deep_thought.web.crawler import PageResult, WebCrawler
from deep_thought.web.processor import (
    _build_lookback_summaries,
    _collect_article_urls,
    _get_changelog_changed_urls,
    _is_article_content,
    _process_page,
    run_blog_mode,
    run_direct_mode,
    run_documentation_mode,
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
    max_pages: int = 100,
    changelog_url: str | None = None,
    include_patterns: list[str] | None = None,
    exclude_patterns: list[str] | None = None,
    strip_boilerplate: list[str] | None = None,
    unwrap_tags: list[str] | None = None,
) -> WebConfig:
    """Create a minimal WebConfig for use in tests."""
    return WebConfig(
        crawl=CrawlConfig(
            mode=mode,
            input_url=None,
            max_depth=3,
            max_pages=max_pages,
            js_wait=0.0,
            browser_channel=None,
            stealth=False,
            headless=True,
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
            strip_path_prefix=None,
            strip_domain=False,
            llms_lookback_days=30,
            strip_boilerplate=strip_boilerplate or [],
            unwrap_tags=unwrap_tags or [],
            pagination="none",
            pagination_selector=None,
            pagination_wait=2.0,
            max_paginations=10,
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
            output_root=tmp_path,
            rule_name=None,
            dry_run=False,
        )

        # No markdown files should exist in the output directory
        md_files = list(tmp_path.rglob("*.md"))
        assert md_files == []


# ---------------------------------------------------------------------------
# TestProcessPageWritePath (T-08: dry_run=False)
# ---------------------------------------------------------------------------


class TestProcessPageWritePath:
    """Tests for _process_page with dry_run=False (file writing path)."""

    def test_rich_page_writes_markdown_file_to_disk(self, tmp_path: Path) -> None:
        """A page above min_article_words must produce a .md file on disk when dry_run=False."""
        page_result = _make_page_result(url="https://example.com/blog/post-one", html=_RICH_ARTICLE_HTML)
        config = _make_web_config(min_article_words=50)

        page_model, page_summary = _process_page(
            page_result=page_result,
            config=config,
            output_root=tmp_path,
            rule_name=None,
            dry_run=False,
        )

        assert page_model.status == "success"
        assert page_model.output_path != ""
        written_file = tmp_path / page_model.output_path
        # The output_path may already be absolute
        if not written_file.exists():
            written_file = Path(page_model.output_path)
        assert written_file.exists(), f"Expected output file at {page_model.output_path}"

    def test_rich_page_returns_page_summary_with_content(self, tmp_path: Path) -> None:
        """A successfully written page must return a PageSummary with non-empty content."""
        page_result = _make_page_result(url="https://example.com/blog/post-one", html=_RICH_ARTICLE_HTML)
        config = _make_web_config(min_article_words=50)

        _page_model, page_summary = _process_page(
            page_result=page_result,
            config=config,
            output_root=tmp_path,
            rule_name=None,
            dry_run=False,
        )

        assert page_summary is not None
        assert page_summary.url == "https://example.com/blog/post-one"
        assert page_summary.word_count > 0
        assert len(page_summary.content) > 0

    def test_written_file_contains_frontmatter(self, tmp_path: Path) -> None:
        """The written markdown file must start with a YAML frontmatter block."""
        page_result = _make_page_result(url="https://example.com/blog/post-one", html=_RICH_ARTICLE_HTML)
        config = _make_web_config(min_article_words=50)

        page_model, _page_summary = _process_page(
            page_result=page_result,
            config=config,
            output_root=tmp_path,
            rule_name=None,
            dry_run=False,
        )

        written_file = Path(page_model.output_path)
        file_content = written_file.read_text(encoding="utf-8")
        assert file_content.startswith("---\n"), "Output file must begin with YAML frontmatter"
        assert "url:" in file_content
        assert "tool: web" in file_content

    def test_page_summary_content_has_frontmatter_stripped(self, tmp_path: Path) -> None:
        """The PageSummary content must not include the YAML frontmatter block."""
        page_result = _make_page_result(url="https://example.com/blog/post-one", html=_RICH_ARTICLE_HTML)
        config = _make_web_config(min_article_words=50)

        _page_model, page_summary = _process_page(
            page_result=page_result,
            config=config,
            output_root=tmp_path,
            rule_name=None,
            dry_run=False,
        )

        assert page_summary is not None
        # Frontmatter-stripped content must not start with "---"
        assert not page_summary.content.startswith("---")

    def test_rule_name_stored_in_page_model(self, tmp_path: Path) -> None:
        """A rule_name passed to _process_page must appear in the returned page model."""
        page_result = _make_page_result(url="https://example.com/blog/post-one", html=_RICH_ARTICLE_HTML)
        config = _make_web_config(min_article_words=50)

        page_model, _page_summary = _process_page(
            page_result=page_result,
            config=config,
            output_root=tmp_path,
            rule_name="my-site",
            dry_run=False,
        )

        assert page_model.rule_name == "my-site"


# ---------------------------------------------------------------------------
# TestBuildLookbackSummaries
# ---------------------------------------------------------------------------


def _insert_test_page(
    conn: sqlite3.Connection,
    url: str,
    title: str,
    output_path: str,
    word_count: int,
    updated_at: str,
    status: str = "success",
) -> None:
    """Insert a crawled_pages row for testing."""
    from deep_thought.web.db.queries import upsert_crawled_page

    upsert_crawled_page(
        conn,
        {
            "url": url,
            "rule_name": None,
            "title": title,
            "status_code": 200,
            "word_count": word_count,
            "output_path": output_path,
            "status": status,
            "created_at": updated_at,
            "updated_at": updated_at,
        },
    )
    conn.commit()


class TestBuildLookbackSummaries:
    """Tests for _build_lookback_summaries merging current + historical pages."""

    def test_includes_historical_pages_from_db(self, in_memory_db: sqlite3.Connection, tmp_path: Path) -> None:
        """Historical pages within the lookback window are included."""
        from datetime import UTC, datetime

        output_root = tmp_path / "output"
        output_root.mkdir()

        # Write a historical .md file on disk
        md_path = output_root / "example.com" / "old-post.md"
        md_path.parent.mkdir(parents=True)
        md_path.write_text("---\ntool: web\n---\n\nOld post content here.", encoding="utf-8")

        now_iso = datetime.now(UTC).isoformat()
        _insert_test_page(
            in_memory_db, "https://example.com/old-post", "Old Post", "example.com/old-post.md", 100, now_iso
        )

        result = _build_lookback_summaries(in_memory_db, [], output_root, lookback_days=30, mode="blog")

        assert len(result) == 1
        assert result[0].url == "https://example.com/old-post"
        assert result[0].title == "Old Post"
        assert "Old post content here." in result[0].content

    def test_current_run_wins_on_overlap(self, in_memory_db: sqlite3.Connection, tmp_path: Path) -> None:
        """When a URL exists in both current run and DB, the current-run version wins."""
        from datetime import UTC, datetime

        from deep_thought.web.llms import PageSummary

        output_root = tmp_path / "output"
        output_root.mkdir()

        now_iso = datetime.now(UTC).isoformat()
        _insert_test_page(in_memory_db, "https://example.com/page", "DB Title", "example.com/page.md", 50, now_iso)

        current_summary = PageSummary(
            title="Current Title",
            url="https://example.com/page",
            md_relative_path="example.com/page.md",
            mode="blog",
            word_count=200,
            content="Fresh content from current run.",
        )

        result = _build_lookback_summaries(in_memory_db, [current_summary], output_root, lookback_days=30, mode="blog")

        assert len(result) == 1
        assert result[0].title == "Current Title"
        assert result[0].content == "Fresh content from current run."

    def test_missing_file_skipped_gracefully(self, in_memory_db: sqlite3.Connection, tmp_path: Path) -> None:
        """A DB row whose .md file is missing on disk is silently skipped."""
        from datetime import UTC, datetime

        output_root = tmp_path / "output"
        output_root.mkdir()

        now_iso = datetime.now(UTC).isoformat()
        _insert_test_page(in_memory_db, "https://example.com/gone", "Gone Page", "example.com/gone.md", 100, now_iso)

        result = _build_lookback_summaries(in_memory_db, [], output_root, lookback_days=30, mode="blog")

        assert len(result) == 0

    def test_old_pages_outside_window_excluded(self, in_memory_db: sqlite3.Connection, tmp_path: Path) -> None:
        """Pages with updated_at older than the lookback window are not included."""
        from datetime import UTC, datetime, timedelta

        output_root = tmp_path / "output"
        output_root.mkdir()

        md_path = output_root / "example.com" / "ancient.md"
        md_path.parent.mkdir(parents=True)
        md_path.write_text("---\ntool: web\n---\n\nAncient content.", encoding="utf-8")

        old_date = (datetime.now(UTC) - timedelta(days=60)).isoformat()
        _insert_test_page(
            in_memory_db, "https://example.com/ancient", "Ancient", "example.com/ancient.md", 100, old_date
        )

        result = _build_lookback_summaries(in_memory_db, [], output_root, lookback_days=30, mode="blog")

        assert len(result) == 0

    def test_output_sorted_by_url(self, in_memory_db: sqlite3.Connection, tmp_path: Path) -> None:
        """Merged summaries are sorted alphabetically by URL."""
        from datetime import UTC, datetime

        from deep_thought.web.llms import PageSummary

        output_root = tmp_path / "output"
        output_root.mkdir()

        now_iso = datetime.now(UTC).isoformat()

        # Historical page (alphabetically first)
        md_path = output_root / "example.com" / "aaa.md"
        md_path.parent.mkdir(parents=True)
        md_path.write_text("---\ntool: web\n---\n\nAAA content.", encoding="utf-8")
        _insert_test_page(in_memory_db, "https://example.com/aaa", "AAA", "example.com/aaa.md", 50, now_iso)

        # Current-run page (alphabetically last)
        current_summary = PageSummary(
            title="ZZZ",
            url="https://example.com/zzz",
            md_relative_path="example.com/zzz.md",
            mode="blog",
            word_count=100,
            content="ZZZ content.",
        )

        result = _build_lookback_summaries(in_memory_db, [current_summary], output_root, lookback_days=30, mode="blog")

        assert len(result) == 2
        assert result[0].url == "https://example.com/aaa"
        assert result[1].url == "https://example.com/zzz"

    def test_error_status_pages_excluded(self, in_memory_db: sqlite3.Connection, tmp_path: Path) -> None:
        """Pages with status 'error' are not included even if within the window."""
        from datetime import UTC, datetime

        output_root = tmp_path / "output"
        output_root.mkdir()

        now_iso = datetime.now(UTC).isoformat()
        _insert_test_page(
            in_memory_db, "https://example.com/broken", "Broken", "example.com/broken.md", 100, now_iso, status="error"
        )

        result = _build_lookback_summaries(in_memory_db, [], output_root, lookback_days=30, mode="blog")

        assert len(result) == 0


# ---------------------------------------------------------------------------
# TestModeRunners (T-06)
# ---------------------------------------------------------------------------


class TestRunBlogMode:
    """Tests for run_blog_mode orchestration."""

    def test_returns_crawl_result_and_summaries(self, in_memory_db: sqlite3.Connection, tmp_path: Path) -> None:
        """run_blog_mode must return a (CrawlResult, list[PageSummary]) tuple."""
        mock_crawler = MagicMock(spec=WebCrawler)
        # Index page linking to one article
        index_html = (
            "<!DOCTYPE html><html><head><title>Index</title></head><body>"
            '<a href="https://example.com/post">Post</a></body></html>'
        )
        article_html = (
            "<!DOCTYPE html><html><head><title>Post</title></head><body>"
            "<p>" + " ".join(["word"] * 300) + "</p></body></html>"
        )
        mock_crawler.fetch_page.side_effect = [
            PageResult(url="https://example.com/", html=index_html, status_code=200, title="Index"),
            PageResult(url="https://example.com/post", html=article_html, status_code=200, title="Post"),
        ]

        config = _make_web_config(mode="blog", min_article_words=50, index_depth=1)
        crawl_result, summaries = run_blog_mode(
            crawler=mock_crawler,
            config=config,
            conn=in_memory_db,
            root_url="https://example.com/",
            output_root=tmp_path,
            dry_run=True,
            force=False,
        )

        assert crawl_result.succeeded >= 0
        assert isinstance(summaries, list)

    def test_skips_already_crawled_urls_without_force(self, in_memory_db: sqlite3.Connection, tmp_path: Path) -> None:
        """Existing 'success' URLs must be skipped when force=False."""
        from deep_thought.web.db.queries import upsert_crawled_page

        already_crawled_url = "https://example.com/post"
        upsert_crawled_page(
            in_memory_db,
            {
                "url": already_crawled_url,
                "rule_name": None,
                "title": "Post",
                "status_code": 200,
                "word_count": 300,
                "output_path": "output/example.com/post.md",
                "status": "success",
                "created_at": "2026-03-01T00:00:00+00:00",
                "updated_at": "2026-03-01T00:00:00+00:00",
            },
        )
        in_memory_db.commit()

        mock_crawler = MagicMock(spec=WebCrawler)
        index_html = f'<!DOCTYPE html><html><body><a href="{already_crawled_url}">Post</a></body></html>'
        mock_crawler.fetch_page.return_value = PageResult(
            url="https://example.com/", html=index_html, status_code=200, title="Index"
        )

        config = _make_web_config(mode="blog", min_article_words=50, index_depth=1)
        crawl_result, _summaries = run_blog_mode(
            crawler=mock_crawler,
            config=config,
            conn=in_memory_db,
            root_url="https://example.com/",
            output_root=tmp_path,
            dry_run=True,
            force=False,
        )

        assert crawl_result.skipped >= 1


class TestRunDirectMode:
    """Tests for run_direct_mode orchestration."""

    def test_raises_file_not_found_for_missing_url_file(self, in_memory_db: sqlite3.Connection, tmp_path: Path) -> None:
        """run_direct_mode must raise FileNotFoundError when the URL file does not exist."""
        import pytest

        mock_crawler = MagicMock(spec=WebCrawler)
        config = _make_web_config(mode="direct")
        missing_file = tmp_path / "urls.txt"

        with pytest.raises(FileNotFoundError):
            run_direct_mode(
                crawler=mock_crawler,
                config=config,
                conn=in_memory_db,
                url_file=missing_file,
                output_root=tmp_path,
                dry_run=True,
                force=False,
            )

    def test_skips_blank_lines_and_comments_in_url_file(self, in_memory_db: sqlite3.Connection, tmp_path: Path) -> None:
        """Blank lines and comment lines starting with # must not be crawled."""
        url_file = tmp_path / "urls.txt"
        url_file.write_text(
            "# This is a comment\n\nhttps://example.com/page\n\n",
            encoding="utf-8",
        )

        article_html = (
            "<!DOCTYPE html><html><head><title>Page</title></head><body>"
            "<p>" + " ".join(["word"] * 300) + "</p></body></html>"
        )
        mock_crawler = MagicMock(spec=WebCrawler)
        mock_crawler.fetch_page.return_value = PageResult(
            url="https://example.com/page", html=article_html, status_code=200, title="Page"
        )

        config = _make_web_config(mode="direct", min_article_words=50)
        crawl_result, _summaries = run_direct_mode(
            crawler=mock_crawler,
            config=config,
            conn=in_memory_db,
            url_file=url_file,
            output_root=tmp_path,
            dry_run=True,
            force=False,
        )

        # Only one real URL should have been attempted
        assert mock_crawler.fetch_page.call_count == 1
        assert crawl_result.total == 1

    def test_records_error_on_fetch_failure(self, in_memory_db: sqlite3.Connection, tmp_path: Path) -> None:
        """A fetch failure must increment the failed count and not raise."""
        url_file = tmp_path / "urls.txt"
        url_file.write_text("https://example.com/broken\n", encoding="utf-8")

        mock_crawler = MagicMock(spec=WebCrawler)
        mock_crawler.fetch_page.side_effect = ConnectionError("Timeout")

        config = _make_web_config(mode="direct", min_article_words=50)
        crawl_result, _summaries = run_direct_mode(
            crawler=mock_crawler,
            config=config,
            conn=in_memory_db,
            url_file=url_file,
            output_root=tmp_path,
            dry_run=True,
            force=False,
        )

        assert crawl_result.failed == 1
        assert crawl_result.succeeded == 0


class TestRunDocumentationMode:
    """Tests for run_documentation_mode orchestration."""

    def test_returns_crawl_result(self, in_memory_db: sqlite3.Connection, tmp_path: Path) -> None:
        """run_documentation_mode must return a (CrawlResult, list[PageSummary]) tuple."""
        article_html = (
            "<!DOCTYPE html><html><head><title>Doc</title></head><body>"
            "<p>" + " ".join(["word"] * 300) + "</p></body></html>"
        )
        mock_crawler = MagicMock(spec=WebCrawler)
        mock_crawler.fetch_page.return_value = PageResult(
            url="https://docs.example.com/", html=article_html, status_code=200, title="Doc"
        )

        config = _make_web_config(mode="documentation", min_article_words=50)
        crawl_result, summaries = run_documentation_mode(
            crawler=mock_crawler,
            config=config,
            conn=in_memory_db,
            root_url="https://docs.example.com/",
            output_root=tmp_path,
            dry_run=True,
            force=False,
        )

        assert crawl_result.total >= 0
        assert isinstance(summaries, list)

    def test_stops_at_max_pages(self, in_memory_db: sqlite3.Connection, tmp_path: Path) -> None:
        """run_documentation_mode must not process more pages than max_pages."""
        article_html = (
            "<!DOCTYPE html><html><head><title>Doc</title></head><body>"
            "<p>" + " ".join(["word"] * 300) + "</p></body></html>"
        )
        mock_crawler = MagicMock(spec=WebCrawler)
        mock_crawler.fetch_page.return_value = PageResult(
            url="https://docs.example.com/", html=article_html, status_code=200, title="Doc"
        )

        # max_pages=1 means only the root page is processed
        config = _make_web_config(mode="documentation", min_article_words=50, max_pages=1)
        crawl_result, _summaries = run_documentation_mode(
            crawler=mock_crawler,
            config=config,
            conn=in_memory_db,
            root_url="https://docs.example.com/",
            output_root=tmp_path,
            dry_run=True,
            force=False,
        )

        assert crawl_result.total <= 1
