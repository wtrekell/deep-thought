"""Gmail API client wrapper with OAuth 2.0 authentication.

Wraps the Google API Python Client in a thin class that normalises the API
surface used by the rest of the tool, making it easy to mock in tests.
Handles pagination, rate limiting, and retry with exponential backoff.
"""

from __future__ import annotations

import base64
import contextlib
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

# Label cache TTL: discard cached label name→ID mappings after this many seconds
# so that labels deleted or renamed in Gmail during a long-running session do
# not leave the client using stale IDs.
_LABEL_CACHE_TTL_SECONDS = 3600.0


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
                # Honour the server-specified Retry-After header when present
                retry_after_value: float = 0.0
                if http_error.resp:
                    raw_retry_after = http_error.resp.get("retry-after", "")
                    if raw_retry_after:
                        with contextlib.suppress(ValueError):
                            retry_after_value = float(raw_retry_after)

                sleep_duration = max(retry_after_value, delay)
                logger.warning(
                    "Gmail API error %d (attempt %d/%d), retrying in %.1fs...",
                    status_code,
                    attempt + 1,
                    max_attempts,
                    sleep_duration,
                )
                time.sleep(sleep_duration)
                delay *= 2

    if last_error is not None:
        raise last_error
    raise RuntimeError("Unexpected state in _retry_with_backoff")  # pragma: no cover


# ---------------------------------------------------------------------------
# GmailClient
# ---------------------------------------------------------------------------


class GmailClient:
    """Thin wrapper around the Gmail API v1 service object.

    Handles OAuth 2.0 authentication, pagination collapsing, label caching,
    rate limiting, and retry with exponential backoff.
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
            rate_limit_rpm: Maximum requests per minute to the Gmail API.
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
        self._label_cache: dict[str, str] = {}
        self._label_cache_populated_at: float = 0.0
        self._last_request_time: float = 0.0

    def authenticate(self) -> None:
        """Run the OAuth 2.0 flow and build the Gmail API service.

        Delegates to the shared ``deep_thought.secrets`` module for keychain-first
        token storage with file fallback.  See ``gmail._auth.get_credentials``
        for the full lifecycle.

        Raises:
            FileNotFoundError: If credentials_path does not exist.
            google.auth.exceptions.RefreshError: If token refresh fails.
        """
        from deep_thought.gmail._auth import get_credentials

        credentials = get_credentials(self._credentials_path, self._token_path, self._scopes)
        self._service = build("gmail", "v1", credentials=credentials)
        logger.debug("Gmail API service initialised.")

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
        """Execute a Gmail API request with rate limiting and retry.

        Args:
            request: A Google API request object (from .list(), .get(), etc.).

        Returns:
            The API response dict.

        Raises:
            RuntimeError: If authenticate() has not been called yet.
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
    # Message operations
    # -----------------------------------------------------------------------

    def list_messages(
        self,
        query: str,
        max_results: int = 100,
        include_spam_trash: bool = False,
    ) -> list[dict[str, Any]]:
        """Search Gmail with a query string and return all matching message stubs.

        Collapses pagination into a flat list. Each stub contains 'id' and
        'threadId' fields only — use get_message() for full content.

        Args:
            query: Gmail search query (same syntax as the Gmail search bar).
            max_results: Maximum number of messages to return.
            include_spam_trash: When True, include messages in Spam and Trash in
                results (passed to the Gmail API as ``includeSpamTrash``).
                Required for any query that targets ``in:trash`` or ``in:spam``.
                Defaults to False to preserve existing collection behavior.

        Returns:
            A list of message stub dicts with 'id' and 'threadId'.
        """
        messages: list[dict[str, Any]] = []
        page_token: str | None = None

        while len(messages) < max_results:
            remaining = max_results - len(messages)
            page_size = min(remaining, 100)

            request = (
                self._service.users()
                .messages()
                .list(
                    userId="me",
                    q=query,
                    maxResults=page_size,
                    pageToken=page_token,
                    includeSpamTrash=include_spam_trash,
                )
            )
            response = self._execute(request)

            batch = response.get("messages", [])
            messages.extend(batch)

            page_token = response.get("nextPageToken")
            if not page_token or not batch:
                break

        return messages[:max_results]

    def get_message(self, message_id: str, format_type: str = "full") -> dict[str, Any]:
        """Fetch a single message by ID.

        Args:
            message_id: The Gmail message ID.
            format_type: One of 'full', 'raw', 'metadata', 'minimal'.

        Returns:
            The full message dict from the Gmail API.
        """
        request = (
            self._service.users()
            .messages()
            .get(
                userId="me",
                id=message_id,
                format=format_type,
            )
        )
        result: dict[str, Any] = self._execute(request)
        return result

    def get_raw_message(self, message_id: str) -> bytes:
        """Fetch a message in raw RFC 2822 format.

        Used for forwarding emails while preserving the original MIME structure.

        Args:
            message_id: The Gmail message ID.

        Returns:
            The decoded raw message bytes.
        """
        message = self.get_message(message_id, format_type="raw")
        raw_data = message.get("raw")
        if not raw_data:
            raise ValueError(f"Message {message_id} has no 'raw' field — check format_type parameter.")
        return base64.urlsafe_b64decode(raw_data)

    def send_message(self, raw_message: bytes) -> dict[str, Any]:
        """Send a message from raw RFC 2822 bytes.

        The raw message is base64url-encoded before sending.

        Args:
            raw_message: The complete RFC 2822 message as bytes.

        Returns:
            The API response dict containing 'id' and 'threadId'.
        """
        encoded = base64.urlsafe_b64encode(raw_message).decode("ascii")
        body: dict[str, str] = {"raw": encoded}
        request = self._service.users().messages().send(userId="me", body=body)
        result: dict[str, Any] = self._execute(request)
        return result

    # -----------------------------------------------------------------------
    # Message modification
    # -----------------------------------------------------------------------

    def modify_message(
        self,
        message_id: str,
        add_labels: list[str] | None = None,
        remove_labels: list[str] | None = None,
    ) -> dict[str, Any]:
        """Add or remove labels from a message.

        Common operations:
        - archive: remove_labels=["INBOX"]
        - mark_read: remove_labels=["UNREAD"]
        - label: add_labels=[label_id]

        Args:
            message_id: The Gmail message ID.
            add_labels: List of label IDs to add.
            remove_labels: List of label IDs to remove.

        Returns:
            The updated message dict.
        """
        body: dict[str, list[str]] = {}
        if add_labels:
            body["addLabelIds"] = add_labels
        if remove_labels:
            body["removeLabelIds"] = remove_labels

        request = (
            self._service.users()
            .messages()
            .modify(
                userId="me",
                id=message_id,
                body=body,
            )
        )
        result: dict[str, Any] = self._execute(request)
        return result

    def delete_message(self, message_id: str) -> None:
        """Permanently delete a message (bypasses Trash).

        Requires the https://mail.google.com/ scope.

        Args:
            message_id: The Gmail message ID.
        """
        request = self._service.users().messages().delete(userId="me", id=message_id)
        self._execute(request)

    def trash_message(self, message_id: str) -> None:
        """Move a message to Gmail Trash.

        Args:
            message_id: The Gmail message ID.
        """
        request = self._service.users().messages().trash(userId="me", id=message_id)
        self._execute(request)

    # -----------------------------------------------------------------------
    # Label management
    # -----------------------------------------------------------------------

    def get_label(self, label_name: str) -> str | None:
        """Get the label ID for a name without creating it if missing.

        Results are served from the same cache used by get_or_create_label.
        Returns None if the label does not exist in Gmail.

        Args:
            label_name: The human-readable label name.

        Returns:
            The Gmail label ID string, or None if the label does not exist.
        """
        # Invalidate the entire cache if it has aged past the TTL
        cache_age = time.time() - self._label_cache_populated_at
        if cache_age >= _LABEL_CACHE_TTL_SECONDS:
            self._label_cache = {}

        if label_name in self._label_cache:
            return self._label_cache[label_name]

        # Search existing labels — do NOT create if missing
        request = self._service.users().labels().list(userId="me")
        response = self._execute(request)
        for label in response.get("labels", []):
            if label.get("name") == label_name:
                label_id: str = label["id"]
                self._label_cache[label_name] = label_id
                self._label_cache_populated_at = time.time()
                return label_id

        return None

    def get_or_create_label(self, label_name: str) -> str:
        """Get the label ID for a name, creating the label if needed.

        Results are cached for up to _LABEL_CACHE_TTL_SECONDS. The cache is
        invalidated as a whole when the TTL expires so that labels deleted or
        renamed in Gmail during a long-running session are not missed.

        Args:
            label_name: The human-readable label name.

        Returns:
            The Gmail label ID string.
        """
        # Invalidate the entire cache if it has aged past the TTL
        cache_age = time.time() - self._label_cache_populated_at
        if cache_age >= _LABEL_CACHE_TTL_SECONDS:
            self._label_cache = {}

        if label_name in self._label_cache:
            return self._label_cache[label_name]

        # Search existing labels
        request = self._service.users().labels().list(userId="me")
        response = self._execute(request)
        for label in response.get("labels", []):
            if label.get("name") == label_name:
                label_id: str = label["id"]
                self._label_cache[label_name] = label_id
                self._label_cache_populated_at = time.time()
                return label_id

        # Create the label
        label_body: dict[str, str] = {"name": label_name, "labelListVisibility": "labelShow"}
        create_request = self._service.users().labels().create(userId="me", body=label_body)
        created_label = self._execute(create_request)
        created_id: str = created_label["id"]
        self._label_cache[label_name] = created_id
        self._label_cache_populated_at = time.time()
        logger.info("Created Gmail label '%s' (ID: %s)", label_name, created_id)
        return created_id
