"""Markdown transcript output with YAML frontmatter.

Generates output markdown files from transcription results. Each output file
lives in its own subdirectory inside the output root and includes a YAML
frontmatter block with metadata about the source file and transcription run.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path  # noqa: TC003
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from deep_thought.audio.models import TranscriptSegment

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_FILLER_WORDS: list[str] = [
    "um",
    "uh",
    "like",
    "you know",
    "I mean",
    "so",
    "actually",
    "basically",
    "right",
    "okay",
]

# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def format_timestamp(seconds: float) -> str:
    """Convert a duration in seconds to a bracketed timestamp string.

    Uses [HH:MM:SS] format when the duration is one hour or longer, and
    [MM:SS] format for shorter durations.

    Args:
        seconds: Duration in seconds (non-negative).

    Returns:
        A string in the form ``[MM:SS]`` or ``[HH:MM:SS]``.
    """
    total_seconds = int(seconds)
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    remaining_seconds = total_seconds % 60

    if hours > 0:
        return f"[{hours:02d}:{minutes:02d}:{remaining_seconds:02d}]"
    return f"[{minutes:02d}:{remaining_seconds:02d}]"


def remove_fillers(text: str, filler_words: list[str] | None = None) -> str:
    """Remove filler words from text using word-boundary matching.

    Uses regex word boundaries so that filler substrings inside real words
    are never removed (e.g. "like" does not affect "likely").

    Args:
        text: The transcript text to clean.
        filler_words: List of filler words/phrases to remove. When None,
                      the default list is used (um, uh, like, you know, etc.).

    Returns:
        The cleaned text with filler words removed and extra whitespace collapsed.
    """
    fillers_to_remove = filler_words if filler_words is not None else _DEFAULT_FILLER_WORDS

    cleaned_text = text
    for filler_phrase in fillers_to_remove:
        # Build a case-insensitive pattern with word boundaries on each end.
        # For multi-word fillers (e.g. "you know") we anchor both the first
        # and last word to word boundaries.
        escaped_phrase = re.escape(filler_phrase)
        pattern = rf"\b{escaped_phrase}\b"
        cleaned_text = re.sub(pattern, "", cleaned_text, flags=re.IGNORECASE)

    # Collapse extra whitespace introduced by removals
    cleaned_text = re.sub(r" {2,}", " ", cleaned_text).strip()
    return cleaned_text


# ---------------------------------------------------------------------------
# Output mode formatters
# ---------------------------------------------------------------------------


def format_paragraph_mode(
    segments: list[TranscriptSegment],
    pause_threshold: float = 1.5,
) -> str:
    """Format segments as continuous prose with paragraph breaks at pauses.

    Consecutive segments that are separated by a gap shorter than
    ``pause_threshold`` are joined with a single space. Gaps exceeding
    the threshold — or a change in speaker label — insert a blank line to
    start a new paragraph.

    Args:
        segments: Ordered list of transcript segments.
        pause_threshold: Silence gap in seconds that triggers a paragraph break.

    Returns:
        Formatted prose string with blank-line paragraph breaks.
    """
    if not segments:
        return ""

    paragraphs: list[list[str]] = [[segments[0].text.strip()]]
    previous_segment = segments[0]

    for current_segment in segments[1:]:
        gap_between_segments = current_segment.start - previous_segment.end
        speaker_changed = (
            current_segment.speaker is not None
            and previous_segment.speaker is not None
            and current_segment.speaker != previous_segment.speaker
        )
        pause_exceeded = gap_between_segments > pause_threshold

        if pause_exceeded or speaker_changed:
            paragraphs.append([current_segment.text.strip()])
        else:
            paragraphs[-1].append(current_segment.text.strip())

        previous_segment = current_segment

    return "\n\n".join(" ".join(paragraph_words) for paragraph_words in paragraphs)


def format_segment_mode(segments: list[TranscriptSegment]) -> str:
    """Format segments as one line each, with an optional speaker prefix.

    When a segment has a speaker label set, the line is prefixed with
    ``[Speaker Label]``. Segments without a speaker label are written
    as plain text.

    Args:
        segments: Ordered list of transcript segments.

    Returns:
        Newline-separated string, one segment per line.
    """
    lines: list[str] = []
    for segment in segments:
        segment_text = segment.text.strip()
        if segment.speaker is not None:
            lines.append(f"[{segment.speaker}] {segment_text}")
        else:
            lines.append(segment_text)
    return "\n".join(lines)


def format_timestamp_mode(segments: list[TranscriptSegment]) -> str:
    """Format segments with a timestamp prefix on each line.

    Each line begins with the segment start time formatted as ``[MM:SS]``
    or ``[HH:MM:SS]``, followed by the segment text.

    Args:
        segments: Ordered list of transcript segments.

    Returns:
        Newline-separated string, one segment per line with timestamp prefix.
    """
    lines: list[str] = []
    for segment in segments:
        timestamp_label = format_timestamp(segment.start)
        lines.append(f"{timestamp_label} {segment.text.strip()}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Frontmatter builder
# ---------------------------------------------------------------------------


def _build_frontmatter(
    source_file: str,
    engine: str,
    model: str,
    language: str,
    duration_seconds: float,
    speaker_count: int,
    output_mode: str,
    processed_date: str,
) -> str:
    """Build the YAML frontmatter block as a string.

    Only includes fields that have non-null values. speaker_count is omitted
    when zero (i.e., diarization was not performed).

    Args:
        source_file: Original audio filename.
        engine: Transcription engine used (e.g. "mlx", "whisper").
        model: Model identifier (e.g. "large-v3-turbo").
        language: Detected or configured language code.
        duration_seconds: Total audio duration in seconds.
        speaker_count: Number of identified speakers; 0 means no diarization.
        output_mode: Formatting mode used ("paragraph", "segment", "timestamp").
        processed_date: ISO 8601 datetime string for when processing occurred.

    Returns:
        A string containing the full YAML frontmatter block including the
        opening and closing ``---`` delimiters and a trailing newline.
    """
    lines: list[str] = ["---"]
    lines.append("tool: audio")
    lines.append(f"source_file: {source_file}")
    lines.append(f"engine: {engine}")
    lines.append(f"model: {model}")
    lines.append(f"language: {language}")
    lines.append(f"duration_seconds: {duration_seconds}")
    if speaker_count > 0:
        lines.append(f"speaker_count: {speaker_count}")
    lines.append(f"output_mode: {output_mode}")
    lines.append(f"processed_date: {processed_date}")
    lines.append("---")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Public write API
# ---------------------------------------------------------------------------


def write_transcript(
    segments: list[TranscriptSegment],
    source_path: Path,
    output_root: Path,
    *,
    engine: str,
    model: str,
    language: str,
    duration_seconds: float,
    speaker_count: int,
    output_mode: str,
    pause_threshold: float = 1.5,
) -> Path:
    """Write a complete markdown transcript file with YAML frontmatter.

    Creates a subdirectory named after the source file (without extension)
    inside output_root, then writes ``{stem}/{stem}.md``.

    The formatting function is selected based on ``output_mode``:
    - "paragraph": prose with paragraph breaks at pauses and speaker changes
    - "segment": one line per segment, with optional speaker prefix
    - "timestamp": one line per segment, each prefixed with a timestamp

    Args:
        segments: Ordered list of transcript segments to format.
        source_path: Original audio file path (used to derive the output name).
        output_root: Root directory for output; a subdirectory will be created.
        engine: Transcription engine identifier.
        model: Model identifier.
        language: Language code.
        duration_seconds: Total audio duration.
        speaker_count: Number of identified speakers (0 = no diarization).
        output_mode: One of "paragraph", "segment", or "timestamp".
        pause_threshold: Seconds of silence that trigger a paragraph break
                         (only used in "paragraph" mode).

    Returns:
        The Path to the written markdown file.
    """
    document_stem = source_path.stem
    output_dir = output_root / document_stem
    output_dir.mkdir(parents=True, exist_ok=True)

    if output_mode == "segment":
        formatted_body = format_segment_mode(segments)
    elif output_mode == "timestamp":
        formatted_body = format_timestamp_mode(segments)
    else:
        # Default to paragraph mode for "paragraph" or any unrecognised value
        formatted_body = format_paragraph_mode(segments, pause_threshold=pause_threshold)

    processed_date = datetime.now(tz=UTC).isoformat()
    frontmatter_block = _build_frontmatter(
        source_file=source_path.name,
        engine=engine,
        model=model,
        language=language,
        duration_seconds=duration_seconds,
        speaker_count=speaker_count,
        output_mode=output_mode,
        processed_date=processed_date,
    )

    output_file_path = output_dir / f"{document_stem}.md"
    output_file_path.write_text(frontmatter_block + "\n" + formatted_body, encoding="utf-8")

    return output_file_path
