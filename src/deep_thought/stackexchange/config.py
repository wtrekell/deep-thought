"""YAML configuration loader with .env integration for the Stack Exchange Tool."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class TagConfig:
    """Tag filtering configuration for a single collection rule.

    Attributes:
        include: All of these tags must be present on a question for it to match.
        any: At least one of these tags must be present (in addition to include tags).
             An empty list means no additional tag constraint is applied.
    """

    include: list[str]
    any: list[str]


@dataclass
class RuleConfig:
    """Configuration for a single collection rule targeting one Stack Exchange site."""

    name: str
    site: str
    tags: TagConfig
    sort: str
    order: str
    min_score: int
    min_answers: int
    only_answered: bool
    max_age_days: int
    keywords: list[str]
    max_questions: int
    max_answers_per_question: int
    include_comments: bool
    max_comments_per_question: int


@dataclass
class StackExchangeConfig:
    """Top-level configuration for the Stack Exchange Tool."""

    api_key_env: str
    max_questions_per_run: int
    output_dir: str
    generate_llms_files: bool
    qdrant_collection: str
    rules: list[RuleConfig]


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

_PACKAGE_DIR = Path(__file__).resolve().parent
_BUNDLED_DEFAULT_CONFIG = _PACKAGE_DIR / "default-config.yaml"
_PROJECT_CONFIG_RELATIVE_PATH = Path("src") / "config" / "stackexchange-configuration.yaml"


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
        Absolute path to src/config/stackexchange-configuration.yaml in the calling repo.
    """
    return Path.cwd() / _PROJECT_CONFIG_RELATIVE_PATH


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

_VALID_SORT_VALUES = {"activity", "votes", "creation"}
_VALID_ORDER_VALUES = {"asc", "desc"}

# Rule names are used as subdirectory names within the output directory.
# Restrict to alphanumerics, hyphens, and underscores to prevent path traversal.
_SAFE_RULE_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")


def _parse_tag_config(raw_tags: Any) -> TagConfig:
    """Parse the tags block from a rule config dict.

    Args:
        raw_tags: The raw YAML value for the 'tags' key, expected to be a dict
                  with optional 'include' and 'any' list fields.

    Returns:
        A TagConfig with both lists normalized to list[str].
    """
    if not isinstance(raw_tags, dict):
        return TagConfig(include=[], any=[])

    raw_include = raw_tags.get("include")
    include_tags: list[str] = [str(tag) for tag in raw_include] if isinstance(raw_include, list) else []

    raw_any = raw_tags.get("any")
    any_tags: list[str] = [str(tag) for tag in raw_any] if isinstance(raw_any, list) else []

    return TagConfig(include=include_tags, any=any_tags)


def _parse_rule_config(raw_rule: dict[str, Any]) -> RuleConfig:
    """Parse a single rule block from the YAML rules list.

    Args:
        raw_rule: A raw YAML dict for one rule entry.

    Returns:
        A fully populated RuleConfig.

    Raises:
        ValueError: If required fields like 'name' or 'site' are missing.
    """
    rule_name = raw_rule.get("name")
    if not rule_name:
        raise ValueError("Each rule must have a 'name' field.")

    site = raw_rule.get("site")
    if not site:
        raise ValueError(f"Rule '{rule_name}' must have a 'site' field.")

    raw_keywords = raw_rule.get("keywords")
    keywords: list[str] = [str(kw) for kw in raw_keywords] if isinstance(raw_keywords, list) else []

    return RuleConfig(
        name=str(rule_name),
        site=str(site),
        tags=_parse_tag_config(raw_rule.get("tags", {})),
        sort=str(raw_rule.get("sort", "votes")),
        order=str(raw_rule.get("order", "desc")),
        min_score=int(raw_rule.get("min_score", 0)),
        min_answers=int(raw_rule.get("min_answers", 0)),
        only_answered=bool(raw_rule.get("only_answered", False)),
        max_age_days=int(raw_rule.get("max_age_days", 365)),
        keywords=keywords,
        max_questions=int(raw_rule.get("max_questions", 50)),
        max_answers_per_question=int(raw_rule.get("max_answers_per_question", 5)),
        include_comments=bool(raw_rule.get("include_comments", False)),
        max_comments_per_question=int(raw_rule.get("max_comments_per_question", 30)),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_config(config_path: Path | None = None) -> StackExchangeConfig:
    """Load the YAML configuration and return a typed StackExchangeConfig.

    Calls load_dotenv() first so that any .env file values are available when
    the caller later resolves the API key via get_api_key().

    If config_path is None, the default path is used
    (src/config/stackexchange-configuration.yaml relative to the project root).

    Args:
        config_path: Optional explicit path to the YAML configuration file.

    Returns:
        A fully parsed StackExchangeConfig.

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

    return StackExchangeConfig(
        api_key_env=str(raw_dict.get("api_key_env", "STACKEXCHANGE_API_KEY")),
        max_questions_per_run=int(raw_dict.get("max_questions_per_run", 500)),
        output_dir=str(raw_dict.get("output_dir", "data/stackexchange/export/")),
        generate_llms_files=bool(raw_dict.get("generate_llms_files", True)),
        qdrant_collection=str(raw_dict.get("qdrant_collection", "deep_thought_db")),
        rules=rules,
    )


def validate_config(config: StackExchangeConfig) -> list[str]:
    """Validate the loaded configuration and return a list of warning/error messages.

    An empty list means the configuration is valid.

    Args:
        config: A loaded StackExchangeConfig to validate.

    Returns:
        A list of human-readable issue strings. Empty list means no issues.
    """
    issues: list[str] = []

    if not config.rules:
        issues.append("No rules configured — nothing will be collected. Add at least one rule under 'rules'.")

    if config.max_questions_per_run <= 0:
        issues.append(f"max_questions_per_run must be > 0, got: {config.max_questions_per_run}.")

    seen_rule_names: set[str] = set()
    for rule in config.rules:
        if rule.name in seen_rule_names:
            issues.append(f"Duplicate rule name: '{rule.name}'. Rule names must be unique.")
        seen_rule_names.add(rule.name)

        if not _SAFE_RULE_NAME_PATTERN.match(rule.name):
            issues.append(
                f"Rule name '{rule.name}' contains unsafe characters. "
                "Rule names may only contain alphanumerics, hyphens, and underscores."
            )

        if rule.sort not in _VALID_SORT_VALUES:
            issues.append(
                f"Rule '{rule.name}': sort '{rule.sort}' is not valid. Must be one of: {sorted(_VALID_SORT_VALUES)}."
            )

        if rule.order not in _VALID_ORDER_VALUES:
            issues.append(
                f"Rule '{rule.name}': order '{rule.order}' is not valid. Must be one of: {sorted(_VALID_ORDER_VALUES)}."
            )

        if rule.max_questions <= 0:
            issues.append(f"Rule '{rule.name}': max_questions must be > 0, got: {rule.max_questions}.")

        if rule.max_answers_per_question <= 0:
            issues.append(
                f"Rule '{rule.name}': max_answers_per_question must be > 0, got: {rule.max_answers_per_question}."
            )

        if rule.max_age_days <= 0:
            issues.append(f"Rule '{rule.name}': max_age_days must be > 0, got: {rule.max_age_days}.")

        if rule.min_score < 0:
            issues.append(f"Rule '{rule.name}': min_score must be >= 0, got: {rule.min_score}.")

        if rule.min_answers < 0:
            issues.append(f"Rule '{rule.name}': min_answers must be >= 0, got: {rule.min_answers}.")

        if rule.max_comments_per_question <= 0:
            issues.append(
                f"Rule '{rule.name}': max_comments_per_question must be > 0, got: {rule.max_comments_per_question}."
            )

    return issues


def get_api_key(config: StackExchangeConfig) -> str | None:
    """Read the Stack Exchange API key from macOS Keychain or environment variables.

    The API key is optional — the Stack Exchange API works without one at a
    reduced quota (300 requests/day vs 10,000/day with a key). Returns None
    rather than raising if no key is found.

    Args:
        config: A loaded StackExchangeConfig specifying the env var name to read.

    Returns:
        The API key string, or None if no key is configured.
    """
    from deep_thought.secrets import get_secret

    try:
        return get_secret("stackexchange", "api-key", env_var=config.api_key_env)
    except OSError:
        return None
