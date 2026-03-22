"""Tests for the EML email conversion engine in deep_thought.file_txt.engines.eml_engine."""

from __future__ import annotations

from email.message import EmailMessage
from pathlib import Path  # noqa: TC003
from unittest.mock import patch

import pytest

from deep_thought.file_txt.engines.email_utils import format_file_size
from deep_thought.file_txt.engines.eml_engine import convert_eml

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_plain_eml(
    *,
    from_addr: str = "sender@example.com",
    to_addr: str = "recipient@example.com",
    subject: str = "Test Subject",
    body: str = "Hello, this is the email body.",
) -> bytes:
    """Build a minimal plain-text .eml file as bytes."""
    msg = EmailMessage()
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg["Date"] = "Sat, 22 Mar 2026 10:00:00 +0000"
    msg.set_content(body)
    return msg.as_bytes()


def _build_multipart_eml(
    *,
    plain_body: str = "Plain text body.",
    html_body: str = "<html><body><p>HTML body.</p></body></html>",
) -> bytes:
    """Build a multipart .eml with both plain text and HTML parts."""
    msg = EmailMessage()
    msg["From"] = "sender@example.com"
    msg["To"] = "recipient@example.com"
    msg["Subject"] = "Multipart Test"
    msg["Date"] = "Sat, 22 Mar 2026 10:00:00 +0000"
    msg.set_content(plain_body)
    msg.add_alternative(html_body, subtype="html")
    return msg.as_bytes()


def _build_eml_with_attachment(
    *,
    body: str = "Email with attachment.",
    attachment_filename: str = "document.pdf",
    attachment_data: bytes = b"fake pdf content",
) -> bytes:
    """Build an .eml with a text body and a binary attachment."""
    msg = EmailMessage()
    msg["From"] = "sender@example.com"
    msg["To"] = "recipient@example.com"
    msg["Subject"] = "Attachment Test"
    msg["Date"] = "Sat, 22 Mar 2026 10:00:00 +0000"
    msg.set_content(body)
    msg.add_attachment(
        attachment_data,
        maintype="application",
        subtype="pdf",
        filename=attachment_filename,
    )
    return msg.as_bytes()


# ---------------------------------------------------------------------------
# Plain text extraction
# ---------------------------------------------------------------------------


class TestConvertEmlPlainText:
    def test_plain_text_body_extracted(self, tmp_path: Path) -> None:
        """The plain text body must appear in the markdown output."""
        eml_file = tmp_path / "message.eml"
        eml_file.write_bytes(_build_plain_eml(body="Hello from the test."))

        markdown, _metadata = convert_eml(eml_file, prefer_html=False, full_headers=False, include_attachments=False)

        assert "Hello from the test." in markdown

    def test_headers_extracted(self, tmp_path: Path) -> None:
        """The metadata dict must contain parsed header values."""
        eml_file = tmp_path / "message.eml"
        eml_file.write_bytes(_build_plain_eml(from_addr="alice@test.com", to_addr="bob@test.com"))

        _markdown, metadata = convert_eml(eml_file, prefer_html=False, full_headers=False, include_attachments=False)

        assert metadata["from_address"] == "alice@test.com"
        assert metadata["to_address"] == "bob@test.com"
        assert metadata["subject"] == "Test Subject"
        assert "2026-03-22" in metadata["date"]  # ISO 8601 format

    def test_returns_correct_metadata_types(self, tmp_path: Path) -> None:
        """Metadata has_attachments must be bool and attachment_count must be int."""
        eml_file = tmp_path / "message.eml"
        eml_file.write_bytes(_build_plain_eml())

        _markdown, metadata = convert_eml(eml_file, prefer_html=False, full_headers=False, include_attachments=False)

        assert isinstance(metadata["has_attachments"], bool)
        assert isinstance(metadata["attachment_count"], int)

    def test_subject_used_as_heading(self, tmp_path: Path) -> None:
        """The email subject must appear as an h1 heading in the markdown."""
        eml_file = tmp_path / "message.eml"
        eml_file.write_bytes(_build_plain_eml(subject="Important Update"))

        markdown, _metadata = convert_eml(eml_file, prefer_html=False, full_headers=False, include_attachments=False)

        assert "# Important Update" in markdown


# ---------------------------------------------------------------------------
# HTML body preference
# ---------------------------------------------------------------------------


class TestConvertEmlHtml:
    def test_html_body_used_when_prefer_html_true(self, tmp_path: Path) -> None:
        """When prefer_html is True, the HTML body must be converted and used."""
        eml_file = tmp_path / "message.eml"
        eml_file.write_bytes(
            _build_multipart_eml(
                plain_body="Plain version.",
                html_body="<html><body><p>HTML version.</p></body></html>",
            )
        )

        with patch("html2text.HTML2Text") as mock_h2t_class:
            mock_instance = mock_h2t_class.return_value
            mock_instance.handle.return_value = "HTML version converted."

            markdown, _metadata = convert_eml(eml_file, prefer_html=True, full_headers=False, include_attachments=False)

        assert "HTML version converted." in markdown

    def test_plain_text_preferred_when_prefer_html_false(self, tmp_path: Path) -> None:
        """When prefer_html is False, the plain text body must be used."""
        eml_file = tmp_path / "message.eml"
        eml_file.write_bytes(
            _build_multipart_eml(
                plain_body="Plain version here.",
                html_body="<html><body><p>HTML version.</p></body></html>",
            )
        )

        markdown, _metadata = convert_eml(eml_file, prefer_html=False, full_headers=False, include_attachments=False)

        assert "Plain version here." in markdown

    def test_html_fallback_when_html2text_fails(self, tmp_path: Path) -> None:
        """When html2text raises, the raw HTML must be returned as fallback."""
        eml_file = tmp_path / "message.eml"
        raw_html = "<html><body><p>Fallback HTML content.</p></body></html>"
        eml_file.write_bytes(
            _build_multipart_eml(
                plain_body="Plain version.",
                html_body=raw_html,
            )
        )

        # Patch html2text.HTML2Text so that .handle() raises — the fallback in
        # convert_html_to_markdown catches all non-ImportError exceptions and
        # returns the raw HTML string instead.
        with patch("html2text.HTML2Text") as mock_h2t_class:
            mock_h2t_class.return_value.handle.side_effect = RuntimeError("html2text blew up")
            markdown, _metadata = convert_eml(eml_file, prefer_html=True, full_headers=False, include_attachments=False)

        assert raw_html in markdown


# ---------------------------------------------------------------------------
# Attachment handling
# ---------------------------------------------------------------------------


class TestConvertEmlAttachments:
    def test_attachment_metadata_included(self, tmp_path: Path) -> None:
        """Attachments must appear in the output and metadata when include_attachments is True."""
        eml_file = tmp_path / "message.eml"
        eml_file.write_bytes(
            _build_eml_with_attachment(
                attachment_filename="report.pdf",
                attachment_data=b"x" * 2048,
            )
        )

        markdown, metadata = convert_eml(eml_file, prefer_html=False, full_headers=False, include_attachments=True)

        assert metadata["has_attachments"] is True
        assert metadata["attachment_count"] == 1
        assert "## Attachments" in markdown
        assert "report.pdf" in markdown

    def test_attachment_metadata_excluded(self, tmp_path: Path) -> None:
        """Attachments section must not appear when include_attachments is False."""
        eml_file = tmp_path / "message.eml"
        eml_file.write_bytes(_build_eml_with_attachment())

        markdown, metadata = convert_eml(eml_file, prefer_html=False, full_headers=False, include_attachments=False)

        assert metadata["has_attachments"] is True
        assert "## Attachments" not in markdown

    def test_zero_size_attachment(self, tmp_path: Path) -> None:
        """A zero-size attachment must report '0 B' size."""
        eml_file = tmp_path / "message.eml"
        eml_file.write_bytes(
            _build_eml_with_attachment(
                attachment_filename="empty.pdf",
                attachment_data=b"",
            )
        )

        markdown, metadata = convert_eml(eml_file, prefer_html=False, full_headers=False, include_attachments=True)

        assert metadata["has_attachments"] is True
        assert "0 B" in markdown


# ---------------------------------------------------------------------------
# Full headers
# ---------------------------------------------------------------------------


class TestConvertEmlFullHeaders:
    def test_full_headers_includes_all_mime_headers(self, tmp_path: Path) -> None:
        """When full_headers is True, all MIME headers must appear in the output."""
        eml_file = tmp_path / "message.eml"
        eml_file.write_bytes(_build_plain_eml())

        markdown, _metadata = convert_eml(eml_file, prefer_html=False, full_headers=True, include_attachments=False)

        assert "**Content-Type:**" in markdown

    def test_default_headers_only_shows_key_headers(self, tmp_path: Path) -> None:
        """When full_headers is False, only From, To, Subject, Date must appear."""
        eml_file = tmp_path / "message.eml"
        eml_file.write_bytes(_build_plain_eml())

        markdown, _metadata = convert_eml(eml_file, prefer_html=False, full_headers=False, include_attachments=False)

        assert "**From:**" in markdown
        assert "**To:**" in markdown
        assert "**Date:**" in markdown
        assert "**Content-Type:**" not in markdown


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestConvertEmlErrors:
    @pytest.mark.error_handling
    def test_missing_file_raises_file_not_found(self, tmp_path: Path) -> None:
        """Passing a non-existent path must raise FileNotFoundError."""
        missing_path = tmp_path / "nonexistent.eml"
        with pytest.raises(FileNotFoundError, match="EML file not found"):
            convert_eml(missing_path, prefer_html=False, full_headers=False, include_attachments=False)


# ---------------------------------------------------------------------------
# Empty body
# ---------------------------------------------------------------------------


class TestConvertEmlEmptyBody:
    def test_empty_body_returns_empty_string(self, tmp_path: Path) -> None:
        """An EML with no text/plain and no text/html must produce empty body text."""
        headers_only_msg = EmailMessage()
        headers_only_msg["From"] = "sender@example.com"
        headers_only_msg["To"] = "recipient@example.com"
        headers_only_msg["Subject"] = "No Body"
        headers_only_msg["Date"] = "Sat, 22 Mar 2026 10:00:00 +0000"
        # Intentionally no set_content() call — message has no body parts

        eml_file = tmp_path / "no_body.eml"
        eml_file.write_bytes(headers_only_msg.as_bytes())

        markdown, _metadata = convert_eml(eml_file, prefer_html=False, full_headers=False, include_attachments=False)

        # The subject heading must be present but there should be no body text
        assert "# No Body" in markdown
        # Body section should be empty (just the separator and empty string)
        body_lines = [
            line
            for line in markdown.splitlines()
            if line.strip() and not line.startswith("#") and line != "---" and not line.startswith("**")
        ]
        assert body_lines == []


# ---------------------------------------------------------------------------
# RFC 2047 encoded headers
# ---------------------------------------------------------------------------


class TestConvertEmlEncodedHeaders:
    def test_utf8_encoded_subject(self, tmp_path: Path) -> None:
        """An RFC 2047 encoded subject must be decoded correctly."""
        unicode_subject = "Ré: Mise à jour du projet"
        eml_file = tmp_path / "encoded_subject.eml"
        eml_file.write_bytes(_build_plain_eml(subject=unicode_subject))

        markdown, metadata = convert_eml(eml_file, prefer_html=False, full_headers=False, include_attachments=False)

        assert metadata["subject"] == unicode_subject
        assert f"# {unicode_subject}" in markdown


# ---------------------------------------------------------------------------
# format_file_size boundary values (shared email_utils function)
# ---------------------------------------------------------------------------


class TestFormatFileSize:
    def test_bytes_below_1024(self) -> None:
        """Values below 1024 must be returned with a 'B' suffix."""
        assert format_file_size(500) == "500 B"

    def test_exact_1024_boundary(self) -> None:
        """Exactly 1024 bytes must display as '1 KB'."""
        assert format_file_size(1024) == "1 KB"

    def test_just_below_1024(self) -> None:
        """1023 bytes is still below the KB threshold."""
        assert format_file_size(1023) == "1023 B"

    def test_kilobytes(self) -> None:
        """5120 bytes is 5 KB."""
        assert format_file_size(5120) == "5 KB"

    def test_exact_megabyte_boundary(self) -> None:
        """Exactly 1 MiB must display as '1.0 MB'."""
        assert format_file_size(1024 * 1024) == "1.0 MB"

    def test_just_below_megabyte(self) -> None:
        """One byte below 1 MiB must still display in KB."""
        assert format_file_size(1024 * 1024 - 1) == "1024 KB"

    def test_megabytes(self) -> None:
        """5 MiB must display as '5.0 MB'."""
        assert format_file_size(5 * 1024 * 1024) == "5.0 MB"

    def test_zero_bytes(self) -> None:
        """Zero bytes must display as '0 B'."""
        assert format_file_size(0) == "0 B"
