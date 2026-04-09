"""YAML configuration loader with .env integration for the Todoist Tool."""

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
class FilterConfig:
    include: list[str]
    exclude: list[str]


@dataclass
class PullFilters:
    labels: FilterConfig
    projects: FilterConfig
    sections: FilterConfig
    assignee: FilterConfig
    has_due_date: bool | None  # None = all, True = only with due date, False = only without


@dataclass
class PushFilters:
    labels: FilterConfig
    assignee: FilterConfig
    conflict_resolution: str  # "prompt", "remote_wins", "local_wins"
    require_confirmation: bool


@dataclass
class CommentConfig:
    sync: bool
    include_attachments: bool


@dataclass
class ClaudeConfig:
    label: str | None
    repo: str | None
    branch: str


@dataclass
class TodoistConfig:
    api_token_env: str
    projects: list[str]  # project names
    pull_filters: PullFilters
    push_filters: PushFilters
    comments: CommentConfig
    claude: ClaudeConfig


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

_PACKAGE_DIR = Path(__file__).resolve().parent
_BUNDLED_DEFAULT_CONFIG = _PACKAGE_DIR / "default-config.yaml"
_PROJECT_CONFIG_RELATIVE_PATH = Path("src") / "config" / "todoist-configuration.yaml"


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
        Absolute path to src/config/todoist-configuration.yaml in the calling repo.
    """
    return Path.cwd() / _PROJECT_CONFIG_RELATIVE_PATH


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def _parse_filter_config(raw_filter: dict[str, Any], *, require_exclude: bool = True) -> FilterConfig:
    """Parse a filter block that contains include/exclude lists."""
    include: list[str] = raw_filter.get("include") or []
    exclude: list[str] = []
    if require_exclude:
        exclude = raw_filter.get("exclude") or []
    return FilterConfig(include=include, exclude=exclude)


def _parse_pull_filters(raw_filters: dict[str, Any]) -> PullFilters:
    """Parse the pull filters section of the YAML configuration."""
    raw_pull: dict[str, Any] = raw_filters.get("pull", {})

    labels = _parse_filter_config(raw_pull.get("labels", {}))
    projects = _parse_filter_config(raw_pull.get("projects", {}), require_exclude=False)
    sections = _parse_filter_config(raw_pull.get("sections", {}))
    assignee = _parse_filter_config(raw_pull.get("assignee", {}), require_exclude=False)

    raw_due: dict[str, Any] = raw_pull.get("due", {})
    has_due_date: bool | None = raw_due.get("has_due_date")

    return PullFilters(
        labels=labels,
        projects=projects,
        sections=sections,
        assignee=assignee,
        has_due_date=has_due_date,
    )


def _parse_push_filters(raw_filters: dict[str, Any]) -> PushFilters:
    """Parse the push filters section of the YAML configuration."""
    raw_push: dict[str, Any] = raw_filters.get("push", {})

    labels = _parse_filter_config(raw_push.get("labels", {}))
    assignee = _parse_filter_config(raw_push.get("assignee", {}), require_exclude=False)
    conflict_resolution: str = raw_push.get("conflict_resolution", "prompt")
    require_confirmation: bool = raw_push.get("require_confirmation", True)

    return PushFilters(
        labels=labels,
        assignee=assignee,
        conflict_resolution=conflict_resolution,
        require_confirmation=require_confirmation,
    )


def _parse_comment_config(raw_comments: dict[str, Any]) -> CommentConfig:
    """Parse the comments section of the YAML configuration."""
    return CommentConfig(
        sync=raw_comments.get("sync", True),
        include_attachments=raw_comments.get("include_attachments", False),
    )


def _parse_claude_config(raw_claude: dict[str, Any]) -> ClaudeConfig:
    """Parse the claude section of the YAML configuration."""
    raw_role: dict[str, Any] = raw_claude.get("role", {})
    raw_label = raw_claude.get("label")
    raw_repo = raw_role.get("repo")
    return ClaudeConfig(
        label=raw_label if raw_label else None,
        repo=raw_repo if raw_repo else None,
        branch=raw_role.get("branch", "main"),
    )


def _parse_projects(raw_projects: list[dict[str, Any]] | None) -> list[str]:
    """Extract project names from the projects list."""
    if not raw_projects:
        return []
    return [entry["name"] for entry in raw_projects if "name" in entry]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_config(config_path: Path | None = None) -> TodoistConfig:
    """Load the YAML configuration, integrate .env variables, and return a typed config.

    If config_path is None the default path is used (configuration/todoist-configuration.yaml
    relative to the project root).
    """
    load_dotenv()

    resolved_path = config_path if config_path is not None else get_default_config_path()

    if not resolved_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {resolved_path}")

    with resolved_path.open("r", encoding="utf-8") as config_file:
        raw: dict[str, Any] = yaml.safe_load(config_file)

    if not isinstance(raw, dict):
        raise ValueError(f"Configuration file must contain a YAML mapping, got: {type(raw).__name__}")

    raw_todoist: dict[str, Any] = raw.get("todoist") or {}
    api_token_env: str = raw_todoist.get("api_token_env", "TODOIST_API_TOKEN")

    raw_projects: list[dict[str, Any]] = raw.get("projects") or []
    project_names = _parse_projects(raw_projects)

    raw_filters: dict[str, Any] = raw.get("filters") or {}
    pull_filters = _parse_pull_filters(raw_filters)
    push_filters = _parse_push_filters(raw_filters)

    raw_comments: dict[str, Any] = raw.get("comments") or {}
    comment_config = _parse_comment_config(raw_comments)

    raw_claude: dict[str, Any] = raw.get("claude") or {}
    claude_config = _parse_claude_config(raw_claude)

    return TodoistConfig(
        api_token_env=api_token_env,
        projects=project_names,
        pull_filters=pull_filters,
        push_filters=push_filters,
        comments=comment_config,
        claude=claude_config,
    )


def get_api_token(config: TodoistConfig) -> str:
    """Read the API token from macOS Keychain or the environment variable named in config.

    Checks Keychain first (service ``deep-thought-todoist``, key ``api-token``),
    then falls back to the environment variable specified by ``config.api_token_env``.

    Raises OSError if neither source has the token.
    """
    from deep_thought.secrets import get_secret

    return get_secret("todoist", "api-token", env_var=config.api_token_env)


_VALID_CONFLICT_RESOLUTION_VALUES = {"prompt", "remote_wins", "local_wins"}


def validate_config(config: TodoistConfig) -> list[str]:
    """Validate the loaded configuration and return a list of warning/error messages.

    An empty list means the configuration is valid.
    """
    issues: list[str] = []

    if not config.api_token_env:
        issues.append("todoist.api_token_env is empty — cannot determine which env var holds the API token.")

    if not config.projects and not config.pull_filters.labels.include:
        issues.append(
            "No projects configured and no pull label filters set — nothing will be synced. "
            "Add at least one project under 'projects', or set filters.pull.labels.include."
        )

    if config.push_filters.conflict_resolution not in _VALID_CONFLICT_RESOLUTION_VALUES:
        issues.append(
            f"push.conflict_resolution '{config.push_filters.conflict_resolution}' is not valid. "
            f"Must be one of: {sorted(_VALID_CONFLICT_RESOLUTION_VALUES)}."
        )

    if config.claude.label and not config.claude.repo:
        issues.append(
            "claude.label is set but claude.role.repo is empty. "
            "Tasks marked with the Claude label will lack a repository reference."
        )

    return issues
