"""Tests for deep_thought.gdrive._auth — direct file-based OAuth token storage.

The gdrive tool uses a plain token.json file on disk for OAuth credential
storage. It does not use the macOS keychain and does not share a token with
the gmail or gcal tools. These tests verify the load / refresh / consent
flow / persist paths against ``google.oauth2.credentials.Credentials``,
``google.auth.transport.requests.Request``, and
``google_auth_oauthlib.flow.InstalledAppFlow`` directly.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from deep_thought.gdrive._auth import get_credentials

if TYPE_CHECKING:
    from pathlib import Path


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
    creds.scopes = set(_SCOPES)
    creds.to_json.return_value = _FAKE_TOKEN_JSON
    return creds


def _make_expired_credentials() -> MagicMock:
    """Return a mock Credentials object that is expired but has a refresh token."""
    creds = MagicMock()
    creds.valid = False
    creds.expired = True
    creds.refresh_token = "fake-refresh-token"
    creds.scopes = set(_SCOPES)
    creds.to_json.return_value = _FAKE_TOKEN_JSON
    return creds


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


def test_empty_token_path_raises_value_error() -> None:
    """An empty token_path is a configuration error — fail loudly."""
    with pytest.raises(ValueError, match="auth.token_file must be a non-empty path"):
        get_credentials("/fake/credentials.json", "", _SCOPES)


# ---------------------------------------------------------------------------
# Load existing token
# ---------------------------------------------------------------------------


def test_loads_valid_token_from_file(tmp_path: Path) -> None:
    """When token_file exists and is valid, it is loaded and returned directly."""
    token_file = tmp_path / "token.json"
    token_file.write_text(_FAKE_TOKEN_JSON)
    valid_creds = _make_valid_credentials()

    with patch("deep_thought.gdrive._auth.Credentials") as mock_creds_cls:
        mock_creds_cls.from_authorized_user_file.return_value = valid_creds
        result = get_credentials("/fake/credentials.json", str(token_file), _SCOPES)

    mock_creds_cls.from_authorized_user_file.assert_called_once_with(str(token_file), _SCOPES)
    assert result is valid_creds


def test_corrupt_token_file_falls_through_to_consent_flow(tmp_path: Path) -> None:
    """A token file that fails to parse is logged and the consent flow is run."""
    token_file = tmp_path / "token.json"
    token_file.write_text("{{ not valid json")

    credentials_file = tmp_path / "credentials.json"
    credentials_file.write_text('{"installed": {}}')

    new_creds = _make_valid_credentials()

    with (
        patch("deep_thought.gdrive._auth.Credentials") as mock_creds_cls,
        patch("deep_thought.gdrive._auth.InstalledAppFlow") as mock_flow_cls,
    ):
        mock_creds_cls.from_authorized_user_file.side_effect = ValueError("bad json")
        mock_flow = MagicMock()
        mock_flow.run_local_server.return_value = new_creds
        mock_flow_cls.from_client_secrets_file.return_value = mock_flow

        result = get_credentials(str(credentials_file), str(token_file), _SCOPES)

    assert result is new_creds
    mock_flow.run_local_server.assert_called_once_with(port=0)


# ---------------------------------------------------------------------------
# Refresh expired token
# ---------------------------------------------------------------------------


def test_refreshes_expired_token_and_writes_back(tmp_path: Path) -> None:
    """An expired token with a refresh_token is refreshed and persisted."""
    token_file = tmp_path / "token.json"
    token_file.write_text(_FAKE_TOKEN_JSON)
    expired_creds = _make_expired_credentials()

    with (
        patch("deep_thought.gdrive._auth.Credentials") as mock_creds_cls,
        patch("deep_thought.gdrive._auth.Request") as mock_request_cls,
    ):
        mock_creds_cls.from_authorized_user_file.return_value = expired_creds
        result = get_credentials("/fake/credentials.json", str(token_file), _SCOPES)

    expired_creds.refresh.assert_called_once_with(mock_request_cls.return_value)
    assert result is expired_creds
    # Token was persisted back to disk.
    assert token_file.read_text(encoding="utf-8") == _FAKE_TOKEN_JSON
    assert oct(token_file.stat().st_mode)[-3:] == "600"


# ---------------------------------------------------------------------------
# Browser consent flow
# ---------------------------------------------------------------------------


def test_runs_browser_flow_when_no_token_exists(tmp_path: Path) -> None:
    """If token_file is absent, the OAuth consent flow runs and the result is persisted."""
    token_file = tmp_path / "token.json"  # does not exist
    credentials_file = tmp_path / "credentials.json"
    credentials_file.write_text('{"installed": {}}')

    new_creds = _make_valid_credentials()

    with patch("deep_thought.gdrive._auth.InstalledAppFlow") as mock_flow_cls:
        mock_flow = MagicMock()
        mock_flow.run_local_server.return_value = new_creds
        mock_flow_cls.from_client_secrets_file.return_value = mock_flow

        result = get_credentials(str(credentials_file), str(token_file), _SCOPES)

    mock_flow_cls.from_client_secrets_file.assert_called_once_with(str(credentials_file), _SCOPES)
    mock_flow.run_local_server.assert_called_once_with(port=0)
    assert result is new_creds
    assert token_file.exists()
    assert token_file.read_text(encoding="utf-8") == _FAKE_TOKEN_JSON


def test_token_file_is_chmod_600_after_write(tmp_path: Path) -> None:
    """Tokens persisted by the consent flow are written with mode 0o600."""
    token_file = tmp_path / "token.json"
    credentials_file = tmp_path / "credentials.json"
    credentials_file.write_text('{"installed": {}}')

    new_creds = _make_valid_credentials()

    with patch("deep_thought.gdrive._auth.InstalledAppFlow") as mock_flow_cls:
        mock_flow = MagicMock()
        mock_flow.run_local_server.return_value = new_creds
        mock_flow_cls.from_client_secrets_file.return_value = mock_flow

        get_credentials(str(credentials_file), str(token_file), _SCOPES)

    assert oct(token_file.stat().st_mode)[-3:] == "600"


def test_token_file_parent_directory_is_created(tmp_path: Path) -> None:
    """Missing parent directories of token_file are created on write."""
    token_file = tmp_path / "nested" / "dir" / "token.json"
    credentials_file = tmp_path / "credentials.json"
    credentials_file.write_text('{"installed": {}}')

    new_creds = _make_valid_credentials()

    with patch("deep_thought.gdrive._auth.InstalledAppFlow") as mock_flow_cls:
        mock_flow = MagicMock()
        mock_flow.run_local_server.return_value = new_creds
        mock_flow_cls.from_client_secrets_file.return_value = mock_flow

        get_credentials(str(credentials_file), str(token_file), _SCOPES)

    assert token_file.exists()


def test_missing_credentials_file_raises_with_actionable_message(tmp_path: Path) -> None:
    """No token file AND no credentials.json → FileNotFoundError mentioning `gdrive auth`."""
    token_file = tmp_path / "token.json"  # missing
    credentials_file = tmp_path / "credentials.json"  # also missing

    with pytest.raises(FileNotFoundError, match="OAuth client secret not found"):
        get_credentials(str(credentials_file), str(token_file), _SCOPES)
