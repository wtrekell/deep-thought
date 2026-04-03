"""Tests for the configuration loader in deep_thought.file_txt.config."""

from __future__ import annotations

from pathlib import Path  # noqa: TC003

import pytest

from deep_thought.file_txt.config import (
    FileTxtConfig,
    _parse_email_config,
    _parse_filter_config,
    _parse_limits_config,
    _parse_output_config,
    _parse_pdf_config,
    load_config,
    save_default_config,
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

    def test_pdf_config_parsed(self) -> None:
        """A PdfConfig instance must be present after loading."""
        from deep_thought.file_txt.config import PdfConfig

        config = load_config()
        assert isinstance(config.pdf, PdfConfig)

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

    def test_email_config_parsed(self) -> None:
        """Email fields must be read from the YAML root."""
        config = load_config()
        assert isinstance(config.email.prefer_html, bool)
        assert isinstance(config.email.full_headers, bool)
        assert isinstance(config.email.include_attachments, bool)

    def test_allowed_extensions_contain_pdf(self) -> None:
        """The default config must include .pdf in allowed extensions."""
        config = load_config()
        assert ".pdf" in config.filter.allowed_extensions

    def test_allowed_extensions_contain_eml_and_msg(self) -> None:
        """The default config must include .eml and .msg in allowed extensions."""
        config = load_config()
        assert ".eml" in config.filter.allowed_extensions
        assert ".msg" in config.filter.allowed_extensions

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
            "output_dir: output/\ninclude_page_numbers: false\nextract_images: true\n"
            "max_file_size_mb: 100\nallowed_extensions: ['.pdf']\nexclude_patterns: []\n",
            encoding="utf-8",
        )
        config = load_config(minimal_yaml)
        assert config.limits.max_file_size_mb == 100

    def test_explicit_config_path_overrides_default(self, tmp_path: Path) -> None:
        """Passing an explicit path must load that file, not the default."""
        custom_yaml = tmp_path / "custom.yaml"
        custom_yaml.write_text(
            "output_dir: custom_out/\ninclude_page_numbers: true\nextract_images: false\n"
            "max_file_size_mb: 50\nallowed_extensions: ['.pdf']\nexclude_patterns: []\n",
            encoding="utf-8",
        )
        config = load_config(custom_yaml)
        assert config.output.output_dir == "custom_out/"
        assert config.limits.max_file_size_mb == 50

    def test_unknown_keys_emit_warning(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        """Unknown keys in the YAML must emit a WARNING and not raise an error."""
        yaml_with_typo = tmp_path / "typo.yaml"
        yaml_with_typo.write_text(
            "output_dir: output/\ninclude_page_numbers: false\nextract_images: true\n"
            "max_file_size_mb: 100\nallowed_extensions: ['.pdf']\nexclude_patterns: []\n"
            "ouptut_dir: typo/\n",  # misspelled key
            encoding="utf-8",
        )
        import logging

        with caplog.at_level(logging.WARNING, logger="deep_thought.file_txt.config"):
            config = load_config(yaml_with_typo)

        assert isinstance(config, FileTxtConfig)
        assert any("ouptut_dir" in record.message for record in caplog.records)

    def test_known_keys_do_not_emit_warning(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        """A config with only known keys must not emit any unknown-key warning."""
        clean_yaml = tmp_path / "clean.yaml"
        clean_yaml.write_text(
            "output_dir: output/\ninclude_page_numbers: false\nextract_images: true\n"
            "max_file_size_mb: 100\nallowed_extensions: ['.pdf']\nexclude_patterns: []\n",
            encoding="utf-8",
        )
        import logging

        with caplog.at_level(logging.WARNING, logger="deep_thought.file_txt.config"):
            load_config(clean_yaml)

        unknown_key_warnings = [r for r in caplog.records if "possibly misspelled" in r.message]
        assert unknown_key_warnings == []


# ---------------------------------------------------------------------------
# validate_config
# ---------------------------------------------------------------------------


class TestValidateConfig:
    def test_valid_default_config_returns_no_issues(self) -> None:
        """The bundled default config must produce no validation issues."""
        config = load_config()
        issues = validate_config(config)
        assert issues == []

    def test_zero_max_file_size_is_flagged(self, tmp_path: Path) -> None:
        """A max_file_size_mb of 0 must appear in the issues list."""
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text(
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
            "output_dir: output/\ninclude_page_numbers: false\nextract_images: true\n"
            "max_file_size_mb: 0\nallowed_extensions: []\nexclude_patterns: []\n",
            encoding="utf-8",
        )
        config = load_config(yaml_file)
        issues = validate_config(config)
        # max_file_size_mb and allowed_extensions are both invalid
        assert len(issues) >= 2


# ---------------------------------------------------------------------------
# _parse_pdf_config (internal helper)
# ---------------------------------------------------------------------------


class TestParsePdfConfig:
    def test_returns_pdf_config_instance(self) -> None:
        """_parse_pdf_config must always return a PdfConfig regardless of input."""
        from deep_thought.file_txt.config import PdfConfig

        result = _parse_pdf_config({"some_key": "value"})
        assert isinstance(result, PdfConfig)

    def test_empty_dict_returns_pdf_config(self) -> None:
        """An empty dict must produce a valid PdfConfig."""
        from deep_thought.file_txt.config import PdfConfig

        result = _parse_pdf_config({})
        assert isinstance(result, PdfConfig)


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


# ---------------------------------------------------------------------------
# _parse_email_config (internal helper)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# save_default_config
# ---------------------------------------------------------------------------


class TestSaveDefaultConfig:
    def test_writes_config_to_destination(self, tmp_path: Path) -> None:
        """save_default_config must write the bundled config to the given path."""
        destination_file = tmp_path / "config.yaml"
        save_default_config(destination_file)
        assert destination_file.exists()
        written_content = destination_file.read_text(encoding="utf-8")
        assert "output_dir" in written_content

    @pytest.mark.error_handling
    def test_raises_if_file_exists(self, tmp_path: Path) -> None:
        """save_default_config must raise FileExistsError if destination exists."""
        destination_file = tmp_path / "config.yaml"
        destination_file.write_text("existing content", encoding="utf-8")
        with pytest.raises(FileExistsError):
            save_default_config(destination_file)

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        """save_default_config must create parent dirs if they don't exist."""
        destination_file = tmp_path / "nested" / "deep" / "config.yaml"
        save_default_config(destination_file)
        assert destination_file.exists()


# ---------------------------------------------------------------------------
# _parse_email_config (internal helper)
# ---------------------------------------------------------------------------


class TestParseEmailConfig:
    def test_reads_all_email_fields(self) -> None:
        """All three email fields must be parsed from the top-level dict."""
        raw = {"prefer_html": True, "full_headers": True, "include_attachments": False}
        result = _parse_email_config(raw)
        assert result.prefer_html is True
        assert result.full_headers is True
        assert result.include_attachments is False

    def test_defaults_when_keys_absent(self) -> None:
        """Missing keys must fall back to sensible defaults."""
        result = _parse_email_config({})
        assert result.prefer_html is False
        assert result.full_headers is False
        assert result.include_attachments is True
