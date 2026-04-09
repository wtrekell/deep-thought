"""YAML configuration loader for the file-txt tool."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

_KNOWN_CONFIG_KEYS = frozenset(
    {
        "prefer_html",
        "full_headers",
        "include_attachments",
        "output_dir",
        "include_page_numbers",
        "extract_images",
        "max_file_size_mb",
        "allowed_extensions",
        "exclude_patterns",
    }
)

# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class PdfConfig:
    """Configuration placeholder for the PyMuPDF PDF conversion engine.

    PyMuPDF requires no engine-specific settings. This dataclass is retained
    so the FileTxtConfig structure remains extensible if PDF options are added
    in the future.
    """


@dataclass
class EmailConfig:
    """Configuration for email (.eml/.msg) conversion."""

    prefer_html: bool
    full_headers: bool
    include_attachments: bool


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

    pdf: PdfConfig
    email: EmailConfig
    output: OutputConfig
    limits: LimitsConfig
    filter: FilterConfig


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

_PACKAGE_DIR = Path(__file__).resolve().parent
_BUNDLED_DEFAULT_CONFIG = _PACKAGE_DIR / "default-config.yaml"
_PROJECT_CONFIG_RELATIVE_PATH = Path("src") / "config" / "file-txt-configuration.yaml"


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
        Absolute path to src/config/file-txt-configuration.yaml in the calling repo.
    """
    return Path.cwd() / _PROJECT_CONFIG_RELATIVE_PATH


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def _parse_pdf_config(raw: dict[str, Any]) -> PdfConfig:  # noqa: ARG001
    """Parse PDF-related fields from the top-level YAML mapping.

    PyMuPDF requires no engine-specific settings so this always returns an
    empty PdfConfig. The ``raw`` parameter is accepted to keep the signature
    consistent with the other parse helpers.

    Args:
        raw: The full YAML mapping as a dict (unused).

    Returns:
        An empty PdfConfig.
    """
    return PdfConfig()


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


def _parse_email_config(raw: dict[str, Any]) -> EmailConfig:
    """Parse the email-related fields from the top-level YAML mapping.

    Args:
        raw: The full YAML mapping as a dict.

    Returns:
        An EmailConfig with prefer_html, full_headers, and include_attachments populated.
    """
    prefer_html: bool = raw.get("prefer_html", False)
    full_headers: bool = raw.get("full_headers", False)
    include_attachments: bool = raw.get("include_attachments", True)
    return EmailConfig(prefer_html=prefer_html, full_headers=full_headers, include_attachments=include_attachments)


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

    pdf_config = _parse_pdf_config(raw_dict)
    email_config = _parse_email_config(raw_dict)
    output_config = _parse_output_config(raw_dict)
    limits_config = _parse_limits_config(raw_dict)
    filter_config = _parse_filter_config(raw_dict)

    unknown_keys = set(raw_dict.keys()) - _KNOWN_CONFIG_KEYS
    if unknown_keys:
        config_logger = logging.getLogger(__name__)
        config_logger.warning("Unknown configuration keys (possibly misspelled): %s", sorted(unknown_keys))

    return FileTxtConfig(
        pdf=pdf_config,
        email=email_config,
        output=output_config,
        limits=limits_config,
        filter=filter_config,
    )


def validate_config(config: FileTxtConfig) -> list[str]:
    """Validate the loaded configuration and return a list of warning/error messages.

    An empty list means the configuration is valid.

    Args:
        config: A loaded FileTxtConfig to validate.

    Returns:
        A list of human-readable issue strings. Empty list means no issues.
    """
    issues: list[str] = []

    if config.limits.max_file_size_mb <= 0:
        issues.append(f"max_file_size_mb must be greater than 0, got: {config.limits.max_file_size_mb}.")

    if not config.filter.allowed_extensions:
        issues.append(
            "allowed_extensions is empty — no files will be processed. Add at least one extension (e.g., '.pdf')."
        )

    return issues


