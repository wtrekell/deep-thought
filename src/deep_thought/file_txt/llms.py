"""Aggregate LLM context file generator for the file-txt tool.

Produces two output files from a collection of processed documents:
- llms-full.txt: complete markdown content of every document, concatenated
- llms.txt: a navigable index with one entry per document

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
class DocumentSummary:
    """Metadata and content for one processed document."""

    name: str
    md_relative_path: str  # relative to output root, e.g. "report/report.md"
    source_file: str
    file_type: str
    word_count: int
    content: str  # full markdown content with frontmatter stripped


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _strip_frontmatter(markdown_text: str) -> str:
    """Remove YAML frontmatter from a markdown string.

    Frontmatter is defined as content between the first two ``---`` lines
    at the very beginning of the file. If no valid frontmatter block is
    found the text is returned unchanged.

    Args:
        markdown_text: Full markdown content, possibly starting with ``---``.

    Returns:
        The markdown body with the frontmatter block removed.
    """
    lines = markdown_text.splitlines()
    if not lines or lines[0].strip() != "---":
        return markdown_text

    closing_index: int | None = None
    for line_index in range(1, len(lines)):
        if lines[line_index].strip() == "---":
            closing_index = line_index
            break

    if closing_index is None:
        return markdown_text

    body_lines = lines[closing_index + 1 :]
    return "\n".join(body_lines).lstrip("\n")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def write_llms_full(summaries: list[DocumentSummary], output_root: Path) -> Path:
    """Write the llms-full.txt aggregate file to output_root.

    Each document is written as a block separated by a ``---`` divider.
    Within each block the document name, source metadata, and complete
    markdown body are included.

    Args:
        summaries: Ordered list of DocumentSummary objects, one per processed
                   document.
        output_root: Directory to write llms-full.txt into.

    Returns:
        The Path to the written llms-full.txt file.
    """
    output_root.mkdir(parents=True, exist_ok=True)
    output_path = output_root / "llms-full.txt"

    processed_date = datetime.now(tz=UTC).isoformat()
    blocks: list[str] = []

    for summary in summaries:
        block_lines: list[str] = [
            f"# {summary.name}",
            "",
            f"source: {summary.source_file}",
            f"type: {summary.file_type}",
            f"processed: {processed_date}",
            "",
            summary.content,
            "",
            "---",
        ]
        blocks.append("\n".join(block_lines))

    output_path.write_text("\n".join(blocks), encoding="utf-8")
    return output_path


def write_llms_index(summaries: list[DocumentSummary], output_root: Path) -> Path:
    """Write the llms.txt index file to output_root.

    The index contains one line per document with a link to its markdown
    file, the source filename, file type, and word count.

    Args:
        summaries: Ordered list of DocumentSummary objects, one per processed
                   document.
        output_root: Directory to write llms.txt into.

    Returns:
        The Path to the written llms.txt file.
    """
    output_root.mkdir(parents=True, exist_ok=True)
    output_path = output_root / "llms.txt"

    processed_date = datetime.now(tz=UTC).date().isoformat()
    document_count = len(summaries)

    lines: list[str] = [
        "# Document Index",
        "",
        f"> Processed by file-txt on {processed_date}. {document_count} documents.",
        "",
        "## Documents",
        "",
    ]

    for summary in summaries:
        entry = (
            f"- [{summary.name}.md]({summary.md_relative_path}): "
            f"{summary.source_file}, {summary.file_type}, {summary.word_count} words"
        )
        lines.append(entry)

    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path
