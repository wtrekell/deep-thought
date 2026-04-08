"""YAML configuration loader with .env integration for the Research Tool."""

from __future__ import annotations

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
    qdrant_collection: str


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
# Valid recency values and API mapping
# ---------------------------------------------------------------------------

# The Perplexity API only accepts these five discrete values for search_recency_filter.
# "3 months" and "6 months" are user-facing aliases that map to "year" (the closest
# supported superset). The user-specified value is preserved in output frontmatter and
# Qdrant payloads for transparency; only the API call receives the mapped value.
_VALID_RECENCY_VALUES = {"hour", "day", "week", "month", "year", "3 months", "6 months"}

RECENCY_API_MAP: dict[str, str] = {
    "3 months": "year",
    "6 months": "year",
}


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

    # Required fields: raise KeyError immediately when absent so the caller sees
    # a clear error rather than silently using a baked-in default value.
    try:
        api_key_env = str(raw_dict["api_key_env"])
        search_model = str(raw_dict["search_model"])
        research_model = str(raw_dict["research_model"])
        output_dir = str(raw_dict["output_dir"])
    except KeyError as missing_key:
        raise ValueError(f"Configuration file missing required field: {missing_key}") from missing_key

    # Optional fields with documented defaults.
    retry_max_attempts = int(raw_dict.get("retry_max_attempts", 3))
    retry_base_delay_seconds = int(raw_dict.get("retry_base_delay_seconds", 1))

    raw_default_recency = raw_dict.get("default_recency")
    default_recency: str | None = str(raw_default_recency) if raw_default_recency is not None else None

    qdrant_collection = str(raw_dict.get("qdrant_collection", "deep_thought_db"))

    return ResearchConfig(
        api_key_env=api_key_env,
        retry_max_attempts=retry_max_attempts,
        retry_base_delay_seconds=retry_base_delay_seconds,
        search_model=search_model,
        research_model=research_model,
        default_recency=default_recency,
        output_dir=output_dir,
        qdrant_collection=qdrant_collection,
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

    if not config.output_dir:
        issues.append("output_dir is empty — cannot determine where to write output files.")

    if config.default_recency is not None and config.default_recency not in _VALID_RECENCY_VALUES:
        native_values = ", ".join(f'"{v}"' for v in sorted({"hour", "day", "week", "month", "year"}))
        alias_values = ", ".join(f'"{v}"' for v in sorted(RECENCY_API_MAP))
        issues.append(
            f"default_recency '{config.default_recency}' is not a recognised value. "
            f"Native Perplexity values: {native_values}. "
            f'Aliases (map to "year" at the API level): {alias_values}. '
            f"Or set to null to disable."
        )

    return issues


def get_api_key(config: ResearchConfig) -> str:
    """Read the Perplexity API key from macOS Keychain or the environment variable named in config.

    Checks Keychain first (service ``deep-thought-research``, key ``api-key``),
    then falls back to the environment variable specified by ``config.api_key_env``.

    Args:
        config: A loaded ResearchConfig specifying which env var holds the API key.

    Returns:
        The Perplexity API key string.

    Raises:
        OSError: If the API key is not found in Keychain or environment.
    """
    from deep_thought.secrets import get_secret

    return get_secret("research", "api-key", env_var=config.api_key_env)
