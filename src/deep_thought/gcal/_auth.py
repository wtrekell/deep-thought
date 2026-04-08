"""OAuth 2.0 token management for the GCal Tool.

Delegates to the shared ``deep_thought.secrets`` module for the full token
lifecycle: load from keychain (or file fallback), refresh if expired, run
browser consent flow if no valid token exists, and persist the token back
to keychain (or file).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from deep_thought.secrets import get_oauth_credentials

if TYPE_CHECKING:
    from google.oauth2.credentials import Credentials

_GCAL_SERVICE = "gcal"


def get_credentials(credentials_path: str, token_path: str, scopes: list[str]) -> Credentials:
    """Load, refresh, or obtain OAuth 2.0 credentials for the Google Calendar API.

    See ``deep_thought.secrets.get_oauth_credentials`` for full behavior.

    Args:
        credentials_path: Path to the OAuth client secret JSON file.
        token_path: File path used as fallback when keychain is unavailable.
        scopes: List of OAuth scope URIs to request.

    Returns:
        A valid google.oauth2.credentials.Credentials object.

    Raises:
        FileNotFoundError: If ``credentials_path`` does not exist.
        RuntimeError: If neither keychain nor token_path is available.
        google.auth.exceptions.RefreshError: If token refresh fails.
    """
    return get_oauth_credentials(_GCAL_SERVICE, credentials_path, token_path, scopes)
