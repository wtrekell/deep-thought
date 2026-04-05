"""OAuth 2.0 token management for the GDrive Tool.

Provides a single public function, get_credentials(), which handles the full
token lifecycle: load from keychain (or file fallback), refresh if expired,
run browser consent flow if no valid token exists, and persist the token back
to keychain (or file).

Storage priority:
  1. macOS Keychain (via the ``keyring`` library) — used when a real backend is
     available.
  2. File on disk (``token_path``) — used when no keychain backend is available
     (e.g., headless CI). Falls back silently with a log message.

Auto-migration: on first run after upgrading to keychain support, if a
file-based token exists and the keychain is available, the token is moved to
the keychain and the file is deleted automatically.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import keyring
import keyring.backends.fail
import keyring.errors
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)

_KEYRING_SERVICE = "deep-thought-gdrive"
_KEYRING_ACCOUNT = "oauth-token"


# ---------------------------------------------------------------------------
# Keychain helpers
# ---------------------------------------------------------------------------


def _keychain_available() -> bool:
    """Return True if a real keychain backend is available.

    Returns False when ``keyring`` resolves to the no-op fail backend, which
    happens in headless environments without a configured secrets store.
    """
    return not isinstance(keyring.get_keyring(), keyring.backends.fail.Keyring)


def _load_token_from_keychain(scopes: list[str]) -> Credentials | None:
    """Load OAuth credentials from the keychain.

    Args:
        scopes: OAuth scope URIs used to initialise the credentials object.

    Returns:
        A Credentials object if a token is found, or None if the keychain
        has no entry for this service/account pair.
    """
    token_json = keyring.get_password(_KEYRING_SERVICE, _KEYRING_ACCOUNT)
    if token_json is None:
        logger.debug("No OAuth token found in keychain (service=%s, account=%s).", _KEYRING_SERVICE, _KEYRING_ACCOUNT)
        return None

    try:
        token_data = json.loads(token_json)
    except json.JSONDecodeError:
        logger.warning(
            "OAuth token in keychain is corrupt and cannot be parsed. "
            "Run 'gdrive auth' to re-authorize and replace the stored token."
        )
        return None

    logger.debug("Loaded OAuth token from keychain (service=%s, account=%s).", _KEYRING_SERVICE, _KEYRING_ACCOUNT)
    return Credentials.from_authorized_user_info(token_data, scopes)  # type: ignore[no-untyped-call, no-any-return]


def _save_token_to_keychain(credentials: Credentials) -> None:
    """Persist OAuth credentials JSON to the keychain.

    Args:
        credentials: The credentials to serialise and store.
    """
    try:
        keyring.set_password(_KEYRING_SERVICE, _KEYRING_ACCOUNT, credentials.to_json())  # type: ignore[no-untyped-call]
    except keyring.errors.PasswordSetError as exc:
        raise RuntimeError(
            f"Failed to save OAuth token to keychain: {exc}. "
            "Your keychain may be locked. Unlock it and run 'gdrive auth' to re-authorize."
        ) from exc
    logger.debug("OAuth token saved to keychain (service=%s, account=%s).", _KEYRING_SERVICE, _KEYRING_ACCOUNT)


# ---------------------------------------------------------------------------
# File helpers (fallback path)
# ---------------------------------------------------------------------------


def _save_token(credentials: Credentials, token_path: Path) -> None:
    """Persist OAuth credentials to disk, restricted to owner-read only.

    Args:
        credentials: The credentials object to serialise as JSON.
        token_path: The file path to write the token to.
    """
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(credentials.to_json())  # type: ignore[no-untyped-call]
    # chmod(0o600) restricts access to the owner only on POSIX systems.
    # This call is a no-op on Windows — a known platform limitation.
    token_path.chmod(0o600)
    logger.debug("OAuth token saved to %s", token_path)


# ---------------------------------------------------------------------------
# Persistence router
# ---------------------------------------------------------------------------


def _persist_credentials(credentials: Credentials, token_path: str, use_keychain: bool) -> None:
    """Save credentials to the appropriate storage backend.

    Args:
        credentials: The credentials to persist.
        token_path: File path used when keychain is not available. May be an
                    empty string when keychain is the only configured backend.
        use_keychain: Whether to write to the keychain.

    Raises:
        RuntimeError: If keychain is unavailable and no token_file path is set.
    """
    if use_keychain:
        _save_token_to_keychain(credentials)
    elif token_path:
        _save_token(credentials, Path(token_path))
    else:
        raise RuntimeError(
            "No token storage available: keychain is not accessible and "
            "auth.token_file is not configured. Either configure a keychain "
            "backend or set auth.token_file in the configuration."
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_credentials(credentials_path: str, token_path: str, scopes: list[str]) -> Credentials:
    """Load, refresh, or obtain OAuth 2.0 credentials for the Drive API.

    Attempts operations in this order:
    1. Load an existing token from the keychain (if a real backend is available).
       - If the keychain has no token but a token file exists, auto-migrate the
         file token to the keychain and delete the file.
    2. If no keychain backend is available, load from ``token_path`` on disk.
    3. If the token is expired but has a refresh token, refresh it silently.
    4. If no valid token exists, open a browser window for user consent.
    5. Persist the (new or refreshed) token via the appropriate backend.

    Args:
        credentials_path: Path to the OAuth client secret JSON file
                          (downloaded from Google Cloud Console).
        token_path: File path used as the fallback token store when no keychain
                    backend is available. May be an empty string when keychain
                    is the only configured backend.
        scopes: List of OAuth scope URIs to request (e.g. drive.file).

    Returns:
        A valid google.oauth2.credentials.Credentials object.

    Raises:
        FileNotFoundError: If ``credentials_path`` does not exist when a
                           browser consent flow is required.
        RuntimeError: If neither keychain nor token_file is available for
                      token storage.
        google.auth.exceptions.RefreshError: If a token refresh fails.
    """
    use_keychain = _keychain_available()
    if use_keychain:
        logger.debug("Keychain backend available — using keychain for token storage.")
    else:
        logger.debug("No keychain backend available — using file-based token storage.")

    existing_credentials: Credentials | None = None
    resolved_token_path = Path(token_path) if token_path else None

    if use_keychain:
        existing_credentials = _load_token_from_keychain(scopes)

        # Auto-migrate: file token present but keychain is empty → move it over.
        if existing_credentials is None and resolved_token_path is not None and resolved_token_path.exists():
            logger.info("Migrating OAuth token from file to keychain: %s", resolved_token_path)
            existing_credentials = Credentials.from_authorized_user_file(  # type: ignore[no-untyped-call]
                str(resolved_token_path), scopes
            )
            if existing_credentials is not None:
                _save_token_to_keychain(existing_credentials)
                # Keychain write succeeded — delete the file. If the process is
                # interrupted here, the file is left as an orphan, but the keychain
                # already holds the current token so there is no data loss.
                resolved_token_path.unlink()
                logger.info("Token migrated to keychain. File deleted: %s", resolved_token_path)
    else:
        if resolved_token_path is not None and resolved_token_path.exists():
            existing_credentials = Credentials.from_authorized_user_file(  # type: ignore[no-untyped-call]
                str(resolved_token_path), scopes
            )
            logger.debug("Loaded existing OAuth token from %s", resolved_token_path)

    if existing_credentials is not None and existing_credentials.valid:
        return existing_credentials

    if existing_credentials is not None and existing_credentials.expired and existing_credentials.refresh_token:
        logger.debug("Refreshing expired OAuth token.")
        existing_credentials.refresh(Request())
        _persist_credentials(existing_credentials, token_path, use_keychain)
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

    _persist_credentials(new_credentials, token_path, use_keychain)
    return new_credentials
