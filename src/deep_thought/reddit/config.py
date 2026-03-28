"""YAML configuration loader with .env integration for the Reddit Tool."""

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
class RuleConfig:
    """Configuration for a single collection rule targeting one subreddit."""

    name: str
    subreddit: str
    sort: str
    time_filter: str
    limit: int
    min_score: int
    min_comments: int
    max_age_days: int
    include_keywords: list[str]
    exclude_keywords: list[str]
    include_flair: list[str]
    exclude_flair: list[str]
    search_comments: bool
    max_comment_depth: int
    max_comments: int
    include_images: bool


@dataclass
class RedditConfig:
    """Top-level configuration for the Reddit Tool."""

    client_id_env: str
    client_secret_env: str
    user_agent_env: str
    max_posts_per_run: int
    output_dir: str
    generate_llms_files: bool
    rules: list[RuleConfig]


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

_PACKAGE_DIR = Path(__file__).resolve().parent
_BUNDLED_DEFAULT_CONFIG = _PACKAGE_DIR / "default-config.yaml"
_PROJECT_CONFIG_RELATIVE_PATH = Path("src") / "config" / "reddit-configuration.yaml"


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
        Absolute path to src/config/reddit-configuration.yaml in the calling repo.
    """
    return Path.cwd() / _PROJECT_CONFIG_RELATIVE_PATH


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

_VALID_SORT_VALUES = {"new", "hot", "top", "rising"}
_VALID_TIME_FILTER_VALUES = {"hour", "day", "week", "month", "year", "all"}


def _parse_rule_config(raw_rule: dict[str, Any]) -> RuleConfig:
    """Parse a single rule block from the YAML rules list.

    Args:
        raw_rule: A raw YAML dict for one rule entry.

    Returns:
        A fully populated RuleConfig.

    Raises:
        ValueError: If required fields like 'name' or 'subreddit' are missing.
    """
    rule_name = raw_rule.get("name")
    if not rule_name:
        raise ValueError("Each rule must have a 'name' field.")

    subreddit = raw_rule.get("subreddit")
    if not subreddit:
        raise ValueError(f"Rule '{rule_name}' must have a 'subreddit' field.")

    raw_include_keywords = raw_rule.get("include_keywords")
    include_keywords: list[str] = list(raw_include_keywords) if isinstance(raw_include_keywords, list) else []

    raw_exclude_keywords = raw_rule.get("exclude_keywords")
    exclude_keywords: list[str] = list(raw_exclude_keywords) if isinstance(raw_exclude_keywords, list) else []

    raw_include_flair = raw_rule.get("include_flair")
    include_flair: list[str] = list(raw_include_flair) if isinstance(raw_include_flair, list) else []

    raw_exclude_flair = raw_rule.get("exclude_flair")
    exclude_flair: list[str] = list(raw_exclude_flair) if isinstance(raw_exclude_flair, list) else []

    return RuleConfig(
        name=str(rule_name),
        subreddit=str(subreddit),
        sort=str(raw_rule.get("sort", "hot")),
        time_filter=str(raw_rule.get("time_filter", "week")),
        limit=int(raw_rule.get("limit", 25)),
        min_score=int(raw_rule.get("min_score", 0)),
        min_comments=int(raw_rule.get("min_comments", 0)),
        max_age_days=int(raw_rule.get("max_age_days", 7)),
        include_keywords=include_keywords,
        exclude_keywords=exclude_keywords,
        include_flair=include_flair,
        exclude_flair=exclude_flair,
        search_comments=bool(raw_rule.get("search_comments", False)),
        max_comment_depth=int(raw_rule.get("max_comment_depth", 3)),
        max_comments=int(raw_rule.get("max_comments", 200)),
        include_images=bool(raw_rule.get("include_images", False)),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_config(config_path: Path | None = None) -> RedditConfig:
    """Load the YAML configuration and return a typed RedditConfig.

    If config_path is None, the default path is used
    (src/config/reddit-configuration.yaml relative to the project root).

    Args:
        config_path: Optional explicit path to the YAML configuration file.

    Returns:
        A fully parsed RedditConfig.

    Raises:
        FileNotFoundError: If the configuration file does not exist.
        ValueError: If the file does not contain a valid YAML mapping or rule data is invalid.
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

    raw_rules = raw_dict.get("rules")
    rules: list[RuleConfig] = []
    if isinstance(raw_rules, list):
        for raw_rule_item in raw_rules:
            if isinstance(raw_rule_item, dict):
                rules.append(_parse_rule_config(raw_rule_item))

    return RedditConfig(
        client_id_env=str(raw_dict.get("client_id_env", "REDDIT_CLIENT_ID")),
        client_secret_env=str(raw_dict.get("client_secret_env", "REDDIT_CLIENT_SECRET")),
        user_agent_env=str(raw_dict.get("user_agent_env", "REDDIT_USER_AGENT")),
        max_posts_per_run=int(raw_dict.get("max_posts_per_run", 500)),
        output_dir=str(raw_dict.get("output_dir", "data/reddit/export/")),
        generate_llms_files=bool(raw_dict.get("generate_llms_files", False)),
        rules=rules,
    )


def validate_config(config: RedditConfig) -> list[str]:
    """Validate the loaded configuration and return a list of warning/error messages.

    An empty list means the configuration is valid.

    Args:
        config: A loaded RedditConfig to validate.

    Returns:
        A list of human-readable issue strings. Empty list means no issues.
    """
    issues: list[str] = []

    if not config.client_id_env:
        issues.append("client_id_env is empty — cannot determine which env var holds the Reddit client ID.")

    if not config.client_secret_env:
        issues.append("client_secret_env is empty — cannot determine which env var holds the Reddit client secret.")

    if not config.user_agent_env:
        issues.append("user_agent_env is empty — cannot determine which env var holds the Reddit user agent.")

    if not config.rules:
        issues.append("No rules configured — nothing will be collected. Add at least one rule under 'rules'.")

    if config.max_posts_per_run <= 0:
        issues.append(f"max_posts_per_run must be > 0, got: {config.max_posts_per_run}.")

    seen_rule_names: set[str] = set()
    for rule in config.rules:
        if rule.name in seen_rule_names:
            issues.append(f"Duplicate rule name: '{rule.name}'. Rule names must be unique.")
        seen_rule_names.add(rule.name)

        if rule.sort not in _VALID_SORT_VALUES:
            issues.append(
                f"Rule '{rule.name}': sort '{rule.sort}' is not valid. Must be one of: {sorted(_VALID_SORT_VALUES)}."
            )

        if rule.sort == "top" and rule.time_filter not in _VALID_TIME_FILTER_VALUES:
            issues.append(
                f"Rule '{rule.name}': time_filter '{rule.time_filter}' is not valid for sort='top'. "
                f"Must be one of: {sorted(_VALID_TIME_FILTER_VALUES)}."
            )

        if rule.limit <= 0:
            issues.append(f"Rule '{rule.name}': limit must be > 0, got: {rule.limit}.")

        if rule.max_age_days <= 0:
            issues.append(f"Rule '{rule.name}': max_age_days must be > 0, got: {rule.max_age_days}.")

        if rule.max_comment_depth < 0:
            issues.append(f"Rule '{rule.name}': max_comment_depth must be >= 0, got: {rule.max_comment_depth}.")

        if rule.max_comments <= 0:
            issues.append(f"Rule '{rule.name}': max_comments must be > 0, got: {rule.max_comments}.")

    return issues


def get_credentials(config: RedditConfig) -> tuple[str, str, str]:
    """Read Reddit API credentials from environment variables named in config.

    Args:
        config: A loaded RedditConfig specifying which env var names to read.

    Returns:
        A tuple of (client_id, client_secret, user_agent).

    Raises:
        OSError: If any of the required environment variables are not set or empty.
    """
    client_id = os.environ.get(config.client_id_env)
    if not client_id:
        raise OSError(
            f"Reddit client ID not found. Set the '{config.client_id_env}' environment variable "
            "(either in your shell or in a .env file at the project root)."
        )

    client_secret = os.environ.get(config.client_secret_env)
    if not client_secret:
        raise OSError(
            f"Reddit client secret not found. Set the '{config.client_secret_env}' environment variable "
            "(either in your shell or in a .env file at the project root)."
        )

    user_agent = os.environ.get(config.user_agent_env)
    if not user_agent:
        raise OSError(
            f"Reddit user agent not found. Set the '{config.user_agent_env}' environment variable "
            "(either in your shell or in a .env file at the project root)."
        )

    return client_id, client_secret, user_agent
