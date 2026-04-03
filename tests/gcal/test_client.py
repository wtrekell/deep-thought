"""Tests for the GCal Tool API client wrapper."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Retry logic
# ---------------------------------------------------------------------------


class TestRetryWithBackoff:
    """Tests for the _retry_with_backoff helper."""

    def test_returns_on_success(self) -> None:
        """Should return the function's result on first attempt."""
        from deep_thought.gcal.client import _retry_with_backoff

        func = MagicMock(return_value="success")
        assert _retry_with_backoff(func, max_attempts=3) == "success"
        func.assert_called_once()

    def test_retries_on_429(self) -> None:
        """Should retry on HTTP 429 and succeed on the next attempt."""
        from deep_thought.gcal.client import _retry_with_backoff

        mock_resp = MagicMock()
        mock_resp.status = 429

        from googleapiclient.errors import HttpError

        error = HttpError(resp=mock_resp, content=b"Rate limited")
        func = MagicMock(side_effect=[error, "success"])

        with patch("deep_thought.gcal.client.time.sleep"):
            result = _retry_with_backoff(func, max_attempts=3, base_delay=0.01)

        assert result == "success"
        assert func.call_count == 2

    def test_retries_on_500(self) -> None:
        """Should retry on HTTP 500 server error."""
        from deep_thought.gcal.client import _retry_with_backoff

        mock_resp = MagicMock()
        mock_resp.status = 500

        from googleapiclient.errors import HttpError

        error = HttpError(resp=mock_resp, content=b"Server error")
        func = MagicMock(side_effect=[error, "recovered"])

        with patch("deep_thought.gcal.client.time.sleep"):
            result = _retry_with_backoff(func, max_attempts=3, base_delay=0.01)

        assert result == "recovered"

    def test_retries_on_503(self) -> None:
        """Should retry on HTTP 503 service unavailable error."""
        from deep_thought.gcal.client import _retry_with_backoff

        mock_resp = MagicMock()
        mock_resp.status = 503

        from googleapiclient.errors import HttpError

        error = HttpError(resp=mock_resp, content=b"Service unavailable")
        func = MagicMock(side_effect=[error, "recovered"])

        with patch("deep_thought.gcal.client.time.sleep"):
            result = _retry_with_backoff(func, max_attempts=3, base_delay=0.01)

        assert result == "recovered"

    def test_raises_on_permanent_4xx(self) -> None:
        """Should NOT retry on permanent 4xx errors (other than 429)."""
        from deep_thought.gcal.client import _retry_with_backoff

        mock_resp = MagicMock()
        mock_resp.status = 404

        from googleapiclient.errors import HttpError

        error = HttpError(resp=mock_resp, content=b"Not found")
        func = MagicMock(side_effect=error)

        with pytest.raises(HttpError):
            _retry_with_backoff(func, max_attempts=3)

        func.assert_called_once()

    @pytest.mark.error_handling
    def test_raises_after_max_attempts(self) -> None:
        """Should raise the last error after exhausting all attempts."""
        from deep_thought.gcal.client import _retry_with_backoff

        mock_resp = MagicMock()
        mock_resp.status = 503

        from googleapiclient.errors import HttpError

        error = HttpError(resp=mock_resp, content=b"Unavailable")
        func = MagicMock(side_effect=error)

        with patch("deep_thought.gcal.client.time.sleep"), pytest.raises(HttpError):
            _retry_with_backoff(func, max_attempts=2, base_delay=0.01)

        assert func.call_count == 2


# ---------------------------------------------------------------------------
# GcalClient.authenticate
# ---------------------------------------------------------------------------


class TestGcalClientAuthenticate:
    """Tests for GcalClient.authenticate."""

    def _make_client(self) -> object:
        """Return a GcalClient instance bypassing __init__."""
        from deep_thought.gcal.client import GcalClient

        client = GcalClient.__new__(GcalClient)
        client._credentials_path = "/fake/credentials.json"
        client._token_path = "/fake/token.json"
        client._scopes = ["https://www.googleapis.com/auth/calendar"]
        client._rate_limit_rpm = 0
        client._retry_max_attempts = 1
        client._retry_base_delay = 0.0
        client._last_request_time = 0.0
        client._service = None
        return client

    def test_loads_existing_valid_token(self) -> None:
        """Should use an existing valid token without opening a browser."""
        from deep_thought.gcal.client import GcalClient

        client = self._make_client()
        assert isinstance(client, GcalClient)

        mock_credentials = MagicMock()
        mock_credentials.valid = True

        with (
            patch("deep_thought.gcal.client.Path.exists", return_value=True),
            patch("deep_thought.gcal.client.Credentials.from_authorized_user_file", return_value=mock_credentials),
            patch("deep_thought.gcal.client.build") as mock_build,
        ):
            client.authenticate()

        mock_build.assert_called_once_with("calendar", "v3", credentials=mock_credentials)
        assert client._service is mock_build.return_value

    def test_refreshes_expired_token(self) -> None:
        """Should silently refresh an expired token that has a refresh_token."""
        from deep_thought.gcal.client import GcalClient

        client = self._make_client()
        assert isinstance(client, GcalClient)

        mock_credentials = MagicMock()
        mock_credentials.valid = False
        mock_credentials.expired = True
        mock_credentials.refresh_token = "refresh_abc"

        with (
            patch("deep_thought.gcal.client.Path.exists", return_value=True),
            patch("deep_thought.gcal.client.Credentials.from_authorized_user_file", return_value=mock_credentials),
            patch("deep_thought.gcal.client.Request") as mock_request_cls,
            patch("deep_thought.gcal.client.Path.write_text"),
            patch("deep_thought.gcal.client.Path.chmod"),
            patch("deep_thought.gcal.client.Path.mkdir"),
            patch("deep_thought.gcal.client.build"),
        ):
            client.authenticate()

        mock_credentials.refresh.assert_called_once_with(mock_request_cls.return_value)

    def test_runs_browser_flow_when_no_token_file(self) -> None:
        """Should open a browser flow when no token file exists."""
        from deep_thought.gcal.client import GcalClient

        client = self._make_client()
        assert isinstance(client, GcalClient)

        mock_flow_credentials = MagicMock()
        mock_flow = MagicMock()
        mock_flow.run_local_server.return_value = mock_flow_credentials

        def path_exists_side_effect(self_path: object) -> bool:
            # Token path does not exist; credentials file does
            path_str = str(self_path)
            return "token" not in path_str

        with (
            patch("deep_thought.gcal.client.Path.exists", path_exists_side_effect),
            patch("deep_thought.gcal.client.InstalledAppFlow.from_client_secrets_file", return_value=mock_flow),
            patch("deep_thought.gcal.client.Path.write_text"),
            patch("deep_thought.gcal.client.Path.chmod"),
            patch("deep_thought.gcal.client.Path.mkdir"),
            patch("deep_thought.gcal.client.build"),
        ):
            client.authenticate()

        mock_flow.run_local_server.assert_called_once_with(port=0)

    def test_raises_when_credentials_file_missing(self) -> None:
        """Should raise FileNotFoundError when credentials.json does not exist."""
        from deep_thought.gcal.client import GcalClient

        client = self._make_client()
        assert isinstance(client, GcalClient)

        with (
            patch("deep_thought.gcal.client.Path.exists", return_value=False),
            pytest.raises(FileNotFoundError, match="OAuth client secret not found"),
        ):
            client.authenticate()

    def test_saves_token_with_restricted_permissions(self) -> None:
        """Should write the token file and chmod it to 0o600."""
        from deep_thought.gcal.client import GcalClient

        client = self._make_client()
        assert isinstance(client, GcalClient)

        mock_credentials = MagicMock()
        mock_credentials.valid = False
        mock_credentials.expired = True
        mock_credentials.refresh_token = "refresh_xyz"
        mock_credentials.to_json.return_value = '{"token": "abc"}'

        with (
            patch("deep_thought.gcal.client.Path.exists", return_value=True),
            patch("deep_thought.gcal.client.Credentials.from_authorized_user_file", return_value=mock_credentials),
            patch("deep_thought.gcal.client.Request"),
            patch("deep_thought.gcal.client.Path.mkdir"),
            patch("deep_thought.gcal.client.Path.write_text") as mock_write,
            patch("deep_thought.gcal.client.Path.chmod") as mock_chmod,
            patch("deep_thought.gcal.client.build"),
        ):
            client.authenticate()

        mock_write.assert_called_once_with('{"token": "abc"}')
        mock_chmod.assert_called_once_with(0o600)


# ---------------------------------------------------------------------------
# GcalClient.list_calendars
# ---------------------------------------------------------------------------


class TestGcalClientListCalendars:
    """Tests for GcalClient.list_calendars."""

    def _make_client(self) -> object:
        """Return a GcalClient with a mocked service."""
        from deep_thought.gcal.client import GcalClient

        client = GcalClient.__new__(GcalClient)
        client._rate_limit_rpm = 0
        client._retry_max_attempts = 1
        client._retry_base_delay = 0.0
        client._last_request_time = 0.0
        return client

    def test_returns_flat_list(self) -> None:
        """Should return all calendar entries as a flat list."""
        from deep_thought.gcal.client import GcalClient

        client = self._make_client()
        assert isinstance(client, GcalClient)

        mock_service = MagicMock()
        mock_list_request = MagicMock()
        mock_list_request.execute.return_value = {
            "items": [{"id": "primary", "summary": "My Calendar"}, {"id": "cal2", "summary": "Work"}]
        }
        mock_service.calendarList().list.return_value = mock_list_request
        client._service = mock_service

        result = client.list_calendars()

        assert len(result) == 2
        assert result[0]["id"] == "primary"
        assert result[1]["id"] == "cal2"

    def test_handles_pagination(self) -> None:
        """Should follow nextPageToken until all calendars are fetched."""
        from deep_thought.gcal.client import GcalClient

        client = self._make_client()
        assert isinstance(client, GcalClient)

        page1 = {"items": [{"id": "cal1", "summary": "Calendar 1"}], "nextPageToken": "token_page2"}
        page2 = {"items": [{"id": "cal2", "summary": "Calendar 2"}]}

        mock_service = MagicMock()
        mock_list_request = MagicMock()
        mock_list_request.execute.side_effect = [page1, page2]
        mock_service.calendarList().list.return_value = mock_list_request
        client._service = mock_service

        result = client.list_calendars()

        assert len(result) == 2
        assert result[0]["id"] == "cal1"
        assert result[1]["id"] == "cal2"


# ---------------------------------------------------------------------------
# GcalClient.list_events
# ---------------------------------------------------------------------------


class TestGcalClientListEvents:
    """Tests for GcalClient.list_events."""

    def _make_client(self) -> object:
        """Return a GcalClient with a mocked service."""
        from deep_thought.gcal.client import GcalClient

        client = GcalClient.__new__(GcalClient)
        client._rate_limit_rpm = 0
        client._retry_max_attempts = 1
        client._retry_base_delay = 0.0
        client._last_request_time = 0.0
        return client

    def test_time_windowed_pull_includes_time_params(self) -> None:
        """Should pass timeMin and timeMax when no sync_token is given."""
        from deep_thought.gcal.client import GcalClient

        client = self._make_client()
        assert isinstance(client, GcalClient)

        mock_service = MagicMock()
        mock_list_request = MagicMock()
        mock_list_request.execute.return_value = {
            "items": [{"id": "evt1"}],
            "nextSyncToken": "sync_abc",
        }
        mock_service.events().list.return_value = mock_list_request
        client._service = mock_service

        events, sync_token = client.list_events(
            calendar_id="primary",
            time_min="2026-01-01T00:00:00Z",
            time_max="2026-02-01T00:00:00Z",
        )

        assert len(events) == 1
        assert sync_token == "sync_abc"
        call_kwargs = mock_service.events().list.call_args[1]
        assert call_kwargs["timeMin"] == "2026-01-01T00:00:00Z"
        assert call_kwargs["timeMax"] == "2026-02-01T00:00:00Z"
        assert "syncToken" not in call_kwargs

    def test_sync_token_pull_omits_time_params(self) -> None:
        """Should omit timeMin, timeMax, and singleEvents when sync_token is set."""
        from deep_thought.gcal.client import GcalClient

        client = self._make_client()
        assert isinstance(client, GcalClient)

        mock_service = MagicMock()
        mock_list_request = MagicMock()
        mock_list_request.execute.return_value = {
            "items": [{"id": "evt2"}],
            "nextSyncToken": "sync_def",
        }
        mock_service.events().list.return_value = mock_list_request
        client._service = mock_service

        events, sync_token = client.list_events(
            calendar_id="primary",
            time_min="2026-01-01T00:00:00Z",
            time_max="2026-02-01T00:00:00Z",
            sync_token="sync_previous",
        )

        assert len(events) == 1
        assert sync_token == "sync_def"
        call_kwargs = mock_service.events().list.call_args[1]
        assert call_kwargs["syncToken"] == "sync_previous"
        assert "timeMin" not in call_kwargs
        assert "timeMax" not in call_kwargs
        assert "singleEvents" not in call_kwargs

    def test_handles_pagination(self) -> None:
        """Should follow nextPageToken until all events are fetched."""
        from deep_thought.gcal.client import GcalClient

        client = self._make_client()
        assert isinstance(client, GcalClient)

        page1 = {"items": [{"id": "evt1"}], "nextPageToken": "page_token_2"}
        page2 = {"items": [{"id": "evt2"}, {"id": "evt3"}], "nextSyncToken": "sync_final"}

        mock_service = MagicMock()
        mock_list_request = MagicMock()
        mock_list_request.execute.side_effect = [page1, page2]
        mock_service.events().list.return_value = mock_list_request
        client._service = mock_service

        events, sync_token = client.list_events(calendar_id="primary")

        assert len(events) == 3
        assert sync_token == "sync_final"

    def test_returns_none_sync_token_when_absent(self) -> None:
        """Should return None for next_sync_token when the API does not include it."""
        from deep_thought.gcal.client import GcalClient

        client = self._make_client()
        assert isinstance(client, GcalClient)

        mock_service = MagicMock()
        mock_list_request = MagicMock()
        mock_list_request.execute.return_value = {"items": []}
        mock_service.events().list.return_value = mock_list_request
        client._service = mock_service

        events, sync_token = client.list_events(calendar_id="primary")

        assert events == []
        assert sync_token is None


# ---------------------------------------------------------------------------
# GcalClient.get_event
# ---------------------------------------------------------------------------


class TestGcalClientGetEvent:
    """Tests for GcalClient.get_event."""

    def test_passes_correct_params(self) -> None:
        """Should call events().get with the correct calendarId and eventId."""
        from deep_thought.gcal.client import GcalClient

        client = GcalClient.__new__(GcalClient)
        client._rate_limit_rpm = 0
        client._retry_max_attempts = 1
        client._retry_base_delay = 0.0
        client._last_request_time = 0.0

        expected_event = {"id": "evt_001", "summary": "Team Standup"}
        mock_service = MagicMock()
        mock_get_request = MagicMock()
        mock_get_request.execute.return_value = expected_event
        mock_service.events().get.return_value = mock_get_request
        client._service = mock_service

        result = client.get_event(calendar_id="primary", event_id="evt_001")

        assert result == expected_event
        mock_service.events().get.assert_called_with(calendarId="primary", eventId="evt_001")


# ---------------------------------------------------------------------------
# GcalClient.insert_event
# ---------------------------------------------------------------------------


class TestGcalClientInsertEvent:
    """Tests for GcalClient.insert_event."""

    def test_returns_created_event_with_id(self) -> None:
        """Should return the created event dict, including the server-assigned id."""
        from deep_thought.gcal.client import GcalClient

        client = GcalClient.__new__(GcalClient)
        client._rate_limit_rpm = 0
        client._retry_max_attempts = 1
        client._retry_base_delay = 0.0
        client._last_request_time = 0.0

        event_body = {"summary": "New Meeting", "start": {"dateTime": "2026-03-23T10:00:00Z"}}
        created_event = {"id": "evt_new_001", "summary": "New Meeting"}

        mock_service = MagicMock()
        mock_insert_request = MagicMock()
        mock_insert_request.execute.return_value = created_event
        mock_service.events().insert.return_value = mock_insert_request
        client._service = mock_service

        result = client.insert_event(calendar_id="primary", event_body=event_body)

        assert result["id"] == "evt_new_001"
        mock_service.events().insert.assert_called_with(calendarId="primary", body=event_body)


# ---------------------------------------------------------------------------
# GcalClient.patch_event
# ---------------------------------------------------------------------------


class TestGcalClientPatchEvent:
    """Tests for GcalClient.patch_event."""

    def test_returns_updated_event(self) -> None:
        """Should return the updated event dict after a partial update."""
        from deep_thought.gcal.client import GcalClient

        client = GcalClient.__new__(GcalClient)
        client._rate_limit_rpm = 0
        client._retry_max_attempts = 1
        client._retry_base_delay = 0.0
        client._last_request_time = 0.0

        patch_body = {"summary": "Updated Meeting Title"}
        updated_event = {"id": "evt_001", "summary": "Updated Meeting Title"}

        mock_service = MagicMock()
        mock_patch_request = MagicMock()
        mock_patch_request.execute.return_value = updated_event
        mock_service.events().patch.return_value = mock_patch_request
        client._service = mock_service

        result = client.patch_event(calendar_id="primary", event_id="evt_001", event_body=patch_body)

        assert result["summary"] == "Updated Meeting Title"
        mock_service.events().patch.assert_called_with(calendarId="primary", eventId="evt_001", body=patch_body)


# ---------------------------------------------------------------------------
# GcalClient.delete_event
# ---------------------------------------------------------------------------


class TestGcalClientDeleteEvent:
    """Tests for GcalClient.delete_event."""

    def test_calls_delete_with_correct_params(self) -> None:
        """Should call events().delete with the correct calendarId and eventId."""
        from deep_thought.gcal.client import GcalClient

        client = GcalClient.__new__(GcalClient)
        client._rate_limit_rpm = 0
        client._retry_max_attempts = 1
        client._retry_base_delay = 0.0
        client._last_request_time = 0.0

        mock_service = MagicMock()
        mock_delete_request = MagicMock()
        mock_delete_request.execute.return_value = None
        mock_service.events().delete.return_value = mock_delete_request
        client._service = mock_service

        client.delete_event(calendar_id="primary", event_id="evt_001")

        mock_service.events().delete.assert_called_with(calendarId="primary", eventId="evt_001")


# ---------------------------------------------------------------------------
# GcalClient._execute — service-initialized guard (L2)
# ---------------------------------------------------------------------------


class TestGcalClientExecuteGuard:
    """Tests for the service-initialized check in _execute."""

    def test_raises_runtime_error_when_service_is_none(self) -> None:
        """Should raise RuntimeError if authenticate() has not been called."""
        from deep_thought.gcal.client import GcalClient

        client = GcalClient.__new__(GcalClient)
        client._rate_limit_rpm = 0
        client._retry_max_attempts = 1
        client._retry_base_delay = 0.0
        client._last_request_time = 0.0
        client._service = None

        mock_request = MagicMock()
        with pytest.raises(RuntimeError, match="authenticate"):
            client._execute(mock_request)


# ---------------------------------------------------------------------------
# GcalClient.list_events — partial pagination results (M5)
# ---------------------------------------------------------------------------


class TestGcalClientListEventsPartialPagination:
    """Tests for partial-results behaviour on pagination errors."""

    def test_returns_partial_results_on_page_two_error(self) -> None:
        """Should return events from page 1 when page 2+ raises an error."""
        from googleapiclient.errors import HttpError

        from deep_thought.gcal.client import GcalClient

        client = GcalClient.__new__(GcalClient)
        client._rate_limit_rpm = 0
        client._retry_max_attempts = 1
        client._retry_base_delay = 0.0
        client._last_request_time = 0.0

        page1 = {"items": [{"id": "evt_page1"}], "nextPageToken": "token_p2"}
        mock_resp = MagicMock()
        mock_resp.status = 500
        page2_error = HttpError(resp=mock_resp, content=b"Server error")

        mock_service = MagicMock()
        mock_list_request = MagicMock()
        mock_list_request.execute.side_effect = [page1, page2_error]
        mock_service.events().list.return_value = mock_list_request
        client._service = mock_service

        events, sync_token = client.list_events(calendar_id="primary")

        # Should return the one event from page 1, not raise
        assert len(events) == 1
        assert events[0]["id"] == "evt_page1"
        assert sync_token is None

    def test_raises_on_first_page_error(self) -> None:
        """Should propagate the error when the first page fails."""
        from googleapiclient.errors import HttpError

        from deep_thought.gcal.client import GcalClient

        client = GcalClient.__new__(GcalClient)
        client._rate_limit_rpm = 0
        client._retry_max_attempts = 1
        client._retry_base_delay = 0.0
        client._last_request_time = 0.0

        mock_resp = MagicMock()
        mock_resp.status = 403
        first_page_error = HttpError(resp=mock_resp, content=b"Forbidden")

        mock_service = MagicMock()
        mock_list_request = MagicMock()
        mock_list_request.execute.side_effect = first_page_error
        mock_service.events().list.return_value = mock_list_request
        client._service = mock_service

        with pytest.raises(HttpError):
            client.list_events(calendar_id="primary")


# ---------------------------------------------------------------------------
# _retry_with_backoff — final failure log (L4)
# ---------------------------------------------------------------------------


class TestRetryFinalFailureLog:
    """Tests for the final-failure log message in _retry_with_backoff."""

    def test_logs_error_after_all_attempts_exhausted(self) -> None:
        """Should call logger.error once when all retry attempts fail."""

        from googleapiclient.errors import HttpError

        from deep_thought.gcal.client import _retry_with_backoff

        mock_resp = MagicMock()
        mock_resp.status = 503
        error = HttpError(resp=mock_resp, content=b"Unavailable")
        func = MagicMock(side_effect=error)

        with (
            patch("deep_thought.gcal.client.time.sleep"),
            patch("deep_thought.gcal.client.logger") as mock_logger,
            pytest.raises(HttpError),
        ):
            _retry_with_backoff(func, max_attempts=2, base_delay=0.01)

        mock_logger.error.assert_called_once()
        error_call_args = mock_logger.error.call_args[0]
        assert "attempt" in error_call_args[0].lower() or "fail" in error_call_args[0].lower()
