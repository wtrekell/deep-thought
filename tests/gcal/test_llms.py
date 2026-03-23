"""Tests for the GCal Tool LLM context file generation."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

from deep_thought.gcal.llms import (
    _strip_frontmatter,
    generate_llms_full,
    generate_llms_index,
    write_llms_files,
)


def _write_test_event_file(tmp_path: Path, filename: str, content: str) -> Path:
    """Helper to create a test markdown file."""
    file_path = tmp_path / filename
    file_path.write_text(content, encoding="utf-8")
    return file_path


class TestStripFrontmatter:
    """Tests for _strip_frontmatter."""

    def test_strips_frontmatter(self) -> None:
        """Should remove the --- delimited frontmatter block."""
        text = "---\ntool: gcal\nevent_id: abc\n---\n\nBody content here."
        assert _strip_frontmatter(text) == "Body content here."

    def test_no_frontmatter(self) -> None:
        """Should return the text unchanged if no frontmatter."""
        text = "Just plain text."
        assert _strip_frontmatter(text) == "Just plain text."

    def test_unclosed_frontmatter(self) -> None:
        """Should return the text unchanged if frontmatter is not closed."""
        text = "---\ntool: gcal\nno closing delimiter"
        assert _strip_frontmatter(text) == text


class TestGenerateLlmsIndex:
    """Tests for generate_llms_index."""

    def test_generates_index(self, tmp_path: Path) -> None:
        """Should generate an index with file names and first lines."""
        file1 = _write_test_event_file(
            tmp_path, "2026-03-24_standup.md", "---\ntool: gcal\n---\n\nDaily standup notes."
        )
        file2 = _write_test_event_file(
            tmp_path, "2026-03-25_review.md", "---\ntool: gcal\n---\n\nWeekly review agenda."
        )
        result = generate_llms_index([file1, file2], "Personal")
        assert "# Personal — Event Index" in result
        assert "2026-03-24_standup.md: Daily standup notes." in result
        assert "2026-03-25_review.md: Weekly review agenda." in result

    def test_empty_file_list(self) -> None:
        """Should generate header-only index for empty file list."""
        result = generate_llms_index([], "Personal")
        assert "# Personal — Event Index" in result


class TestGenerateLlmsFull:
    """Tests for generate_llms_full."""

    def test_generates_full_content(self, tmp_path: Path) -> None:
        """Should concatenate all event content with headers."""
        file1 = _write_test_event_file(tmp_path, "2026-03-24_standup.md", "---\ntool: gcal\n---\n\nStandup notes.")
        result = generate_llms_full([file1], "Personal")
        assert "# Personal — Full Event Content" in result
        assert "## 2026-03-24_standup.md" in result
        assert "Standup notes." in result


class TestWriteLlmsFiles:
    """Tests for write_llms_files."""

    def test_creates_llm_directory_and_files(self, tmp_path: Path) -> None:
        """Should create the llm/ subdirectory with both files."""
        cal_dir = tmp_path / "personal"
        cal_dir.mkdir()
        file1 = _write_test_event_file(cal_dir, "2026-03-24_standup.md", "---\ntool: gcal\n---\n\nNotes.")
        write_llms_files([file1], tmp_path, "Personal")
        llm_dir = tmp_path / "personal" / "llm"
        assert llm_dir.exists()
        assert (llm_dir / "personal.llms.txt").exists()
        assert (llm_dir / "personal.llms-full.txt").exists()

    def test_skips_for_empty_files(self, tmp_path: Path) -> None:
        """Should do nothing when file list is empty."""
        write_llms_files([], tmp_path, "Personal")
        assert not (tmp_path / "personal" / "llm").exists()
