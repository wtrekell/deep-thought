"""Tests for JS pagination support: config parsing, validation, and crawl logic."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from deep_thought.web.config import CrawlConfig, WebConfig, _parse_crawl_config, validate_config
from deep_thought.web.crawler import CrawlerConfig, PageResult, WebCrawler
from deep_thought.web.processor import _collect_article_urls

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_crawl_config(
    pagination: str = "none",
    pagination_selector: str | None = None,
    pagination_wait: float = 2.0,
    max_paginations: int = 10,
) -> CrawlConfig:
    """Return a minimal CrawlConfig with pagination settings applied."""
    return CrawlConfig(
        mode="blog",
        input_url=None,
        max_depth=3,
        max_pages=100,
        js_wait=0.0,
        browser_channel=None,
        stealth=False,
        headless=True,
        include_patterns=[],
        exclude_patterns=[],
        retry_attempts=1,
        retry_delay=0.0,
        output_dir="output/web/",
        extract_images=False,
        generate_llms_files=False,
        index_depth=1,
        min_article_words=200,
        changelog_url=None,
        strip_path_prefix=None,
        strip_domain=False,
        llms_lookback_days=30,
        strip_boilerplate=[],
        unwrap_tags=[],
        pagination=pagination,
        pagination_selector=pagination_selector,
        pagination_wait=pagination_wait,
        max_paginations=max_paginations,
    )


def _make_web_config(
    pagination: str = "none",
    pagination_selector: str | None = None,
    pagination_wait: float = 2.0,
    max_paginations: int = 10,
) -> WebConfig:
    """Return a minimal WebConfig with pagination settings applied."""
    return WebConfig(
        crawl=_make_crawl_config(
            pagination=pagination,
            pagination_selector=pagination_selector,
            pagination_wait=pagination_wait,
            max_paginations=max_paginations,
        )
    )


def _make_minimal_crawler_config(
    pagination: str = "none",
    pagination_selector: str | None = None,
    pagination_wait: float = 2.0,
    max_paginations: int = 10,
) -> CrawlerConfig:
    """Return a minimal CrawlerConfig with pagination settings applied."""
    return CrawlerConfig(
        js_wait=0.0,
        browser_channel=None,
        stealth=False,
        headless=True,
        retry_attempts=0,
        retry_delay=0.0,
        pagination=pagination,
        pagination_selector=pagination_selector,
        pagination_wait=pagination_wait,
        max_paginations=max_paginations,
    )


def _make_page_result(url: str, html: str, status_code: int = 200) -> PageResult:
    """Return a PageResult for use in tests."""
    return PageResult(url=url, html=html, status_code=status_code, title=None)


_INDEX_HTML_WITH_LINKS = """<!DOCTYPE html>
<html>
<head><title>Blog Index</title></head>
<body>
<h1>Blog Posts</h1>
<ul>
  <li><a href="https://example.com/blog/post-one">Post One</a></li>
  <li><a href="https://example.com/blog/post-two">Post Two</a></li>
</ul>
</body>
</html>"""


# ---------------------------------------------------------------------------
# TestConfigParsing — pagination fields parsed from YAML
# ---------------------------------------------------------------------------


class TestConfigParsing:
    def test_defaults_applied_when_pagination_fields_absent(self) -> None:
        """_parse_crawl_config must apply 'none'/null/2.0/10 defaults when pagination keys are absent."""
        raw: dict[str, object] = {"mode": "blog", "output_dir": "output/web/"}
        crawl_config = _parse_crawl_config(raw)

        assert crawl_config.pagination == "none"
        assert crawl_config.pagination_selector is None
        assert crawl_config.pagination_wait == 2.0
        assert crawl_config.max_paginations == 10

    def test_scroll_strategy_parsed_correctly(self) -> None:
        """_parse_crawl_config must read pagination='scroll' from YAML."""
        raw: dict[str, object] = {"mode": "blog", "output_dir": "output/web/", "pagination": "scroll"}
        crawl_config = _parse_crawl_config(raw)

        assert crawl_config.pagination == "scroll"

    def test_click_strategy_parsed_correctly(self) -> None:
        """_parse_crawl_config must read pagination='click' and pagination_selector from YAML."""
        raw: dict[str, object] = {
            "mode": "blog",
            "output_dir": "output/web/",
            "pagination": "click",
            "pagination_selector": "button.load-more",
        }
        crawl_config = _parse_crawl_config(raw)

        assert crawl_config.pagination == "click"
        assert crawl_config.pagination_selector == "button.load-more"

    def test_pagination_wait_and_max_paginations_parsed(self) -> None:
        """_parse_crawl_config must read pagination_wait and max_paginations from YAML."""
        raw: dict[str, object] = {
            "mode": "blog",
            "output_dir": "output/web/",
            "pagination_wait": 3.5,
            "max_paginations": 5,
        }
        crawl_config = _parse_crawl_config(raw)

        assert crawl_config.pagination_wait == 3.5
        assert crawl_config.max_paginations == 5

    def test_pagination_selector_null_yields_none(self) -> None:
        """An explicit null pagination_selector in YAML must produce None in the config."""
        raw: dict[str, object] = {
            "mode": "blog",
            "output_dir": "output/web/",
            "pagination_selector": None,
        }
        crawl_config = _parse_crawl_config(raw)

        assert crawl_config.pagination_selector is None


# ---------------------------------------------------------------------------
# TestConfigValidation — invalid pagination values caught
# ---------------------------------------------------------------------------


class TestConfigValidation:
    def test_valid_none_strategy_produces_no_issues(self) -> None:
        """pagination='none' is valid and must not produce validation issues."""
        config = _make_web_config(pagination="none")
        issues = validate_config(config)

        pagination_issues = [issue for issue in issues if "pagination" in issue.lower()]
        assert pagination_issues == []

    def test_valid_scroll_strategy_produces_no_issues(self) -> None:
        """pagination='scroll' is valid and must not produce validation issues."""
        config = _make_web_config(pagination="scroll")
        issues = validate_config(config)

        pagination_issues = [issue for issue in issues if "pagination" in issue.lower()]
        assert pagination_issues == []

    def test_valid_click_strategy_with_selector_produces_no_issues(self) -> None:
        """pagination='click' with a non-empty selector must not produce validation issues."""
        config = _make_web_config(pagination="click", pagination_selector="button.load-more")
        issues = validate_config(config)

        pagination_issues = [issue for issue in issues if "pagination" in issue.lower()]
        assert pagination_issues == []

    def test_invalid_pagination_strategy_produces_issue(self) -> None:
        """An unrecognised pagination strategy must produce a validation issue."""
        config = _make_web_config(pagination="infinite")
        issues = validate_config(config)

        assert any("pagination" in issue.lower() and "infinite" in issue for issue in issues)

    def test_click_strategy_without_selector_produces_issue(self) -> None:
        """pagination='click' with pagination_selector=None must produce a validation issue."""
        config = _make_web_config(pagination="click", pagination_selector=None)
        issues = validate_config(config)

        assert any("pagination_selector" in issue for issue in issues)

    def test_click_strategy_with_empty_selector_produces_issue(self) -> None:
        """pagination='click' with a whitespace-only selector must produce a validation issue."""
        config = _make_web_config(pagination="click", pagination_selector="   ")
        issues = validate_config(config)

        assert any("pagination_selector" in issue for issue in issues)

    def test_negative_pagination_wait_produces_issue(self) -> None:
        """pagination_wait < 0 must produce a validation issue."""
        config = _make_web_config(pagination_wait=-1.0)
        issues = validate_config(config)

        assert any("pagination_wait" in issue for issue in issues)

    def test_zero_max_paginations_produces_issue(self) -> None:
        """max_paginations <= 0 must produce a validation issue."""
        config = _make_web_config(max_paginations=0)
        issues = validate_config(config)

        assert any("max_paginations" in issue for issue in issues)

    def test_negative_max_paginations_produces_issue(self) -> None:
        """max_paginations < 0 must produce a validation issue."""
        config = _make_web_config(max_paginations=-5)
        issues = validate_config(config)

        assert any("max_paginations" in issue for issue in issues)


# ---------------------------------------------------------------------------
# TestFetchPageWithPaginationNone — passthrough to fetch_page
# ---------------------------------------------------------------------------


class TestFetchPageWithPaginationNone:
    def test_none_strategy_delegates_to_fetch_page(self) -> None:
        """fetch_page_with_pagination must delegate to fetch_page when pagination='none'."""
        crawler_config = _make_minimal_crawler_config(pagination="none")
        expected_result = _make_page_result("https://example.com/blog/", _INDEX_HTML_WITH_LINKS)

        with (
            patch.object(WebCrawler, "fetch_page", return_value=expected_result) as mock_fetch,
            WebCrawler(crawler_config) as crawler,
        ):
            result = crawler.fetch_page_with_pagination("https://example.com/blog/")

        mock_fetch.assert_called_once_with("https://example.com/blog/")
        assert result is expected_result


# ---------------------------------------------------------------------------
# TestPaginateByScroll — scroll pagination logic
# ---------------------------------------------------------------------------


class TestPaginateByScroll:
    def _make_mock_page(self, height_sequence: list[int]) -> MagicMock:
        """Return a mock Page whose evaluate('document.body.scrollHeight') returns values in sequence.

        The scroll method calls evaluate() three times per iteration:
          1. get previous scrollHeight
          2. scrollTo (returns None)
          3. get current scrollHeight
        This helper routes calls by script content: scrollHeight reads consume
        from height_sequence in order; scrollTo calls return None.
        """
        height_iterator = iter(height_sequence)
        mock_page = MagicMock()

        def evaluate_side_effect(script: str) -> int | None:
            if "scrollHeight" in script and "scrollTo" not in script:
                return next(height_iterator)
            return None  # scrollTo returns nothing meaningful

        mock_page.evaluate.side_effect = evaluate_side_effect
        mock_page.wait_for_load_state.return_value = None
        mock_page.wait_for_timeout.return_value = None
        return mock_page

    def test_stops_when_height_does_not_grow(self) -> None:
        """_paginate_by_scroll must stop after a single iteration when the page height does not change."""
        crawler_config = _make_minimal_crawler_config(pagination="scroll", pagination_wait=0.0, max_paginations=5)
        # Same height before and after scroll — no new content loaded
        mock_page = self._make_mock_page([1000, 1000])

        with WebCrawler(crawler_config) as crawler:
            crawler._paginate_by_scroll(mock_page)

        # 1 iteration × 3 evaluate calls (get height, scrollTo, get height)
        assert mock_page.evaluate.call_count == 3

    def test_continues_while_height_grows(self) -> None:
        """_paginate_by_scroll must continue iterating as long as the page height keeps growing."""
        crawler_config = _make_minimal_crawler_config(pagination="scroll", pagination_wait=0.0, max_paginations=5)
        # Heights: 1000 → 2000 → 3000 → 3000 (stops at third iteration)
        mock_page = self._make_mock_page([1000, 2000, 2000, 3000, 3000, 3000])

        with WebCrawler(crawler_config) as crawler:
            crawler._paginate_by_scroll(mock_page)

        # 3 iterations × 3 evaluate calls each = 9
        assert mock_page.evaluate.call_count == 9

    def test_respects_max_paginations_limit(self) -> None:
        """_paginate_by_scroll must not exceed max_paginations iterations even if height keeps growing."""
        max_paginations = 3
        crawler_config = _make_minimal_crawler_config(
            pagination="scroll", pagination_wait=0.0, max_paginations=max_paginations
        )
        # Endless growing page: heights always increase so the only stop is max_paginations
        mock_page = self._make_mock_page([1000, 2000, 2000, 3000, 3000, 4000, 4000, 5000])

        with WebCrawler(crawler_config) as crawler:
            crawler._paginate_by_scroll(mock_page)

        # max_paginations iterations × 3 evaluate calls each = 9
        assert mock_page.evaluate.call_count == max_paginations * 3

    def test_playwright_error_stops_pagination_gracefully(self) -> None:
        """A PlaywrightError during a scroll iteration must stop pagination without raising."""
        from playwright.sync_api import Error as PlaywrightError

        crawler_config = _make_minimal_crawler_config(pagination="scroll", pagination_wait=0.0, max_paginations=5)
        mock_page = MagicMock()
        mock_page.evaluate.side_effect = PlaywrightError("detached frame")

        with WebCrawler(crawler_config) as crawler:
            # Must not raise
            crawler._paginate_by_scroll(mock_page)


# ---------------------------------------------------------------------------
# TestPaginateByClick — click pagination logic
# ---------------------------------------------------------------------------


class TestPaginateByClick:
    def test_stops_when_button_disappears(self) -> None:
        """_paginate_by_click must stop when the selector is no longer visible."""
        crawler_config = _make_minimal_crawler_config(
            pagination="click",
            pagination_selector="button.load-more",
            pagination_wait=0.0,
            max_paginations=5,
        )
        mock_page = MagicMock()
        mock_locator = MagicMock()
        # Visible on first check, invisible on second check
        mock_locator.is_visible.side_effect = [True, False]
        mock_page.locator.return_value = mock_locator
        mock_page.wait_for_load_state.return_value = None
        mock_page.wait_for_timeout.return_value = None

        with WebCrawler(crawler_config) as crawler:
            crawler._paginate_by_click(mock_page)

        assert mock_locator.click.call_count == 1

    def test_respects_max_paginations_limit(self) -> None:
        """_paginate_by_click must not exceed max_paginations clicks even if button stays visible."""
        max_paginations = 3
        crawler_config = _make_minimal_crawler_config(
            pagination="click",
            pagination_selector="button.load-more",
            pagination_wait=0.0,
            max_paginations=max_paginations,
        )
        mock_page = MagicMock()
        mock_locator = MagicMock()
        # Always visible — only max_paginations stops the loop
        mock_locator.is_visible.return_value = True
        mock_page.locator.return_value = mock_locator
        mock_page.wait_for_load_state.return_value = None
        mock_page.wait_for_timeout.return_value = None

        with WebCrawler(crawler_config) as crawler:
            crawler._paginate_by_click(mock_page)

        assert mock_locator.click.call_count == max_paginations

    def test_no_selector_logs_warning_and_returns(self) -> None:
        """_paginate_by_click must skip pagination and log a warning when selector is None."""
        crawler_config = _make_minimal_crawler_config(
            pagination="click",
            pagination_selector=None,
            pagination_wait=0.0,
            max_paginations=5,
        )
        mock_page = MagicMock()

        with WebCrawler(crawler_config) as crawler:
            crawler._paginate_by_click(mock_page)

        # No locator interaction should occur
        mock_page.locator.assert_not_called()

    def test_playwright_error_stops_pagination_gracefully(self) -> None:
        """A PlaywrightError during a click iteration must stop pagination without raising."""
        from playwright.sync_api import Error as PlaywrightError

        crawler_config = _make_minimal_crawler_config(
            pagination="click",
            pagination_selector="button.load-more",
            pagination_wait=0.0,
            max_paginations=5,
        )
        mock_page = MagicMock()
        mock_locator = MagicMock()
        mock_locator.is_visible.return_value = True
        mock_locator.click.side_effect = PlaywrightError("element not clickable")
        mock_page.locator.return_value = mock_locator
        mock_page.wait_for_timeout.return_value = None

        with WebCrawler(crawler_config) as crawler:
            # Must not raise
            crawler._paginate_by_click(mock_page)


# ---------------------------------------------------------------------------
# TestCollectArticleUrlsWithPagination — wiring into processor
# ---------------------------------------------------------------------------


class TestCollectArticleUrlsWithPagination:
    def test_pagination_none_uses_fetch_page(self) -> None:
        """_collect_article_urls must call fetch_page (not fetch_page_with_pagination) when pagination='none'."""
        config = _make_web_config(pagination="none")
        mock_crawler = MagicMock(spec=WebCrawler)
        mock_crawler.fetch_page.return_value = _make_page_result(
            url="https://example.com/blog/",
            html=_INDEX_HTML_WITH_LINKS,
        )

        result = _collect_article_urls(
            crawler=mock_crawler,
            url="https://example.com/blog/",
            include_patterns=[],
            exclude_patterns=[],
            remaining_depth=1,
            visited={"https://example.com/blog/"},
            config=config,
        )

        mock_crawler.fetch_page.assert_called_once_with("https://example.com/blog/")
        mock_crawler.fetch_page_with_pagination.assert_not_called()
        assert "https://example.com/blog/post-one" in result
        assert "https://example.com/blog/post-two" in result

    def test_pagination_scroll_uses_fetch_page_with_pagination(self) -> None:
        """_collect_article_urls must call fetch_page_with_pagination when pagination='scroll'."""
        config = _make_web_config(pagination="scroll")
        mock_crawler = MagicMock(spec=WebCrawler)
        mock_crawler.fetch_page_with_pagination.return_value = _make_page_result(
            url="https://example.com/blog/",
            html=_INDEX_HTML_WITH_LINKS,
        )

        result = _collect_article_urls(
            crawler=mock_crawler,
            url="https://example.com/blog/",
            include_patterns=[],
            exclude_patterns=[],
            remaining_depth=1,
            visited={"https://example.com/blog/"},
            config=config,
        )

        mock_crawler.fetch_page_with_pagination.assert_called_once_with("https://example.com/blog/")
        mock_crawler.fetch_page.assert_not_called()
        assert "https://example.com/blog/post-one" in result
        assert "https://example.com/blog/post-two" in result

    def test_pagination_click_uses_fetch_page_with_pagination(self) -> None:
        """_collect_article_urls must call fetch_page_with_pagination when pagination='click'."""
        config = _make_web_config(pagination="click", pagination_selector="button.load-more")
        mock_crawler = MagicMock(spec=WebCrawler)
        mock_crawler.fetch_page_with_pagination.return_value = _make_page_result(
            url="https://example.com/blog/",
            html=_INDEX_HTML_WITH_LINKS,
        )

        _collect_article_urls(
            crawler=mock_crawler,
            url="https://example.com/blog/",
            include_patterns=[],
            exclude_patterns=[],
            remaining_depth=1,
            visited={"https://example.com/blog/"},
            config=config,
        )

        mock_crawler.fetch_page_with_pagination.assert_called_once_with("https://example.com/blog/")
        mock_crawler.fetch_page.assert_not_called()

    def test_no_config_uses_fetch_page(self) -> None:
        """_collect_article_urls must call fetch_page when no config is provided (backward compat)."""
        mock_crawler = MagicMock(spec=WebCrawler)
        mock_crawler.fetch_page.return_value = _make_page_result(
            url="https://example.com/blog/",
            html=_INDEX_HTML_WITH_LINKS,
        )

        _collect_article_urls(
            crawler=mock_crawler,
            url="https://example.com/blog/",
            include_patterns=[],
            exclude_patterns=[],
            remaining_depth=1,
            visited={"https://example.com/blog/"},
            config=None,
        )

        mock_crawler.fetch_page.assert_called_once_with("https://example.com/blog/")
        mock_crawler.fetch_page_with_pagination.assert_not_called()

    def test_depth_zero_skips_fetch_regardless_of_pagination(self) -> None:
        """At remaining_depth=0 the URL is returned directly and no fetch is attempted."""
        config = _make_web_config(pagination="scroll")
        mock_crawler = MagicMock(spec=WebCrawler)

        result = _collect_article_urls(
            crawler=mock_crawler,
            url="https://example.com/blog/post-one",
            include_patterns=[],
            exclude_patterns=[],
            remaining_depth=0,
            visited=set(),
            config=config,
        )

        mock_crawler.fetch_page.assert_not_called()
        mock_crawler.fetch_page_with_pagination.assert_not_called()
        assert result == ["https://example.com/blog/post-one"]
