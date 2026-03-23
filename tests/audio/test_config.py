"""Tests for the configuration loader in deep_thought.audio.config."""

from __future__ import annotations

from pathlib import Path  # noqa: TC003

import pytest

from deep_thought.audio.config import (
    AudioConfig,
    load_config,
    save_default_config,
    validate_config,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_YAML = """\
engine: 'mlx'
model: 'small'
language: 'en'
output_mode: 'paragraph'
pause_threshold: 1.5
diarize: false
hf_token_env: 'HF_TOKEN'
remove_fillers: false
output_dir: 'data/audio/export/'
generate_llms_files: true
max_file_size_mb: 100
chunk_duration_minutes: 5
hallucination_detection:
  repetition_threshold: 3
  compression_ratio_threshold: 2.4
  confidence_floor: -1.0
  no_speech_prob_threshold: 0.6
  duration_chars_per_sec_max: 25
  duration_chars_per_sec_min: 2
  use_vad: true
  blocklist_enabled: true
  score_threshold: 2
  action: 'remove'
"""


# ---------------------------------------------------------------------------
# load_config — file loading and parsing
# ---------------------------------------------------------------------------


class TestLoadConfig:
    def test_loads_fixture_config_successfully(self) -> None:
        """The test fixture YAML must parse without errors."""
        fixture_path = Path(__file__).parent / "fixtures" / "test_config.yaml"
        config = load_config(fixture_path)
        assert isinstance(config, AudioConfig)

    def test_loads_default_config_successfully(self) -> None:
        """The bundled default config file must parse without errors."""
        config = load_config()
        assert isinstance(config, AudioConfig)

    def test_engine_config_parsed(self) -> None:
        """Engine fields must be read from the YAML root."""
        fixture_path = Path(__file__).parent / "fixtures" / "test_config.yaml"
        config = load_config(fixture_path)
        assert config.engine.engine == "mlx"
        assert config.engine.model == "small"
        assert config.engine.language == "en"

    def test_output_config_parsed(self) -> None:
        """Output fields must be read from the YAML root."""
        fixture_path = Path(__file__).parent / "fixtures" / "test_config.yaml"
        config = load_config(fixture_path)
        assert config.output.output_mode == "paragraph"
        assert isinstance(config.output.pause_threshold, float)
        assert isinstance(config.output.generate_llms_files, bool)

    def test_limits_config_parsed(self) -> None:
        """Limits fields must be parsed as positive integers."""
        fixture_path = Path(__file__).parent / "fixtures" / "test_config.yaml"
        config = load_config(fixture_path)
        assert config.limits.max_file_size_mb == 100
        assert config.limits.chunk_duration_minutes == 5

    def test_hallucination_config_parsed(self) -> None:
        """Hallucination detection fields must be read from the nested key."""
        fixture_path = Path(__file__).parent / "fixtures" / "test_config.yaml"
        config = load_config(fixture_path)
        assert config.hallucination.action == "remove"
        assert config.hallucination.score_threshold == 2
        assert config.hallucination.use_vad is True

    def test_null_language_parsed_as_none(self, tmp_path: Path) -> None:
        """A null language value in YAML must be parsed as Python None."""
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text(_VALID_YAML.replace("language: 'en'", "language: null"), encoding="utf-8")
        config = load_config(yaml_file)
        assert config.engine.language is None

    @pytest.mark.error_handling
    def test_missing_file_raises_file_not_found(self, tmp_path: Path) -> None:
        """A path to a non-existent file must raise FileNotFoundError."""
        missing_path = tmp_path / "does_not_exist.yaml"
        with pytest.raises(FileNotFoundError, match="Configuration file not found"):
            load_config(missing_path)

    @pytest.mark.error_handling
    def test_non_dict_yaml_raises_value_error(self, tmp_path: Path) -> None:
        """A YAML file that does not contain a mapping must raise ValueError."""
        bad_yaml_file = tmp_path / "bad.yaml"
        bad_yaml_file.write_text("- item1\n- item2\n", encoding="utf-8")
        with pytest.raises(ValueError, match="YAML mapping"):
            load_config(bad_yaml_file)

    def test_explicit_config_path_overrides_default(self, tmp_path: Path) -> None:
        """Passing an explicit path must load that file, not the default."""
        custom_yaml = tmp_path / "custom.yaml"
        custom_yaml.write_text(_VALID_YAML, encoding="utf-8")
        config = load_config(custom_yaml)
        assert config.limits.max_file_size_mb == 100


# ---------------------------------------------------------------------------
# validate_config
# ---------------------------------------------------------------------------


class TestValidateConfig:
    def test_valid_default_config_returns_no_issues(self) -> None:
        """The bundled default config must produce no validation issues."""
        config = load_config()
        issues = validate_config(config)
        assert issues == []

    def test_valid_fixture_config_returns_no_issues(self) -> None:
        """The fixture config must produce no validation issues."""
        fixture_path = Path(__file__).parent / "fixtures" / "test_config.yaml"
        config = load_config(fixture_path)
        issues = validate_config(config)
        assert issues == []

    def test_invalid_engine_is_flagged(self, tmp_path: Path) -> None:
        """An unrecognised engine value must appear in the issues list."""
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text(_VALID_YAML.replace("engine: 'mlx'", "engine: 'deepgram'"), encoding="utf-8")
        config = load_config(yaml_file)
        issues = validate_config(config)
        assert any("engine" in issue for issue in issues)

    def test_invalid_output_mode_is_flagged(self, tmp_path: Path) -> None:
        """An unrecognised output_mode value must appear in the issues list."""
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text(_VALID_YAML.replace("output_mode: 'paragraph'", "output_mode: 'stream'"), encoding="utf-8")
        config = load_config(yaml_file)
        issues = validate_config(config)
        assert any("output_mode" in issue for issue in issues)

    def test_invalid_hallucination_action_is_flagged(self, tmp_path: Path) -> None:
        """An unrecognised hallucination action must appear in the issues list."""
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text(_VALID_YAML.replace("action: 'remove'", "action: 'suppress'"), encoding="utf-8")
        config = load_config(yaml_file)
        issues = validate_config(config)
        assert any("action" in issue for issue in issues)

    def test_zero_max_file_size_is_flagged(self, tmp_path: Path) -> None:
        """A max_file_size_mb of 0 must appear in the issues list."""
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text(_VALID_YAML.replace("max_file_size_mb: 100", "max_file_size_mb: 0"), encoding="utf-8")
        config = load_config(yaml_file)
        issues = validate_config(config)
        assert any("max_file_size_mb" in issue for issue in issues)

    def test_score_threshold_below_one_is_flagged(self, tmp_path: Path) -> None:
        """A score_threshold of 0 must appear in the issues list."""
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text(_VALID_YAML.replace("score_threshold: 2", "score_threshold: 0"), encoding="utf-8")
        config = load_config(yaml_file)
        issues = validate_config(config)
        assert any("score_threshold" in issue for issue in issues)

    def test_multiple_issues_all_returned(self, tmp_path: Path) -> None:
        """validate_config must collect all issues, not stop at the first."""
        invalid_yaml = _VALID_YAML.replace("engine: 'mlx'", "engine: 'bad_engine'")
        invalid_yaml = invalid_yaml.replace("output_mode: 'paragraph'", "output_mode: 'bad_mode'")
        invalid_yaml = invalid_yaml.replace("max_file_size_mb: 100", "max_file_size_mb: 0")
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text(invalid_yaml, encoding="utf-8")
        config = load_config(yaml_file)
        issues = validate_config(config)
        assert len(issues) >= 3

    def test_zero_pause_threshold_is_flagged(self, tmp_path: Path) -> None:
        """A pause_threshold of 0 must appear in the issues list."""
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text(_VALID_YAML.replace("pause_threshold: 1.5", "pause_threshold: 0"), encoding="utf-8")
        config = load_config(yaml_file)
        issues = validate_config(config)
        assert any("pause_threshold" in issue for issue in issues)

    def test_negative_pause_threshold_is_flagged(self, tmp_path: Path) -> None:
        """A negative pause_threshold must appear in the issues list."""
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text(_VALID_YAML.replace("pause_threshold: 1.5", "pause_threshold: -1.0"), encoding="utf-8")
        config = load_config(yaml_file)
        issues = validate_config(config)
        assert any("pause_threshold" in issue for issue in issues)

    def test_zero_chunk_duration_minutes_is_flagged(self, tmp_path: Path) -> None:
        """A chunk_duration_minutes of 0 must appear in the issues list."""
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text(
            _VALID_YAML.replace("chunk_duration_minutes: 5", "chunk_duration_minutes: 0"), encoding="utf-8"
        )
        config = load_config(yaml_file)
        issues = validate_config(config)
        assert any("chunk_duration_minutes" in issue for issue in issues)

    def test_negative_chunk_duration_minutes_is_flagged(self, tmp_path: Path) -> None:
        """A negative chunk_duration_minutes must appear in the issues list."""
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text(
            _VALID_YAML.replace("chunk_duration_minutes: 5", "chunk_duration_minutes: -3"), encoding="utf-8"
        )
        config = load_config(yaml_file)
        issues = validate_config(config)
        assert any("chunk_duration_minutes" in issue for issue in issues)


# ---------------------------------------------------------------------------
# save_default_config
# ---------------------------------------------------------------------------


class TestSaveDefaultConfig:
    def test_creates_file_at_destination(self, tmp_path: Path) -> None:
        """save_default_config() must write a file to the specified path."""
        destination = tmp_path / "my-audio-config.yaml"
        save_default_config(destination)
        assert destination.exists()

    def test_written_file_is_parseable(self, tmp_path: Path) -> None:
        """The file written by save_default_config() must load without errors."""
        destination = tmp_path / "audio-configuration.yaml"
        save_default_config(destination)
        config = load_config(destination)
        assert isinstance(config, AudioConfig)

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        """save_default_config() must create any missing parent directories."""
        destination = tmp_path / "nested" / "dir" / "audio-configuration.yaml"
        save_default_config(destination)
        assert destination.exists()

    @pytest.mark.error_handling
    def test_raises_file_exists_error_if_destination_exists(self, tmp_path: Path) -> None:
        """save_default_config() must raise FileExistsError if the destination already exists."""
        destination = tmp_path / "audio-configuration.yaml"
        destination.write_text("existing content", encoding="utf-8")
        with pytest.raises(FileExistsError, match="already exists"):
            save_default_config(destination)
