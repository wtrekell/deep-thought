"""Pull/sync orchestration for the GCal Tool.

Fetches events from configured Google Calendars, stores them in SQLite,
and exports as LLM-optimized markdown. Supports incremental sync via
Calendar API sync tokens.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3  # noqa: TC003 — sqlite3.Connection is used at runtime in function signatures
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from googleapiclient.errors import HttpError  # type: ignore[import-untyped]

from deep_thought.gcal.db.queries import (
    clear_all_sync_tokens,
    clear_sync_token,
    delete_event,
    get_event,
    get_events_by_calendar,
    get_sync_state,
    upsert_calendar,
    upsert_event,
    upsert_sync_state,
)
from deep_thought.gcal.db.schema import get_data_dir
from deep_thought.gcal.filters import filter_calendars, is_event_updated, should_include_event
from deep_thought.gcal.llms import write_llms_files
from deep_thought.gcal.models import CalendarLocal, EventLocal, PullResult
from deep_thought.gcal.output import (
    delete_event_file,
    generate_event_markdown,
    get_event_files_for_calendar,
    write_event_file,
)
from deep_thought.progress import track_items

if TYPE_CHECKING:
    from deep_thought.gcal.client import GcalClient
    from deep_thought.gcal.config import GcalConfig

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Snapshot helper
# ---------------------------------------------------------------------------


def _write_snapshot(events: list[dict[str, Any]], data_dir: Path) -> Path:
    """Save a JSON snapshot of all fetched raw API events to disk.

    Creates a timestamped file under data_dir/snapshots/ that can be used
    for debugging or replaying a sync. The directory is created automatically
    if it does not exist.

    Args:
        events: List of raw Google Calendar API event dicts to snapshot.
        data_dir: Base data directory (e.g. data/gcal/).

    Returns:
        The Path to the written snapshot file.
    """
    snapshots_dir = data_dir / "snapshots"
    snapshots_dir.mkdir(parents=True, exist_ok=True)

    # Capture the timestamp once so the filename and JSON payload are consistent.
    snapshot_time = datetime.now(UTC)
    timestamp_str = snapshot_time.strftime("%Y-%m-%dT%H%M%S")
    snapshot_filename = f"{timestamp_str}.json"
    snapshot_path = snapshots_dir / snapshot_filename

    snapshot_payload: dict[str, Any] = {
        "timestamp": snapshot_time.isoformat(),
        "event_count": len(events),
        "events": events,
    }
    snapshot_path.write_text(json.dumps(snapshot_payload, indent=2), encoding="utf-8")
    logger.debug("Snapshot written to %s", snapshot_path)
    return snapshot_path


# ---------------------------------------------------------------------------
# Per-calendar sync
# ---------------------------------------------------------------------------


def _sync_single_calendar(
    client: GcalClient,
    calendar_id: str,
    calendar_summary: str,
    config: GcalConfig,
    db_conn: sqlite3.Connection,
    output_dir: Path,
    *,
    dry_run: bool,
    force: bool,
) -> PullResult:
    """Run the full sync pipeline for a single calendar.

    Fetches events from the Google Calendar API (using an incremental sync
    token when available, or a full time-windowed pull otherwise), compares
    each event against the local database to detect changes, writes updated
    events to SQLite and markdown, and deletes any cancelled events.

    Args:
        client: An authenticated GcalClient.
        calendar_id: The Google Calendar ID to sync.
        calendar_summary: The human-readable calendar name (used for output paths).
        config: The loaded GcalConfig.
        db_conn: An open SQLite connection.
        output_dir: Root directory for markdown output files.
        dry_run: If True, fetch and evaluate events but skip all writes.
        force: If True, clear the existing sync token before fetching.

    Returns:
        A PullResult summarising what happened for this calendar.
    """
    result = PullResult()

    # Step 1: Force mode clears the stored sync token so we do a full pull.
    if force:
        clear_sync_token(db_conn, calendar_id)
        logger.debug("Force mode: cleared sync token for calendar %s", calendar_id)

    # Step 2: Determine which fetch strategy to use.
    sync_state = get_sync_state(db_conn, calendar_id)
    stored_sync_token: str | None = sync_state.get("sync_token") if sync_state else None

    # Sync tokens are incompatible with single_events expansion, so we only
    # use the token when single_events is False. This matches the Calendar
    # API constraint that forbids mixing syncToken with singleEvents.
    use_sync_token = stored_sync_token is not None and not config.single_events

    if use_sync_token:
        logger.debug("Calendar %s: using incremental sync token", calendar_id)
        fetch_time_min: str | None = None
        fetch_time_max: str | None = None
        active_sync_token: str | None = stored_sync_token
    else:
        now_utc = datetime.now(UTC)
        time_min_dt = now_utc - timedelta(days=config.lookback_days)
        time_max_dt = now_utc + timedelta(days=config.lookahead_days)
        # RFC 3339 format required by the Calendar API
        fetch_time_min = time_min_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        fetch_time_max = time_max_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        active_sync_token = None
        logger.debug(
            "Calendar %s: full pull from %s to %s",
            calendar_id,
            fetch_time_min,
            fetch_time_max,
        )

    # Step 3: Fetch events from the API, falling back on 410 Gone.
    fetched_events: list[dict[str, Any]]
    new_sync_token: str | None

    try:
        fetched_events, new_sync_token = client.list_events(
            calendar_id,
            time_min=fetch_time_min,
            time_max=fetch_time_max,
            sync_token=active_sync_token,
            single_events=config.single_events,
        )
    except HttpError as http_error:
        status_code = http_error.resp.status if http_error.resp else 0
        if status_code == 410:
            # 410 Gone means the sync token has expired. Clear it and retry
            # with a full time-windowed pull.
            logger.warning(
                "Calendar %s: sync token expired (HTTP 410), falling back to full pull.",
                calendar_id,
            )
            clear_sync_token(db_conn, calendar_id)

            now_utc = datetime.now(UTC)
            time_min_dt = now_utc - timedelta(days=config.lookback_days)
            time_max_dt = now_utc + timedelta(days=config.lookahead_days)
            fallback_time_min = time_min_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            fallback_time_max = time_max_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

            fetched_events, new_sync_token = client.list_events(
                calendar_id,
                time_min=fallback_time_min,
                time_max=fallback_time_max,
                sync_token=None,
                single_events=config.single_events,
            )
        else:
            raise

    logger.debug("Calendar %s: fetched %d event(s) from API", calendar_id, len(fetched_events))

    # Step 4: Process each event.
    # All DB writes in the loop are wrapped in a savepoint so that a mid-loop
    # failure rolls back all writes for this calendar rather than leaving a
    # partially-updated state. A SAVEPOINT is used instead of BEGIN because
    # Python's sqlite3 module may have already implicitly started a transaction
    # (e.g. from the clear_sync_token call above), and nested BEGIN would error.
    # SAVEPOINT/RELEASE/ROLLBACK TO works at any nesting level.
    savepoint_name = f"sp_sync_{re.sub(r'[^a-zA-Z0-9_]', '_', calendar_id)}"

    try:
        db_conn.execute(f"SAVEPOINT {savepoint_name};")
        for api_event in track_items(fetched_events, description=f"Syncing: {calendar_summary}"):
            event_id: str = api_event.get("id", "")
            event_status: str = api_event.get("status", "confirmed")

            # Skip events that should not be included (e.g. cancelled when
            # include_cancelled=False). Cancelled events handled below are the
            # special case where we need to clean up an existing local record.
            if not should_include_event(api_event, include_cancelled=config.include_cancelled):
                # Even when include_cancelled=False we still need to clean up any
                # existing local record for a newly-cancelled event.
                if event_status == "cancelled":
                    existing_row = get_event(db_conn, event_id, calendar_id)
                    if existing_row is not None:
                        # Tombstone events from the API only carry id/status/updated —
                        # no start/end fields. Reconstruct from the local DB record
                        # so we can resolve the correct markdown file path to delete.
                        cancelled_event_local = EventLocal(
                            event_id=existing_row["event_id"],
                            calendar_id=existing_row["calendar_id"],
                            summary=existing_row["summary"],
                            description=existing_row.get("description"),
                            location=existing_row.get("location"),
                            start_time=existing_row["start_time"],
                            end_time=existing_row["end_time"],
                            all_day=bool(existing_row["all_day"]),
                            status=existing_row["status"],
                            organizer=existing_row.get("organizer"),
                            attendees=existing_row.get("attendees"),
                            recurrence=existing_row.get("recurrence"),
                            html_link=existing_row.get("html_link"),
                            created_at=existing_row["created_at"],
                            updated_at=existing_row["updated_at"],
                            synced_at=existing_row["synced_at"],
                        )
                        if not dry_run:
                            delete_event_file(
                                output_dir,
                                calendar_summary,
                                cancelled_event_local,
                                flat_output=config.flat_output,
                            )
                            delete_event(db_conn, event_id, calendar_id)
                        result.cancelled += 1
                        logger.debug("Calendar %s: cancelled event %s removed", calendar_id, event_id)
                continue

            # For non-cancelled events, check whether we already have an up-to-date
            # local copy so we can skip unnecessary writes.
            existing_row = get_event(db_conn, event_id, calendar_id)
            existing_updated_at: str | None = existing_row.get("updated_at") if existing_row else None

            if existing_row is not None and not is_event_updated(api_event, existing_updated_at):
                result.unchanged += 1
                logger.debug("Calendar %s: event %s unchanged, skipping", calendar_id, event_id)
                continue

            is_new_event = existing_row is None

            # Convert API dict to our local model.
            event_local = EventLocal.from_api_response(api_event, calendar_id)

            if not dry_run:
                upsert_event(db_conn, event_local.to_dict())
                event_markdown_content = generate_event_markdown(event_local)
                write_event_file(
                    event_markdown_content,
                    output_dir,
                    calendar_summary,
                    event_local,
                    flat_output=config.flat_output,
                )

            if is_new_event:
                result.created += 1
                logger.debug("Calendar %s: created event %s", calendar_id, event_id)
            else:
                result.updated += 1
                logger.debug("Calendar %s: updated event %s", calendar_id, event_id)

        db_conn.execute(f"RELEASE {savepoint_name};")
    except Exception as processing_error:
        db_conn.execute(f"ROLLBACK TO {savepoint_name};")
        db_conn.execute(f"RELEASE {savepoint_name};")
        logger.error(
            "Calendar %s: error during event processing — rolling back savepoint. Error: %s",
            calendar_id,
            processing_error,
        )
        raise

    # Step 5: Persist the new sync token when available.
    # Sync tokens are only returned (and valid) for non-single_events pulls.
    if new_sync_token is not None and not config.single_events and not dry_run:
        last_sync_time = datetime.now(UTC).isoformat()
        upsert_sync_state(db_conn, calendar_id, new_sync_token, last_sync_time)
        logger.debug("Calendar %s: sync token updated", calendar_id)

    result.calendars_synced = 1
    return result


# ---------------------------------------------------------------------------
# Top-level orchestrator
# ---------------------------------------------------------------------------


def run_pull(
    client: GcalClient,
    config: GcalConfig,
    db_conn: sqlite3.Connection,
    *,
    dry_run: bool = False,
    force: bool = False,
    calendar_override: list[str] | None = None,
    output_override: str | None = None,
) -> PullResult:
    """Orchestrate a full pull across all configured calendars.

    Fetches the calendar list from Google, filters to configured (or
    overridden) calendars, syncs each one via _sync_single_calendar, and
    optionally generates LLM index files and a raw JSON snapshot.

    Args:
        client: An authenticated GcalClient.
        config: The loaded GcalConfig.
        db_conn: An open SQLite connection.
        dry_run: If True, fetch and evaluate but skip all writes to disk and DB.
        force: If True, clear all stored sync tokens before syncing.
        calendar_override: Optional list of calendar IDs that replaces config.calendars.
        output_override: Optional string path that replaces config.output_dir.

    Returns:
        An aggregated PullResult across all calendars.
    """
    aggregated_result = PullResult()

    # Determine the output directory.
    resolved_output_dir = Path(output_override) if output_override is not None else Path(config.output_dir)

    # Force mode: wipe all sync tokens so every calendar does a full pull.
    if force and not dry_run:
        clear_all_sync_tokens(db_conn)
        logger.debug("Force mode: cleared all sync tokens")

    # Fetch the full calendar list from the API.
    all_api_calendars: list[dict[str, Any]] = client.list_calendars()
    logger.debug("Retrieved %d calendar(s) from API", len(all_api_calendars))

    # Filter to only the calendars we are configured (or overridden) to sync.
    configured_calendar_ids = calendar_override if calendar_override is not None else config.calendars
    target_calendars = filter_calendars(all_api_calendars, configured_calendar_ids)
    logger.debug("Syncing %d calendar(s) after filtering", len(target_calendars))

    # Collect all raw events for the snapshot.
    all_fetched_events: list[dict[str, Any]] = []

    for api_calendar in track_items(target_calendars, description="Syncing calendars"):
        calendar_id: str = api_calendar["id"]
        calendar_summary: str = api_calendar.get("summary", calendar_id)

        # Upsert the calendar metadata to our local DB.
        calendar_local = CalendarLocal.from_api_response(api_calendar)
        if not dry_run:
            upsert_calendar(db_conn, calendar_local.to_dict())

        # Run the per-calendar sync and merge its result into the aggregate.
        calendar_result = _sync_single_calendar(
            client,
            calendar_id,
            calendar_summary,
            config,
            db_conn,
            resolved_output_dir,
            dry_run=dry_run,
            force=force,
        )

        aggregated_result.created += calendar_result.created
        aggregated_result.updated += calendar_result.updated
        aggregated_result.cancelled += calendar_result.cancelled
        aggregated_result.unchanged += calendar_result.unchanged
        aggregated_result.calendars_synced += calendar_result.calendars_synced

        # Accumulate this calendar's events for the snapshot.
        calendar_events = get_events_by_calendar(db_conn, calendar_id) if not dry_run else []
        all_fetched_events.extend(calendar_events)

    # Commit all DB writes together.
    if not dry_run:
        db_conn.commit()

    # Generate LLM index files per calendar when configured.
    if config.generate_llms_files and not dry_run:
        for api_calendar in target_calendars:
            calendar_summary = api_calendar.get("summary", api_calendar["id"])
            event_files = get_event_files_for_calendar(
                resolved_output_dir,
                calendar_summary,
                flat_output=config.flat_output,
            )
            if event_files:
                write_llms_files(event_files, resolved_output_dir, calendar_summary)
                logger.debug("LLM files written for calendar %s", calendar_summary)

    # Write the raw snapshot.
    if not dry_run:
        data_dir = get_data_dir()
        _write_snapshot(all_fetched_events, data_dir)

    logger.info(
        "Pull complete: %d calendar(s), %d created, %d updated, %d cancelled, %d unchanged",
        aggregated_result.calendars_synced,
        aggregated_result.created,
        aggregated_result.updated,
        aggregated_result.cancelled,
        aggregated_result.unchanged,
    )

    return aggregated_result
