"""Shared pytest fixtures for the GCal Tool test suite.

All database fixtures use in-memory SQLite so no disk I/O occurs.
API client fixtures use MagicMock so no real network calls are made.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock

if TYPE_CHECKING:
    import sqlite3
    from collections.abc import Generator

import pytest

from deep_thought.gcal.db.queries import upsert_calendar, upsert_event, upsert_sync_state
from deep_thought.gcal.db.schema import initialize_database

# Path to the fixtures directory, used by tests that load files from disk
FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Database fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def in_memory_db() -> Generator[sqlite3.Connection, None, None]:
    """Return a fully initialized in-memory SQLite connection.

    The connection has WAL mode enabled, foreign keys enforced, and all
    migrations applied. Closes automatically after each test.
    """
    connection = initialize_database(":memory:")
    yield connection
    connection.close()


@pytest.fixture()
def seeded_db(in_memory_db: sqlite3.Connection) -> sqlite3.Connection:
    """Return an in-memory database pre-populated with sample data.

    Contains 2 calendars, 5 events (timed, all-day, recurring, cancelled, multi-attendee),
    and sync state entries.
    """
    now_iso = datetime.now(UTC).isoformat()

    # Calendars
    upsert_calendar(
        in_memory_db,
        {
            "calendar_id": "primary",
            "summary": "Personal",
            "description": "Main calendar",
            "time_zone": "America/Chicago",
            "primary_calendar": 1,
            "created_at": now_iso,
        },
    )
    upsert_calendar(
        in_memory_db,
        {
            "calendar_id": "work@group.calendar.google.com",
            "summary": "Work",
            "description": "Work calendar",
            "time_zone": "America/New_York",
            "primary_calendar": 0,
            "created_at": now_iso,
        },
    )

    # Events
    upsert_event(
        in_memory_db,
        {
            "event_id": "evt_timed_1",
            "calendar_id": "primary",
            "summary": "Team Standup",
            "description": "Daily standup meeting",
            "location": "Conference Room B",
            "start_time": "2026-03-24T09:00:00-05:00",
            "end_time": "2026-03-24T09:30:00-05:00",
            "all_day": 0,
            "status": "confirmed",
            "organizer": "manager@example.com",
            "attendees": json.dumps([{"email": "colleague@example.com"}]),
            "recurrence": None,
            "html_link": "https://calendar.google.com/event?eid=evt_timed_1",
            "created_at": now_iso,
            "updated_at": now_iso,
        },
    )
    upsert_event(
        in_memory_db,
        {
            "event_id": "evt_allday_1",
            "calendar_id": "primary",
            "summary": "Company Holiday",
            "description": None,
            "location": None,
            "start_time": "2026-03-25",
            "end_time": "2026-03-26",
            "all_day": 1,
            "status": "confirmed",
            "organizer": None,
            "attendees": None,
            "recurrence": None,
            "html_link": None,
            "created_at": now_iso,
            "updated_at": now_iso,
        },
    )
    upsert_event(
        in_memory_db,
        {
            "event_id": "evt_recurring_1",
            "calendar_id": "primary",
            "summary": "Weekly Review",
            "description": "Weekly project review",
            "location": "Zoom",
            "start_time": "2026-03-24T14:00:00-05:00",
            "end_time": "2026-03-24T15:00:00-05:00",
            "all_day": 0,
            "status": "confirmed",
            "organizer": "manager@example.com",
            "attendees": json.dumps([{"email": "team@example.com"}, {"email": "lead@example.com"}]),
            "recurrence": json.dumps(["RRULE:FREQ=WEEKLY;COUNT=10"]),
            "html_link": "https://calendar.google.com/event?eid=evt_recurring_1",
            "created_at": now_iso,
            "updated_at": now_iso,
        },
    )
    upsert_event(
        in_memory_db,
        {
            "event_id": "evt_cancelled_1",
            "calendar_id": "primary",
            "summary": "Cancelled Meeting",
            "description": None,
            "location": None,
            "start_time": "2026-03-26T10:00:00-05:00",
            "end_time": "2026-03-26T11:00:00-05:00",
            "all_day": 0,
            "status": "cancelled",
            "organizer": None,
            "attendees": None,
            "recurrence": None,
            "html_link": None,
            "created_at": now_iso,
            "updated_at": now_iso,
        },
    )
    upsert_event(
        in_memory_db,
        {
            "event_id": "evt_work_1",
            "calendar_id": "work@group.calendar.google.com",
            "summary": "Sprint Planning",
            "description": "Sprint planning session",
            "location": "Room 101",
            "start_time": "2026-03-24T10:00:00-04:00",
            "end_time": "2026-03-24T11:00:00-04:00",
            "all_day": 0,
            "status": "confirmed",
            "organizer": "pm@example.com",
            "attendees": json.dumps([{"email": "dev@example.com"}]),
            "recurrence": None,
            "html_link": "https://calendar.google.com/event?eid=evt_work_1",
            "created_at": now_iso,
            "updated_at": now_iso,
        },
    )

    # Sync state
    upsert_sync_state(in_memory_db, "primary", "sync_token_abc", now_iso)
    upsert_sync_state(in_memory_db, "work@group.calendar.google.com", None, now_iso)

    in_memory_db.commit()
    return in_memory_db


# ---------------------------------------------------------------------------
# Mock API response factories
# ---------------------------------------------------------------------------


def make_api_event(
    event_id: str = "evt_test_1",
    calendar_id: str = "primary",
    summary: str = "Test Event",
    start_datetime: str = "2026-03-24T09:00:00-05:00",
    end_datetime: str = "2026-03-24T10:00:00-05:00",
    all_day: bool = False,
    status: str = "confirmed",
    description: str | None = "Test event description",
    location: str | None = "Test Location",
    organizer_email: str | None = "organizer@example.com",
    attendees: list[str] | None = None,
    recurrence: list[str] | None = None,
    html_link: str | None = "https://calendar.google.com/event?eid=test",
    updated: str = "2026-03-23T12:00:00.000Z",
) -> dict[str, Any]:
    """Return a dict mimicking a Google Calendar API event response.

    Args:
        event_id: The Calendar event ID string.
        calendar_id: The calendar this event belongs to (not in API response but useful for tests).
        summary: Event title.
        start_datetime: ISO 8601 start time (or date for all-day).
        end_datetime: ISO 8601 end time (or date for all-day).
        all_day: If True, uses date fields instead of dateTime.
        status: Event status (confirmed, tentative, cancelled).
        description: Event description text.
        location: Event location.
        organizer_email: Organizer email address.
        attendees: List of attendee email addresses.
        recurrence: List of RRULE strings.
        html_link: URL to event in Google Calendar.
        updated: ISO 8601 timestamp of last modification.

    Returns:
        A dict matching the Calendar API v3 event format.
    """
    event: dict[str, Any] = {
        "id": event_id,
        "status": status,
        "summary": summary,
        "updated": updated,
    }

    if all_day:
        event["start"] = {"date": start_datetime}
        event["end"] = {"date": end_datetime}
    else:
        event["start"] = {"dateTime": start_datetime, "timeZone": "America/Chicago"}
        event["end"] = {"dateTime": end_datetime, "timeZone": "America/Chicago"}

    if description is not None:
        event["description"] = description
    if location is not None:
        event["location"] = location
    if organizer_email is not None:
        event["organizer"] = {"email": organizer_email, "self": False}
    if attendees is not None:
        event["attendees"] = [{"email": email, "responseStatus": "needsAction"} for email in attendees]
    if recurrence is not None:
        event["recurrence"] = recurrence
    if html_link is not None:
        event["htmlLink"] = html_link

    return event


def make_api_calendar(
    calendar_id: str = "primary",
    summary: str = "Personal",
    description: str | None = "Main calendar",
    time_zone: str = "America/Chicago",
    primary: bool = True,
) -> dict[str, Any]:
    """Return a dict mimicking a Google Calendar API calendarList entry.

    Args:
        calendar_id: The Calendar ID.
        summary: Calendar display name.
        description: Calendar description.
        time_zone: IANA time zone string.
        primary: Whether this is the user's primary calendar.

    Returns:
        A dict matching the Calendar API v3 calendarList format.
    """
    calendar: dict[str, Any] = {
        "id": calendar_id,
        "summary": summary,
        "timeZone": time_zone,
    }
    if description is not None:
        calendar["description"] = description
    if primary:
        calendar["primary"] = True
    return calendar


# ---------------------------------------------------------------------------
# Fixture-based versions of the factories
# ---------------------------------------------------------------------------


@pytest.fixture()
def sample_event() -> dict[str, Any]:
    """Return a Calendar API event dict with default realistic attributes."""
    return make_api_event()


@pytest.fixture()
def sample_allday_event() -> dict[str, Any]:
    """Return a Calendar API all-day event dict."""
    return make_api_event(
        event_id="evt_allday_test",
        summary="Company Holiday",
        start_datetime="2026-03-25",
        end_datetime="2026-03-26",
        all_day=True,
        description=None,
        location=None,
        organizer_email=None,
    )


@pytest.fixture()
def sample_calendar() -> dict[str, Any]:
    """Return a Calendar API calendarList entry with default attributes."""
    return make_api_calendar()


# ---------------------------------------------------------------------------
# Mock client fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_gcal_client() -> MagicMock:
    """Return a mock GcalClient with all methods returning empty defaults."""
    client = MagicMock()
    client.list_calendars.return_value = []
    client.list_events.return_value = ([], None)
    client.get_event.return_value = {}
    client.insert_event.return_value = {"id": "new_evt_123", "htmlLink": "https://calendar.google.com/event?eid=new"}
    client.patch_event.return_value = {"id": "evt_123", "htmlLink": "https://calendar.google.com/event?eid=updated"}
    client.delete_event.return_value = None
    return client
