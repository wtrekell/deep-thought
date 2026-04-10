"""Tests for deep_thought.gcal._auth — OAuth token management via shared secrets module."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from deep_thought.gcal._auth import get_credentials
from deep_thought.secrets import GOOGLE_OAUTH_SCOPES, GOOGLE_SERVICE

if TYPE_CHECKING:
    from pathlib import Path


_SCOPES = ["https://www.googleapis.com/auth/calendar"]


def _make_valid_credentials() -> MagicMock:
    creds = MagicMock()
    creds.valid = True
    creds.expired = False
    creds.scopes = set(GOOGLE_OAUTH_SCOPES)
    return creds


def test_delegates_to_shared_oauth_with_google_service() -> None:
    """get_credentials should delegate to secrets.get_oauth_credentials with service='google'."""
    valid_creds = _make_valid_credentials()
    with patch("deep_thought.gcal._auth.get_oauth_credentials", return_value=valid_creds) as mock_get:
        result = get_credentials("/creds.json", "/token.json", _SCOPES)

    mock_get.assert_called_once_with(
        GOOGLE_SERVICE,
        "/creds.json",
        "/token.json",
        GOOGLE_OAUTH_SCOPES,
        required_scopes=GOOGLE_OAUTH_SCOPES,
    )
    assert result is valid_creds


def test_loads_from_keychain() -> None:
    """Should return valid credentials from keychain."""
    valid_creds = _make_valid_credentials()
    with (
        patch("deep_thought.secrets.keychain_available", return_value=True),
        patch("deep_thought.secrets._load_oauth_from_keychain", return_value=valid_creds),
    ):
        result = get_credentials("/creds.json", "", _SCOPES)

    assert result is valid_creds


def test_raises_when_credentials_file_missing() -> None:
    """Should raise FileNotFoundError when no credentials file exists."""
    with (
        patch("deep_thought.secrets.keychain_available", return_value=True),
        patch("deep_thought.secrets._load_oauth_from_keychain", return_value=None),
        pytest.raises(FileNotFoundError, match="OAuth client secret not found"),
    ):
        get_credentials("/nonexistent/creds.json", "", _SCOPES)


def test_auto_migrates_file_to_keychain(tmp_path: Path) -> None:
    """Should migrate file-based token to keychain when keychain is available."""
    token_file = tmp_path / "token.json"
    token_file.write_text('{"token": "abc"}')

    valid_creds = _make_valid_credentials()

    with (
        patch("deep_thought.secrets.keychain_available", return_value=True),
        patch("deep_thought.secrets._load_oauth_from_keychain", return_value=None),
        patch("deep_thought.secrets.Credentials") as mock_creds_cls,
        patch("deep_thought.secrets._save_oauth_to_keychain") as mock_save,
    ):
        mock_creds_cls.from_authorized_user_file.return_value = valid_creds
        result = get_credentials("/creds.json", str(token_file), _SCOPES)

    mock_save.assert_called_once_with(GOOGLE_SERVICE, valid_creds)
    assert not token_file.exists()
    assert result is valid_creds
