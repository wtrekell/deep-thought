"""Tests for deep_thought.secrets — shared keychain + env-var secret storage."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from deep_thought.secrets import (
    _KEYRING_SERVICE_PREFIX,
    delete_secret,
    get_oauth_credentials,
    get_secret,
    keychain_available,
    set_secret,
)

if TYPE_CHECKING:
    from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SCOPES = ["https://www.googleapis.com/auth/calendar"]

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
# keychain_available
# ---------------------------------------------------------------------------


def test_keychain_available_returns_true_for_real_backend() -> None:
    """keychain_available() returns True when the active backend is not FailKeyring."""
    real_backend = MagicMock()
    with patch("deep_thought.secrets.keyring.get_keyring", return_value=real_backend):
        assert keychain_available() is True


def test_keychain_available_returns_false_for_fail_backend() -> None:
    """keychain_available() returns False when the active backend is FailKeyring."""
    import keyring.backends.fail

    fail_backend = keyring.backends.fail.Keyring()
    with patch("deep_thought.secrets.keyring.get_keyring", return_value=fail_backend):
        assert keychain_available() is False


# ---------------------------------------------------------------------------
# get_secret — keychain path
# ---------------------------------------------------------------------------


def test_get_secret_returns_from_keychain_when_available() -> None:
    """get_secret returns the keychain value when it exists."""
    with (
        patch("deep_thought.secrets.keychain_available", return_value=True),
        patch("deep_thought.secrets.keyring.get_password", return_value="keychain-value"),
    ):
        result = get_secret("todoist", "api-token", env_var="TODOIST_API_TOKEN")

    assert result == "keychain-value"


def test_get_secret_prefers_keychain_over_env_var() -> None:
    """get_secret uses keychain even when env var is also set."""
    with (
        patch("deep_thought.secrets.keychain_available", return_value=True),
        patch("deep_thought.secrets.keyring.get_password", return_value="keychain-value"),
        patch.dict("os.environ", {"MY_TOKEN": "env-value"}),
    ):
        result = get_secret("test", "token", env_var="MY_TOKEN")

    assert result == "keychain-value"


# ---------------------------------------------------------------------------
# get_secret — env var fallback
# ---------------------------------------------------------------------------


def test_get_secret_falls_back_to_env_var_when_keychain_unavailable() -> None:
    """get_secret uses the env var when no keychain backend is available."""
    with (
        patch("deep_thought.secrets.keychain_available", return_value=False),
        patch.dict("os.environ", {"TODOIST_API_TOKEN": "env-value"}),
    ):
        result = get_secret("todoist", "api-token", env_var="TODOIST_API_TOKEN")

    assert result == "env-value"


def test_get_secret_falls_back_to_env_var_when_keychain_empty() -> None:
    """get_secret uses env var when keychain is available but has no entry."""
    with (
        patch("deep_thought.secrets.keychain_available", return_value=True),
        patch("deep_thought.secrets.keyring.get_password", return_value=None),
        patch.dict("os.environ", {"TODOIST_API_TOKEN": "env-value"}),
    ):
        result = get_secret("todoist", "api-token", env_var="TODOIST_API_TOKEN")

    assert result == "env-value"


# ---------------------------------------------------------------------------
# get_secret — error path
# ---------------------------------------------------------------------------


def test_get_secret_raises_when_both_miss() -> None:
    """get_secret raises OSError when keychain and env var are both empty."""
    with (
        patch("deep_thought.secrets.keychain_available", return_value=True),
        patch("deep_thought.secrets.keyring.get_password", return_value=None),
        patch.dict("os.environ", {}, clear=True),
        pytest.raises(OSError, match="Secret not found"),
    ):
        get_secret("todoist", "api-token", env_var="TODOIST_API_TOKEN")


def test_get_secret_raises_when_no_keychain_and_no_env_var() -> None:
    """get_secret raises OSError when keychain is unavailable and no env var name given."""
    with (
        patch("deep_thought.secrets.keychain_available", return_value=False),
        pytest.raises(OSError, match="Secret not found"),
    ):
        get_secret("todoist", "api-token")


def test_get_secret_error_message_includes_env_var_name() -> None:
    """The OSError message includes the env var name for discoverability."""
    with (
        patch("deep_thought.secrets.keychain_available", return_value=False),
        patch.dict("os.environ", {}, clear=True),
        pytest.raises(OSError, match="TODOIST_API_TOKEN"),
    ):
        get_secret("todoist", "api-token", env_var="TODOIST_API_TOKEN")


# ---------------------------------------------------------------------------
# set_secret
# ---------------------------------------------------------------------------


def test_set_secret_writes_to_keychain() -> None:
    """set_secret calls keyring.set_password with the correct service name."""
    with (
        patch("deep_thought.secrets.keychain_available", return_value=True),
        patch("deep_thought.secrets.keyring.set_password") as mock_set,
    ):
        set_secret("todoist", "api-token", "my-secret-value")

    mock_set.assert_called_once_with(f"{_KEYRING_SERVICE_PREFIX}todoist", "api-token", "my-secret-value")


def test_set_secret_raises_runtime_error_on_failure() -> None:
    """set_secret raises RuntimeError when keychain write fails."""
    import keyring.errors

    with (
        patch("deep_thought.secrets.keychain_available", return_value=True),
        patch("deep_thought.secrets.keyring.set_password", side_effect=keyring.errors.PasswordSetError),
        pytest.raises(RuntimeError, match="Failed to save secret"),
    ):
        set_secret("todoist", "api-token", "value")


# ---------------------------------------------------------------------------
# delete_secret
# ---------------------------------------------------------------------------


def test_delete_secret_removes_from_keychain() -> None:
    """delete_secret calls keyring.delete_password."""
    with (
        patch("deep_thought.secrets.keychain_available", return_value=True),
        patch("deep_thought.secrets.keyring.delete_password") as mock_del,
    ):
        delete_secret("todoist", "api-token")

    mock_del.assert_called_once_with(f"{_KEYRING_SERVICE_PREFIX}todoist", "api-token")


def test_delete_secret_does_not_raise_when_missing() -> None:
    """delete_secret silently ignores PasswordDeleteError."""
    import keyring.errors

    with (
        patch("deep_thought.secrets.keychain_available", return_value=True),
        patch(
            "deep_thought.secrets.keyring.delete_password",
            side_effect=keyring.errors.PasswordDeleteError,
        ),
    ):
        delete_secret("todoist", "api-token")  # Should not raise


# ---------------------------------------------------------------------------
# get_oauth_credentials — keychain path
# ---------------------------------------------------------------------------


def test_oauth_loads_valid_token_from_keychain() -> None:
    """get_oauth_credentials returns immediately when a valid token is in keychain."""
    valid_creds = _make_valid_credentials()

    with (
        patch("deep_thought.secrets.keychain_available", return_value=True),
        patch("deep_thought.secrets._load_oauth_from_keychain", return_value=valid_creds),
    ):
        result = get_oauth_credentials("gmail", "/fake/creds.json", "", _SCOPES)

    assert result is valid_creds


def test_oauth_refreshes_expired_keychain_token() -> None:
    """get_oauth_credentials refreshes an expired token and re-saves to keychain."""
    expired_creds = _make_expired_credentials()

    with (
        patch("deep_thought.secrets.keychain_available", return_value=True),
        patch("deep_thought.secrets._load_oauth_from_keychain", return_value=expired_creds),
        patch("deep_thought.secrets.Request"),
        patch("deep_thought.secrets._save_oauth_to_keychain") as mock_save,
    ):
        result = get_oauth_credentials("gmail", "/fake/creds.json", "", _SCOPES)

    expired_creds.refresh.assert_called_once()
    mock_save.assert_called_once_with("gmail", expired_creds)
    assert result is expired_creds


# ---------------------------------------------------------------------------
# get_oauth_credentials — auto-migration
# ---------------------------------------------------------------------------


def test_oauth_auto_migrates_file_token_to_keychain(tmp_path: Path) -> None:
    """When keychain is available but empty, file token is migrated and file deleted."""
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
        result = get_oauth_credentials("gcal", "/fake/creds.json", str(token_file), _SCOPES)

    mock_save.assert_called_once_with("gcal", valid_creds)
    assert not token_file.exists(), "File should be deleted after migration."
    assert result is valid_creds


# ---------------------------------------------------------------------------
# get_oauth_credentials — file fallback
# ---------------------------------------------------------------------------


def test_oauth_falls_back_to_file_when_keychain_unavailable(tmp_path: Path) -> None:
    """When no keychain backend is available, loads token from file."""
    token_file = tmp_path / "token.json"
    token_file.write_text(_FAKE_TOKEN_JSON)

    valid_creds = _make_valid_credentials()

    with (
        patch("deep_thought.secrets.keychain_available", return_value=False),
        patch("deep_thought.secrets.Credentials") as mock_creds_cls,
    ):
        mock_creds_cls.from_authorized_user_file.return_value = valid_creds
        result = get_oauth_credentials("gcal", "/fake/creds.json", str(token_file), _SCOPES)

    assert result is valid_creds


# ---------------------------------------------------------------------------
# get_oauth_credentials — browser flow
# ---------------------------------------------------------------------------


def test_oauth_runs_browser_flow_when_no_token_exists(tmp_path: Path) -> None:
    """get_oauth_credentials runs browser consent flow when no token exists."""
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

        result = get_oauth_credentials("gmail", str(credentials_file), "", _SCOPES)

    mock_flow.run_local_server.assert_called_once_with(port=0)
    mock_save.assert_called_once_with("gmail", new_creds)
    assert result is new_creds


def test_oauth_raises_if_credentials_file_missing() -> None:
    """get_oauth_credentials raises FileNotFoundError when credentials file is absent."""
    with (
        patch("deep_thought.secrets.keychain_available", return_value=True),
        patch("deep_thought.secrets._load_oauth_from_keychain", return_value=None),
        pytest.raises(FileNotFoundError, match="OAuth client secret not found"),
    ):
        get_oauth_credentials("gmail", "/nonexistent/creds.json", "", _SCOPES)


# ---------------------------------------------------------------------------
# _persist_oauth
# ---------------------------------------------------------------------------


def test_persist_oauth_saves_to_file_with_correct_permissions(tmp_path: Path) -> None:
    """_persist_oauth writes to disk with 0o600 when keychain is unavailable."""
    from deep_thought.secrets import _persist_oauth

    token_file = tmp_path / "token.json"
    creds = _make_valid_credentials()

    _persist_oauth("test", creds, str(token_file), use_keychain=False)

    assert token_file.exists()
    assert token_file.read_text() == _FAKE_TOKEN_JSON
    assert oct(token_file.stat().st_mode)[-3:] == "600"


def test_persist_oauth_raises_when_no_storage_available() -> None:
    """_persist_oauth raises RuntimeError when keychain is off and token_path is empty."""
    creds = _make_valid_credentials()

    from deep_thought.secrets import _persist_oauth

    with pytest.raises(RuntimeError, match="No token storage available"):
        _persist_oauth("test", creds, token_path="", use_keychain=False)


# ---------------------------------------------------------------------------
# OAuth keychain error paths
# ---------------------------------------------------------------------------


def test_save_oauth_to_keychain_raises_on_password_set_error() -> None:
    """_save_oauth_to_keychain raises RuntimeError when keychain is locked."""
    import keyring.errors

    from deep_thought.secrets import _save_oauth_to_keychain

    creds = _make_valid_credentials()

    with (
        patch("deep_thought.secrets.keyring.set_password", side_effect=keyring.errors.PasswordSetError),
        pytest.raises(RuntimeError, match="Failed to save OAuth token"),
    ):
        _save_oauth_to_keychain("gmail", creds)


def test_load_oauth_from_keychain_returns_none_on_corrupt_json() -> None:
    """_load_oauth_from_keychain returns None when keychain JSON is malformed."""
    from deep_thought.secrets import _load_oauth_from_keychain

    with patch("deep_thought.secrets.keyring.get_password", return_value="not valid json {{{"):
        result = _load_oauth_from_keychain("gmail", _SCOPES)

    assert result is None


def test_load_oauth_from_keychain_returns_none_when_empty() -> None:
    """_load_oauth_from_keychain returns None when keychain has no entry."""
    from deep_thought.secrets import _load_oauth_from_keychain

    with patch("deep_thought.secrets.keyring.get_password", return_value=None):
        result = _load_oauth_from_keychain("gmail", _SCOPES)

    assert result is None
