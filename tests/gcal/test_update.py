"""Tests for the GCal Tool event update module."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock

import pytest

from deep_thought.gcal.create import _validate_attendee_emails
from deep_thought.gcal.update import _diff_event_fields, run_update

if TYPE_CHECKING:
    import sqlite3

# Path to test fixture files
_FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# TestValidateAttendeeEmailsInUpdate
# ---------------------------------------------------------------------------


class TestValidateAttendeeEmailsInUpdate:
    """Ensure _validate_attendee_emails is exercised through _diff_event_fields."""

    def test_invalid_attendee_emails_excluded_from_patch_body(self) -> None:
        """_diff_event_fields should only pass valid emails to the patch body."""
        frontmatter: dict[str, Any] = {
            "summary": "Review",
            "start": "2026-03-25T14:00:00-05:00",
            "end": "2026-03-25T15:00:00-05:00",
            "attendees": ["valid@example.com", "not-valid"],
        }
        existing_event: dict[str, Any] = {
            "summary": "Review",
            "start": {"dateTime": "2026-03-25T14:00:00-05:00"},
            "end": {"dateTime": "2026-03-25T15:00:00-05:00"},
            "attendees": None,
        }

        patch_body, fields_changed = _diff_event_fields(frontmatter, existing_event)

        assert "attendees" in fields_changed
        assert patch_body["attendees"] == [{"email": "valid@example.com"}]

    def test_all_invalid_emails_results_in_none_attendees(self) -> None:
        """When every entry is invalid, validated list is empty → new_attendees is None."""
        result = _validate_attendee_emails(["no-at-sign", "also-bad"])
        assert result == []


# ---------------------------------------------------------------------------
# TestDiffEventFields
# ---------------------------------------------------------------------------


class TestDiffEventFields:
    """Tests for _diff_event_fields."""

    def _make_api_event(self, **overrides: Any) -> dict[str, Any]:
        """Build a minimal API-shaped event dict with optional field overrides."""
        base: dict[str, Any] = {
            "summary": "Original Summary",
            "start": {"dateTime": "2026-03-25T14:00:00-05:00"},
            "end": {"dateTime": "2026-03-25T15:00:00-05:00"},
            "location": "Zoom",
            "description": "Original description",
            "attendees": None,
            "recurrence": None,
        }
        base.update(overrides)
        return base

    def test_changed_summary_detected(self) -> None:
        """Should include 'summary' in patch_body and fields_changed when it differs."""
        frontmatter: dict[str, Any] = {
            "summary": "New Summary",
            "start": "2026-03-25T14:00:00-05:00",
            "end": "2026-03-25T15:00:00-05:00",
        }
        existing_event = self._make_api_event(summary="Original Summary")

        patch_body, fields_changed = _diff_event_fields(frontmatter, existing_event)

        assert "summary" in fields_changed
        assert patch_body["summary"] == "New Summary"

    def test_changed_time_detected(self) -> None:
        """Should detect a changed end time and include it in the patch."""
        frontmatter: dict[str, Any] = {
            "summary": "Original Summary",
            "start": "2026-03-25T14:00:00-05:00",
            "end": "2026-03-25T16:00:00-05:00",  # extended by one hour
        }
        existing_event = self._make_api_event(end={"dateTime": "2026-03-25T15:00:00-05:00"})

        patch_body, fields_changed = _diff_event_fields(frontmatter, existing_event)

        assert "end" in fields_changed
        assert patch_body["end"] == {"dateTime": "2026-03-25T16:00:00-05:00"}
        assert "start" not in fields_changed

    def test_no_changes_returns_empty(self) -> None:
        """Should return empty patch_body and fields_changed when nothing differs."""
        frontmatter: dict[str, Any] = {
            "summary": "Original Summary",
            "start": "2026-03-25T14:00:00-05:00",
            "end": "2026-03-25T15:00:00-05:00",
            "location": "Zoom",
            "description": "Original description",
        }
        existing_event = self._make_api_event()

        patch_body, fields_changed = _diff_event_fields(frontmatter, existing_event)

        assert patch_body == {}
        assert fields_changed == []

    def test_all_day_to_timed_change_detected(self) -> None:
        """Should detect a change from an all-day event to a timed event."""
        frontmatter: dict[str, Any] = {
            "summary": "Conference Day",
            "start": "2026-03-25T09:00:00-05:00",  # now timed
            "end": "2026-03-25T17:00:00-05:00",
        }
        existing_event = self._make_api_event(
            start={"date": "2026-03-25"},  # was all-day
            end={"date": "2026-03-26"},
        )

        patch_body, fields_changed = _diff_event_fields(frontmatter, existing_event)

        assert "start" in fields_changed
        assert "end" in fields_changed
        assert patch_body["start"] == {"dateTime": "2026-03-25T09:00:00-05:00"}

    def test_changed_location_detected(self) -> None:
        """Should include 'location' in the diff when it changes."""
        frontmatter: dict[str, Any] = {
            "summary": "Original Summary",
            "start": "2026-03-25T14:00:00-05:00",
            "end": "2026-03-25T15:00:00-05:00",
            "location": "Conference Room B",
        }
        existing_event = self._make_api_event(location="Zoom")

        patch_body, fields_changed = _diff_event_fields(frontmatter, existing_event)

        assert "location" in fields_changed
        assert patch_body["location"] == "Conference Room B"

    def test_added_attendees_detected(self) -> None:
        """Should detect when attendees are added to an event that previously had none."""
        frontmatter: dict[str, Any] = {
            "summary": "Original Summary",
            "start": "2026-03-25T14:00:00-05:00",
            "end": "2026-03-25T15:00:00-05:00",
            "attendees": ["new_person@example.com"],
        }
        existing_event = self._make_api_event(attendees=None)

        patch_body, fields_changed = _diff_event_fields(frontmatter, existing_event)

        assert "attendees" in fields_changed
        assert patch_body["attendees"] == [{"email": "new_person@example.com"}]


# ---------------------------------------------------------------------------
# TestRunUpdate
# ---------------------------------------------------------------------------


class TestRunUpdate:
    """Tests for run_update."""

    def _make_mock_config(self, output_dir: str = "/tmp/gcal_test", flat_output: bool = False) -> MagicMock:
        """Build a minimal mock config for run_update tests."""
        mock_config = MagicMock()
        mock_config.output_dir = output_dir
        mock_config.flat_output = flat_output
        return mock_config

    def _make_patch_response(self) -> dict[str, Any]:
        """Return a complete API-shaped event response for patch_event mocks."""
        return {
            "id": "evt_existing_1",
            "summary": "Updated Project Review",
            "start": {"dateTime": "2026-03-25T14:00:00-05:00"},
            "end": {"dateTime": "2026-03-25T15:30:00-05:00"},
            "status": "confirmed",
            "updated": "2026-03-23T13:00:00.000Z",
            "htmlLink": "https://calendar.google.com/event?eid=evt_existing_1",
        }

    def test_happy_path_patches_and_upserts(
        self, mock_gcal_client: MagicMock, in_memory_db: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """Should call patch_event, upsert to DB, and return an UpdateResult with fields_changed."""
        # Seed the 'primary' calendar row so the FK constraint on events.calendar_id is satisfied.
        from datetime import UTC, datetime

        from deep_thought.gcal.db.queries import upsert_calendar

        upsert_calendar(
            in_memory_db,
            {
                "calendar_id": "primary",
                "summary": "Personal",
                "description": None,
                "time_zone": "America/Chicago",
                "primary_calendar": 1,
                "created_at": datetime.now(UTC).isoformat(),
            },
        )
        in_memory_db.commit()

        mock_gcal_client.get_event.return_value = {
            "id": "evt_existing_1",
            "summary": "Project Review",  # will change
            "start": {"dateTime": "2026-03-25T14:00:00-05:00"},
            "end": {"dateTime": "2026-03-25T15:00:00-05:00"},  # will change
            "status": "confirmed",
        }
        mock_gcal_client.patch_event.return_value = self._make_patch_response()
        mock_config = self._make_mock_config(output_dir=str(tmp_path))

        result = run_update(
            client=mock_gcal_client,
            config=mock_config,
            db_conn=in_memory_db,
            file_path=_FIXTURES_DIR / "update_event.md",
            output_dir=tmp_path,
        )

        mock_gcal_client.patch_event.assert_called_once()
        assert result.event_id == "evt_existing_1"
        assert "summary" in result.fields_changed or "end" in result.fields_changed

        # Verify DB persistence
        from deep_thought.gcal.db.queries import get_event

        stored_event = get_event(in_memory_db, "evt_existing_1", "primary")
        assert stored_event is not None

    def test_no_changes_logs_message_and_skips_patch(
        self, mock_gcal_client: MagicMock, in_memory_db: sqlite3.Connection, tmp_path: Path, caplog: Any
    ) -> None:
        """Should skip patch_event and return empty fields_changed when nothing differs.

        The update_event.md fixture has no 'description' frontmatter key, so
        _diff_event_fields compares frontmatter description=None against the
        existing event. To produce zero diffs the existing event must also have
        no description (i.e. the key is absent / None).
        """
        mock_gcal_client.get_event.return_value = {
            "id": "evt_existing_1",
            "summary": "Updated Project Review",
            "start": {"dateTime": "2026-03-25T14:00:00-05:00"},
            "end": {"dateTime": "2026-03-25T15:30:00-05:00"},
            "location": "Conference Room A",
            # No 'description' key — matches the None from frontmatter.get("description")
            "status": "confirmed",
        }
        mock_config = self._make_mock_config(output_dir=str(tmp_path))

        import logging

        with caplog.at_level(logging.INFO, logger="deep_thought.gcal.update"):
            result = run_update(
                client=mock_gcal_client,
                config=mock_config,
                db_conn=in_memory_db,
                file_path=_FIXTURES_DIR / "update_event.md",
                output_dir=tmp_path,
            )

        mock_gcal_client.patch_event.assert_not_called()
        assert result.fields_changed == []
        assert "no changes" in caplog.text.lower()

    def test_missing_event_id_raises_value_error(
        self, mock_gcal_client: MagicMock, in_memory_db: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """Should raise ValueError when the frontmatter has no event_id field."""
        mock_config = self._make_mock_config(output_dir=str(tmp_path))

        with pytest.raises(ValueError, match="event_id"):
            run_update(
                client=mock_gcal_client,
                config=mock_config,
                db_conn=in_memory_db,
                file_path=_FIXTURES_DIR / "create_event.md",  # has no event_id
                output_dir=tmp_path,
            )

    def test_dry_run_skips_api_call(
        self, mock_gcal_client: MagicMock, in_memory_db: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """Should skip patch_event but still return detected fields_changed."""
        mock_gcal_client.get_event.return_value = {
            "id": "evt_existing_1",
            "summary": "Old Summary",  # will differ from update_event.md
            "start": {"dateTime": "2026-03-25T14:00:00-05:00"},
            "end": {"dateTime": "2026-03-25T15:00:00-05:00"},
            "status": "confirmed",
        }
        mock_config = self._make_mock_config(output_dir=str(tmp_path))

        result = run_update(
            client=mock_gcal_client,
            config=mock_config,
            db_conn=in_memory_db,
            file_path=_FIXTURES_DIR / "update_event.md",
            dry_run=True,
            output_dir=tmp_path,
        )

        mock_gcal_client.patch_event.assert_not_called()
        assert "summary" in result.fields_changed
