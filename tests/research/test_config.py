"""Tests for the Research Tool configuration loader and validation."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from deep_thought.research.config import (
    ResearchConfig,
    get_api_key,
    load_config,
    validate_config,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


class TestLoadConfig:
    """Tests for load_config."""

    def test_loads_from_fixture(self) -> None:
        """Should load the test fixture config without errors."""
        config = load_config(FIXTURES_DIR / "test_config.yaml")
        assert isinstance(config, ResearchConfig)

    def test_parses_all_fields(self) -> None:
        """Should correctly parse all fields from the fixture config."""
        config = load_config(FIXTURES_DIR / "test_config.yaml")
        assert config.api_key_env == "TEST_PERPLEXITY_KEY"
        assert config.retry_max_attempts == 2
        assert config.retry_base_delay_seconds == 1
        assert config.search_model == "sonar"
        assert config.research_model == "sonar-deep-research"
        assert config.default_recency is None
        assert config.output_dir == "data/research/export/"

    def test_null_default_recency_parsed_as_none(self) -> None:
        """A default_recency: null value should be parsed as Python None."""
        config = load_config(FIXTURES_DIR / "test_config.yaml")
        assert config.default_recency is None

    def test_default_recency_string_parsed(self, tmp_path: Path) -> None:
        """A default_recency with a valid string value should be parsed correctly."""
        config_file = tmp_path / "recency.yaml"
        config_file.write_text(
            'api_key_env: "PERPLEXITY_API_KEY"\n'
            'search_model: "sonar"\n'
            'research_model: "sonar-deep-research"\n'
            'output_dir: "data/research/export/"\n'
            'default_recency: "week"\n',
        )
        config = load_config(config_file)
        assert config.default_recency == "week"

    def test_applies_defaults_for_optional_fields(self, tmp_path: Path) -> None:
        """Should fall back to defaults for optional fields when absent from the YAML."""
        # Required fields must be present; only the optional retry fields are omitted here.
        partial_config_file = tmp_path / "partial.yaml"
        partial_config_file.write_text(
            "api_key_env: PERPLEXITY_API_KEY\n"
            "search_model: sonar\n"
            "research_model: sonar-deep-research\n"
            "output_dir: data/research/export/\n",
        )
        config = load_config(partial_config_file)
        assert config.retry_max_attempts == 3
        assert config.retry_base_delay_seconds == 1
        assert config.default_recency is None

    def test_raises_value_error_for_missing_required_field(self, tmp_path: Path) -> None:
        """Should raise ValueError when a required field is absent from the config."""
        # api_key_env is absent — must raise ValueError with the field name, not silently use a default.
        config_file = tmp_path / "missing_required.yaml"
        config_file.write_text(
            "search_model: sonar\nresearch_model: sonar-deep-research\noutput_dir: data/research/export/\n",
        )
        with pytest.raises(ValueError, match="api_key_env"):
            load_config(config_file)

    def test_raises_for_missing_file(self, tmp_path: Path) -> None:
        """Should raise FileNotFoundError when the config file does not exist."""
        with pytest.raises(FileNotFoundError, match="Configuration file not found"):
            load_config(tmp_path / "nonexistent.yaml")

    def test_raises_for_non_mapping(self, tmp_path: Path) -> None:
        """Should raise ValueError when the YAML root is not a mapping."""
        bad_file = tmp_path / "bad.yaml"
        bad_file.write_text("- just\n- a\n- list\n")
        with pytest.raises(ValueError, match="must contain a YAML mapping"):
            load_config(bad_file)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestValidateConfig:
    """Tests for validate_config."""

    def test_valid_config_returns_empty(self) -> None:
        """A valid config should produce zero issues."""
        config = load_config(FIXTURES_DIR / "test_config.yaml")
        issues = validate_config(config)
        assert issues == []

    def test_catches_zero_retry_max_attempts(self) -> None:
        """Should report an issue when retry_max_attempts is zero."""
        config = load_config(FIXTURES_DIR / "test_config.yaml")
        config.retry_max_attempts = 0
        issues = validate_config(config)
        assert any("retry_max_attempts" in issue for issue in issues)

    def test_catches_negative_retry_max_attempts(self) -> None:
        """Should report an issue when retry_max_attempts is negative."""
        config = load_config(FIXTURES_DIR / "test_config.yaml")
        config.retry_max_attempts = -1
        issues = validate_config(config)
        assert any("retry_max_attempts" in issue for issue in issues)

    def test_catches_zero_retry_base_delay(self) -> None:
        """Should report an issue when retry_base_delay_seconds is zero."""
        config = load_config(FIXTURES_DIR / "test_config.yaml")
        config.retry_base_delay_seconds = 0
        issues = validate_config(config)
        assert any("retry_base_delay_seconds" in issue for issue in issues)

    def test_catches_empty_api_key_env(self) -> None:
        """Should report an issue when api_key_env is an empty string."""
        config = load_config(FIXTURES_DIR / "test_config.yaml")
        config.api_key_env = ""
        issues = validate_config(config)
        assert any("api_key_env" in issue for issue in issues)

    def test_catches_empty_search_model(self) -> None:
        """Should report an issue when search_model is an empty string."""
        config = load_config(FIXTURES_DIR / "test_config.yaml")
        config.search_model = ""
        issues = validate_config(config)
        assert any("search_model" in issue for issue in issues)

    def test_catches_empty_research_model(self) -> None:
        """Should report an issue when research_model is an empty string."""
        config = load_config(FIXTURES_DIR / "test_config.yaml")
        config.research_model = ""
        issues = validate_config(config)
        assert any("research_model" in issue for issue in issues)

    def test_catches_invalid_default_recency(self) -> None:
        """Should report an issue when default_recency is not a recognised value."""
        config = load_config(FIXTURES_DIR / "test_config.yaml")
        config.default_recency = "century"
        issues = validate_config(config)
        assert any("default_recency" in issue for issue in issues)

    def test_valid_recency_values_pass(self) -> None:
        """Each of the five recognised recency values should produce no issues."""
        config = load_config(FIXTURES_DIR / "test_config.yaml")
        for valid_recency in ("hour", "day", "week", "month", "year"):
            config.default_recency = valid_recency
            issues = validate_config(config)
            assert issues == [], f"Expected no issues for recency='{valid_recency}', got: {issues}"

    def test_none_default_recency_passes(self) -> None:
        """A None default_recency should produce no issues."""
        config = load_config(FIXTURES_DIR / "test_config.yaml")
        config.default_recency = None
        issues = validate_config(config)
        assert issues == []

    def test_catches_empty_output_dir(self) -> None:
        """Should report an issue when output_dir is an empty string."""
        config = load_config(FIXTURES_DIR / "test_config.yaml")
        config.output_dir = ""
        issues = validate_config(config)
        assert any("output_dir" in issue for issue in issues)


# ---------------------------------------------------------------------------
# API key retrieval
# ---------------------------------------------------------------------------


class TestGetApiKey:
    """Tests for get_api_key."""

    def test_returns_key_when_set(self) -> None:
        """Should return the API key when the env var is populated."""
        config = load_config(FIXTURES_DIR / "test_config.yaml")
        with patch.dict("os.environ", {"TEST_PERPLEXITY_KEY": "test_key_abc123"}):
            api_key = get_api_key(config)
        assert api_key == "test_key_abc123"

    def test_raises_when_env_var_not_set(self) -> None:
        """Should raise OSError when the env var is missing from the environment."""
        config = load_config(FIXTURES_DIR / "test_config.yaml")
        with patch.dict("os.environ", {}, clear=True), pytest.raises(OSError, match="Perplexity API key not found"):
            get_api_key(config)

    def test_raises_when_env_var_is_empty_string(self) -> None:
        """Should raise OSError when the env var is set but empty."""
        config = load_config(FIXTURES_DIR / "test_config.yaml")
        with patch.dict("os.environ", {"TEST_PERPLEXITY_KEY": ""}), pytest.raises(OSError, match="TEST_PERPLEXITY_KEY"):
            get_api_key(config)

    def test_error_message_includes_env_var_name(self) -> None:
        """The OSError message should name the specific env var that is missing."""
        config = load_config(FIXTURES_DIR / "test_config.yaml")
        with patch.dict("os.environ", {}, clear=True), pytest.raises(OSError, match="TEST_PERPLEXITY_KEY"):
            get_api_key(config)
