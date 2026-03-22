"""Generate .llms.txt and .llms-full.txt files for LLM consumption.

Produces two aggregate context files from a collection of processed transcripts:
- .llms.txt: a navigable index with one entry per transcript
- .llms-full.txt: complete transcript content of every document, concatenated

These files are intended to be loaded by LLMs as context. The format
prioritises machine parseability over human readability.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path  # noqa: TC003

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class TranscriptSummary:
    """Metadata and content for one processed transcript."""

    name: str
    """Display name for the transcript (typically the source filename without extension)."""

    md_relative_path: str
    """Relative path to the .md file from the output root, e.g. "interview/interview.md"."""

    source_file: str
    """Original audio file name, e.g. "interview.mp3"."""

    duration_seconds: float
    """Total audio duration in seconds."""

    word_count: int
    """Approximate word count of the transcript text."""

    content: str
    """Full transcript text with frontmatter stripped."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _strip_frontmatter(text: str) -> str:
    """Remove YAML frontmatter from a markdown string.

    Frontmatter is defined as content between the first two ``---`` lines
    at the very beginning of the file. If no valid frontmatter block is
    found the text is returned unchanged.

    Args:
        text: Full markdown content, possibly starting with ``---``.

    Returns:
        The markdown body with the frontmatter block removed.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return text

    closing_index: int | None = None
    for line_index in range(1, len(lines)):
        if lines[line_index].strip() == "---":
            closing_index = line_index
            break

    if closing_index is None:
        return text

    body_lines = lines[closing_index + 1 :]
    return "\n".join(body_lines).lstrip("\n")


def format_duration(seconds: float) -> str:
    """Format a duration in seconds as a human-readable string.

    Produces concise output like "5m 30s" or "1h 23m". Hours are only shown
    when the duration is one hour or longer. Seconds are only shown when the
    duration is under one hour.

    Args:
        seconds: Duration in seconds (non-negative).

    Returns:
        Human-readable duration string, e.g. "45s", "5m 30s", "1h 23m".
    """
    total_seconds = int(seconds)
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    remaining_seconds = total_seconds % 60

    if hours > 0:
        return f"{hours}h {minutes}m"
    if minutes > 0:
        return f"{minutes}m {remaining_seconds}s"
    return f"{remaining_seconds}s"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def write_llms_index(summaries: list[TranscriptSummary], output_root: Path) -> Path:
    """Write the .llms.txt navigation index to output_root.

    Each transcript is listed as a single entry showing the relative path to
    the markdown file, the audio duration, and the word count.

    Args:
        summaries: Ordered list of TranscriptSummary objects, one per transcript.
        output_root: Directory to write .llms.txt into.

    Returns:
        The Path to the written .llms.txt file.
    """
    output_root.mkdir(parents=True, exist_ok=True)
    output_path = output_root / ".llms.txt"

    processed_date = datetime.now(tz=UTC).date().isoformat()
    transcript_count = len(summaries)

    lines: list[str] = [
        "# Transcript Index",
        "",
        f"> Processed by audio on {processed_date}. {transcript_count} transcripts.",
        "",
        "## Transcripts",
        "",
    ]

    for summary in summaries:
        human_duration = format_duration(summary.duration_seconds)
        entry = f"- {summary.name}: {summary.md_relative_path} ({human_duration} | {summary.word_count} words)"
        lines.append(entry)

    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


def write_llms_full(summaries: list[TranscriptSummary], output_root: Path) -> Path:
    """Write the .llms-full.txt aggregate file to output_root.

    Each transcript is written as a block with a heading, metadata line, and
    the full transcript body, separated from the next entry by a ``---`` divider.

    Args:
        summaries: Ordered list of TranscriptSummary objects, one per transcript.
        output_root: Directory to write .llms-full.txt into.

    Returns:
        The Path to the written .llms-full.txt file.
    """
    output_root.mkdir(parents=True, exist_ok=True)
    output_path = output_root / ".llms-full.txt"

    blocks: list[str] = []

    for summary in summaries:
        human_duration = format_duration(summary.duration_seconds)
        block_lines: list[str] = [
            f"# {summary.name}",
            f"Source: {summary.source_file} | Duration: {human_duration} | Words: {summary.word_count}",
            "",
            summary.content,
            "",
            "---",
        ]
        blocks.append("\n".join(block_lines))

    output_path.write_text("\n".join(blocks), encoding="utf-8")
    return output_path
