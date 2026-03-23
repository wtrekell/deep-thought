"""Markdown output generation for the GCal Tool.

Generates markdown files with YAML frontmatter from calendar events.
Supports both calendar-organized and flat output directory modes.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from deep_thought.gcal.models import EventLocal


# ---------------------------------------------------------------------------
# Slug helpers
# ---------------------------------------------------------------------------

_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
_MAX_SLUG_LENGTH = 80


def _slugify(text: str, max_length: int = _MAX_SLUG_LENGTH) -> str:
    """Convert text to a filesystem-safe slug.

    Lowercases, replaces non-alphanumeric runs with hyphens,
    strips leading/trailing hyphens, and truncates.

    Args:
        text: The text to slugify.
        max_length: Maximum slug length.

    Returns:
        A filesystem-safe slug, or "no-title" if the result is empty.
    """
    slug = _NON_ALNUM_RE.sub("-", text.lower()).strip("-")
    slug = slug[:max_length].rstrip("-")
    return slug if slug else "no-title"


# ---------------------------------------------------------------------------
# Frontmatter generation
# ---------------------------------------------------------------------------


def _escape_yaml_value(value: str) -> str:
    """Escape a string for safe inclusion in YAML double-quoted values.

    Args:
        value: The raw string value.

    Returns:
        The escaped string (backslashes and double quotes escaped).
    """
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _build_event_frontmatter(event: EventLocal) -> str:
    """Build YAML frontmatter from an EventLocal.

    Only includes fields with non-null, non-empty values.

    Args:
        event: An EventLocal dataclass instance.

    Returns:
        A YAML frontmatter string including the --- delimiters.
    """
    lines = ["---"]
    lines.append("tool: gcal")
    lines.append(f"event_id: {event.event_id}")
    lines.append(f"calendar_id: {event.calendar_id}")

    escaped_summary = _escape_yaml_value(event.summary)
    lines.append(f'summary: "{escaped_summary}"')

    lines.append(f"start: {event.start_time}")
    lines.append(f"end: {event.end_time}")
    lines.append(f"all_day: {str(event.all_day).lower()}")

    if event.location:
        escaped_location = _escape_yaml_value(event.location)
        lines.append(f'location: "{escaped_location}"')

    lines.append(f"status: {event.status}")

    if event.organizer:
        escaped_organizer = _escape_yaml_value(event.organizer)
        lines.append(f'organizer: "{escaped_organizer}"')

    if event.attendees:
        try:
            attendee_list = json.loads(event.attendees)
            if attendee_list:
                lines.append("attendees:")
                for attendee in attendee_list:
                    email = attendee.get("email", "") if isinstance(attendee, dict) else str(attendee)
                    if email:
                        lines.append(f'  - "{email}"')
        except (json.JSONDecodeError, TypeError):
            pass

    if event.recurrence:
        try:
            recurrence_list = json.loads(event.recurrence)
            if recurrence_list:
                lines.append("recurrence:")
                for rule in recurrence_list:
                    lines.append(f'  - "{rule}"')
        except (json.JSONDecodeError, TypeError):
            pass

    if event.html_link:
        escaped_html_link = _escape_yaml_value(event.html_link)
        lines.append(f'html_link: "{escaped_html_link}"')

    synced_date = datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines.append(f"synced_date: {synced_date}")

    lines.append("---")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Markdown generation
# ---------------------------------------------------------------------------


def generate_event_markdown(event: EventLocal) -> str:
    """Generate a complete markdown document for a single event.

    Args:
        event: An EventLocal dataclass instance.

    Returns:
        A complete markdown string with YAML frontmatter and description body.
    """
    frontmatter = _build_event_frontmatter(event)
    body = event.description or ""
    return f"{frontmatter}\n\n{body}\n"


# ---------------------------------------------------------------------------
# Filename and path helpers
# ---------------------------------------------------------------------------


def _build_filename(event: EventLocal) -> str:
    """Build a filename for an event's markdown file.

    Format: {date}_{summary_slug}.md

    Args:
        event: An EventLocal dataclass instance.

    Returns:
        The filename string.
    """
    # Extract date portion from start_time (handles both date and datetime formats)
    date_str = event.start_time[:10]
    summary_slug = _slugify(event.summary)
    return f"{date_str}_{summary_slug}.md"


def _get_calendar_dir_name(calendar_summary: str) -> str:
    """Slugify a calendar summary for use as a directory name.

    Args:
        calendar_summary: The calendar display name.

    Returns:
        A filesystem-safe directory name.
    """
    return _slugify(calendar_summary)


# ---------------------------------------------------------------------------
# File writing
# ---------------------------------------------------------------------------


def write_event_file(
    content: str,
    output_dir: Path,
    calendar_name: str,
    event: EventLocal,
    *,
    flat_output: bool = False,
) -> Path:
    """Write a single event's markdown content to a file.

    Args:
        content: The full markdown content to write.
        output_dir: The root output directory.
        calendar_name: The calendar display name (used as subdirectory).
        event: The EventLocal for filename generation.
        flat_output: If True, write directly to output_dir without subdirectory.

    Returns:
        The Path to the written file.
    """
    filename = _build_filename(event)

    if flat_output:
        target_dir = output_dir
    else:
        calendar_dir_name = _get_calendar_dir_name(calendar_name)
        target_dir = output_dir / calendar_dir_name

    target_dir.mkdir(parents=True, exist_ok=True)

    file_path = target_dir / filename
    file_path.write_text(content, encoding="utf-8")
    return file_path


def delete_event_file(
    output_dir: Path,
    calendar_name: str,
    event: EventLocal,
    *,
    flat_output: bool = False,
) -> bool:
    """Delete an event's exported markdown file if it exists.

    Args:
        output_dir: The root output directory.
        calendar_name: The calendar display name (used as subdirectory).
        event: The EventLocal for filename generation.
        flat_output: If True, look directly in output_dir.

    Returns:
        True if a file was deleted, False if it did not exist.
    """
    filename = _build_filename(event)

    if flat_output:
        file_path = output_dir / filename
    else:
        calendar_dir_name = _get_calendar_dir_name(calendar_name)
        file_path = output_dir / calendar_dir_name / filename

    if file_path.exists():
        file_path.unlink()
        return True
    return False


def get_event_files_for_calendar(
    output_dir: Path,
    calendar_name: str,
    *,
    flat_output: bool = False,
) -> list[Path]:
    """List all markdown event files for a calendar directory.

    Args:
        output_dir: The root output directory.
        calendar_name: The calendar display name.
        flat_output: If True, list from output_dir directly.

    Returns:
        Sorted list of .md file paths.
    """
    if flat_output:
        target_dir = output_dir
    else:
        calendar_dir_name = _get_calendar_dir_name(calendar_name)
        target_dir = output_dir / calendar_dir_name

    if not target_dir.exists():
        return []

    return sorted(target_dir.glob("*.md"))
