"""Tests for the MSG email conversion engine in deep_thought.file_txt.engines.msg_engine."""

from __future__ import annotations

from pathlib import Path  # noqa: TC003
from unittest.mock import MagicMock, patch

import pytest

from deep_thought.file_txt.engines.msg_engine import convert_msg

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_msg(
    *,
    sender: str = "sender@example.com",
    to: str = "recipient@example.com",
    subject: str = "Test Subject",
    date: str = "2026-03-22 10:00:00",
    body: str | None = "Plain text body content.",
    html_body: bytes | str | None = None,
    attachments: list[MagicMock] | None = None,
    cc: str = "",
    message_id: str | None = None,
    in_reply_to: str | None = None,
) -> MagicMock:
    """Create a mock extract_msg.Message object with standard properties."""
    mock_msg = MagicMock()
    mock_msg.sender = sender
    mock_msg.to = to
    mock_msg.cc = cc
    mock_msg.subject = subject
    mock_msg.date = date
    mock_msg.body = body
    mock_msg.htmlBody = html_body
    mock_msg.attachments = attachments or []
    mock_msg.close = MagicMock()
    mock_msg.messageId = message_id
    mock_msg.inReplyTo = in_reply_to
    return mock_msg


def _make_mock_attachment(
    *,
    long_filename: str | None = "document.pdf",
    short_filename: str | None = None,
    size: int = 1024,
) -> MagicMock:
    """Create a mock attachment object."""
    attachment = MagicMock()
    attachment.longFilename = long_filename
    attachment.shortFilename = short_filename if short_filename is not None else long_filename
    attachment.size = size
    return attachment


# ---------------------------------------------------------------------------
# Plain text extraction
# ---------------------------------------------------------------------------


class TestConvertMsgPlainText:
    def test_plain_text_body_extracted(self, tmp_path: Path) -> None:
        """The plain text body must appear in the markdown output."""
        msg_file = tmp_path / "message.msg"
        msg_file.write_bytes(b"fake msg")
        mock_msg = _make_mock_msg(body="Hello from MSG.")

        with patch("extract_msg.Message", return_value=mock_msg):
            markdown, _metadata = convert_msg(
                msg_file, prefer_html=False, full_headers=False, include_attachments=False
            )

        assert "Hello from MSG." in markdown

    def test_headers_extracted(self, tmp_path: Path) -> None:
        """The metadata dict must contain parsed header values."""
        msg_file = tmp_path / "message.msg"
        msg_file.write_bytes(b"fake msg")
        mock_msg = _make_mock_msg(sender="alice@test.com", to="bob@test.com", subject="Project Update")

        with patch("extract_msg.Message", return_value=mock_msg):
            _markdown, metadata = convert_msg(
                msg_file, prefer_html=False, full_headers=False, include_attachments=False
            )

        assert metadata["from_address"] == "alice@test.com"
        assert metadata["to_address"] == "bob@test.com"
        assert metadata["subject"] == "Project Update"

    def test_msg_close_called(self, tmp_path: Path) -> None:
        """The msg.close() method must be called after processing."""
        msg_file = tmp_path / "message.msg"
        msg_file.write_bytes(b"fake msg")
        mock_msg = _make_mock_msg()

        with patch("extract_msg.Message", return_value=mock_msg):
            convert_msg(msg_file, prefer_html=False, full_headers=False, include_attachments=False)

        mock_msg.close.assert_called_once()


# ---------------------------------------------------------------------------
# HTML body preference
# ---------------------------------------------------------------------------


class TestConvertMsgHtml:
    def test_html_body_used_when_prefer_html_true(self, tmp_path: Path) -> None:
        """When prefer_html is True, the HTML body must be converted and used."""
        msg_file = tmp_path / "message.msg"
        msg_file.write_bytes(b"fake msg")
        mock_msg = _make_mock_msg(
            body="Plain version.",
            html_body=b"<html><body><p>HTML version.</p></body></html>",
        )

        with (
            patch("extract_msg.Message", return_value=mock_msg),
            patch("html2text.HTML2Text") as mock_h2t_class,
        ):
            mock_instance = mock_h2t_class.return_value
            mock_instance.handle.return_value = "HTML version converted."

            markdown, _metadata = convert_msg(msg_file, prefer_html=True, full_headers=False, include_attachments=False)

        assert "HTML version converted." in markdown

    def test_plain_text_preferred_when_prefer_html_false(self, tmp_path: Path) -> None:
        """When prefer_html is False, the plain text body must be used."""
        msg_file = tmp_path / "message.msg"
        msg_file.write_bytes(b"fake msg")
        mock_msg = _make_mock_msg(
            body="Plain version here.",
            html_body=b"<html><body><p>HTML version.</p></body></html>",
        )

        with patch("extract_msg.Message", return_value=mock_msg):
            markdown, _metadata = convert_msg(
                msg_file, prefer_html=False, full_headers=False, include_attachments=False
            )

        assert "Plain version here." in markdown

    def test_html_fallback_when_html2text_fails(self, tmp_path: Path) -> None:
        """When html2text raises, the raw HTML must be returned as fallback."""
        msg_file = tmp_path / "message.msg"
        msg_file.write_bytes(b"fake msg")
        raw_html = "<html><body><p>Fallback HTML content.</p></body></html>"
        mock_msg = _make_mock_msg(
            body=None,
            html_body=raw_html.encode("utf-8"),
        )

        # Patch html2text.HTML2Text so that .handle() raises — the fallback in
        # convert_html_to_markdown catches all non-ImportError exceptions and
        # returns the raw HTML string instead.
        with (
            patch("extract_msg.Message", return_value=mock_msg),
            patch("html2text.HTML2Text") as mock_h2t_class,
        ):
            mock_h2t_class.return_value.handle.side_effect = RuntimeError("html2text blew up")
            markdown, _metadata = convert_msg(msg_file, prefer_html=True, full_headers=False, include_attachments=False)

        assert raw_html in markdown


# ---------------------------------------------------------------------------
# Attachment handling
# ---------------------------------------------------------------------------


class TestConvertMsgAttachments:
    def test_attachment_metadata_included(self, tmp_path: Path) -> None:
        """Attachments must appear in the output and metadata when include_attachments is True."""
        msg_file = tmp_path / "message.msg"
        msg_file.write_bytes(b"fake msg")
        mock_attachment = _make_mock_attachment(long_filename="report.pdf", size=2048)
        mock_msg = _make_mock_msg(attachments=[mock_attachment])

        with patch("extract_msg.Message", return_value=mock_msg):
            markdown, metadata = convert_msg(msg_file, prefer_html=False, full_headers=False, include_attachments=True)

        assert metadata["has_attachments"] is True
        assert metadata["attachment_count"] == 1
        assert "## Attachments" in markdown
        assert "report.pdf" in markdown

    def test_attachment_metadata_excluded(self, tmp_path: Path) -> None:
        """Attachments section must not appear when include_attachments is False."""
        msg_file = tmp_path / "message.msg"
        msg_file.write_bytes(b"fake msg")
        mock_attachment = _make_mock_attachment()
        mock_msg = _make_mock_msg(attachments=[mock_attachment])

        with patch("extract_msg.Message", return_value=mock_msg):
            markdown, metadata = convert_msg(msg_file, prefer_html=False, full_headers=False, include_attachments=False)

        assert metadata["has_attachments"] is True
        assert "## Attachments" not in markdown

    def test_unnamed_attachment(self, tmp_path: Path) -> None:
        """An attachment with no filename must use 'unnamed' as the filename."""
        msg_file = tmp_path / "message.msg"
        msg_file.write_bytes(b"fake msg")
        nameless_attachment = _make_mock_attachment(long_filename=None, short_filename=None, size=512)
        mock_msg = _make_mock_msg(attachments=[nameless_attachment])

        with patch("extract_msg.Message", return_value=mock_msg):
            markdown, metadata = convert_msg(msg_file, prefer_html=False, full_headers=False, include_attachments=True)

        assert metadata["has_attachments"] is True
        assert "unnamed" in markdown

    def test_zero_size_attachment(self, tmp_path: Path) -> None:
        """A zero-size attachment must report '0 B' size."""
        msg_file = tmp_path / "message.msg"
        msg_file.write_bytes(b"fake msg")
        empty_attachment = _make_mock_attachment(long_filename="empty.pdf", size=0)
        mock_msg = _make_mock_msg(attachments=[empty_attachment])

        with patch("extract_msg.Message", return_value=mock_msg):
            markdown, metadata = convert_msg(msg_file, prefer_html=False, full_headers=False, include_attachments=True)

        assert metadata["has_attachments"] is True
        assert "0 B" in markdown


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestConvertMsgErrors:
    @pytest.mark.error_handling
    def test_missing_file_raises_file_not_found(self, tmp_path: Path) -> None:
        """Passing a non-existent path must raise FileNotFoundError."""
        missing_path = tmp_path / "nonexistent.msg"

        with pytest.raises(FileNotFoundError, match="MSG file not found"):
            convert_msg(missing_path, prefer_html=False, full_headers=False, include_attachments=False)


# ---------------------------------------------------------------------------
# Empty body
# ---------------------------------------------------------------------------


class TestConvertMsgEmptyBody:
    def test_empty_body_returns_empty_string(self, tmp_path: Path) -> None:
        """A MSG with no body and no HTML must produce empty body text."""
        msg_file = tmp_path / "message.msg"
        msg_file.write_bytes(b"fake msg")
        mock_msg = _make_mock_msg(body=None, html_body=None)

        with patch("extract_msg.Message", return_value=mock_msg):
            markdown, _metadata = convert_msg(
                msg_file, prefer_html=False, full_headers=False, include_attachments=False
            )

        # The subject heading must be present but there should be no body text
        assert "# Test Subject" in markdown
        body_lines = [
            line
            for line in markdown.splitlines()
            if line.strip() and not line.startswith("#") and line != "---" and not line.startswith("**")
        ]
        assert body_lines == []


# ---------------------------------------------------------------------------
# Full headers (MSG-specific: Message-ID and In-Reply-To)
# ---------------------------------------------------------------------------


class TestConvertMsgFullHeaders:
    def test_full_headers_includes_message_id(self, tmp_path: Path) -> None:
        """When full_headers is True, Message-ID must appear if present."""
        msg_file = tmp_path / "message.msg"
        msg_file.write_bytes(b"fake msg")
        mock_msg = _make_mock_msg(message_id="<123@example.com>")

        with patch("extract_msg.Message", return_value=mock_msg):
            markdown, _metadata = convert_msg(msg_file, prefer_html=False, full_headers=True, include_attachments=False)

        assert "Message-ID" in markdown
        assert "<123@example.com>" in markdown

    def test_full_headers_without_optional_fields(self, tmp_path: Path) -> None:
        """When full_headers is True but no Message-ID/In-Reply-To, standard headers still appear."""
        msg_file = tmp_path / "message.msg"
        msg_file.write_bytes(b"fake msg")
        mock_msg = _make_mock_msg(message_id=None, in_reply_to=None)

        with patch("extract_msg.Message", return_value=mock_msg):
            markdown, _metadata = convert_msg(msg_file, prefer_html=False, full_headers=True, include_attachments=False)

        assert "**From:**" in markdown
        assert "**To:**" in markdown
        assert "Message-ID" not in markdown
