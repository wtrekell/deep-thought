"""Shared utilities for email conversion engines (EML and MSG).

Contains functions used by both eml_engine.py and msg_engine.py to avoid
duplication: HTML-to-markdown conversion, file size formatting, and the
shared markdown builder.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def convert_html_to_markdown(html_content: str) -> str:
    """Convert HTML to markdown using html2text.

    Args:
        html_content: Raw HTML string to convert.

    Returns:
        Markdown string, or the original HTML if conversion fails.

    Raises:
        ImportError: If the html2text library is not installed.
    """
    try:
        import html2text

        converter = html2text.HTML2Text()
        converter.body_width = 0
        converter.protect_links = True
        converter.wrap_links = False
        return converter.handle(html_content).strip()
    except ImportError:
        raise
    except Exception:
        logger.warning("html2text conversion failed, returning raw HTML")
        return html_content


def format_file_size(size_bytes: int) -> str:
    """Format a byte count as a human-readable size string.

    Args:
        size_bytes: File size in bytes.

    Returns:
        Human-readable string such as "4 B", "12 KB", or "1.5 MB".
    """
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.0f} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"


def build_email_markdown(
    *,
    subject: str,
    headers: list[tuple[str, str]],
    body_text: str,
    attachments: list[dict[str, str]],
    include_attachments: bool,
) -> str:
    """Build the structured markdown output for an email.

    Args:
        subject: The email subject, used as the h1 heading.
        headers: Ordered list of (label, value) tuples to render as bold
                 key-value lines (e.g. [("From", "alice@test.com"), ...]).
        body_text: The email body, already converted to plain text or markdown.
        attachments: List of attachment dicts with "filename" and "size" keys.
        include_attachments: If True and attachments is non-empty, append an
                             Attachments section at the end.

    Returns:
        A multi-line markdown string representing the full email document.
    """
    lines: list[str] = []

    lines.append(f"# {subject}")
    lines.append("")

    for header_label, header_value in headers:
        if header_value:
            lines.append(f"**{header_label}:** {header_value}")

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(body_text)

    if include_attachments and attachments:
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("## Attachments")
        lines.append("")
        for attachment in attachments:
            lines.append(f"- `{attachment['filename']}` ({attachment['size']})")

    return "\n".join(lines)
