"""OAuth 2.0 token management for the GDrive Tool.

Self-contained implementation that reads, refreshes, and writes a plain
``token.json`` file on disk. This module does NOT talk to the system
keychain and does NOT share a token with the gmail or gcal tools — gdrive
has its own credentials file, its own token file, and its own scopes.

Behavior:

1. If ``token_path`` points at an existing file, credentials are loaded
   from it via :meth:`google.oauth2.credentials.Credentials.from_authorized_user_file`.
2. If the loaded credentials are valid, they are returned as-is.
3. If the loaded credentials are expired but carry a refresh token, the
   token is refreshed via ``google-auth``'s ``Request`` transport and the
   refreshed credentials are written back to ``token_path``.
4. Otherwise (no token file, or token unusable), the OAuth 2.0 browser
   consent flow is run via :class:`google_auth_oauthlib.flow.InstalledAppFlow`
   and the resulting credentials are written to ``token_path`` with mode
   ``0o600`` so they are not world-readable.

The public API is intentionally a single function, :func:`get_credentials`,
with the same signature as the earlier shim over ``deep_thought.secrets``
so existing callers in ``client.py`` and ``cli.py`` do not need changes.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)


def _load_existing_token(token_path_obj: Path, scopes: list[str]) -> Credentials | None:
    """Return credentials loaded from ``token_path_obj`` or ``None`` if absent.

    Any parse error is logged at WARNING and ``None`` is returned so the caller
    falls through to the browser consent flow.
    """
    if not token_path_obj.exists():
        return None

    try:
        loaded: Credentials = Credentials.from_authorized_user_file(  # type: ignore[no-untyped-call]
            str(token_path_obj), scopes
        )
        return loaded
    except (ValueError, OSError) as load_error:
        logger.warning("Failed to load token file %s: %s — re-running consent flow.", token_path_obj, load_error)
        return None


def _write_token_file(credentials: Credentials, token_path_obj: Path) -> None:
    """Write ``credentials`` to ``token_path_obj`` with mode 0o600.

    Creates parent directories as needed.
    """
    token_path_obj.parent.mkdir(parents=True, exist_ok=True)
    token_path_obj.write_text(credentials.to_json(), encoding="utf-8")  # type: ignore[no-untyped-call]
    os.chmod(token_path_obj, 0o600)
    logger.debug("Wrote OAuth token to %s (mode 0o600).", token_path_obj)


def get_credentials(credentials_path: str, token_path: str, scopes: list[str]) -> Credentials:
    """Load, refresh, or obtain OAuth 2.0 credentials for the Drive API.

    Args:
        credentials_path: Path to the OAuth client secret JSON file downloaded
                          from Google Cloud Console. Only consulted when a new
                          consent flow is required.
        token_path: Path where the OAuth token JSON is stored. Must be a
                    non-empty string. The file is created if it does not
                    already exist.
        scopes: List of OAuth scope URIs to request. Used both when loading
                an existing token file and when running the consent flow.

    Returns:
        A valid :class:`google.oauth2.credentials.Credentials` object.

    Raises:
        ValueError: If ``token_path`` is empty.
        FileNotFoundError: If a new consent flow is required and
                           ``credentials_path`` does not exist.
        google.auth.exceptions.RefreshError: If a token refresh fails.
    """
    if not token_path:
        raise ValueError(
            "auth.token_file must be a non-empty path. "
            "Set it in your gdrive-configuration.yaml to the location where the OAuth token should be stored."
        )

    token_path_obj = Path(token_path)
    existing_credentials = _load_existing_token(token_path_obj, scopes)

    if existing_credentials is not None and existing_credentials.valid:
        return existing_credentials

    if existing_credentials is not None and existing_credentials.expired and existing_credentials.refresh_token:
        logger.debug("Refreshing expired OAuth token at %s.", token_path_obj)
        existing_credentials.refresh(Request())
        _write_token_file(existing_credentials, token_path_obj)
        return existing_credentials

    credentials_path_obj = Path(credentials_path)
    if not credentials_path_obj.exists():
        raise FileNotFoundError(
            f"OAuth client secret not found at {credentials_path}. "
            "Download the client secret JSON from Google Cloud Console, place it at this path, "
            "then run `gdrive auth`."
        )

    logger.debug("Running OAuth consent flow with client secret %s.", credentials_path_obj)
    flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path_obj), scopes)
    new_credentials: Credentials = flow.run_local_server(port=0)
    _write_token_file(new_credentials, token_path_obj)
    return new_credentials
