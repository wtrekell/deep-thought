"""Tests for the Gmail Tool configuration loader and validation."""

from __future__ import annotations

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
        assert rule.append_mode is False

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
            RuleConfig(name="test_rule", query="label:dup", ai_instructions=None, actions=[], append_mode=False)
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
