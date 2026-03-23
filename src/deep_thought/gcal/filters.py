"""Post-fetch event filtering for the GCal Tool.

Applied after API fetch, before database write. Handles cancelled event
exclusion, change detection, and calendar filtering.
"""

from __future__ import annotations

from typing import Any


def should_include_event(event: dict[str, Any], *, include_cancelled: bool = False) -> bool:
    """Check if an event should be included in the export.

    Excludes cancelled events unless include_cancelled is True.

    Args:
        event: A Google Calendar API event dict.
        include_cancelled: Whether to include cancelled events.

    Returns:
        True if the event should be included, False otherwise.
    """
    status = event.get("status", "confirmed")
    return not (status == "cancelled" and not include_cancelled)


def is_event_updated(event: dict[str, Any], existing_updated_at: str | None) -> bool:
    """Check if the remote event has been updated since the last sync.

    Compares the event's 'updated' timestamp against the locally stored
    updated_at. If no local record exists (existing_updated_at is None),
    the event is considered new and therefore updated.

    Args:
        event: A Google Calendar API event dict containing an 'updated' field.
        existing_updated_at: The locally stored updated_at timestamp, or None
                             if no local record exists.

    Returns:
        True if the event is new or has been modified remotely.
    """
    if existing_updated_at is None:
        return True
    remote_updated: str = event.get("updated", "")
    return remote_updated > existing_updated_at


def filter_calendars(
    available_calendars: list[dict[str, Any]],
    configured_calendar_ids: list[str],
) -> list[dict[str, Any]]:
    """Filter the calendar list to only include configured calendars.

    If configured_calendar_ids contains 'primary', matches the calendar
    where primary=True in the API response.

    Args:
        available_calendars: List of calendarList entries from the API.
        configured_calendar_ids: List of calendar IDs from the config.

    Returns:
        Filtered list of calendar dicts matching the configured IDs.
    """
    result: list[dict[str, Any]] = []
    for calendar in available_calendars:
        calendar_id = calendar.get("id", "")
        is_primary = calendar.get("primary", False)

        if calendar_id in configured_calendar_ids or ("primary" in configured_calendar_ids and is_primary):
            result.append(calendar)

    return result
