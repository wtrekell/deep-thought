"""YAML configuration loader for the GDrive Tool."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_PROJECT_CONFIG_RELATIVE_PATH = Path("src") / "config" / "gdrive-configuration.yaml"


@dataclass
class GDriveConfig:
    """Top-level configuration for the GDrive backup tool.

    Fields map to the nested YAML structure:
        auth.credentials_file     → credentials_file
        auth.token_file           → token_file
        auth.scopes               → scopes
        backup.source_dir         → source_dir
        backup.drive_folder_id    → drive_folder_id
        api_rate_limit_rpm        → api_rate_limit_rpm
        retry.max_attempts        → retry_max_attempts
        retry.base_delay_seconds  → retry_base_delay_seconds
    """

    credentials_file: str
    token_file: str
    scopes: list[str]
    source_dir: str
    drive_folder_id: str
    api_rate_limit_rpm: int
    retry_max_attempts: int
    retry_base_delay_seconds: float


def get_default_config_path() -> Path:
    """Return the absolute path to the project-level configuration file.

    Resolves relative to the current working directory so it targets the
    calling repo, not the source repo.

    Returns:
        Absolute path to src/config/gdrive-configuration.yaml in the calling repo.
    """
    return Path.cwd() / _PROJECT_CONFIG_RELATIVE_PATH


def load_config(config_path: Path | None = None) -> GDriveConfig:
    """Load the YAML configuration and return a typed GDriveConfig.

    The YAML file uses a nested structure (``auth:``, ``backup:``, ``retry:``
    sections) that is flattened into a single GDriveConfig dataclass.

    If ``config_path`` is None, the default path is used
    (src/config/gdrive-configuration.yaml relative to the project root).

    Args:
        config_path: Optional explicit path to the YAML configuration file.

    Returns:
        A fully parsed GDriveConfig.

    Raises:
        FileNotFoundError: If the configuration file does not exist.
        ValueError: If the file does not contain a valid YAML mapping, or if
                    required fields are missing or have the wrong type.
    """
    resolved_path = config_path if config_path is not None else get_default_config_path()

    if not resolved_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {resolved_path}")

    with resolved_path.open("r", encoding="utf-8") as config_file:
        raw: Any = yaml.safe_load(config_file)

    if not isinstance(raw, dict):
        raise ValueError(f"Configuration file must contain a YAML mapping, got: {type(raw).__name__}")

    raw_dict: dict[str, Any] = raw

    # Extract nested sections with safe defaults
    auth_section: dict[str, Any] = raw_dict.get("auth", {})
    backup_section: dict[str, Any] = raw_dict.get("backup", {})
    retry_section: dict[str, Any] = raw_dict.get("retry", {})

    if not isinstance(auth_section, dict):
        raise ValueError("Configuration 'auth' section must be a YAML mapping.")
    if not isinstance(backup_section, dict):
        raise ValueError("Configuration 'backup' section must be a YAML mapping.")
    if not isinstance(retry_section, dict):
        raise ValueError("Configuration 'retry' section must be a YAML mapping.")

    # credentials_file is required
    raw_credentials_file = auth_section.get("credentials_file")
    if raw_credentials_file is None:
        raise ValueError("Missing required config field: auth.credentials_file")
    if not isinstance(raw_credentials_file, str):
        raise ValueError(f"auth.credentials_file must be a string, got: {type(raw_credentials_file).__name__}")

    # token_file is required
    raw_token_file = auth_section.get("token_file")
    if raw_token_file is None:
        raise ValueError("Missing required config field: auth.token_file")
    if not isinstance(raw_token_file, str):
        raise ValueError(f"auth.token_file must be a string, got: {type(raw_token_file).__name__}")

    # scopes — required list
    raw_scopes = auth_section.get("scopes")
    if raw_scopes is None:
        raise ValueError("Missing required config field: auth.scopes")
    if not isinstance(raw_scopes, list):
        raise ValueError(f"auth.scopes must be a list, got: {type(raw_scopes).__name__}")
    scopes: list[str] = [str(scope) for scope in raw_scopes]

    # source_dir is required
    raw_source_dir = backup_section.get("source_dir")
    if raw_source_dir is None:
        raise ValueError("Missing required config field: backup.source_dir")
    if not isinstance(raw_source_dir, str):
        raise ValueError(f"backup.source_dir must be a string, got: {type(raw_source_dir).__name__}")

    # drive_folder_id may be empty at load time; validated at backup time
    raw_drive_folder_id = backup_section.get("drive_folder_id", "")
    if not isinstance(raw_drive_folder_id, str):
        raise ValueError(f"backup.drive_folder_id must be a string, got: {type(raw_drive_folder_id).__name__}")

    # api_rate_limit_rpm — top-level key
    raw_rate_limit = raw_dict.get("api_rate_limit_rpm", 100)
    if not isinstance(raw_rate_limit, int):
        raise ValueError(f"api_rate_limit_rpm must be an integer, got: {type(raw_rate_limit).__name__}")

    # retry section
    raw_max_attempts = retry_section.get("max_attempts", 3)
    if not isinstance(raw_max_attempts, int):
        raise ValueError(f"retry.max_attempts must be an integer, got: {type(raw_max_attempts).__name__}")

    raw_base_delay = retry_section.get("base_delay_seconds", 2.0)
    if not isinstance(raw_base_delay, (int, float)):
        raise ValueError(f"retry.base_delay_seconds must be a number, got: {type(raw_base_delay).__name__}")

    return GDriveConfig(
        credentials_file=raw_credentials_file,
        token_file=raw_token_file,
        scopes=scopes,
        source_dir=raw_source_dir,
        drive_folder_id=raw_drive_folder_id,
        api_rate_limit_rpm=raw_rate_limit,
        retry_max_attempts=raw_max_attempts,
        retry_base_delay_seconds=float(raw_base_delay),
    )
