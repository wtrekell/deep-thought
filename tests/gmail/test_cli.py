"""Tests for the Gmail Tool CLI argument parsing and dispatch."""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from deep_thought.gmail.cli import (
    _build_argument_parser,
    _handle_save_config,
    _run_command,
    _setup_logging,
    cmd_collect,
    cmd_config,
    cmd_init,
    cmd_send,
    main,
)

# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


class TestBuildArgumentParser:
    """Tests for _build_argument_parser."""

    def test_returns_parser(self) -> None:
        """Should return an ArgumentParser instance."""
        parser = _build_argument_parser()
        assert isinstance(parser, argparse.ArgumentParser)

    def test_parses_version_flag(self) -> None:
        """Should support --version flag."""
        parser = _build_argument_parser()
        with pytest.raises(SystemExit) as exit_info:
            parser.parse_args(["--version"])
        assert exit_info.value.code == 0

    def test_parses_dry_run_flag(self) -> None:
        """Should parse --dry-run as boolean."""
        parser = _build_argument_parser()
        args = parser.parse_args(["--dry-run"])
        assert args.dry_run is True

    def test_parses_verbose_flag(self) -> None:
        """Should parse --verbose / -v as boolean."""
        parser = _build_argument_parser()
        args = parser.parse_args(["--verbose"])
        assert args.verbose is True

        args_short = parser.parse_args(["-v"])
        assert args_short.verbose is True

    def test_parses_config_path(self) -> None:
        """Should parse --config with a path value."""
        parser = _build_argument_parser()
        args = parser.parse_args(["--config", "/custom/config.yaml"])
        assert args.config == "/custom/config.yaml"

    def test_parses_output_path(self) -> None:
        """Should parse --output with a path value."""
        parser = _build_argument_parser()
        args = parser.parse_args(["--output", "/custom/output"])
        assert args.output == "/custom/output"

    def test_parses_max_emails(self) -> None:
        """Should parse --max-emails as an integer."""
        parser = _build_argument_parser()
        args = parser.parse_args(["--max-emails", "50"])
        assert args.max_emails == 50

    def test_parses_force_flag(self) -> None:
        """Should parse --force as boolean."""
        parser = _build_argument_parser()
        args = parser.parse_args(["--force"])
        assert args.force is True

    def test_parses_rule_flag(self) -> None:
        """Should parse --rule with a name value."""
        parser = _build_argument_parser()
        args = parser.parse_args(["--rule", "newsletters"])
        assert args.rule == "newsletters"

    def test_parses_save_config_flag(self) -> None:
        """Should parse --save-config with a path."""
        parser = _build_argument_parser()
        args = parser.parse_args(["--save-config", "/path/to/output.yaml"])
        assert args.save_config == "/path/to/output.yaml"

    def test_parses_init_subcommand(self) -> None:
        """Should recognise the init subcommand."""
        parser = _build_argument_parser()
        args = parser.parse_args(["init"])
        assert args.subcommand == "init"

    def test_parses_config_subcommand(self) -> None:
        """Should recognise the config subcommand."""
        parser = _build_argument_parser()
        args = parser.parse_args(["config"])
        assert args.subcommand == "config"

    def test_parses_auth_subcommand(self) -> None:
        """Should recognise the auth subcommand."""
        parser = _build_argument_parser()
        args = parser.parse_args(["auth"])
        assert args.subcommand == "auth"

    def test_parses_send_subcommand(self) -> None:
        """Should recognise the send subcommand with message_path."""
        parser = _build_argument_parser()
        args = parser.parse_args(["send", "message.md"])
        assert args.subcommand == "send"
        assert args.message_path == "message.md"

    def test_send_message_path_optional(self) -> None:
        """Should allow send without message_path."""
        parser = _build_argument_parser()
        args = parser.parse_args(["send"])
        assert args.subcommand == "send"
        assert args.message_path is None

    def test_defaults_none_subcommand(self) -> None:
        """Should default subcommand to None when no subcommand given."""
        parser = _build_argument_parser()
        args = parser.parse_args(["--dry-run"])
        assert args.subcommand is None

    def test_defaults_dry_run_false(self) -> None:
        """Should default --dry-run to False."""
        parser = _build_argument_parser()
        args = parser.parse_args([])
        assert args.dry_run is False

    def test_defaults_verbose_false(self) -> None:
        """Should default --verbose to False."""
        parser = _build_argument_parser()
        args = parser.parse_args([])
        assert args.verbose is False


# ---------------------------------------------------------------------------
# _setup_logging
# ---------------------------------------------------------------------------


class TestSetupLogging:
    """Tests for _setup_logging."""

    def test_verbose_sets_debug_level(self) -> None:
        """Should set root logger to DEBUG when verbose is True."""
        import logging

        _setup_logging(verbose=True)
        assert logging.getLogger().level == logging.DEBUG

    def test_non_verbose_sets_info_level(self) -> None:
        """Should set root logger to INFO when verbose is False."""
        import logging

        _setup_logging(verbose=False)
        assert logging.getLogger().level == logging.INFO


# ---------------------------------------------------------------------------
# _run_command
# ---------------------------------------------------------------------------


class TestRunCommand:
    """Tests for _run_command error wrapper."""

    def test_calls_handler(self) -> None:
        """Should call the provided handler with args."""
        handler = MagicMock()
        args = argparse.Namespace()
        _run_command(handler, args)
        handler.assert_called_once_with(args)

    def test_catches_file_not_found(self) -> None:
        """Should exit with code 1 on FileNotFoundError."""
        handler = MagicMock(side_effect=FileNotFoundError("missing.yaml"))
        with pytest.raises(SystemExit) as exit_info:
            _run_command(handler, argparse.Namespace())
        assert exit_info.value.code == 1

    def test_catches_os_error(self) -> None:
        """Should exit with code 1 on OSError."""
        handler = MagicMock(side_effect=OSError("disk full"))
        with pytest.raises(SystemExit) as exit_info:
            _run_command(handler, argparse.Namespace())
        assert exit_info.value.code == 1

    def test_catches_value_error(self) -> None:
        """Should exit with code 1 on ValueError."""
        handler = MagicMock(side_effect=ValueError("bad config"))
        with pytest.raises(SystemExit) as exit_info:
            _run_command(handler, argparse.Namespace())
        assert exit_info.value.code == 1

    def test_catches_unexpected_error(self) -> None:
        """Should exit with code 1 on unexpected exceptions."""
        handler = MagicMock(side_effect=RuntimeError("something broke"))
        with pytest.raises(SystemExit) as exit_info:
            _run_command(handler, argparse.Namespace())
        assert exit_info.value.code == 1


# ---------------------------------------------------------------------------
# _handle_save_config
# ---------------------------------------------------------------------------


class TestHandleSaveConfig:
    """Tests for _handle_save_config."""

    def test_writes_config_to_destination(self, tmp_path: Path) -> None:
        """Should copy the default config to the specified path."""

        destination = tmp_path / "my-config.yaml"

        with patch("deep_thought.gmail.cli.get_default_config_path") as mock_config_path:
            source = tmp_path / "source-config.yaml"
            source.write_text("# example config\nrules: []", encoding="utf-8")
            mock_config_path.return_value = source

            _handle_save_config(str(destination))

        assert destination.exists()
        assert destination.read_text() == "# example config\nrules: []"

    def test_exits_if_source_missing(self, tmp_path: Path) -> None:
        """Should exit with code 1 if the default config template is missing."""

        with patch("deep_thought.gmail.cli.get_default_config_path") as mock_config_path:
            mock_config_path.return_value = tmp_path / "nonexistent.yaml"

            with pytest.raises(SystemExit) as exit_info:
                _handle_save_config(str(tmp_path / "output.yaml"))

        assert exit_info.value.code == 1

    def test_exits_if_destination_exists(self, tmp_path: Path) -> None:
        """Should exit with code 1 if destination file already exists."""

        destination = tmp_path / "existing.yaml"
        destination.write_text("existing content", encoding="utf-8")

        with patch("deep_thought.gmail.cli.get_default_config_path") as mock_config_path:
            source = tmp_path / "source.yaml"
            source.write_text("# config", encoding="utf-8")
            mock_config_path.return_value = source

            with pytest.raises(SystemExit) as exit_info:
                _handle_save_config(str(destination))

        assert exit_info.value.code == 1


# ---------------------------------------------------------------------------
# main entry point
# ---------------------------------------------------------------------------


class TestMain:
    """Tests for the main() entry point."""

    def test_no_args_prints_help(self) -> None:
        """Should print help and exit 0 when invoked with no arguments."""
        with patch("sys.argv", ["gmail"]), pytest.raises(SystemExit) as exit_info:
            main()
        assert exit_info.value.code == 0

    def test_dispatches_to_config_handler(self) -> None:
        """Should dispatch 'config' subcommand to cmd_config."""
        with (
            patch("sys.argv", ["gmail", "config"]),
            patch("deep_thought.gmail.cli._run_command") as mock_run,
            patch("deep_thought.gmail.cli.load_dotenv"),
        ):
            main()
            mock_run.assert_called_once()
            handler_arg = mock_run.call_args[0][0]
            assert handler_arg is cmd_config

    def test_dispatches_to_init_handler(self) -> None:
        """Should dispatch 'init' subcommand to cmd_init."""
        with (
            patch("sys.argv", ["gmail", "init"]),
            patch("deep_thought.gmail.cli._run_command") as mock_run,
            patch("deep_thought.gmail.cli.load_dotenv"),
        ):
            main()
            handler_arg = mock_run.call_args[0][0]
            assert handler_arg is cmd_init

    def test_flags_without_subcommand_dispatches_collect(self) -> None:
        """Should dispatch to cmd_collect when flags are given but no subcommand."""
        with (
            patch("sys.argv", ["gmail", "--dry-run"]),
            patch("deep_thought.gmail.cli._run_command") as mock_run,
            patch("deep_thought.gmail.cli.load_dotenv"),
        ):
            main()
            handler_arg = mock_run.call_args[0][0]
            assert handler_arg is cmd_collect

    def test_save_config_flag(self, tmp_path: Path) -> None:
        """Should invoke _handle_save_config when --save-config is used."""

        destination = str(tmp_path / "out.yaml")
        with (
            patch("sys.argv", ["gmail", "--save-config", destination]),
            patch("deep_thought.gmail.cli._handle_save_config") as mock_save,
            patch("deep_thought.gmail.cli.load_dotenv"),
        ):
            main()
            mock_save.assert_called_once_with(destination)

    def test_dispatches_send_subcommand(self) -> None:
        """Should dispatch 'send' to cmd_send."""
        with (
            patch("sys.argv", ["gmail", "send", "message.md"]),
            patch("deep_thought.gmail.cli._run_command") as mock_run,
            patch("deep_thought.gmail.cli.load_dotenv"),
        ):
            main()
            handler_arg = mock_run.call_args[0][0]
            assert handler_arg is cmd_send
