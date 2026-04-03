"""Playwright-based web page fetcher for the web crawl tool.

Uses Playwright's synchronous API to render JavaScript-heavy pages and
extract their final HTML, title, and HTTP status code. Supports retry
logic and optional stealth mode to reduce bot-detection fingerprinting.
"""

from __future__ import annotations

import contextlib
import logging
import random
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from playwright.sync_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    sync_playwright,
)
from playwright.sync_api import Error as PlaywrightError

if TYPE_CHECKING:
    from types import TracebackType

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class PageResult:
    """Represents the fetched content of a single web page."""

    url: str
    html: str
    status_code: int
    title: str | None


@dataclass
class CrawlerConfig:
    """Configuration for the WebCrawler."""

    js_wait: float
    browser_channel: str | None
    stealth: bool
    headless: bool
    retry_attempts: int
    retry_delay: float
    pagination: str
    pagination_selector: str | None
    pagination_wait: float
    max_paginations: int


# ---------------------------------------------------------------------------
# Stealth helpers
# ---------------------------------------------------------------------------

_STEALTH_USER_AGENTS: list[str] = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",  # noqa: E501
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_2_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",  # noqa: E501
]


# ---------------------------------------------------------------------------
# WebCrawler
# ---------------------------------------------------------------------------


class WebCrawler:
    """Playwright-based synchronous web crawler.

    Designed to be used as a context manager. The browser is launched on
    entry and closed on exit.

    Example::

        with WebCrawler(config) as crawler:
            result = crawler.fetch_page("https://example.com")
    """

    def __init__(self, config: CrawlerConfig) -> None:
        """Initialise the crawler with the provided configuration.

        Playwright is not started here; it is started lazily in __enter__ to
        avoid leaking a subprocess when the crawler is never used as a context
        manager.

        Args:
            config: CrawlerConfig specifying rendering, stealth, and retry settings.
        """
        self._config = config
        self._playwright_cm: Any = sync_playwright()
        self._playwright_instance: Playwright | None = None
        self._browser: Browser | None = None

    def __enter__(self) -> WebCrawler:
        """Start Playwright, launch the browser, and return this crawler instance.

        Returns:
            This WebCrawler instance, ready to fetch pages.
        """
        self._playwright_instance = self._playwright_cm.__enter__()

        stealth_args = ["--disable-blink-features=AutomationControlled"] if self._config.stealth else []
        if self._config.browser_channel is not None:
            self._browser = self._playwright_instance.chromium.launch(
                channel=self._config.browser_channel,
                headless=self._config.headless,
                args=stealth_args,
            )
        else:
            self._browser = self._playwright_instance.chromium.launch(
                headless=self._config.headless,
                args=stealth_args,
            )
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Close the browser and stop playwright.

        Args:
            exc_type: Exception type, if any.
            exc_val: Exception value, if any.
            exc_tb: Exception traceback, if any.
        """
        if self._browser is not None:
            self._browser.close()
        self._playwright_cm.__exit__(exc_type, exc_val, exc_tb)

    def fetch_page(self, url: str) -> PageResult:
        """Fetch a web page and return its content.

        Navigates to url, waits for network idle, applies an additional
        js_wait delay, then extracts the HTML, title, and HTTP status.
        Retries on PlaywrightError or ConnectionError up to retry_attempts times.

        Args:
            url: The URL to fetch.

        Returns:
            A PageResult containing the HTML, status code, and title.

        Raises:
            PlaywrightError: If all retry attempts are exhausted.
            ConnectionError: If a connection error persists after all retries.
        """
        if self._browser is None:
            raise RuntimeError("WebCrawler must be used as a context manager before calling fetch_page.")

        last_exception: Exception | None = None

        for attempt_number in range(self._config.retry_attempts + 1):
            if attempt_number > 0:
                time.sleep(self._config.retry_delay)

            try:
                if self._config.stealth:
                    selected_user_agent = random.choice(_STEALTH_USER_AGENTS)
                    viewport_width = random.randint(1024, 1920)
                    viewport_height = random.randint(768, 1080)
                    context: BrowserContext = self._browser.new_context(
                        user_agent=selected_user_agent,
                        viewport={"width": viewport_width, "height": viewport_height},
                    )
                else:
                    context = self._browser.new_context()

                page: Page = context.new_page()

                if self._config.stealth:
                    page.add_init_script('Object.defineProperty(navigator, "webdriver", {get: () => undefined})')

                try:
                    wait_strategy: Literal["networkidle", "domcontentloaded"] = (
                        "domcontentloaded" if self._config.js_wait < 2.0 else "networkidle"
                    )
                    response = page.goto(url, wait_until=wait_strategy, timeout=60000)
                    page.wait_for_timeout(int(self._config.js_wait * 1000))

                    # Wait for Cloudflare challenge to resolve (up to 30s)
                    cloudflare_wait_elapsed = 0.0
                    cloudflare_poll_interval = 2.0
                    cloudflare_max_wait = 30.0
                    while page.title() == "Just a moment..." and cloudflare_wait_elapsed < cloudflare_max_wait:
                        page.wait_for_timeout(int(cloudflare_poll_interval * 1000))
                        cloudflare_wait_elapsed += cloudflare_poll_interval

                    status_code: int = response.status if response is not None else 0
                    page_title: str | None = page.title() or None
                    html_content: str = page.content()

                    return PageResult(
                        url=url,
                        html=html_content,
                        status_code=status_code,
                        title=page_title,
                    )
                finally:
                    page.close()
                    context.close()

            except (PlaywrightError, ConnectionError) as fetch_error:
                last_exception = fetch_error

        if last_exception is not None:
            raise last_exception

        # This path is unreachable when retry_attempts >= 0, but mypy requires it
        raise RuntimeError(f"Failed to fetch {url} after all retry attempts.")

    def fetch_page_with_pagination(self, url: str) -> PageResult:
        """Fetch a web page and expand it by scrolling or clicking through pagination.

        Delegates to fetch_page() first to obtain the initial render, then
        applies the configured pagination strategy (scroll or click) up to
        max_paginations times. Returns a PageResult whose html reflects the
        fully-expanded page content.

        If no pagination strategy is configured (pagination == "none"), this
        method behaves identically to fetch_page().

        Errors during individual pagination steps are logged as warnings and
        stop the pagination loop early; the HTML accumulated so far is returned.

        Args:
            url: The URL to fetch and paginate.

        Returns:
            A PageResult with the fully-expanded HTML after all pagination is complete.

        Raises:
            PlaywrightError: If the initial page fetch fails after all retries.
            ConnectionError: If a connection error persists after all retries.
        """
        if self._browser is None:
            raise RuntimeError(
                "WebCrawler must be used as a context manager before calling fetch_page_with_pagination."
            )

        if self._config.pagination == "none":
            return self.fetch_page(url)

        if self._config.stealth:
            selected_user_agent = random.choice(_STEALTH_USER_AGENTS)
            viewport_width = random.randint(1024, 1920)
            viewport_height = random.randint(768, 1080)
            context: BrowserContext = self._browser.new_context(
                user_agent=selected_user_agent,
                viewport={"width": viewport_width, "height": viewport_height},
            )
        else:
            context = self._browser.new_context()

        page: Page = context.new_page()

        if self._config.stealth:
            page.add_init_script('Object.defineProperty(navigator, "webdriver", {get: () => undefined})')

        try:
            wait_strategy: Literal["networkidle", "domcontentloaded"] = (
                "domcontentloaded" if self._config.js_wait < 2.0 else "networkidle"
            )
            response = page.goto(url, wait_until=wait_strategy, timeout=60000)
            page.wait_for_timeout(int(self._config.js_wait * 1000))

            # Wait for Cloudflare challenge to resolve (up to 30s)
            cloudflare_wait_elapsed = 0.0
            cloudflare_poll_interval = 2.0
            cloudflare_max_wait = 30.0
            while page.title() == "Just a moment..." and cloudflare_wait_elapsed < cloudflare_max_wait:
                page.wait_for_timeout(int(cloudflare_poll_interval * 1000))
                cloudflare_wait_elapsed += cloudflare_poll_interval

            if self._config.pagination == "scroll":
                self._paginate_by_scroll(page)
            elif self._config.pagination == "click":
                self._paginate_by_click(page)

            status_code: int = response.status if response is not None else 0
            page_title: str | None = page.title() or None
            html_content: str = page.content()

            return PageResult(
                url=url,
                html=html_content,
                status_code=status_code,
                title=page_title,
            )
        finally:
            page.close()
            context.close()

    def _paginate_by_scroll(self, page: Page) -> None:
        """Scroll to the bottom of the page repeatedly to trigger lazy-loaded content.

        After each scroll, waits for network activity to settle and checks whether
        the page height has grown. Stops when the height stops increasing or
        max_paginations iterations are reached.

        Args:
            page: The Playwright Page object to scroll.
        """
        pagination_wait_ms = int(self._config.pagination_wait * 1000)

        for scroll_iteration in range(self._config.max_paginations):
            try:
                previous_scroll_height: int = page.evaluate("document.body.scrollHeight")
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(pagination_wait_ms)

                with contextlib.suppress(PlaywrightError):
                    # networkidle timeout is acceptable — content may still have loaded
                    page.wait_for_load_state("networkidle", timeout=5000)

                current_scroll_height: int = page.evaluate("document.body.scrollHeight")

                if current_scroll_height <= previous_scroll_height:
                    logger.debug(
                        "Scroll pagination stopping at iteration %d: page height did not grow (%d px)",
                        scroll_iteration + 1,
                        current_scroll_height,
                    )
                    break

                logger.debug(
                    "Scroll pagination iteration %d: height grew from %d to %d px",
                    scroll_iteration + 1,
                    previous_scroll_height,
                    current_scroll_height,
                )

            except PlaywrightError as scroll_error:
                logger.warning(
                    "Scroll pagination stopped at iteration %d due to error: %s",
                    scroll_iteration + 1,
                    scroll_error,
                )
                break

    def _paginate_by_click(self, page: Page) -> None:
        """Click the pagination element repeatedly to load more content.

        After each click, waits for network idle. Stops when the selector is no
        longer visible in the DOM or max_paginations iterations are reached.

        Args:
            page: The Playwright Page object to interact with.
        """
        if self._config.pagination_selector is None:
            logger.warning("Click pagination configured but pagination_selector is not set; skipping pagination.")
            return

        selector = self._config.pagination_selector
        pagination_wait_ms = int(self._config.pagination_wait * 1000)

        for click_iteration in range(self._config.max_paginations):
            try:
                button_locator = page.locator(selector)
                is_button_visible = button_locator.is_visible()

                if not is_button_visible:
                    logger.debug(
                        "Click pagination stopping at iteration %d: selector '%s' is no longer visible",
                        click_iteration + 1,
                        selector,
                    )
                    break

                button_locator.click()
                page.wait_for_timeout(pagination_wait_ms)

                with contextlib.suppress(PlaywrightError):
                    # networkidle timeout is acceptable — partial content is still useful
                    page.wait_for_load_state("networkidle", timeout=10000)

                logger.debug("Click pagination iteration %d: clicked '%s'", click_iteration + 1, selector)

            except PlaywrightError as click_error:
                logger.warning(
                    "Click pagination stopped at iteration %d due to error: %s",
                    click_iteration + 1,
                    click_error,
                )
                break
