"""Tests for deep_thought.gdrive.client — DriveClient wrapper."""

from __future__ import annotations

import logging
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


def test_ensure_folder_no_race_returns_created_id() -> None:
    """ensure_folder returns the newly created ID when the post-create re-query finds only one folder."""
    client = _make_client()
    mock_service = MagicMock()
    client._service = mock_service  # type: ignore[attr-defined]

    mock_list_empty = MagicMock()
    mock_list_empty.execute.return_value = {"files": []}

    mock_list_single = MagicMock()
    mock_list_single.execute.return_value = {
        "files": [{"id": "new-folder-id", "name": "notes", "createdTime": "2026-04-16T10:00:00.000Z"}]
    }

    mock_create_request = MagicMock()
    mock_create_request.execute.return_value = {"id": "new-folder-id"}

    # Call sequence: initial list (empty) → create → post-create list (one result)
    mock_service.files.return_value.list.side_effect = [mock_list_empty, mock_list_single]
    mock_service.files.return_value.create.return_value = mock_create_request

    folder_id = client.ensure_folder(folder_name="notes", parent_folder_id="parent-id")

    assert folder_id == "new-folder-id"
    assert mock_service.files.return_value.list.call_count == 2
    mock_service.files.return_value.create.assert_called_once()


def test_ensure_folder_toctou_race_logs_warning_and_picks_oldest() -> None:
    """ensure_folder detects a TOCTOU race when the post-create re-query returns two folders.

    Simulates the case where an external process created the same folder between
    our initial list (empty) and our create call. After the create, the re-query
    returns both folders. The function should log a WARNING and return the oldest
    folder by createdTime.
    """
    client = _make_client()
    mock_service = MagicMock()
    client._service = mock_service  # type: ignore[attr-defined]

    mock_list_empty = MagicMock()
    mock_list_empty.execute.return_value = {"files": []}

    # Two folders — our newly created one and an externally created duplicate.
    # The external one is older (earlier createdTime) and should win.
    mock_list_duplicates = MagicMock()
    mock_list_duplicates.execute.return_value = {
        "files": [
            {"id": "our-folder-id", "name": "notes", "createdTime": "2026-04-16T10:00:02.000Z"},
            {"id": "external-folder-id", "name": "notes", "createdTime": "2026-04-16T10:00:00.000Z"},
        ]
    }

    mock_create_request = MagicMock()
    mock_create_request.execute.return_value = {"id": "our-folder-id"}

    # Call sequence: initial list (empty) → create → post-create list (two results)
    mock_service.files.return_value.list.side_effect = [mock_list_empty, mock_list_duplicates]
    mock_service.files.return_value.create.return_value = mock_create_request

    folder_id = client.ensure_folder(folder_name="notes", parent_folder_id="parent-id")

    # The external (older) folder should win
    assert folder_id == "external-folder-id"
    assert mock_service.files.return_value.list.call_count == 2


def test_ensure_folder_toctou_race_warning_message(caplog: pytest.LogCaptureFixture) -> None:
    """ensure_folder emits a WARNING when duplicates are detected after create."""
    client = _make_client()
    mock_service = MagicMock()
    client._service = mock_service  # type: ignore[attr-defined]

    mock_list_empty = MagicMock()
    mock_list_empty.execute.return_value = {"files": []}

    mock_list_duplicates = MagicMock()
    mock_list_duplicates.execute.return_value = {
        "files": [
            {"id": "folder-newer", "name": "archive", "createdTime": "2026-04-16T10:00:05.000Z"},
            {"id": "folder-older", "name": "archive", "createdTime": "2026-04-16T10:00:01.000Z"},
        ]
    }

    mock_create_request = MagicMock()
    mock_create_request.execute.return_value = {"id": "folder-newer"}

    mock_service.files.return_value.list.side_effect = [mock_list_empty, mock_list_duplicates]
    mock_service.files.return_value.create.return_value = mock_create_request

    with caplog.at_level(logging.WARNING, logger="deep_thought.gdrive.client"):
        folder_id = client.ensure_folder(folder_name="archive", parent_folder_id="parent-id")

    # Oldest wins
    assert folder_id == "folder-older"
    # At least one WARNING was emitted
    warning_messages = [record.message for record in caplog.records if record.levelno == logging.WARNING]
    assert len(warning_messages) >= 1
    # The warning should mention the duplicate count and folder name
    combined_warning_text = " ".join(warning_messages)
    assert "archive" in combined_warning_text
    assert "2" in combined_warning_text  # found 2 folders


def test_ensure_folder_toctou_race_id_tiebreak_for_same_created_time() -> None:
    """ensure_folder breaks createdTime ties by picking the smallest folder ID."""
    client = _make_client()
    mock_service = MagicMock()
    client._service = mock_service  # type: ignore[attr-defined]

    same_timestamp = "2026-04-16T10:00:00.000Z"
    mock_list_empty = MagicMock()
    mock_list_empty.execute.return_value = {"files": []}

    mock_list_duplicates = MagicMock()
    mock_list_duplicates.execute.return_value = {
        "files": [
            {"id": "zzz-folder-id", "name": "notes", "createdTime": same_timestamp},
            {"id": "aaa-folder-id", "name": "notes", "createdTime": same_timestamp},
        ]
    }

    mock_create_request = MagicMock()
    mock_create_request.execute.return_value = {"id": "zzz-folder-id"}

    mock_service.files.return_value.list.side_effect = [mock_list_empty, mock_list_duplicates]
    mock_service.files.return_value.create.return_value = mock_create_request

    folder_id = client.ensure_folder(folder_name="notes", parent_folder_id="parent-id")

    # Smallest ID wins the tiebreak
    assert folder_id == "aaa-folder-id"


def test_delete_file_calls_drive_api_delete() -> None:
    """delete_file calls files().delete() with the correct fileId."""
    client = _make_client()
    mock_service = MagicMock()
    client._service = mock_service  # type: ignore[attr-defined]

    mock_delete_request = MagicMock()
    mock_delete_request.execute.return_value = None
    mock_service.files.return_value.delete.return_value = mock_delete_request

    client.delete_file("file-to-delete-id")

    mock_service.files.return_value.delete.assert_called_once_with(fileId="file-to-delete-id")
    mock_delete_request.execute.assert_called_once()


def test_upload_file_uses_media_file_upload(tmp_path: Path) -> None:
    """upload_file uses MediaFileUpload (streaming) not MediaIoBaseUpload (buffered)."""
    test_file = tmp_path / "large_file.txt"
    test_file.write_text("file content")

    client = _make_client()
    mock_service = MagicMock()
    client._service = mock_service  # type: ignore[attr-defined]

    mock_create_request = MagicMock()
    mock_create_request.execute.return_value = {"id": "streamed-file-id"}
    mock_service.files.return_value.create.return_value = mock_create_request

    captured_media_objects: list[object] = []

    original_create = mock_service.files.return_value.create

    def capture_create(**kwargs: object) -> MagicMock:
        captured_media_objects.append(kwargs.get("media_body"))
        return mock_create_request

    mock_service.files.return_value.create.side_effect = capture_create

    client.upload_file(
        local_path=str(test_file),
        drive_folder_id="parent-folder-id",
        mime_type="text/plain",
    )

    assert len(captured_media_objects) == 1
    from googleapiclient.http import MediaFileUpload  # type: ignore[import-untyped]

    assert isinstance(captured_media_objects[0], MediaFileUpload), (
        "upload_file must pass a MediaFileUpload (streaming) not MediaIoBaseUpload (buffered)"
    )

    # Restore so later tests are unaffected
    mock_service.files.return_value.create.side_effect = None
    mock_service.files.return_value.create = original_create


def test_update_file_uses_media_file_upload(tmp_path: Path) -> None:
    """update_file uses MediaFileUpload (streaming) not MediaIoBaseUpload (buffered)."""
    test_file = tmp_path / "updated_file.txt"
    test_file.write_text("updated content")

    client = _make_client()
    mock_service = MagicMock()
    client._service = mock_service  # type: ignore[attr-defined]

    mock_update_request = MagicMock()
    mock_update_request.execute.return_value = {}

    captured_media_objects: list[object] = []

    def capture_update(**kwargs: object) -> MagicMock:
        captured_media_objects.append(kwargs.get("media_body"))
        return mock_update_request

    mock_service.files.return_value.update.side_effect = capture_update

    client.update_file(
        drive_file_id="existing-file-id",
        local_path=str(test_file),
        mime_type="text/plain",
    )

    assert len(captured_media_objects) == 1
    from googleapiclient.http import MediaFileUpload  # type: ignore[import-untyped]

    assert isinstance(captured_media_objects[0], MediaFileUpload), (
        "update_file must pass a MediaFileUpload (streaming) not MediaIoBaseUpload (buffered)"
    )


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
