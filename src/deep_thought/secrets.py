"""Shared secret storage with macOS Keychain priority and .env fallback.

Provides two APIs:

1. **Simple secrets** (API keys, tokens): ``get_secret()`` checks the system
   keychain first, then falls back to an environment variable (typically loaded
   from ``.env`` via python-dotenv).

2. **Google OAuth tokens**: ``get_oauth_credentials()`` manages the full token
   lifecycle — load from keychain (or file fallback), refresh if expired, run a
   browser consent flow if no valid token exists, and persist the result.

Storage priority (both APIs):
  1. macOS Keychain (via the ``keyring`` library) — used when a real backend is
     available.
  2. Environment variable / file on disk — used when no keychain backend is
     available (e.g., headless CI). Falls back silently with a log message.

Auto-migration: for OAuth tokens, if a file-based token exists and the keychain
is available but empty, the token is moved to the keychain and the file is
deleted automatically.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import keyring
import keyring.backends.fail
import keyring.errors
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)

_KEYRING_SERVICE_PREFIX = "deep-thought-"
_OAUTH_ACCOUNT = "oauth-token"


# ---------------------------------------------------------------------------
# Keychain availability
# ---------------------------------------------------------------------------


def keychain_available() -> bool:
    """Return True if a real keychain backend is available.

    Returns False when ``keyring`` resolves to the no-op fail backend, which
    happens in headless environments without a configured secrets store.
    Also returns False when ``DEEP_THOUGHT_NO_KEYCHAIN=1`` is set, which
    suppresses macOS keychain prompts in non-interactive contexts like git hooks.
    """
    if os.environ.get("DEEP_THOUGHT_NO_KEYCHAIN") == "1":
        return False
    return not isinstance(keyring.get_keyring(), keyring.backends.fail.Keyring)


# ---------------------------------------------------------------------------
# Simple secret API (API keys, tokens)
# ---------------------------------------------------------------------------


def _service_name(service: str) -> str:
    """Build the full keyring service name from a short tool identifier."""
    return f"{_KEYRING_SERVICE_PREFIX}{service}"


def get_secret(service: str, key_name: str, *, env_var: str | None = None) -> str:
    """Retrieve a secret, checking the system keychain first then the environment.

    Lookup order:
      1. If a real keychain backend is available, look up
         ``keyring.get_password("deep-thought-{service}", key_name)``.
      2. If ``env_var`` is provided, try ``os.environ.get(env_var)``.
      3. If both miss, raise ``OSError`` with an actionable message.

    Args:
        service: Short tool identifier (e.g., ``"todoist"``, ``"reddit"``).
        key_name: Account / key name within the service (e.g., ``"api-token"``).
        env_var: Optional environment variable name to check as a fallback.

    Returns:
        The secret value as a string.

    Raises:
        OSError: If the secret is not found in keychain or environment.
    """
    full_service = _service_name(service)

    if keychain_available():
        try:
            value = keyring.get_password(full_service, key_name)
            if value:
                logger.debug("Loaded secret from keychain (service=%s, key=%s).", full_service, key_name)
                return value
        except keyring.errors.KeyringLocked:
            logger.warning(
                "Keychain access denied (service=%s, key=%s). Falling back to environment.",
                full_service,
                key_name,
            )

    if env_var:
        value = os.environ.get(env_var)
        if value:
            logger.debug("Loaded secret from environment variable %s.", env_var)
            return value

    # Build an actionable error message.
    hint_parts: list[str] = [
        f"Secret not found for {full_service}/{key_name}.",
        "Store it in macOS Keychain with 'secrets set' or",
    ]
    if env_var:
        hint_parts.append(f"set the '{env_var}' environment variable (in your shell or .env file).")
    else:
        hint_parts.append("set the appropriate environment variable (in your shell or .env file).")
    raise OSError(" ".join(hint_parts))


def set_secret(service: str, key_name: str, value: str) -> None:
    """Store a secret in the system keychain.

    Args:
        service: Short tool identifier (e.g., ``"todoist"``).
        key_name: Account / key name within the service.
        value: The secret value to store.

    Raises:
        RuntimeError: If the keychain is unavailable or the write fails.
    """
    if not keychain_available():
        raise RuntimeError(
            "Keychain is not available (no backend or DEEP_THOUGHT_NO_KEYCHAIN=1). "
            "Cannot store secrets without a keychain."
        )
    full_service = _service_name(service)
    try:
        keyring.set_password(full_service, key_name, value)
    except (keyring.errors.PasswordSetError, keyring.errors.KeyringLocked) as exc:
        raise RuntimeError(
            f"Failed to save secret to keychain ({full_service}/{key_name}): {exc}. Your keychain may be locked."
        ) from exc
    logger.debug("Secret saved to keychain (service=%s, key=%s).", full_service, key_name)


def delete_secret(service: str, key_name: str) -> None:
    """Remove a secret from the system keychain.

    No error is raised if the secret does not exist.

    Args:
        service: Short tool identifier (e.g., ``"todoist"``).
        key_name: Account / key name within the service.

    Raises:
        RuntimeError: If the keychain is not available.
    """
    if not keychain_available():
        raise RuntimeError(
            "Keychain is not available (no backend or DEEP_THOUGHT_NO_KEYCHAIN=1). "
            "Cannot delete secrets without a keychain."
        )
    full_service = _service_name(service)
    try:
        keyring.delete_password(full_service, key_name)
        logger.debug("Secret deleted from keychain (service=%s, key=%s).", full_service, key_name)
    except (keyring.errors.PasswordDeleteError, keyring.errors.KeyringLocked):
        logger.debug("No secret to delete in keychain (service=%s, key=%s).", full_service, key_name)


# ---------------------------------------------------------------------------
# OAuth token helpers
# ---------------------------------------------------------------------------


def _load_oauth_from_keychain(service: str, scopes: list[str]) -> Credentials | None:
    """Load OAuth credentials from the keychain.

    Args:
        service: Short tool identifier (e.g., ``"gmail"``).
        scopes: OAuth scope URIs used to initialise the credentials object.

    Returns:
        A Credentials object if a token is found, or None.
    """
    full_service = _service_name(service)
    try:
        token_json = keyring.get_password(full_service, _OAUTH_ACCOUNT)
    except keyring.errors.KeyringLocked:
        logger.warning("Keychain access denied loading OAuth token (service=%s).", full_service)
        return None
    if token_json is None:
        logger.debug("No OAuth token found in keychain (service=%s).", full_service)
        return None

    try:
        token_data = json.loads(token_json)
    except json.JSONDecodeError:
        logger.warning(
            "OAuth token in keychain is corrupt and cannot be parsed (service=%s). "
            "Run the tool's auth command to re-authorize.",
            full_service,
        )
        return None

    logger.debug("Loaded OAuth token from keychain (service=%s).", full_service)
    return Credentials.from_authorized_user_info(token_data, scopes)  # type: ignore[no-untyped-call, no-any-return]


def _save_oauth_to_keychain(service: str, credentials: Credentials) -> None:
    """Persist OAuth credentials JSON to the keychain.

    Args:
        service: Short tool identifier.
        credentials: The credentials to serialise and store.

    Raises:
        RuntimeError: If the keychain write fails.
    """
    full_service = _service_name(service)
    try:
        keyring.set_password(full_service, _OAUTH_ACCOUNT, credentials.to_json())  # type: ignore[no-untyped-call]
    except (keyring.errors.PasswordSetError, keyring.errors.KeyringLocked) as exc:
        raise RuntimeError(
            f"Failed to save OAuth token to keychain ({full_service}): {exc}. "
            "Your keychain may be locked. Unlock it and run the tool's auth command to re-authorize."
        ) from exc
    logger.debug("OAuth token saved to keychain (service=%s).", full_service)


def _save_oauth_to_file(credentials: Credentials, token_path: Path) -> None:
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


def _persist_oauth(service: str, credentials: Credentials, token_path: str, use_keychain: bool) -> None:
    """Save OAuth credentials to the appropriate storage backend.

    Args:
        service: Short tool identifier.
        credentials: The credentials to persist.
        token_path: File path used when keychain is not available. May be an
                    empty string when keychain is the only configured backend.
        use_keychain: Whether to write to the keychain.

    Raises:
        RuntimeError: If keychain is unavailable and no token_path is set.
    """
    if use_keychain:
        try:
            _save_oauth_to_keychain(service, credentials)
            return
        except (keyring.errors.KeyringLocked, RuntimeError):
            logger.warning("Keychain write denied (service=%s). Falling back to file-based token.", service)
    if token_path:
        _save_oauth_to_file(credentials, Path(token_path))
    else:
        raise RuntimeError(
            "No token storage available: keychain is not accessible and "
            "no token file path is configured. Either configure a keychain "
            "backend or set the token file path in the configuration."
        )


def get_oauth_credentials(
    service: str,
    credentials_path: str,
    token_path: str,
    scopes: list[str],
) -> Credentials:
    """Load, refresh, or obtain OAuth 2.0 credentials.

    Attempts operations in this order:
    1. Load an existing token from the keychain (if a real backend is available).
       - If the keychain has no token but a token file exists, auto-migrate the
         file token to the keychain and delete the file.
    2. If no keychain backend is available, load from ``token_path`` on disk.
    3. If the token is expired but has a refresh token, refresh it silently.
    4. If no valid token exists, open a browser window for user consent.
    5. Persist the (new or refreshed) token via the appropriate backend.

    Args:
        service: Short tool identifier (e.g., ``"gmail"``, ``"gcal"``, ``"gdrive"``).
        credentials_path: Path to the OAuth client secret JSON file
                          (downloaded from Google Cloud Console).
        token_path: File path used as the fallback token store when no keychain
                    backend is available. May be an empty string when keychain
                    is the only configured backend.
        scopes: List of OAuth scope URIs to request.

    Returns:
        A valid google.oauth2.credentials.Credentials object.

    Raises:
        FileNotFoundError: If ``credentials_path`` does not exist when a
                           browser consent flow is required.
        RuntimeError: If neither keychain nor token_path is available for
                      token storage.
        google.auth.exceptions.RefreshError: If a token refresh fails.
    """
    use_keychain = keychain_available()
    if use_keychain:
        logger.debug("Keychain backend available — using keychain for token storage (service=%s).", service)
    else:
        logger.debug("No keychain backend — using file-based token storage (service=%s).", service)

    existing_credentials: Credentials | None = None
    resolved_token_path = Path(token_path) if token_path else None
    migrated_file_to_delete: Path | None = None  # Set during auto-migration; deleted after validation.

    if use_keychain:
        try:
            existing_credentials = _load_oauth_from_keychain(service, scopes)
        except keyring.errors.KeyringLocked:
            logger.warning("Keychain access denied (service=%s). Falling back to file-based token.", service)
            use_keychain = False
            existing_credentials = None

        # Auto-migrate: file token present but keychain is empty → move it over.
        if (
            use_keychain
            and existing_credentials is None
            and resolved_token_path is not None
            and resolved_token_path.exists()
        ):
            logger.info("Migrating OAuth token from file to keychain (service=%s): %s", service, resolved_token_path)
            try:
                existing_credentials = Credentials.from_authorized_user_file(  # type: ignore[no-untyped-call]
                    str(resolved_token_path), scopes
                )
            except (ValueError, json.JSONDecodeError):
                logger.warning(
                    "Token file is corrupt (service=%s, path=%s). Ignoring file.",
                    service,
                    resolved_token_path,
                )
                existing_credentials = None
            if existing_credentials is not None:
                try:
                    _save_oauth_to_keychain(service, existing_credentials)
                    # Defer file deletion until after credential validation succeeds.
                    migrated_file_to_delete = resolved_token_path
                    logger.info("Token migrated to keychain (service=%s).", service)
                except (keyring.errors.KeyringLocked, RuntimeError):
                    logger.warning("Keychain write denied during migration (service=%s). Keeping file token.", service)
                    use_keychain = False
    else:
        if resolved_token_path is not None and resolved_token_path.exists():
            existing_credentials = Credentials.from_authorized_user_file(  # type: ignore[no-untyped-call]
                str(resolved_token_path), scopes
            )
            logger.debug("Loaded existing OAuth token from %s", resolved_token_path)

    if existing_credentials is not None and existing_credentials.valid:
        if migrated_file_to_delete is not None:
            migrated_file_to_delete.unlink(missing_ok=True)
            logger.info("Migrated token file deleted: %s", migrated_file_to_delete)
        return existing_credentials

    if existing_credentials is not None and existing_credentials.expired and existing_credentials.refresh_token:
        logger.debug("Refreshing expired OAuth token (service=%s).", service)
        existing_credentials.refresh(Request())
        _persist_oauth(service, existing_credentials, token_path, use_keychain)
        if migrated_file_to_delete is not None:
            migrated_file_to_delete.unlink(missing_ok=True)
            logger.info("Migrated token file deleted: %s", migrated_file_to_delete)
        return existing_credentials

    # No valid token — run the interactive browser consent flow.
    if os.environ.get("DEEP_THOUGHT_NO_KEYCHAIN") == "1":
        raise RuntimeError(
            f"No valid OAuth token available for service '{service}' and interactive browser "
            "auth is disabled (DEEP_THOUGHT_NO_KEYCHAIN=1). "
            "Run the tool's auth command interactively first to obtain a token."
        )

    resolved_credentials_path = Path(credentials_path)
    if not resolved_credentials_path.exists():
        raise FileNotFoundError(
            f"OAuth client secret not found at {credentials_path}. "
            "Download credentials.json from Google Cloud Console and place it at the configured path."
        )

    logger.info("Starting OAuth browser flow for user consent (service=%s).", service)
    flow = InstalledAppFlow.from_client_secrets_file(str(resolved_credentials_path), scopes)
    new_credentials: Credentials = flow.run_local_server(port=0)

    _persist_oauth(service, new_credentials, token_path, use_keychain)
    return new_credentials
