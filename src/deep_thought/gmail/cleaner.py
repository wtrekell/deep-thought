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


def _remove_tracking_pixels(html: str) -> str:
    """Remove 1x1 tracking pixel images from HTML.

    Matches <img> tags where width and/or height are set to 1.

    Args:
        html: Raw HTML string.

    Returns:
        HTML with tracking pixel images removed.
    """
    # Match img tags with 1x1 dimensions
    html = re.sub(
        r'<img[^>]*(?:width\s*=\s*["\']?1["\']?[^>]*height\s*=\s*["\']?1["\']?'
        r"|height\s*=\s*[\"']?1[\"']?[^>]*width\s*=\s*[\"']?1[\"']?)[^>]*/?>",
        "",
        html,
        flags=re.IGNORECASE,
    )
    # Match common tracking pixel patterns in src URLs
    html = re.sub(
        r'<img[^>]*src\s*=\s*["\'][^"\']*(?:track|pixel|open|beacon|click)[^"\']*["\'][^>]*/?>',
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
