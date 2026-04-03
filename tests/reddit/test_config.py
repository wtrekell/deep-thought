"""Tests for the config loader in deep_thought.reddit.config.

Tests cover valid config loading, error cases, validation, and credential retrieval.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from deep_thought.reddit.config import (
    RedditConfig,
    RuleConfig,
    get_credentials,
    get_default_config_path,
    load_config,
    validate_config,
)
from tests.reddit.conftest import FIXTURES_DIR

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_CONFIG_PATH = FIXTURES_DIR / "test_config.yaml"


def _make_minimal_config() -> RedditConfig:
    """Return a minimal valid RedditConfig for use in validation tests."""
    return RedditConfig(
        client_id_env="REDDIT_CLIENT_ID",
        client_secret_env="REDDIT_CLIENT_SECRET",
        user_agent_env="REDDIT_USER_AGENT",
        max_posts_per_run=100,
        output_dir="data/reddit/export/",
        generate_llms_files=False,
        rules=[
            RuleConfig(
                name="test_rule",
                subreddit="python",
                sort="top",
                time_filter="week",
                limit=10,
                min_score=0,
                min_comments=0,
                max_age_days=7,
                include_keywords=[],
                exclude_keywords=[],
                include_flair=[],
                exclude_flair=[],
                search_comments=False,
                max_comment_depth=3,
                max_comments=200,
                include_images=False,
            )
        ],
    )


# ---------------------------------------------------------------------------
# get_default_config_path
# ---------------------------------------------------------------------------


class TestGetDefaultConfigPath:
    def test_returns_a_path_object(self) -> None:
        """get_default_config_path should return a Path object."""
        result = get_default_config_path()
        assert isinstance(result, Path)

    def test_path_ends_with_expected_filename(self) -> None:
        """The default config path should end with reddit-configuration.yaml."""
        result = get_default_config_path()
        assert result.name == "reddit-configuration.yaml"


# ---------------------------------------------------------------------------
# load_config
# ---------------------------------------------------------------------------


class TestLoadConfig:
    def test_loads_valid_config_from_fixture(self) -> None:
        """Loading the test fixture config should return a RedditConfig with one rule."""
        config = load_config(_VALID_CONFIG_PATH)
        assert isinstance(config, RedditConfig)
        assert len(config.rules) == 1
        assert config.rules[0].name == "test_rule"
        assert config.rules[0].subreddit == "python"

    def test_rule_fields_parsed_correctly(self) -> None:
        """Rule fields should be parsed with correct types from the YAML."""
        config = load_config(_VALID_CONFIG_PATH)
        rule = config.rules[0]
        assert rule.sort == "top"
        assert rule.time_filter == "week"
        assert rule.limit == 10
        assert rule.min_score == 10
        assert rule.min_comments == 2
        assert rule.max_age_days == 7
        assert rule.max_comment_depth == 2
        assert rule.max_comments == 50
        assert rule.include_images is False
        assert rule.search_comments is False

    def test_raises_file_not_found_for_missing_file(self) -> None:
        """Passing a non-existent path should raise FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="Configuration file not found"):
            load_config(Path("/nonexistent/path/config.yaml"))

    def test_raises_value_error_for_invalid_yaml(self, tmp_path: Path) -> None:
        """A YAML file that does not contain a mapping should raise ValueError."""
        bad_yaml = tmp_path / "bad.yaml"
        bad_yaml.write_text("- just\n- a\n- list\n", encoding="utf-8")
        with pytest.raises(ValueError, match="YAML mapping"):
            load_config(bad_yaml)

    def test_uses_default_path_when_none_given(self) -> None:
        """When config_path is None, load_config uses the default path (may not exist in test env)."""
        default_path = get_default_config_path()
        if default_path.exists():
            # If the default config exists, it should load without error
            config = load_config(None)
            assert isinstance(config, RedditConfig)
        else:
            with pytest.raises(FileNotFoundError):
                load_config(None)

    def test_empty_rules_list_is_valid_yaml(self, tmp_path: Path) -> None:
        """A YAML file with an empty rules list should parse without error."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            "client_id_env: REDDIT_CLIENT_ID\n"
            "client_secret_env: REDDIT_CLIENT_SECRET\n"
            "user_agent_env: REDDIT_USER_AGENT\n"
            "max_posts_per_run: 10\n"
            "output_dir: data/\n"
            "generate_llms_files: false\n"
            "rules: []\n",
            encoding="utf-8",
        )
        config = load_config(config_file)
        assert config.rules == []


# ---------------------------------------------------------------------------
# validate_config
# ---------------------------------------------------------------------------


class TestValidateConfig:
    def test_valid_config_returns_no_issues(self) -> None:
        """A fully valid config should produce an empty issues list."""
        config = _make_minimal_config()
        issues = validate_config(config)
        assert issues == []

    def test_empty_rules_produces_issue(self) -> None:
        """A config with no rules should produce a validation issue."""
        config = _make_minimal_config()
        config.rules = []
        issues = validate_config(config)
        assert any("No rules" in issue for issue in issues)

    def test_invalid_sort_produces_issue(self) -> None:
        """A rule with an invalid sort value should produce a validation issue."""
        config = _make_minimal_config()
        config.rules[0].sort = "random"
        issues = validate_config(config)
        assert any("sort" in issue for issue in issues)

    def test_invalid_time_filter_for_top_sort_produces_issue(self) -> None:
        """A 'top' rule with an invalid time_filter should produce a validation issue."""
        config = _make_minimal_config()
        config.rules[0].sort = "top"
        config.rules[0].time_filter = "yesterday"
        issues = validate_config(config)
        assert any("time_filter" in issue for issue in issues)

    def test_time_filter_not_validated_for_hot_sort(self) -> None:
        """time_filter should not be validated for non-top sorts."""
        config = _make_minimal_config()
        config.rules[0].sort = "hot"
        config.rules[0].time_filter = "any_value_is_fine"
        issues = validate_config(config)
        assert not any("time_filter" in issue for issue in issues)

    def test_duplicate_rule_names_produce_issue(self) -> None:
        """Two rules with the same name should produce a validation issue."""
        config = _make_minimal_config()
        second_rule = RuleConfig(
            name="test_rule",  # duplicate
            subreddit="learnpython",
            sort="hot",
            time_filter="week",
            limit=5,
            min_score=0,
            min_comments=0,
            max_age_days=7,
            include_keywords=[],
            exclude_keywords=[],
            include_flair=[],
            exclude_flair=[],
            search_comments=False,
            max_comment_depth=3,
            max_comments=50,
            include_images=False,
        )
        config.rules.append(second_rule)
        issues = validate_config(config)
        assert any("Duplicate rule name" in issue for issue in issues)

    def test_max_posts_per_run_zero_produces_issue(self) -> None:
        """max_posts_per_run of 0 should produce a validation issue."""
        config = _make_minimal_config()
        config.max_posts_per_run = 0
        issues = validate_config(config)
        assert any("max_posts_per_run" in issue for issue in issues)

    def test_negative_limit_produces_issue(self) -> None:
        """A rule with limit <= 0 should produce a validation issue."""
        config = _make_minimal_config()
        config.rules[0].limit = -1
        issues = validate_config(config)
        assert any("limit" in issue for issue in issues)

    def test_rule_name_with_path_traversal_produces_issue(self) -> None:
        """A rule name containing path separators must produce a validation issue.

        Rule names are used as subdirectory names. A name like '../../evil' or
        'my/rule' could escape the output directory when joined to a base path.
        """
        config = _make_minimal_config()
        config.rules[0].name = "../../evil"
        issues = validate_config(config)
        assert any("unsafe characters" in issue for issue in issues)

    def test_rule_name_with_slash_produces_issue(self) -> None:
        """A rule name containing a forward slash must produce a validation issue."""
        config = _make_minimal_config()
        config.rules[0].name = "my/rule"
        issues = validate_config(config)
        assert any("unsafe characters" in issue for issue in issues)

    def test_rule_name_with_alphanumerics_and_hyphens_is_valid(self) -> None:
        """A rule name using only alphanumerics, hyphens, and underscores must be valid."""
        config = _make_minimal_config()
        config.rules[0].name = "valid-rule_name123"
        issues = validate_config(config)
        assert not any("unsafe characters" in issue for issue in issues)


# ---------------------------------------------------------------------------
# get_credentials
# ---------------------------------------------------------------------------


class TestGetCredentials:
    @pytest.mark.error_handling
    def test_raises_os_error_when_client_id_missing(self) -> None:
        """OSError should be raised when the client ID env var is not set."""
        config = _make_minimal_config()
        with patch.dict(os.environ, {}, clear=True), pytest.raises(OSError, match="client ID"):
            get_credentials(config)

    @pytest.mark.error_handling
    def test_raises_os_error_when_client_secret_missing(self) -> None:
        """OSError should be raised when the client secret env var is not set."""
        config = _make_minimal_config()
        env_vars = {"REDDIT_CLIENT_ID": "test_id"}
        with patch.dict(os.environ, env_vars, clear=True), pytest.raises(OSError, match="client secret"):
            get_credentials(config)

    @pytest.mark.error_handling
    def test_raises_os_error_when_user_agent_missing(self) -> None:
        """OSError should be raised when the user agent env var is not set."""
        config = _make_minimal_config()
        env_vars = {"REDDIT_CLIENT_ID": "test_id", "REDDIT_CLIENT_SECRET": "test_secret"}
        with patch.dict(os.environ, env_vars, clear=True), pytest.raises(OSError, match="user agent"):
            get_credentials(config)

    def test_returns_credentials_when_all_vars_set(self) -> None:
        """All three credentials should be returned when env vars are set."""
        config = _make_minimal_config()
        env_vars = {
            "REDDIT_CLIENT_ID": "my_client_id",
            "REDDIT_CLIENT_SECRET": "my_secret",
            "REDDIT_USER_AGENT": "my_agent/1.0",
        }
        with patch.dict(os.environ, env_vars, clear=True):
            client_id, client_secret, user_agent = get_credentials(config)

        assert client_id == "my_client_id"
        assert client_secret == "my_secret"
        assert user_agent == "my_agent/1.0"
