"""Tests for the Gmail Tool API client wrapper."""

from __future__ import annotations

import base64
from unittest.mock import MagicMock, patch

import pytest

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
        from deep_thought.gmail.client import GmailClient

        client = GmailClient.__new__(GmailClient)
        client._label_cache = {"Processed": "Label_123"}
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
