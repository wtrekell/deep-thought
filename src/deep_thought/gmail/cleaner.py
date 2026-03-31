"""Newsletter HTML cleaning for the Gmail Tool.

Strips tracking pixels, scripts, social buttons, and other non-content
elements from newsletter HTML before converting to markdown text.
"""

from __future__ import annotations

import re

import html2text

# ---------------------------------------------------------------------------
# HTML cleaning functions
# ---------------------------------------------------------------------------


def _attr_value_is_one(value: str) -> bool:
    """Return True if the attribute value represents the number 1.

    Handles quoted values ('1', "1"), unquoted 1, and numerically-equal
    strings like "01" or "0001".

    Args:
        value: The raw attribute value string (may include surrounding quotes).

    Returns:
        True if the value represents the integer 1.
    """
    stripped = value.strip("\"' \t")
    try:
        return int(stripped) == 1
    except ValueError:
        return False


def _remove_tracking_pixels(html: str) -> str:
    """Remove 1x1 tracking pixel images from HTML.

    Uses a simple scan over <img> tags so it handles single quotes, unquoted
    attribute values, and numeric strings like "01" that a pure regex would
    miss.

    Args:
        html: Raw HTML string.

    Returns:
        HTML with tracking pixel images removed.
    """

    # Pass 1: remove img tags where width AND/OR height indicate 1 pixel
    def _strip_if_pixel(match: re.Match[str]) -> str:
        """Return empty string if the matched img tag is a 1×1 pixel, else return it."""
        tag_text = match.group(0)

        width_match = re.search(r'width\s*=\s*(["\']?[0-9]+["\']?)', tag_text, re.IGNORECASE)
        height_match = re.search(r'height\s*=\s*(["\']?[0-9]+["\']?)', tag_text, re.IGNORECASE)

        width_is_one = _attr_value_is_one(width_match.group(1)) if width_match else False
        height_is_one = _attr_value_is_one(height_match.group(1)) if height_match else False

        if width_is_one and height_is_one:
            return ""
        return tag_text

    html = re.sub(r"<img[^>]*/?>", _strip_if_pixel, html, flags=re.IGNORECASE)

    # Pass 2: match common tracking keywords in src URLs regardless of quote style
    html = re.sub(
        r'<img[^>]*src\s*=\s*["\']?[^"\'>\s]*(?:track|pixel|open|beacon|click)[^"\'>\s]*["\']?[^>]*/?>',
        "",
        html,
        flags=re.IGNORECASE,
    )
    return html


def _remove_script_tags(html: str) -> str:
    """Remove all <script> tags and their content.

    Args:
        html: Raw HTML string.

    Returns:
        HTML with script tags and content removed.
    """
    return re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)


def _remove_style_tags(html: str) -> str:
    """Remove all <style> tags and their content.

    Args:
        html: Raw HTML string.

    Returns:
        HTML with style tags and content removed.
    """
    return re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)


def _remove_social_buttons(html: str) -> str:
    """Remove common social media sharing buttons and sections.

    Targets elements with common social sharing class names and link patterns.

    Args:
        html: Raw HTML string.

    Returns:
        HTML with social button sections removed.
    """
    # Remove elements with social-related class names
    html = re.sub(
        r'<(?:div|table|tr|td|a|span)[^>]*class\s*=\s*["\'][^"\']*'
        r"(?:social|share|follow-us|social-links)[^\"']*[\"'][^>]*>.*?</(?:div|table|tr|td|a|span)>",
        "",
        html,
        flags=re.DOTALL | re.IGNORECASE,
    )
    return html


def _remove_unsubscribe_sections(html: str) -> str:
    """Remove unsubscribe links and surrounding footer text.

    Args:
        html: Raw HTML string.

    Returns:
        HTML with unsubscribe sections removed.
    """
    # Remove elements containing "unsubscribe" links
    html = re.sub(
        r"<(?:div|p|td|span)[^>]*>[^<]*<a[^>]*>[^<]*(?:unsubscribe|opt.out|manage.preferences)[^<]*</a>[^<]*"
        r"</(?:div|p|td|span)>",
        "",
        html,
        flags=re.DOTALL | re.IGNORECASE,
    )
    return html


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def clean_newsletter_html(html_content: str) -> str:
    """Strip non-content elements from newsletter HTML and convert to markdown.

    Removes tracking pixels, scripts, styles, social buttons, and unsubscribe
    sections, then converts the cleaned HTML to markdown text using html2text.

    Args:
        html_content: Raw newsletter HTML string.

    Returns:
        Cleaned markdown text.
    """
    cleaned = html_content
    cleaned = _remove_script_tags(cleaned)
    cleaned = _remove_style_tags(cleaned)
    cleaned = _remove_tracking_pixels(cleaned)
    cleaned = _remove_social_buttons(cleaned)
    cleaned = _remove_unsubscribe_sections(cleaned)

    converter = html2text.HTML2Text()
    converter.body_width = 0  # No line wrapping
    converter.ignore_links = False
    converter.ignore_images = True  # Skip newsletter images
    converter.ignore_emphasis = False
    converter.protect_links = True
    converter.wrap_links = False

    markdown_text: str = converter.handle(cleaned)
    return markdown_text.strip()
