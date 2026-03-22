"""Tests for the configuration loader in deep_thought.file_txt.config."""

from __future__ import annotations

from pathlib import Path  # noqa: TC003

import pytest

from deep_thought.file_txt.config import (
    FileTxtConfig,
    _parse_filter_config,
    _parse_limits_config,
    _parse_marker_config,
    _parse_output_config,
    load_config,
    validate_config,
)

# ---------------------------------------------------------------------------
# load_config — file loading and parsing
# ---------------------------------------------------------------------------


class TestLoadConfig:
    def test_loads_default_config_successfully(self) -> None:
        """The bundled default config file must parse without errors."""
        config = load_config()
        assert isinstance(config, FileTxtConfig)

    def test_marker_config_parsed(self) -> None:
        """force_ocr and torch_device must be read from the YAML root."""
        config = load_config()
        assert isinstance(config.marker.force_ocr, bool)
        assert config.marker.torch_device in {"mps", "cuda", "cpu"}

    def test_output_config_parsed(self) -> None:
        """Output fields must be read from the YAML root."""
        config = load_config()
        assert isinstance(config.output.output_dir, str)
        assert isinstance(config.output.include_page_numbers, bool)
        assert isinstance(config.output.extract_images, bool)

    def test_limits_config_parsed(self) -> None:
        """max_file_size_mb must be parsed as a positive integer."""
        config = load_config()
        assert isinstance(config.limits.max_file_size_mb, int)
        assert config.limits.max_file_size_mb > 0

    def test_filter_config_parsed(self) -> None:
        """allowed_extensions and exclude_patterns must be populated lists."""
        config = load_config()
        assert isinstance(config.filter.allowed_extensions, list)
        assert len(config.filter.allowed_extensions) > 0

    def test_allowed_extensions_contain_pdf(self) -> None:
        """The default config must include .pdf in allowed extensions."""
        config = load_config()
        assert ".pdf" in config.filter.allowed_extensions

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
        bad_yaml_file.write_text("- item1\n- item2\n", encoding="utf-8")
        with pytest.raises(ValueError, match="YAML mapping"):
            load_config(bad_yaml_file)

    def test_minimal_yaml_loads_with_defaults(self, tmp_path: Path) -> None:
        """A YAML file with only required fields must produce a valid config."""
        minimal_yaml = tmp_path / "minimal.yaml"
        minimal_yaml.write_text(
            "force_ocr: false\ntorch_device: cpu\n"
            "output_dir: output/\ninclude_page_numbers: false\nextract_images: true\n"
            "max_file_size_mb: 100\nallowed_extensions: ['.pdf']\nexclude_patterns: []\n",
            encoding="utf-8",
        )
        config = load_config(minimal_yaml)
        assert config.marker.torch_device == "cpu"
        assert config.limits.max_file_size_mb == 100

    def test_explicit_config_path_overrides_default(self, tmp_path: Path) -> None:
        """Passing an explicit path must load that file, not the default."""
        custom_yaml = tmp_path / "custom.yaml"
        custom_yaml.write_text(
            "force_ocr: true\ntorch_device: cuda\n"
            "output_dir: custom_out/\ninclude_page_numbers: true\nextract_images: false\n"
            "max_file_size_mb: 50\nallowed_extensions: ['.pdf']\nexclude_patterns: []\n",
            encoding="utf-8",
        )
        config = load_config(custom_yaml)
        assert config.marker.force_ocr is True
        assert config.marker.torch_device == "cuda"
        assert config.limits.max_file_size_mb == 50


# ---------------------------------------------------------------------------
# validate_config
# ---------------------------------------------------------------------------


class TestValidateConfig:
    def test_valid_default_config_returns_no_issues(self) -> None:
        """The bundled default config must produce no validation issues."""
        config = load_config()
        issues = validate_config(config)
        assert issues == []

    def test_invalid_torch_device_is_flagged(self, tmp_path: Path) -> None:
        """An unrecognised torch_device value must appear in the issues list."""
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text(
            "force_ocr: false\ntorch_device: tpu\n"
            "output_dir: output/\ninclude_page_numbers: false\nextract_images: true\n"
            "max_file_size_mb: 200\nallowed_extensions: ['.pdf']\nexclude_patterns: []\n",
            encoding="utf-8",
        )
        config = load_config(yaml_file)
        issues = validate_config(config)
        assert any("torch_device" in issue for issue in issues)

    def test_zero_max_file_size_is_flagged(self, tmp_path: Path) -> None:
        """A max_file_size_mb of 0 must appear in the issues list."""
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text(
            "force_ocr: false\ntorch_device: cpu\n"
            "output_dir: output/\ninclude_page_numbers: false\nextract_images: true\n"
            "max_file_size_mb: 0\nallowed_extensions: ['.pdf']\nexclude_patterns: []\n",
            encoding="utf-8",
        )
        config = load_config(yaml_file)
        issues = validate_config(config)
        assert any("max_file_size_mb" in issue for issue in issues)

    def test_empty_allowed_extensions_is_flagged(self, tmp_path: Path) -> None:
        """An empty allowed_extensions list must appear in the issues list."""
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text(
            "force_ocr: false\ntorch_device: cpu\n"
            "output_dir: output/\ninclude_page_numbers: false\nextract_images: true\n"
            "max_file_size_mb: 200\nallowed_extensions: []\nexclude_patterns: []\n",
            encoding="utf-8",
        )
        config = load_config(yaml_file)
        issues = validate_config(config)
        assert any("allowed_extensions" in issue for issue in issues)

    def test_multiple_issues_all_returned(self, tmp_path: Path) -> None:
        """validate_config must collect all issues, not stop at the first one."""
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text(
            "force_ocr: false\ntorch_device: tpu\n"
            "output_dir: output/\ninclude_page_numbers: false\nextract_images: true\n"
            "max_file_size_mb: 0\nallowed_extensions: []\nexclude_patterns: []\n",
            encoding="utf-8",
        )
        config = load_config(yaml_file)
        issues = validate_config(config)
        # torch_device, max_file_size_mb, and allowed_extensions are all invalid
        assert len(issues) >= 3


# ---------------------------------------------------------------------------
# _parse_marker_config (internal helper)
# ---------------------------------------------------------------------------


class TestParseMarkerConfig:
    def test_reads_force_ocr_and_torch_device(self) -> None:
        """Both marker fields must be parsed from the top-level dict."""
        raw = {"force_ocr": True, "torch_device": "cuda"}
        result = _parse_marker_config(raw)
        assert result.force_ocr is True
        assert result.torch_device == "cuda"

    def test_defaults_when_keys_absent(self) -> None:
        """Missing keys must fall back to sensible defaults."""
        result = _parse_marker_config({})
        assert result.force_ocr is False
        assert result.torch_device == "cpu"


# ---------------------------------------------------------------------------
# _parse_output_config (internal helper)
# ---------------------------------------------------------------------------


class TestParseOutputConfig:
    def test_reads_all_output_fields(self) -> None:
        """All three output fields must be parsed from the dict."""
        raw = {"output_dir": "my_out/", "include_page_numbers": True, "extract_images": False}
        result = _parse_output_config(raw)
        assert result.output_dir == "my_out/"
        assert result.include_page_numbers is True
        assert result.extract_images is False

    def test_defaults_when_keys_absent(self) -> None:
        """Missing keys must fall back to sensible defaults."""
        result = _parse_output_config({})
        assert result.output_dir == "output/"
        assert result.include_page_numbers is False
        assert result.extract_images is True


# ---------------------------------------------------------------------------
# _parse_limits_config (internal helper)
# ---------------------------------------------------------------------------


class TestParseLimitsConfig:
    def test_reads_max_file_size_mb(self) -> None:
        """max_file_size_mb must be parsed as an integer."""
        result = _parse_limits_config({"max_file_size_mb": 500})
        assert result.max_file_size_mb == 500

    def test_defaults_to_200_when_absent(self) -> None:
        """Missing key must default to 200."""
        result = _parse_limits_config({})
        assert result.max_file_size_mb == 200

    @pytest.mark.error_handling
    def test_non_integer_raises_value_error(self) -> None:
        """A non-integer value for max_file_size_mb must raise ValueError."""
        with pytest.raises(ValueError, match="max_file_size_mb must be an integer"):
            _parse_limits_config({"max_file_size_mb": "large"})


# ---------------------------------------------------------------------------
# _parse_filter_config (internal helper)
# ---------------------------------------------------------------------------


class TestParseFilterConfigFileTxt:
    def test_reads_extensions_and_patterns(self) -> None:
        """Both filter fields must be parsed from the dict."""
        raw = {"allowed_extensions": [".pdf", ".docx"], "exclude_patterns": ["~$*"]}
        result = _parse_filter_config(raw)
        assert result.allowed_extensions == [".pdf", ".docx"]
        assert result.exclude_patterns == ["~$*"]

    def test_non_list_values_default_to_empty(self) -> None:
        """Non-list values for filter fields must fall back to empty lists."""
        result = _parse_filter_config({"allowed_extensions": None, "exclude_patterns": None})
        assert result.allowed_extensions == []
        assert result.exclude_patterns == []

    def test_empty_dict_produces_empty_lists(self) -> None:
        """A dict with no filter keys must produce empty lists."""
        result = _parse_filter_config({})
        assert result.allowed_extensions == []
        assert result.exclude_patterns == []
