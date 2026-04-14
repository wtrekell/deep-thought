"""Google Drive API v3 client wrapper with OAuth 2.0 authentication.

Wraps the Google API Python Client in a thin class that normalises the Drive
API surface used by the backup tool. Handles rate limiting via a token-bucket
approach and retry with exponential backoff on transient errors.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from googleapiclient.discovery import build  # type: ignore[import-untyped]
from googleapiclient.errors import HttpError  # type: ignore[import-untyped]
from googleapiclient.http import MediaFileUpload  # type: ignore[import-untyped]

from deep_thought.gdrive._auth import get_credentials

logger = logging.getLogger(__name__)

_RETRYABLE_STATUS_CODES = {429, 500, 503}

# MIME type for Google Drive folders
_DRIVE_FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"


def _retry_with_backoff(
    func: Any,
    max_attempts: int = 3,
    base_delay: float = 2.0,
) -> Any:
    """Execute a callable with exponential backoff on transient Drive API errors.

    Retries on HTTP 429, 500, and 503. Permanent 4xx errors (except 429)
    are raised immediately without retry.

    Args:
        func: A no-argument callable that may raise HttpError.
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
                    "Drive API error %d (attempt %d/%d), retrying in %.1fs...",
                    status_code,
                    attempt + 1,
                    max_attempts,
                    delay,
                )
                time.sleep(delay)
                delay *= 2

    if last_error is not None:
        logger.error(
            "Drive API call failed after %d attempt(s). Final error: %s",
            max_attempts,
            last_error,
        )
        raise last_error
    raise RuntimeError("Unexpected state in _retry_with_backoff")  # pragma: no cover


class DriveClient:
    """Thin wrapper around the Google Drive API v3 service object.

    Handles OAuth 2.0 authentication, rate limiting, and retry with
    exponential backoff. Call authenticate() before any other method.
    """

    def __init__(
        self,
        credentials_path: str,
        token_path: str,
        scopes: list[str],
        rate_limit_rpm: int = 100,
        retry_max_attempts: int = 3,
        retry_base_delay: float = 2.0,
    ) -> None:
        """Store configuration for later authentication.

        Does NOT authenticate on construction. Call authenticate() to build
        the Drive API service object. This separation allows the CLI 'auth'
        command to run the flow independently.

        Args:
            credentials_path: Path to the OAuth client secret JSON file.
            token_path: Path to store/load the OAuth access + refresh token.
            scopes: List of OAuth scope URIs to request.
            rate_limit_rpm: Maximum Drive API calls per minute.
            retry_max_attempts: Maximum retry attempts for transient errors.
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
        """Run the OAuth 2.0 flow and build the Drive API service object.

        Delegates token management to _auth.get_credentials(). Builds the
        Drive v3 service after obtaining valid credentials.

        Raises:
            FileNotFoundError: If credentials_path does not exist and a
                               new consent flow is required.
            google.auth.exceptions.RefreshError: If token refresh fails.
        """
        credentials = get_credentials(
            credentials_path=self._credentials_path,
            token_path=self._token_path,
            scopes=self._scopes,
        )
        self._service = build("drive", "v3", credentials=credentials)
        logger.debug("Drive API v3 service initialised.")

    def _rate_limit(self) -> None:
        """Enforce the configured rate limit between API calls.

        Sleeps for the remaining time if the minimum inter-request interval
        has not elapsed since the last call.
        """
        if self._rate_limit_rpm <= 0:
            return
        minimum_interval_seconds = 60.0 / self._rate_limit_rpm
        elapsed_since_last_request = time.time() - self._last_request_time
        if elapsed_since_last_request < minimum_interval_seconds:
            time.sleep(minimum_interval_seconds - elapsed_since_last_request)
        self._last_request_time = time.time()

    def _execute(self, request: Any) -> Any:
        """Execute a Drive API request with rate limiting and retry.

        Args:
            request: A Google API request object (from .create(), .get(), etc.).

        Returns:
            The API response dict.

        Raises:
            RuntimeError: If authenticate() has not been called.
        """
        if self._service is None:
            raise RuntimeError("Must call authenticate() before making Drive API requests.")
        self._rate_limit()
        return _retry_with_backoff(
            request.execute,
            max_attempts=self._retry_max_attempts,
            base_delay=self._retry_base_delay,
        )

    def upload_file(self, local_path: str, drive_folder_id: str, mime_type: str) -> str:
        """Upload a local file to a Drive folder as a new file.

        Args:
            local_path: Absolute path to the local file to upload.
            drive_folder_id: The Drive folder ID to upload into.
            mime_type: The MIME type of the file (e.g. 'text/plain').

        Returns:
            The Drive file ID of the newly created file.

        Raises:
            RuntimeError: If authenticate() has not been called.
            HttpError: If the API call fails after all retries.
        """
        file_name = Path(local_path).name
        file_metadata: dict[str, Any] = {
            "name": file_name,
            "parents": [drive_folder_id],
        }

        media = MediaFileUpload(local_path, mimetype=mime_type, resumable=True)

        request = self._service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id",
        )
        response: dict[str, Any] = self._execute(request)
        drive_file_id: str = response["id"]
        logger.debug("Uploaded %s → Drive file ID %s", local_path, drive_file_id)
        return drive_file_id

    def update_file(self, drive_file_id: str, local_path: str, mime_type: str) -> None:
        """Update the content of an existing Drive file in-place.

        The file metadata (name, location) is unchanged; only the content
        is replaced. Uses PATCH semantics with a media body.

        Args:
            drive_file_id: The Drive file ID to update.
            local_path: Absolute path to the local file with new content.
            mime_type: The MIME type of the file.

        Raises:
            RuntimeError: If authenticate() has not been called.
            HttpError: If the API call fails after all retries.
        """
        media = MediaFileUpload(local_path, mimetype=mime_type, resumable=True)

        request = self._service.files().update(
            fileId=drive_file_id,
            media_body=media,
        )
        self._execute(request)
        logger.debug("Updated Drive file ID %s from %s", drive_file_id, local_path)

    def delete_file(self, drive_file_id: str) -> None:
        """Permanently delete a file from Google Drive.

        Args:
            drive_file_id: The Drive file ID to delete.

        Raises:
            RuntimeError: If authenticate() has not been called.
            HttpError: If the API call fails after all retries.
        """
        request = self._service.files().delete(fileId=drive_file_id)
        self._execute(request)
        logger.debug("Deleted Drive file ID %s", drive_file_id)

    def ensure_folder(self, folder_name: str, parent_folder_id: str) -> str:
        """Return the Drive folder ID for folder_name under parent_folder_id.

        Searches for an existing folder with that name in the parent. If none
        is found, creates it. This is idempotent — repeated calls with the
        same arguments return the same folder ID without creating duplicates.

        Args:
            folder_name: The display name of the folder to find or create.
            parent_folder_id: The Drive folder ID of the parent directory.

        Returns:
            The Drive folder ID of the found or newly created folder.

        Raises:
            RuntimeError: If authenticate() has not been called.
            HttpError: If the API call fails after all retries.
        """
        # Escape single quotes in folder name for the query string
        escaped_folder_name = folder_name.replace("'", "\\'")
        query = (
            f"name = '{escaped_folder_name}' "
            f"and mimeType = 'application/vnd.google-apps.folder' "
            f"and '{parent_folder_id}' in parents "
            f"and trashed = false"
        )

        list_request = self._service.files().list(
            q=query,
            fields="files(id, name)",
            spaces="drive",
        )
        list_response: dict[str, Any] = self._execute(list_request)
        existing_folders: list[dict[str, Any]] = list_response.get("files", [])

        if existing_folders:
            found_folder_id: str = existing_folders[0]["id"]
            logger.debug("Found existing Drive folder '%s' → ID %s", folder_name, found_folder_id)
            return found_folder_id

        # Folder does not exist — create it
        folder_metadata: dict[str, Any] = {
            "name": folder_name,
            "mimeType": _DRIVE_FOLDER_MIME_TYPE,
            "parents": [parent_folder_id],
        }
        create_request = self._service.files().create(
            body=folder_metadata,
            fields="id",
        )
        create_response: dict[str, Any] = self._execute(create_request)
        new_folder_id: str = create_response["id"]
        logger.debug("Created Drive folder '%s' → ID %s", folder_name, new_folder_id)
        return new_folder_id
