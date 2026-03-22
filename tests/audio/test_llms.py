"""Tests for the LLM context file generators in deep_thought.audio.llms."""

from __future__ import annotations

from pathlib import Path  # noqa: TC003

from deep_thought.audio.llms import (
    TranscriptSummary,
    _strip_frontmatter,
    format_duration,
    write_llms_full,
    write_llms_index,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_summary(
    name: str = "interview",
    md_relative_path: str = "interview/interview.md",
    source_file: str = "interview.mp3",
    duration_seconds: float = 330.0,
    word_count: int = 1200,
    content: str = "This is the transcript body.",
) -> TranscriptSummary:
    """Return a TranscriptSummary with sensible test defaults."""
    return TranscriptSummary(
        name=name,
        md_relative_path=md_relative_path,
        source_file=source_file,
        duration_seconds=duration_seconds,
        word_count=word_count,
        content=content,
    )


# ---------------------------------------------------------------------------
# _strip_frontmatter
# ---------------------------------------------------------------------------


class TestStripFrontmatter:
    def test_removes_frontmatter_block(self) -> None:
        """Text with a valid frontmatter block must have the block stripped."""
        text = "---\ntool: audio\nsource_file: audio.mp3\n---\n# Transcript\n\nBody text."
        result = _strip_frontmatter(text)
        assert "tool: audio" not in result
        assert "# Transcript" in result

    def test_returns_unchanged_when_no_frontmatter(self) -> None:
        """Text without a leading --- must be returned unchanged."""
        text = "# Transcript\n\nBody content."
        result = _strip_frontmatter(text)
        assert result == text

    def test_handles_text_with_only_frontmatter(self) -> None:
        """A string containing only a frontmatter block must return an empty string."""
        text = "---\ntool: audio\n---\n"
        result = _strip_frontmatter(text)
        assert result.strip() == ""

    def test_unclosed_frontmatter_returned_unchanged(self) -> None:
        """A --- that is never closed must leave the text unchanged."""
        text = "---\ntool: audio\n# Title"
        result = _strip_frontmatter(text)
        assert result == text

    def test_body_starts_after_closing_dashes(self) -> None:
        """The returned body must not include the --- delimiters."""
        text = "---\nkey: value\n---\nActual content here."
        result = _strip_frontmatter(text)
        assert "---" not in result
        assert "Actual content here." in result


# ---------------------------------------------------------------------------
# format_duration
# ---------------------------------------------------------------------------


class TestFormatDuration:
    def test_under_one_minute_shows_seconds(self) -> None:
        """Durations under 60 seconds must be expressed as seconds only."""
        result = format_duration(45.0)
        assert result == "45s"

    def test_exactly_one_minute(self) -> None:
        """Exactly 60 seconds must display as '1m 0s'."""
        result = format_duration(60.0)
        assert result == "1m 0s"

    def test_minutes_and_seconds(self) -> None:
        """Durations between 1 and 60 minutes must include minutes and seconds."""
        result = format_duration(330.0)
        assert result == "5m 30s"

    def test_exactly_one_hour(self) -> None:
        """Exactly one hour must display as '1h 0m'."""
        result = format_duration(3600.0)
        assert result == "1h 0m"

    def test_hours_and_minutes(self) -> None:
        """Durations over one hour must show hours and minutes, not seconds."""
        result = format_duration(5580.0)  # 1h 33m
        assert result == "1h 33m"

    def test_zero_seconds(self) -> None:
        """Zero seconds must display as '0s'."""
        result = format_duration(0.0)
        assert result == "0s"


# ---------------------------------------------------------------------------
# write_llms_index
# ---------------------------------------------------------------------------


class TestWriteLlmsIndex:
    def test_creates_llms_txt_file(self, tmp_path: Path) -> None:
        """write_llms_index must create .llms.txt in the output root."""
        summaries = [_make_summary()]
        output_path = write_llms_index(summaries, tmp_path)
        assert output_path == tmp_path / ".llms.txt"
        assert output_path.exists()

    def test_returns_path_to_written_file(self, tmp_path: Path) -> None:
        """The returned Path must point to the file that was written."""
        summaries = [_make_summary()]
        returned_path = write_llms_index(summaries, tmp_path)
        assert returned_path.is_file()

    def test_index_contains_header(self, tmp_path: Path) -> None:
        """The index must include a '# Transcript Index' heading."""
        write_llms_index([_make_summary()], tmp_path)
        content = (tmp_path / ".llms.txt").read_text(encoding="utf-8")
        assert "# Transcript Index" in content

    def test_index_contains_transcript_count(self, tmp_path: Path) -> None:
        """The index must state the total number of transcripts."""
        summaries = [
            _make_summary(name="a", md_relative_path="a/a.md"),
            _make_summary(name="b", md_relative_path="b/b.md"),
        ]
        write_llms_index(summaries, tmp_path)
        content = (tmp_path / ".llms.txt").read_text(encoding="utf-8")
        assert "2 transcripts" in content

    def test_index_entry_contains_name_and_path(self, tmp_path: Path) -> None:
        """Each entry must include the transcript name and relative path."""
        summary = _make_summary(name="talk", md_relative_path="talk/talk.md")
        write_llms_index([summary], tmp_path)
        content = (tmp_path / ".llms.txt").read_text(encoding="utf-8")
        assert "talk" in content
        assert "talk/talk.md" in content

    def test_index_entry_contains_duration_and_word_count(self, tmp_path: Path) -> None:
        """Each entry must include the duration and word count."""
        summary = _make_summary(duration_seconds=330.0, word_count=800)
        write_llms_index([summary], tmp_path)
        content = (tmp_path / ".llms.txt").read_text(encoding="utf-8")
        assert "800 words" in content
        # Duration should appear in some human-readable form
        assert "5m" in content

    def test_index_contains_processed_date(self, tmp_path: Path) -> None:
        """The index header must include a 'Processed by audio' line."""
        write_llms_index([_make_summary()], tmp_path)
        content = (tmp_path / ".llms.txt").read_text(encoding="utf-8")
        assert "Processed by audio" in content

    def test_creates_output_directory_if_missing(self, tmp_path: Path) -> None:
        """write_llms_index must create output_root if it does not exist."""
        new_dir = tmp_path / "new_output"
        write_llms_index([_make_summary()], new_dir)
        assert (new_dir / ".llms.txt").exists()


# ---------------------------------------------------------------------------
# write_llms_full
# ---------------------------------------------------------------------------


class TestWriteLlmsFull:
    def test_creates_llms_full_txt_file(self, tmp_path: Path) -> None:
        """write_llms_full must create .llms-full.txt in the output root."""
        summaries = [_make_summary()]
        output_path = write_llms_full(summaries, tmp_path)
        assert output_path == tmp_path / ".llms-full.txt"
        assert output_path.exists()

    def test_returns_path_to_written_file(self, tmp_path: Path) -> None:
        """The returned Path must point to the file that was written."""
        summaries = [_make_summary()]
        returned_path = write_llms_full(summaries, tmp_path)
        assert returned_path.is_file()

    def test_content_includes_transcript_name_as_heading(self, tmp_path: Path) -> None:
        """Each block must start with the transcript name as a markdown heading."""
        summaries = [_make_summary(name="keynote")]
        write_llms_full(summaries, tmp_path)
        content = (tmp_path / ".llms-full.txt").read_text(encoding="utf-8")
        assert "# keynote" in content

    def test_content_includes_metadata_line(self, tmp_path: Path) -> None:
        """Each block must include the Source, Duration, and Words metadata line."""
        summaries = [_make_summary(source_file="keynote.mp3", duration_seconds=300.0, word_count=500)]
        write_llms_full(summaries, tmp_path)
        content = (tmp_path / ".llms-full.txt").read_text(encoding="utf-8")
        assert "Source: keynote.mp3" in content
        assert "Words: 500" in content

    def test_content_includes_transcript_body(self, tmp_path: Path) -> None:
        """Each block must include the full transcript text."""
        summaries = [_make_summary(content="Important spoken words.")]
        write_llms_full(summaries, tmp_path)
        content = (tmp_path / ".llms-full.txt").read_text(encoding="utf-8")
        assert "Important spoken words." in content

    def test_multiple_transcripts_separated_by_divider(self, tmp_path: Path) -> None:
        """Multiple transcripts must be separated by --- dividers."""
        summaries = [
            _make_summary(name="alpha", md_relative_path="alpha/alpha.md"),
            _make_summary(name="beta", md_relative_path="beta/beta.md"),
        ]
        write_llms_full(summaries, tmp_path)
        content = (tmp_path / ".llms-full.txt").read_text(encoding="utf-8")
        assert "# alpha" in content
        assert "# beta" in content
        assert "---" in content

    def test_creates_output_directory_if_missing(self, tmp_path: Path) -> None:
        """write_llms_full must create output_root if it does not exist."""
        new_dir = tmp_path / "new_output"
        write_llms_full([_make_summary()], new_dir)
        assert (new_dir / ".llms-full.txt").exists()

    def test_empty_summaries_creates_file(self, tmp_path: Path) -> None:
        """An empty summaries list must still produce a (possibly empty) file."""
        output_path = write_llms_full([], tmp_path)
        assert output_path.exists()
