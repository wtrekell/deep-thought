"""Event creation from markdown frontmatter for the GCal Tool."""

from __future__ import annotations

import logging
import re
import sqlite3  # noqa: TC003 — sqlite3.Connection is used at runtime in run_create
from pathlib import Path
from typing import Any

import yaml

from deep_thought.gcal.db.queries import clear_sync_token, get_calendar, upsert_event
from deep_thought.gcal.models import CreateResult, EventLocal
from deep_thought.gcal.output import generate_event_markdown, write_event_file

# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

_DATETIME_COMPARISON_STRIP_TZ_RE = re.compile(r"[+-]\d{2}:\d{2}$|Z$")

logger = logging.getLogger(__name__)


def _validate_start_before_end(start_value: str, end_value: str) -> None:
    """Raise ValueError if start_value is not strictly before end_value.

    Compares the raw string values lexicographically, which is correct for
    both ISO 8601 date-only (YYYY-MM-DD) and datetime strings that share the
    same time zone representation.

    Args:
        start_value: The event start as an ISO 8601 string.
        end_value: The event end as an ISO 8601 string.

    Raises:
        ValueError: If start_value >= end_value.
    """
    if start_value >= end_value:
        raise ValueError(f"Event start must be before end. Got start='{start_value}', end='{end_value}'.")


# ---------------------------------------------------------------------------
# Frontmatter parsing
# ---------------------------------------------------------------------------

_REQUIRED_FRONTMATTER_FIELDS = ("summary", "start", "end")
_DATE_ONLY_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def parse_event_frontmatter(file_path: Path) -> tuple[dict[str, Any], str]:
    """Read a markdown file and extract its YAML frontmatter and body text.

    Splits the file on ``---`` delimiters to locate the YAML block, then
    parses it with ``yaml.safe_load``. The text after the closing ``---``
    is returned as the body.

    Args:
        file_path: Path to the markdown file to parse.

    Returns:
        A tuple of (frontmatter_dict, body_text). body_text is the content
        after the closing ``---`` delimiter, stripped of leading/trailing
        whitespace.

    Raises:
        FileNotFoundError: If the file does not exist at file_path.
        ValueError: If the YAML block is malformed, the required fields
                    (summary, start, end) are missing, or no frontmatter
                    delimiters are found.
    """
    if not file_path.exists():
        raise FileNotFoundError(f"Event file not found: {file_path}")

    raw_content = file_path.read_text(encoding="utf-8")
    parts = raw_content.split("---")

    # A well-formed file starts with "---\n...\n---\n..." which splits into
    # at least three parts: ["", yaml_block, body_remainder].
    if len(parts) < 3:
        raise ValueError(f"No valid YAML frontmatter delimiters found in: {file_path}")

    yaml_block = parts[1]
    body_text = "---".join(parts[2:]).strip()

    try:
        parsed_yaml: Any = yaml.safe_load(yaml_block)
    except yaml.YAMLError as yaml_error:
        raise ValueError(f"Invalid YAML frontmatter in {file_path}: {yaml_error}") from yaml_error

    if not isinstance(parsed_yaml, dict):
        raise ValueError(f"Frontmatter must be a YAML mapping, got: {type(parsed_yaml).__name__}")

    frontmatter: dict[str, Any] = parsed_yaml

    missing_fields = [field for field in _REQUIRED_FRONTMATTER_FIELDS if field not in frontmatter]
    if missing_fields:
        raise ValueError(f"Missing required frontmatter fields in {file_path}: {missing_fields}")

    return frontmatter, body_text


# ---------------------------------------------------------------------------
# Date detection helper
# ---------------------------------------------------------------------------


def _is_date_only(value: str) -> bool:
    """Return True if the string is a date-only value (YYYY-MM-DD format).

    Args:
        value: A string representing either a date or a datetime.

    Returns:
        True when the string matches YYYY-MM-DD with no time component.
    """
    return bool(_DATE_ONLY_PATTERN.match(value))


# ---------------------------------------------------------------------------
# API body builder
# ---------------------------------------------------------------------------


def _build_api_event_body(frontmatter: dict[str, Any], body_text: str) -> dict[str, Any]:
    """Convert parsed frontmatter into a Calendar API event resource dict.

    Maps frontmatter fields to the format expected by the Google Calendar API.
    All-day events use ``{"date": value}`` while timed events use
    ``{"dateTime": value}``. Only non-None fields are included in the result.

    Args:
        frontmatter: A dict of parsed YAML frontmatter fields.
        body_text: The markdown body text below the frontmatter block. Used
                   as the event description when no ``description`` key is
                   present in the frontmatter.

    Returns:
        A dict ready to pass as the body to the Calendar API insert or patch
        methods. Contains at minimum: summary, start, end.
    """
    event_body: dict[str, Any] = {}

    # --- Summary (required) ---
    event_body["summary"] = frontmatter["summary"]

    # --- Start and end times ---
    start_value = str(frontmatter["start"])
    end_value = str(frontmatter["end"])

    if _is_date_only(start_value):
        event_body["start"] = {"date": start_value}
        event_body["end"] = {"date": end_value}
    else:
        event_body["start"] = {"dateTime": start_value}
        event_body["end"] = {"dateTime": end_value}

    # --- Optional scalar fields ---
    location_value: str | None = frontmatter.get("location")
    if location_value is not None:
        event_body["location"] = location_value

    # --- Description: prefer frontmatter key, fall back to body text ---
    frontmatter_description: str | None = frontmatter.get("description")
    if frontmatter_description is not None:
        event_body["description"] = frontmatter_description
    elif body_text:
        event_body["description"] = body_text

    # --- Attendees: convert email strings to API dicts ---
    raw_attendees: list[str] | None = frontmatter.get("attendees")
    if raw_attendees:
        event_body["attendees"] = [{"email": email_address} for email_address in raw_attendees]

    # --- Recurrence: pass RRULE strings through as-is ---
    raw_recurrence: list[str] | None = frontmatter.get("recurrence")
    if raw_recurrence:
        event_body["recurrence"] = raw_recurrence

    return event_body


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def run_create(
    client: Any,
    config: Any,
    db_conn: sqlite3.Connection,
    file_path: Path,
    *,
    dry_run: bool = False,
    output_dir: Path | None = None,
) -> CreateResult:
    """Create a new Google Calendar event from a markdown frontmatter file.

    Parses frontmatter from file_path, builds an API request body, calls the
    Calendar API (unless dry_run is True), persists the result to the local
    database, and writes an updated markdown file with the assigned event_id.

    Args:
        client: A GcalClient (or compatible mock) with an insert_event method.
        config: A GcalConfig with output_dir and flat_output settings.
        db_conn: An open SQLite connection for persisting the new event.
        file_path: Path to the markdown file containing event frontmatter.
        dry_run: When True, skip the API call and return an empty CreateResult.
        output_dir: Override the output directory from config. If None, uses
                    config.output_dir.

    Returns:
        A CreateResult with event_id and html_link populated on success,
        or empty strings when dry_run is True.
    """
    frontmatter, body_text = parse_event_frontmatter(file_path)

    # Validate start < end before calling the API so the user gets a clear
    # local error rather than a cryptic API rejection.
    start_value: str = str(frontmatter["start"])
    end_value: str = str(frontmatter["end"])
    _validate_start_before_end(start_value, end_value)

    event_api_body = _build_api_event_body(frontmatter, body_text)

    calendar_id: str = str(frontmatter.get("calendar_id", "primary"))

    if dry_run:
        logger.info("Dry run — skipping Calendar API call for file: %s", file_path)
        return CreateResult()

    logger.info("Creating event on calendar '%s': %s", calendar_id, frontmatter.get("summary"))
    api_response: dict[str, Any] = client.insert_event(calendar_id, event_api_body)

    event_local = EventLocal.from_api_response(api_response, calendar_id)

    # Resolve the calendar display name for the output directory structure
    # before the DB write so the commit only happens after all I/O succeeds.
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

    # Write to the DB only after the file has been successfully created.
    # The caller (cli.py) is responsible for calling db_conn.commit().
    upsert_event(db_conn, event_local.to_dict())
    clear_sync_token(db_conn, calendar_id)

    logger.info("Event created: %s (%s)", event_local.event_id, event_local.html_link)

    return CreateResult(
        event_id=event_local.event_id,
        html_link=event_local.html_link or "",
    )
