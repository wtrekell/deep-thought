"""URL filtering and internal link extraction for the web crawl tool.

Provides regex-based URL allow/deny filtering and HTML link extraction
using the standard library HTMLParser, keeping external dependencies minimal.
"""

from __future__ import annotations

import logging
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# URL pattern matching
# ---------------------------------------------------------------------------


def compile_patterns(pattern_strings: list[str]) -> list[re.Pattern[str]]:
    """Pre-compile a list of regex pattern strings into compiled pattern objects.

    Invalid patterns are skipped with a warning so a single bad pattern does
    not prevent the remaining patterns from being applied.

    Args:
        pattern_strings: List of regex pattern strings.

    Returns:
        List of compiled re.Pattern objects (one per valid input string).
    """
    compiled: list[re.Pattern[str]] = []
    for pattern_text in pattern_strings:
        try:
            compiled.append(re.compile(pattern_text))
        except re.error:
            logger.warning("Skipping invalid regex pattern: %r", pattern_text)
    return compiled


def matches_any_compiled_pattern(url: str, compiled_patterns: list[re.Pattern[str]]) -> bool:
    """Return True if url matches any of the provided pre-compiled patterns.

    Args:
        url: The URL string to test.
        compiled_patterns: List of pre-compiled re.Pattern objects.

    Returns:
        True if at least one pattern partially matches url.
    """
    return any(pattern.search(url) for pattern in compiled_patterns)


def matches_any_pattern(url: str, patterns: list[str]) -> bool:
    """Return True if url matches any of the provided regex patterns.

    Compiles patterns on every call. For hot paths where the same pattern
    list is tested against many URLs, prefer ``compile_patterns()`` once
    and then ``matches_any_compiled_pattern()`` per URL.

    Args:
        url: The URL string to test.
        patterns: List of regex pattern strings.

    Returns:
        True if at least one pattern fully or partially matches url.
    """
    compiled_patterns = compile_patterns(patterns)
    return matches_any_compiled_pattern(url, compiled_patterns)


def is_url_allowed(url: str, include_patterns: list[str], exclude_patterns: list[str]) -> bool:
    """Return True if url passes the include/exclude filter rules.

    Rules applied in order:
    1. If include_patterns is non-empty, the URL must match at least one.
    2. The URL must not match any exclude pattern.

    Args:
        url: The URL string to test.
        include_patterns: Regex patterns the URL must match at least one of (if non-empty).
        exclude_patterns: Regex patterns the URL must not match any of.

    Returns:
        True if the URL is allowed; False if it should be skipped.
    """
    if include_patterns and not matches_any_pattern(url, include_patterns):
        return False

    return not matches_any_pattern(url, exclude_patterns)


def is_same_domain(url: str, root_url: str) -> bool:
    """Return True if url shares the same domain as root_url.

    Leading 'www.' is stripped from both netloc values before comparing so
    that 'www.example.com' and 'example.com' are treated as the same domain.

    Args:
        url: The URL to test.
        root_url: The root/reference URL to compare against.

    Returns:
        True if both URLs belong to the same normalised domain.
    """
    url_netloc = urlparse(url).netloc.lower().removeprefix("www.")
    root_netloc = urlparse(root_url).netloc.lower().removeprefix("www.")
    return url_netloc == root_netloc


# ---------------------------------------------------------------------------
# HTML link extraction
# ---------------------------------------------------------------------------


class _LinkParser(HTMLParser):
    """Minimal HTMLParser subclass that collects href attributes from <a> tags."""

    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Collect href attribute values from anchor tags.

        Args:
            tag: The HTML tag name.
            attrs: List of (name, value) attribute pairs for the tag.
        """
        if tag.lower() == "a":
            for attr_name, attr_value in attrs:
                if attr_name.lower() == "href" and attr_value:
                    self.hrefs.append(attr_value)


def extract_internal_links(html: str, root_url: str) -> list[str]:
    """Extract all internal links from an HTML document.

    Finds all <a href> tags, resolves relative URLs against root_url,
    filters to links that share the same domain as root_url, deduplicates,
    and returns a sorted list.

    Known limitation: query strings (e.g. ``?utm_source=nav``) are preserved
    in extracted URLs. Tracking parameters can therefore create duplicate page
    fetches. Use ``exclude_patterns`` in the config to filter out known
    tracking parameter patterns if this causes problems.

    Args:
        html: Raw HTML content of the page.
        root_url: The URL of the page being parsed; used to resolve relative links
                  and determine domain membership.

    Returns:
        Sorted, deduplicated list of absolute URLs on the same domain.
    """
    parser = _LinkParser()
    parser.feed(html)

    resolved_urls: set[str] = set()
    for raw_href in parser.hrefs:
        absolute_url = urljoin(root_url, raw_href)
        # Strip fragments — we only want the page itself
        parsed = urlparse(absolute_url)
        clean_url = parsed._replace(fragment="").geturl()
        if is_same_domain(clean_url, root_url):
            resolved_urls.add(clean_url)

    return sorted(resolved_urls)
