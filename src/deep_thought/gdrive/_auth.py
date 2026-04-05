"""OAuth 2.0 token management for the GDrive Tool.

Provides a single public function, get_credentials(), which handles the full
token lifecycle: load from disk, refresh if expired, run browser consent flow
if no valid token exists, and persist the token back to disk.
"""

from __future__ import annotations

import logging
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)


def get_credentials(credentials_path: str, token_path: str, scopes: list[str]) -> Credentials:
    """Load, refresh, or obtain OAuth 2.0 credentials for the Drive API.

    Attempts operations in this order:
    1. Load an existing token from ``token_path``.
    2. If the token is expired but has a refresh token, refresh it silently.
    3. If no valid token exists, open a browser window for user consent.
    4. Persist the (new or refreshed) token back to ``token_path``.

    Args:
        credentials_path: Path to the OAuth client secret JSON file
                          (downloaded from Google Cloud Console).
        token_path: Path where the OAuth access + refresh token is stored.
                    Created or overwritten on each successful auth.
        scopes: List of OAuth scope URIs to request (e.g. drive.file).

    Returns:
        A valid google.oauth2.credentials.Credentials object.

    Raises:
        FileNotFoundError: If ``credentials_path`` does not exist when a
                           browser consent flow is required.
        google.auth.exceptions.RefreshError: If a token refresh fails.
    """
    resolved_token_path = Path(token_path)
    existing_credentials: Credentials | None = None

    if resolved_token_path.exists():
        existing_credentials = Credentials.from_authorized_user_file(  # type: ignore[no-untyped-call]
            str(resolved_token_path), scopes
        )
        logger.debug("Loaded existing OAuth token from %s", resolved_token_path)

    if existing_credentials is not None and existing_credentials.valid:
        return existing_credentials

    if existing_credentials is not None and existing_credentials.expired and existing_credentials.refresh_token:
        logger.debug("Refreshing expired OAuth token.")
        existing_credentials.refresh(Request())
        _save_token(existing_credentials, resolved_token_path)
        return existing_credentials

    # No valid token — run the interactive browser consent flow.
    resolved_credentials_path = Path(credentials_path)
    if not resolved_credentials_path.exists():
        raise FileNotFoundError(
            f"OAuth client secret not found at {credentials_path}. "
            "Download credentials.json from Google Cloud Console and place it at the configured path."
        )

    logger.info("Starting OAuth browser flow for user consent.")
    flow = InstalledAppFlow.from_client_secrets_file(str(resolved_credentials_path), scopes)
    new_credentials: Credentials = flow.run_local_server(port=0)

    _save_token(new_credentials, resolved_token_path)
    return new_credentials


def _save_token(credentials: Credentials, token_path: Path) -> None:
    """Persist OAuth credentials to disk, restricted to owner-read only.

    Args:
        credentials: The credentials object to serialize as JSON.
        token_path: The file path to write the token to.
    """
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(credentials.to_json())  # type: ignore[no-untyped-call]
    # chmod(0o600) restricts access to the owner only on POSIX systems.
    # This call is a no-op on Windows — a known platform limitation.
    token_path.chmod(0o600)
    logger.debug("OAuth token saved to %s", token_path)
