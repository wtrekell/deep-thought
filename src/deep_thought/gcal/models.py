"""Local dataclasses for the GCal Tool.

EventLocal mirrors the events database table and represents the state of a
single Google Calendar event as stored locally.

CalendarLocal mirrors the calendars database table and represents a single
calendar entry from the user's calendar list.

PullResult, CreateResult, UpdateResult, and DeleteResult are returned from
operations to summarise what happened.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _slugify_summary(summary: str, max_length: int = 80) -> str:
    """Convert a calendar event summary to a filesystem-safe slug.

    Lowercases, replaces non-alphanumeric characters with hyphens, collapses
    repeated hyphens, strips leading/trailing hyphens, and truncates.

    Args:
        summary: The raw event summary string.
        max_length: Maximum length of the resulting slug.

    Returns:
        A cleaned slug suitable for use in a filename, or "no-title" if
        the summary is empty or reduces to only hyphens.
    """
    slug = summary.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    if not slug:
        return "no-title"
    return slug[:max_length] if len(slug) > max_length else slug


def _parse_event_time(time_dict: dict[str, Any]) -> tuple[str, bool]:
    """Extract a time value from a Calendar API event time object.

    Google Calendar represents event times as a dict containing either a
    "dateTime" key (for timed events) or a "date" key (for all-day events).

    Args:
        time_dict: A Calendar API start or end time object.

    Returns:
        A tuple of (time_string, all_day) where all_day is True when the
        event spans a full calendar date with no time component.

    Raises:
        ValueError: If neither "dateTime" nor "date" key is present.
    """
    if "dateTime" in time_dict:
        return time_dict["dateTime"], False
    if "date" in time_dict:
        return time_dict["date"], True
    raise ValueError(f"Event time object has neither 'dateTime' nor 'date' key: {time_dict!r}")


def _serialize_attendees(attendees: list[dict[str, Any]] | None) -> str | None:
    """JSON-serialize a list of attendee dicts.

    Args:
        attendees: A list of Calendar API attendee objects, or None.

    Returns:
        A JSON string if the list is non-empty, otherwise None.
    """
    if not attendees:
        return None
    return json.dumps(attendees)


def _serialize_recurrence(recurrence: list[str] | None) -> str | None:
    """JSON-serialize a list of RRULE strings.

    Args:
        recurrence: A list of RRULE/EXRULE strings from the Calendar API, or None.

    Returns:
        A JSON string if the list is non-empty, otherwise None.
    """
    if not recurrence:
        return None
    return json.dumps(recurrence)


# ---------------------------------------------------------------------------
# EventLocal
# ---------------------------------------------------------------------------


@dataclass
class EventLocal:
    """Local representation of a Google Calendar event.

    Mirrors the events database table. All timestamp fields are ISO 8601 strings.
    Boolean fields are stored as Python bools here; to_dict() converts them to
    integers (0/1) for SQLite compatibility.
    """

    event_id: str
    calendar_id: str
    summary: str
    description: str | None
    location: str | None
    start_time: str
    end_time: str
    all_day: bool
    status: str
    organizer: str | None
    attendees: str | None  # JSON string
    recurrence: str | None  # JSON string
    html_link: str | None
    created_at: str
    updated_at: str
    synced_at: str

    @classmethod
    def from_api_response(cls, event: dict[str, Any], calendar_id: str) -> EventLocal:
        """Convert a Calendar API event dict into an EventLocal.

        Parses start/end times, serializes attendees and recurrence to JSON,
        and sets timestamps. created_at and synced_at are set to now (UTC);
        updated_at is taken from the event's "updated" field.

        Args:
            event: A Calendar API v3 event resource dict.
            calendar_id: The ID of the calendar this event belongs to.

        Returns:
            An EventLocal with all fields populated.
        """
        current_timestamp: str = datetime.now(tz=UTC).isoformat()

        start_time, all_day = _parse_event_time(event["start"])
        end_time, _ = _parse_event_time(event["end"])

        organizer_email: str | None = event.get("organizer", {}).get("email")
        raw_attendees: list[dict[str, Any]] | None = event.get("attendees")
        raw_recurrence: list[str] | None = event.get("recurrence")

        return cls(
            event_id=event["id"],
            calendar_id=calendar_id,
            summary=event.get("summary", ""),
            description=event.get("description"),
            location=event.get("location"),
            start_time=start_time,
            end_time=end_time,
            all_day=all_day,
            status=event.get("status", "confirmed"),
            organizer=organizer_email,
            attendees=_serialize_attendees(raw_attendees),
            recurrence=_serialize_recurrence(raw_recurrence),
            html_link=event.get("htmlLink"),
            created_at=current_timestamp,
            updated_at=event["updated"],
            synced_at=current_timestamp,
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a flat dict keyed by database column names.

        Converts the all_day boolean to an integer (0 or 1) for SQLite
        compatibility, since SQLite has no native boolean type.

        Returns:
            A plain dictionary representation suitable for passing to
            database query functions.
        """
        return {
            "event_id": self.event_id,
            "calendar_id": self.calendar_id,
            "summary": self.summary,
            "description": self.description,
            "location": self.location,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "all_day": 1 if self.all_day else 0,
            "status": self.status,
            "organizer": self.organizer,
            "attendees": self.attendees,
            "recurrence": self.recurrence,
            "html_link": self.html_link,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "synced_at": self.synced_at,
        }


# ---------------------------------------------------------------------------
# CalendarLocal
# ---------------------------------------------------------------------------


@dataclass
class CalendarLocal:
    """Local representation of a Google Calendar list entry.

    Mirrors the calendars database table. All timestamp fields are ISO 8601
    strings. The primary_calendar boolean is converted to an integer in
    to_dict() for SQLite compatibility.
    """

    calendar_id: str
    summary: str
    description: str | None
    time_zone: str
    primary_calendar: bool
    created_at: str
    updated_at: str
    synced_at: str

    @classmethod
    def from_api_response(cls, calendar: dict[str, Any]) -> CalendarLocal:
        """Convert a Calendar API calendarList entry into a CalendarLocal.

        All three timestamps (created_at, updated_at, synced_at) are set to
        the current UTC time since the Calendar API does not expose calendar
        metadata timestamps.

        Args:
            calendar: A Calendar API v3 calendarList resource dict.

        Returns:
            A CalendarLocal with all fields populated.
        """
        current_timestamp: str = datetime.now(tz=UTC).isoformat()

        return cls(
            calendar_id=calendar["id"],
            summary=calendar["summary"],
            description=calendar.get("description"),
            time_zone=calendar["timeZone"],
            primary_calendar=calendar.get("primary", False),
            created_at=current_timestamp,
            updated_at=current_timestamp,
            synced_at=current_timestamp,
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a flat dict keyed by database column names.

        Converts the primary_calendar boolean to an integer (0 or 1) for
        SQLite compatibility.

        Returns:
            A plain dictionary representation suitable for passing to
            database query functions.
        """
        return {
            "calendar_id": self.calendar_id,
            "summary": self.summary,
            "description": self.description,
            "time_zone": self.time_zone,
            "primary_calendar": 1 if self.primary_calendar else 0,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "synced_at": self.synced_at,
        }


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class PullResult:
    """Summary of a calendar pull (sync) operation."""

    created: int = 0
    updated: int = 0
    cancelled: int = 0
    unchanged: int = 0
    calendars_synced: int = 0


@dataclass
class CreateResult:
    """Summary of an event creation operation."""

    event_id: str = ""
    html_link: str = ""


@dataclass
class UpdateResult:
    """Summary of an event update operation."""

    event_id: str = ""
    html_link: str = ""
    fields_changed: list[str] = field(default_factory=list)


@dataclass
class DeleteResult:
    """Summary of an event deletion operation."""

    event_id: str = ""
    calendar_id: str = ""
