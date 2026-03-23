"""Tests for the GCal Tool CLI argument parsing and dispatch."""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from deep_thought.gcal.cli import (
    _build_argument_parser,
    _handle_save_config,
    _run_command,
    _setup_logging,
    cmd_auth,
    cmd_config,
    cmd_create,
    cmd_delete,
    cmd_init,
    cmd_pull,
    cmd_update,
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

    def test_parses_calendar_flag(self) -> None:
        """Should parse --calendar with a comma-separated value."""
        parser = _build_argument_parser()
        args = parser.parse_args(["--calendar", "primary,work@group.calendar.google.com"])
        assert args.calendar == "primary,work@group.calendar.google.com"

    def test_parses_days_back_flag(self) -> None:
        """Should parse --days-back as an integer stored as days_back."""
        parser = _build_argument_parser()
        args = parser.parse_args(["--days-back", "14"])
        assert args.days_back == 14

    def test_parses_days_ahead_flag(self) -> None:
        """Should parse --days-ahead as an integer stored as days_ahead."""
        parser = _build_argument_parser()
        args = parser.parse_args(["--days-ahead", "60"])
        assert args.days_ahead == 60

    def test_parses_force_flag(self) -> None:
        """Should parse --force as boolean."""
        parser = _build_argument_parser()
        args = parser.parse_args(["--force"])
        assert args.force is True

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

    def test_parses_pull_subcommand(self) -> None:
        """Should recognise the pull subcommand."""
        parser = _build_argument_parser()
        args = parser.parse_args(["pull"])
        assert args.subcommand == "pull"

    def test_parses_create_subcommand(self) -> None:
        """Should recognise the create subcommand with file_path."""
        parser = _build_argument_parser()
        args = parser.parse_args(["create", "event.md"])
        assert args.subcommand == "create"
        assert args.file_path == "event.md"

    def test_create_file_path_optional(self) -> None:
        """Should allow create without file_path (defaults to None)."""
        parser = _build_argument_parser()
        args = parser.parse_args(["create"])
        assert args.subcommand == "create"
        assert args.file_path is None

    def test_parses_update_subcommand(self) -> None:
        """Should recognise the update subcommand with file_path."""
        parser = _build_argument_parser()
        args = parser.parse_args(["update", "event.md"])
        assert args.subcommand == "update"
        assert args.file_path == "event.md"

    def test_parses_delete_subcommand(self) -> None:
        """Should recognise the delete subcommand with event_id."""
        parser = _build_argument_parser()
        args = parser.parse_args(["delete", "evt_abc123"])
        assert args.subcommand == "delete"
        assert args.event_id == "evt_abc123"

    def test_delete_defaults_calendar_id_to_primary(self) -> None:
        """Should default --calendar-id to 'primary' on the delete subcommand."""
        parser = _build_argument_parser()
        args = parser.parse_args(["delete", "evt_abc123"])
        assert args.calendar_id == "primary"

    def test_delete_parses_calendar_id_override(self) -> None:
        """Should accept a --calendar-id override on the delete subcommand."""
        parser = _build_argument_parser()
        args = parser.parse_args(["delete", "evt_abc123", "--calendar-id", "work@group.calendar.google.com"])
        assert args.calendar_id == "work@group.calendar.google.com"

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

    def test_defaults_force_false(self) -> None:
        """Should default --force to False."""
        parser = _build_argument_parser()
        args = parser.parse_args([])
        assert args.force is False


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

        with patch("deep_thought.gcal.cli.get_default_config_path") as mock_config_path:
            source = tmp_path / "source-config.yaml"
            source.write_text("# example config\ncalendars: []", encoding="utf-8")
            mock_config_path.return_value = source

            _handle_save_config(str(destination))

        assert destination.exists()
        assert destination.read_text() == "# example config\ncalendars: []"

    def test_exits_if_source_missing(self, tmp_path: Path) -> None:
        """Should exit with code 1 if the default config template is missing."""
        with patch("deep_thought.gcal.cli.get_default_config_path") as mock_config_path:
            mock_config_path.return_value = tmp_path / "nonexistent.yaml"

            with pytest.raises(SystemExit) as exit_info:
                _handle_save_config(str(tmp_path / "output.yaml"))

        assert exit_info.value.code == 1

    def test_exits_if_destination_exists(self, tmp_path: Path) -> None:
        """Should exit with code 1 if destination file already exists."""
        destination = tmp_path / "existing.yaml"
        destination.write_text("existing content", encoding="utf-8")

        with patch("deep_thought.gcal.cli.get_default_config_path") as mock_config_path:
            source = tmp_path / "source.yaml"
            source.write_text("# config", encoding="utf-8")
            mock_config_path.return_value = source

            with pytest.raises(SystemExit) as exit_info:
                _handle_save_config(str(destination))

        assert exit_info.value.code == 1


# ---------------------------------------------------------------------------
# TestMainEntryPoint
# ---------------------------------------------------------------------------


class TestMainEntryPoint:
    """Tests for the main() entry point."""

    def test_no_args_prints_help(self) -> None:
        """Should print help and exit 0 when invoked with no arguments."""
        with patch("sys.argv", ["gcal"]), pytest.raises(SystemExit) as exit_info:
            main()
        assert exit_info.value.code == 0

    def test_version_flag_exits_zero(self) -> None:
        """Should print version and exit 0 when --version is given."""
        with patch("sys.argv", ["gcal", "--version"]), pytest.raises(SystemExit) as exit_info:
            main()
        assert exit_info.value.code == 0

    def test_dispatches_to_init_handler(self) -> None:
        """Should dispatch 'init' subcommand to cmd_init."""
        with (
            patch("sys.argv", ["gcal", "init"]),
            patch("deep_thought.gcal.cli._run_command") as mock_run,
            patch("deep_thought.gcal.cli.load_dotenv"),
        ):
            main()
            handler_arg = mock_run.call_args[0][0]
            assert handler_arg is cmd_init

    def test_dispatches_to_config_handler(self) -> None:
        """Should dispatch 'config' subcommand to cmd_config."""
        with (
            patch("sys.argv", ["gcal", "config"]),
            patch("deep_thought.gcal.cli._run_command") as mock_run,
            patch("deep_thought.gcal.cli.load_dotenv"),
        ):
            main()
            handler_arg = mock_run.call_args[0][0]
            assert handler_arg is cmd_config

    def test_dispatches_to_auth_handler(self) -> None:
        """Should dispatch 'auth' subcommand to cmd_auth."""
        with (
            patch("sys.argv", ["gcal", "auth"]),
            patch("deep_thought.gcal.cli._run_command") as mock_run,
            patch("deep_thought.gcal.cli.load_dotenv"),
        ):
            main()
            handler_arg = mock_run.call_args[0][0]
            assert handler_arg is cmd_auth

    def test_dispatches_to_pull_handler(self) -> None:
        """Should dispatch 'pull' subcommand to cmd_pull."""
        with (
            patch("sys.argv", ["gcal", "pull"]),
            patch("deep_thought.gcal.cli._run_command") as mock_run,
            patch("deep_thought.gcal.cli.load_dotenv"),
        ):
            main()
            handler_arg = mock_run.call_args[0][0]
            assert handler_arg is cmd_pull

    def test_dispatches_to_create_handler(self) -> None:
        """Should dispatch 'create' subcommand to cmd_create."""
        with (
            patch("sys.argv", ["gcal", "create", "event.md"]),
            patch("deep_thought.gcal.cli._run_command") as mock_run,
            patch("deep_thought.gcal.cli.load_dotenv"),
        ):
            main()
            handler_arg = mock_run.call_args[0][0]
            assert handler_arg is cmd_create

    def test_dispatches_to_update_handler(self) -> None:
        """Should dispatch 'update' subcommand to cmd_update."""
        with (
            patch("sys.argv", ["gcal", "update", "event.md"]),
            patch("deep_thought.gcal.cli._run_command") as mock_run,
            patch("deep_thought.gcal.cli.load_dotenv"),
        ):
            main()
            handler_arg = mock_run.call_args[0][0]
            assert handler_arg is cmd_update

    def test_dispatches_to_delete_handler(self) -> None:
        """Should dispatch 'delete' subcommand to cmd_delete."""
        with (
            patch("sys.argv", ["gcal", "delete", "evt_abc123"]),
            patch("deep_thought.gcal.cli._run_command") as mock_run,
            patch("deep_thought.gcal.cli.load_dotenv"),
        ):
            main()
            handler_arg = mock_run.call_args[0][0]
            assert handler_arg is cmd_delete

    def test_flags_without_subcommand_dispatches_pull(self) -> None:
        """Should dispatch to cmd_pull when flags are given but no subcommand."""
        with (
            patch("sys.argv", ["gcal", "--dry-run"]),
            patch("deep_thought.gcal.cli._run_command") as mock_run,
            patch("deep_thought.gcal.cli.load_dotenv"),
        ):
            main()
            handler_arg = mock_run.call_args[0][0]
            assert handler_arg is cmd_pull

    def test_save_config_flag_invokes_handler(self, tmp_path: Path) -> None:
        """Should invoke _handle_save_config when --save-config is used."""
        destination = str(tmp_path / "out.yaml")
        with (
            patch("sys.argv", ["gcal", "--save-config", destination]),
            patch("deep_thought.gcal.cli._handle_save_config") as mock_save,
            patch("deep_thought.gcal.cli.load_dotenv"),
        ):
            main()
            mock_save.assert_called_once_with(destination)


# ---------------------------------------------------------------------------
# TestCmdInit
# ---------------------------------------------------------------------------


class TestCmdInit:
    """Tests for cmd_init."""

    def test_creates_directories_and_database(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """Should initialise the database and create required subdirectories."""
        mock_db_path = tmp_path / "gcal.db"
        mock_connection = MagicMock()

        mock_config = MagicMock()
        mock_config.credentials_path = str(tmp_path / "credentials.json")

        args = argparse.Namespace(config=None, output=None, calendar=None, days_back=None, days_ahead=None)

        with (
            patch("deep_thought.gcal.cli.get_database_path", return_value=mock_db_path),
            patch("deep_thought.gcal.cli.initialize_database", return_value=mock_connection) as mock_init_db,
            patch("deep_thought.gcal.cli._load_config_from_args", return_value=mock_config),
        ):
            cmd_init(args)
            mock_init_db.assert_called_once_with(mock_db_path)
            mock_connection.close.assert_called_once()

        captured_output = capsys.readouterr()
        assert "GCal Tool initialised successfully." in captured_output.out
        assert str(mock_db_path) in captured_output.out

    def test_prints_credentials_warning_when_missing(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """Should warn when credentials.json does not exist."""
        mock_db_path = tmp_path / "gcal.db"
        mock_connection = MagicMock()

        mock_config = MagicMock()
        mock_config.credentials_path = str(tmp_path / "credentials.json")  # file does not exist

        args = argparse.Namespace(config=None, output=None, calendar=None, days_back=None, days_ahead=None)

        with (
            patch("deep_thought.gcal.cli.get_database_path", return_value=mock_db_path),
            patch("deep_thought.gcal.cli.initialize_database", return_value=mock_connection),
            patch("deep_thought.gcal.cli._load_config_from_args", return_value=mock_config),
        ):
            cmd_init(args)

        captured_output = capsys.readouterr()
        assert "WARNING: Credentials NOT found" in captured_output.out

    def test_prints_credentials_found_when_present(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """Should confirm credentials found when credentials.json exists."""
        mock_db_path = tmp_path / "gcal.db"
        mock_connection = MagicMock()

        credentials_file = tmp_path / "credentials.json"
        credentials_file.write_text("{}", encoding="utf-8")

        mock_config = MagicMock()
        mock_config.credentials_path = str(credentials_file)

        args = argparse.Namespace(config=None, output=None, calendar=None, days_back=None, days_ahead=None)

        with (
            patch("deep_thought.gcal.cli.get_database_path", return_value=mock_db_path),
            patch("deep_thought.gcal.cli.initialize_database", return_value=mock_connection),
            patch("deep_thought.gcal.cli._load_config_from_args", return_value=mock_config),
        ):
            cmd_init(args)

        captured_output = capsys.readouterr()
        assert "Credentials found at:" in captured_output.out


# ---------------------------------------------------------------------------
# TestCmdConfig
# ---------------------------------------------------------------------------


class TestCmdConfig:
    """Tests for cmd_config."""

    def test_loads_and_displays_config(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Should load the config and print all settings."""
        mock_config = MagicMock()
        mock_config.credentials_path = "src/config/gcal/credentials.json"
        mock_config.token_path = "data/gcal/token.json"
        mock_config.scopes = ["https://www.googleapis.com/auth/calendar"]
        mock_config.api_rate_limit_rpm = 250
        mock_config.retry_max_attempts = 3
        mock_config.retry_base_delay_seconds = 1
        mock_config.calendars = ["primary"]
        mock_config.lookback_days = 7
        mock_config.lookahead_days = 30
        mock_config.include_cancelled = False
        mock_config.single_events = True
        mock_config.output_dir = "data/gcal/export/"
        mock_config.generate_llms_files = False
        mock_config.flat_output = False

        args = argparse.Namespace(config=None, output=None, calendar=None, days_back=None, days_ahead=None)

        with (
            patch("deep_thought.gcal.cli._load_config_from_args", return_value=mock_config),
            patch("deep_thought.gcal.cli.validate_config", return_value=[]),
        ):
            cmd_config(args)

        captured_output = capsys.readouterr()
        assert "Configuration is valid." in captured_output.out
        assert "credentials_path" in captured_output.out
        assert "calendars" in captured_output.out

    def test_shows_validation_issues(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Should display validation warnings when config has issues."""
        mock_config = MagicMock()
        mock_config.credentials_path = ""
        mock_config.token_path = ""
        mock_config.scopes = []
        mock_config.calendars = []
        mock_config.lookback_days = 7
        mock_config.lookahead_days = 30
        mock_config.include_cancelled = False
        mock_config.single_events = True
        mock_config.output_dir = ""
        mock_config.generate_llms_files = False
        mock_config.flat_output = False
        mock_config.api_rate_limit_rpm = 250
        mock_config.retry_max_attempts = 3
        mock_config.retry_base_delay_seconds = 1

        args = argparse.Namespace(config=None, output=None, calendar=None, days_back=None, days_ahead=None)

        validation_problems = ["credentials_path is empty", "No calendars configured"]
        with (
            patch("deep_thought.gcal.cli._load_config_from_args", return_value=mock_config),
            patch("deep_thought.gcal.cli.validate_config", return_value=validation_problems),
        ):
            cmd_config(args)

        captured_output = capsys.readouterr()
        assert "Configuration issues (2 found)" in captured_output.out
        assert "WARNING: credentials_path is empty" in captured_output.out
        assert "WARNING: No calendars configured" in captured_output.out


# ---------------------------------------------------------------------------
# TestCmdAuth
# ---------------------------------------------------------------------------


class TestCmdAuth:
    """Tests for cmd_auth."""

    def test_calls_authenticate(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Should authenticate the client and print a success message."""
        mock_config = MagicMock()
        mock_client = MagicMock()

        args = argparse.Namespace(config=None, output=None, calendar=None, days_back=None, days_ahead=None)

        with (
            patch("deep_thought.gcal.cli._load_config_from_args", return_value=mock_config),
            patch("deep_thought.gcal.cli._make_client_from_config", return_value=mock_client),
        ):
            cmd_auth(args)

        captured_output = capsys.readouterr()
        assert "Authentication successful." in captured_output.out


# ---------------------------------------------------------------------------
# TestCmdPull
# ---------------------------------------------------------------------------


class TestCmdPull:
    """Tests for cmd_pull."""

    def _make_pull_args(self, **kwargs: object) -> argparse.Namespace:
        """Build an argparse.Namespace suitable for cmd_pull."""
        defaults: dict[str, object] = {
            "config": None,
            "output": None,
            "calendar": None,
            "days_back": None,
            "days_ahead": None,
            "dry_run": False,
            "force": False,
        }
        defaults.update(kwargs)
        return argparse.Namespace(**defaults)

    def test_calls_run_pull_with_correct_params(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Should call run_pull with client, config, connection, and flags."""
        from deep_thought.gcal.models import PullResult

        mock_config = MagicMock()
        mock_client = MagicMock()
        mock_connection = MagicMock()
        pull_result = PullResult(created=2, updated=1, cancelled=0, unchanged=3, calendars_synced=1)

        args = self._make_pull_args()

        mock_run_pull = MagicMock(return_value=pull_result)

        with (
            patch("deep_thought.gcal.cli._load_config_from_args", return_value=mock_config),
            patch("deep_thought.gcal.cli._make_client_from_config", return_value=mock_client),
            patch("deep_thought.gcal.cli.initialize_database", return_value=mock_connection),
            patch.dict("sys.modules", {"deep_thought.gcal.pull": MagicMock(run_pull=mock_run_pull)}),
        ):
            cmd_pull(args)

        mock_run_pull.assert_called_once()
        captured_output = capsys.readouterr()
        assert "Pull complete" in captured_output.out

    def test_dry_run_prefix_shown(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Should prefix output with [dry-run] when --dry-run is set."""
        from deep_thought.gcal.models import PullResult

        mock_config = MagicMock()
        mock_client = MagicMock()
        mock_connection = MagicMock()
        pull_result = PullResult(created=0, updated=0, cancelled=0, unchanged=0, calendars_synced=1)

        args = self._make_pull_args(dry_run=True)

        mock_run_pull = MagicMock(return_value=pull_result)

        with (
            patch("deep_thought.gcal.cli._load_config_from_args", return_value=mock_config),
            patch("deep_thought.gcal.cli._make_client_from_config", return_value=mock_client),
            patch("deep_thought.gcal.cli.initialize_database", return_value=mock_connection),
            patch.dict("sys.modules", {"deep_thought.gcal.pull": MagicMock(run_pull=mock_run_pull)}),
        ):
            cmd_pull(args)

        captured_output = capsys.readouterr()
        assert "[dry-run]" in captured_output.out

    def test_force_flag_passed_to_run_pull(self) -> None:
        """Should pass force=True to run_pull when --force is set."""
        from deep_thought.gcal.models import PullResult

        mock_config = MagicMock()
        mock_client = MagicMock()
        mock_connection = MagicMock()
        pull_result = PullResult(created=0, updated=0, cancelled=0, unchanged=0, calendars_synced=1)

        args = self._make_pull_args(force=True)

        mock_run_pull = MagicMock(return_value=pull_result)

        with (
            patch("deep_thought.gcal.cli._load_config_from_args", return_value=mock_config),
            patch("deep_thought.gcal.cli._make_client_from_config", return_value=mock_client),
            patch("deep_thought.gcal.cli.initialize_database", return_value=mock_connection),
            patch.dict("sys.modules", {"deep_thought.gcal.pull": MagicMock(run_pull=mock_run_pull)}),
        ):
            cmd_pull(args)

        call_kwargs = mock_run_pull.call_args[1]
        assert call_kwargs["force"] is True

    def test_calendar_override_passed_to_run_pull(self) -> None:
        """Should split and pass --calendar value as calendar_override list."""
        from deep_thought.gcal.models import PullResult

        mock_config = MagicMock()
        mock_client = MagicMock()
        mock_connection = MagicMock()
        pull_result = PullResult(created=0, updated=0, cancelled=0, unchanged=0, calendars_synced=1)

        args = self._make_pull_args(calendar="primary,work@group.calendar.google.com")

        mock_run_pull = MagicMock(return_value=pull_result)

        with (
            patch("deep_thought.gcal.cli._load_config_from_args", return_value=mock_config),
            patch("deep_thought.gcal.cli._make_client_from_config", return_value=mock_client),
            patch("deep_thought.gcal.cli.initialize_database", return_value=mock_connection),
            patch.dict("sys.modules", {"deep_thought.gcal.pull": MagicMock(run_pull=mock_run_pull)}),
        ):
            cmd_pull(args)

        call_kwargs = mock_run_pull.call_args[1]
        assert call_kwargs["calendar_override"] == ["primary", "work@group.calendar.google.com"]

    def test_no_calendar_flag_passes_none_override(self) -> None:
        """Should pass calendar_override=None when no --calendar flag is given."""
        from deep_thought.gcal.models import PullResult

        mock_config = MagicMock()
        mock_client = MagicMock()
        mock_connection = MagicMock()
        pull_result = PullResult(created=0, updated=0, cancelled=0, unchanged=0, calendars_synced=1)

        args = self._make_pull_args(calendar=None)

        mock_run_pull = MagicMock(return_value=pull_result)

        with (
            patch("deep_thought.gcal.cli._load_config_from_args", return_value=mock_config),
            patch("deep_thought.gcal.cli._make_client_from_config", return_value=mock_client),
            patch("deep_thought.gcal.cli.initialize_database", return_value=mock_connection),
            patch.dict("sys.modules", {"deep_thought.gcal.pull": MagicMock(run_pull=mock_run_pull)}),
        ):
            cmd_pull(args)

        call_kwargs = mock_run_pull.call_args[1]
        assert call_kwargs["calendar_override"] is None


# ---------------------------------------------------------------------------
# TestCmdCreate
# ---------------------------------------------------------------------------


class TestCmdCreate:
    """Tests for cmd_create."""

    def _make_create_args(self, **kwargs: object) -> argparse.Namespace:
        """Build an argparse.Namespace suitable for cmd_create."""
        defaults: dict[str, object] = {
            "config": None,
            "output": None,
            "calendar": None,
            "days_back": None,
            "days_ahead": None,
            "dry_run": False,
            "file_path": None,
        }
        defaults.update(kwargs)
        return argparse.Namespace(**defaults)

    def test_exits_when_file_path_missing(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Should exit with code 1 when no file_path argument is given."""
        args = self._make_create_args(file_path=None)
        with pytest.raises(SystemExit) as exit_info:
            cmd_create(args)
        assert exit_info.value.code == 1

    def test_exits_when_file_does_not_exist(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """Should exit with code 1 when the specified file does not exist."""
        args = self._make_create_args(file_path=str(tmp_path / "nonexistent.md"))
        with pytest.raises(SystemExit) as exit_info:
            cmd_create(args)
        assert exit_info.value.code == 1

    def test_calls_run_create(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """Should call run_create with the correct arguments."""
        from deep_thought.gcal.models import CreateResult

        event_markdown_file = tmp_path / "event.md"
        event_markdown_file.write_text("---\ntool: gcal\n---\n", encoding="utf-8")

        mock_config = MagicMock()
        mock_client = MagicMock()
        mock_connection = MagicMock()
        create_result = CreateResult(event_id="new_evt_456", html_link="https://calendar.google.com/event?eid=new")

        args = self._make_create_args(file_path=str(event_markdown_file))

        mock_run_create = MagicMock(return_value=create_result)

        with (
            patch("deep_thought.gcal.cli._load_config_from_args", return_value=mock_config),
            patch("deep_thought.gcal.cli._make_client_from_config", return_value=mock_client),
            patch("deep_thought.gcal.cli.initialize_database", return_value=mock_connection),
            patch.dict("sys.modules", {"deep_thought.gcal.create": MagicMock(run_create=mock_run_create)}),
        ):
            cmd_create(args)

        mock_run_create.assert_called_once()
        captured_output = capsys.readouterr()
        assert "Event created successfully." in captured_output.out
        assert "new_evt_456" in captured_output.out


# ---------------------------------------------------------------------------
# TestCmdUpdate
# ---------------------------------------------------------------------------


class TestCmdUpdate:
    """Tests for cmd_update."""

    def _make_update_args(self, **kwargs: object) -> argparse.Namespace:
        """Build an argparse.Namespace suitable for cmd_update."""
        defaults: dict[str, object] = {
            "config": None,
            "output": None,
            "calendar": None,
            "days_back": None,
            "days_ahead": None,
            "dry_run": False,
            "file_path": None,
        }
        defaults.update(kwargs)
        return argparse.Namespace(**defaults)

    def test_exits_when_file_path_missing(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Should exit with code 1 when no file_path argument is given."""
        args = self._make_update_args(file_path=None)
        with pytest.raises(SystemExit) as exit_info:
            cmd_update(args)
        assert exit_info.value.code == 1

    def test_exits_when_file_does_not_exist(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """Should exit with code 1 when the specified file does not exist."""
        args = self._make_update_args(file_path=str(tmp_path / "nonexistent.md"))
        with pytest.raises(SystemExit) as exit_info:
            cmd_update(args)
        assert exit_info.value.code == 1

    def test_calls_run_update(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """Should call run_update with the correct arguments."""
        from deep_thought.gcal.models import UpdateResult

        event_markdown_file = tmp_path / "event.md"
        event_markdown_file.write_text("---\ntool: gcal\nevent_id: evt_123\n---\n", encoding="utf-8")

        mock_config = MagicMock()
        mock_client = MagicMock()
        mock_connection = MagicMock()
        update_result = UpdateResult(
            event_id="evt_123",
            html_link="https://calendar.google.com/event?eid=updated",
            fields_changed=["summary", "location"],
        )

        args = self._make_update_args(file_path=str(event_markdown_file))

        mock_run_update = MagicMock(return_value=update_result)

        with (
            patch("deep_thought.gcal.cli._load_config_from_args", return_value=mock_config),
            patch("deep_thought.gcal.cli._make_client_from_config", return_value=mock_client),
            patch("deep_thought.gcal.cli.initialize_database", return_value=mock_connection),
            patch.dict("sys.modules", {"deep_thought.gcal.update": MagicMock(run_update=mock_run_update)}),
        ):
            cmd_update(args)

        mock_run_update.assert_called_once()
        captured_output = capsys.readouterr()
        assert "Event updated successfully." in captured_output.out
        assert "evt_123" in captured_output.out

    def test_shows_no_fields_changed_message(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """Should report no fields changed when fields_changed list is empty."""
        from deep_thought.gcal.models import UpdateResult

        event_markdown_file = tmp_path / "event.md"
        event_markdown_file.write_text("---\ntool: gcal\nevent_id: evt_123\n---\n", encoding="utf-8")

        mock_config = MagicMock()
        mock_client = MagicMock()
        mock_connection = MagicMock()
        update_result = UpdateResult(
            event_id="evt_123",
            html_link="https://calendar.google.com/event?eid=unchanged",
            fields_changed=[],
        )

        args = self._make_update_args(file_path=str(event_markdown_file))

        mock_run_update = MagicMock(return_value=update_result)

        with (
            patch("deep_thought.gcal.cli._load_config_from_args", return_value=mock_config),
            patch("deep_thought.gcal.cli._make_client_from_config", return_value=mock_client),
            patch("deep_thought.gcal.cli.initialize_database", return_value=mock_connection),
            patch.dict("sys.modules", {"deep_thought.gcal.update": MagicMock(run_update=mock_run_update)}),
        ):
            cmd_update(args)

        captured_output = capsys.readouterr()
        assert "No fields changed." in captured_output.out


# ---------------------------------------------------------------------------
# TestCmdDelete
# ---------------------------------------------------------------------------


class TestCmdDelete:
    """Tests for cmd_delete."""

    def _make_delete_args(self, **kwargs: object) -> argparse.Namespace:
        """Build an argparse.Namespace suitable for cmd_delete."""
        defaults: dict[str, object] = {
            "config": None,
            "output": None,
            "calendar": None,
            "days_back": None,
            "days_ahead": None,
            "event_id": "evt_abc123",
            "calendar_id": "primary",
        }
        defaults.update(kwargs)
        return argparse.Namespace(**defaults)

    def test_calls_delete_event_on_client(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Should call client.delete_event with calendar_id and event_id."""
        mock_config = MagicMock()
        mock_config.output_dir = "data/gcal/export/"
        mock_config.flat_output = False
        mock_client = MagicMock()
        mock_connection = MagicMock()

        args = self._make_delete_args(event_id="evt_abc123", calendar_id="primary")

        mock_get_event = MagicMock(return_value=None)
        mock_get_calendar = MagicMock(return_value=None)
        mock_delete_event = MagicMock(return_value=1)

        with (
            patch("deep_thought.gcal.cli._load_config_from_args", return_value=mock_config),
            patch("deep_thought.gcal.cli._make_client_from_config", return_value=mock_client),
            patch("deep_thought.gcal.cli.initialize_database", return_value=mock_connection),
            patch.dict(
                "sys.modules",
                {
                    "deep_thought.gcal.db.queries": MagicMock(
                        get_event=mock_get_event,
                        get_calendar=mock_get_calendar,
                        delete_event=mock_delete_event,
                    ),
                    "deep_thought.gcal.output": MagicMock(delete_event_file=MagicMock()),
                },
            ),
        ):
            cmd_delete(args)

        mock_client.delete_event.assert_called_once_with("primary", "evt_abc123")
        captured_output = capsys.readouterr()
        assert "Event deleted successfully." in captured_output.out
        assert "evt_abc123" in captured_output.out

    def test_with_calendar_id_override(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Should use the provided --calendar-id instead of defaulting to primary."""
        work_calendar_id = "work@group.calendar.google.com"

        mock_config = MagicMock()
        mock_config.output_dir = "data/gcal/export/"
        mock_config.flat_output = False
        mock_client = MagicMock()
        mock_connection = MagicMock()

        args = self._make_delete_args(event_id="evt_work_1", calendar_id=work_calendar_id)

        mock_get_event = MagicMock(return_value=None)
        mock_get_calendar = MagicMock(return_value=None)
        mock_delete_event = MagicMock(return_value=1)

        with (
            patch("deep_thought.gcal.cli._load_config_from_args", return_value=mock_config),
            patch("deep_thought.gcal.cli._make_client_from_config", return_value=mock_client),
            patch("deep_thought.gcal.cli.initialize_database", return_value=mock_connection),
            patch.dict(
                "sys.modules",
                {
                    "deep_thought.gcal.db.queries": MagicMock(
                        get_event=mock_get_event,
                        get_calendar=mock_get_calendar,
                        delete_event=mock_delete_event,
                    ),
                    "deep_thought.gcal.output": MagicMock(delete_event_file=MagicMock()),
                },
            ),
        ):
            cmd_delete(args)

        mock_client.delete_event.assert_called_once_with(work_calendar_id, "evt_work_1")
        captured_output = capsys.readouterr()
        assert work_calendar_id in captured_output.out
