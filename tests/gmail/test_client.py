"""Tests for the Gmail Tool API client wrapper."""

from __future__ import annotations

import base64
import time
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

if TYPE_CHECKING:
    from pathlib import Path

# ---------------------------------------------------------------------------
# Retry logic
# ---------------------------------------------------------------------------


class TestRetryWithBackoff:
    """Tests for the _retry_with_backoff helper."""

    def test_returns_on_success(self) -> None:
        """Should return the function's result on first attempt."""
        from deep_thought.gmail.client import _retry_with_backoff

        func = MagicMock(return_value="success")
        assert _retry_with_backoff(func, max_attempts=3) == "success"
        func.assert_called_once()

    def test_retries_on_429(self) -> None:
        """Should retry on HTTP 429 and succeed on the next attempt."""
        from deep_thought.gmail.client import _retry_with_backoff

        mock_resp = MagicMock()
        mock_resp.status = 429

        from googleapiclient.errors import HttpError

        error = HttpError(resp=mock_resp, content=b"Rate limited")
        func = MagicMock(side_effect=[error, "success"])

        with patch("deep_thought.gmail.client.time.sleep"):
            result = _retry_with_backoff(func, max_attempts=3, base_delay=0.01)

        assert result == "success"
        assert func.call_count == 2

    def test_retries_on_500(self) -> None:
        """Should retry on HTTP 500 server error."""
        from deep_thought.gmail.client import _retry_with_backoff

        mock_resp = MagicMock()
        mock_resp.status = 500

        from googleapiclient.errors import HttpError

        error = HttpError(resp=mock_resp, content=b"Server error")
        func = MagicMock(side_effect=[error, "recovered"])

        with patch("deep_thought.gmail.client.time.sleep"):
            result = _retry_with_backoff(func, max_attempts=3, base_delay=0.01)

        assert result == "recovered"

    def test_raises_on_permanent_4xx(self) -> None:
        """Should NOT retry on permanent 4xx errors (other than 429)."""
        from deep_thought.gmail.client import _retry_with_backoff

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
        from deep_thought.gmail.client import _retry_with_backoff

        mock_resp = MagicMock()
        mock_resp.status = 503

        from googleapiclient.errors import HttpError

        error = HttpError(resp=mock_resp, content=b"Unavailable")
        func = MagicMock(side_effect=error)

        with patch("deep_thought.gmail.client.time.sleep"), pytest.raises(HttpError):
            _retry_with_backoff(func, max_attempts=2, base_delay=0.01)

        assert func.call_count == 2


# ---------------------------------------------------------------------------
# GmailClient
# ---------------------------------------------------------------------------


class TestGmailClientListMessages:
    """Tests for GmailClient.list_messages."""

    def test_returns_flat_list(self) -> None:
        """Should collapse pagination into a flat list of message stubs."""
        from deep_thought.gmail.client import GmailClient

        client = GmailClient.__new__(GmailClient)
        client._rate_limit_rpm = 0
        client._retry_max_attempts = 1
        client._retry_base_delay = 0.0
        client._last_request_time = 0.0

        mock_service = MagicMock()
        page1 = {"messages": [{"id": "m1"}, {"id": "m2"}], "nextPageToken": "token_2"}
        page2 = {"messages": [{"id": "m3"}]}
        mock_service.users().messages().list().execute.side_effect = [page1, page2]
        client._service = mock_service

        # Since we need the mock to work across calls with different params
        mock_list = MagicMock()
        mock_list.execute.side_effect = [page1, page2]
        mock_service.users().messages().list.return_value = mock_list

        result = client.list_messages("label:test", max_results=10)
        assert len(result) == 3
        assert result[0]["id"] == "m1"

    def test_respects_max_results(self) -> None:
        """Should stop when max_results is reached."""
        from deep_thought.gmail.client import GmailClient

        client = GmailClient.__new__(GmailClient)
        client._rate_limit_rpm = 0
        client._retry_max_attempts = 1
        client._retry_base_delay = 0.0
        client._last_request_time = 0.0

        mock_service = MagicMock()
        page = {"messages": [{"id": f"m{i}"} for i in range(100)], "nextPageToken": "next"}
        mock_list = MagicMock()
        mock_list.execute.return_value = page
        mock_service.users().messages().list.return_value = mock_list
        client._service = mock_service

        result = client.list_messages("label:test", max_results=5)
        assert len(result) == 5


class TestGmailClientGetMessage:
    """Tests for GmailClient.get_message."""

    def test_calls_api_with_correct_params(self) -> None:
        """Should call the messages.get endpoint with the right ID and format."""
        from deep_thought.gmail.client import GmailClient

        client = GmailClient.__new__(GmailClient)
        client._rate_limit_rpm = 0
        client._retry_max_attempts = 1
        client._retry_base_delay = 0.0
        client._last_request_time = 0.0

        mock_service = MagicMock()
        expected_response = {"id": "msg_001", "payload": {"headers": []}}
        mock_service.users().messages().get().execute.return_value = expected_response
        mock_get = MagicMock()
        mock_get.execute.return_value = expected_response
        mock_service.users().messages().get.return_value = mock_get
        client._service = mock_service

        result = client.get_message("msg_001", format_type="full")
        assert result["id"] == "msg_001"
        mock_service.users().messages().get.assert_called_with(userId="me", id="msg_001", format="full")


class TestGmailClientGetRawMessage:
    """Tests for GmailClient.get_raw_message."""

    def test_decodes_base64url(self) -> None:
        """Should decode the raw base64url-encoded message content."""
        from deep_thought.gmail.client import GmailClient

        client = GmailClient.__new__(GmailClient)
        client._rate_limit_rpm = 0
        client._retry_max_attempts = 1
        client._retry_base_delay = 0.0
        client._last_request_time = 0.0

        raw_content = b"From: sender@example.com\r\nSubject: Test\r\n\r\nBody"
        encoded_content = base64.urlsafe_b64encode(raw_content).decode()

        mock_service = MagicMock()
        mock_get = MagicMock()
        mock_get.execute.return_value = {"id": "msg_001", "raw": encoded_content}
        mock_service.users().messages().get.return_value = mock_get
        client._service = mock_service

        result = client.get_raw_message("msg_001")
        assert result == raw_content


class TestGmailClientSendMessage:
    """Tests for GmailClient.send_message."""

    def test_encodes_and_sends(self) -> None:
        """Should base64url-encode the raw message and call send."""
        from deep_thought.gmail.client import GmailClient

        client = GmailClient.__new__(GmailClient)
        client._rate_limit_rpm = 0
        client._retry_max_attempts = 1
        client._retry_base_delay = 0.0
        client._last_request_time = 0.0

        mock_service = MagicMock()
        mock_send = MagicMock()
        mock_send.execute.return_value = {"id": "sent_001", "threadId": "thread_001"}
        mock_service.users().messages().send.return_value = mock_send
        client._service = mock_service

        raw_message = b"From: me@example.com\r\nTo: you@example.com\r\n\r\nHi"
        result = client.send_message(raw_message)

        assert result["id"] == "sent_001"
        call_args = mock_service.users().messages().send.call_args
        assert call_args[1]["userId"] == "me"
        assert "raw" in call_args[1]["body"]


class TestGmailClientModifyMessage:
    """Tests for GmailClient.modify_message."""

    def test_adds_labels(self) -> None:
        """Should call modify with addLabelIds."""
        from deep_thought.gmail.client import GmailClient

        client = GmailClient.__new__(GmailClient)
        client._rate_limit_rpm = 0
        client._retry_max_attempts = 1
        client._retry_base_delay = 0.0
        client._last_request_time = 0.0

        mock_service = MagicMock()
        mock_modify = MagicMock()
        mock_modify.execute.return_value = {"id": "msg_001"}
        mock_service.users().messages().modify.return_value = mock_modify
        client._service = mock_service

        client.modify_message("msg_001", add_labels=["Label_1"])
        call_args = mock_service.users().messages().modify.call_args
        assert call_args[1]["body"]["addLabelIds"] == ["Label_1"]

    def test_removes_labels(self) -> None:
        """Should call modify with removeLabelIds."""
        from deep_thought.gmail.client import GmailClient

        client = GmailClient.__new__(GmailClient)
        client._rate_limit_rpm = 0
        client._retry_max_attempts = 1
        client._retry_base_delay = 0.0
        client._last_request_time = 0.0

        mock_service = MagicMock()
        mock_modify = MagicMock()
        mock_modify.execute.return_value = {"id": "msg_001"}
        mock_service.users().messages().modify.return_value = mock_modify
        client._service = mock_service

        client.modify_message("msg_001", remove_labels=["INBOX"])
        call_args = mock_service.users().messages().modify.call_args
        assert call_args[1]["body"]["removeLabelIds"] == ["INBOX"]


class TestGmailClientLabelCache:
    """Tests for GmailClient.get_or_create_label."""

    def test_returns_cached_label(self) -> None:
        """Should return from cache without hitting the API."""
        import time

        from deep_thought.gmail.client import GmailClient

        client = GmailClient.__new__(GmailClient)
        client._label_cache = {"Processed": "Label_123"}
        # Set populated_at to now so the cache is considered fresh (not expired)
        client._label_cache_populated_at = time.time()
        client._rate_limit_rpm = 0
        client._retry_max_attempts = 1
        client._retry_base_delay = 0.0
        client._last_request_time = 0.0
        client._service = MagicMock()

        result = client.get_or_create_label("Processed")
        assert result == "Label_123"
        # Should not have called the API
        client._service.users().labels().list.assert_not_called()

    def test_finds_existing_label(self) -> None:
        """Should find an existing label via the API and cache it."""
        from deep_thought.gmail.client import GmailClient

        client = GmailClient.__new__(GmailClient)
        client._label_cache = {}
        client._label_cache_populated_at = 0.0
        client._rate_limit_rpm = 0
        client._retry_max_attempts = 1
        client._retry_base_delay = 0.0
        client._last_request_time = 0.0

        mock_service = MagicMock()
        mock_list = MagicMock()
        mock_list.execute.return_value = {"labels": [{"name": "Processed", "id": "Label_456"}]}
        mock_service.users().labels().list.return_value = mock_list
        client._service = mock_service

        result = client.get_or_create_label("Processed")
        assert result == "Label_456"
        assert client._label_cache["Processed"] == "Label_456"

    def test_creates_missing_label(self) -> None:
        """Should create a label when it does not exist and cache it."""
        from deep_thought.gmail.client import GmailClient

        client = GmailClient.__new__(GmailClient)
        client._label_cache = {}
        client._label_cache_populated_at = 0.0
        client._rate_limit_rpm = 0
        client._retry_max_attempts = 1
        client._retry_base_delay = 0.0
        client._last_request_time = 0.0

        mock_service = MagicMock()
        mock_list = MagicMock()
        mock_list.execute.return_value = {"labels": []}
        mock_service.users().labels().list.return_value = mock_list

        mock_create = MagicMock()
        mock_create.execute.return_value = {"id": "Label_789", "name": "NewLabel"}
        mock_service.users().labels().create.return_value = mock_create
        client._service = mock_service

        result = client.get_or_create_label("NewLabel")
        assert result == "Label_789"
        assert client._label_cache["NewLabel"] == "Label_789"


# ---------------------------------------------------------------------------
# Retry-After header (M6)
# ---------------------------------------------------------------------------


class TestRetryAfterHeader:
    """Tests that _retry_with_backoff respects the Retry-After response header."""

    def test_uses_retry_after_when_longer_than_backoff(self) -> None:
        """Should sleep for Retry-After value when it exceeds the exponential backoff delay."""
        from deep_thought.gmail.client import _retry_with_backoff

        mock_resp = MagicMock()
        mock_resp.status = 429
        mock_resp.get.side_effect = lambda key, default="": "10" if key == "retry-after" else default

        from googleapiclient.errors import HttpError

        error = HttpError(resp=mock_resp, content=b"Rate limited")
        func = MagicMock(side_effect=[error, "success"])

        with patch("deep_thought.gmail.client.time.sleep") as mock_sleep:
            result = _retry_with_backoff(func, max_attempts=3, base_delay=1.0)

        assert result == "success"
        # The Retry-After value (10s) is larger than base_delay (1s), so sleep should be 10s
        mock_sleep.assert_called_once_with(10.0)

    def test_uses_backoff_when_longer_than_retry_after(self) -> None:
        """Should sleep for the exponential backoff when it exceeds Retry-After."""
        from deep_thought.gmail.client import _retry_with_backoff

        mock_resp = MagicMock()
        mock_resp.status = 429
        # Retry-After of 0.1s — much shorter than base_delay=5s
        mock_resp.get.side_effect = lambda key, default="": "0.1" if key == "retry-after" else default

        from googleapiclient.errors import HttpError

        error = HttpError(resp=mock_resp, content=b"Rate limited")
        func = MagicMock(side_effect=[error, "success"])

        with patch("deep_thought.gmail.client.time.sleep") as mock_sleep:
            result = _retry_with_backoff(func, max_attempts=3, base_delay=5.0)

        assert result == "success"
        # max(0.1, 5.0) → should sleep for 5.0s
        mock_sleep.assert_called_once_with(5.0)

    def test_ignores_non_numeric_retry_after(self) -> None:
        """Should fall back to exponential backoff when Retry-After is not a number."""
        from deep_thought.gmail.client import _retry_with_backoff

        mock_resp = MagicMock()
        mock_resp.status = 429
        mock_resp.get.side_effect = lambda key, default="": "not-a-number" if key == "retry-after" else default

        from googleapiclient.errors import HttpError

        error = HttpError(resp=mock_resp, content=b"Rate limited")
        func = MagicMock(side_effect=[error, "success"])

        with patch("deep_thought.gmail.client.time.sleep") as mock_sleep:
            result = _retry_with_backoff(func, max_attempts=3, base_delay=2.0)

        assert result == "success"
        mock_sleep.assert_called_once_with(2.0)


# ---------------------------------------------------------------------------
# Label cache TTL (M3)
# ---------------------------------------------------------------------------


class TestLabelCacheTTL:
    """Tests that the label cache expires after _LABEL_CACHE_TTL_SECONDS."""

    def test_cache_is_used_when_fresh(self) -> None:
        """Should serve from cache without calling the API when cache is not expired."""
        from deep_thought.gmail.client import GmailClient

        client = GmailClient.__new__(GmailClient)
        client._label_cache = {"MyLabel": "Label_fresh"}
        client._label_cache_populated_at = time.time()  # Populated just now — fresh
        client._rate_limit_rpm = 0
        client._retry_max_attempts = 1
        client._retry_base_delay = 0.0
        client._last_request_time = 0.0
        client._service = MagicMock()

        result = client.get_or_create_label("MyLabel")

        assert result == "Label_fresh"
        client._service.users().labels().list.assert_not_called()

    def test_cache_is_invalidated_after_ttl(self) -> None:
        """Should discard the cache and re-fetch from the API after the TTL elapses."""
        from deep_thought.gmail.client import _LABEL_CACHE_TTL_SECONDS, GmailClient

        client = GmailClient.__new__(GmailClient)
        # Simulate a cache that was populated longer ago than the TTL
        client._label_cache = {"StaleLabel": "Label_stale"}
        client._label_cache_populated_at = time.time() - _LABEL_CACHE_TTL_SECONDS - 1.0
        client._rate_limit_rpm = 0
        client._retry_max_attempts = 1
        client._retry_base_delay = 0.0
        client._last_request_time = 0.0

        mock_service = MagicMock()
        mock_list = MagicMock()
        mock_list.execute.return_value = {"labels": [{"name": "StaleLabel", "id": "Label_fresh_id"}]}
        mock_service.users().labels().list.return_value = mock_list
        client._service = mock_service

        result = client.get_or_create_label("StaleLabel")

        assert result == "Label_fresh_id"
        # The API must have been called because the cache was invalidated
        mock_service.users().labels().list.assert_called_once()


# ---------------------------------------------------------------------------
# Rate limiting (M9)
# ---------------------------------------------------------------------------


class TestGmailClientRateLimit:
    """Tests for GmailClient._rate_limit."""

    def test_no_sleep_on_first_call(self) -> None:
        """Should not sleep when no prior request has been made."""
        from deep_thought.gmail.client import GmailClient

        client = GmailClient.__new__(GmailClient)
        client._rate_limit_rpm = 60
        client._last_request_time = 0.0  # Never called before

        with (
            patch("deep_thought.gmail.client.time.sleep") as mock_sleep,
            patch("deep_thought.gmail.client.time.time", return_value=1000.0),
        ):
            client._rate_limit()

        mock_sleep.assert_not_called()

    def test_sleeps_when_within_minimum_interval(self) -> None:
        """Should sleep the remaining interval when called too soon after the last request."""
        from deep_thought.gmail.client import GmailClient

        client = GmailClient.__new__(GmailClient)
        client._rate_limit_rpm = 60  # 1 request/s → interval = 1.0s
        client._last_request_time = 999.8  # 0.2s ago

        with (
            patch("deep_thought.gmail.client.time.sleep") as mock_sleep,
            patch("deep_thought.gmail.client.time.time", side_effect=[1000.0, 1000.0]),
        ):
            client._rate_limit()

        # elapsed = 1000.0 - 999.8 = 0.2s; need to sleep 1.0 - 0.2 = 0.8s
        mock_sleep.assert_called_once()
        sleep_duration = mock_sleep.call_args[0][0]
        assert abs(sleep_duration - 0.8) < 0.001

    def test_rate_limit_disabled_when_rpm_is_zero(self) -> None:
        """Should not sleep or check time when rate_limit_rpm is 0 (disabled)."""
        from deep_thought.gmail.client import GmailClient

        client = GmailClient.__new__(GmailClient)
        client._rate_limit_rpm = 0

        with (
            patch("deep_thought.gmail.client.time.sleep") as mock_sleep,
            patch("deep_thought.gmail.client.time.time") as mock_time,
        ):
            client._rate_limit()

        mock_sleep.assert_not_called()
        mock_time.assert_not_called()


class TestGeminiExtractorRateLimit:
    """Tests for GeminiExtractor._rate_limit."""

    def test_no_sleep_on_first_call(self) -> None:
        """Should not sleep when no prior extraction has been made."""
        from deep_thought.gmail.extractor import GeminiExtractor

        extractor = GeminiExtractor.__new__(GeminiExtractor)
        extractor._rate_limit_rpm = 60
        extractor._last_request_time = 0.0

        with (
            patch("deep_thought.gmail.extractor.time.sleep") as mock_sleep,
            patch("deep_thought.gmail.extractor.time.time", return_value=1000.0),
        ):
            extractor._rate_limit()

        mock_sleep.assert_not_called()

    def test_sleeps_when_within_minimum_interval(self) -> None:
        """Should sleep the remaining gap when called too soon after the last extraction."""
        from deep_thought.gmail.extractor import GeminiExtractor

        extractor = GeminiExtractor.__new__(GeminiExtractor)
        extractor._rate_limit_rpm = 60  # 1/s → interval = 1.0s
        extractor._last_request_time = 999.7  # 0.3s ago

        with (
            patch("deep_thought.gmail.extractor.time.sleep") as mock_sleep,
            patch("deep_thought.gmail.extractor.time.time", side_effect=[1000.0, 1000.0]),
        ):
            extractor._rate_limit()

        mock_sleep.assert_called_once()
        sleep_duration = mock_sleep.call_args[0][0]
        assert abs(sleep_duration - 0.7) < 0.001

    def test_rate_limit_disabled_when_rpm_is_zero(self) -> None:
        """Should do nothing when rate_limit_rpm is 0."""
        from deep_thought.gmail.extractor import GeminiExtractor

        extractor = GeminiExtractor.__new__(GeminiExtractor)
        extractor._rate_limit_rpm = 0

        with (
            patch("deep_thought.gmail.extractor.time.sleep") as mock_sleep,
            patch("deep_thought.gmail.extractor.time.time") as mock_time,
        ):
            extractor._rate_limit()

        mock_sleep.assert_not_called()
        mock_time.assert_not_called()


# ---------------------------------------------------------------------------
# authenticate() coverage (M8)
# ---------------------------------------------------------------------------


class TestGmailClientAuthenticate:
    """Tests for GmailClient.authenticate."""

    def test_loads_valid_token_from_file(self, tmp_path: Path) -> None:
        """Should load credentials from an existing token file if valid."""
        from deep_thought.gmail.client import GmailClient

        token_file = tmp_path / "token.json"
        token_file.write_text("{}", encoding="utf-8")  # Must exist so the loading branch runs

        client = GmailClient(
            credentials_path=str(tmp_path / "credentials.json"),
            token_path=str(token_file),
            scopes=["https://mail.google.com/"],
        )

        mock_creds = MagicMock()
        mock_creds.valid = True

        with (
            patch("deep_thought.gmail.client.Credentials.from_authorized_user_file", return_value=mock_creds),
            patch("deep_thought.gmail.client.build") as mock_build,
        ):
            client.authenticate()

        mock_build.assert_called_once_with("gmail", "v1", credentials=mock_creds)

    def test_refreshes_expired_token(self, tmp_path: MagicMock) -> None:
        """Should call credentials.refresh() when the token is expired but has a refresh token."""
        from deep_thought.gmail.client import GmailClient

        token_file = tmp_path / "token.json"
        token_file.write_text("{}", encoding="utf-8")  # Must exist for the token-loading branch

        client = GmailClient(
            credentials_path=str(tmp_path / "credentials.json"),
            token_path=str(token_file),
            scopes=["https://mail.google.com/"],
        )

        mock_creds = MagicMock()
        mock_creds.valid = False
        mock_creds.expired = True
        mock_creds.refresh_token = "refresh_tok"
        mock_creds.to_json.return_value = "{}"

        with (
            patch("deep_thought.gmail.client.Credentials.from_authorized_user_file", return_value=mock_creds),
            patch("deep_thought.gmail.client.Request") as mock_request_class,
            patch("deep_thought.gmail.client.build"),
        ):
            client.authenticate()

        mock_creds.refresh.assert_called_once_with(mock_request_class())

    def test_runs_browser_flow_when_no_token(self, tmp_path: Path) -> None:
        """Should run InstalledAppFlow when no valid token file exists."""
        from deep_thought.gmail.client import GmailClient

        credentials_file = tmp_path / "credentials.json"
        credentials_file.write_text("{}", encoding="utf-8")
        # Deliberately do NOT create the token file — forces the browser flow path

        client = GmailClient(
            credentials_path=str(credentials_file),
            token_path=str(tmp_path / "token.json"),
            scopes=["https://mail.google.com/"],
        )

        mock_flow = MagicMock()
        mock_new_creds = MagicMock()
        mock_new_creds.to_json.return_value = "{}"
        mock_flow.run_local_server.return_value = mock_new_creds

        with (
            patch("deep_thought.gmail.client.InstalledAppFlow.from_client_secrets_file", return_value=mock_flow),
            patch("deep_thought.gmail.client.build"),
        ):
            client.authenticate()

        mock_flow.run_local_server.assert_called_once_with(port=0)

    def test_raises_when_credentials_file_missing(self, tmp_path: Path) -> None:
        """Should raise FileNotFoundError when the credentials.json file does not exist."""
        from deep_thought.gmail.client import GmailClient

        client = GmailClient(
            credentials_path=str(tmp_path / "missing_credentials.json"),
            token_path=str(tmp_path / "token.json"),
            scopes=["https://mail.google.com/"],
        )

        # No token file exists either — forces the browser flow path
        with pytest.raises(FileNotFoundError):
            client.authenticate()


# ---------------------------------------------------------------------------
# get_raw_message missing field (L8)
# ---------------------------------------------------------------------------


class TestGmailClientGetRawMessageMissingField:
    """Tests that get_raw_message raises ValueError when 'raw' field is absent."""

    def test_raises_value_error_when_raw_field_missing(self) -> None:
        """Should raise ValueError when the API response lacks the 'raw' field."""
        from deep_thought.gmail.client import GmailClient

        client = GmailClient.__new__(GmailClient)
        client._rate_limit_rpm = 0
        client._retry_max_attempts = 1
        client._retry_base_delay = 0.0
        client._last_request_time = 0.0

        mock_service = MagicMock()
        mock_get = MagicMock()
        # Response without the 'raw' key
        mock_get.execute.return_value = {"id": "msg_001", "payload": {}}
        mock_service.users().messages().get.return_value = mock_get
        client._service = mock_service

        with pytest.raises(ValueError, match="no 'raw' field"):
            client.get_raw_message("msg_001")
