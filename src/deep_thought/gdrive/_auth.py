"""OAuth 2.0 token management for the GDrive Tool.

Delegates to the shared ``deep_thought.secrets`` module for the full token
lifecycle: load from keychain (or file fallback), refresh if expired, run
browser consent flow if no valid token exists, and persist the token back
to keychain (or file).

This module preserves backward-compatible names so that existing callers
(``gdrive/client.py``, ``gdrive/cli.py``) and tests continue to work
without changes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from deep_thought.secrets import (
    GOOGLE_OAUTH_SCOPES,
    GOOGLE_SERVICE,
    get_oauth_credentials,
    keychain_available,
)
from deep_thought.secrets import (
    _load_oauth_from_keychain as _shared_load_oauth,
)
from deep_thought.secrets import (
    _persist_oauth as _shared_persist,
)
from deep_thought.secrets import (
    _save_oauth_to_keychain as _shared_save_oauth,
)

if TYPE_CHECKING:
    from google.oauth2.credentials import Credentials


# ---------------------------------------------------------------------------
# Backward-compatible wrappers
# ---------------------------------------------------------------------------


def _keychain_available() -> bool:
    """Return True if a real keychain backend is available."""
    return keychain_available()


def _load_token_from_keychain(scopes: list[str]) -> Credentials | None:
    """Load OAuth credentials from the shared Google keychain entry."""
    return _shared_load_oauth(GOOGLE_SERVICE, scopes)


def _save_token_to_keychain(credentials: Credentials) -> None:
    """Persist OAuth credentials JSON to the shared Google keychain entry."""
    _shared_save_oauth(GOOGLE_SERVICE, credentials)


def _persist_credentials(credentials: Credentials, token_path: str, use_keychain: bool) -> None:
    """Save credentials to the appropriate storage backend."""
    _shared_persist(GOOGLE_SERVICE, credentials, token_path, use_keychain)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_credentials(credentials_path: str, token_path: str, scopes: list[str]) -> Credentials:
    """Load, refresh, or obtain OAuth 2.0 credentials for the Drive API.

    Delegates to the shared ``google`` token, requesting the full set of
    Google OAuth scopes so that a single keychain entry covers gmail, gcal,
    and gdrive.  The ``scopes`` parameter is accepted for backward
    compatibility but is not used — ``GOOGLE_OAUTH_SCOPES`` is always
    requested.

    See ``deep_thought.secrets.get_oauth_credentials`` for full behavior.

    Args:
        credentials_path: Path to the OAuth client secret JSON file
                          (downloaded from Google Cloud Console).
        token_path: File path used as the fallback token store when no keychain
                    backend is available. May be an empty string when keychain
                    is the only configured backend.
        scopes: Ignored. Present for backward compatibility only.

    Returns:
        A valid google.oauth2.credentials.Credentials object.

    Raises:
        FileNotFoundError: If ``credentials_path`` does not exist when a
                           browser consent flow is required.
        RuntimeError: If neither keychain nor token_file is available for
                      token storage.
        google.auth.exceptions.RefreshError: If a token refresh fails.
    """
    return get_oauth_credentials(
        GOOGLE_SERVICE,
        credentials_path,
        token_path,
        GOOGLE_OAUTH_SCOPES,
        required_scopes=GOOGLE_OAUTH_SCOPES,
    )
