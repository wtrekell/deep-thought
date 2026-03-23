"""Tests for the GCal Tool markdown output generation."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

from deep_thought.gcal.models import EventLocal
from deep_thought.gcal.output import (
    _build_filename,
    _get_calendar_dir_name,
    _slugify,
    delete_event_file,
    generate_event_markdown,
    get_event_files_for_calendar,
    write_event_file,
)

# ---------------------------------------------------------------------------
# Helper to create a test EventLocal
# ---------------------------------------------------------------------------


def _make_test_event(
    event_id: str = "evt_test_1",
    calendar_id: str = "primary",
    summary: str = "Team Standup",
    description: str | None = "Daily standup meeting",
    location: str | None = "Conference Room B",
    start_time: str = "2026-03-24T09:00:00-05:00",
    end_time: str = "2026-03-24T09:30:00-05:00",
    all_day: bool = False,
    status: str = "confirmed",
    organizer: str | None = "manager@example.com",
    attendees: str | None = None,
    recurrence: str | None = None,
    html_link: str | None = "https://calendar.google.com/event?eid=test",
) -> EventLocal:
    """Create a test EventLocal with sensible defaults."""
    return EventLocal(
        event_id=event_id,
        calendar_id=calendar_id,
        summary=summary,
        description=description,
        location=location,
        start_time=start_time,
        end_time=end_time,
        all_day=all_day,
        status=status,
        organizer=organizer,
        attendees=attendees,
        recurrence=recurrence,
        html_link=html_link,
        created_at="2026-03-23T12:00:00+00:00",
        updated_at="2026-03-23T12:00:00+00:00",
        synced_at="2026-03-23T12:00:00+00:00",
    )


class TestSlugify:
    """Tests for _slugify."""

    def test_normal_text(self) -> None:
        """Should lowercase and replace spaces with hyphens."""
        assert _slugify("Team Standup") == "team-standup"

    def test_special_characters(self) -> None:
        """Should replace non-alphanumeric characters with hyphens."""
        assert _slugify("Meeting: Q1 Review!") == "meeting-q1-review"

    def test_empty_string(self) -> None:
        """Should return 'no-title' for empty input."""
        assert _slugify("") == "no-title"

    def test_truncation(self) -> None:
        """Should truncate to max_length."""
        long_text = "a" * 100
        result = _slugify(long_text, max_length=80)
        assert len(result) <= 80

    def test_consecutive_hyphens_collapsed(self) -> None:
        """Should collapse consecutive hyphens."""
        assert _slugify("Hello   World") == "hello-world"


class TestBuildFilename:
    """Tests for _build_filename."""

    def test_timed_event(self) -> None:
        """Should extract date from datetime start_time."""
        event = _make_test_event(start_time="2026-03-24T09:00:00-05:00")
        assert _build_filename(event) == "2026-03-24_team-standup.md"

    def test_allday_event(self) -> None:
        """Should extract date from date-only start_time."""
        event = _make_test_event(start_time="2026-03-25", summary="Company Holiday")
        assert _build_filename(event) == "2026-03-25_company-holiday.md"


class TestGetCalendarDirName:
    """Tests for _get_calendar_dir_name."""

    def test_normal_name(self) -> None:
        """Should slugify calendar name."""
        assert _get_calendar_dir_name("Personal Calendar") == "personal-calendar"


class TestGenerateEventMarkdown:
    """Tests for generate_event_markdown."""

    def test_includes_frontmatter(self) -> None:
        """Should include YAML frontmatter with tool identifier."""
        event = _make_test_event()
        result = generate_event_markdown(event)
        assert result.startswith("---\n")
        assert "tool: gcal" in result
        assert "event_id: evt_test_1" in result

    def test_includes_body(self) -> None:
        """Should include the event description after frontmatter."""
        event = _make_test_event(description="This is the event body.")
        result = generate_event_markdown(event)
        assert "This is the event body." in result

    def test_empty_description(self) -> None:
        """Should handle None description gracefully."""
        event = _make_test_event(description=None)
        result = generate_event_markdown(event)
        assert "---\n\n\n" in result

    def test_escapes_quotes_in_summary(self) -> None:
        """Should escape double quotes in summary."""
        event = _make_test_event(summary='Meeting: "Important" Update')
        result = generate_event_markdown(event)
        assert '\\"Important\\"' in result

    def test_includes_attendees(self) -> None:
        """Should include attendees in frontmatter when present."""
        import json

        event = _make_test_event(
            attendees=json.dumps([{"email": "colleague@example.com"}, {"email": "boss@example.com"}])
        )
        result = generate_event_markdown(event)
        assert "attendees:" in result
        assert '"colleague@example.com"' in result

    def test_includes_recurrence(self) -> None:
        """Should include recurrence rules in frontmatter when present."""
        import json

        event = _make_test_event(recurrence=json.dumps(["RRULE:FREQ=WEEKLY;COUNT=10"]))
        result = generate_event_markdown(event)
        assert "recurrence:" in result
        assert '"RRULE:FREQ=WEEKLY;COUNT=10"' in result

    def test_omits_null_optional_fields(self) -> None:
        """Should not include location, organizer, etc. when None."""
        event = _make_test_event(location=None, organizer=None, attendees=None, recurrence=None, html_link=None)
        result = generate_event_markdown(event)
        assert "location:" not in result
        assert "organizer:" not in result
        assert "html_link:" not in result


class TestWriteEventFile:
    """Tests for write_event_file."""

    def test_creates_file(self, tmp_path: Path) -> None:
        """Should create the markdown file at the expected path."""
        event = _make_test_event()
        file_path = write_event_file(
            content="---\ntool: gcal\n---\n\nContent",
            output_dir=tmp_path,
            calendar_name="Personal",
            event=event,
        )
        assert file_path.exists()
        assert "team-standup" in file_path.name
        assert file_path.read_text() == "---\ntool: gcal\n---\n\nContent"

    def test_creates_calendar_subdirectory(self, tmp_path: Path) -> None:
        """Should create the calendar subdirectory if it does not exist."""
        event = _make_test_event()
        file_path = write_event_file(
            content="content",
            output_dir=tmp_path,
            calendar_name="Work Calendar",
            event=event,
        )
        assert file_path.parent.name == "work-calendar"

    def test_flat_output(self, tmp_path: Path) -> None:
        """Should write directly to output_dir in flat mode."""
        event = _make_test_event()
        file_path = write_event_file(
            content="content",
            output_dir=tmp_path,
            calendar_name="Personal",
            event=event,
            flat_output=True,
        )
        assert file_path.parent == tmp_path


class TestDeleteEventFile:
    """Tests for delete_event_file."""

    def test_deletes_existing_file(self, tmp_path: Path) -> None:
        """Should delete the file and return True."""
        event = _make_test_event()
        write_event_file("content", tmp_path, "Personal", event)
        assert delete_event_file(tmp_path, "Personal", event) is True

    def test_returns_false_for_missing(self, tmp_path: Path) -> None:
        """Should return False when the file does not exist."""
        event = _make_test_event()
        assert delete_event_file(tmp_path, "Personal", event) is False


class TestGetEventFilesForCalendar:
    """Tests for get_event_files_for_calendar."""

    def test_lists_markdown_files(self, tmp_path: Path) -> None:
        """Should list all .md files in the calendar directory."""
        event1 = _make_test_event(event_id="e1", summary="First", start_time="2026-03-24T09:00:00-05:00")
        event2 = _make_test_event(event_id="e2", summary="Second", start_time="2026-03-25T09:00:00-05:00")
        write_event_file("content1", tmp_path, "Personal", event1)
        write_event_file("content2", tmp_path, "Personal", event2)
        files = get_event_files_for_calendar(tmp_path, "Personal")
        assert len(files) == 2

    def test_empty_directory(self, tmp_path: Path) -> None:
        """Should return empty list for nonexistent directory."""
        assert get_event_files_for_calendar(tmp_path, "Nonexistent") == []
