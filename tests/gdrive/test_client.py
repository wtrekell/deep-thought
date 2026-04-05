"""Tests for deep_thought.gdrive.client — DriveClient wrapper."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
from googleapiclient.errors import HttpError  # type: ignore[import-untyped]

from deep_thought.gdrive.client import DriveClient, _retry_with_backoff

if TYPE_CHECKING:
    from pathlib import Path

# ---------------------------------------------------------------------------
# Retry helper tests
# ---------------------------------------------------------------------------


def test_retry_with_backoff_succeeds_on_first_attempt() -> None:
    """_retry_with_backoff returns immediately when the callable succeeds."""
    call_count = 0

    def always_succeeds() -> str:
        nonlocal call_count
        call_count += 1
        return "ok"

    result = _retry_with_backoff(always_succeeds, max_attempts=3, base_delay=0.0)

    assert result == "ok"
    assert call_count == 1


def test_retry_with_backoff_retries_on_429() -> None:
    """_retry_with_backoff retries up to max_attempts on HTTP 429."""
    attempt_count = 0

    def fail_twice_then_succeed() -> str:
        nonlocal attempt_count
        attempt_count += 1
        if attempt_count < 3:
            fake_response = MagicMock()
            fake_response.status = 429
            raise HttpError(resp=fake_response, content=b"rate limited")
        return "success"

    with patch("deep_thought.gdrive.client.time.sleep"):
        result = _retry_with_backoff(fail_twice_then_succeed, max_attempts=3, base_delay=0.01)

    assert result == "success"
    assert attempt_count == 3


def test_retry_with_backoff_raises_immediately_on_404() -> None:
    """_retry_with_backoff raises immediately on non-retryable 4xx errors."""
    call_count = 0

    def always_404() -> str:
        nonlocal call_count
        call_count += 1
        fake_response = MagicMock()
        fake_response.status = 404
        raise HttpError(resp=fake_response, content=b"not found")

    with pytest.raises(HttpError):
        _retry_with_backoff(always_404, max_attempts=3, base_delay=0.0)

    assert call_count == 1  # No retries for 404


def test_retry_with_backoff_exhausts_all_attempts_on_500() -> None:
    """_retry_with_backoff raises after exhausting all attempts on HTTP 500."""
    call_count = 0

    def always_500() -> str:
        nonlocal call_count
        call_count += 1
        fake_response = MagicMock()
        fake_response.status = 500
        raise HttpError(resp=fake_response, content=b"server error")

    with patch("deep_thought.gdrive.client.time.sleep"), pytest.raises(HttpError):
        _retry_with_backoff(always_500, max_attempts=3, base_delay=0.01)

    assert call_count == 3


# ---------------------------------------------------------------------------
# DriveClient unit tests (mocked Drive service)
# ---------------------------------------------------------------------------


def _make_client() -> DriveClient:
    """Return a DriveClient configured with dummy credentials."""
    return DriveClient(
        credentials_path="/fake/credentials.json",
        token_path="/fake/token.json",
        scopes=["https://www.googleapis.com/auth/drive.file"],
        rate_limit_rpm=0,  # Disable rate limiting in tests
        retry_max_attempts=1,
        retry_base_delay=0.0,
    )


def test_drive_client_raises_if_not_authenticated() -> None:
    """Calling _execute before authenticate() raises RuntimeError."""
    client = _make_client()
    fake_request = MagicMock()

    with pytest.raises(RuntimeError, match="authenticate\\(\\)"):
        client._execute(fake_request)  # type: ignore[attr-defined]


def test_authenticate_builds_drive_service() -> None:
    """authenticate() calls get_credentials and builds the Drive v3 service."""
    client = _make_client()

    mock_credentials = MagicMock()
    mock_service = MagicMock()

    with (
        patch("deep_thought.gdrive.client.get_credentials", return_value=mock_credentials),
        patch("deep_thought.gdrive.client.build", return_value=mock_service),
    ):
        client.authenticate()

    assert client._service is mock_service  # type: ignore[attr-defined]


def test_upload_file_calls_drive_api_with_correct_args(tmp_path: Path) -> None:
    """upload_file calls files().create() with the correct metadata."""
    test_file = tmp_path / "test.txt"
    test_file.write_text("hello world")

    client = _make_client()
    mock_service = MagicMock()
    client._service = mock_service  # type: ignore[attr-defined]

    # Set up the mock chain: service.files().create().execute()
    mock_create_request = MagicMock()
    mock_create_request.execute.return_value = {"id": "new-file-id-123"}
    mock_service.files.return_value.create.return_value = mock_create_request

    file_id = client.upload_file(
        local_path=str(test_file),
        drive_folder_id="parent-folder-id",
        mime_type="text/plain",
    )

    assert file_id == "new-file-id-123"
    mock_service.files.return_value.create.assert_called_once()
    call_kwargs = mock_service.files.return_value.create.call_args.kwargs
    assert call_kwargs["body"]["parents"] == ["parent-folder-id"]
    assert call_kwargs["body"]["name"] == "test.txt"


def test_update_file_calls_drive_api_update(tmp_path: Path) -> None:
    """update_file calls files().update() with the correct fileId."""
    test_file = tmp_path / "test.txt"
    test_file.write_text("updated content")

    client = _make_client()
    mock_service = MagicMock()
    client._service = mock_service  # type: ignore[attr-defined]

    mock_update_request = MagicMock()
    mock_update_request.execute.return_value = {}
    mock_service.files.return_value.update.return_value = mock_update_request

    client.update_file(
        drive_file_id="existing-file-id",
        local_path=str(test_file),
        mime_type="text/plain",
    )

    mock_service.files.return_value.update.assert_called_once()
    call_kwargs = mock_service.files.return_value.update.call_args.kwargs
    assert call_kwargs["fileId"] == "existing-file-id"


def test_ensure_folder_returns_existing_folder_id() -> None:
    """ensure_folder returns the existing folder ID when a matching folder is found."""
    client = _make_client()
    mock_service = MagicMock()
    client._service = mock_service  # type: ignore[attr-defined]

    mock_list_request = MagicMock()
    mock_list_request.execute.return_value = {"files": [{"id": "existing-folder-id", "name": "notes"}]}
    mock_service.files.return_value.list.return_value = mock_list_request

    folder_id = client.ensure_folder(folder_name="notes", parent_folder_id="parent-id")

    assert folder_id == "existing-folder-id"
    # create should NOT have been called
    mock_service.files.return_value.create.assert_not_called()


def test_ensure_folder_creates_folder_when_not_found() -> None:
    """ensure_folder creates a new folder when none exists with that name."""
    client = _make_client()
    mock_service = MagicMock()
    client._service = mock_service  # type: ignore[attr-defined]

    mock_list_request = MagicMock()
    mock_list_request.execute.return_value = {"files": []}
    mock_service.files.return_value.list.return_value = mock_list_request

    mock_create_request = MagicMock()
    mock_create_request.execute.return_value = {"id": "new-folder-id"}
    mock_service.files.return_value.create.return_value = mock_create_request

    folder_id = client.ensure_folder(folder_name="new-folder", parent_folder_id="parent-id")

    assert folder_id == "new-folder-id"
    mock_service.files.return_value.create.assert_called_once()


def test_rate_limiting_sleeps_between_calls(tmp_path: Path) -> None:
    """DriveClient sleeps to respect the configured rate limit."""
    test_file = tmp_path / "file.txt"
    test_file.write_text("content")

    # 60 RPM = 1 second between calls
    client = DriveClient(
        credentials_path="/fake/credentials.json",
        token_path="/fake/token.json",
        scopes=[],
        rate_limit_rpm=60,
        retry_max_attempts=1,
        retry_base_delay=0.0,
    )
    mock_service = MagicMock()
    client._service = mock_service  # type: ignore[attr-defined]

    # Set last_request_time to "just now" to trigger the sleep
    client._last_request_time = time.time()  # type: ignore[attr-defined]

    sleep_durations: list[float] = []

    def capture_sleep(duration: float) -> None:
        sleep_durations.append(duration)

    mock_request = MagicMock()
    mock_request.execute.return_value = {}

    with patch("deep_thought.gdrive.client.time.sleep", side_effect=capture_sleep):
        client._execute(mock_request)  # type: ignore[attr-defined]

    # At 60 RPM the sleep should be close to 1 second
    assert len(sleep_durations) == 1
    assert sleep_durations[0] > 0.5  # At least half a second
