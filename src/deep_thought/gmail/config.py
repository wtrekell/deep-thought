"""YAML configuration loader with .env integration for the Gmail Tool."""

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
    """Configuration for a single email collection rule."""

    name: str
    query: str
    ai_instructions: str | None
    actions: list[str]
    append_mode: bool


@dataclass
class GmailConfig:
    """Top-level configuration for the Gmail Tool."""

    credentials_path: str
    token_path: str
    scopes: list[str]
    gemini_api_key_env: str
    gemini_model: str
    gemini_rate_limit_rpm: int
    gmail_rate_limit_rpm: int
    retry_max_attempts: int
    retry_base_delay_seconds: int
    max_emails_per_run: int
    clean_newsletters: bool
    decision_cache_ttl: int
    output_dir: str
    generate_llms_files: bool
    flat_output: bool
    rules: list[RuleConfig]


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

_PACKAGE_DIR = Path(__file__).resolve().parent
_BUNDLED_DEFAULT_CONFIG = _PACKAGE_DIR / "default-config.yaml"
_PROJECT_CONFIG_RELATIVE_PATH = Path("src") / "config" / "gmail-configuration.yaml"


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
        Absolute path to src/config/gmail-configuration.yaml in the calling repo.
    """
    return Path.cwd() / _PROJECT_CONFIG_RELATIVE_PATH


# ---------------------------------------------------------------------------
# Valid action patterns
# ---------------------------------------------------------------------------

_SIMPLE_ACTIONS = {"archive", "mark_read", "trash", "delete"}
_PARAMETERIZED_ACTION_PREFIXES = ("label:", "remove_label:", "forward:")


def _is_valid_action(action: str) -> bool:
    """Check whether an action string matches a known action pattern.

    Args:
        action: An action string like 'archive', 'label:Processed', or 'forward:user@example.com'.

    Returns:
        True if the action is recognised, False otherwise.
    """
    if action in _SIMPLE_ACTIONS:
        return True
    return any(action.startswith(prefix) and len(action) > len(prefix) for prefix in _PARAMETERIZED_ACTION_PREFIXES)


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def _parse_rule_config(raw_rule: dict[str, Any]) -> RuleConfig:
    """Parse a single rule block from the YAML rules list.

    Args:
        raw_rule: A raw YAML dict for one rule entry.

    Returns:
        A fully populated RuleConfig.

    Raises:
        ValueError: If required fields like 'name' or 'query' are missing.
    """
    rule_name = raw_rule.get("name")
    if not rule_name:
        raise ValueError("Each rule must have a 'name' field.")

    rule_name_str = str(rule_name)
    if "/" in rule_name_str or "\\" in rule_name_str or rule_name_str.startswith("."):
        raise ValueError(f"Invalid rule name '{rule_name_str}': must not contain path separators or start with a dot.")

    query = raw_rule.get("query")
    if not query:
        raise ValueError(f"Rule '{rule_name}' must have a 'query' field.")

    raw_ai_instructions = raw_rule.get("ai_instructions")
    ai_instructions: str | None = str(raw_ai_instructions) if raw_ai_instructions is not None else None

    raw_actions = raw_rule.get("actions")
    actions: list[str] = list(raw_actions) if isinstance(raw_actions, list) else []

    return RuleConfig(
        name=str(rule_name),
        query=str(query),
        ai_instructions=ai_instructions,
        actions=actions,
        append_mode=bool(raw_rule.get("append_mode", False)),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_config(config_path: Path | None = None) -> GmailConfig:
    """Load the YAML configuration and return a typed GmailConfig.

    If config_path is None, the default path is used
    (src/config/gmail-configuration.yaml relative to the project root).

    Args:
        config_path: Optional explicit path to the YAML configuration file.

    Returns:
        A fully parsed GmailConfig.

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

    raw_scopes = raw_dict.get("scopes")
    scopes: list[str] = list(raw_scopes) if isinstance(raw_scopes, list) else ["https://mail.google.com/"]

    def _resolve_path(raw_value: object, default: str) -> str:
        """Return an absolute path string, resolving relative paths against CWD."""
        path = Path(str(raw_value)) if raw_value else Path(default)
        return str(path if path.is_absolute() else Path.cwd() / path)

    return GmailConfig(
        credentials_path=_resolve_path(raw_dict.get("credentials_path"), "src/config/gmail/credentials.json"),
        token_path=_resolve_path(raw_dict.get("token_path"), "data/gmail/token.json"),
        scopes=scopes,
        gemini_api_key_env=str(raw_dict.get("gemini_api_key_env", "GEMINI_API_KEY")),
        gemini_model=str(raw_dict.get("gemini_model", "gemini-2.5-flash")),
        gemini_rate_limit_rpm=int(raw_dict.get("gemini_rate_limit_rpm", 15)),
        gmail_rate_limit_rpm=int(raw_dict.get("gmail_rate_limit_rpm", 250)),
        retry_max_attempts=int(raw_dict.get("retry_max_attempts", 3)),
        retry_base_delay_seconds=int(raw_dict.get("retry_base_delay_seconds", 1)),
        max_emails_per_run=int(raw_dict.get("max_emails_per_run", 100)),
        clean_newsletters=bool(raw_dict.get("clean_newsletters", True)),
        decision_cache_ttl=int(raw_dict.get("decision_cache_ttl", 3600)),
        output_dir=str(raw_dict.get("output_dir", "data/gmail/export/")),
        generate_llms_files=bool(raw_dict.get("generate_llms_files", False)),
        flat_output=bool(raw_dict.get("flat_output", False)),
        rules=rules,
    )


def validate_config(config: GmailConfig) -> list[str]:
    """Validate the loaded configuration and return a list of warning/error messages.

    An empty list means the configuration is valid.

    Args:
        config: A loaded GmailConfig to validate.

    Returns:
        A list of human-readable issue strings. Empty list means no issues.
    """
    issues: list[str] = []

    if not config.credentials_path:
        issues.append("credentials_path is empty — cannot locate OAuth client secret.")

    if not config.token_path:
        issues.append("token_path is empty — cannot store OAuth tokens.")

    if not config.scopes:
        issues.append("No OAuth scopes configured — the tool will not be able to access Gmail.")

    if not config.rules:
        issues.append("No rules configured — nothing will be collected. Add at least one rule under 'rules'.")

    if config.max_emails_per_run <= 0:
        issues.append(f"max_emails_per_run must be > 0, got: {config.max_emails_per_run}.")

    if config.retry_max_attempts <= 0:
        issues.append(f"retry_max_attempts must be > 0, got: {config.retry_max_attempts}.")

    if config.decision_cache_ttl < 0:
        issues.append(f"decision_cache_ttl must be >= 0, got: {config.decision_cache_ttl}.")

    seen_rule_names: set[str] = set()
    for rule in config.rules:
        if rule.name in seen_rule_names:
            issues.append(f"Duplicate rule name: '{rule.name}'. Rule names must be unique.")
        seen_rule_names.add(rule.name)

        for action in rule.actions:
            if not _is_valid_action(action):
                issues.append(
                    f"Rule '{rule.name}': unknown action '{action}'. "
                    f"Valid actions: archive, label:{{name}}, remove_label:{{name}}, "
                    f"forward:{{address}}, mark_read, trash, delete."
                )

    return issues


def get_gemini_api_key(config: GmailConfig) -> str:
    """Read the Gemini API key from the environment variable named in config.

    Args:
        config: A loaded GmailConfig specifying which env var holds the API key.

    Returns:
        The Gemini API key string.

    Raises:
        OSError: If the environment variable is not set or empty.
    """
    api_key = os.environ.get(config.gemini_api_key_env)
    if not api_key:
        raise OSError(
            f"Gemini API key not found. Set the '{config.gemini_api_key_env}' environment variable "
            "(either in your shell or in a .env file at the project root)."
        )
    return api_key
