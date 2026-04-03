"""Tests for the GCal Tool data models."""

from __future__ import annotations

import json

import pytest

from deep_thought.gcal.models import (
    CalendarLocal,
    CreateResult,
    DeleteResult,
    EventLocal,
    PullResult,
    UpdateResult,
    _parse_event_time,
    _serialize_attendees,
    _serialize_recurrence,
)
from deep_thought.text_utils import slugify as _shared_slugify

from .conftest import make_api_calendar, make_api_event

# ---------------------------------------------------------------------------
# slugify (shared) — gcal summary behaviour
# ---------------------------------------------------------------------------


class TestSlugifySummary:
    """Tests for shared slugify as used by the gcal models."""

    def test_basic_summary(self) -> None:
        """Should lowercase and replace spaces with hyphens."""
        assert _shared_slugify("Team Standup") == "team-standup"

    def test_special_characters(self) -> None:
        """Should replace non-alphanumeric characters with hyphens."""
        assert _shared_slugify("Q1 Planning — Budget & Roadmap!") == "q1-planning-budget-roadmap"

    def test_collapses_consecutive_hyphens(self) -> None:
        """Should collapse multiple consecutive hyphens into one."""
        assert _shared_slugify("a---b---c") == "a-b-c"

    def test_strips_leading_trailing_hyphens(self) -> None:
        """Should strip hyphens from start and end."""
        assert _shared_slugify("---hello---") == "hello"

    def test_truncates_to_max_length(self) -> None:
        """Should truncate long slugs to the specified max length."""
        long_summary = "a" * 100
        result = _shared_slugify(long_summary, max_length=80)
        assert len(result) == 80

    def test_empty_string_returns_no_title(self) -> None:
        """Should return 'no-title' when empty_fallback is provided."""
        assert _shared_slugify("", empty_fallback="no-title") == "no-title"

    def test_only_special_chars_returns_no_title(self) -> None:
        """Should return 'no-title' when summary reduces to only hyphens."""
        assert _shared_slugify("---!!!---", empty_fallback="no-title") == "no-title"


# ---------------------------------------------------------------------------
# _parse_event_time
# ---------------------------------------------------------------------------


class TestParseEventTime:
    """Tests for the _parse_event_time helper."""

    def test_datetime_key_returns_value_and_false(self) -> None:
        """Should return (dateTime value, False) for timed events."""
        time_dict = {"dateTime": "2026-03-24T09:00:00-05:00", "timeZone": "America/Chicago"}
        time_value, all_day = _parse_event_time(time_dict)
        assert time_value == "2026-03-24T09:00:00-05:00"
        assert all_day is False

    def test_date_key_returns_value_and_true(self) -> None:
        """Should return (date value, True) for all-day events."""
        time_dict = {"date": "2026-03-25"}
        time_value, all_day = _parse_event_time(time_dict)
        assert time_value == "2026-03-25"
        assert all_day is True

    def test_neither_key_raises_value_error(self) -> None:
        """Should raise ValueError when neither 'dateTime' nor 'date' is present."""
        time_dict: dict[str, str] = {"timeZone": "America/Chicago"}
        with pytest.raises(ValueError, match="neither"):
            _parse_event_time(time_dict)

    def test_empty_dict_raises_value_error(self) -> None:
        """Should raise ValueError for an empty dict."""
        with pytest.raises(ValueError):
            _parse_event_time({})


# ---------------------------------------------------------------------------
# _serialize_attendees
# ---------------------------------------------------------------------------


class TestSerializeAttendees:
    """Tests for the _serialize_attendees helper."""

    def test_list_of_dicts_serialized_to_json(self) -> None:
        """Should return a JSON string for a non-empty attendee list."""
        attendees = [{"email": "a@example.com", "responseStatus": "accepted"}]
        result = _serialize_attendees(attendees)
        assert result is not None
        parsed = json.loads(result)
        assert parsed[0]["email"] == "a@example.com"

    def test_none_returns_none(self) -> None:
        """Should return None when passed None."""
        assert _serialize_attendees(None) is None

    def test_empty_list_returns_none(self) -> None:
        """Should return None for an empty list."""
        assert _serialize_attendees([]) is None

    def test_multiple_attendees_preserved(self) -> None:
        """Should preserve all attendee entries in the JSON output."""
        attendees = [
            {"email": "a@example.com"},
            {"email": "b@example.com"},
        ]
        result = _serialize_attendees(attendees)
        assert result is not None
        parsed = json.loads(result)
        assert len(parsed) == 2


# ---------------------------------------------------------------------------
# _serialize_recurrence
# ---------------------------------------------------------------------------


class TestSerializeRecurrence:
    """Tests for the _serialize_recurrence helper."""

    def test_list_of_strings_serialized_to_json(self) -> None:
        """Should return a JSON string for a non-empty recurrence list."""
        recurrence = ["RRULE:FREQ=WEEKLY;COUNT=10"]
        result = _serialize_recurrence(recurrence)
        assert result is not None
        parsed = json.loads(result)
        assert parsed[0] == "RRULE:FREQ=WEEKLY;COUNT=10"

    def test_none_returns_none(self) -> None:
        """Should return None when passed None."""
        assert _serialize_recurrence(None) is None

    def test_empty_list_returns_none(self) -> None:
        """Should return None for an empty list."""
        assert _serialize_recurrence([]) is None

    def test_multiple_rules_preserved(self) -> None:
        """Should preserve multiple RRULE/EXRULE entries in the JSON output."""
        recurrence = ["RRULE:FREQ=WEEKLY", "EXDATE:20260401"]
        result = _serialize_recurrence(recurrence)
        assert result is not None
        parsed = json.loads(result)
        assert len(parsed) == 2


# ---------------------------------------------------------------------------
# EventLocal.from_api_response
# ---------------------------------------------------------------------------


class TestEventLocalFromApiResponse:
    """Tests for EventLocal.from_api_response."""

    def test_constructs_from_timed_event(self) -> None:
        """Should populate all fields from a standard timed API event dict."""
        api_event = make_api_event(
            event_id="evt_001",
            calendar_id="primary",
            summary="Team Standup",
            start_datetime="2026-03-24T09:00:00-05:00",
            end_datetime="2026-03-24T09:30:00-05:00",
        )
        event = EventLocal.from_api_response(api_event, "primary")

        assert event.event_id == "evt_001"
        assert event.calendar_id == "primary"
        assert event.summary == "Team Standup"
        assert event.start_time == "2026-03-24T09:00:00-05:00"
        assert event.end_time == "2026-03-24T09:30:00-05:00"
        assert event.all_day is False
        assert event.status == "confirmed"

    def test_constructs_from_all_day_event(self) -> None:
        """Should set all_day=True and parse date strings for all-day events."""
        api_event = make_api_event(
            event_id="evt_allday",
            summary="Company Holiday",
            start_datetime="2026-03-25",
            end_datetime="2026-03-26",
            all_day=True,
            description=None,
            location=None,
            organizer_email=None,
        )
        event = EventLocal.from_api_response(api_event, "primary")

        assert event.all_day is True
        assert event.start_time == "2026-03-25"
        assert event.end_time == "2026-03-26"

    def test_extracts_organizer_email(self) -> None:
        """Should extract only the email string from the organizer dict."""
        api_event = make_api_event(organizer_email="boss@example.com")
        event = EventLocal.from_api_response(api_event, "primary")
        assert event.organizer == "boss@example.com"

    def test_missing_optional_fields_are_none(self) -> None:
        """Should set description, location, attendees, recurrence to None when absent."""
        api_event = make_api_event(
            description=None,
            location=None,
            organizer_email=None,
            attendees=None,
            recurrence=None,
            html_link=None,
        )
        event = EventLocal.from_api_response(api_event, "primary")

        assert event.description is None
        assert event.location is None
        assert event.organizer is None
        assert event.attendees is None
        assert event.recurrence is None
        assert event.html_link is None

    def test_attendees_serialized_to_json(self) -> None:
        """Should serialize the attendee list to a JSON string."""
        api_event = make_api_event(attendees=["colleague@example.com", "lead@example.com"])
        event = EventLocal.from_api_response(api_event, "primary")

        assert event.attendees is not None
        parsed_attendees = json.loads(event.attendees)
        assert len(parsed_attendees) == 2
        emails = [entry["email"] for entry in parsed_attendees]
        assert "colleague@example.com" in emails

    def test_recurrence_serialized_to_json(self) -> None:
        """Should serialize the recurrence list to a JSON string."""
        api_event = make_api_event(recurrence=["RRULE:FREQ=WEEKLY;COUNT=10"])
        event = EventLocal.from_api_response(api_event, "primary")

        assert event.recurrence is not None
        parsed_recurrence = json.loads(event.recurrence)
        assert parsed_recurrence[0] == "RRULE:FREQ=WEEKLY;COUNT=10"

    def test_timestamps_are_set(self) -> None:
        """Should populate created_at and synced_at with a current UTC timestamp."""
        api_event = make_api_event(updated="2026-03-23T12:00:00.000Z")
        event = EventLocal.from_api_response(api_event, "primary")

        assert event.created_at != ""
        assert event.synced_at != ""
        assert event.updated_at == "2026-03-23T12:00:00.000Z"


# ---------------------------------------------------------------------------
# CalendarLocal.from_api_response
# ---------------------------------------------------------------------------


class TestCalendarLocalFromApiResponse:
    """Tests for CalendarLocal.from_api_response."""

    def test_constructs_from_calendar_dict(self) -> None:
        """Should populate all fields from a standard calendarList entry dict."""
        api_calendar = make_api_calendar(
            calendar_id="primary",
            summary="Personal",
            description="Main calendar",
            time_zone="America/Chicago",
            primary=True,
        )
        calendar = CalendarLocal.from_api_response(api_calendar)

        assert calendar.calendar_id == "primary"
        assert calendar.summary == "Personal"
        assert calendar.description == "Main calendar"
        assert calendar.time_zone == "America/Chicago"
        assert calendar.primary_calendar is True

    def test_primary_flag_false_for_non_primary(self) -> None:
        """Should set primary_calendar to False when the 'primary' key is absent."""
        api_calendar = make_api_calendar(
            calendar_id="work@group.calendar.google.com",
            summary="Work",
            primary=False,
        )
        calendar = CalendarLocal.from_api_response(api_calendar)
        assert calendar.primary_calendar is False

    def test_missing_description_is_none(self) -> None:
        """Should set description to None when the key is absent from the API response."""
        api_calendar = make_api_calendar(description=None)
        calendar = CalendarLocal.from_api_response(api_calendar)
        assert calendar.description is None

    def test_timestamps_are_set(self) -> None:
        """Should populate all three timestamps with a current UTC timestamp."""
        api_calendar = make_api_calendar()
        calendar = CalendarLocal.from_api_response(api_calendar)

        assert calendar.created_at != ""
        assert calendar.updated_at != ""
        assert calendar.synced_at != ""


# ---------------------------------------------------------------------------
# EventLocal.to_dict
# ---------------------------------------------------------------------------


class TestEventLocalToDict:
    """Tests for EventLocal.to_dict."""

    def test_returns_dict_with_all_expected_keys(self) -> None:
        """to_dict should return a dict containing all database column names."""
        api_event = make_api_event()
        event = EventLocal.from_api_response(api_event, "primary")
        result = event.to_dict()

        expected_keys = {
            "event_id",
            "calendar_id",
            "summary",
            "description",
            "location",
            "start_time",
            "end_time",
            "all_day",
            "status",
            "organizer",
            "attendees",
            "recurrence",
            "html_link",
            "created_at",
            "updated_at",
            "synced_at",
        }
        assert set(result.keys()) == expected_keys

    def test_all_day_true_converts_to_one(self) -> None:
        """Should convert all_day=True to integer 1 for SQLite."""
        api_event = make_api_event(
            start_datetime="2026-03-25",
            end_datetime="2026-03-26",
            all_day=True,
            description=None,
            location=None,
            organizer_email=None,
        )
        event = EventLocal.from_api_response(api_event, "primary")
        assert event.to_dict()["all_day"] == 1

    def test_all_day_false_converts_to_zero(self) -> None:
        """Should convert all_day=False to integer 0 for SQLite."""
        api_event = make_api_event(all_day=False)
        event = EventLocal.from_api_response(api_event, "primary")
        assert event.to_dict()["all_day"] == 0


# ---------------------------------------------------------------------------
# CalendarLocal.to_dict
# ---------------------------------------------------------------------------


class TestCalendarLocalToDict:
    """Tests for CalendarLocal.to_dict."""

    def test_returns_dict_with_all_expected_keys(self) -> None:
        """to_dict should return a dict containing all database column names."""
        api_calendar = make_api_calendar()
        calendar = CalendarLocal.from_api_response(api_calendar)
        result = calendar.to_dict()

        expected_keys = {
            "calendar_id",
            "summary",
            "description",
            "time_zone",
            "primary_calendar",
            "created_at",
            "updated_at",
            "synced_at",
        }
        assert set(result.keys()) == expected_keys

    def test_primary_calendar_true_converts_to_one(self) -> None:
        """Should convert primary_calendar=True to integer 1 for SQLite."""
        api_calendar = make_api_calendar(primary=True)
        calendar = CalendarLocal.from_api_response(api_calendar)
        assert calendar.to_dict()["primary_calendar"] == 1

    def test_primary_calendar_false_converts_to_zero(self) -> None:
        """Should convert primary_calendar=False to integer 0 for SQLite."""
        api_calendar = make_api_calendar(primary=False)
        calendar = CalendarLocal.from_api_response(api_calendar)
        assert calendar.to_dict()["primary_calendar"] == 0


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


class TestPullResult:
    """Tests for the PullResult dataclass."""

    def test_default_values(self) -> None:
        """Default PullResult should have zero counts for all fields."""
        result = PullResult()
        assert result.created == 0
        assert result.updated == 0
        assert result.cancelled == 0
        assert result.unchanged == 0
        assert result.calendars_synced == 0


class TestCreateResult:
    """Tests for the CreateResult dataclass."""

    def test_default_values(self) -> None:
        """Default CreateResult should have empty strings."""
        result = CreateResult()
        assert result.event_id == ""
        assert result.html_link == ""


class TestUpdateResult:
    """Tests for the UpdateResult dataclass."""

    def test_default_values(self) -> None:
        """Default UpdateResult should have empty strings and an empty list."""
        result = UpdateResult()
        assert result.event_id == ""
        assert result.html_link == ""
        assert result.fields_changed == []

    def test_fields_changed_list_is_independent(self) -> None:
        """Each UpdateResult instance should have its own fields_changed list."""
        result_a = UpdateResult()
        result_b = UpdateResult()
        result_a.fields_changed.append("summary")
        assert result_b.fields_changed == []


class TestDeleteResult:
    """Tests for the DeleteResult dataclass."""

    def test_default_values(self) -> None:
        """Default DeleteResult should have empty strings."""
        result = DeleteResult()
        assert result.event_id == ""
        assert result.calendar_id == ""
