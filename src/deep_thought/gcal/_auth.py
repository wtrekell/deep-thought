"""OAuth 2.0 token management for the GCal Tool.

Delegates to the shared ``deep_thought.secrets`` module for the full token
lifecycle: load from keychain (or file fallback), refresh if expired, run
browser consent flow if no valid token exists, and persist the token back
to keychain (or file).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from deep_thought.secrets import GOOGLE_OAUTH_SCOPES, GOOGLE_SERVICE, get_oauth_credentials

if TYPE_CHECKING:
    from google.oauth2.credentials import Credentials


def get_credentials(credentials_path: str, token_path: str, scopes: list[str]) -> Credentials:
    """Load, refresh, or obtain OAuth 2.0 credentials for the Google Calendar API.

    Delegates to the shared ``google`` token, requesting the full set of
    Google OAuth scopes so that a single keychain entry covers gmail, gcal,
    and gdrive.  The ``scopes`` parameter is accepted for backward
    compatibility but is not used — ``GOOGLE_OAUTH_SCOPES`` is always
    requested.

    See ``deep_thought.secrets.get_oauth_credentials`` for full behavior.

    Args:
        credentials_path: Path to the OAuth client secret JSON file.
        token_path: File path used as fallback when keychain is unavailable.
        scopes: Ignored. Present for backward compatibility only.

    Returns:
        A valid google.oauth2.credentials.Credentials object.

    Raises:
        FileNotFoundError: If ``credentials_path`` does not exist.
        RuntimeError: If neither keychain nor token_path is available.
        google.auth.exceptions.RefreshError: If token refresh fails.
    """
    return get_oauth_credentials(
        GOOGLE_SERVICE,
        credentials_path,
        token_path,
        GOOGLE_OAUTH_SCOPES,
        required_scopes=GOOGLE_OAUTH_SCOPES,
    )
