"""Tests for the configuration loader in deep_thought.todoist.config."""

from __future__ import annotations

from pathlib import Path

import pytest

from deep_thought.todoist.config import (
    TodoistConfig,
    _parse_filter_config,
    _parse_projects,
    get_api_token,
    load_config,
    validate_config,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# load_config — file loading and parsing
# ---------------------------------------------------------------------------


class TestLoadConfig:
    def test_loads_valid_config_from_yaml(self) -> None:
        """A well-formed YAML config file must parse without errors."""
        config = load_config(FIXTURES_DIR / "test_config.yaml")
        assert isinstance(config, TodoistConfig)

    def test_api_token_env_parsed(self) -> None:
        """api_token_env must be read from the todoist.api_token_env key."""
        config = load_config(FIXTURES_DIR / "test_config.yaml")
        assert config.api_token_env == "TEST_TODOIST_API_TOKEN"

    def test_projects_list_parsed(self) -> None:
        """Project names must be extracted from the projects list."""
        config = load_config(FIXTURES_DIR / "test_config.yaml")
        assert "Work" in config.projects
        assert "Personal" in config.projects

    def test_pull_filters_parsed(self) -> None:
        """Pull filter values must be read from the filters.pull block."""
        config = load_config(FIXTURES_DIR / "test_config.yaml")
        assert "urgent" in config.pull_filters.labels.include
        assert "personal" in config.pull_filters.labels.exclude

    def test_push_filters_parsed(self) -> None:
        """Push filter values must be read from the filters.push block."""
        config = load_config(FIXTURES_DIR / "test_config.yaml")
        assert "claude-code" in config.push_filters.labels.include
        assert config.push_filters.conflict_resolution == "remote_wins"
        assert config.push_filters.require_confirmation is False

    def test_comments_config_parsed(self) -> None:
        """Comment sync settings must be read from the comments block."""
        config = load_config(FIXTURES_DIR / "test_config.yaml")
        assert config.comments.sync is True
        assert config.comments.include_attachments is False

    def test_claude_config_parsed(self) -> None:
        """Claude integration settings must be read from the claude block."""
        config = load_config(FIXTURES_DIR / "test_config.yaml")
        assert config.claude.label == "claude-code"
        assert config.claude.repo == "deep-thought"
        assert config.claude.branch == "main"

    @pytest.mark.error_handling
    def test_missing_file_raises_file_not_found(self, tmp_path: Path) -> None:
        """A path to a non-existent file must raise FileNotFoundError."""
        missing_path = tmp_path / "does_not_exist.yaml"
        with pytest.raises(FileNotFoundError, match="Configuration file not found"):
            load_config(missing_path)

    @pytest.mark.error_handling
    def test_invalid_yaml_raises_value_error(self, tmp_path: Path) -> None:
        """A YAML file that does not contain a mapping must raise ValueError."""
        bad_yaml_file = tmp_path / "bad.yaml"
        # A top-level list is not a mapping
        bad_yaml_file.write_text("- item1\n- item2\n", encoding="utf-8")
        with pytest.raises(ValueError, match="YAML mapping"):
            load_config(bad_yaml_file)

    def test_empty_filters_default_to_empty_lists(self, tmp_path: Path) -> None:
        """A config with no filter block must produce empty include/exclude lists."""
        minimal_yaml = tmp_path / "minimal.yaml"
        minimal_yaml.write_text(
            "todoist:\n  api_token_env: TOKEN\nprojects:\n  - name: Work\n",
            encoding="utf-8",
        )
        config = load_config(minimal_yaml)
        assert config.pull_filters.labels.include == []
        assert config.pull_filters.labels.exclude == []

    def test_has_due_date_none_when_not_set(self, tmp_path: Path) -> None:
        """has_due_date must be None when not specified in the YAML."""
        minimal_yaml = tmp_path / "minimal.yaml"
        minimal_yaml.write_text(
            "todoist:\n  api_token_env: TOKEN\nprojects:\n  - name: Work\n",
            encoding="utf-8",
        )
        config = load_config(minimal_yaml)
        assert config.pull_filters.has_due_date is None

    def test_has_due_date_true_when_set(self, tmp_path: Path) -> None:
        """has_due_date must be True when configured in the YAML."""
        yaml_content = (
            "todoist:\n  api_token_env: TOKEN\n"
            "projects:\n  - name: Work\n"
            "filters:\n  pull:\n    due:\n      has_due_date: true\n"
        )
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")
        config = load_config(yaml_file)
        assert config.pull_filters.has_due_date is True


# ---------------------------------------------------------------------------
# get_api_token
# ---------------------------------------------------------------------------


class TestGetApiToken:
    def test_returns_token_when_env_var_is_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """get_api_token must return the token value when the env var is set."""
        monkeypatch.setenv("TEST_TODOIST_API_TOKEN", "secret-token-value")
        config = load_config(FIXTURES_DIR / "test_config.yaml")
        token = get_api_token(config)
        assert token == "secret-token-value"

    @pytest.mark.error_handling
    def test_raises_os_error_when_env_var_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """get_api_token must raise OSError when the env var is not set."""
        monkeypatch.delenv("TEST_TODOIST_API_TOKEN", raising=False)
        config = load_config(FIXTURES_DIR / "test_config.yaml")
        with pytest.raises(OSError, match="TEST_TODOIST_API_TOKEN"):
            get_api_token(config)

    @pytest.mark.error_handling
    def test_raises_os_error_when_env_var_is_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """get_api_token must raise OSError when the env var is set but empty."""
        monkeypatch.setenv("TEST_TODOIST_API_TOKEN", "")
        config = load_config(FIXTURES_DIR / "test_config.yaml")
        with pytest.raises(OSError):
            get_api_token(config)


# ---------------------------------------------------------------------------
# validate_config
# ---------------------------------------------------------------------------


class TestValidateConfig:
    def test_valid_config_returns_empty_list(self) -> None:
        """A fully valid config must produce no issues."""
        config = load_config(FIXTURES_DIR / "test_config.yaml")
        issues = validate_config(config)
        assert issues == []

    def test_empty_api_token_env_is_flagged(self, tmp_path: Path) -> None:
        """An empty api_token_env must appear in the issues list."""
        yaml_content = (
            "todoist:\n  api_token_env: ''\n"
            "projects:\n  - name: Work\n"
            "filters:\n  push:\n    conflict_resolution: prompt\n"
        )
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")
        config = load_config(yaml_file)
        issues = validate_config(config)
        assert any("api_token_env" in issue for issue in issues)

    def test_no_projects_is_flagged(self, tmp_path: Path) -> None:
        """An empty projects list must appear in the issues list."""
        yaml_content = "todoist:\n  api_token_env: TOKEN\nprojects: []\n"
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")
        config = load_config(yaml_file)
        issues = validate_config(config)
        assert any("project" in issue.lower() for issue in issues)

    def test_invalid_conflict_resolution_is_flagged(self, tmp_path: Path) -> None:
        """An unrecognized conflict_resolution value must appear in the issues list."""
        yaml_content = (
            "todoist:\n  api_token_env: TOKEN\n"
            "projects:\n  - name: Work\n"
            "filters:\n  push:\n    conflict_resolution: invalid_value\n"
        )
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")
        config = load_config(yaml_file)
        issues = validate_config(config)
        assert any("conflict_resolution" in issue for issue in issues)

    def test_claude_label_without_repo_is_flagged(self, tmp_path: Path) -> None:
        """Setting claude.label without claude.role.repo must produce a warning."""
        yaml_content = (
            "todoist:\n  api_token_env: TOKEN\n"
            "projects:\n  - name: Work\n"
            "claude:\n  label: claude-code\n  role:\n    repo: ''\n    branch: main\n"
        )
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")
        config = load_config(yaml_file)
        issues = validate_config(config)
        assert any("repo" in issue for issue in issues)

    def test_multiple_issues_all_returned(self, tmp_path: Path) -> None:
        """validate_config must collect all issues, not stop at the first one."""
        yaml_content = "todoist:\n  api_token_env: ''\nprojects: []\n"
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")
        config = load_config(yaml_file)
        issues = validate_config(config)
        # Both the empty api_token_env and empty projects must be reported
        assert len(issues) >= 2


# ---------------------------------------------------------------------------
# _parse_filter_config (internal helper)
# ---------------------------------------------------------------------------


class TestParseFilterConfig:
    def test_empty_dict_produces_empty_lists(self) -> None:
        filter_config = _parse_filter_config({})
        assert filter_config.include == []
        assert filter_config.exclude == []

    def test_include_and_exclude_populated(self) -> None:
        raw: dict[str, list[str]] = {"include": ["a", "b"], "exclude": ["c"]}
        filter_config = _parse_filter_config(raw)
        assert filter_config.include == ["a", "b"]
        assert filter_config.exclude == ["c"]

    def test_require_exclude_false_omits_exclude(self) -> None:
        """When require_exclude=False, the exclude key is ignored."""
        raw: dict[str, list[str]] = {"include": ["x"], "exclude": ["y"]}
        filter_config = _parse_filter_config(raw, require_exclude=False)
        assert filter_config.include == ["x"]
        assert filter_config.exclude == []

    def test_none_values_treated_as_empty(self) -> None:
        raw: dict[str, None] = {"include": None, "exclude": None}
        filter_config = _parse_filter_config(raw)
        assert filter_config.include == []
        assert filter_config.exclude == []


# ---------------------------------------------------------------------------
# _parse_projects (internal helper)
# ---------------------------------------------------------------------------


class TestParseProjects:
    def test_extracts_names_from_list(self) -> None:
        raw = [{"name": "Work"}, {"name": "Personal"}]
        result = _parse_projects(raw)
        assert result == ["Work", "Personal"]

    def test_entries_without_name_key_are_skipped(self) -> None:
        raw: list[dict[str, str]] = [{"name": "Work"}, {"other_key": "ignored"}]
        result = _parse_projects(raw)
        assert result == ["Work"]

    def test_empty_list_returns_empty(self) -> None:
        assert _parse_projects([]) == []
