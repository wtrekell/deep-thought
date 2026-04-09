"""Tests for deep_thought.gdrive._auth — keychain and file token storage.

After the refactor to use the shared ``deep_thought.secrets`` module, the
GDrive ``_auth`` module is a thin wrapper. Tests patch the shared module
where the real logic lives.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from deep_thought.gdrive._auth import (
    _keychain_available,
    _persist_credentials,
    get_credentials,
)
from deep_thought.secrets import _KEYRING_SERVICE_PREFIX, _OAUTH_ACCOUNT

_KEYRING_SERVICE = f"{_KEYRING_SERVICE_PREFIX}gdrive"
_KEYRING_ACCOUNT = _OAUTH_ACCOUNT

if TYPE_CHECKING:
    from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SCOPES = ["https://www.googleapis.com/auth/drive.file"]

_FAKE_TOKEN_JSON = json.dumps(
    {
        "token": "fake-access-token",
        "refresh_token": "fake-refresh-token",
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": "fake-client-id",
        "client_secret": "fake-client-secret",
        "scopes": _SCOPES,
    }
)


def _make_valid_credentials() -> MagicMock:
    """Return a mock Credentials object that is valid and not expired."""
    creds = MagicMock()
    creds.valid = True
    creds.expired = False
    creds.refresh_token = "fake-refresh-token"
    creds.to_json.return_value = _FAKE_TOKEN_JSON
    return creds


def _make_expired_credentials() -> MagicMock:
    """Return a mock Credentials object that is expired but has a refresh token."""
    creds = MagicMock()
    creds.valid = False
    creds.expired = True
    creds.refresh_token = "fake-refresh-token"
    creds.to_json.return_value = _FAKE_TOKEN_JSON
    return creds


# ---------------------------------------------------------------------------
# _keychain_available
# ---------------------------------------------------------------------------


def test_keychain_available_returns_true_for_real_backend() -> None:
    """_keychain_available() returns True when the active backend is not FailKeyring."""

    real_backend = MagicMock()  # Not an instance of FailKeyring

    with patch("deep_thought.secrets.keyring.get_keyring", return_value=real_backend):
        result = _keychain_available()

    assert result is True


def test_keychain_available_returns_false_for_fail_backend() -> None:
    """_keychain_available() returns False when the active backend is FailKeyring."""
    import keyring.backends.fail

    fail_backend = keyring.backends.fail.Keyring()

    with patch("deep_thought.secrets.keyring.get_keyring", return_value=fail_backend):
        result = _keychain_available()

    assert result is False


# ---------------------------------------------------------------------------
# _persist_credentials
# ---------------------------------------------------------------------------


def test_persist_credentials_saves_to_keychain_when_available() -> None:
    """_persist_credentials routes to keychain when use_keychain is True."""
    creds = _make_valid_credentials()

    with patch("deep_thought.secrets.keyring.set_password") as mock_set_password:
        _persist_credentials(creds, token_path="", use_keychain=True)

    mock_set_password.assert_called_once_with(_KEYRING_SERVICE, _KEYRING_ACCOUNT, _FAKE_TOKEN_JSON)


def test_persist_credentials_saves_to_file_when_keychain_unavailable(tmp_path: Path) -> None:
    """_persist_credentials writes to disk when use_keychain is False."""
    token_file = tmp_path / "token.json"
    creds = _make_valid_credentials()

    _persist_credentials(creds, token_path=str(token_file), use_keychain=False)

    assert token_file.exists()
    assert token_file.read_text() == _FAKE_TOKEN_JSON
    assert oct(token_file.stat().st_mode)[-3:] == "600"


def test_persist_credentials_raises_when_no_storage_available() -> None:
    """_persist_credentials raises RuntimeError when keychain is off and token_path is empty."""
    creds = _make_valid_credentials()

    with pytest.raises(RuntimeError, match="No token storage available"):
        _persist_credentials(creds, token_path="", use_keychain=False)


# ---------------------------------------------------------------------------
# get_credentials — keychain path
# ---------------------------------------------------------------------------


def test_get_credentials_loads_valid_token_from_keychain() -> None:
    """get_credentials returns immediately when a valid token is in the keychain."""
    valid_creds = _make_valid_credentials()

    with (
        patch("deep_thought.secrets.keychain_available", return_value=True),
        patch("deep_thought.secrets._load_oauth_from_keychain", return_value=valid_creds),
    ):
        result = get_credentials("/fake/credentials.json", "", _SCOPES)

    assert result is valid_creds


def test_get_credentials_refreshes_expired_keychain_token() -> None:
    """get_credentials refreshes an expired token and re-saves it to the keychain."""
    expired_creds = _make_expired_credentials()

    with (
        patch("deep_thought.secrets.keychain_available", return_value=True),
        patch("deep_thought.secrets._load_oauth_from_keychain", return_value=expired_creds),
        patch("deep_thought.secrets.Request"),
        patch("deep_thought.secrets._save_oauth_to_keychain") as mock_save,
    ):
        result = get_credentials("/fake/credentials.json", "", _SCOPES)

    expired_creds.refresh.assert_called_once()
    mock_save.assert_called_once_with("gdrive", expired_creds)
    assert result is expired_creds


# ---------------------------------------------------------------------------
# get_credentials — auto-migration
# ---------------------------------------------------------------------------


def test_get_credentials_auto_migrates_file_token_to_keychain(tmp_path: Path) -> None:
    """When keychain is available but empty, a file token is migrated to keychain and the file deleted."""
    token_file = tmp_path / "token.json"
    token_file.write_text(_FAKE_TOKEN_JSON)
    token_file.chmod(0o600)

    valid_creds = _make_valid_credentials()

    with (
        patch("deep_thought.secrets.keychain_available", return_value=True),
        patch("deep_thought.secrets._load_oauth_from_keychain", return_value=None),
        patch("deep_thought.secrets.Credentials") as mock_creds_cls,
        patch("deep_thought.secrets._save_oauth_to_keychain") as mock_save,
    ):
        mock_creds_cls.from_authorized_user_file.return_value = valid_creds
        result = get_credentials("/fake/credentials.json", str(token_file), _SCOPES)

    mock_save.assert_called_once_with("gdrive", valid_creds)
    assert not token_file.exists(), "File should have been deleted after migration."
    assert result is valid_creds


# ---------------------------------------------------------------------------
# get_credentials — file fallback path
# ---------------------------------------------------------------------------


def test_get_credentials_falls_back_to_file_when_keychain_unavailable(tmp_path: Path) -> None:
    """When no keychain backend is available, get_credentials loads from token_file."""
    token_file = tmp_path / "token.json"
    token_file.write_text(_FAKE_TOKEN_JSON)

    valid_creds = _make_valid_credentials()

    with (
        patch("deep_thought.secrets.keychain_available", return_value=False),
        patch("deep_thought.secrets.Credentials") as mock_creds_cls,
    ):
        mock_creds_cls.from_authorized_user_file.return_value = valid_creds
        result = get_credentials("/fake/credentials.json", str(token_file), _SCOPES)

    assert result is valid_creds
    mock_creds_cls.from_authorized_user_file.assert_called_once_with(str(token_file), _SCOPES)


# ---------------------------------------------------------------------------
# get_credentials — browser consent flow
# ---------------------------------------------------------------------------


def test_get_credentials_runs_browser_flow_when_no_token_exists(tmp_path: Path) -> None:
    """get_credentials runs the browser consent flow when no token exists in keychain or file."""
    credentials_file = tmp_path / "credentials.json"
    credentials_file.write_text('{"installed": {}}')

    new_creds = _make_valid_credentials()

    with (
        patch("deep_thought.secrets.keychain_available", return_value=True),
        patch("deep_thought.secrets._load_oauth_from_keychain", return_value=None),
        patch("deep_thought.secrets.InstalledAppFlow") as mock_flow_cls,
        patch("deep_thought.secrets._save_oauth_to_keychain") as mock_save,
    ):
        mock_flow = MagicMock()
        mock_flow.run_local_server.return_value = new_creds
        mock_flow_cls.from_client_secrets_file.return_value = mock_flow

        result = get_credentials(str(credentials_file), "", _SCOPES)

    mock_flow.run_local_server.assert_called_once_with(port=0)
    mock_save.assert_called_once_with("gdrive", new_creds)
    assert result is new_creds


def test_get_credentials_raises_if_credentials_file_missing() -> None:
    """get_credentials raises FileNotFoundError when the credentials file is absent."""
    with (
        patch("deep_thought.secrets.keychain_available", return_value=True),
        patch("deep_thought.secrets._load_oauth_from_keychain", return_value=None),
        pytest.raises(FileNotFoundError, match="OAuth client secret not found"),
    ):
        get_credentials("/nonexistent/credentials.json", "", _SCOPES)


def test_get_credentials_raises_when_no_keychain_and_no_token(tmp_path: Path) -> None:
    """In non-interactive mode, get_credentials raises instead of opening a browser."""
    with (
        patch.dict("os.environ", {"DEEP_THOUGHT_NO_KEYCHAIN": "1"}),
        patch("deep_thought.secrets.InstalledAppFlow") as mock_flow_cls,
        pytest.raises(RuntimeError, match="interactive browser auth is disabled"),
    ):
        get_credentials("/fake/credentials.json", str(tmp_path / "missing-token.json"), _SCOPES)

    mock_flow_cls.from_client_secrets_file.assert_not_called()


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


def test_save_token_to_keychain_raises_runtime_error_on_password_set_error() -> None:
    """_save_token_to_keychain raises RuntimeError with an actionable message when keychain is locked."""
    import keyring.errors

    from deep_thought.gdrive._auth import _save_token_to_keychain

    creds = _make_valid_credentials()

    with (
        patch("deep_thought.secrets.keyring.set_password", side_effect=keyring.errors.PasswordSetError),
        pytest.raises(RuntimeError, match="Failed to save OAuth token"),
    ):
        _save_token_to_keychain(creds)


def test_load_token_from_keychain_returns_none_on_corrupt_json() -> None:
    """_load_token_from_keychain returns None and logs a warning when keychain JSON is malformed."""
    from deep_thought.gdrive._auth import _load_token_from_keychain

    with patch("deep_thought.secrets.keyring.get_password", return_value="not valid json {{{"):
        result = _load_token_from_keychain(_SCOPES)

    assert result is None


def test_get_credentials_migration_skipped_when_keychain_write_fails(tmp_path: Path) -> None:
    """If keychain write fails during migration, the file is preserved and fallback to file is used."""
    import keyring.errors

    token_file = tmp_path / "token.json"
    token_file.write_text(_FAKE_TOKEN_JSON)

    valid_creds = _make_valid_credentials()

    with (
        patch("deep_thought.secrets.keychain_available", return_value=True),
        patch("deep_thought.secrets._load_oauth_from_keychain", return_value=None),
        patch("deep_thought.secrets.Credentials") as mock_creds_cls,
        patch(
            "deep_thought.secrets.keyring.set_password",
            side_effect=keyring.errors.PasswordSetError,
        ),
    ):
        mock_creds_cls.from_authorized_user_file.return_value = valid_creds
        result = get_credentials("/fake/credentials.json", str(token_file), _SCOPES)

    # File must still exist — keychain write failed, so file token is kept.
    assert token_file.exists(), "Token file should be preserved when keychain write fails."
    assert result is valid_creds
