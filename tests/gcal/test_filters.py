"""Tests for the GCal Tool event filtering."""

from __future__ import annotations

from deep_thought.gcal.filters import filter_calendars, is_event_updated, should_include_event

from .conftest import make_api_calendar, make_api_event


class TestShouldIncludeEvent:
    """Tests for should_include_event."""

    def test_confirmed_event_included(self) -> None:
        """Confirmed events should always be included."""
        event = make_api_event(status="confirmed")
        assert should_include_event(event) is True

    def test_tentative_event_included(self) -> None:
        """Tentative events should always be included."""
        event = make_api_event(status="tentative")
        assert should_include_event(event) is True

    def test_cancelled_event_excluded_by_default(self) -> None:
        """Cancelled events should be excluded when include_cancelled is False."""
        event = make_api_event(status="cancelled")
        assert should_include_event(event) is False

    def test_cancelled_event_included_when_configured(self) -> None:
        """Cancelled events should be included when include_cancelled is True."""
        event = make_api_event(status="cancelled")
        assert should_include_event(event, include_cancelled=True) is True

    def test_missing_status_defaults_to_confirmed(self) -> None:
        """Events without a status field should default to confirmed."""
        event: dict = {"id": "test", "summary": "Test"}
        assert should_include_event(event) is True


class TestIsEventUpdated:
    """Tests for is_event_updated."""

    def test_no_local_record_is_updated(self) -> None:
        """Events with no local record should be considered updated."""
        event = make_api_event(updated="2026-03-23T12:00:00.000Z")
        assert is_event_updated(event, None) is True

    def test_newer_remote_is_updated(self) -> None:
        """Events with a newer remote timestamp should be updated."""
        event = make_api_event(updated="2026-03-24T12:00:00.000Z")
        assert is_event_updated(event, "2026-03-23T12:00:00.000Z") is True

    def test_same_timestamp_not_updated(self) -> None:
        """Events with the same timestamp should not be updated."""
        event = make_api_event(updated="2026-03-23T12:00:00.000Z")
        assert is_event_updated(event, "2026-03-23T12:00:00.000Z") is False

    def test_older_remote_not_updated(self) -> None:
        """Events with an older remote timestamp should not be updated."""
        event = make_api_event(updated="2026-03-22T12:00:00.000Z")
        assert is_event_updated(event, "2026-03-23T12:00:00.000Z") is False


class TestFilterCalendars:
    """Tests for filter_calendars."""

    def test_filters_to_configured_ids(self) -> None:
        """Should only return calendars matching configured IDs."""
        calendars = [
            make_api_calendar(calendar_id="cal_a", summary="A", primary=False),
            make_api_calendar(calendar_id="cal_b", summary="B", primary=False),
            make_api_calendar(calendar_id="cal_c", summary="C", primary=False),
        ]
        result = filter_calendars(calendars, ["cal_a", "cal_c"])
        assert len(result) == 2
        assert result[0]["id"] == "cal_a"
        assert result[1]["id"] == "cal_c"

    def test_handles_primary_keyword(self) -> None:
        """Should match the primary calendar when 'primary' is in configured IDs."""
        calendars = [
            make_api_calendar(calendar_id="user@gmail.com", summary="Personal", primary=True),
            make_api_calendar(calendar_id="work@group.calendar.google.com", summary="Work", primary=False),
        ]
        result = filter_calendars(calendars, ["primary"])
        assert len(result) == 1
        assert result[0]["id"] == "user@gmail.com"

    def test_empty_config_returns_empty(self) -> None:
        """Should return empty list when no calendars are configured."""
        calendars = [make_api_calendar()]
        assert filter_calendars(calendars, []) == []

    def test_no_matching_calendars(self) -> None:
        """Should return empty list when no calendars match."""
        calendars = [make_api_calendar(calendar_id="other")]
        assert filter_calendars(calendars, ["nonexistent"]) == []

    def test_primary_and_explicit_id(self) -> None:
        """Should handle both 'primary' keyword and explicit IDs together."""
        calendars = [
            make_api_calendar(calendar_id="user@gmail.com", summary="Personal", primary=True),
            make_api_calendar(calendar_id="work@group.calendar.google.com", summary="Work", primary=False),
        ]
        result = filter_calendars(calendars, ["primary", "work@group.calendar.google.com"])
        assert len(result) == 2
