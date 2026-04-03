"""YAML configuration loader with .env integration for the GCal Tool."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

_LARGE_DAY_VALUE_THRESHOLD = 365

# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class GcalConfig:
    """Top-level configuration for the GCal Tool."""

    credentials_path: str
    token_path: str
    scopes: list[str]
    api_rate_limit_rpm: int
    retry_max_attempts: int
    retry_base_delay_seconds: int
    calendars: list[str]
    lookback_days: int
    lookahead_days: int
    include_cancelled: bool
    single_events: bool
    output_dir: str
    generate_llms_files: bool
    flat_output: bool


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

_PACKAGE_DIR = Path(__file__).resolve().parent
_BUNDLED_DEFAULT_CONFIG = _PACKAGE_DIR / "default-config.yaml"
_PROJECT_CONFIG_RELATIVE_PATH = Path("src") / "config" / "gcal-configuration.yaml"


def get_bundled_config_path() -> Path:
    """Return the absolute path to the bundled default config template.

    This resolves via ``__file__`` so it always finds the template inside the
    package, regardless of symlinks or the current working directory.

    Returns:
        Absolute path to the ``default-config.yaml`` bundled in the package.
    """
    return _BUNDLED_DEFAULT_CONFIG


def get_default_config_path() -> Path:
    """Return the absolute path to the project-level configuration file.

    Resolves relative to the current working directory so it targets the
    *calling repo* (e.g., magrathea), not the source repo (deep-thought).

    Returns:
        Absolute path to src/config/gcal-configuration.yaml in the calling repo.
    """
    return Path.cwd() / _PROJECT_CONFIG_RELATIVE_PATH


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_config(config_path: Path | None = None) -> GcalConfig:
    """Load the YAML configuration and return a typed GcalConfig.

    If config_path is None, the default path is used
    (src/config/gcal-configuration.yaml relative to the project root).

    Args:
        config_path: Optional explicit path to the YAML configuration file.

    Returns:
        A fully parsed GcalConfig.

    Raises:
        FileNotFoundError: If the configuration file does not exist.
        ValueError: If the file does not contain a valid YAML mapping.
    """
    load_dotenv()

    resolved_path = config_path if config_path is not None else get_default_config_path()

    if not resolved_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {resolved_path}")

    with resolved_path.open("r", encoding="utf-8") as config_file:
        raw: Any = yaml.safe_load(config_file)

    if not isinstance(raw, dict):
        raise ValueError(f"Configuration file must contain a YAML mapping, got: {type(raw).__name__}")

    raw_dict: dict[str, Any] = raw

    raw_scopes = raw_dict.get("scopes")
    scopes: list[str] = (
        list(raw_scopes) if isinstance(raw_scopes, list) else ["https://www.googleapis.com/auth/calendar"]
    )

    raw_calendars = raw_dict.get("calendars")
    calendars: list[str] = list(raw_calendars) if isinstance(raw_calendars, list) else ["primary"]

    return GcalConfig(
        credentials_path=str(raw_dict.get("credentials_path", "src/config/gcal/credentials.json")),
        token_path=str(raw_dict.get("token_path", "data/gcal/token.json")),
        scopes=scopes,
        api_rate_limit_rpm=int(raw_dict.get("api_rate_limit_rpm", 250)),
        retry_max_attempts=int(raw_dict.get("retry_max_attempts", 3)),
        retry_base_delay_seconds=int(raw_dict.get("retry_base_delay_seconds", 1)),
        calendars=calendars,
        lookback_days=int(raw_dict.get("lookback_days", 7)),
        lookahead_days=int(raw_dict.get("lookahead_days", 30)),
        include_cancelled=bool(raw_dict.get("include_cancelled", False)),
        single_events=bool(raw_dict.get("single_events", True)),
        output_dir=str(raw_dict.get("output_dir", "data/gcal/export/")),
        generate_llms_files=bool(raw_dict.get("generate_llms_files", False)),
        flat_output=bool(raw_dict.get("flat_output", False)),
    )


def validate_config(config: GcalConfig) -> list[str]:
    """Validate the loaded configuration and return a list of warning/error messages.

    An empty list means the configuration is valid.

    Args:
        config: A loaded GcalConfig to validate.

    Returns:
        A list of human-readable issue strings. Empty list means no issues.
    """
    issues: list[str] = []

    if not config.credentials_path:
        issues.append("credentials_path is empty — cannot locate OAuth client secret.")

    if not config.token_path:
        issues.append("token_path is empty — cannot store OAuth tokens.")

    if not config.scopes:
        issues.append("No OAuth scopes configured — the tool will not be able to access Google Calendar.")

    if not config.calendars:
        issues.append(
            "No calendars configured — nothing will be collected. Add at least one calendar ID under 'calendars'."
        )

    if config.api_rate_limit_rpm <= 0:
        issues.append(f"api_rate_limit_rpm must be > 0, got: {config.api_rate_limit_rpm}.")

    if config.lookback_days < 0:
        issues.append(f"lookback_days must be >= 0, got: {config.lookback_days}.")
    elif config.lookback_days > _LARGE_DAY_VALUE_THRESHOLD:
        logger.warning(
            "lookback_days is set to %d (> %d). This may result in very slow API calls and excessive data.",
            config.lookback_days,
            _LARGE_DAY_VALUE_THRESHOLD,
        )
        issues.append(
            f"lookback_days value of {config.lookback_days} is very large (> {_LARGE_DAY_VALUE_THRESHOLD} days) "
            "and may result in slow API calls."
        )

    if config.lookahead_days < 0:
        issues.append(f"lookahead_days must be >= 0, got: {config.lookahead_days}.")
    elif config.lookahead_days > _LARGE_DAY_VALUE_THRESHOLD:
        logger.warning(
            "lookahead_days is set to %d (> %d). This may result in very slow API calls and excessive data.",
            config.lookahead_days,
            _LARGE_DAY_VALUE_THRESHOLD,
        )
        issues.append(
            f"lookahead_days value of {config.lookahead_days} is very large (> {_LARGE_DAY_VALUE_THRESHOLD} days) "
            "and may result in slow API calls."
        )

    if config.retry_max_attempts <= 0:
        issues.append(f"retry_max_attempts must be > 0, got: {config.retry_max_attempts}.")

    for calendar_id in config.calendars:
        if "/" in calendar_id or "\\" in calendar_id or calendar_id.startswith("."):
            issues.append(f"Invalid calendar ID '{calendar_id}': must not contain path separators or start with a dot.")

    return issues
