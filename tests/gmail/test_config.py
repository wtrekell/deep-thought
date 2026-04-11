"""Tests for the Gmail Tool configuration loader and validation."""

from __future__ import annotations

import warnings
from pathlib import Path
from unittest.mock import patch

import pytest

from deep_thought.gmail.config import (
    GmailConfig,
    RuleConfig,
    _parse_rule_config,
    get_gemini_api_key,
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
        assert isinstance(config, GmailConfig)
        assert config.max_emails_per_run == 50

    def test_parses_rules(self) -> None:
        """Should parse all rules from the config file."""
        config = load_config(FIXTURES_DIR / "test_config.yaml")
        assert len(config.rules) == 1
        assert config.rules[0].name == "test_rule"
        assert config.rules[0].query == "label:test newer_than:7d"

    def test_parses_rule_fields(self) -> None:
        """Should correctly parse all fields on a rule."""
        config = load_config(FIXTURES_DIR / "test_config.yaml")
        rule = config.rules[0]
        assert rule.ai_instructions == "Extract key points."
        assert rule.actions == ["archive", "label:TestLabel"]
        assert rule.save_mode == "individual"

    def test_parses_scopes(self) -> None:
        """Should parse the OAuth scopes list."""
        config = load_config(FIXTURES_DIR / "test_config.yaml")
        assert config.scopes == ["https://mail.google.com/"]

    def test_parses_all_top_level_fields(self) -> None:
        """Should correctly parse all top-level configuration fields.

        credentials_path and token_path are resolved to absolute paths
        at load time (L1 fix), so we check they end with the expected
        relative suffix rather than asserting the literal string.
        """
        config = load_config(FIXTURES_DIR / "test_config.yaml")
        assert Path(config.credentials_path).is_absolute()
        assert config.credentials_path.endswith("src/config/gmail/credentials.json")
        assert Path(config.token_path).is_absolute()
        assert config.token_path.endswith("data/gmail/token.json")
        assert config.gemini_api_key_env == "GEMINI_API_KEY"
        assert config.gemini_model == "gemini-2.5-flash"
        assert config.gemini_rate_limit_rpm == 15
        assert config.gmail_rate_limit_rpm == 250
        assert config.retry_max_attempts == 3
        assert config.retry_base_delay_seconds == 1
        assert config.clean_newsletters is True
        assert config.decision_cache_ttl == 3600
        assert config.output_dir == "data/gmail/export/"
        assert config.qdrant_collection == "test_collection"

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

    def test_raises_for_rule_missing_name(self, tmp_path: Path) -> None:
        """Should raise ValueError when a rule has no name."""
        bad_file = tmp_path / "bad_rule.yaml"
        bad_file.write_text("rules:\n  - query: 'test'\n")
        with pytest.raises(ValueError, match="must have a 'name' field"):
            load_config(bad_file)

    def test_raises_for_rule_missing_query(self, tmp_path: Path) -> None:
        """Should raise ValueError when a rule has no query."""
        bad_file = tmp_path / "bad_rule.yaml"
        bad_file.write_text("rules:\n  - name: 'test'\n")
        with pytest.raises(ValueError, match="must have a 'query' field"):
            load_config(bad_file)

    def test_save_mode_defaults_to_individual(self, tmp_path: Path) -> None:
        """A rule without save_mode should default to 'individual'."""
        config_file = tmp_path / "no_save_mode.yaml"
        config_file.write_text("rules:\n  - name: 'minimal'\n    query: 'label:test'\n")
        config = load_config(config_file)
        assert config.rules[0].save_mode == "individual"

    def test_save_mode_values_parsed(self, tmp_path: Path) -> None:
        """Each valid save_mode value should be parsed correctly."""
        for mode in ("individual", "append", "both", "none"):
            config_file = tmp_path / f"mode_{mode}.yaml"
            config_file.write_text(f"rules:\n  - name: 'r'\n    query: 'label:test'\n    save_mode: {mode}\n")
            config = load_config(config_file)
            assert config.rules[0].save_mode == mode

    def test_old_fields_produce_deprecation_warning(self, tmp_path: Path) -> None:
        """Legacy save_local/append_mode fields should map to save_mode with a DeprecationWarning."""
        config_file = tmp_path / "old_fields.yaml"
        config_file.write_text(
            "rules:\n  - name: 'old'\n    query: 'label:test'\n    save_local: false\n    append_mode: false\n"
        )
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            config = load_config(config_file)
        assert config.rules[0].save_mode == "none"
        deprecation_warnings = [w for w in caught if issubclass(w.category, DeprecationWarning)]
        assert len(deprecation_warnings) >= 1
        assert "save_mode: none" in str(deprecation_warnings[0].message)

    def test_old_append_mode_true_maps_to_append(self, tmp_path: Path) -> None:
        """Legacy append_mode: true should map to save_mode 'append'."""
        config_file = tmp_path / "old_append.yaml"
        config_file.write_text("rules:\n  - name: 'old'\n    query: 'label:test'\n    append_mode: true\n")
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            config = load_config(config_file)
        assert config.rules[0].save_mode == "append"
        deprecation_warnings = [w for w in caught if issubclass(w.category, DeprecationWarning)]
        assert len(deprecation_warnings) >= 1

    def test_save_mode_wins_over_old_fields(self, tmp_path: Path) -> None:
        """When save_mode and old fields are both present, save_mode wins."""
        config_file = tmp_path / "both_fields.yaml"
        config_file.write_text(
            "rules:\n  - name: 'mixed'\n    query: 'label:test'\n"
            "    save_mode: both\n    append_mode: true\n    save_local: false\n"
        )
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            config = load_config(config_file)
        assert config.rules[0].save_mode == "both"
        deprecation_warnings = [w for w in caught if issubclass(w.category, DeprecationWarning)]
        assert len(deprecation_warnings) >= 1
        assert "ignoring deprecated" in str(deprecation_warnings[0].message).lower()

    def test_null_ai_instructions_parsed_as_none(self, tmp_path: Path) -> None:
        """A rule with ai_instructions: null should set the field to None."""
        config_file = tmp_path / "null_ai.yaml"
        config_file.write_text(
            "rules:\n"
            "  - name: 'fwd_rule'\n"
            "    query: 'label:test'\n"
            "    ai_instructions: null\n"
            "    actions:\n"
            "      - archive\n"
        )
        config = load_config(config_file)
        assert config.rules[0].ai_instructions is None


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

    def test_catches_empty_rules(self) -> None:
        """Should report an issue when no rules are configured."""
        config = load_config(FIXTURES_DIR / "test_config.yaml")
        config.rules = []
        issues = validate_config(config)
        assert any("No rules configured" in issue for issue in issues)

    def test_catches_invalid_max_emails(self) -> None:
        """Should report an issue when max_emails_per_run is not positive."""
        config = load_config(FIXTURES_DIR / "test_config.yaml")
        config.max_emails_per_run = 0
        issues = validate_config(config)
        assert any("max_emails_per_run" in issue for issue in issues)

    def test_catches_duplicate_rule_names(self) -> None:
        """Should report an issue when two rules share the same name."""
        config = load_config(FIXTURES_DIR / "test_config.yaml")
        config.rules.append(
            RuleConfig(
                name="test_rule",
                query="label:dup",
                ai_instructions=None,
                actions=[],
                save_mode="individual",
            )
        )
        issues = validate_config(config)
        assert any("Duplicate rule name" in issue for issue in issues)

    def test_catches_invalid_action(self) -> None:
        """Should report an issue for unrecognised action strings."""
        config = load_config(FIXTURES_DIR / "test_config.yaml")
        config.rules[0].actions.append("explode")
        issues = validate_config(config)
        assert any("unknown action 'explode'" in issue for issue in issues)

    def test_valid_parameterized_actions(self) -> None:
        """Parameterized actions like label:X and forward:X should pass validation."""
        config = load_config(FIXTURES_DIR / "test_config.yaml")
        config.rules[0].actions = ["label:Processed", "forward:user@example.com", "remove_label:Old"]
        issues = validate_config(config)
        assert issues == []

    def test_catches_empty_credentials_path(self) -> None:
        """Should report an issue when credentials_path is empty."""
        config = load_config(FIXTURES_DIR / "test_config.yaml")
        config.credentials_path = ""
        issues = validate_config(config)
        assert any("credentials_path" in issue for issue in issues)

    def test_catches_invalid_retry_attempts(self) -> None:
        """Should report an issue when retry_max_attempts is not positive."""
        config = load_config(FIXTURES_DIR / "test_config.yaml")
        config.retry_max_attempts = 0
        issues = validate_config(config)
        assert any("retry_max_attempts" in issue for issue in issues)

    def test_catches_invalid_save_mode(self) -> None:
        """Should report an issue for an invalid save_mode value."""
        config = load_config(FIXTURES_DIR / "test_config.yaml")
        config.rules[0].save_mode = "bogus"
        issues = validate_config(config)
        assert any("invalid save_mode 'bogus'" in issue for issue in issues)


# ---------------------------------------------------------------------------
# Gemini API key
# ---------------------------------------------------------------------------


class TestGetGeminiApiKey:
    """Tests for get_gemini_api_key."""

    def test_returns_key_when_set(self) -> None:
        """Should return the API key when the env var is set (keychain fallback)."""
        config = load_config(FIXTURES_DIR / "test_config.yaml")
        with (
            patch("deep_thought.secrets.keychain_available", return_value=False),
            patch.dict("os.environ", {"GEMINI_API_KEY": "test_key_123"}),
        ):
            key = get_gemini_api_key(config)
        assert key == "test_key_123"

    def test_returns_key_from_keychain(self) -> None:
        """Should return the API key from keychain when available."""
        config = load_config(FIXTURES_DIR / "test_config.yaml")
        with (
            patch("deep_thought.secrets.keychain_available", return_value=True),
            patch("deep_thought.secrets.keyring.get_password", return_value="keychain-gemini-key"),
        ):
            key = get_gemini_api_key(config)
        assert key == "keychain-gemini-key"

    def test_raises_when_not_set(self) -> None:
        """Should raise OSError when neither keychain nor env var have the key."""
        config = load_config(FIXTURES_DIR / "test_config.yaml")
        with (
            patch("deep_thought.secrets.keychain_available", return_value=False),
            patch.dict("os.environ", {}, clear=True),
            pytest.raises(OSError, match="Secret not found"),
        ):
            get_gemini_api_key(config)


# ---------------------------------------------------------------------------
# Rule name validation (path traversal prevention)
# ---------------------------------------------------------------------------


class TestRuleNameValidation:
    """Tests for rule name path traversal prevention."""

    def test_rejects_forward_slash(self) -> None:
        """Should reject rule names with forward slashes."""
        with pytest.raises(ValueError, match="path separators"):
            _parse_rule_config({"name": "../evil", "query": "from:x"})

    def test_rejects_backslash(self) -> None:
        """Should reject rule names with backslashes."""
        with pytest.raises(ValueError, match="path separators"):
            _parse_rule_config({"name": "..\\evil", "query": "from:x"})

    def test_rejects_dot_prefix(self) -> None:
        """Should reject rule names starting with a dot."""
        with pytest.raises(ValueError, match="start with a dot"):
            _parse_rule_config({"name": ".hidden", "query": "from:x"})

    def test_allows_valid_names(self) -> None:
        """Should accept clean rule names."""
        rule = _parse_rule_config({"name": "newsletters", "query": "from:x"})
        assert rule.name == "newsletters"
