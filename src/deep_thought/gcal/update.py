"""Event update from markdown frontmatter for the GCal Tool."""

from __future__ import annotations

import logging
import sqlite3  # noqa: TC003 — sqlite3.Connection is used at runtime in run_update
from pathlib import Path
from typing import Any

from deep_thought.gcal.create import _is_date_only, parse_event_frontmatter
from deep_thought.gcal.db.queries import get_calendar, upsert_event
from deep_thought.gcal.models import EventLocal, UpdateResult
from deep_thought.gcal.output import generate_event_markdown, write_event_file

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Field diffing
# ---------------------------------------------------------------------------


def _diff_event_fields(
    frontmatter: dict[str, Any],
    existing_event: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    """Compare frontmatter fields against an existing Calendar API event.

    Builds a minimal patch body containing only the fields that differ from
    the current API state. Handles the date vs dateTime distinction for
    start/end comparisons.

    Args:
        frontmatter: Parsed frontmatter dict from the local markdown file.
        existing_event: The current event dict from the Calendar API.

    Returns:
        A tuple of (patch_body, fields_changed). patch_body contains only
        changed fields in API format. fields_changed lists the field names
        that were modified. Both are empty when no differences are detected.
    """
    patch_body: dict[str, Any] = {}
    fields_changed: list[str] = []

    # --- Summary ---
    frontmatter_summary: str = str(frontmatter.get("summary", ""))
    existing_summary: str = existing_event.get("summary", "")
    if frontmatter_summary != existing_summary:
        patch_body["summary"] = frontmatter_summary
        fields_changed.append("summary")

    # --- Start time ---
    start_value = str(frontmatter["start"])
    if _is_date_only(start_value):
        new_start: dict[str, str] = {"date": start_value}
    else:
        new_start = {"dateTime": start_value}

    existing_start: dict[str, str] = existing_event.get("start", {})
    if new_start != existing_start:
        patch_body["start"] = new_start
        fields_changed.append("start")

    # --- End time ---
    end_value = str(frontmatter["end"])
    if _is_date_only(end_value):
        new_end: dict[str, str] = {"date": end_value}
    else:
        new_end = {"dateTime": end_value}

    existing_end: dict[str, str] = existing_event.get("end", {})
    if new_end != existing_end:
        patch_body["end"] = new_end
        fields_changed.append("end")

    # --- Location ---
    frontmatter_location: str | None = frontmatter.get("location")
    existing_location: str | None = existing_event.get("location")
    if frontmatter_location != existing_location:
        if frontmatter_location is not None:
            patch_body["location"] = frontmatter_location
        else:
            # Sending an empty string clears the field in the Calendar API
            patch_body["location"] = ""
        fields_changed.append("location")

    # --- Description ---
    frontmatter_description: str | None = frontmatter.get("description")
    existing_description: str | None = existing_event.get("description")
    if frontmatter_description != existing_description:
        patch_body["description"] = frontmatter_description if frontmatter_description is not None else ""
        fields_changed.append("description")

    # --- Attendees ---
    raw_attendees: list[str] | None = frontmatter.get("attendees")
    new_attendees: list[dict[str, str]] | None = (
        [{"email": email_address} for email_address in raw_attendees] if raw_attendees else None
    )
    existing_attendees: list[dict[str, Any]] | None = existing_event.get("attendees")
    if new_attendees != existing_attendees:
        patch_body["attendees"] = new_attendees if new_attendees is not None else []
        fields_changed.append("attendees")

    # --- Recurrence ---
    raw_recurrence: list[str] | None = frontmatter.get("recurrence")
    existing_recurrence: list[str] | None = existing_event.get("recurrence")
    if raw_recurrence != existing_recurrence:
        patch_body["recurrence"] = raw_recurrence if raw_recurrence is not None else []
        fields_changed.append("recurrence")

    return patch_body, fields_changed


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def run_update(
    client: Any,
    config: Any,
    db_conn: sqlite3.Connection,
    file_path: Path,
    *,
    dry_run: bool = False,
    output_dir: Path | None = None,
) -> UpdateResult:
    """Update an existing Google Calendar event from a markdown frontmatter file.

    Parses frontmatter from file_path, fetches the current event from the API,
    diffs the fields, and issues a PATCH request for any changes. Persists the
    updated event to the local database and rewrites the markdown file.

    Args:
        client: A GcalClient (or compatible mock) with get_event and patch_event methods.
        config: A GcalConfig with output_dir and flat_output settings.
        db_conn: An open SQLite connection for persisting the updated event.
        file_path: Path to the markdown file containing event frontmatter.
        dry_run: When True, compute the diff but skip the API call and DB write.
        output_dir: Override the output directory from config. If None, uses
                    config.output_dir.

    Returns:
        An UpdateResult with event_id, html_link, and fields_changed populated.
        fields_changed is an empty list when no differences were detected.

    Raises:
        ValueError: If the frontmatter does not contain an event_id field.
    """
    frontmatter, body_text = parse_event_frontmatter(file_path)

    event_id_raw: Any = frontmatter.get("event_id")
    if not event_id_raw:
        raise ValueError(f"Missing required 'event_id' field in frontmatter: {file_path}")
    event_id: str = str(event_id_raw)

    calendar_id: str = str(frontmatter.get("calendar_id", "primary"))

    logger.debug("Fetching current event '%s' from calendar '%s'", event_id, calendar_id)
    existing_api_event: dict[str, Any] = client.get_event(calendar_id, event_id)

    patch_body, fields_changed = _diff_event_fields(frontmatter, existing_api_event)

    existing_html_link: str = existing_api_event.get("htmlLink", "")

    if not fields_changed:
        logger.info("No changes detected for event '%s' — skipping update.", event_id)
        return UpdateResult(event_id=event_id, html_link=existing_html_link, fields_changed=[])

    if dry_run:
        logger.info(
            "Dry run — skipping Calendar API patch for event '%s'. Would change: %s",
            event_id,
            fields_changed,
        )
        return UpdateResult(event_id=event_id, html_link=existing_html_link, fields_changed=fields_changed)

    logger.info("Patching event '%s' on calendar '%s'. Changing: %s", event_id, calendar_id, fields_changed)
    api_response: dict[str, Any] = client.patch_event(calendar_id, event_id, patch_body)

    event_local = EventLocal.from_api_response(api_response, calendar_id)
    upsert_event(db_conn, event_local.to_dict())
    db_conn.commit()

    # Resolve the calendar display name for the output directory structure
    calendar_row = get_calendar(db_conn, calendar_id)
    calendar_display_name: str = calendar_row["summary"] if calendar_row else calendar_id

    resolved_output_dir = Path(output_dir) if output_dir is not None else Path(config.output_dir)
    flat_output: bool = bool(config.flat_output)

    markdown_content = generate_event_markdown(event_local)
    write_event_file(
        content=markdown_content,
        output_dir=resolved_output_dir,
        calendar_name=calendar_display_name,
        event=event_local,
        flat_output=flat_output,
    )

    logger.info("Event updated: %s (%s)", event_local.event_id, event_local.html_link)

    return UpdateResult(
        event_id=event_local.event_id,
        html_link=event_local.html_link or "",
        fields_changed=fields_changed,
    )
