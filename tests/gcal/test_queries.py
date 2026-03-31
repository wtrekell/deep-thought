"""Tests for the GCal Tool database query functions."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import sqlite3

from deep_thought.gcal.db.queries import (
    clear_all_sync_tokens,
    clear_sync_token,
    delete_calendar,
    delete_event,
    delete_events_by_calendar,
    get_all_calendars,
    get_all_events,
    get_calendar,
    get_cancelled_events,
    get_event,
    get_events_by_calendar,
    get_events_in_range,
    get_key_value,
    get_sync_state,
    set_key_value,
    upsert_calendar,
    upsert_event,
    upsert_sync_state,
)


def _make_calendar_dict(
    calendar_id: str = "primary",
    summary: str = "Personal",
    description: str | None = "Main calendar",
    time_zone: str = "America/Chicago",
    primary_calendar: int = 1,
) -> dict:
    """Build a calendar dict for upsert_calendar."""
    return {
        "calendar_id": calendar_id,
        "summary": summary,
        "description": description,
        "time_zone": time_zone,
        "primary_calendar": primary_calendar,
        "created_at": datetime.now(UTC).isoformat(),
    }


def _make_event_dict(
    event_id: str = "evt_1",
    calendar_id: str = "primary",
    summary: str = "Test Event",
    start_time: str = "2026-03-24T09:00:00-05:00",
    end_time: str = "2026-03-24T10:00:00-05:00",
    all_day: int = 0,
    status: str = "confirmed",
) -> dict:
    """Build an event dict for upsert_event."""
    now_iso = datetime.now(UTC).isoformat()
    return {
        "event_id": event_id,
        "calendar_id": calendar_id,
        "summary": summary,
        "description": "Test description",
        "location": "Test Location",
        "start_time": start_time,
        "end_time": end_time,
        "all_day": all_day,
        "status": status,
        "organizer": "organizer@example.com",
        "attendees": None,
        "recurrence": None,
        "html_link": "https://calendar.google.com/event?eid=test",
        "created_at": now_iso,
        "updated_at": now_iso,
    }


# ---------------------------------------------------------------------------
# Calendar queries
# ---------------------------------------------------------------------------


class TestUpsertCalendar:
    """Tests for upsert_calendar."""

    def test_inserts_new_calendar(self, in_memory_db: sqlite3.Connection) -> None:
        """Should insert a new calendar row."""
        upsert_calendar(in_memory_db, _make_calendar_dict())
        in_memory_db.commit()
        result = get_calendar(in_memory_db, "primary")
        assert result is not None
        assert result["summary"] == "Personal"

    def test_updates_existing_preserves_created_at(self, in_memory_db: sqlite3.Connection) -> None:
        """Should update fields but preserve the original created_at."""
        upsert_calendar(in_memory_db, _make_calendar_dict())
        in_memory_db.commit()
        original = get_calendar(in_memory_db, "primary")
        assert original is not None
        original_created = original["created_at"]

        upsert_calendar(in_memory_db, _make_calendar_dict(summary="Updated Name"))
        in_memory_db.commit()
        updated = get_calendar(in_memory_db, "primary")
        assert updated is not None
        assert updated["summary"] == "Updated Name"
        assert updated["created_at"] == original_created


class TestGetCalendar:
    """Tests for get_calendar."""

    def test_returns_none_for_missing(self, in_memory_db: sqlite3.Connection) -> None:
        """Should return None when calendar does not exist."""
        assert get_calendar(in_memory_db, "nonexistent") is None


class TestGetAllCalendars:
    """Tests for get_all_calendars."""

    def test_returns_ordered_list(self, seeded_db: sqlite3.Connection) -> None:
        """Should return calendars ordered by primary_calendar DESC, then summary ASC."""
        calendars = get_all_calendars(seeded_db)
        assert len(calendars) == 2
        assert calendars[0]["calendar_id"] == "primary"  # primary_calendar=1 first

    def test_empty_table(self, in_memory_db: sqlite3.Connection) -> None:
        """Should return empty list when no calendars exist."""
        assert get_all_calendars(in_memory_db) == []


class TestDeleteCalendar:
    """Tests for delete_calendar."""

    def test_deletes_existing(self, seeded_db: sqlite3.Connection) -> None:
        """Should delete the calendar and return 1."""
        assert delete_calendar(seeded_db, "primary") == 1
        seeded_db.commit()
        assert get_calendar(seeded_db, "primary") is None

    def test_returns_zero_for_missing(self, in_memory_db: sqlite3.Connection) -> None:
        """Should return 0 when calendar does not exist."""
        assert delete_calendar(in_memory_db, "nonexistent") == 0


# ---------------------------------------------------------------------------
# Event queries
# ---------------------------------------------------------------------------


class TestUpsertEvent:
    """Tests for upsert_event."""

    def test_inserts_new_event(self, seeded_db: sqlite3.Connection) -> None:
        """Should insert a new event row."""
        upsert_event(seeded_db, _make_event_dict(event_id="evt_new"))
        seeded_db.commit()
        result = get_event(seeded_db, "evt_new", "primary")
        assert result is not None
        assert result["summary"] == "Test Event"

    def test_updates_existing_preserves_created_at(self, seeded_db: sqlite3.Connection) -> None:
        """Should update fields but preserve the original created_at."""
        original = get_event(seeded_db, "evt_timed_1", "primary")
        assert original is not None
        original_created = original["created_at"]

        upsert_event(seeded_db, _make_event_dict(event_id="evt_timed_1", summary="Updated Standup"))
        seeded_db.commit()
        updated = get_event(seeded_db, "evt_timed_1", "primary")
        assert updated is not None
        assert updated["summary"] == "Updated Standup"
        assert updated["created_at"] == original_created

    def test_composite_pk_distinct_calendars(self, seeded_db: sqlite3.Connection) -> None:
        """Same event_id in different calendars should be separate rows."""
        upsert_event(seeded_db, _make_event_dict(event_id="shared_evt", calendar_id="primary"))
        upsert_event(
            seeded_db,
            _make_event_dict(
                event_id="shared_evt",
                calendar_id="work@group.calendar.google.com",
                summary="Work Version",
            ),
        )
        seeded_db.commit()

        personal = get_event(seeded_db, "shared_evt", "primary")
        work = get_event(seeded_db, "shared_evt", "work@group.calendar.google.com")
        assert personal is not None
        assert work is not None
        assert personal["summary"] == "Test Event"
        assert work["summary"] == "Work Version"


class TestGetEvent:
    """Tests for get_event."""

    def test_returns_by_composite_pk(self, seeded_db: sqlite3.Connection) -> None:
        """Should find event by composite PK."""
        result = get_event(seeded_db, "evt_timed_1", "primary")
        assert result is not None
        assert result["summary"] == "Team Standup"

    def test_returns_none_for_wrong_calendar(self, seeded_db: sqlite3.Connection) -> None:
        """Should return None when event_id exists but calendar_id doesn't match."""
        assert get_event(seeded_db, "evt_timed_1", "wrong_calendar") is None


class TestGetEventsByCalendar:
    """Tests for get_events_by_calendar."""

    def test_returns_events_for_calendar(self, seeded_db: sqlite3.Connection) -> None:
        """Should return all events for the given calendar ordered by start_time."""
        events = get_events_by_calendar(seeded_db, "primary")
        assert len(events) == 4  # timed, recurring, allday, cancelled
        # Check ordering by start_time
        start_times = [e["start_time"] for e in events]
        assert start_times == sorted(start_times)

    def test_returns_empty_for_unknown_calendar(self, in_memory_db: sqlite3.Connection) -> None:
        """Should return empty list for a calendar with no events."""
        assert get_events_by_calendar(in_memory_db, "nonexistent") == []


class TestGetEventsInRange:
    """Tests for get_events_in_range."""

    def test_returns_events_in_range(self, seeded_db: sqlite3.Connection) -> None:
        """Should return only events within the time window."""
        events = get_events_in_range(seeded_db, "primary", "2026-03-24T00:00:00", "2026-03-25T00:00:00")
        # Should include timed and recurring events on 2026-03-24
        assert len(events) >= 2
        for event in events:
            assert event["start_time"] >= "2026-03-24T00:00:00"
            assert event["start_time"] < "2026-03-25T00:00:00"


class TestGetAllEvents:
    """Tests for get_all_events."""

    def test_returns_all_events(self, seeded_db: sqlite3.Connection) -> None:
        """Should return events from all calendars."""
        events = get_all_events(seeded_db)
        assert len(events) == 5  # 4 primary + 1 work


class TestDeleteEvent:
    """Tests for delete_event."""

    def test_deletes_by_composite_pk(self, seeded_db: sqlite3.Connection) -> None:
        """Should delete the correct event and return 1."""
        assert delete_event(seeded_db, "evt_timed_1", "primary") == 1
        seeded_db.commit()
        assert get_event(seeded_db, "evt_timed_1", "primary") is None

    def test_returns_zero_for_missing(self, seeded_db: sqlite3.Connection) -> None:
        """Should return 0 when event does not exist."""
        assert delete_event(seeded_db, "nonexistent", "primary") == 0


class TestDeleteEventsByCalendar:
    """Tests for delete_events_by_calendar."""

    def test_deletes_all_for_calendar(self, seeded_db: sqlite3.Connection) -> None:
        """Should delete all events for the given calendar."""
        deleted = delete_events_by_calendar(seeded_db, "primary")
        seeded_db.commit()
        assert deleted == 4
        assert get_events_by_calendar(seeded_db, "primary") == []

    def test_does_not_affect_other_calendars(self, seeded_db: sqlite3.Connection) -> None:
        """Deleting events for one calendar should not affect others."""
        delete_events_by_calendar(seeded_db, "primary")
        seeded_db.commit()
        work_events = get_events_by_calendar(seeded_db, "work@group.calendar.google.com")
        assert len(work_events) == 1


class TestGetCancelledEvents:
    """Tests for get_cancelled_events."""

    def test_returns_cancelled_only(self, seeded_db: sqlite3.Connection) -> None:
        """Should return only events with status 'cancelled'."""
        cancelled = get_cancelled_events(seeded_db, "primary")
        assert len(cancelled) == 1
        assert cancelled[0]["event_id"] == "evt_cancelled_1"


# ---------------------------------------------------------------------------
# Sync state queries
# ---------------------------------------------------------------------------


class TestSyncState:
    """Tests for sync state operations."""

    def test_upsert_and_get(self, seeded_db: sqlite3.Connection) -> None:
        """Should store and retrieve sync state."""
        state = get_sync_state(seeded_db, "primary")
        assert state is not None
        assert state["sync_token"] == "sync_token_abc"

    def test_get_returns_none_for_missing(self, in_memory_db: sqlite3.Connection) -> None:
        """Should return None for a calendar with no sync state."""
        assert get_sync_state(in_memory_db, "nonexistent") is None

    def test_clear_sync_token(self, seeded_db: sqlite3.Connection) -> None:
        """Should set sync_token to NULL for the given calendar."""
        clear_sync_token(seeded_db, "primary")
        seeded_db.commit()
        state = get_sync_state(seeded_db, "primary")
        assert state is not None
        assert state["sync_token"] is None

    def test_clear_all_sync_tokens(self, seeded_db: sqlite3.Connection) -> None:
        """Should set all sync tokens to NULL."""
        clear_all_sync_tokens(seeded_db)
        seeded_db.commit()
        for calendar_id in ("primary", "work@group.calendar.google.com"):
            state = get_sync_state(seeded_db, calendar_id)
            if state is not None:
                assert state["sync_token"] is None

    def test_upsert_overwrites_existing(self, seeded_db: sqlite3.Connection) -> None:
        """Should update sync_token and last_sync_time on conflict."""
        upsert_sync_state(seeded_db, "primary", "new_token_xyz", "2026-03-24T00:00:00Z")
        seeded_db.commit()
        state = get_sync_state(seeded_db, "primary")
        assert state is not None
        assert state["sync_token"] == "new_token_xyz"

    def test_upsert_sets_updated_at_and_synced_at(self, seeded_db: sqlite3.Connection) -> None:
        """upsert_sync_state should populate updated_at and synced_at with the current time."""
        upsert_sync_state(seeded_db, "primary", "token_ts_test", "2026-03-24T00:00:00Z")
        seeded_db.commit()
        state = get_sync_state(seeded_db, "primary")
        assert state is not None
        assert state["updated_at"] is not None
        assert state["synced_at"] is not None
        # Both should be recent ISO timestamps
        assert state["updated_at"].startswith("2026")
        assert state["synced_at"].startswith("2026")

    def test_clear_sync_token_updates_updated_at(self, seeded_db: sqlite3.Connection) -> None:
        """clear_sync_token should update updated_at on the cleared row."""
        state_before = get_sync_state(seeded_db, "primary")
        assert state_before is not None
        old_updated_at = state_before.get("updated_at")

        clear_sync_token(seeded_db, "primary")
        seeded_db.commit()
        state_after = get_sync_state(seeded_db, "primary")
        assert state_after is not None
        assert state_after["sync_token"] is None
        # updated_at should have changed from the epoch default or prior value
        assert state_after["updated_at"] != old_updated_at or old_updated_at == "1970-01-01T00:00:00+00:00"

    def test_clear_all_sync_tokens_updates_updated_at(self, seeded_db: sqlite3.Connection) -> None:
        """clear_all_sync_tokens should update updated_at for every row."""
        clear_all_sync_tokens(seeded_db)
        seeded_db.commit()
        for calendar_id in ("primary", "work@group.calendar.google.com"):
            state = get_sync_state(seeded_db, calendar_id)
            if state is not None:
                assert state["sync_token"] is None
                # updated_at should not be the epoch default after a clear
                assert state["updated_at"] != "1970-01-01T00:00:00+00:00"


# ---------------------------------------------------------------------------
# Key/value store
# ---------------------------------------------------------------------------


class TestKeyValue:
    """Tests for the key/value store."""

    def test_set_and_get(self, in_memory_db: sqlite3.Connection) -> None:
        """Should store and retrieve a key-value pair."""
        set_key_value(in_memory_db, "test_key", "test_value")
        in_memory_db.commit()
        assert get_key_value(in_memory_db, "test_key") == "test_value"

    def test_get_returns_none_for_missing(self, in_memory_db: sqlite3.Connection) -> None:
        """Should return None for a key that does not exist."""
        assert get_key_value(in_memory_db, "nonexistent") is None

    def test_overwrite_existing(self, in_memory_db: sqlite3.Connection) -> None:
        """Should overwrite an existing value."""
        set_key_value(in_memory_db, "key", "old")
        set_key_value(in_memory_db, "key", "new")
        in_memory_db.commit()
        assert get_key_value(in_memory_db, "key") == "new"
