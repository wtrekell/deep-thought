"""Tests for the CLI entry point in deep_thought.file_txt.cli."""

from __future__ import annotations

import argparse
from pathlib import Path  # noqa: TC003
from unittest.mock import MagicMock, patch

import pytest

from deep_thought.file_txt.cli import (
    _build_config_with_overrides,
    _resolve_output_root,
    cmd_config,
    cmd_convert,
)
from deep_thought.file_txt.config import (
    EmailConfig,
    FileTxtConfig,
    FilterConfig,
    LimitsConfig,
    MarkerConfig,
    OutputConfig,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(
    force_ocr: bool = False,
    torch_device: str = "cpu",
    prefer_html: bool = False,
    full_headers: bool = False,
    include_attachments: bool = True,
    output_dir: str = "output/",
    include_page_numbers: bool = False,
    extract_images: bool = True,
) -> FileTxtConfig:
    """Return a FileTxtConfig with sensible test defaults."""
    return FileTxtConfig(
        marker=MarkerConfig(force_ocr=force_ocr, torch_device=torch_device),
        email=EmailConfig(
            prefer_html=prefer_html,
            full_headers=full_headers,
            include_attachments=include_attachments,
        ),
        output=OutputConfig(
            output_dir=output_dir,
            include_page_numbers=include_page_numbers,
            extract_images=extract_images,
        ),
        limits=LimitsConfig(max_file_size_mb=200),
        filter=FilterConfig(allowed_extensions=[".pdf"], exclude_patterns=[]),
    )


def _make_convert_args(**kwargs: object) -> argparse.Namespace:
    """Return a Namespace with default convert-command fields and any overrides."""
    defaults: dict[str, object] = {
        "path": "/some/path",
        "output": None,
        "config": None,
        "verbose": False,
        "dry_run": False,
        "nuke": False,
        "llm": False,
        "force_ocr": None,
        "torch_device": None,
        "include_page_numbers": None,
        "extract_images": None,
        "prefer_html": None,
        "full_headers": None,
        "include_attachments": None,
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


# ---------------------------------------------------------------------------
# TestBuildConfigWithOverrides
# ---------------------------------------------------------------------------


class TestBuildConfigWithOverrides:
    def test_force_ocr_true_overrides_config(self) -> None:
        """--force-ocr True must override the config's force_ocr value."""
        base_config = _make_config(force_ocr=False)
        args = _make_convert_args(force_ocr=True)

        result_config = _build_config_with_overrides(args, base_config)

        assert result_config.marker.force_ocr is True

    def test_force_ocr_false_overrides_config(self) -> None:
        """--no-force-ocr (False) must override a config value of True."""
        base_config = _make_config(force_ocr=True)
        args = _make_convert_args(force_ocr=False)

        result_config = _build_config_with_overrides(args, base_config)

        assert result_config.marker.force_ocr is False

    def test_force_ocr_none_preserves_config_value(self) -> None:
        """When force_ocr is None (flag not passed), config value must be kept."""
        base_config = _make_config(force_ocr=True)
        args = _make_convert_args(force_ocr=None)

        result_config = _build_config_with_overrides(args, base_config)

        assert result_config.marker.force_ocr is True

    def test_include_page_numbers_none_preserves_config(self) -> None:
        """When include_page_numbers is None, config value must be preserved."""
        base_config = _make_config(include_page_numbers=True)
        args = _make_convert_args(include_page_numbers=None)

        result_config = _build_config_with_overrides(args, base_config)

        assert result_config.output.include_page_numbers is True

    def test_prefer_html_override(self) -> None:
        """--prefer-html True must override the email config's prefer_html value."""
        base_config = _make_config(prefer_html=False)
        args = _make_convert_args(prefer_html=True)

        result_config = _build_config_with_overrides(args, base_config)

        assert result_config.email.prefer_html is True

    def test_full_headers_none_preserves_config(self) -> None:
        """When full_headers is None, config's full_headers value must be kept."""
        base_config = _make_config(full_headers=True)
        args = _make_convert_args(full_headers=None)

        result_config = _build_config_with_overrides(args, base_config)

        assert result_config.email.full_headers is True

    def test_include_attachments_override(self) -> None:
        """--no-include-attachments (False) must override config's include_attachments."""
        base_config = _make_config(include_attachments=True)
        args = _make_convert_args(include_attachments=False)

        result_config = _build_config_with_overrides(args, base_config)

        assert result_config.email.include_attachments is False

    def test_extract_images_true_overrides_config(self) -> None:
        """--extract-images True must override config's extract_images value."""
        base_config = _make_config(extract_images=False)
        args = _make_convert_args(extract_images=True)

        result_config = _build_config_with_overrides(args, base_config)

        assert result_config.output.extract_images is True

    def test_extract_images_none_preserves_config(self) -> None:
        """When extract_images is None, config's extract_images value must be kept."""
        base_config = _make_config(extract_images=False)
        args = _make_convert_args(extract_images=None)

        result_config = _build_config_with_overrides(args, base_config)

        assert result_config.output.extract_images is False

    def test_torch_device_override(self) -> None:
        """--torch-device must override the config's torch_device value."""
        base_config = _make_config(torch_device="cpu")
        args = _make_convert_args(torch_device="cuda")

        result_config = _build_config_with_overrides(args, base_config)

        assert result_config.marker.torch_device == "cuda"

    def test_torch_device_none_preserves_config(self) -> None:
        """When torch_device is None (not passed), config's value must be kept."""
        base_config = _make_config(torch_device="mps")
        args = _make_convert_args(torch_device=None)

        result_config = _build_config_with_overrides(args, base_config)

        assert result_config.marker.torch_device == "mps"


# ---------------------------------------------------------------------------
# TestResolveOutputRoot
# ---------------------------------------------------------------------------


class TestResolveOutputRoot:
    def test_cli_output_flag_overrides_config(self) -> None:
        """--output path must take precedence over config.output.output_dir."""
        base_config = _make_config(output_dir="output/")
        args = _make_convert_args(output="/custom/output/dir")

        resolved_path = _resolve_output_root(args, base_config)

        assert resolved_path == Path("/custom/output/dir")

    def test_config_value_used_when_output_not_passed(self) -> None:
        """When --output is not provided, config.output.output_dir must be used."""
        base_config = _make_config(output_dir="my_output/")
        args = _make_convert_args(output=None)

        resolved_path = _resolve_output_root(args, base_config)

        assert resolved_path == Path("my_output/")


# ---------------------------------------------------------------------------
# TestCmdConvert
# ---------------------------------------------------------------------------


class TestCmdConvert:
    def test_validation_warnings_printed_to_stderr(self, capsys: pytest.CaptureFixture[str]) -> None:
        """validate_config warnings must appear on stderr, not stdout."""
        base_config = _make_config()
        args = _make_convert_args(path="/some/path")

        fake_source_file = MagicMock()
        fake_source_file.name = "doc.pdf"

        fake_result = MagicMock()
        fake_result.skipped = False
        fake_result.errors = []
        fake_result.output_path = Path("/some/output/doc/doc.md")

        with (
            patch("deep_thought.file_txt.cli._load_config_from_args", return_value=base_config),
            patch("deep_thought.file_txt.cli.validate_config", return_value=["torch_device 'bad' is not valid."]),
            patch("deep_thought.file_txt.cli.collect_input_files", return_value=[fake_source_file]),
            patch("deep_thought.file_txt.cli.convert_file", return_value=fake_result),
        ):
            cmd_convert(args)

        captured = capsys.readouterr()
        assert "WARNING: torch_device" in captured.err

    def test_exit_code_zero_when_all_files_succeed(self) -> None:
        """When all files convert successfully, cmd_convert must not call sys.exit."""
        base_config = _make_config()
        args = _make_convert_args(path="/some/path")

        fake_source_file = MagicMock()
        fake_source_file.name = "doc.pdf"

        fake_result = MagicMock()
        fake_result.skipped = False
        fake_result.errors = []
        fake_result.output_path = Path("/some/output/doc/doc.md")

        with (
            patch("deep_thought.file_txt.cli._load_config_from_args", return_value=base_config),
            patch("deep_thought.file_txt.cli.validate_config", return_value=[]),
            patch("deep_thought.file_txt.cli.collect_input_files", return_value=[fake_source_file]),
            patch("deep_thought.file_txt.cli.convert_file", return_value=fake_result),
            patch("sys.exit") as mock_exit,
        ):
            cmd_convert(args)

        # sys.exit must not have been called with a non-zero code
        for call_args in mock_exit.call_args_list:
            assert call_args.args[0] == 0

    @pytest.mark.error_handling
    def test_exit_code_one_when_all_files_error(self) -> None:
        """When every file produces an error, cmd_convert must exit with code 1."""
        base_config = _make_config()
        args = _make_convert_args(path="/some/path")

        fake_source_file = MagicMock()
        fake_source_file.name = "bad.pdf"

        fake_result = MagicMock()
        fake_result.skipped = False
        fake_result.errors = ["Conversion failed: engine error"]

        with (
            patch("deep_thought.file_txt.cli._load_config_from_args", return_value=base_config),
            patch("deep_thought.file_txt.cli.validate_config", return_value=[]),
            patch("deep_thought.file_txt.cli.collect_input_files", return_value=[fake_source_file]),
            patch("deep_thought.file_txt.cli.convert_file", return_value=fake_result),
            pytest.raises(SystemExit) as exc_info,
        ):
            cmd_convert(args)

        assert exc_info.value.code == 1

    @pytest.mark.error_handling
    def test_exit_code_two_for_partial_failure(self) -> None:
        """When some files succeed and some error, cmd_convert must exit with code 2."""
        base_config = _make_config()
        args = _make_convert_args(path="/some/path")

        fake_ok_file = MagicMock()
        fake_ok_file.name = "ok.pdf"
        fake_error_file = MagicMock()
        fake_error_file.name = "bad.pdf"

        ok_result = MagicMock()
        ok_result.skipped = False
        ok_result.errors = []
        ok_result.output_path = Path("/out/ok/ok.md")

        error_result = MagicMock()
        error_result.skipped = False
        error_result.errors = ["Conversion failed"]

        def _side_effect_convert(source_path: object, *args_: object, **kwargs: object) -> MagicMock:
            if source_path is fake_ok_file:
                return ok_result
            return error_result

        with (
            patch("deep_thought.file_txt.cli._load_config_from_args", return_value=base_config),
            patch("deep_thought.file_txt.cli.validate_config", return_value=[]),
            patch(
                "deep_thought.file_txt.cli.collect_input_files",
                return_value=[fake_ok_file, fake_error_file],
            ),
            patch("deep_thought.file_txt.cli.convert_file", side_effect=_side_effect_convert),
            pytest.raises(SystemExit) as exc_info,
        ):
            cmd_convert(args)

        assert exc_info.value.code == 2

    def test_nuke_deletes_source_after_success(self, tmp_path: Path) -> None:
        """--nuke must delete the source file when conversion succeeds."""
        base_config = _make_config()
        source_file = tmp_path / "doc.pdf"
        source_file.write_bytes(b"fake pdf")

        args = _make_convert_args(path=str(tmp_path), nuke=True, dry_run=False)

        fake_result = MagicMock()
        fake_result.skipped = False
        fake_result.errors = []
        fake_result.output_path = tmp_path / "doc" / "doc.md"

        with (
            patch("deep_thought.file_txt.cli._load_config_from_args", return_value=base_config),
            patch("deep_thought.file_txt.cli.validate_config", return_value=[]),
            patch("deep_thought.file_txt.cli.collect_input_files", return_value=[source_file]),
            patch("deep_thought.file_txt.cli.convert_file", return_value=fake_result),
        ):
            cmd_convert(args)

        assert not source_file.exists()

    def test_nuke_does_not_delete_source_on_dry_run(self, tmp_path: Path) -> None:
        """--nuke must NOT delete the source file when --dry-run is also set."""
        base_config = _make_config()
        source_file = tmp_path / "doc.pdf"
        source_file.write_bytes(b"fake pdf")

        args = _make_convert_args(path=str(tmp_path), nuke=True, dry_run=True)

        fake_result = MagicMock()
        fake_result.skipped = False
        fake_result.errors = []
        fake_result.output_path = None  # dry-run produces no output path

        with (
            patch("deep_thought.file_txt.cli._load_config_from_args", return_value=base_config),
            patch("deep_thought.file_txt.cli.validate_config", return_value=[]),
            patch("deep_thought.file_txt.cli.collect_input_files", return_value=[source_file]),
            patch("deep_thought.file_txt.cli.convert_file", return_value=fake_result),
        ):
            cmd_convert(args)

        assert source_file.exists()

    def test_dry_run_does_not_write_output(self, capsys: pytest.CaptureFixture[str]) -> None:
        """--dry-run must pass dry_run=True to convert_file (not write files)."""
        base_config = _make_config()
        args = _make_convert_args(path="/some/path", dry_run=True)

        fake_source_file = MagicMock()
        fake_source_file.name = "doc.pdf"

        fake_result = MagicMock()
        fake_result.skipped = False
        fake_result.errors = []
        fake_result.output_path = None

        with (
            patch("deep_thought.file_txt.cli._load_config_from_args", return_value=base_config),
            patch("deep_thought.file_txt.cli.validate_config", return_value=[]),
            patch("deep_thought.file_txt.cli.collect_input_files", return_value=[fake_source_file]),
            patch("deep_thought.file_txt.cli.convert_file", return_value=fake_result) as mock_convert,
        ):
            cmd_convert(args)

        call_kwargs = mock_convert.call_args[1]
        assert call_kwargs.get("dry_run") is True


# ---------------------------------------------------------------------------
# TestCmdConfig
# ---------------------------------------------------------------------------


class TestCmdConfig:
    def test_valid_config_prints_valid_message(self, capsys: pytest.CaptureFixture[str]) -> None:
        """When validation passes, cmd_config must print 'Configuration is valid.'."""
        base_config = _make_config()
        args = argparse.Namespace(config=None)

        with (
            patch("deep_thought.file_txt.cli._load_config_from_args", return_value=base_config),
            patch("deep_thought.file_txt.cli.validate_config", return_value=[]),
        ):
            cmd_config(args)

        captured = capsys.readouterr()
        assert "Configuration is valid." in captured.out

    def test_invalid_config_prints_warnings(self, capsys: pytest.CaptureFixture[str]) -> None:
        """When validation finds issues, cmd_config must print the warning text."""
        base_config = _make_config()
        args = argparse.Namespace(config=None)

        validation_issues = ["torch_device 'tpu' is not valid.", "max_file_size_mb must be greater than 0."]

        with (
            patch("deep_thought.file_txt.cli._load_config_from_args", return_value=base_config),
            patch("deep_thought.file_txt.cli.validate_config", return_value=validation_issues),
        ):
            cmd_config(args)

        captured = capsys.readouterr()
        assert "torch_device" in captured.out
        assert "max_file_size_mb" in captured.out


# ---------------------------------------------------------------------------
# TestGetVersion
# ---------------------------------------------------------------------------


class TestGetVersion:
    def test_fallback_returns_default_version_string(self) -> None:
        """When importlib.metadata raises, _get_version must return '0.1.0'."""
        with patch("deep_thought.file_txt.cli._get_version", side_effect=Exception("no metadata")):
            # Call the real function directly to exercise the except branch
            pass

        # Test the actual fallback logic inline by calling the real function
        # with a patched importlib.metadata.version
        import importlib.metadata

        with patch.object(importlib.metadata, "version", side_effect=Exception("not found")):
            from deep_thought.file_txt import cli

            version_string = cli._get_version()

        assert version_string == "0.1.0"
