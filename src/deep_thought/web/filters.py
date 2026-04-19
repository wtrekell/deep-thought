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
# URL canonicalization and sanity gate
# ---------------------------------------------------------------------------

# Path segments containing square brackets (raw or percent-encoded) usually
# indicate markdown-link corruption in the extracted href — e.g. an encoded
# "[text](url)" leaking into the path. These URLs are never legitimate pages
# on the source site, and fetching them only wastes quota.
_MARKDOWN_LINK_CORRUPTION_TOKENS = ("%5B", "%5D", "%5b", "%5d", "[", "]")


def canonicalize_url(url: str) -> str:
    """Return a canonical form of url for dedup and queue comparisons.

    Applies a small, conservative set of normalizations:

    - Folds a leading ``www.`` in the netloc to its apex (``www.example.com``
      → ``example.com``) so the two spellings don't produce duplicate rows.
    - Lowercases the scheme and netloc (both are case-insensitive per RFC 3986).
    - Strips a trailing slash from non-root paths (``/foo/`` → ``/foo``), but
      leaves ``/`` on root URLs alone so ``https://example.com/`` stays valid.

    Query string, fragment, path case, and percent-encoding are preserved —
    those can be semantically significant and changing them risks breaking
    legitimate distinct URLs.

    Args:
        url: The URL to canonicalize. May be any absolute URL.

    Returns:
        A canonicalized URL string. Returns ``url`` unchanged if it can't be
        parsed (e.g. malformed input) — callers decide how to handle that.
    """
    try:
        parsed = urlparse(url)
    except ValueError:
        return url

    netloc = parsed.netloc.lower().removeprefix("www.")
    scheme = parsed.scheme.lower()

    path = parsed.path
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/") or "/"

    return parsed._replace(scheme=scheme, netloc=netloc, path=path).geturl()


def has_markdown_link_corruption(url: str) -> bool:
    """Return True if url contains markdown-link corruption in its path.

    Detects path segments holding the raw or percent-encoded square brackets
    of a markdown ``[text](url)`` form, which indicates the link extractor
    mis-parsed an already-converted markdown fragment and treated the
    ``[...](...)`` as a URL path segment. These should never enter the crawl
    queue — the target site always 404s on them.

    Args:
        url: The URL to test.

    Returns:
        True if the URL's path appears to contain markdown-link debris.
    """
    try:
        parsed = urlparse(url)
    except ValueError:
        return False

    path_and_query = parsed.path + ("?" + parsed.query if parsed.query else "")
    return any(token in path_and_query for token in _MARKDOWN_LINK_CORRUPTION_TOKENS)


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
    filters to links that share the same domain as root_url, canonicalizes
    each URL (folding ``www.`` to apex and stripping trailing slashes from
    non-root paths), drops URLs whose path contains markdown-link corruption
    (``[...](...)`` debris), deduplicates, and returns a sorted list.

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
        if not is_same_domain(clean_url, root_url):
            continue
        if has_markdown_link_corruption(clean_url):
            logger.warning(
                "Dropping link with markdown-link corruption in path: %s (source page: %s)",
                clean_url,
                root_url,
            )
            continue
        resolved_urls.add(canonicalize_url(clean_url))

    return sorted(resolved_urls)
