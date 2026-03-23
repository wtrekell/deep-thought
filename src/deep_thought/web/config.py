"""YAML configuration loader for the web crawl tool."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

_VALID_MODES = {"blog", "documentation", "direct"}


@dataclass
class CrawlConfig:
    """Configuration for the web crawl behaviour."""

    mode: str
    input_url: str | None
    max_depth: int
    max_pages: int
    js_wait: float
    browser_channel: str | None
    stealth: bool
    include_patterns: list[str]
    exclude_patterns: list[str]
    retry_attempts: int
    retry_delay: float
    output_dir: str
    extract_images: bool
    generate_llms_files: bool
    index_depth: int
    min_article_words: int
    changelog_url: str | None


@dataclass
class WebConfig:
    """Top-level configuration for the web crawl tool."""

    crawl: CrawlConfig


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
_DEFAULT_CONFIG_RELATIVE_PATH = Path("src") / "config" / "web-configuration.yaml"
_TEMPLATES_RELATIVE_PATH = Path("src") / "config" / "web" / "templates"
_BATCH_CONFIG_RELATIVE_PATH = Path("src") / "config" / "web"


def get_default_config_path() -> Path:
    """Return the absolute path to the default YAML configuration file.

    Returns:
        Absolute path to src/config/web-configuration.yaml relative to the project root.
    """
    return _PROJECT_ROOT / _DEFAULT_CONFIG_RELATIVE_PATH


def get_templates_dir() -> Path:
    """Return the absolute path to the batch config templates directory.

    Returns:
        Absolute path to src/config/web/templates/ relative to the project root.
    """
    return _PROJECT_ROOT / _TEMPLATES_RELATIVE_PATH


def get_batch_config_dir() -> Path:
    """Return the absolute path to the batch config directory.

    Returns:
        Absolute path to src/config/web/ relative to the project root.
    """
    return _PROJECT_ROOT / _BATCH_CONFIG_RELATIVE_PATH


def copy_default_templates(batch_config_dir: Path | None = None) -> list[tuple[str, str]]:
    """Copy template YAML files to the batch config directory.

    Scans the templates directory for files matching ``*-template.yaml``
    and copies each one to the batch config directory with the ``-template``
    suffix stripped (e.g. ``blog-template.yaml`` becomes ``blog.yaml``).

    Existing files are never overwritten.

    Args:
        batch_config_dir: Destination directory. Defaults to src/config/web/.

    Returns:
        A list of (status, filename) tuples where status is ``"created"``
        or ``"exists"``.
    """
    templates_directory = get_templates_dir()
    destination_directory = batch_config_dir if batch_config_dir is not None else get_batch_config_dir()

    results: list[tuple[str, str]] = []

    if not templates_directory.exists():
        return results

    destination_directory.mkdir(parents=True, exist_ok=True)

    for template_path in sorted(templates_directory.glob("*-template.yaml")):
        target_name = template_path.stem.replace("-template", "") + ".yaml"
        target_path = destination_directory / target_name

        if target_path.exists():
            results.append(("exists", target_name))
        else:
            target_path.write_bytes(template_path.read_bytes())
            results.append(("created", target_name))

    return results


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def _parse_crawl_config(raw: dict[str, Any]) -> CrawlConfig:
    """Parse crawl-related fields from the top-level YAML mapping.

    Args:
        raw: The full YAML mapping as a dict.

    Returns:
        A CrawlConfig with all crawl settings populated from raw or defaults.
    """
    mode: str = raw.get("mode", "blog")

    raw_input_url = raw.get("input_url")
    input_url: str | None = str(raw_input_url) if raw_input_url is not None else None

    max_depth: int = int(raw.get("max_depth", 3))
    max_pages: int = int(raw.get("max_pages", 100))
    js_wait: float = float(raw.get("js_wait", 1.0))

    raw_channel = raw.get("browser_channel")
    browser_channel: str | None = str(raw_channel) if raw_channel is not None else None

    stealth: bool = bool(raw.get("stealth", False))

    raw_include = raw.get("include_patterns")
    include_patterns: list[str] = list(raw_include) if isinstance(raw_include, list) else []

    raw_exclude = raw.get("exclude_patterns")
    exclude_patterns: list[str] = list(raw_exclude) if isinstance(raw_exclude, list) else []

    retry_attempts: int = int(raw.get("retry_attempts", 2))
    retry_delay: float = float(raw.get("retry_delay", 5.0))
    output_dir: str = str(raw.get("output_dir", "output/web/"))
    extract_images: bool = bool(raw.get("extract_images", False))
    generate_llms_files: bool = bool(raw.get("generate_llms_files", True))
    index_depth: int = int(raw.get("index_depth", 1))
    min_article_words: int = int(raw.get("min_article_words", 200))

    raw_changelog = raw.get("changelog_url")
    changelog_url: str | None = str(raw_changelog) if raw_changelog is not None else None

    return CrawlConfig(
        mode=mode,
        input_url=input_url,
        max_depth=max_depth,
        max_pages=max_pages,
        js_wait=js_wait,
        browser_channel=browser_channel,
        stealth=stealth,
        include_patterns=include_patterns,
        exclude_patterns=exclude_patterns,
        retry_attempts=retry_attempts,
        retry_delay=retry_delay,
        output_dir=output_dir,
        extract_images=extract_images,
        generate_llms_files=generate_llms_files,
        index_depth=index_depth,
        min_article_words=min_article_words,
        changelog_url=changelog_url,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_config(config_path: Path | None = None) -> WebConfig:
    """Load the YAML configuration and return a typed WebConfig.

    If config_path is None the default path is used
    (src/config/web-configuration.yaml relative to the project root).

    Args:
        config_path: Optional explicit path to the YAML configuration file.

    Returns:
        A fully parsed WebConfig.

    Raises:
        FileNotFoundError: If the configuration file does not exist.
        ValueError: If the file does not contain a valid YAML mapping.
    """
    resolved_path = config_path if config_path is not None else get_default_config_path()

    if not resolved_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {resolved_path}")

    with resolved_path.open("r", encoding="utf-8") as config_file:
        raw: Any = yaml.safe_load(config_file)

    if not isinstance(raw, dict):
        raise ValueError(f"Configuration file must contain a YAML mapping, got: {type(raw).__name__}")

    raw_dict: dict[str, Any] = raw
    crawl_config = _parse_crawl_config(raw_dict)

    return WebConfig(crawl=crawl_config)


def validate_config(config: WebConfig) -> list[str]:
    """Validate the loaded configuration and return a list of warning/error messages.

    An empty list means the configuration is valid.

    Args:
        config: A loaded WebConfig to validate.

    Returns:
        A list of human-readable issue strings. Empty list means no issues.
    """
    issues: list[str] = []

    if config.crawl.mode not in _VALID_MODES:
        issues.append(f"mode '{config.crawl.mode}' is not valid. Must be one of: {sorted(_VALID_MODES)}.")

    for pattern_text in config.crawl.include_patterns:
        try:
            re.compile(pattern_text)
        except re.error as regex_error:
            issues.append(f"include_patterns contains invalid regex '{pattern_text}': {regex_error}")

    for pattern_text in config.crawl.exclude_patterns:
        try:
            re.compile(pattern_text)
        except re.error as regex_error:
            issues.append(f"exclude_patterns contains invalid regex '{pattern_text}': {regex_error}")

    if config.crawl.max_depth < 0:
        issues.append(f"max_depth must be non-negative, got: {config.crawl.max_depth}.")

    if config.crawl.max_pages < 0:
        issues.append(f"max_pages must be non-negative, got: {config.crawl.max_pages}.")

    if config.crawl.js_wait < 0:
        issues.append(f"js_wait must be non-negative, got: {config.crawl.js_wait}.")

    if config.crawl.retry_attempts < 0:
        issues.append(f"retry_attempts must be non-negative, got: {config.crawl.retry_attempts}.")

    if config.crawl.retry_delay < 0:
        issues.append(f"retry_delay must be non-negative, got: {config.crawl.retry_delay}.")

    if config.crawl.index_depth < 1:
        issues.append(f"index_depth must be >= 1, got: {config.crawl.index_depth}.")

    if config.crawl.min_article_words <= 0:
        issues.append(f"min_article_words must be > 0, got: {config.crawl.min_article_words}.")

    return issues


def save_default_config(destination_path: Path) -> None:
    """Write the bundled default configuration YAML to destination_path.

    Creates parent directories as needed.

    Args:
        destination_path: Where to write the default config file.

    Raises:
        FileExistsError: If a file already exists at destination_path.
        FileNotFoundError: If the bundled default config does not exist.
    """
    if destination_path.exists():
        raise FileExistsError(f"Configuration file already exists: {destination_path}")

    source_path = get_default_config_path()
    if not source_path.exists():
        raise FileNotFoundError(f"Bundled default config not found: {source_path}")

    destination_path.parent.mkdir(parents=True, exist_ok=True)
    destination_path.write_bytes(source_path.read_bytes())
