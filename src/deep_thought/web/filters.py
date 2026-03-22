"""URL filtering and internal link extraction for the web crawl tool.

Provides regex-based URL allow/deny filtering and HTML link extraction
using the standard library HTMLParser, keeping external dependencies minimal.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

# ---------------------------------------------------------------------------
# URL pattern matching
# ---------------------------------------------------------------------------


def matches_any_pattern(url: str, patterns: list[str]) -> bool:
    """Return True if url matches any of the provided regex patterns.

    Each pattern string is compiled fresh; this function is intentionally
    simple and does not cache compiled patterns.

    Args:
        url: The URL string to test.
        patterns: List of regex pattern strings.

    Returns:
        True if at least one pattern fully or partially matches url.
    """
    for pattern_text in patterns:
        compiled_pattern = re.compile(pattern_text)
        if compiled_pattern.search(url):
            return True
    return False


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
