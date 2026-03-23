"""Tests for the web tool CLI (deep_thought.web.cli).

Uses argparse directly and mocks at the module boundary so no real browser
launches, database writes, or filesystem operations occur in unit tests.
"""

from __future__ import annotations

import argparse
from pathlib import Path  # noqa: TC003
from unittest.mock import MagicMock, patch

import pytest

from deep_thought.web.cli import (
    _COMMAND_HANDLERS,
    _build_argument_parser,
    cmd_config,
    cmd_init,
    main,
)
from deep_thought.web.config import CrawlConfig, WebConfig

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def minimal_crawl_config() -> CrawlConfig:
    """Return a minimal CrawlConfig with safe test defaults."""
    return CrawlConfig(
        mode="blog",
        input_url=None,
        max_depth=3,
        max_pages=100,
        js_wait=1.0,
        browser_channel=None,
        stealth=False,
        include_patterns=[],
        exclude_patterns=[],
        retry_attempts=2,
        retry_delay=5.0,
        output_dir="data/web/export/",
        extract_images=False,
        generate_llms_files=True,
        index_depth=1,
        min_article_words=200,
        changelog_url=None,
    )


@pytest.fixture()
def minimal_web_config(minimal_crawl_config: CrawlConfig) -> WebConfig:
    """Return a minimal WebConfig wrapping the minimal CrawlConfig."""
    return WebConfig(crawl=minimal_crawl_config)


@pytest.fixture()
def args_base() -> argparse.Namespace:
    """Return a Namespace with all global flags at their defaults."""
    return argparse.Namespace(
        verbose=False,
        config=None,
        subcommand=None,
        save_config=None,
    )


# ---------------------------------------------------------------------------
# TestArgumentParser
# ---------------------------------------------------------------------------


class TestArgumentParser:
    def test_has_config_subcommand(self) -> None:
        """The 'config' subcommand must be parseable without error."""
        parser = _build_argument_parser()
        parsed = parser.parse_args(["config"])
        assert parsed.subcommand == "config"

    def test_has_init_subcommand(self) -> None:
        """The 'init' subcommand must be parseable without error."""
        parser = _build_argument_parser()
        parsed = parser.parse_args(["init"])
        assert parsed.subcommand == "init"

    def test_has_crawl_subcommand(self) -> None:
        """The 'crawl' subcommand must be parseable without error."""
        parser = _build_argument_parser()
        parsed = parser.parse_args(["crawl"])
        assert parsed.subcommand == "crawl"

    def test_crawl_subcommand_has_mode_flag(self) -> None:
        """The 'crawl' subcommand must accept a --mode flag."""
        parser = _build_argument_parser()
        parsed = parser.parse_args(["crawl", "--mode", "blog"])
        assert parsed.mode == "blog"

    def test_crawl_mode_defaults_to_none_when_not_set(self) -> None:
        """The --mode flag must default to None when not provided (config value is used)."""
        parser = _build_argument_parser()
        parsed = parser.parse_args(["crawl"])
        assert parsed.mode is None

    def test_crawl_subcommand_has_input_flag(self) -> None:
        """The 'crawl' subcommand must accept a --input flag."""
        parser = _build_argument_parser()
        parsed = parser.parse_args(["crawl", "--input", "https://example.com"])
        assert parsed.input == "https://example.com"

    def test_has_verbose_flag(self) -> None:
        """The --verbose flag must be present at the root level."""
        parser = _build_argument_parser()
        parsed = parser.parse_args(["--verbose", "config"])
        assert parsed.verbose is True

    def test_verbose_short_flag_works(self) -> None:
        """-v must be an alias for --verbose."""
        parser = _build_argument_parser()
        parsed = parser.parse_args(["-v", "config"])
        assert parsed.verbose is True

    def test_no_subcommand_defaults_to_none(self) -> None:
        """When no subcommand is given, subcommand dest must be None."""
        parser = _build_argument_parser()
        parsed, _ = parser.parse_known_args([])
        assert parsed.subcommand is None

    def test_init_subcommand_has_save_config_flag(self) -> None:
        """The 'init' subcommand must accept a --save-config flag."""
        parser = _build_argument_parser()
        parsed = parser.parse_args(["init", "--save-config", "/tmp/web-config.yaml"])
        assert parsed.save_config == "/tmp/web-config.yaml"

    def test_mode_choices_are_valid(self) -> None:
        """--mode must only accept 'blog', 'documentation', and 'direct'."""
        parser = _build_argument_parser()
        for valid_mode in ["blog", "documentation", "direct"]:
            parsed = parser.parse_args(["crawl", "--mode", valid_mode])
            assert parsed.mode == valid_mode

    @pytest.mark.error_handling
    def test_invalid_mode_raises_system_exit(self) -> None:
        """An invalid --mode value must cause argparse to exit with an error."""
        parser = _build_argument_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["crawl", "--mode", "invalid-mode"])


# ---------------------------------------------------------------------------
# TestCmdConfig
# ---------------------------------------------------------------------------


class TestCmdConfig:
    def test_prints_valid_message_for_valid_config(
        self,
        args_base: argparse.Namespace,
        minimal_web_config: WebConfig,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """cmd_config must print 'Configuration is valid.' when validation passes."""
        with (
            patch("deep_thought.web.cli.load_config", return_value=minimal_web_config),
            patch("deep_thought.web.cli.validate_config", return_value=[]),
        ):
            cmd_config(args_base)

        captured_output = capsys.readouterr().out
        assert "Configuration is valid." in captured_output

    def test_prints_loaded_configuration_section(
        self,
        args_base: argparse.Namespace,
        minimal_web_config: WebConfig,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """cmd_config must print a 'Loaded configuration:' section."""
        with (
            patch("deep_thought.web.cli.load_config", return_value=minimal_web_config),
            patch("deep_thought.web.cli.validate_config", return_value=[]),
        ):
            cmd_config(args_base)

        captured_output = capsys.readouterr().out
        assert "Loaded configuration:" in captured_output

    def test_prints_mode_value(
        self,
        args_base: argparse.Namespace,
        minimal_web_config: WebConfig,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """cmd_config must print the crawl mode from the loaded config."""
        with (
            patch("deep_thought.web.cli.load_config", return_value=minimal_web_config),
            patch("deep_thought.web.cli.validate_config", return_value=[]),
        ):
            cmd_config(args_base)

        captured_output = capsys.readouterr().out
        assert "blog" in captured_output

    def test_prints_validation_warnings_when_present(
        self,
        args_base: argparse.Namespace,
        minimal_web_config: WebConfig,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """cmd_config must display validation warnings when validation fails."""
        warning_message = "mode 'invalid' is not valid."
        with (
            patch("deep_thought.web.cli.load_config", return_value=minimal_web_config),
            patch("deep_thought.web.cli.validate_config", return_value=[warning_message]),
        ):
            cmd_config(args_base)

        captured_output = capsys.readouterr().out
        assert "WARNING" in captured_output
        assert warning_message in captured_output


# ---------------------------------------------------------------------------
# TestCmdInit
# ---------------------------------------------------------------------------


class TestCmdInit:
    """Tests for the cmd_init scaffolding command."""

    @staticmethod
    def _init_mocks() -> tuple[MagicMock, MagicMock, MagicMock]:
        """Return mock objects for save_default_config, copy_default_templates, and initialize_database."""
        mock_save_config = MagicMock()
        mock_copy_templates = MagicMock(return_value=[("created", "blog.yaml"), ("created", "docs.yaml")])
        mock_init_db = MagicMock()
        return mock_save_config, mock_copy_templates, mock_init_db

    def test_with_save_config_writes_file_to_temp_path(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """cmd_init with --save-config must write a config file to the specified path."""
        target_config_path = tmp_path / "my-web-config.yaml"
        mock_save, mock_templates, mock_db = self._init_mocks()

        args = argparse.Namespace(save_config=str(target_config_path), config=None)

        with (
            patch("deep_thought.web.cli.save_default_config", mock_save),
            patch("deep_thought.web.cli.copy_default_templates", mock_templates),
            patch("deep_thought.web.cli.initialize_database", mock_db),
        ):
            cmd_init(args)
            mock_save.assert_called_once_with(target_config_path)

    def test_prints_output_directory_paths(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """cmd_init must print both output directory paths."""
        mock_save, mock_templates, mock_db = self._init_mocks()

        args = argparse.Namespace(save_config=None, config=None)

        with (
            patch("deep_thought.web.cli.save_default_config", mock_save),
            patch("deep_thought.web.cli.copy_default_templates", mock_templates),
            patch("deep_thought.web.cli.initialize_database", mock_db),
            patch("deep_thought.web.cli.get_default_config_path", return_value=tmp_path / "web-config.yaml"),
        ):
            cmd_init(args)

        captured_output = capsys.readouterr().out
        assert "output/web" in captured_output
        assert "docs" in captured_output

    def test_prints_next_steps_guidance(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """cmd_init must print 'Next steps:' guidance to help the user get started."""
        mock_save, mock_templates, mock_db = self._init_mocks()

        args = argparse.Namespace(save_config=None, config=None)

        with (
            patch("deep_thought.web.cli.save_default_config", mock_save),
            patch("deep_thought.web.cli.copy_default_templates", mock_templates),
            patch("deep_thought.web.cli.initialize_database", mock_db),
            patch("deep_thought.web.cli.get_default_config_path", return_value=tmp_path / "web-config.yaml"),
        ):
            cmd_init(args)

        captured_output = capsys.readouterr().out
        assert "Next steps" in captured_output
        assert "web crawl --batch" in captured_output

    def test_calls_copy_default_templates(
        self,
        tmp_path: Path,
    ) -> None:
        """cmd_init must call copy_default_templates to scaffold batch configs."""
        mock_save, mock_templates, mock_db = self._init_mocks()

        args = argparse.Namespace(save_config=None, config=None)

        with (
            patch("deep_thought.web.cli.save_default_config", mock_save),
            patch("deep_thought.web.cli.copy_default_templates", mock_templates),
            patch("deep_thought.web.cli.initialize_database", mock_db),
            patch("deep_thought.web.cli.get_default_config_path", return_value=tmp_path / "web-config.yaml"),
        ):
            cmd_init(args)

        mock_templates.assert_called_once()

    def test_calls_initialize_database(
        self,
        tmp_path: Path,
    ) -> None:
        """cmd_init must initialize the SQLite database."""
        mock_save, mock_templates, mock_db = self._init_mocks()

        args = argparse.Namespace(save_config=None, config=None)

        with (
            patch("deep_thought.web.cli.save_default_config", mock_save),
            patch("deep_thought.web.cli.copy_default_templates", mock_templates),
            patch("deep_thought.web.cli.initialize_database", mock_db),
            patch("deep_thought.web.cli.get_default_config_path", return_value=tmp_path / "web-config.yaml"),
        ):
            cmd_init(args)

        mock_db.assert_called_once()

    def test_prints_batch_config_created_status(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """cmd_init must print 'created' status for newly copied batch configs."""
        mock_save, _, mock_db = self._init_mocks()
        mock_templates = MagicMock(return_value=[("created", "blog.yaml")])

        args = argparse.Namespace(save_config=None, config=None)

        with (
            patch("deep_thought.web.cli.save_default_config", mock_save),
            patch("deep_thought.web.cli.copy_default_templates", mock_templates),
            patch("deep_thought.web.cli.initialize_database", mock_db),
            patch("deep_thought.web.cli.get_default_config_path", return_value=tmp_path / "web-config.yaml"),
        ):
            cmd_init(args)

        captured_output = capsys.readouterr().out
        assert "Batch config created" in captured_output
        assert "blog.yaml" in captured_output

    def test_prints_batch_config_exists_status(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """cmd_init must print 'already exists' status for existing batch configs."""
        mock_save, _, mock_db = self._init_mocks()
        mock_templates = MagicMock(return_value=[("exists", "blog.yaml")])

        args = argparse.Namespace(save_config=None, config=None)

        with (
            patch("deep_thought.web.cli.save_default_config", mock_save),
            patch("deep_thought.web.cli.copy_default_templates", mock_templates),
            patch("deep_thought.web.cli.initialize_database", mock_db),
            patch("deep_thought.web.cli.get_default_config_path", return_value=tmp_path / "web-config.yaml"),
        ):
            cmd_init(args)

        captured_output = capsys.readouterr().out
        assert "already exists" in captured_output
        assert "blog.yaml" in captured_output

    def test_prints_database_initialized_message(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """cmd_init must print a database initialized message."""
        mock_save, mock_templates, mock_db = self._init_mocks()

        args = argparse.Namespace(save_config=None, config=None)

        with (
            patch("deep_thought.web.cli.save_default_config", mock_save),
            patch("deep_thought.web.cli.copy_default_templates", mock_templates),
            patch("deep_thought.web.cli.initialize_database", mock_db),
            patch("deep_thought.web.cli.get_default_config_path", return_value=tmp_path / "web-config.yaml"),
        ):
            cmd_init(args)

        captured_output = capsys.readouterr().out
        assert "Database initialized" in captured_output


# ---------------------------------------------------------------------------
# TestCopyDefaultTemplates
# ---------------------------------------------------------------------------


class TestCopyDefaultTemplates:
    """Tests for the copy_default_templates config helper."""

    def test_copies_template_when_target_missing(self, tmp_path: Path) -> None:
        """Template files must be copied when the target does not exist."""
        from deep_thought.web.config import copy_default_templates

        templates_dir = tmp_path / "templates"
        templates_dir.mkdir()
        (templates_dir / "blog-template.yaml").write_text("mode: blog\n")

        batch_dir = tmp_path / "batch"
        batch_dir.mkdir()

        with patch("deep_thought.web.config.get_templates_dir", return_value=templates_dir):
            results = copy_default_templates(batch_config_dir=batch_dir)

        assert results == [("created", "blog.yaml")]
        assert (batch_dir / "blog.yaml").exists()
        assert (batch_dir / "blog.yaml").read_text() == "mode: blog\n"

    def test_skips_copy_when_target_exists(self, tmp_path: Path) -> None:
        """Existing batch config files must not be overwritten."""
        from deep_thought.web.config import copy_default_templates

        templates_dir = tmp_path / "templates"
        templates_dir.mkdir()
        (templates_dir / "blog-template.yaml").write_text("mode: blog\n")

        batch_dir = tmp_path / "batch"
        batch_dir.mkdir()
        (batch_dir / "blog.yaml").write_text("mode: blog\ncustomized: true\n")

        with patch("deep_thought.web.config.get_templates_dir", return_value=templates_dir):
            results = copy_default_templates(batch_config_dir=batch_dir)

        assert results == [("exists", "blog.yaml")]
        assert (batch_dir / "blog.yaml").read_text() == "mode: blog\ncustomized: true\n"

    def test_strips_template_suffix_from_filename(self, tmp_path: Path) -> None:
        """The '-template' suffix must be stripped from the copied filename."""
        from deep_thought.web.config import copy_default_templates

        templates_dir = tmp_path / "templates"
        templates_dir.mkdir()
        (templates_dir / "docs-template.yaml").write_text("mode: documentation\n")

        batch_dir = tmp_path / "batch"
        batch_dir.mkdir()

        with patch("deep_thought.web.config.get_templates_dir", return_value=templates_dir):
            results = copy_default_templates(batch_config_dir=batch_dir)

        assert results == [("created", "docs.yaml")]
        assert (batch_dir / "docs.yaml").exists()

    def test_returns_empty_list_when_no_templates(self, tmp_path: Path) -> None:
        """An empty list must be returned when the templates directory has no templates."""
        from deep_thought.web.config import copy_default_templates

        templates_dir = tmp_path / "templates"
        templates_dir.mkdir()

        with patch("deep_thought.web.config.get_templates_dir", return_value=templates_dir):
            results = copy_default_templates(batch_config_dir=tmp_path / "batch")

        assert results == []

    def test_returns_empty_list_when_templates_dir_missing(self, tmp_path: Path) -> None:
        """An empty list must be returned when the templates directory does not exist."""
        from deep_thought.web.config import copy_default_templates

        with patch("deep_thought.web.config.get_templates_dir", return_value=tmp_path / "nonexistent"):
            results = copy_default_templates(batch_config_dir=tmp_path / "batch")

        assert results == []


# ---------------------------------------------------------------------------
# TestMain
# ---------------------------------------------------------------------------


class TestMain:
    def test_dispatches_to_config_handler(self) -> None:
        """main must call the handler registered for the 'config' subcommand."""
        mock_handler = MagicMock()
        with (
            patch("sys.argv", ["web", "config"]),
            patch.dict(_COMMAND_HANDLERS, {"config": mock_handler}),
        ):
            main()
            mock_handler.assert_called_once()

    def test_dispatches_to_init_handler(self) -> None:
        """main must call the handler registered for the 'init' subcommand."""
        mock_handler = MagicMock()
        with (
            patch("sys.argv", ["web", "init"]),
            patch.dict(_COMMAND_HANDLERS, {"init": mock_handler}),
        ):
            main()
            mock_handler.assert_called_once()

    @pytest.mark.error_handling
    def test_file_not_found_exits_with_code_1(self, capsys: pytest.CaptureFixture[str]) -> None:
        """A FileNotFoundError raised inside a handler must exit with code 1."""
        mock_handler = MagicMock(side_effect=FileNotFoundError("web-config.yaml"))
        with (
            patch("sys.argv", ["web", "config"]),
            patch.dict(_COMMAND_HANDLERS, {"config": mock_handler}),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()
        assert exc_info.value.code == 1
        assert "File not found" in capsys.readouterr().err

    @pytest.mark.error_handling
    def test_os_error_exits_with_code_1(self, capsys: pytest.CaptureFixture[str]) -> None:
        """An OSError raised inside a handler must exit with code 1."""
        mock_handler = MagicMock(side_effect=OSError("permission denied"))
        with (
            patch("sys.argv", ["web", "config"]),
            patch.dict(_COMMAND_HANDLERS, {"config": mock_handler}),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()
        assert exc_info.value.code == 1
        assert "permission denied" in capsys.readouterr().err

    @pytest.mark.error_handling
    def test_unexpected_exception_exits_with_code_1(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Any unhandled exception inside a handler must exit with code 1."""
        mock_handler = MagicMock(side_effect=RuntimeError("unexpected boom"))
        with (
            patch("sys.argv", ["web", "config"]),
            patch.dict(_COMMAND_HANDLERS, {"config": mock_handler}),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()
        assert exc_info.value.code == 1
        assert "unexpected error" in capsys.readouterr().err.lower()

    @pytest.mark.error_handling
    def test_crawl_without_input_exits_with_code_1(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Calling main with no subcommand and no --input must exit with code 1."""
        with (
            patch("sys.argv", ["web"]),
            patch("deep_thought.web.cli.load_config") as mock_load,
            pytest.raises(SystemExit) as exc_info,
        ):
            mock_load.return_value = WebConfig(
                crawl=CrawlConfig(
                    mode="blog",
                    input_url=None,
                    max_depth=3,
                    max_pages=100,
                    js_wait=1.0,
                    browser_channel=None,
                    stealth=False,
                    include_patterns=[],
                    exclude_patterns=[],
                    retry_attempts=2,
                    retry_delay=5.0,
                    output_dir="data/web/export/",
                    extract_images=False,
                    generate_llms_files=True,
                    index_depth=1,
                    min_article_words=200,
                    changelog_url=None,
                )
            )
            main()
        assert exc_info.value.code == 1
