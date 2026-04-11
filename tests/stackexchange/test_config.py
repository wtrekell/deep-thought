"""Tests for the config loader in deep_thought.stackexchange.config.

Tests cover valid config loading, error cases, validation, and API key retrieval.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from deep_thought.stackexchange.config import (
    RuleConfig,
    StackExchangeConfig,
    TagConfig,
    get_api_key,
    get_bundled_config_path,
    get_default_config_path,
    load_config,
    validate_config,
)
from tests.stackexchange.conftest import FIXTURES_DIR

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_CONFIG_PATH = FIXTURES_DIR / "test_config.yaml"


def _make_minimal_config() -> StackExchangeConfig:
    """Return a minimal valid StackExchangeConfig for use in validation tests."""
    return StackExchangeConfig(
        api_key_env="STACKEXCHANGE_API_KEY",
        max_questions_per_run=100,
        output_dir="data/stackexchange/export/",
        generate_llms_files=False,
        qdrant_collection="deep_thought_db",
        rules=[
            RuleConfig(
                name="test_rule",
                site="stackoverflow",
                tags=TagConfig(include=["python"], any=[]),
                sort="votes",
                order="desc",
                min_score=10,
                min_answers=1,
                only_answered=True,
                max_age_days=365,
                keywords=[],
                max_questions=50,
                max_answers_per_question=5,
                include_comments=True,
                max_comments_per_question=30,
            )
        ],
    )


# ---------------------------------------------------------------------------
# TestGetDefaultConfigPath
# ---------------------------------------------------------------------------


class TestGetDefaultConfigPath:
    def test_returns_a_path_object(self) -> None:
        """get_default_config_path should return a Path object."""
        result = get_default_config_path()
        assert isinstance(result, Path)

    def test_path_ends_with_expected_filename(self) -> None:
        """The default config path should end with stackexchange-configuration.yaml."""
        result = get_default_config_path()
        assert result.name == "stackexchange-configuration.yaml"

    def test_path_is_relative_to_cwd(self) -> None:
        """The default config path should be relative to the current working directory."""
        result = get_default_config_path()
        # Path should be absolute (resolved from cwd)
        assert result.is_absolute()


# ---------------------------------------------------------------------------
# TestGetBundledConfigPath
# ---------------------------------------------------------------------------


class TestGetBundledConfigPath:
    def test_returns_a_path_object(self) -> None:
        """get_bundled_config_path should return a Path object."""
        result = get_bundled_config_path()
        assert isinstance(result, Path)

    def test_path_ends_with_default_config_yaml(self) -> None:
        """The bundled config path should end with default-config.yaml."""
        result = get_bundled_config_path()
        assert result.name == "default-config.yaml"

    def test_bundled_config_file_exists(self) -> None:
        """The bundled default config must actually exist in the package."""
        result = get_bundled_config_path()
        assert result.exists()

    def test_path_is_package_relative(self) -> None:
        """The bundled config path should be absolute and within the package directory."""
        result = get_bundled_config_path()
        assert result.is_absolute()
        assert "stackexchange" in str(result)


# ---------------------------------------------------------------------------
# TestLoadConfig
# ---------------------------------------------------------------------------


class TestLoadConfig:
    def test_loads_valid_config_from_fixture(self) -> None:
        """Loading the test fixture config should return a StackExchangeConfig with one rule."""
        config = load_config(_VALID_CONFIG_PATH)
        assert isinstance(config, StackExchangeConfig)
        assert len(config.rules) == 1
        assert config.rules[0].name == "test_rule"
        assert config.rules[0].site == "stackoverflow"

    def test_rule_fields_parsed_correctly(self) -> None:
        """Rule fields should be parsed with correct types from the YAML."""
        config = load_config(_VALID_CONFIG_PATH)
        rule = config.rules[0]
        assert rule.sort == "votes"
        assert rule.order == "desc"
        assert rule.min_score == 10
        assert rule.min_answers == 1
        assert rule.only_answered is True
        assert rule.max_age_days == 365
        assert rule.max_questions == 50
        assert rule.max_answers_per_question == 5
        assert rule.include_comments is True
        assert rule.max_comments_per_question == 30

    def test_tag_config_parsed_correctly(self) -> None:
        """Tag config should parse include and any lists from the YAML."""
        config = load_config(_VALID_CONFIG_PATH)
        rule = config.rules[0]
        assert rule.tags.include == ["python"]
        assert rule.tags.any == []

    def test_top_level_fields_parsed_correctly(self) -> None:
        """Top-level config fields should be parsed with correct values."""
        config = load_config(_VALID_CONFIG_PATH)
        assert config.api_key_env == "STACKEXCHANGE_API_KEY"
        assert config.max_questions_per_run == 100
        assert config.output_dir == "data/stackexchange/export/"
        assert config.generate_llms_files is False
        assert config.qdrant_collection == "deep_thought_db"

    def test_raises_file_not_found_for_missing_file(self) -> None:
        """Passing a non-existent path should raise FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="Configuration file not found"):
            load_config(Path("/nonexistent/path/config.yaml"))

    def test_raises_value_error_for_invalid_yaml(self, tmp_path: Path) -> None:
        """A YAML file that does not contain a mapping should raise ValueError."""
        bad_yaml_file = tmp_path / "bad.yaml"
        bad_yaml_file.write_text("- just\n- a\n- list\n", encoding="utf-8")
        with pytest.raises(ValueError, match="YAML mapping"):
            load_config(bad_yaml_file)

    def test_uses_default_path_when_none_given(self) -> None:
        """When config_path is None, load_config uses the default path (may not exist in test env)."""
        default_path = get_default_config_path()
        if default_path.exists():
            config = load_config(None)
            assert isinstance(config, StackExchangeConfig)
        else:
            with pytest.raises(FileNotFoundError):
                load_config(None)

    def test_empty_rules_list_is_valid_yaml(self, tmp_path: Path) -> None:
        """A YAML file with an empty rules list should parse without error."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            "api_key_env: STACKEXCHANGE_API_KEY\n"
            "max_questions_per_run: 100\n"
            "output_dir: data/\n"
            "generate_llms_files: false\n"
            "qdrant_collection: deep_thought_db\n"
            "rules: []\n",
            encoding="utf-8",
        )
        config = load_config(config_file)
        assert config.rules == []


# ---------------------------------------------------------------------------
# TestValidateConfig
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

    def test_duplicate_rule_names_produce_issue(self) -> None:
        """Two rules with the same name should produce a validation issue."""
        config = _make_minimal_config()
        duplicate_rule = RuleConfig(
            name="test_rule",  # same name as the first rule
            site="superuser",
            tags=TagConfig(include=[], any=[]),
            sort="votes",
            order="desc",
            min_score=0,
            min_answers=0,
            only_answered=False,
            max_age_days=365,
            keywords=[],
            max_questions=50,
            max_answers_per_question=5,
            include_comments=False,
            max_comments_per_question=30,
        )
        config.rules.append(duplicate_rule)
        issues = validate_config(config)
        assert any("Duplicate rule name" in issue for issue in issues)

    def test_invalid_sort_value_produces_issue(self) -> None:
        """A rule with an invalid sort value should produce a validation issue."""
        config = _make_minimal_config()
        config.rules[0].sort = "random"
        issues = validate_config(config)
        assert any("sort" in issue for issue in issues)

    def test_unsafe_rule_name_produces_issue(self) -> None:
        """A rule name with path traversal characters should produce a validation issue."""
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

    def test_max_questions_per_run_zero_produces_issue(self) -> None:
        """max_questions_per_run of 0 should produce a validation issue."""
        config = _make_minimal_config()
        config.max_questions_per_run = 0
        issues = validate_config(config)
        assert any("max_questions_per_run" in issue for issue in issues)

    def test_negative_max_questions_per_run_produces_issue(self) -> None:
        """A negative max_questions_per_run should produce a validation issue."""
        config = _make_minimal_config()
        config.max_questions_per_run = -1
        issues = validate_config(config)
        assert any("max_questions_per_run" in issue for issue in issues)

    def test_empty_rules_list_is_flagged(self) -> None:
        """An empty rules list should be flagged exactly once."""
        config = _make_minimal_config()
        config.rules = []
        issues = validate_config(config)
        assert len([i for i in issues if "No rules" in i]) == 1


# ---------------------------------------------------------------------------
# TestGetApiKey
# ---------------------------------------------------------------------------


class TestGetApiKey:
    @pytest.mark.error_handling
    def test_returns_none_when_key_not_set(self) -> None:
        """get_api_key should return None when the secret cannot be found."""
        config = _make_minimal_config()
        with patch("deep_thought.secrets.get_secret", side_effect=OSError("not found")):
            result = get_api_key(config)
        assert result is None
