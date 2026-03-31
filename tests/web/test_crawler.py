"""Tests for crawler.py: WebCrawler context manager, retry logic, and stealth mode.

All tests mock Playwright at the sync_playwright level to avoid launching real
browsers and keep tests fast.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from deep_thought.web.crawler import CrawlerConfig, PageResult, WebCrawler

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_crawler_config(
    js_wait: float = 0.0,
    retry_attempts: int = 0,
    retry_delay: float = 0.0,
    stealth: bool = False,
    headless: bool = True,
    browser_channel: str | None = None,
    pagination: str = "none",
    pagination_selector: str | None = None,
    pagination_wait: float = 0.0,
    max_paginations: int = 0,
) -> CrawlerConfig:
    """Build a minimal CrawlerConfig for testing."""
    return CrawlerConfig(
        js_wait=js_wait,
        browser_channel=browser_channel,
        stealth=stealth,
        headless=headless,
        retry_attempts=retry_attempts,
        retry_delay=retry_delay,
        pagination=pagination,
        pagination_selector=pagination_selector,
        pagination_wait=pagination_wait,
        max_paginations=max_paginations,
    )


def _make_mock_playwright_stack() -> tuple[Any, Any, Any, Any]:
    """Build a layered mock that models sync_playwright → browser → context → page.

    Returns:
        Tuple of (mock_playwright_cm, mock_playwright, mock_browser, mock_page)
        where mock_playwright_cm is the value returned by sync_playwright().
    """
    mock_page = MagicMock()
    mock_page.title.return_value = "Test Page"
    mock_page.content.return_value = "<html><body>content</body></html>"
    mock_page.goto.return_value = MagicMock(status=200)

    mock_context = MagicMock()
    mock_context.new_page.return_value = mock_page

    mock_browser = MagicMock()
    mock_browser.new_context.return_value = mock_context

    mock_playwright = MagicMock()
    mock_playwright.chromium.launch.return_value = mock_browser

    mock_playwright_cm = MagicMock()
    mock_playwright_cm.__enter__ = MagicMock(return_value=mock_playwright)
    mock_playwright_cm.__exit__ = MagicMock(return_value=False)

    return mock_playwright_cm, mock_playwright, mock_browser, mock_page


# ---------------------------------------------------------------------------
# TestWebCrawlerContextManager
# ---------------------------------------------------------------------------


class TestWebCrawlerContextManager:
    """Tests for WebCrawler.__enter__ / __exit__ lifecycle."""

    def test_playwright_not_started_before_entering_context(self) -> None:
        """Playwright must not be started when WebCrawler is instantiated without entering the context."""
        mock_playwright_cm, mock_playwright, _mock_browser, _mock_page = _make_mock_playwright_stack()

        with patch("deep_thought.web.crawler.sync_playwright", return_value=mock_playwright_cm):
            _crawler = WebCrawler(_make_crawler_config())

        # __enter__ was NOT called on the playwright context manager
        mock_playwright_cm.__enter__.assert_not_called()

    def test_context_manager_starts_and_stops_playwright(self) -> None:
        """Using WebCrawler as a context manager must start Playwright on entry and stop it on exit."""
        mock_playwright_cm, _mock_playwright, _mock_browser, _mock_page = _make_mock_playwright_stack()

        with (
            patch("deep_thought.web.crawler.sync_playwright", return_value=mock_playwright_cm),
            WebCrawler(_make_crawler_config()),
        ):
            pass

        mock_playwright_cm.__enter__.assert_called_once()
        mock_playwright_cm.__exit__.assert_called_once()

    def test_context_manager_launches_and_closes_browser(self) -> None:
        """Entering the context manager must launch a browser; exiting must close it."""
        mock_playwright_cm, mock_playwright, mock_browser, _mock_page = _make_mock_playwright_stack()

        with (
            patch("deep_thought.web.crawler.sync_playwright", return_value=mock_playwright_cm),
            WebCrawler(_make_crawler_config()),
        ):
            pass

        mock_playwright.chromium.launch.assert_called_once()
        mock_browser.close.assert_called_once()

    def test_fetch_page_raises_when_not_in_context(self) -> None:
        """Calling fetch_page outside a context manager must raise RuntimeError."""
        mock_playwright_cm, _mock_playwright, _mock_browser, _mock_page = _make_mock_playwright_stack()

        with patch("deep_thought.web.crawler.sync_playwright", return_value=mock_playwright_cm):
            crawler = WebCrawler(_make_crawler_config())
            with pytest.raises(RuntimeError, match="context manager"):
                crawler.fetch_page("https://example.com/")

    def test_browser_channel_passed_to_playwright(self) -> None:
        """When browser_channel is set, it must be passed to chromium.launch()."""
        mock_playwright_cm, mock_playwright, _mock_browser, _mock_page = _make_mock_playwright_stack()

        with (
            patch("deep_thought.web.crawler.sync_playwright", return_value=mock_playwright_cm),
            WebCrawler(_make_crawler_config(browser_channel="chrome")),
        ):
            pass

        call_kwargs = mock_playwright.chromium.launch.call_args.kwargs
        assert call_kwargs.get("channel") == "chrome"


# ---------------------------------------------------------------------------
# TestFetchPage
# ---------------------------------------------------------------------------


class TestFetchPage:
    """Tests for WebCrawler.fetch_page."""

    def test_fetch_page_returns_page_result(self) -> None:
        """fetch_page must return a PageResult with the page's URL, HTML, and status code."""
        mock_playwright_cm, _mock_playwright, _mock_browser, _mock_page = _make_mock_playwright_stack()

        with (
            patch("deep_thought.web.crawler.sync_playwright", return_value=mock_playwright_cm),
            WebCrawler(_make_crawler_config()) as crawler,
        ):
            result = crawler.fetch_page("https://example.com/")

        assert isinstance(result, PageResult)
        assert result.url == "https://example.com/"
        assert result.status_code == 200
        assert "<html>" in result.html

    def test_fetch_page_title_from_playwright(self) -> None:
        """fetch_page must capture the page title reported by Playwright."""
        mock_playwright_cm, _mock_playwright, _mock_browser, mock_page = _make_mock_playwright_stack()
        mock_page.title.return_value = "My Page Title"

        with (
            patch("deep_thought.web.crawler.sync_playwright", return_value=mock_playwright_cm),
            WebCrawler(_make_crawler_config()) as crawler,
        ):
            result = crawler.fetch_page("https://example.com/")

        assert result.title == "My Page Title"

    def test_fetch_page_returns_none_title_for_empty_string(self) -> None:
        """A Playwright page.title() returning '' must be converted to None in PageResult."""
        mock_playwright_cm, _mock_playwright, _mock_browser, mock_page = _make_mock_playwright_stack()
        mock_page.title.return_value = ""

        with (
            patch("deep_thought.web.crawler.sync_playwright", return_value=mock_playwright_cm),
            WebCrawler(_make_crawler_config()) as crawler,
        ):
            result = crawler.fetch_page("https://example.com/")

        assert result.title is None

    def test_retries_on_playwright_error(self) -> None:
        """fetch_page must retry on PlaywrightError up to retry_attempts times."""
        from playwright.sync_api import Error as PlaywrightError

        mock_playwright_cm, _mock_playwright, _mock_browser, mock_page = _make_mock_playwright_stack()
        # Fail once, then succeed
        mock_page.goto.side_effect = [PlaywrightError("Network error"), MagicMock(status=200)]

        with (
            patch("deep_thought.web.crawler.sync_playwright", return_value=mock_playwright_cm),
            patch("deep_thought.web.crawler.time.sleep"),  # suppress retry delay
            WebCrawler(_make_crawler_config(retry_attempts=1)) as crawler,
        ):
            result = crawler.fetch_page("https://example.com/")

        assert result.status_code == 200

    def test_raises_after_all_retries_exhausted(self) -> None:
        """fetch_page must raise after all retry attempts are exhausted."""
        from playwright.sync_api import Error as PlaywrightError

        mock_playwright_cm, _mock_playwright, _mock_browser, mock_page = _make_mock_playwright_stack()
        mock_page.goto.side_effect = PlaywrightError("Persistent error")

        with (
            patch("deep_thought.web.crawler.sync_playwright", return_value=mock_playwright_cm),
            patch("deep_thought.web.crawler.time.sleep"),
            pytest.raises(PlaywrightError),
            WebCrawler(_make_crawler_config(retry_attempts=1)) as crawler,
        ):
            crawler.fetch_page("https://example.com/")


# ---------------------------------------------------------------------------
# TestStealthMode
# ---------------------------------------------------------------------------


class TestStealthMode:
    """Tests for stealth mode configuration."""

    def test_stealth_sets_user_agent_on_context(self) -> None:
        """In stealth mode, new_context() must be called with a user_agent argument."""
        mock_playwright_cm, _mock_playwright, mock_browser, _mock_page = _make_mock_playwright_stack()

        with (
            patch("deep_thought.web.crawler.sync_playwright", return_value=mock_playwright_cm),
            WebCrawler(_make_crawler_config(stealth=True)) as crawler,
        ):
            crawler.fetch_page("https://example.com/")

        call_kwargs = mock_browser.new_context.call_args.kwargs
        assert "user_agent" in call_kwargs
        assert call_kwargs["user_agent"]  # non-empty string

    def test_stealth_sets_viewport_on_context(self) -> None:
        """In stealth mode, new_context() must be called with a viewport argument."""
        mock_playwright_cm, _mock_playwright, mock_browser, _mock_page = _make_mock_playwright_stack()

        with (
            patch("deep_thought.web.crawler.sync_playwright", return_value=mock_playwright_cm),
            WebCrawler(_make_crawler_config(stealth=True)) as crawler,
        ):
            crawler.fetch_page("https://example.com/")

        call_kwargs = mock_browser.new_context.call_args.kwargs
        assert "viewport" in call_kwargs
        viewport = call_kwargs["viewport"]
        assert "width" in viewport and "height" in viewport

    def test_non_stealth_uses_default_context(self) -> None:
        """When stealth=False, new_context() must be called without user_agent or viewport."""
        mock_playwright_cm, _mock_playwright, mock_browser, _mock_page = _make_mock_playwright_stack()

        with (
            patch("deep_thought.web.crawler.sync_playwright", return_value=mock_playwright_cm),
            WebCrawler(_make_crawler_config(stealth=False)) as crawler,
        ):
            crawler.fetch_page("https://example.com/")

        call_kwargs = mock_browser.new_context.call_args.kwargs
        assert "user_agent" not in call_kwargs


# ---------------------------------------------------------------------------
# TestPaginationFetch
# ---------------------------------------------------------------------------


class TestPaginationFetch:
    """Tests for fetch_page_with_pagination."""

    def test_no_pagination_delegates_to_fetch_page(self) -> None:
        """When pagination='none', fetch_page_with_pagination must behave like fetch_page."""
        mock_playwright_cm, _mock_playwright, _mock_browser, _mock_page = _make_mock_playwright_stack()

        with (
            patch("deep_thought.web.crawler.sync_playwright", return_value=mock_playwright_cm),
            WebCrawler(_make_crawler_config(pagination="none")) as crawler,
        ):
            result = crawler.fetch_page_with_pagination("https://example.com/")

        assert isinstance(result, PageResult)
        assert result.url == "https://example.com/"

    def test_scroll_pagination_calls_scroll_javascript(self) -> None:
        """Scroll pagination must call window.scrollTo via page.evaluate."""
        mock_playwright_cm, _mock_playwright, _mock_browser, mock_page = _make_mock_playwright_stack()
        # The scroll loop evaluates: (1) document.body.scrollHeight before scroll,
        # (2) window.scrollTo (fire-and-forget), (3) document.body.scrollHeight after.
        # Returning the same height on the before/after checks stops the loop after
        # the first iteration. Provide a fixed return value so the mock never runs dry.
        mock_page.evaluate.return_value = 1000  # height never grows → stops after first scroll

        with (
            patch("deep_thought.web.crawler.sync_playwright", return_value=mock_playwright_cm),
            WebCrawler(_make_crawler_config(pagination="scroll", max_paginations=3)) as crawler,
        ):
            result = crawler.fetch_page_with_pagination("https://example.com/")

        assert isinstance(result, PageResult)
        # evaluate must have been called at least once for scroll height check
        assert mock_page.evaluate.called
