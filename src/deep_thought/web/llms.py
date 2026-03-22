"""Aggregate LLM context file generator for the web crawl tool.

Produces two output files from a collection of crawled pages:
- llms-full.txt: complete markdown content of every page, concatenated
- llms.txt: a navigable index with one entry per page

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
class PageSummary:
    """Metadata and content for one crawled and converted web page."""

    title: str | None
    url: str
    md_relative_path: str  # relative to output root
    mode: str
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


def write_llms_full(summaries: list[PageSummary], output_root: Path) -> Path:
    """Write the llms-full.txt aggregate file to output_root.

    Each page is written as a block separated by a ``---`` divider.
    Within each block the page title (or URL), source metadata, and
    complete markdown body are included.

    Args:
        summaries: Ordered list of PageSummary objects, one per crawled page.
        output_root: Directory to write llms-full.txt into.

    Returns:
        The Path to the written llms-full.txt file.
    """
    output_root.mkdir(parents=True, exist_ok=True)
    output_path = output_root / "llms-full.txt"

    crawled_date = datetime.now(tz=UTC).isoformat()
    blocks: list[str] = []

    for summary in summaries:
        page_heading = summary.title if summary.title else summary.url
        block_lines: list[str] = [
            f"# {page_heading}",
            "",
            f"url: {summary.url}",
            f"mode: {summary.mode}",
            f"crawled: {crawled_date}",
            "",
            summary.content,
            "",
            "---",
        ]
        blocks.append("\n".join(block_lines))

    output_path.write_text("\n".join(blocks), encoding="utf-8")
    return output_path


def write_llms_index(summaries: list[PageSummary], output_root: Path) -> Path:
    """Write the llms.txt index file to output_root.

    The index contains one line per page with a link to its markdown file,
    the source URL, and word count.

    Args:
        summaries: Ordered list of PageSummary objects, one per crawled page.
        output_root: Directory to write llms.txt into.

    Returns:
        The Path to the written llms.txt file.
    """
    output_root.mkdir(parents=True, exist_ok=True)
    output_path = output_root / "llms.txt"

    crawled_date = datetime.now(tz=UTC).date().isoformat()
    page_count = len(summaries)

    lines: list[str] = [
        "# Page Index",
        "",
        f"> Crawled by web on {crawled_date}. {page_count} pages.",
        "",
        "## Pages",
        "",
    ]

    for summary in summaries:
        page_label = summary.title if summary.title else summary.url
        entry = f"- [{page_label}.md]({summary.md_relative_path}): {summary.url}, {summary.word_count} words"
        lines.append(entry)

    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path
