"""EML email conversion engine for the file-txt tool.

Parses RFC 822 .eml files using the Python standard library email module.
Produces structured markdown with email headers, body content, and optional
attachment metadata. Uses html2text for HTML body conversion.
"""

from __future__ import annotations

import email
import email.header
import email.policy
import email.utils
import logging
from typing import TYPE_CHECKING, Any

from deep_thought.file_txt.engines.email_utils import (
    build_email_markdown,
    convert_html_to_markdown,
    format_file_size,
)

if TYPE_CHECKING:
    from email.message import Message
    from pathlib import Path

logger = logging.getLogger(__name__)


def convert_eml(
    source_path: Path,
    *,
    prefer_html: bool,
    full_headers: bool,
    include_attachments: bool,
) -> tuple[str, dict[str, Any]]:
    """Convert an .eml file to markdown text with email metadata.

    Args:
        source_path: Absolute path to the .eml file.
        prefer_html: If True and both plain text and HTML parts exist,
                     convert the HTML body via html2text instead of using plain text.
        full_headers: If True, include all MIME headers in the output.
                      Otherwise only key headers (From, To, Cc, Subject, Date).
        include_attachments: If True, append an attachments section listing
                             filename and size for each attachment.

    Returns:
        A tuple of (markdown_text, email_metadata) where email_metadata is a dict
        containing from_address, to_address, subject, date, has_attachments,
        attachment_count, and attachments list.

    Raises:
        FileNotFoundError: If source_path does not exist.
    """
    if not source_path.exists():
        raise FileNotFoundError(f"EML file not found: {source_path}")

    raw_bytes = source_path.read_bytes()
    message: Message = email.message_from_bytes(raw_bytes, policy=email.policy.default)

    from_address = _decode_header(message.get("From", ""))
    to_address = _decode_header(message.get("To", ""))
    cc_address = _decode_header(message.get("Cc", ""))
    subject = _decode_header(message.get("Subject", "(No Subject)"))
    date_raw = message.get("Date", "")
    date_string = _format_date(date_raw)

    body_text = _extract_body(message, prefer_html=prefer_html)
    attachments = _collect_attachments(message)

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
        message=message,
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


def _decode_header(raw_value: str) -> str:
    """Decode an RFC 2047 encoded header value to a plain string."""
    if not raw_value:
        return ""
    decoded_parts = email.header.decode_header(raw_value)
    result_parts: list[str] = []
    for part_bytes, charset in decoded_parts:
        if isinstance(part_bytes, bytes):
            result_parts.append(part_bytes.decode(charset or "utf-8", errors="replace"))
        else:
            result_parts.append(part_bytes)
    return " ".join(result_parts)


def _format_date(raw_date: str) -> str:
    """Parse an email date header and return an ISO 8601 string."""
    if not raw_date:
        return ""
    try:
        parsed = email.utils.parsedate_to_datetime(raw_date)
        return parsed.isoformat()
    except (ValueError, TypeError):
        logger.warning("Could not parse email date header: %s", raw_date)
        return raw_date


def _extract_body(message: Message, *, prefer_html: bool) -> str:
    """Extract the email body text from a MIME message.

    Walks the MIME tree looking for text/plain and text/html parts.
    Returns the preferred body based on the prefer_html flag.
    """
    plain_body: str | None = None
    html_body: str | None = None

    if message.is_multipart():
        for part in message.walk():
            content_type = part.get_content_type()
            disposition = str(part.get("Content-Disposition", ""))
            if "attachment" in disposition:
                continue
            if content_type == "text/plain" and plain_body is None:
                payload = part.get_payload(decode=True)
                if isinstance(payload, bytes):
                    charset = part.get_content_charset() or "utf-8"
                    plain_body = payload.decode(charset, errors="replace")
            elif content_type == "text/html" and html_body is None:
                payload = part.get_payload(decode=True)
                if isinstance(payload, bytes):
                    charset = part.get_content_charset() or "utf-8"
                    html_body = payload.decode(charset, errors="replace")
    else:
        content_type = message.get_content_type()
        payload = message.get_payload(decode=True)
        if isinstance(payload, bytes):
            charset = message.get_content_charset() or "utf-8"
            decoded = payload.decode(charset, errors="replace")
            if content_type == "text/html":
                html_body = decoded
            else:
                plain_body = decoded

    if prefer_html and html_body is not None:
        return convert_html_to_markdown(html_body)
    if plain_body is not None:
        return plain_body
    if html_body is not None:
        return convert_html_to_markdown(html_body)
    return ""


def _collect_attachments(message: Message) -> list[dict[str, str]]:
    """Collect attachment metadata from a MIME message.

    Captures both Content-Disposition: attachment parts and inline parts
    that carry an explicit filename (e.g. inline images with a Content-ID).
    Plain inline parts without filenames (such as the text body itself) are
    skipped.
    """
    attachments: list[dict[str, str]] = []
    if not message.is_multipart():
        return attachments

    for part in message.walk():
        disposition = str(part.get("Content-Disposition", ""))
        if "attachment" not in disposition and "inline" not in disposition:
            continue
        if not part.get_filename():
            # Skip inline parts without filenames (e.g. plain text body parts)
            continue
        filename = part.get_filename()
        filename = _decode_header(filename) if filename else "unnamed_attachment"
        payload = part.get_payload(decode=True)
        size_bytes = len(payload) if isinstance(payload, bytes) else 0
        attachments.append(
            {
                "filename": filename,
                "size": format_file_size(size_bytes),
            }
        )
    return attachments


def _build_header_list(
    *,
    message: Message,
    from_address: str,
    to_address: str,
    cc_address: str,
    date_string: str,
    full_headers: bool,
) -> list[tuple[str, str]]:
    """Build the ordered list of (label, value) header tuples to render.

    When full_headers is True, iterates all MIME headers on the message.
    Otherwise returns only the key headers (From, To, Cc, Date).
    """
    headers: list[tuple[str, str]] = []

    if full_headers:
        for header_name in message:
            header_value = _decode_header(str(message.get(header_name, "")))
            headers.append((header_name, header_value))
    else:
        headers.append(("From", from_address))
        headers.append(("To", to_address))
        if cc_address:
            headers.append(("Cc", cc_address))
        headers.append(("Date", date_string))

    return headers
