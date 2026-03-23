"""Tests for the Gmail Tool LLM context file generation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from deep_thought.gmail.llms import (
    _strip_frontmatter,
    generate_llms_full,
    generate_llms_index,
    write_llms_files,
)

if TYPE_CHECKING:
    from pathlib import Path


# ---------------------------------------------------------------------------
# _strip_frontmatter
# ---------------------------------------------------------------------------


class TestStripFrontmatter:
    """Tests for _strip_frontmatter."""

    def test_removes_frontmatter(self) -> None:
        """Should remove YAML frontmatter delimited by ---."""
        text = "---\ntool: gmail\nrule: test\n---\n\nBody content here."
        result = _strip_frontmatter(text)
        assert result == "Body content here."

    def test_returns_text_without_frontmatter(self) -> None:
        """Should return text unchanged if no frontmatter is present."""
        text = "Just plain text with no frontmatter."
        result = _strip_frontmatter(text)
        assert result == text

    def test_returns_text_with_unclosed_frontmatter(self) -> None:
        """Should return original text if frontmatter has no closing ---."""
        text = "---\ntool: gmail\nrule: test\nNo closing delimiter."
        result = _strip_frontmatter(text)
        assert result == text

    def test_empty_string(self) -> None:
        """Should return empty string for empty input."""
        assert _strip_frontmatter("") == ""

    def test_frontmatter_only(self) -> None:
        """Should return empty string when file is only frontmatter."""
        text = "---\ntool: gmail\n---"
        result = _strip_frontmatter(text)
        assert result == ""

    def test_strips_leading_whitespace_from_body(self) -> None:
        """Should strip leading/trailing whitespace from the body after frontmatter removal."""
        text = "---\nkey: val\n---\n\n\n  Body with leading space.  \n\n"
        result = _strip_frontmatter(text)
        assert result == "Body with leading space."


# ---------------------------------------------------------------------------
# generate_llms_index
# ---------------------------------------------------------------------------


class TestGenerateLlmsIndex:
    """Tests for generate_llms_index."""

    def test_generates_index_with_files(self, tmp_path: Path) -> None:
        """Should list each file with its first non-empty line as summary."""
        file_one = tmp_path / "email1.md"
        file_one.write_text("---\ntool: gmail\n---\n\nFirst email content.", encoding="utf-8")
        file_two = tmp_path / "email2.md"
        file_two.write_text("---\ntool: gmail\n---\n\nSecond email content.", encoding="utf-8")

        result = generate_llms_index([file_one, file_two], "newsletters")

        assert "# newsletters — Email Index" in result
        assert "- email1.md: First email content." in result
        assert "- email2.md: Second email content." in result

    def test_empty_file_list(self) -> None:
        """Should return header with no entries for empty file list."""
        result = generate_llms_index([], "newsletters")
        assert "# newsletters — Email Index" in result
        assert result.endswith("\n")

    def test_truncates_long_first_lines(self, tmp_path: Path) -> None:
        """Should truncate first lines longer than 120 characters."""
        long_file = tmp_path / "long.md"
        long_line = "A" * 200
        long_file.write_text(long_line, encoding="utf-8")

        result = generate_llms_index([long_file], "test")
        # The summary should be truncated to 120 chars
        for line in result.splitlines():
            if line.startswith("- long.md:"):
                summary = line.split(": ", 1)[1]
                assert len(summary) <= 120
                break

    def test_skips_blank_lines_for_summary(self, tmp_path: Path) -> None:
        """Should skip blank lines and use the first non-empty line as summary."""
        file_path = tmp_path / "blanky.md"
        file_path.write_text("---\nkey: val\n---\n\n\n\nActual content here.", encoding="utf-8")

        result = generate_llms_index([file_path], "test")
        assert "Actual content here." in result


# ---------------------------------------------------------------------------
# generate_llms_full
# ---------------------------------------------------------------------------


class TestGenerateLlmsFull:
    """Tests for generate_llms_full."""

    def test_concatenates_files_with_separators(self, tmp_path: Path) -> None:
        """Should concatenate all file bodies separated by horizontal rules."""
        file_one = tmp_path / "email1.md"
        file_one.write_text("---\ntool: gmail\n---\n\nFirst body.", encoding="utf-8")
        file_two = tmp_path / "email2.md"
        file_two.write_text("---\ntool: gmail\n---\n\nSecond body.", encoding="utf-8")

        result = generate_llms_full([file_one, file_two], "newsletters")

        assert "# newsletters — Full Email Content" in result
        assert "## email1.md" in result
        assert "First body." in result
        assert "## email2.md" in result
        assert "Second body." in result
        assert "---" in result

    def test_empty_file_list(self) -> None:
        """Should return header only for empty file list."""
        result = generate_llms_full([], "newsletters")
        assert "# newsletters — Full Email Content" in result


# ---------------------------------------------------------------------------
# write_llms_files
# ---------------------------------------------------------------------------


class TestWriteLlmsFiles:
    """Tests for write_llms_files."""

    def test_creates_llm_directory_and_files(self, tmp_path: Path) -> None:
        """Should create the llm/ subdirectory and both output files."""
        email_file = tmp_path / "email.md"
        email_file.write_text("---\ntool: gmail\n---\n\nContent.", encoding="utf-8")

        write_llms_files([email_file], tmp_path, "newsletters")

        llm_dir = tmp_path / "newsletters" / "llm"
        assert llm_dir.exists()
        assert (llm_dir / "newsletters.llms.txt").exists()
        assert (llm_dir / "newsletters.llms-full.txt").exists()

    def test_index_file_content(self, tmp_path: Path) -> None:
        """Should write correct index content to the .llms.txt file."""
        email_file = tmp_path / "email.md"
        email_file.write_text("---\ntool: gmail\n---\n\nTest content.", encoding="utf-8")

        write_llms_files([email_file], tmp_path, "test_rule")

        index_path = tmp_path / "test_rule" / "llm" / "test_rule.llms.txt"
        index_content = index_path.read_text(encoding="utf-8")
        assert "# test_rule — Email Index" in index_content
        assert "email.md" in index_content

    def test_full_file_content(self, tmp_path: Path) -> None:
        """Should write correct full content to the .llms-full.txt file."""
        email_file = tmp_path / "email.md"
        email_file.write_text("---\ntool: gmail\n---\n\nFull body here.", encoding="utf-8")

        write_llms_files([email_file], tmp_path, "test_rule")

        full_path = tmp_path / "test_rule" / "llm" / "test_rule.llms-full.txt"
        full_content = full_path.read_text(encoding="utf-8")
        assert "Full body here." in full_content

    def test_skips_on_empty_file_list(self, tmp_path: Path) -> None:
        """Should not create any files when the email list is empty."""
        write_llms_files([], tmp_path, "newsletters")

        llm_dir = tmp_path / "newsletters" / "llm"
        assert not llm_dir.exists()
