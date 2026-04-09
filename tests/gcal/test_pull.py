"""Tests for the GCal Tool pull/sync orchestration module."""

from __future__ import annotations

import json
import sqlite3  # noqa: TC003 — sqlite3.Connection used at runtime in helper and test signatures
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from deep_thought.gcal.db.queries import get_event, get_sync_state, upsert_calendar, upsert_sync_state
from deep_thought.gcal.pull import _sync_single_calendar, _write_snapshot, run_pull

from .conftest import make_api_calendar, make_api_event

# ---------------------------------------------------------------------------
# Config helper
# ---------------------------------------------------------------------------


def _make_config(
    calendars: list[str] | None = None,
    lookback_days: int = 7,
    lookahead_days: int = 30,
    include_cancelled: bool = False,
    single_events: bool = True,
    output_dir: str = "/tmp/gcal_test_output",
    generate_llms_files: bool = False,
    flat_output: bool = False,
) -> MagicMock:
    """Return a mock GcalConfig with controllable fields."""
    config = MagicMock()
    config.calendars = calendars if calendars is not None else ["primary"]
    config.lookback_days = lookback_days
    config.lookahead_days = lookahead_days
    config.include_cancelled = include_cancelled
    config.single_events = single_events
    config.output_dir = output_dir
    config.generate_llms_files = generate_llms_files
    config.flat_output = flat_output
    return config


def _seed_calendar(db_conn: sqlite3.Connection, calendar_id: str = "primary", summary: str = "Personal") -> None:
    """Insert a minimal calendar row so FK constraints on events are satisfied."""
    from datetime import UTC, datetime

    now_iso = datetime.now(UTC).isoformat()
    upsert_calendar(
        db_conn,
        {
            "calendar_id": calendar_id,
            "summary": summary,
            "description": None,
            "time_zone": "America/Chicago",
            "primary_calendar": 1,
            "created_at": now_iso,
        },
    )
    db_conn.commit()


# ---------------------------------------------------------------------------
# TestWriteSnapshot
# ---------------------------------------------------------------------------


class TestWriteSnapshot:
    """Tests for _write_snapshot."""

    def test_creates_file_in_snapshots_dir(self, tmp_path: Path) -> None:
        """The snapshot file should land inside data_dir/snapshots/."""
        events = [make_api_event()]
        result_path = _write_snapshot(events, tmp_path)

        snapshots_dir = tmp_path / "snapshots"
        assert snapshots_dir.exists()
        assert result_path.parent == snapshots_dir
        assert result_path.suffix == ".json"

    def test_json_content_is_correct(self, tmp_path: Path) -> None:
        """The snapshot should contain the events list and metadata."""
        api_event = make_api_event(event_id="evt_snap_1", summary="Snapshot Event")
        result_path = _write_snapshot([api_event], tmp_path)

        written_data = json.loads(result_path.read_text(encoding="utf-8"))
        assert written_data["event_count"] == 1
        assert "timestamp" in written_data
        assert written_data["events"][0]["id"] == "evt_snap_1"

    def test_empty_events_list_writes_file(self, tmp_path: Path) -> None:
        """An empty events list should still write a valid snapshot file."""
        result_path = _write_snapshot([], tmp_path)
        written_data = json.loads(result_path.read_text(encoding="utf-8"))
        assert written_data["event_count"] == 0
        assert written_data["events"] == []

    def test_creates_snapshots_dir_if_missing(self, tmp_path: Path) -> None:
        """snapshots/ directory should be created automatically."""
        data_dir = tmp_path / "nested" / "data"
        _write_snapshot([], data_dir)
        assert (data_dir / "snapshots").exists()


# ---------------------------------------------------------------------------
# TestSyncSingleCalendar
# ---------------------------------------------------------------------------


class TestSyncSingleCalendar:
    """Tests for _sync_single_calendar."""

    def test_full_pull_creates_new_events(
        self, in_memory_db: sqlite3.Connection, mock_gcal_client: MagicMock, tmp_path: Path
    ) -> None:
        """New events returned by a time-windowed pull should be inserted."""
        _seed_calendar(in_memory_db)
        new_api_event = make_api_event(event_id="evt_new_1", summary="New Meeting")
        mock_gcal_client.list_events.return_value = ([new_api_event], None)
        config = _make_config(single_events=True)  # forces time-windowed pull (no sync token)

        with (
            patch("deep_thought.gcal.pull.write_event_file"),
            patch("deep_thought.gcal.pull.generate_event_markdown", return_value="# markdown"),
        ):
            result = _sync_single_calendar(
                mock_gcal_client,
                "primary",
                "Personal",
                config,
                in_memory_db,
                tmp_path,
                dry_run=False,
                force=False,
            )

        assert result.created == 1
        assert result.updated == 0
        assert result.cancelled == 0
        assert result.unchanged == 0
        assert result.calendars_synced == 1

    def test_incremental_sync_token_used_when_available(
        self, in_memory_db: sqlite3.Connection, mock_gcal_client: MagicMock, tmp_path: Path
    ) -> None:
        """When a stored sync token exists and single_events=False, it should be passed to list_events."""
        from datetime import UTC, datetime

        _seed_calendar(in_memory_db)
        # Store a sync token in the DB.
        upsert_sync_state(in_memory_db, "primary", "token_abc", datetime.now(UTC).isoformat())
        in_memory_db.commit()

        updated_api_event = make_api_event(event_id="evt_updated_1", summary="Updated Event")
        new_token = "token_xyz"
        mock_gcal_client.list_events.return_value = ([updated_api_event], new_token)

        # single_events=False is required for sync token usage.
        config = _make_config(single_events=False)

        with (
            patch("deep_thought.gcal.pull.write_event_file"),
            patch("deep_thought.gcal.pull.generate_event_markdown", return_value="# markdown"),
        ):
            result = _sync_single_calendar(
                mock_gcal_client,
                "primary",
                "Personal",
                config,
                in_memory_db,
                tmp_path,
                dry_run=False,
                force=False,
            )

        # Confirm that list_events was called with the sync token.
        call_kwargs = mock_gcal_client.list_events.call_args
        assert call_kwargs.kwargs.get("sync_token") == "token_abc"
        assert result.created == 1

        # Confirm new token was persisted.
        stored_state = get_sync_state(in_memory_db, "primary")
        assert stored_state is not None
        assert stored_state["sync_token"] == new_token

    def test_410_fallback_clears_token_and_retries(
        self, in_memory_db: sqlite3.Connection, mock_gcal_client: MagicMock, tmp_path: Path
    ) -> None:
        """A 410 Gone response should clear the sync token and retry with a full pull."""
        from datetime import UTC, datetime

        from googleapiclient.errors import HttpError  # type: ignore[import-untyped]

        _seed_calendar(in_memory_db)
        # Seed a sync token.
        upsert_sync_state(in_memory_db, "primary", "stale_token", datetime.now(UTC).isoformat())
        in_memory_db.commit()

        # First call raises 410; second call (the retry) succeeds.
        mock_resp = MagicMock()
        mock_resp.status = 410
        stale_token_error = HttpError(resp=mock_resp, content=b"Sync token no longer valid")

        fallback_event = make_api_event(event_id="evt_fallback_1", summary="Fallback Event")
        mock_gcal_client.list_events.side_effect = [stale_token_error, ([fallback_event], None)]

        config = _make_config(single_events=False)

        with (
            patch("deep_thought.gcal.pull.write_event_file"),
            patch("deep_thought.gcal.pull.generate_event_markdown", return_value="# markdown"),
        ):
            result = _sync_single_calendar(
                mock_gcal_client,
                "primary",
                "Personal",
                config,
                in_memory_db,
                tmp_path,
                dry_run=False,
                force=False,
            )

        assert mock_gcal_client.list_events.call_count == 2
        # The retry call must NOT pass a sync token.
        retry_call_kwargs = mock_gcal_client.list_events.call_args
        assert retry_call_kwargs.kwargs.get("sync_token") is None
        assert result.created == 1

    def test_force_mode_clears_token_before_fetch(
        self, in_memory_db: sqlite3.Connection, mock_gcal_client: MagicMock, tmp_path: Path
    ) -> None:
        """force=True should clear the calendar's sync token before fetching."""
        from datetime import UTC, datetime

        _seed_calendar(in_memory_db)
        upsert_sync_state(in_memory_db, "primary", "existing_token", datetime.now(UTC).isoformat())
        in_memory_db.commit()

        mock_gcal_client.list_events.return_value = ([], None)
        config = _make_config(single_events=False)

        with patch("deep_thought.gcal.pull.write_event_file"):
            _sync_single_calendar(
                mock_gcal_client,
                "primary",
                "Personal",
                config,
                in_memory_db,
                tmp_path,
                dry_run=False,
                force=True,
            )

        # The sync token should have been cleared (force wipes it at the start).
        call_kwargs = mock_gcal_client.list_events.call_args
        # After clearing the token, single_events=False but no token — uses time window.
        assert call_kwargs.kwargs.get("sync_token") is None

    def test_dry_run_skips_db_and_file_writes(
        self, in_memory_db: sqlite3.Connection, mock_gcal_client: MagicMock, tmp_path: Path
    ) -> None:
        """dry_run=True should not write to the database or file system."""
        new_api_event = make_api_event(event_id="evt_dry_1", summary="Dry Run Event")
        mock_gcal_client.list_events.return_value = ([new_api_event], None)
        config = _make_config(single_events=True)

        with (
            patch("deep_thought.gcal.pull.write_event_file") as mock_write,
            patch("deep_thought.gcal.pull.upsert_event") as mock_upsert,
        ):
            result = _sync_single_calendar(
                mock_gcal_client,
                "primary",
                "Personal",
                config,
                in_memory_db,
                tmp_path,
                dry_run=True,
                force=False,
            )

        mock_write.assert_not_called()
        mock_upsert.assert_not_called()
        # The result still counts the would-be created event.
        assert result.created == 1

    def test_cancelled_event_deletes_local_record_and_file(
        self, seeded_db: sqlite3.Connection, mock_gcal_client: MagicMock, tmp_path: Path
    ) -> None:
        """A cancelled event that exists locally should be deleted from DB and disk."""
        # "evt_timed_1" exists in seeded_db for calendar "primary".
        cancelled_api_event = make_api_event(event_id="evt_timed_1", status="cancelled")
        mock_gcal_client.list_events.return_value = ([cancelled_api_event], None)
        config = _make_config(include_cancelled=False, single_events=True)

        with (
            patch("deep_thought.gcal.pull.delete_event_file") as mock_delete_file,
            patch("deep_thought.gcal.pull.delete_event") as mock_delete_db,
        ):
            result = _sync_single_calendar(
                mock_gcal_client,
                "primary",
                "Personal",
                config,
                seeded_db,
                tmp_path,
                dry_run=False,
                force=False,
            )

        mock_delete_file.assert_called_once()
        mock_delete_db.assert_called_once()
        assert result.cancelled == 1

    def test_tombstone_event_deletes_local_record_and_file(
        self, seeded_db: sqlite3.Connection, mock_gcal_client: MagicMock, tmp_path: Path
    ) -> None:
        """A tombstone event (cancelled with no start/end fields) should delete DB record and file.

        The Google Calendar incremental sync API returns tombstone entries for deleted
        events: only 'id', 'status: "cancelled"', and 'updated' are present — no 'start'
        or 'end' fields. The pull logic must handle this without crashing.
        """
        # Build a tombstone dict manually — no start/end fields at all.
        tombstone_event: dict[str, Any] = {
            "id": "evt_timed_1",
            "status": "cancelled",
            "updated": "2026-04-09T10:00:00.000Z",
        }
        mock_gcal_client.list_events.return_value = ([tombstone_event], None)
        config = _make_config(include_cancelled=False, single_events=True)

        with (
            patch("deep_thought.gcal.pull.delete_event_file") as mock_delete_file,
            patch("deep_thought.gcal.pull.delete_event") as mock_delete_db,
        ):
            result = _sync_single_calendar(
                mock_gcal_client,
                "primary",
                "Personal",
                config,
                seeded_db,
                tmp_path,
                dry_run=False,
                force=False,
            )

        mock_delete_file.assert_called_once()
        mock_delete_db.assert_called_once()
        assert result.cancelled == 1

    def test_unchanged_event_is_skipped(
        self, seeded_db: sqlite3.Connection, mock_gcal_client: MagicMock, tmp_path: Path
    ) -> None:
        """An event with the same updated timestamp as the local copy should not be re-written."""
        # "evt_timed_1" is in seeded_db with updated_at matching our make_api_event default.
        # We need to query the DB to find its actual updated_at.
        existing_row = get_event(seeded_db, "evt_timed_1", "primary")
        assert existing_row is not None
        existing_updated_at = existing_row["updated_at"]

        unchanged_api_event = make_api_event(
            event_id="evt_timed_1",
            summary="Team Standup",
            updated=existing_updated_at,
        )
        mock_gcal_client.list_events.return_value = ([unchanged_api_event], None)
        config = _make_config(single_events=True)

        with (
            patch("deep_thought.gcal.pull.write_event_file") as mock_write,
            patch("deep_thought.gcal.pull.upsert_event") as mock_upsert,
        ):
            result = _sync_single_calendar(
                mock_gcal_client,
                "primary",
                "Personal",
                config,
                seeded_db,
                tmp_path,
                dry_run=False,
                force=False,
            )

        mock_write.assert_not_called()
        mock_upsert.assert_not_called()
        assert result.unchanged == 1
        assert result.updated == 0

    def test_new_event_increments_created_counter(
        self, in_memory_db: sqlite3.Connection, mock_gcal_client: MagicMock, tmp_path: Path
    ) -> None:
        """A brand-new event (not in DB) should increment result.created."""
        _seed_calendar(in_memory_db)
        api_event = make_api_event(event_id="evt_brand_new", summary="Brand New Event")
        mock_gcal_client.list_events.return_value = ([api_event], None)
        config = _make_config(single_events=True)

        with (
            patch("deep_thought.gcal.pull.write_event_file"),
            patch("deep_thought.gcal.pull.generate_event_markdown", return_value="# markdown"),
        ):
            result = _sync_single_calendar(
                mock_gcal_client,
                "primary",
                "Personal",
                config,
                in_memory_db,
                tmp_path,
                dry_run=False,
                force=False,
            )

        assert result.created == 1
        assert result.updated == 0

    def test_updated_event_increments_updated_counter(
        self, seeded_db: sqlite3.Connection, mock_gcal_client: MagicMock, tmp_path: Path
    ) -> None:
        """An event that already exists but has a newer remote timestamp should increment result.updated."""
        # "evt_timed_1" is in seeded_db. Use a clearly newer timestamp.
        updated_api_event = make_api_event(
            event_id="evt_timed_1",
            summary="Team Standup — Updated",
            updated="2099-01-01T00:00:00.000Z",
        )
        mock_gcal_client.list_events.return_value = ([updated_api_event], None)
        config = _make_config(single_events=True)

        with (
            patch("deep_thought.gcal.pull.write_event_file"),
            patch("deep_thought.gcal.pull.generate_event_markdown", return_value="# markdown"),
        ):
            result = _sync_single_calendar(
                mock_gcal_client,
                "primary",
                "Personal",
                config,
                seeded_db,
                tmp_path,
                dry_run=False,
                force=False,
            )

        assert result.updated == 1
        assert result.created == 0

    def test_non_410_http_error_propagates(
        self, in_memory_db: sqlite3.Connection, mock_gcal_client: MagicMock, tmp_path: Path
    ) -> None:
        """HTTP errors other than 410 should not be swallowed."""
        from googleapiclient.errors import HttpError

        mock_resp = MagicMock()
        mock_resp.status = 403
        mock_gcal_client.list_events.side_effect = HttpError(resp=mock_resp, content=b"Forbidden")

        config = _make_config(single_events=True)

        with pytest.raises(HttpError):
            _sync_single_calendar(
                mock_gcal_client,
                "primary",
                "Personal",
                config,
                in_memory_db,
                tmp_path,
                dry_run=False,
                force=False,
            )


# ---------------------------------------------------------------------------
# TestRunPull
# ---------------------------------------------------------------------------


class TestRunPull:
    """Tests for run_pull."""

    def test_multiple_calendars_aggregated(
        self, in_memory_db: sqlite3.Connection, mock_gcal_client: MagicMock, tmp_path: Path
    ) -> None:
        """Results from multiple calendars should be summed in the returned PullResult."""
        personal_calendar = make_api_calendar(calendar_id="primary", summary="Personal", primary=True)
        work_calendar = make_api_calendar(calendar_id="work@group.calendar.google.com", summary="Work", primary=False)
        mock_gcal_client.list_calendars.return_value = [personal_calendar, work_calendar]

        personal_event = make_api_event(event_id="evt_personal_1", summary="Personal Event")
        work_event = make_api_event(
            event_id="evt_work_1", calendar_id="work@group.calendar.google.com", summary="Work Event"
        )

        def list_events_side_effect(
            calendar_id: str,
            time_min: str | None = None,
            time_max: str | None = None,
            sync_token: str | None = None,
            single_events: bool = True,
        ) -> tuple[list[dict[str, Any]], None]:
            if calendar_id == "primary":
                return ([personal_event], None)
            return ([work_event], None)

        mock_gcal_client.list_events.side_effect = list_events_side_effect
        config = _make_config(
            calendars=["primary", "work@group.calendar.google.com"],
            output_dir=str(tmp_path),
        )

        with (
            patch("deep_thought.gcal.pull.write_event_file"),
            patch("deep_thought.gcal.pull.generate_event_markdown", return_value="# markdown"),
            patch("deep_thought.gcal.pull._write_snapshot"),
        ):
            result = run_pull(mock_gcal_client, config, in_memory_db)

        assert result.calendars_synced == 2
        assert result.created == 2

    def test_calendar_override_filters_to_subset(
        self, in_memory_db: sqlite3.Connection, mock_gcal_client: MagicMock, tmp_path: Path
    ) -> None:
        """calendar_override should restrict syncing to only specified calendar IDs."""
        personal_calendar = make_api_calendar(calendar_id="primary", summary="Personal", primary=True)
        work_calendar = make_api_calendar(calendar_id="work@group.calendar.google.com", summary="Work", primary=False)
        mock_gcal_client.list_calendars.return_value = [personal_calendar, work_calendar]
        mock_gcal_client.list_events.return_value = ([], None)

        config = _make_config(
            calendars=["primary", "work@group.calendar.google.com"],
            output_dir=str(tmp_path),
        )

        with patch("deep_thought.gcal.pull._write_snapshot"):
            run_pull(
                mock_gcal_client,
                config,
                in_memory_db,
                calendar_override=["primary"],
            )

        # list_events should only have been called once (for primary).
        assert mock_gcal_client.list_events.call_count == 1
        first_call_args = mock_gcal_client.list_events.call_args_list[0]
        assert first_call_args.args[0] == "primary"

    def test_output_override_used_instead_of_config(
        self, in_memory_db: sqlite3.Connection, mock_gcal_client: MagicMock, tmp_path: Path
    ) -> None:
        """output_override should replace config.output_dir for file writes."""
        personal_calendar = make_api_calendar(calendar_id="primary", summary="Personal", primary=True)
        mock_gcal_client.list_calendars.return_value = [personal_calendar]

        new_event = make_api_event(event_id="evt_override_1", summary="Override Event")
        mock_gcal_client.list_events.return_value = ([new_event], None)

        config = _make_config(output_dir="/should/not/be/used", calendars=["primary"])
        override_dir = str(tmp_path / "override_output")

        captured_write_calls: list[Path] = []

        def mock_write_event_file(
            content: str,
            output_dir: Path,
            calendar_name: str,
            event: object,
            *,
            flat_output: bool = False,
        ) -> Path:
            captured_write_calls.append(output_dir)
            return Path(str(output_dir) + "/dummy.md")

        with (
            patch("deep_thought.gcal.pull.write_event_file", side_effect=mock_write_event_file),
            patch("deep_thought.gcal.pull.generate_event_markdown", return_value="# markdown"),
            patch("deep_thought.gcal.pull._write_snapshot"),
        ):
            run_pull(
                mock_gcal_client,
                config,
                in_memory_db,
                output_override=override_dir,
            )

        assert len(captured_write_calls) == 1
        assert str(captured_write_calls[0]) == override_dir

    def test_generate_llms_files_when_configured(
        self, in_memory_db: sqlite3.Connection, mock_gcal_client: MagicMock, tmp_path: Path
    ) -> None:
        """LLM index files should be generated when config.generate_llms_files is True."""
        personal_calendar = make_api_calendar(calendar_id="primary", summary="Personal", primary=True)
        mock_gcal_client.list_calendars.return_value = [personal_calendar]
        mock_gcal_client.list_events.return_value = ([], None)

        config = _make_config(
            calendars=["primary"],
            output_dir=str(tmp_path),
            generate_llms_files=True,
        )

        # get_event_files_for_calendar must return something so write_llms_files is called.
        dummy_md_file = tmp_path / "personal" / "260324-meeting.md"
        dummy_md_file.parent.mkdir(parents=True, exist_ok=True)
        dummy_md_file.write_text("# Meeting\n\nSome content.", encoding="utf-8")

        with (
            patch("deep_thought.gcal.pull.get_event_files_for_calendar", return_value=[dummy_md_file]),
            patch("deep_thought.gcal.pull.write_llms_files") as mock_llms,
            patch("deep_thought.gcal.pull._write_snapshot"),
        ):
            run_pull(mock_gcal_client, config, in_memory_db)

        mock_llms.assert_called_once()
        call_args = mock_llms.call_args
        assert call_args.args[2] == "Personal"

    def test_force_clears_all_tokens(
        self, seeded_db: sqlite3.Connection, mock_gcal_client: MagicMock, tmp_path: Path
    ) -> None:
        """force=True should clear all stored sync tokens via clear_all_sync_tokens."""
        personal_calendar = make_api_calendar(calendar_id="primary", summary="Personal", primary=True)
        mock_gcal_client.list_calendars.return_value = [personal_calendar]
        mock_gcal_client.list_events.return_value = ([], None)

        config = _make_config(calendars=["primary"], output_dir=str(tmp_path))

        with (
            patch("deep_thought.gcal.pull.clear_all_sync_tokens") as mock_clear_all,
            patch("deep_thought.gcal.pull._write_snapshot"),
        ):
            run_pull(mock_gcal_client, config, seeded_db, force=True)

        mock_clear_all.assert_called_once_with(seeded_db)

    def test_dry_run_skips_snapshot_and_db_writes(
        self, in_memory_db: sqlite3.Connection, mock_gcal_client: MagicMock, tmp_path: Path
    ) -> None:
        """dry_run=True should skip the snapshot write and all DB commits."""
        personal_calendar = make_api_calendar(calendar_id="primary", summary="Personal", primary=True)
        mock_gcal_client.list_calendars.return_value = [personal_calendar]

        new_api_event = make_api_event(event_id="evt_dryrun_top", summary="Dry Run Top Event")
        mock_gcal_client.list_events.return_value = ([new_api_event], None)

        config = _make_config(calendars=["primary"], output_dir=str(tmp_path))

        with (
            patch("deep_thought.gcal.pull._write_snapshot") as mock_snapshot,
            patch("deep_thought.gcal.pull.upsert_event") as mock_upsert,
            patch("deep_thought.gcal.pull.upsert_calendar") as mock_upsert_cal,
        ):
            result = run_pull(mock_gcal_client, config, in_memory_db, dry_run=True)

        mock_snapshot.assert_not_called()
        mock_upsert.assert_not_called()
        mock_upsert_cal.assert_not_called()
        assert result.created == 1
