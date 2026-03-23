"""LLM context file generation for the GCal Tool.

Generates .llms.txt and .llms-full.txt files for calendar events,
controlled by the generate_llms_files configuration setting.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


def _strip_frontmatter(markdown_text: str) -> str:
    """Remove YAML frontmatter from a markdown string.

    Args:
        markdown_text: A markdown string that may start with --- delimited frontmatter.

    Returns:
        The markdown text with frontmatter removed.
    """
    if not markdown_text.startswith("---"):
        return markdown_text

    # Find the closing ---
    end_index = markdown_text.find("---", 3)
    if end_index == -1:
        return markdown_text

    return markdown_text[end_index + 3 :].strip()


def generate_llms_index(
    event_files: list[Path],
    calendar_name: str,
) -> str:
    """Generate a .llms.txt index of all event files for a calendar.

    Lists each file with its path and first non-empty line as a summary.

    Args:
        event_files: List of markdown file paths.
        calendar_name: The calendar name for the header.

    Returns:
        The .llms.txt content as a string.
    """
    lines = [f"# {calendar_name} — Event Index", ""]

    for file_path in event_files:
        text = file_path.read_text(encoding="utf-8")
        body = _strip_frontmatter(text)
        first_line = ""
        for line in body.splitlines():
            stripped = line.strip()
            if stripped:
                first_line = stripped[:120]
                break
        lines.append(f"- {file_path.name}: {first_line}")

    return "\n".join(lines) + "\n"


def generate_llms_full(
    event_files: list[Path],
    calendar_name: str,
) -> str:
    """Generate a .llms-full.txt with all event content concatenated.

    Each event is separated by a horizontal rule.

    Args:
        event_files: List of markdown file paths.
        calendar_name: The calendar name for the header.

    Returns:
        The .llms-full.txt content as a string.
    """
    sections = [f"# {calendar_name} — Full Event Content"]

    for file_path in event_files:
        text = file_path.read_text(encoding="utf-8")
        body = _strip_frontmatter(text)
        sections.append(f"\n---\n\n## {file_path.name}\n\n{body}")

    return "\n".join(sections) + "\n"


def write_llms_files(
    event_files: list[Path],
    output_dir: Path,
    calendar_name: str,
) -> None:
    """Write .llms.txt and .llms-full.txt files for a calendar.

    Files are placed in {output_dir}/{calendar_slug}/llm/.

    Args:
        event_files: List of markdown file paths for this calendar.
        output_dir: The root output directory.
        calendar_name: The calendar name (used for subdirectory and file naming).
    """
    if not event_files:
        return

    from deep_thought.gcal.output import _get_calendar_dir_name

    calendar_dir_name = _get_calendar_dir_name(calendar_name)
    llm_dir = output_dir / calendar_dir_name / "llm"
    llm_dir.mkdir(parents=True, exist_ok=True)

    slug = _get_calendar_dir_name(calendar_name)

    index_content = generate_llms_index(event_files, calendar_name)
    index_path = llm_dir / f"{slug}.llms.txt"
    index_path.write_text(index_content, encoding="utf-8")

    full_content = generate_llms_full(event_files, calendar_name)
    full_path = llm_dir / f"{slug}.llms-full.txt"
    full_path.write_text(full_content, encoding="utf-8")
