"""Google Calendar API client wrapper with OAuth 2.0 authentication.

Wraps the Google API Python Client in a thin class that normalises the API
surface used by the rest of the tool, making it easy to mock in tests.
Handles pagination, rate limiting, and retry with exponential backoff.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from googleapiclient.discovery import build  # type: ignore[import-untyped]
from googleapiclient.errors import HttpError  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Retry helper
# ---------------------------------------------------------------------------

_RETRYABLE_STATUS_CODES = {429, 500, 503}


def _retry_with_backoff(
    func: Any,
    max_attempts: int = 3,
    base_delay: float = 1.0,
) -> Any:
    """Execute a callable with exponential backoff on transient errors.

    Retries on HTTP 429, 500, and 503 errors. Permanent 4xx errors (other
    than 429) are raised immediately.

    Args:
        func: A callable that may raise HttpError.
        max_attempts: Maximum number of attempts (including the first).
        base_delay: Initial delay in seconds; doubles on each retry.

    Returns:
        The return value of func() on success.

    Raises:
        HttpError: If all attempts fail or a non-retryable error occurs.
    """
    last_error: HttpError | None = None  # type: ignore[no-any-unimported]
    delay = base_delay

    for attempt in range(max_attempts):
        try:
            return func()
        except HttpError as http_error:
            last_error = http_error
            status_code = http_error.resp.status if http_error.resp else 0

            if status_code not in _RETRYABLE_STATUS_CODES:
                raise

            if attempt < max_attempts - 1:
                logger.warning(
                    "Calendar API error %d (attempt %d/%d), retrying in %.1fs...",
                    status_code,
                    attempt + 1,
                    max_attempts,
                    delay,
                )
                time.sleep(delay)
                delay *= 2

    if last_error is not None:
        logger.error(
            "Calendar API call failed after %d attempt(s). Final error: %s",
            max_attempts,
            last_error,
        )
        raise last_error
    raise RuntimeError("Unexpected state in _retry_with_backoff")  # pragma: no cover


# ---------------------------------------------------------------------------
# GcalClient
# ---------------------------------------------------------------------------


class GcalClient:
    """Thin wrapper around the Google Calendar API v3 service object.

    Handles OAuth 2.0 authentication, pagination collapsing, rate limiting,
    and retry with exponential backoff.
    """

    def __init__(
        self,
        credentials_path: str,
        token_path: str,
        scopes: list[str],
        rate_limit_rpm: int = 250,
        retry_max_attempts: int = 3,
        retry_base_delay: float = 1.0,
    ) -> None:
        """Store configuration for later authentication.

        Does NOT authenticate on construction — call authenticate() to build
        the API service. This separation allows the CLI 'auth' command to run
        the flow independently.

        Args:
            credentials_path: Path to the OAuth client secret JSON file.
            token_path: Path to store/load the OAuth access + refresh token.
            scopes: List of OAuth scope URIs to request.
            rate_limit_rpm: Maximum requests per minute to the Calendar API.
            retry_max_attempts: Max retry attempts for transient errors.
            retry_base_delay: Initial backoff delay in seconds.
        """
        self._credentials_path = credentials_path
        self._token_path = token_path
        self._scopes = scopes
        self._rate_limit_rpm = rate_limit_rpm
        self._retry_max_attempts = retry_max_attempts
        self._retry_base_delay = retry_base_delay
        self._service: Any = None
        self._last_request_time: float = 0.0

    def authenticate(self) -> None:
        """Run the OAuth 2.0 flow and build the Calendar API service.

        Delegates to the shared ``deep_thought.secrets`` module for keychain-first
        token storage with file fallback.  See ``gcal._auth.get_credentials``
        for the full lifecycle.

        Raises:
            FileNotFoundError: If credentials_path does not exist.
            google.auth.exceptions.RefreshError: If token refresh fails.
        """
        from deep_thought.gcal._auth import get_credentials

        credentials = get_credentials(self._credentials_path, self._token_path, self._scopes)
        self._service = build("calendar", "v3", credentials=credentials)
        logger.debug("Calendar API service initialised.")

    def _rate_limit(self) -> None:
        """Enforce a simple rate limit between API calls.

        Sleeps if the minimum interval since the last request has not elapsed.
        """
        if self._rate_limit_rpm <= 0:
            return
        minimum_interval = 60.0 / self._rate_limit_rpm
        elapsed = time.time() - self._last_request_time
        if elapsed < minimum_interval:
            time.sleep(minimum_interval - elapsed)
        self._last_request_time = time.time()

    def _execute(self, request: Any) -> Any:
        """Execute a Calendar API request with rate limiting and retry.

        Args:
            request: A Google API request object (from .list(), .get(), etc.).

        Returns:
            The API response dict.

        Raises:
            RuntimeError: If authenticate() has not been called before this method.
        """
        if self._service is None:
            raise RuntimeError("Must call authenticate() before making API requests.")
        self._rate_limit()
        return _retry_with_backoff(
            request.execute,
            max_attempts=self._retry_max_attempts,
            base_delay=self._retry_base_delay,
        )

    # -----------------------------------------------------------------------
    # Calendar list operations
    # -----------------------------------------------------------------------

    def list_calendars(self) -> list[dict[str, Any]]:
        """Fetch all calendars from the calendarList API with pagination.

        Collapses pagination into a flat list. Each entry contains the full
        calendar metadata including 'id', 'summary', 'accessRole', etc.

        Returns:
            A flat list of calendarList entry dicts.
        """
        calendars: list[dict[str, Any]] = []
        page_token: str | None = None

        while True:
            request = self._service.calendarList().list(pageToken=page_token)
            response = self._execute(request)

            batch: list[dict[str, Any]] = response.get("items", [])
            calendars.extend(batch)

            page_token = response.get("nextPageToken")
            if not page_token:
                break

        return calendars

    # -----------------------------------------------------------------------
    # Event operations
    # -----------------------------------------------------------------------

    def list_events(
        self,
        calendar_id: str,
        time_min: str | None = None,
        time_max: str | None = None,
        sync_token: str | None = None,
        single_events: bool = True,
    ) -> tuple[list[dict[str, Any]], str | None]:
        """Fetch events with pagination. Returns (events_list, next_sync_token).

        When sync_token is provided, the Calendar API prohibits supplying
        time_min, time_max, or singleEvents — those parameters are omitted
        automatically.

        Args:
            calendar_id: The calendar ID to query (e.g. 'primary').
            time_min: RFC 3339 timestamp lower bound (ignored when sync_token is set).
            time_max: RFC 3339 timestamp upper bound (ignored when sync_token is set).
            sync_token: Incremental sync token from a previous call's response.
            single_events: Whether to expand recurring events into instances
                           (ignored when sync_token is set).

        Returns:
            A tuple of (flat list of event dicts, next_sync_token or None).
        """
        events: list[dict[str, Any]] = []
        page_token: str | None = None
        next_sync_token: str | None = None
        is_first_page = True

        while True:
            if sync_token is not None:
                # The Calendar API forbids time_min/time_max/singleEvents with syncToken
                params: dict[str, Any] = {
                    "calendarId": calendar_id,
                    "syncToken": sync_token,
                    "pageToken": page_token,
                }
            else:
                params = {
                    "calendarId": calendar_id,
                    "singleEvents": single_events,
                    "pageToken": page_token,
                }
                if time_min is not None:
                    params["timeMin"] = time_min
                if time_max is not None:
                    params["timeMax"] = time_max

            request = self._service.events().list(**params)
            try:
                response = self._execute(request)
            except (HttpError, OSError, TimeoutError) as page_error:
                if is_first_page:
                    # An error on the first page means we have nothing — re-raise.
                    raise
                # For page 2+, we already have partial results. Log a warning
                # and return what we have rather than discarding all prior pages.
                logger.warning(
                    "Calendar %s: pagination error on page 2+ — returning %d event(s) fetched so far. Error: %s",
                    calendar_id,
                    len(events),
                    page_error,
                )
                break

            is_first_page = False
            batch: list[dict[str, Any]] = response.get("items", [])
            events.extend(batch)

            page_token = response.get("nextPageToken")
            next_sync_token = response.get("nextSyncToken")

            if not page_token:
                break

        return events, next_sync_token

    def get_event(self, calendar_id: str, event_id: str) -> dict[str, Any]:
        """Fetch a single event by ID.

        Args:
            calendar_id: The calendar ID containing the event.
            event_id: The event ID to fetch.

        Returns:
            The full event dict from the Calendar API.
        """
        request = self._service.events().get(calendarId=calendar_id, eventId=event_id)
        result: dict[str, Any] = self._execute(request)
        return result

    def insert_event(self, calendar_id: str, event_body: dict[str, Any]) -> dict[str, Any]:
        """Create a new event.

        Args:
            calendar_id: The calendar ID to insert the event into.
            event_body: The event resource dict (summary, start, end, etc.).

        Returns:
            The created event dict, including the assigned 'id'.
        """
        request = self._service.events().insert(calendarId=calendar_id, body=event_body)
        result: dict[str, Any] = self._execute(request)
        return result

    def patch_event(self, calendar_id: str, event_id: str, event_body: dict[str, Any]) -> dict[str, Any]:
        """Partially update an event.

        Only the fields present in event_body are updated; omitted fields
        retain their existing values (PATCH semantics, not PUT).

        Args:
            calendar_id: The calendar ID containing the event.
            event_id: The event ID to update.
            event_body: A partial event resource dict with fields to update.

        Returns:
            The updated event dict.
        """
        request = self._service.events().patch(calendarId=calendar_id, eventId=event_id, body=event_body)
        result: dict[str, Any] = self._execute(request)
        return result

    def delete_event(self, calendar_id: str, event_id: str) -> None:
        """Delete an event.

        Args:
            calendar_id: The calendar ID containing the event.
            event_id: The event ID to delete.
        """
        request = self._service.events().delete(calendarId=calendar_id, eventId=event_id)
        self._execute(request)
