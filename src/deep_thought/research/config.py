"""YAML configuration loader with .env integration for the Research Tool."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class ResearchConfig:
    """Top-level configuration for the Research Tool."""

    api_key_env: str
    retry_max_attempts: int
    retry_base_delay_seconds: int
    search_model: str
    research_model: str
    default_recency: str | None
    output_dir: str


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

_PACKAGE_DIR = Path(__file__).resolve().parent
_BUNDLED_DEFAULT_CONFIG = _PACKAGE_DIR / "default-config.yaml"
_PROJECT_CONFIG_RELATIVE_PATH = Path("src") / "config" / "research-configuration.yaml"


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
        Absolute path to src/config/research-configuration.yaml in the calling repo.
    """
    return Path.cwd() / _PROJECT_CONFIG_RELATIVE_PATH


# ---------------------------------------------------------------------------
# Valid recency values
# ---------------------------------------------------------------------------

_VALID_RECENCY_VALUES = {"hour", "day", "week", "month", "year"}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_config(config_path: Path | None = None) -> ResearchConfig:
    """Load the YAML configuration and return a typed ResearchConfig.

    If config_path is None, the default path is used
    (src/config/research-configuration.yaml relative to the project root).

    Args:
        config_path: Optional explicit path to the YAML configuration file.

    Returns:
        A fully parsed ResearchConfig.

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

    raw_default_recency = raw_dict.get("default_recency")
    default_recency: str | None = str(raw_default_recency) if raw_default_recency is not None else None

    return ResearchConfig(
        api_key_env=str(raw_dict.get("api_key_env", "PERPLEXITY_API_KEY")),
        retry_max_attempts=int(raw_dict.get("retry_max_attempts", 3)),
        retry_base_delay_seconds=int(raw_dict.get("retry_base_delay_seconds", 1)),
        search_model=str(raw_dict.get("search_model", "sonar")),
        research_model=str(raw_dict.get("research_model", "sonar-deep-research")),
        default_recency=default_recency,
        output_dir=str(raw_dict.get("output_dir", "data/research/export/")),
    )


def validate_config(config: ResearchConfig) -> list[str]:
    """Validate the loaded configuration and return a list of warning/error messages.

    An empty list means the configuration is valid.

    Args:
        config: A loaded ResearchConfig to validate.

    Returns:
        A list of human-readable issue strings. Empty list means no issues.
    """
    issues: list[str] = []

    if not config.api_key_env:
        issues.append("api_key_env is empty — cannot determine which environment variable holds the API key.")

    if not config.search_model:
        issues.append("search_model is empty — the search command has no model to use.")

    if not config.research_model:
        issues.append("research_model is empty — the research command has no model to use.")

    if config.retry_max_attempts <= 0:
        issues.append(f"retry_max_attempts must be > 0, got: {config.retry_max_attempts}.")

    if config.retry_base_delay_seconds <= 0:
        issues.append(f"retry_base_delay_seconds must be > 0, got: {config.retry_base_delay_seconds}.")

    if config.default_recency is not None and config.default_recency not in _VALID_RECENCY_VALUES:
        valid_options = ", ".join(f'"{value}"' for value in sorted(_VALID_RECENCY_VALUES))
        issues.append(
            f"default_recency '{config.default_recency}' is not a recognised value. "
            f"Valid options: {valid_options}, or null to disable."
        )

    return issues


def get_api_key(config: ResearchConfig) -> str:
    """Read the Perplexity API key from the environment variable named in config.

    Args:
        config: A loaded ResearchConfig specifying which env var holds the API key.

    Returns:
        The Perplexity API key string.

    Raises:
        OSError: If the environment variable is not set or empty.
    """
    api_key = os.environ.get(config.api_key_env)
    if not api_key:
        raise OSError(
            f"Perplexity API key not found. Set the '{config.api_key_env}' environment variable "
            "(either in your shell or in a .env file at the project root)."
        )
    return api_key
