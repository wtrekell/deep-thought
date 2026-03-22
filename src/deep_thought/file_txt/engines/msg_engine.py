"""MSG email conversion engine for the file-txt tool.

Parses OLE 2 compound document .msg files using the extract-msg library.
Produces structured markdown with email headers, body content, and optional
attachment metadata. Uses html2text for HTML body conversion.

Note on full_headers: extract-msg exposes only Message-ID and In-Reply-To as
additional headers beyond the standard set (From, To, Cc, Date). When
full_headers is True, those two fields are appended if present.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from deep_thought.file_txt.engines.email_utils import (
    build_email_markdown,
    convert_html_to_markdown,
    format_file_size,
)

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)


def convert_msg(
    source_path: Path,
    *,
    prefer_html: bool,
    full_headers: bool,
    include_attachments: bool,
) -> tuple[str, dict[str, Any]]:
    """Convert a .msg file to markdown text with email metadata.

    Args:
        source_path: Absolute path to the .msg file.
        prefer_html: If True and both plain text and HTML parts exist,
                     convert the HTML body via html2text instead of using plain text.
        full_headers: If True, include additional headers beyond the key set
                      (Message-ID and In-Reply-To when available).
        include_attachments: If True, append an attachments section listing
                             filename and size for each attachment.

    Returns:
        A tuple of (markdown_text, email_metadata) where email_metadata is a dict
        containing from_address, to_address, subject, date, has_attachments,
        attachment_count, and attachments list.

    Raises:
        ImportError: If extract-msg is not installed.
        FileNotFoundError: If source_path does not exist.
    """
    try:
        import extract_msg
    except ImportError as import_error:
        raise ImportError(
            "The extract-msg library is required for .msg conversion but is not installed. "
            "Install it with: pip install extract-msg>=0.50.0"
        ) from import_error

    if not source_path.exists():
        raise FileNotFoundError(f"MSG file not found: {source_path}")

    msg = extract_msg.Message(str(source_path))  # type: ignore[no-untyped-call]
    try:
        from_address = msg.sender or ""
        to_address = msg.to or ""
        cc_address = msg.cc or ""
        subject = msg.subject or "(No Subject)"
        date_string = str(msg.date) if msg.date else ""

        body_text = _extract_body(msg, prefer_html=prefer_html)
        attachments = _collect_attachments(msg)

        email_metadata: dict[str, Any] = {
            "from_address": from_address,
            "to_address": to_address,
            "subject": subject,
            "date": date_string,
            "has_attachments": len(attachments) > 0,
            "attachment_count": len(attachments),
            "attachments": attachments,
        }

        headers = _build_header_list(
            msg=msg,
            from_address=from_address,
            to_address=to_address,
            cc_address=cc_address,
            date_string=date_string,
            full_headers=full_headers,
        )

        markdown_text = build_email_markdown(
            subject=subject,
            headers=headers,
            body_text=body_text,
            attachments=attachments,
            include_attachments=include_attachments,
        )

        return markdown_text, email_metadata
    finally:
        msg.close()


def _extract_body(msg: Any, *, prefer_html: bool) -> str:
    """Extract the email body from a MSG message object.

    Args:
        msg: An extract_msg.Message instance.
        prefer_html: If True and HTML body exists, convert it to markdown.
    """
    plain_body: str | None = msg.body
    html_body: bytes | str | None = msg.htmlBody

    if prefer_html and html_body is not None:
        html_string = html_body.decode("utf-8", errors="replace") if isinstance(html_body, bytes) else html_body
        return convert_html_to_markdown(html_string)
    if plain_body is not None:
        return plain_body
    if html_body is not None:
        html_string = html_body.decode("utf-8", errors="replace") if isinstance(html_body, bytes) else html_body
        return convert_html_to_markdown(html_string)
    return ""


def _collect_attachments(msg: Any) -> list[dict[str, str]]:
    """Collect attachment metadata from a MSG message."""
    attachments: list[dict[str, str]] = []
    for attachment in msg.attachments:
        filename = getattr(attachment, "longFilename", None) or getattr(attachment, "shortFilename", None) or "unnamed"
        size_bytes: int = getattr(attachment, "size", 0) or 0
        attachments.append(
            {
                "filename": filename,
                "size": format_file_size(size_bytes),
            }
        )
    return attachments


def _build_header_list(
    *,
    msg: Any,
    from_address: str,
    to_address: str,
    cc_address: str,
    date_string: str,
    full_headers: bool,
) -> list[tuple[str, str]]:
    """Build the ordered list of (label, value) header tuples to render.

    Standard headers (From, To, Cc, Date) are always included. When
    full_headers is True, Message-ID and In-Reply-To are appended if the
    extract-msg object exposes them.
    """
    headers: list[tuple[str, str]] = []

    headers.append(("From", from_address))
    headers.append(("To", to_address))
    if cc_address:
        headers.append(("Cc", cc_address))
    headers.append(("Date", date_string))

    if full_headers:
        message_id = getattr(msg, "messageId", None)
        if message_id:
            headers.append(("Message-ID", str(message_id)))
        in_reply_to = getattr(msg, "inReplyTo", None)
        if in_reply_to:
            headers.append(("In-Reply-To", str(in_reply_to)))

    return headers
