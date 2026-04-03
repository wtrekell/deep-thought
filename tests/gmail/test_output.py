"""Tests for the Gmail Tool markdown output generation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

from deep_thought.gmail.output import (
    append_to_rule_file,
    extract_body_text,
    generate_email_markdown,
    write_email_file,
)

from .conftest import make_mock_message


class TestExtractBodyText:
    """Tests for extract_body_text."""

    def test_plain_text_message(self) -> None:
        """Should extract plain text from a simple message."""
        message = make_mock_message(body_text="Hello world")
        plain, html = extract_body_text(message)
        assert plain == "Hello world"
        assert html is None

    def test_multipart_message(self) -> None:
        """Should extract both plain and HTML from multipart messages."""
        message = make_mock_message(
            body_text="Plain version",
            body_html="<p>HTML version</p>",
        )
        plain, html = extract_body_text(message)
        assert plain == "Plain version"
        assert html is not None
        assert "HTML version" in html

    def test_empty_message(self) -> None:
        """Should return empty strings for empty payload."""
        message: dict[str, Any] = {"id": "test", "payload": {}}
        plain, html = extract_body_text(message)
        assert plain == ""
        assert html is None


class TestGenerateEmailMarkdown:
    """Tests for generate_email_markdown."""

    def test_includes_frontmatter(self) -> None:
        """Should include YAML frontmatter with message metadata."""
        message = make_mock_message(subject="Weekly Digest", from_address="news@example.com")
        result = generate_email_markdown(message, "Body text here.", "newsletters", ["archive"])
        assert result.startswith("---\n")
        assert "tool: gmail" in result
        assert "Weekly Digest" in result
        assert "newsletters" in result

    def test_includes_body(self) -> None:
        """Should include the body text after frontmatter."""
        message = make_mock_message()
        result = generate_email_markdown(message, "The actual content.", "test", [])
        assert "The actual content." in result

    def test_includes_actions(self) -> None:
        """Should list actions in frontmatter."""
        message = make_mock_message()
        result = generate_email_markdown(message, "Body", "test", ["archive", "label:Done"])
        assert "  - archive" in result
        assert "  - label:Done" in result

    def test_omits_empty_actions(self) -> None:
        """Should not include actions_taken key when no actions."""
        message = make_mock_message()
        result = generate_email_markdown(message, "Body", "test", [])
        assert "actions_taken:" not in result

    def test_escapes_quotes_in_subject(self) -> None:
        """Should escape double quotes in subject to produce valid YAML."""
        message = make_mock_message(subject='Breaking: "Big News" Today')
        result = generate_email_markdown(message, "Body", "test", [])
        assert 'subject: "Breaking: \\"Big News\\" Today"' in result

    def test_escapes_quotes_in_from_header(self) -> None:
        """Should escape double quotes in from header to produce valid YAML."""
        message = make_mock_message(from_address='"John" Doe <john@example.com>')
        result = generate_email_markdown(message, "Body", "test", [])
        assert '\\"John\\"' in result


class TestWriteEmailFile:
    """Tests for write_email_file."""

    def test_creates_file(self, tmp_path: Path) -> None:
        """Should create the markdown file at the expected path."""
        file_path = write_email_file(
            content="---\ntool: gmail\n---\n\nContent",
            output_dir=tmp_path,
            rule_name="newsletters",
            subject="Weekly Digest",
            date_str="260323",
        )
        assert file_path.exists()
        assert "weekly-digest" in file_path.name
        assert file_path.read_text() == "---\ntool: gmail\n---\n\nContent"

    def test_creates_rule_subdirectory(self, tmp_path: Path) -> None:
        """Should create the rule subdirectory if it does not exist."""
        file_path = write_email_file(
            content="content",
            output_dir=tmp_path,
            rule_name="receipts",
            subject="Invoice",
            date_str="260323",
        )
        assert file_path.parent.name == "receipts"

    def test_handles_empty_subject(self, tmp_path: Path) -> None:
        """Should use a fallback filename when subject is empty."""
        file_path = write_email_file(
            content="content",
            output_dir=tmp_path,
            rule_name="test",
            subject="",
            date_str="260323",
        )
        assert "no-subject" in file_path.name

    def test_collision_appends_counter_suffix(self, tmp_path: Path) -> None:
        """Should append _1, _2, ... when two files would have the same name (M2).

        Subjects that produce the same 80-character slug (e.g., long subjects
        that differ only after the truncation point) would overwrite each other
        without collision detection.
        """
        shared_subject = "a" * 100  # Slugifies to 80 'a' chars — identical for both

        first_path = write_email_file(
            content="First email content",
            output_dir=tmp_path,
            rule_name="test_rule",
            subject=shared_subject,
            date_str="260330",
        )
        second_path = write_email_file(
            content="Second email content",
            output_dir=tmp_path,
            rule_name="test_rule",
            subject=shared_subject,
            date_str="260330",
        )

        assert first_path.exists()
        assert second_path.exists()
        assert first_path != second_path
        assert first_path.read_text() == "First email content"
        assert second_path.read_text() == "Second email content"
        assert "_1" in second_path.name

    def test_collision_counter_increments_beyond_one(self, tmp_path: Path) -> None:
        """Should use _2, _3, ... for the third and subsequent collisions."""
        shared_subject = "collision subject"

        paths = [
            write_email_file(
                content=f"Email {i}",
                output_dir=tmp_path,
                rule_name="test_rule",
                subject=shared_subject,
                date_str="260330",
            )
            for i in range(3)
        ]

        assert len({p.name for p in paths}) == 3, "All three files should have distinct names"
        assert paths[0].read_text() == "Email 0"
        assert paths[1].read_text() == "Email 1"
        assert paths[2].read_text() == "Email 2"


class TestAppendToRuleFile:
    """Tests for append_to_rule_file."""

    def test_creates_new_file(self, tmp_path: Path) -> None:
        """Should create the aggregate file if it does not exist."""
        file_path = append_to_rule_file(
            content="First email content",
            output_dir=tmp_path,
            rule_name="newsletters",
        )
        assert file_path.exists()
        assert file_path.read_text() == "First email content"
        assert file_path.name == "newsletters.md"

    def test_appends_with_separator(self, tmp_path: Path) -> None:
        """Should append new content with a horizontal rule separator."""
        append_to_rule_file("First email", tmp_path, "newsletters")
        file_path = append_to_rule_file("Second email", tmp_path, "newsletters")

        content = file_path.read_text()
        assert "First email" in content
        assert "---" in content
        assert "Second email" in content
