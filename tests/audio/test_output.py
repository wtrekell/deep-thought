"""Tests for the transcript output writer in deep_thought.audio.output."""

from __future__ import annotations

from pathlib import Path

import pytest

from deep_thought.audio.models import TranscriptSegment
from deep_thought.audio.output import (
    _build_frontmatter,
    format_paragraph_mode,
    format_segment_mode,
    format_timestamp,
    format_timestamp_mode,
    remove_fillers,
    write_transcript,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_segment(
    start: float = 0.0,
    end: float = 2.0,
    text: str = "Hello world.",
    speaker: str | None = None,
) -> TranscriptSegment:
    """Return a TranscriptSegment with sensible test defaults."""
    return TranscriptSegment(start=start, end=end, text=text, speaker=speaker)


# ---------------------------------------------------------------------------
# format_timestamp
# ---------------------------------------------------------------------------


class TestFormatTimestamp:
    def test_under_one_hour_uses_mm_ss(self) -> None:
        """Durations under one hour must use the [MM:SS] format."""
        result = format_timestamp(75.0)
        assert result == "[01:15]"

    def test_zero_seconds(self) -> None:
        """Zero seconds must produce [00:00]."""
        result = format_timestamp(0.0)
        assert result == "[00:00]"

    def test_exactly_one_hour_uses_hh_mm_ss(self) -> None:
        """Exactly one hour must switch to the [HH:MM:SS] format."""
        result = format_timestamp(3600.0)
        assert result == "[01:00:00]"

    def test_over_one_hour_uses_hh_mm_ss(self) -> None:
        """Durations over one hour must include the hours component."""
        result = format_timestamp(3661.0)
        assert result == "[01:01:01]"

    def test_large_duration(self) -> None:
        """A multi-hour duration must format correctly."""
        # 2h 3m 4s = 7384 seconds
        result = format_timestamp(7384.0)
        assert result == "[02:03:04]"

    def test_sub_minute_duration(self) -> None:
        """A duration under one minute must show zero minutes."""
        result = format_timestamp(45.0)
        assert result == "[00:45]"


# ---------------------------------------------------------------------------
# remove_fillers
# ---------------------------------------------------------------------------


class TestRemoveFillers:
    def test_removes_default_filler_um(self) -> None:
        """The default filler 'um' must be stripped from the text."""
        result = remove_fillers("So um I was thinking")
        assert "um" not in result

    def test_removes_default_filler_uh(self) -> None:
        """The default filler 'uh' must be stripped from the text."""
        result = remove_fillers("Uh yeah that sounds good")
        assert "uh" not in result.lower()

    def test_removes_multi_word_filler(self) -> None:
        """Multi-word fillers like 'you know' must be removed as a unit."""
        result = remove_fillers("It was, you know, pretty clear")
        assert "you know" not in result

    def test_custom_filler_list_is_used_when_provided(self) -> None:
        """When a custom filler list is given, only those words are removed."""
        result = remove_fillers("Basically um whatever", filler_words=["whatever"])
        assert "whatever" not in result
        # "um" from the default list must NOT be removed since we used a custom list
        assert "um" in result

    def test_custom_filler_list_empty_leaves_text_unchanged(self) -> None:
        """An empty custom filler list must leave the text unchanged."""
        original = "Um well actually that is fine"
        result = remove_fillers(original, filler_words=[])
        assert result == original

    def test_does_not_strip_filler_substring_inside_word(self) -> None:
        """'like' as a filler must not affect words that contain 'like' as a substring."""
        result = remove_fillers("It is likely that I like it")
        # "likely" must be preserved; only the standalone "like" may be removed
        assert "likely" in result

    def test_does_not_strip_okay_inside_word(self) -> None:
        """'okay' as a filler must not affect words that begin with 'okay'."""
        result = remove_fillers("The caretaker said okay")
        assert "caretaker" in result

    def test_whitespace_is_collapsed_after_removal(self) -> None:
        """Removing fillers must not leave double spaces in the output."""
        result = remove_fillers("I um uh think so")
        assert "  " not in result

    def test_case_insensitive_removal(self) -> None:
        """Filler removal must be case-insensitive."""
        result = remove_fillers("Um, yes. UM definitely.")
        assert "um" not in result.lower()


# ---------------------------------------------------------------------------
# format_paragraph_mode
# ---------------------------------------------------------------------------


class TestFormatParagraphMode:
    def test_consecutive_segments_joined_with_space(self) -> None:
        """Segments within the pause threshold must be joined as one paragraph."""
        segments = [
            _make_segment(start=0.0, end=1.0, text="Hello"),
            _make_segment(start=1.1, end=2.0, text="world."),
        ]
        result = format_paragraph_mode(segments, pause_threshold=1.5)
        assert result == "Hello world."

    def test_gap_exceeding_threshold_creates_new_paragraph(self) -> None:
        """A gap longer than pause_threshold must insert a blank line."""
        segments = [
            _make_segment(start=0.0, end=1.0, text="First paragraph."),
            _make_segment(start=4.0, end=5.0, text="Second paragraph."),
        ]
        result = format_paragraph_mode(segments, pause_threshold=1.5)
        assert "\n\n" in result
        assert "First paragraph." in result
        assert "Second paragraph." in result

    def test_speaker_change_triggers_paragraph_break(self) -> None:
        """A change in speaker label must start a new paragraph."""
        segments = [
            _make_segment(start=0.0, end=1.0, text="Hello there.", speaker="SPEAKER_00"),
            _make_segment(start=1.1, end=2.0, text="Hi back.", speaker="SPEAKER_01"),
        ]
        result = format_paragraph_mode(segments, pause_threshold=1.5)
        assert "\n\n" in result

    def test_same_speaker_no_paragraph_break(self) -> None:
        """Consecutive segments from the same speaker must not cause a paragraph break."""
        segments = [
            _make_segment(start=0.0, end=1.0, text="Keep going.", speaker="SPEAKER_00"),
            _make_segment(start=1.1, end=2.0, text="And more.", speaker="SPEAKER_00"),
        ]
        result = format_paragraph_mode(segments, pause_threshold=1.5)
        assert "\n\n" not in result

    def test_empty_segment_list_returns_empty_string(self) -> None:
        """An empty segment list must return an empty string."""
        result = format_paragraph_mode([])
        assert result == ""

    def test_single_segment_returns_its_text(self) -> None:
        """A single segment must return just its text without extra whitespace."""
        segments = [_make_segment(text="Only sentence.")]
        result = format_paragraph_mode(segments)
        assert result == "Only sentence."


# ---------------------------------------------------------------------------
# format_segment_mode
# ---------------------------------------------------------------------------


class TestFormatSegmentMode:
    def test_segment_without_speaker_has_no_prefix(self) -> None:
        """Segments with no speaker label must appear as plain text."""
        segments = [_make_segment(text="No speaker here.")]
        result = format_segment_mode(segments)
        assert result == "No speaker here."

    def test_segment_with_speaker_has_bracketed_prefix(self) -> None:
        """Segments with a speaker label must be prefixed with [Speaker]."""
        segments = [_make_segment(text="Hello.", speaker="SPEAKER_00")]
        result = format_segment_mode(segments)
        assert result == "[SPEAKER_00] Hello."

    def test_multiple_segments_one_per_line(self) -> None:
        """Multiple segments must be separated by newlines, one per line."""
        segments = [
            _make_segment(start=0.0, end=1.0, text="Line one."),
            _make_segment(start=1.0, end=2.0, text="Line two."),
        ]
        result = format_segment_mode(segments)
        lines = result.splitlines()
        assert len(lines) == 2
        assert lines[0] == "Line one."
        assert lines[1] == "Line two."

    def test_mixed_speaker_and_no_speaker(self) -> None:
        """Segments with and without speaker labels can be mixed in the output."""
        segments = [
            _make_segment(start=0.0, end=1.0, text="Labelled.", speaker="SPEAKER_01"),
            _make_segment(start=1.0, end=2.0, text="Unlabelled."),
        ]
        result = format_segment_mode(segments)
        lines = result.splitlines()
        assert lines[0] == "[SPEAKER_01] Labelled."
        assert lines[1] == "Unlabelled."

    def test_empty_segment_list_returns_empty_string(self) -> None:
        """An empty segment list must return an empty string."""
        result = format_segment_mode([])
        assert result == ""


# ---------------------------------------------------------------------------
# format_timestamp_mode
# ---------------------------------------------------------------------------


class TestFormatTimestampMode:
    def test_segment_prefixed_with_timestamp(self) -> None:
        """Each line must start with a [MM:SS] timestamp."""
        segments = [_make_segment(start=90.0, end=92.0, text="Ninety seconds in.")]
        result = format_timestamp_mode(segments)
        assert result == "[01:30] Ninety seconds in."

    def test_multiple_segments_each_on_own_line(self) -> None:
        """Multiple segments must produce one timestamped line each."""
        segments = [
            _make_segment(start=0.0, end=1.0, text="First."),
            _make_segment(start=60.0, end=61.0, text="Second."),
        ]
        result = format_timestamp_mode(segments)
        lines = result.splitlines()
        assert len(lines) == 2
        assert lines[0].startswith("[00:00]")
        assert lines[1].startswith("[01:00]")

    def test_empty_segment_list_returns_empty_string(self) -> None:
        """An empty segment list must return an empty string."""
        result = format_timestamp_mode([])
        assert result == ""

    def test_over_one_hour_uses_hh_mm_ss(self) -> None:
        """Segments starting at or after one hour must use [HH:MM:SS]."""
        segments = [_make_segment(start=3661.0, end=3663.0, text="Late in the file.")]
        result = format_timestamp_mode(segments)
        assert result.startswith("[01:01:01]")


# ---------------------------------------------------------------------------
# _build_frontmatter
# ---------------------------------------------------------------------------


class TestBuildFrontmatter:
    def test_frontmatter_contains_all_required_fields(self) -> None:
        """All standard frontmatter fields must appear in the output."""
        frontmatter = _build_frontmatter(
            source_file="interview.mp3",
            engine="mlx",
            model="large-v3-turbo",
            language="en",
            duration_seconds=330.0,
            speaker_count=2,
            output_mode="paragraph",
            processed_date="2026-03-22T00:00:00+00:00",
        )
        assert "tool: audio" in frontmatter
        assert "source_file: interview.mp3" in frontmatter
        assert "engine: mlx" in frontmatter
        assert "model: large-v3-turbo" in frontmatter
        assert "language: en" in frontmatter
        assert "duration_seconds: 330.0" in frontmatter
        assert "speaker_count: 2" in frontmatter
        assert "output_mode: paragraph" in frontmatter
        assert "processed_date: 2026-03-22T00:00:00+00:00" in frontmatter

    def test_frontmatter_wrapped_in_dashes(self) -> None:
        """The frontmatter block must start and end with --- delimiters."""
        frontmatter = _build_frontmatter(
            source_file="audio.mp3",
            engine="whisper",
            model="base",
            language="fr",
            duration_seconds=60.0,
            speaker_count=0,
            output_mode="segment",
            processed_date="2026-03-22T00:00:00+00:00",
        )
        lines = frontmatter.strip().splitlines()
        assert lines[0] == "---"
        assert lines[-1] == "---"

    def test_speaker_count_zero_omits_field(self) -> None:
        """When speaker_count is 0 (no diarization), the field must be absent."""
        frontmatter = _build_frontmatter(
            source_file="mono.mp3",
            engine="mlx",
            model="small",
            language="en",
            duration_seconds=120.0,
            speaker_count=0,
            output_mode="paragraph",
            processed_date="2026-03-22T00:00:00+00:00",
        )
        assert "speaker_count" not in frontmatter

    def test_speaker_count_nonzero_included(self) -> None:
        """When speaker_count is greater than 0, the field must be included."""
        frontmatter = _build_frontmatter(
            source_file="panel.mp3",
            engine="mlx",
            model="large-v3-turbo",
            language="en",
            duration_seconds=600.0,
            speaker_count=3,
            output_mode="paragraph",
            processed_date="2026-03-22T00:00:00+00:00",
        )
        assert "speaker_count: 3" in frontmatter


# ---------------------------------------------------------------------------
# write_transcript
# ---------------------------------------------------------------------------


class TestWriteTranscript:
    def test_creates_subdirectory_and_file(self, tmp_path: Path) -> None:
        """write_transcript must create output_root/{stem}/{stem}.md."""
        segments = [_make_segment(text="Test transcript.")]
        source_path = Path("/audio/interview.mp3")
        output_path = write_transcript(
            segments,
            source_path,
            tmp_path,
            engine="mlx",
            model="large-v3-turbo",
            language="en",
            duration_seconds=10.0,
            speaker_count=0,
            output_mode="paragraph",
        )
        assert output_path == tmp_path / "interview" / "interview.md"
        assert output_path.exists()

    def test_output_file_contains_frontmatter(self, tmp_path: Path) -> None:
        """The written file must begin with a YAML frontmatter block."""
        segments = [_make_segment(text="Content.")]
        source_path = Path("/audio/talk.mp3")
        output_path = write_transcript(
            segments,
            source_path,
            tmp_path,
            engine="whisper",
            model="small",
            language="de",
            duration_seconds=45.0,
            speaker_count=0,
            output_mode="segment",
        )
        content = output_path.read_text(encoding="utf-8")
        assert content.startswith("---\n")
        assert "tool: audio" in content
        assert "source_file: talk.mp3" in content

    def test_output_file_contains_transcript_body(self, tmp_path: Path) -> None:
        """The written file must contain the formatted transcript text."""
        segments = [_make_segment(text="Spoken words here.")]
        source_path = Path("/audio/notes.mp3")
        output_path = write_transcript(
            segments,
            source_path,
            tmp_path,
            engine="mlx",
            model="large-v3-turbo",
            language="en",
            duration_seconds=5.0,
            speaker_count=0,
            output_mode="paragraph",
        )
        content = output_path.read_text(encoding="utf-8")
        assert "Spoken words here." in content

    def test_returns_path_to_written_file(self, tmp_path: Path) -> None:
        """write_transcript must return the path to the file that was written."""
        segments = [_make_segment(text="Hello.")]
        source_path = Path("/audio/hello.mp3")
        returned_path = write_transcript(
            segments,
            source_path,
            tmp_path,
            engine="mlx",
            model="base",
            language="en",
            duration_seconds=2.0,
            speaker_count=0,
            output_mode="paragraph",
        )
        assert returned_path.is_file()
        assert returned_path.name == "hello.md"

    def test_creates_output_directory_when_missing(self, tmp_path: Path) -> None:
        """write_transcript must create parent directories that do not exist."""
        deep_output_root = tmp_path / "nested" / "export"
        segments = [_make_segment(text="Deep path test.")]
        source_path = Path("/audio/deep.mp3")
        output_path = write_transcript(
            segments,
            source_path,
            deep_output_root,
            engine="mlx",
            model="large-v3-turbo",
            language="en",
            duration_seconds=3.0,
            speaker_count=0,
            output_mode="paragraph",
        )
        assert output_path.exists()

    @pytest.mark.parametrize("output_mode", ["paragraph", "segment", "timestamp"])
    def test_all_output_modes_produce_valid_file(self, tmp_path: Path, output_mode: str) -> None:
        """Every output mode must produce a non-empty file without error."""
        segments = [
            _make_segment(start=0.0, end=2.0, text="First segment."),
            _make_segment(start=3.0, end=5.0, text="Second segment."),
        ]
        source_path = Path(f"/audio/test_{output_mode}.mp3")
        output_path = write_transcript(
            segments,
            source_path,
            tmp_path,
            engine="mlx",
            model="large-v3-turbo",
            language="en",
            duration_seconds=5.0,
            speaker_count=0,
            output_mode=output_mode,
        )
        assert output_path.exists()
        content = output_path.read_text(encoding="utf-8")
        assert len(content) > 0
