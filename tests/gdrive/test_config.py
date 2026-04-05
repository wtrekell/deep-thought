"""Tests for deep_thought.gdrive.config — config loading and validation."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import yaml

from deep_thought.gdrive.config import GDriveConfig, load_config

if TYPE_CHECKING:
    from pathlib import Path


def _write_config(tmp_path: Path, content: dict[object, object]) -> Path:
    """Write a YAML config dict to a temp file and return the path."""
    config_path = tmp_path / "gdrive-configuration.yaml"
    config_path.write_text(yaml.dump(content))
    return config_path


def _valid_config_dict() -> dict[object, object]:
    """Return a minimal valid configuration dict."""
    return {
        "auth": {
            "credentials_file": "src/config/gdrive/credentials.json",
            "token_file": "src/config/gdrive/token.json",
            "scopes": ["https://www.googleapis.com/auth/drive.file"],
        },
        "backup": {
            "source_dir": "/tmp/source",
            "drive_folder_id": "root-folder-id",
        },
        "api_rate_limit_rpm": 100,
        "retry": {
            "max_attempts": 3,
            "base_delay_seconds": 2.0,
        },
    }


def test_load_config_valid_returns_gdrive_config(tmp_path: Path) -> None:
    """A valid config file returns a GDriveConfig with correct values."""
    config_path = _write_config(tmp_path, _valid_config_dict())
    config = load_config(config_path)

    assert isinstance(config, GDriveConfig)
    assert config.credentials_file == "src/config/gdrive/credentials.json"
    assert config.token_file == "src/config/gdrive/token.json"
    assert config.scopes == ["https://www.googleapis.com/auth/drive.file"]
    assert config.source_dir == "/tmp/source"
    assert config.drive_folder_id == "root-folder-id"
    assert config.api_rate_limit_rpm == 100
    assert config.retry_max_attempts == 3
    assert config.retry_base_delay_seconds == 2.0


def test_load_config_allows_empty_drive_folder_id(tmp_path: Path) -> None:
    """drive_folder_id may be empty string at load time (validated later at backup time)."""
    config_data = _valid_config_dict()
    config_data["backup"] = {"source_dir": "/tmp/source", "drive_folder_id": ""}  # type: ignore[index]
    config_path = _write_config(tmp_path, config_data)

    config = load_config(config_path)
    assert config.drive_folder_id == ""


def test_load_config_raises_file_not_found_for_missing_file(tmp_path: Path) -> None:
    """FileNotFoundError is raised when the config file does not exist."""
    missing_path = tmp_path / "nonexistent.yaml"

    with pytest.raises(FileNotFoundError, match="Configuration file not found"):
        load_config(missing_path)


def test_load_config_raises_value_error_for_missing_credentials_file(tmp_path: Path) -> None:
    """ValueError is raised when auth.credentials_file is missing."""
    config_data = _valid_config_dict()
    del config_data["auth"]["credentials_file"]  # type: ignore[index]
    config_path = _write_config(tmp_path, config_data)

    with pytest.raises(ValueError, match="auth.credentials_file"):
        load_config(config_path)


def test_load_config_raises_value_error_for_missing_token_file(tmp_path: Path) -> None:
    """ValueError is raised when auth.token_file is missing."""
    config_data = _valid_config_dict()
    del config_data["auth"]["token_file"]  # type: ignore[index]
    config_path = _write_config(tmp_path, config_data)

    with pytest.raises(ValueError, match="auth.token_file"):
        load_config(config_path)


def test_load_config_raises_value_error_for_missing_scopes(tmp_path: Path) -> None:
    """ValueError is raised when auth.scopes is missing."""
    config_data = _valid_config_dict()
    del config_data["auth"]["scopes"]  # type: ignore[index]
    config_path = _write_config(tmp_path, config_data)

    with pytest.raises(ValueError, match="auth.scopes"):
        load_config(config_path)


def test_load_config_raises_value_error_for_missing_source_dir(tmp_path: Path) -> None:
    """ValueError is raised when backup.source_dir is missing."""
    config_data = _valid_config_dict()
    del config_data["backup"]["source_dir"]  # type: ignore[index]
    config_path = _write_config(tmp_path, config_data)

    with pytest.raises(ValueError, match="backup.source_dir"):
        load_config(config_path)


def test_load_config_raises_value_error_for_wrong_type_credentials_file(tmp_path: Path) -> None:
    """ValueError is raised when auth.credentials_file is not a string."""
    config_data = _valid_config_dict()
    config_data["auth"]["credentials_file"] = 123  # type: ignore[index]
    config_path = _write_config(tmp_path, config_data)

    with pytest.raises(ValueError, match="auth.credentials_file"):
        load_config(config_path)


def test_load_config_raises_value_error_for_wrong_type_rate_limit(tmp_path: Path) -> None:
    """ValueError is raised when api_rate_limit_rpm is not an integer."""
    config_data = _valid_config_dict()
    config_data["api_rate_limit_rpm"] = "fast"
    config_path = _write_config(tmp_path, config_data)

    with pytest.raises(ValueError, match="api_rate_limit_rpm"):
        load_config(config_path)


def test_load_config_raises_value_error_for_non_mapping_yaml(tmp_path: Path) -> None:
    """ValueError is raised when the YAML file does not contain a mapping."""
    config_path = tmp_path / "bad.yaml"
    config_path.write_text("- this\n- is\n- a\n- list\n")

    with pytest.raises(ValueError, match="YAML mapping"):
        load_config(config_path)
