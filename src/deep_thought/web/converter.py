"""HTML to markdown conversion for the web crawl tool.

Converts raw HTML page content to clean markdown text suitable for LLM
consumption. Uses html2text for the core conversion and standard library
HTMLParser for title extraction.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

import html2text

# ---------------------------------------------------------------------------
# Title extraction
# ---------------------------------------------------------------------------


class _TitleParser(HTMLParser):
    """Minimal HTMLParser subclass that captures text inside <title> tags."""

    def __init__(self) -> None:
        super().__init__()
        self._in_title_tag: bool = False
        self._captured_title: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Mark entry into a <title> tag.

        Args:
            tag: The HTML tag name.
            attrs: List of (name, value) attribute pairs (unused for title).
        """
        if tag.lower() == "title":
            self._in_title_tag = True

    def handle_endtag(self, tag: str) -> None:
        """Mark exit from a <title> tag.

        Args:
            tag: The HTML tag name.
        """
        if tag.lower() == "title":
            self._in_title_tag = False

    def handle_data(self, data: str) -> None:
        """Capture text content when inside a <title> tag.

        Args:
            data: Text content found in the current parse position.
        """
        if self._in_title_tag and self._captured_title is None:
            stripped_data = data.strip()
            if stripped_data:
                self._captured_title = stripped_data

    @property
    def title(self) -> str | None:
        """Return the captured title text, or None if no title was found."""
        return self._captured_title


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def extract_title(html: str) -> str | None:
    """Extract the page title from the <title> tag in HTML.

    Args:
        html: Raw HTML content.

    Returns:
        The text content of the first <title> tag found, or None if absent.
    """
    parser = _TitleParser()
    parser.feed(html)
    return parser.title


def convert_html_to_markdown(html: str, base_url: str = "") -> str:
    """Convert HTML content to clean markdown text.

    Configures html2text for LLM-optimised output: links are preserved,
    images are ignored, line wrapping is disabled, and unicode characters
    are passed through without escaping.

    Args:
        html: Raw HTML content to convert.
        base_url: Optional base URL used to resolve relative links in the HTML.

    Returns:
        Stripped markdown text converted from the input HTML.
    """
    converter = html2text.HTML2Text()
    converter.ignore_links = False
    converter.ignore_images = True
    converter.body_width = 0
    converter.protect_links = False
    converter.unicode_snob = True

    if base_url:
        converter.baseurl = base_url

    raw_markdown: str = str(converter.handle(html))
    normalized_markdown = re.sub(r"\n{3,}", "\n\n", raw_markdown)
    return normalized_markdown.strip()


def apply_boilerplate_patterns(markdown_text: str, patterns: list[str]) -> str:
    """Remove boilerplate sections from markdown text using regex patterns.

    Each pattern is applied as a regex substitution against the full markdown
    text.  Patterns use ``re.DOTALL`` so ``.`` matches newlines, allowing
    multi-line blocks (navigation menus, footers) to be matched.

    Args:
        markdown_text: The converted markdown to clean.
        patterns: A list of regex pattern strings.  Empty list = no-op.

    Returns:
        The markdown text with all pattern matches removed and whitespace
        normalised (no runs of three or more consecutive newlines).
    """
    if not patterns:
        return markdown_text

    cleaned_text = markdown_text
    for pattern in patterns:
        cleaned_text = re.sub(pattern, "", cleaned_text, flags=re.DOTALL)

    cleaned_text = re.sub(r"\n{3,}", "\n\n", cleaned_text)
    return cleaned_text.strip()


def count_words(markdown_text: str) -> int:
    """Return an approximate word count for a markdown string.

    Splits on whitespace and counts non-empty tokens.

    Args:
        markdown_text: Any string, typically the body of converted markdown.

    Returns:
        Number of whitespace-separated, non-empty tokens in markdown_text.
    """
    return len([token for token in markdown_text.split() if token])
