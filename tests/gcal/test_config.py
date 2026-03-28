"""Tests for the GCal Tool configuration loader and validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from deep_thought.gcal.config import (
    GcalConfig,
    get_bundled_config_path,
    get_default_config_path,
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
        assert isinstance(config, GcalConfig)
        assert config.lookback_days == 7

    def test_parses_calendars(self) -> None:
        """Should parse all calendar IDs from the config file."""
        config = load_config(FIXTURES_DIR / "test_config.yaml")
        assert config.calendars == ["primary"]

    def test_parses_scopes(self) -> None:
        """Should parse the OAuth scopes list."""
        config = load_config(FIXTURES_DIR / "test_config.yaml")
        assert config.scopes == ["https://www.googleapis.com/auth/calendar"]

    def test_parses_all_top_level_fields(self) -> None:
        """Should correctly parse all top-level configuration fields."""
        config = load_config(FIXTURES_DIR / "test_config.yaml")
        assert config.credentials_path == "src/config/gmail/credentials.json"
        assert config.token_path == "data/gcal/token.json"
        assert config.api_rate_limit_rpm == 250
        assert config.retry_max_attempts == 3
        assert config.retry_base_delay_seconds == 1
        assert config.lookback_days == 7
        assert config.lookahead_days == 30
        assert config.include_cancelled is False
        assert config.single_events is True
        assert config.output_dir == "data/gcal/export/"
        assert config.generate_llms_files is False
        assert config.flat_output is False

    def test_raises_for_missing_file(self, tmp_path: Path) -> None:
        """Should raise FileNotFoundError when the config file is missing."""
        with pytest.raises(FileNotFoundError, match="Configuration file not found"):
            load_config(tmp_path / "nonexistent.yaml")

    def test_raises_for_non_mapping(self, tmp_path: Path) -> None:
        """Should raise ValueError when the YAML is not a mapping."""
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

    def test_catches_empty_calendars(self) -> None:
        """Should report an issue when no calendars are configured."""
        config = load_config(FIXTURES_DIR / "test_config.yaml")
        config.calendars = []
        issues = validate_config(config)
        assert any("No calendars configured" in issue for issue in issues)

    def test_catches_empty_credentials_path(self) -> None:
        """Should report an issue when credentials_path is empty."""
        config = load_config(FIXTURES_DIR / "test_config.yaml")
        config.credentials_path = ""
        issues = validate_config(config)
        assert any("credentials_path" in issue for issue in issues)

    def test_catches_empty_scopes(self) -> None:
        """Should report an issue when no scopes are configured."""
        config = load_config(FIXTURES_DIR / "test_config.yaml")
        config.scopes = []
        issues = validate_config(config)
        assert any("No OAuth scopes" in issue for issue in issues)

    def test_catches_negative_lookback_days(self) -> None:
        """Should report an issue when lookback_days is negative."""
        config = load_config(FIXTURES_DIR / "test_config.yaml")
        config.lookback_days = -1
        issues = validate_config(config)
        assert any("lookback_days" in issue for issue in issues)

    def test_catches_negative_lookahead_days(self) -> None:
        """Should report an issue when lookahead_days is negative."""
        config = load_config(FIXTURES_DIR / "test_config.yaml")
        config.lookahead_days = -1
        issues = validate_config(config)
        assert any("lookahead_days" in issue for issue in issues)

    def test_catches_zero_retry_max_attempts(self) -> None:
        """Should report an issue when retry_max_attempts is not positive."""
        config = load_config(FIXTURES_DIR / "test_config.yaml")
        config.retry_max_attempts = 0
        issues = validate_config(config)
        assert any("retry_max_attempts" in issue for issue in issues)

    def test_catches_calendar_id_with_forward_slash(self) -> None:
        """Should report an issue when a calendar ID contains a forward slash."""
        config = load_config(FIXTURES_DIR / "test_config.yaml")
        config.calendars = ["../evil@example.com"]
        issues = validate_config(config)
        assert any("path separators" in issue for issue in issues)

    def test_catches_calendar_id_with_backslash(self) -> None:
        """Should report an issue when a calendar ID contains a backslash."""
        config = load_config(FIXTURES_DIR / "test_config.yaml")
        config.calendars = ["..\\evil@example.com"]
        issues = validate_config(config)
        assert any("path separators" in issue for issue in issues)

    def test_catches_calendar_id_starting_with_dot(self) -> None:
        """Should report an issue when a calendar ID starts with a dot."""
        config = load_config(FIXTURES_DIR / "test_config.yaml")
        config.calendars = [".hidden@example.com"]
        issues = validate_config(config)
        assert any("path separators" in issue for issue in issues)

    def test_zero_lookback_days_is_valid(self) -> None:
        """lookback_days of 0 should be accepted (only negative is invalid)."""
        config = load_config(FIXTURES_DIR / "test_config.yaml")
        config.lookback_days = 0
        issues = validate_config(config)
        assert not any("lookback_days" in issue for issue in issues)

    def test_zero_lookahead_days_is_valid(self) -> None:
        """lookahead_days of 0 should be accepted (only negative is invalid)."""
        config = load_config(FIXTURES_DIR / "test_config.yaml")
        config.lookahead_days = 0
        issues = validate_config(config)
        assert not any("lookahead_days" in issue for issue in issues)


# ---------------------------------------------------------------------------
# Default config path
# ---------------------------------------------------------------------------


class TestGetDefaultConfigPath:
    """Tests for get_default_config_path."""

    def test_returns_path_ending_in_gcal_configuration_yaml(self) -> None:
        """Should return a Path ending in gcal-configuration.yaml."""
        config_path = get_default_config_path()
        assert str(config_path).endswith("gcal-configuration.yaml")

    def test_returns_path_object(self) -> None:
        """Should return a Path instance, not a string."""
        config_path = get_default_config_path()
        assert isinstance(config_path, Path)

    def test_is_relative_to_cwd(self) -> None:
        """Should return a path relative to the current working directory."""
        import os

        config_path = get_default_config_path()
        assert str(config_path).startswith(os.getcwd())


# ---------------------------------------------------------------------------
# Bundled config path
# ---------------------------------------------------------------------------


class TestGetBundledConfigPath:
    """Tests for get_bundled_config_path."""

    def test_returns_path_object(self) -> None:
        """Should return a Path instance, not a string."""
        bundled_path = get_bundled_config_path()
        assert isinstance(bundled_path, Path)

    def test_returns_path_ending_in_default_config_yaml(self) -> None:
        """Should return a Path ending in default-config.yaml."""
        bundled_path = get_bundled_config_path()
        assert bundled_path.name == "default-config.yaml"

    def test_bundled_config_file_exists(self) -> None:
        """The bundled config template should exist inside the package."""
        bundled_path = get_bundled_config_path()
        assert bundled_path.exists(), f"Bundled config not found at: {bundled_path}"

    def test_bundled_config_is_inside_package(self) -> None:
        """The bundled config path should be located inside the gcal package directory."""
        bundled_path = get_bundled_config_path()
        assert "deep_thought/gcal" in str(bundled_path)
