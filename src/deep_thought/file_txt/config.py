"""YAML configuration loader for the file-txt tool."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class MarkerConfig:
    """Configuration for the Marker PDF conversion engine."""

    force_ocr: bool
    torch_device: str


@dataclass
class OutputConfig:
    """Configuration for document output generation."""

    output_dir: str
    include_page_numbers: bool
    extract_images: bool


@dataclass
class LimitsConfig:
    """Configuration for processing limits."""

    max_file_size_mb: int


@dataclass
class FilterConfig:
    """Configuration for file filtering rules."""

    allowed_extensions: list[str]
    exclude_patterns: list[str]


@dataclass
class FileTxtConfig:
    """Top-level configuration for the file-txt tool."""

    marker: MarkerConfig
    output: OutputConfig
    limits: LimitsConfig
    filter: FilterConfig


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
_DEFAULT_CONFIG_RELATIVE_PATH = Path("src") / "config" / "file-txt-configuration.yaml"


def get_default_config_path() -> Path:
    """Return the absolute path to the default YAML configuration file."""
    return _PROJECT_ROOT / _DEFAULT_CONFIG_RELATIVE_PATH


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def _parse_marker_config(raw: dict[str, Any]) -> MarkerConfig:
    """Parse the marker-related fields from the top-level YAML mapping.

    Args:
        raw: The full YAML mapping as a dict.

    Returns:
        A MarkerConfig with force_ocr and torch_device populated.
    """
    force_ocr: bool = raw.get("force_ocr", False)
    torch_device: str = raw.get("torch_device", "cpu")
    return MarkerConfig(force_ocr=force_ocr, torch_device=torch_device)


def _parse_output_config(raw: dict[str, Any]) -> OutputConfig:
    """Parse the output-related fields from the top-level YAML mapping.

    Args:
        raw: The full YAML mapping as a dict.

    Returns:
        An OutputConfig with output_dir, include_page_numbers, and extract_images.
    """
    output_dir: str = raw.get("output_dir", "output/")
    include_page_numbers: bool = raw.get("include_page_numbers", False)
    extract_images: bool = raw.get("extract_images", True)
    return OutputConfig(
        output_dir=output_dir,
        include_page_numbers=include_page_numbers,
        extract_images=extract_images,
    )


def _parse_limits_config(raw: dict[str, Any]) -> LimitsConfig:
    """Parse the limits-related fields from the top-level YAML mapping.

    Args:
        raw: The full YAML mapping as a dict.

    Returns:
        A LimitsConfig with max_file_size_mb populated.
    """
    raw_max_mb = raw.get("max_file_size_mb", 200)
    if not isinstance(raw_max_mb, int):
        raise ValueError(f"max_file_size_mb must be an integer, got: {type(raw_max_mb).__name__}")
    return LimitsConfig(max_file_size_mb=raw_max_mb)


def _parse_filter_config(raw: dict[str, Any]) -> FilterConfig:
    """Parse the file filter fields from the top-level YAML mapping.

    Args:
        raw: The full YAML mapping as a dict.

    Returns:
        A FilterConfig with allowed_extensions and exclude_patterns populated.
    """
    raw_extensions = raw.get("allowed_extensions")
    allowed_extensions: list[str] = raw_extensions if isinstance(raw_extensions, list) else []

    raw_patterns = raw.get("exclude_patterns")
    exclude_patterns: list[str] = raw_patterns if isinstance(raw_patterns, list) else []

    return FilterConfig(
        allowed_extensions=allowed_extensions,
        exclude_patterns=exclude_patterns,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_config(config_path: Path | None = None) -> FileTxtConfig:
    """Load the YAML configuration and return a typed FileTxtConfig.

    If config_path is None the default path is used
    (src/config/file-txt-configuration.yaml relative to the project root).

    Args:
        config_path: Optional explicit path to the YAML configuration file.

    Returns:
        A fully parsed FileTxtConfig.

    Raises:
        FileNotFoundError: If the configuration file does not exist.
        ValueError: If the file does not contain a valid YAML mapping, or if
                    any field value is of the wrong type.
    """
    resolved_path = config_path if config_path is not None else get_default_config_path()

    if not resolved_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {resolved_path}")

    with resolved_path.open("r", encoding="utf-8") as config_file:
        raw: Any = yaml.safe_load(config_file)

    if not isinstance(raw, dict):
        raise ValueError(f"Configuration file must contain a YAML mapping, got: {type(raw).__name__}")

    raw_dict: dict[str, Any] = raw

    marker_config = _parse_marker_config(raw_dict)
    output_config = _parse_output_config(raw_dict)
    limits_config = _parse_limits_config(raw_dict)
    filter_config = _parse_filter_config(raw_dict)

    return FileTxtConfig(
        marker=marker_config,
        output=output_config,
        limits=limits_config,
        filter=filter_config,
    )


_VALID_TORCH_DEVICES = {"mps", "cuda", "cpu"}


def validate_config(config: FileTxtConfig) -> list[str]:
    """Validate the loaded configuration and return a list of warning/error messages.

    An empty list means the configuration is valid.

    Args:
        config: A loaded FileTxtConfig to validate.

    Returns:
        A list of human-readable issue strings. Empty list means no issues.
    """
    issues: list[str] = []

    if config.marker.torch_device not in _VALID_TORCH_DEVICES:
        issues.append(
            f"torch_device '{config.marker.torch_device}' is not valid. Must be one of: {sorted(_VALID_TORCH_DEVICES)}."
        )

    if config.limits.max_file_size_mb <= 0:
        issues.append(f"max_file_size_mb must be greater than 0, got: {config.limits.max_file_size_mb}.")

    if not config.filter.allowed_extensions:
        issues.append(
            "allowed_extensions is empty — no files will be processed. Add at least one extension (e.g., '.pdf')."
        )

    return issues


def save_default_config(destination_path: Path) -> None:
    """Write the bundled default configuration YAML to destination_path.

    Creates parent directories as needed.

    Args:
        destination_path: Where to write the default config file.

    Raises:
        FileExistsError: If a file already exists at destination_path.
    """
    if destination_path.exists():
        raise FileExistsError(f"Configuration file already exists: {destination_path}")

    source_path = get_default_config_path()
    if not source_path.exists():
        raise FileNotFoundError(f"Bundled default config not found: {source_path}")

    destination_path.parent.mkdir(parents=True, exist_ok=True)
    destination_path.write_bytes(source_path.read_bytes())
