"""Tests for the GCal Tool event creation module."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock

import pytest

from deep_thought.gcal.create import (
    _build_api_event_body,
    _validate_start_before_end,
    parse_event_frontmatter,
    run_create,
)

if TYPE_CHECKING:
    import sqlite3

# Path to test fixture files
_FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# TestParseEventFrontmatter
# ---------------------------------------------------------------------------


class TestParseEventFrontmatter:
    """Tests for parse_event_frontmatter."""

    def test_valid_file_returns_frontmatter_and_body(self) -> None:
        """Should parse a well-formed file into a dict and body text."""
        frontmatter, body_text = parse_event_frontmatter(_FIXTURES_DIR / "create_event.md")

        assert frontmatter["summary"] == "Project Review"
        assert frontmatter["start"] == "2026-03-25T14:00:00-05:00"
        assert frontmatter["end"] == "2026-03-25T15:00:00-05:00"
        assert frontmatter["location"] == "Zoom"
        assert frontmatter["calendar_id"] == "primary"
        assert frontmatter["description"] == "Monthly review of project milestones"
        assert frontmatter["attendees"] == ["reviewer@example.com"]
        assert body_text == "Optional body text."

    def test_missing_required_field_raises_value_error(self, tmp_path: Path) -> None:
        """Should raise ValueError when a required field (summary) is absent."""
        missing_summary_file = tmp_path / "no_summary.md"
        missing_summary_file.write_text(
            "---\nstart: 2026-03-25T14:00:00-05:00\nend: 2026-03-25T15:00:00-05:00\n---\n",
            encoding="utf-8",
        )

        with pytest.raises(ValueError, match="summary"):
            parse_event_frontmatter(missing_summary_file)

    def test_body_text_extracted_when_no_frontmatter_description(self, tmp_path: Path) -> None:
        """Should return body text from content after the closing delimiter."""
        event_file = tmp_path / "body_only.md"
        event_file.write_text(
            "---\nsummary: Meeting\nstart: 2026-03-26\nend: 2026-03-27\n---\n\nThis is the body.\n",
            encoding="utf-8",
        )

        _, body_text = parse_event_frontmatter(event_file)

        assert body_text == "This is the body."

    def test_invalid_yaml_raises_value_error(self, tmp_path: Path) -> None:
        """Should raise ValueError for malformed YAML in the frontmatter block."""
        bad_yaml_file = tmp_path / "bad_yaml.md"
        # Colon without value and inconsistent indentation produces invalid YAML
        bad_yaml_file.write_text(
            "---\nsummary: :\n  - bad\nstart: 2026-03-26\nend: 2026-03-27\n---\n",
            encoding="utf-8",
        )

        with pytest.raises(ValueError, match="Invalid YAML"):
            parse_event_frontmatter(bad_yaml_file)

    def test_missing_file_raises_file_not_found_error(self) -> None:
        """Should raise FileNotFoundError for a path that does not exist."""
        nonexistent_path = _FIXTURES_DIR / "does_not_exist.md"

        with pytest.raises(FileNotFoundError):
            parse_event_frontmatter(nonexistent_path)

    def test_minimal_file_parses_correctly(self) -> None:
        """Should parse a file with only the three required fields."""
        frontmatter, body_text = parse_event_frontmatter(_FIXTURES_DIR / "minimal_event.md")

        assert frontmatter["summary"] == "Quick Meeting"
        assert frontmatter["start"] == "2026-03-26"
        assert frontmatter["end"] == "2026-03-27"
        assert body_text == ""


# ---------------------------------------------------------------------------
# TestBuildApiEventBody
# ---------------------------------------------------------------------------


class TestBuildApiEventBody:
    """Tests for _build_api_event_body."""

    def test_timed_event_uses_date_time_key(self) -> None:
        """Should use 'dateTime' for events with a time component."""
        frontmatter: dict[str, Any] = {
            "summary": "Team Meeting",
            "start": "2026-03-25T14:00:00-05:00",
            "end": "2026-03-25T15:00:00-05:00",
        }

        event_body = _build_api_event_body(frontmatter, "")

        assert event_body["start"] == {"dateTime": "2026-03-25T14:00:00-05:00"}
        assert event_body["end"] == {"dateTime": "2026-03-25T15:00:00-05:00"}

    def test_all_day_event_uses_date_key(self) -> None:
        """Should use 'date' for events with date-only start and end values."""
        frontmatter: dict[str, Any] = {
            "summary": "Company Holiday",
            "start": "2026-03-26",
            "end": "2026-03-27",
        }

        event_body = _build_api_event_body(frontmatter, "")

        assert event_body["start"] == {"date": "2026-03-26"}
        assert event_body["end"] == {"date": "2026-03-27"}

    def test_attendees_converted_to_api_format(self) -> None:
        """Should convert a list of email strings to a list of {'email': ...} dicts."""
        frontmatter: dict[str, Any] = {
            "summary": "Team Sync",
            "start": "2026-03-25T10:00:00-05:00",
            "end": "2026-03-25T11:00:00-05:00",
            "attendees": ["alice@example.com", "bob@example.com"],
        }

        event_body = _build_api_event_body(frontmatter, "")

        assert event_body["attendees"] == [
            {"email": "alice@example.com"},
            {"email": "bob@example.com"},
        ]

    def test_recurrence_passed_through_as_is(self) -> None:
        """Should include recurrence RRULE strings unchanged."""
        rrule_list = ["RRULE:FREQ=WEEKLY;COUNT=10"]
        frontmatter: dict[str, Any] = {
            "summary": "Weekly Sync",
            "start": "2026-03-25T10:00:00-05:00",
            "end": "2026-03-25T11:00:00-05:00",
            "recurrence": rrule_list,
        }

        event_body = _build_api_event_body(frontmatter, "")

        assert event_body["recurrence"] == rrule_list

    def test_minimal_event_contains_only_required_fields(self) -> None:
        """Should produce a body with only summary, start, and end when nothing else is set."""
        frontmatter: dict[str, Any] = {
            "summary": "Quick Meeting",
            "start": "2026-03-26",
            "end": "2026-03-27",
        }

        event_body = _build_api_event_body(frontmatter, "")

        assert set(event_body.keys()) == {"summary", "start", "end"}

    def test_body_text_used_as_description_when_not_in_frontmatter(self) -> None:
        """Should fall back to body_text as the description when frontmatter has no 'description'."""
        frontmatter: dict[str, Any] = {
            "summary": "Planning Session",
            "start": "2026-03-25T14:00:00-05:00",
            "end": "2026-03-25T15:00:00-05:00",
        }

        event_body = _build_api_event_body(frontmatter, "Notes from the planning session.")

        assert event_body["description"] == "Notes from the planning session."

    def test_frontmatter_description_takes_precedence_over_body_text(self) -> None:
        """Should prefer the frontmatter 'description' field over body_text."""
        frontmatter: dict[str, Any] = {
            "summary": "Project Review",
            "start": "2026-03-25T14:00:00-05:00",
            "end": "2026-03-25T15:00:00-05:00",
            "description": "Frontmatter description",
        }

        event_body = _build_api_event_body(frontmatter, "Body text that should be ignored.")

        assert event_body["description"] == "Frontmatter description"

    def test_no_description_when_both_are_empty(self) -> None:
        """Should omit 'description' entirely when frontmatter has none and body_text is empty."""
        frontmatter: dict[str, Any] = {
            "summary": "Quick Meeting",
            "start": "2026-03-26",
            "end": "2026-03-27",
        }

        event_body = _build_api_event_body(frontmatter, "")

        assert "description" not in event_body


# ---------------------------------------------------------------------------
# TestRunCreate
# ---------------------------------------------------------------------------


class TestRunCreate:
    """Tests for run_create."""

    def _make_mock_config(self, output_dir: str = "/tmp/gcal_test", flat_output: bool = False) -> MagicMock:
        """Build a minimal mock config for run_create tests."""
        mock_config = MagicMock()
        mock_config.output_dir = output_dir
        mock_config.flat_output = flat_output
        return mock_config

    def test_happy_path_creates_event_and_upserts_to_db(
        self, mock_gcal_client: MagicMock, in_memory_db: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """Should call insert_event, upsert to DB, and return a CreateResult with event_id."""
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

        # Supply a complete API-shaped response so EventLocal.from_api_response succeeds.
        mock_gcal_client.insert_event.return_value = {
            "id": "new_evt_abc",
            "summary": "Project Review",
            "start": {"dateTime": "2026-03-25T14:00:00-05:00"},
            "end": {"dateTime": "2026-03-25T15:00:00-05:00"},
            "status": "confirmed",
            "updated": "2026-03-23T12:00:00.000Z",
            "htmlLink": "https://calendar.google.com/event?eid=new_evt_abc",
        }
        mock_config = self._make_mock_config(output_dir=str(tmp_path))

        result = run_create(
            client=mock_gcal_client,
            config=mock_config,
            db_conn=in_memory_db,
            file_path=_FIXTURES_DIR / "create_event.md",
            output_dir=tmp_path,
        )

        assert result.event_id == "new_evt_abc"
        assert "new_evt_abc" in result.html_link
        mock_gcal_client.insert_event.assert_called_once()

        # Verify the event was persisted to the database
        from deep_thought.gcal.db.queries import get_event

        stored_event = get_event(in_memory_db, "new_evt_abc", "primary")
        assert stored_event is not None
        assert stored_event["summary"] == "Project Review"

    def test_dry_run_skips_api_call(
        self, mock_gcal_client: MagicMock, in_memory_db: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """Should return an empty CreateResult without calling insert_event."""
        mock_config = self._make_mock_config(output_dir=str(tmp_path))

        result = run_create(
            client=mock_gcal_client,
            config=mock_config,
            db_conn=in_memory_db,
            file_path=_FIXTURES_DIR / "create_event.md",
            dry_run=True,
            output_dir=tmp_path,
        )

        mock_gcal_client.insert_event.assert_not_called()
        assert result.event_id == ""
        assert result.html_link == ""

    def test_default_calendar_id_is_primary(
        self, mock_gcal_client: MagicMock, in_memory_db: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """Should use 'primary' as the calendar_id when none is specified in frontmatter."""
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

        mock_gcal_client.insert_event.return_value = {
            "id": "evt_primary_default",
            "summary": "Quick Meeting",
            "start": {"date": "2026-03-26"},
            "end": {"date": "2026-03-27"},
            "status": "confirmed",
            "updated": "2026-03-23T12:00:00.000Z",
            "htmlLink": "https://calendar.google.com/event?eid=evt_primary_default",
        }
        mock_config = self._make_mock_config(output_dir=str(tmp_path))

        run_create(
            client=mock_gcal_client,
            config=mock_config,
            db_conn=in_memory_db,
            file_path=_FIXTURES_DIR / "minimal_event.md",
            output_dir=tmp_path,
        )

        # The first positional argument to insert_event is the calendar_id
        call_args = mock_gcal_client.insert_event.call_args
        used_calendar_id: str = call_args[0][0]
        assert used_calendar_id == "primary"


# ---------------------------------------------------------------------------
# TestValidateStartBeforeEnd
# ---------------------------------------------------------------------------


class TestValidateStartBeforeEnd:
    """Tests for _validate_start_before_end."""

    def test_valid_timed_event_does_not_raise(self) -> None:
        """Should not raise when start is before end for a timed event."""
        _validate_start_before_end("2026-03-25T14:00:00-05:00", "2026-03-25T15:00:00-05:00")

    def test_valid_all_day_event_does_not_raise(self) -> None:
        """Should not raise when start is before end for an all-day event."""
        _validate_start_before_end("2026-03-25", "2026-03-26")

    def test_equal_start_and_end_raises(self) -> None:
        """Should raise ValueError when start equals end."""
        with pytest.raises(ValueError, match="start must be before end"):
            _validate_start_before_end("2026-03-25T14:00:00-05:00", "2026-03-25T14:00:00-05:00")

    def test_start_after_end_raises(self) -> None:
        """Should raise ValueError when start is after end."""
        with pytest.raises(ValueError, match="start must be before end"):
            _validate_start_before_end("2026-03-25T15:00:00-05:00", "2026-03-25T14:00:00-05:00")

    def test_run_create_raises_on_invalid_dates(
        self, mock_gcal_client: MagicMock, in_memory_db: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """run_create should raise ValueError before calling the API when start >= end."""
        invalid_file = tmp_path / "bad_dates.md"
        invalid_file.write_text(
            "---\nsummary: Bad Event\nstart: 2026-03-25T15:00:00-05:00\nend: 2026-03-25T14:00:00-05:00\n---\n",
            encoding="utf-8",
        )
        mock_config = MagicMock()
        mock_config.output_dir = str(tmp_path)
        mock_config.flat_output = False

        with pytest.raises(ValueError, match="start must be before end"):
            run_create(
                client=mock_gcal_client,
                config=mock_config,
                db_conn=in_memory_db,
                file_path=invalid_file,
            )

        mock_gcal_client.insert_event.assert_not_called()
