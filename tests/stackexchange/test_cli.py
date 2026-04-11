"""Tests for the Stack Exchange Tool CLI (deep_thought.stackexchange.cli).

Uses argparse directly and mocks at the module boundary so no real database
writes or API calls occur.
"""

from __future__ import annotations

import argparse
from pathlib import Path  # noqa: TC003
from unittest.mock import MagicMock, patch

import pytest

from deep_thought.stackexchange.cli import (
    _build_argument_parser,
    cmd_collect,
    cmd_config,
    cmd_init,
    main,
)
from deep_thought.stackexchange.config import RuleConfig, StackExchangeConfig, TagConfig

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def minimal_config() -> StackExchangeConfig:
    """Return a minimal valid StackExchangeConfig for use in handler tests."""
    return StackExchangeConfig(
        api_key_env="STACKEXCHANGE_API_KEY",
        max_questions_per_run=100,
        output_dir="data/stackexchange/export/",
        generate_llms_files=False,
        qdrant_collection="deep_thought_db",
        rules=[
            RuleConfig(
                name="test_rule",
                site="stackoverflow",
                tags=TagConfig(include=["python"], any=[]),
                sort="votes",
                order="desc",
                min_score=10,
                min_answers=1,
                only_answered=True,
                max_age_days=365,
                keywords=[],
                max_questions=50,
                max_answers_per_question=5,
                include_comments=False,
                max_comments_per_question=30,
            )
        ],
    )


@pytest.fixture()
def args_base() -> argparse.Namespace:
    """Return a Namespace with all global flags at their defaults."""
    return argparse.Namespace(
        dry_run=False,
        verbose=False,
        config=None,
        rule=None,
        output=None,
        force=False,
        save_config=None,
        subcommand=None,
    )


# ---------------------------------------------------------------------------
# TestArgumentParser
# ---------------------------------------------------------------------------


class TestArgumentParser:
    def test_version_flag_exits(self) -> None:
        """--version should print version and exit with code 0."""
        parser = _build_argument_parser()
        with pytest.raises(SystemExit) as exc_info:
            parser.parse_args(["--version"])
        assert exc_info.value.code == 0

    def test_dry_run_flag_parsed(self) -> None:
        """--dry-run should set dry_run=True in the parsed namespace."""
        parser = _build_argument_parser()
        args = parser.parse_args(["--dry-run"])
        assert args.dry_run is True

    def test_rule_flag_parsed(self) -> None:
        """--rule NAME should set rule='NAME' in the parsed namespace."""
        parser = _build_argument_parser()
        args = parser.parse_args(["--rule", "my_rule"])
        assert args.rule == "my_rule"

    def test_force_flag_parsed(self) -> None:
        """--force should set force=True in the parsed namespace."""
        parser = _build_argument_parser()
        args = parser.parse_args(["--force"])
        assert args.force is True

    def test_verbose_flag_parsed(self) -> None:
        """--verbose should set verbose=True in the parsed namespace."""
        parser = _build_argument_parser()
        args = parser.parse_args(["--verbose"])
        assert args.verbose is True

    def test_init_subcommand_exists(self) -> None:
        """The 'init' subcommand should be recognized."""
        parser = _build_argument_parser()
        args = parser.parse_args(["init"])
        assert args.subcommand == "init"

    def test_config_subcommand_exists(self) -> None:
        """The 'config' subcommand should be recognized."""
        parser = _build_argument_parser()
        args = parser.parse_args(["config"])
        assert args.subcommand == "config"

    def test_no_subcommand_defaults_to_none(self) -> None:
        """When no subcommand is given, subcommand should be None."""
        parser = _build_argument_parser()
        args = parser.parse_args([])
        assert args.subcommand is None


# ---------------------------------------------------------------------------
# TestCmdInit
# ---------------------------------------------------------------------------


class TestCmdInit:
    def test_copies_config_and_creates_dirs(self, tmp_path: Path, args_base: argparse.Namespace) -> None:
        """cmd_init should copy the bundled config and create required directories."""
        bundled_config = tmp_path / "default-config.yaml"
        bundled_config.write_text("api_key_env: STACKEXCHANGE_API_KEY\n", encoding="utf-8")

        project_config = tmp_path / "src" / "config" / "stackexchange-configuration.yaml"
        db_path = tmp_path / "stackexchange.db"
        mock_conn = MagicMock()

        with (
            patch("deep_thought.stackexchange.cli.get_bundled_config_path", return_value=bundled_config),
            patch("deep_thought.stackexchange.cli.get_default_config_path", return_value=project_config),
            patch("deep_thought.stackexchange.cli.get_database_path", return_value=db_path),
            patch("deep_thought.stackexchange.cli.initialize_database", return_value=mock_conn),
        ):
            cmd_init(args_base)

        assert project_config.exists()
        mock_conn.close.assert_called_once()

    def test_skips_config_if_already_exists(
        self, tmp_path: Path, args_base: argparse.Namespace, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """cmd_init should not overwrite an existing config file."""
        bundled_config = tmp_path / "default-config.yaml"
        bundled_config.write_text("original content\n", encoding="utf-8")

        project_config = tmp_path / "src" / "config" / "stackexchange-configuration.yaml"
        project_config.parent.mkdir(parents=True, exist_ok=True)
        project_config.write_text("existing content\n", encoding="utf-8")

        db_path = tmp_path / "stackexchange.db"
        mock_conn = MagicMock()

        with (
            patch("deep_thought.stackexchange.cli.get_bundled_config_path", return_value=bundled_config),
            patch("deep_thought.stackexchange.cli.get_default_config_path", return_value=project_config),
            patch("deep_thought.stackexchange.cli.get_database_path", return_value=db_path),
            patch("deep_thought.stackexchange.cli.initialize_database", return_value=mock_conn),
        ):
            cmd_init(args_base)

        # Config file should not have been overwritten
        assert project_config.read_text(encoding="utf-8") == "existing content\n"


# ---------------------------------------------------------------------------
# TestCmdConfig
# ---------------------------------------------------------------------------


class TestCmdConfig:
    def test_prints_config_fields(
        self,
        minimal_config: StackExchangeConfig,
        args_base: argparse.Namespace,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """cmd_config should print key configuration fields to stdout."""
        with (
            patch("deep_thought.stackexchange.cli.load_config", return_value=minimal_config),
            patch("deep_thought.stackexchange.cli.validate_config", return_value=[]),
        ):
            cmd_config(args_base)

        captured_output = capsys.readouterr()
        assert "STACKEXCHANGE_API_KEY" in captured_output.out
        assert "100" in captured_output.out
        assert "test_rule" in captured_output.out

    def test_prints_validation_issues_when_present(
        self,
        minimal_config: StackExchangeConfig,
        args_base: argparse.Namespace,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """cmd_config should print validation issues when the config has problems."""
        validation_issues = ["Rule 'bad_rule': something is wrong."]
        with (
            patch("deep_thought.stackexchange.cli.load_config", return_value=minimal_config),
            patch("deep_thought.stackexchange.cli.validate_config", return_value=validation_issues),
        ):
            cmd_config(args_base)

        captured_output = capsys.readouterr()
        assert "WARNING" in captured_output.out
        assert "something is wrong" in captured_output.out

    def test_prints_valid_message_when_no_issues(
        self,
        minimal_config: StackExchangeConfig,
        args_base: argparse.Namespace,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """cmd_config should confirm validity when no issues are found."""
        with (
            patch("deep_thought.stackexchange.cli.load_config", return_value=minimal_config),
            patch("deep_thought.stackexchange.cli.validate_config", return_value=[]),
        ):
            cmd_config(args_base)

        captured_output = capsys.readouterr()
        assert "valid" in captured_output.out.lower()


# ---------------------------------------------------------------------------
# TestCmdCollect
# ---------------------------------------------------------------------------


class TestCmdCollect:
    def test_happy_path_runs_collection(
        self,
        minimal_config: StackExchangeConfig,
        args_base: argparse.Namespace,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """cmd_collect should invoke run_collection and print a summary."""
        from deep_thought.stackexchange.processor import CollectionResult

        mock_collection_result = CollectionResult()
        mock_collection_result.questions_collected = 3
        mock_db_conn = MagicMock()

        with (
            patch("deep_thought.stackexchange.cli.load_config", return_value=minimal_config),
            patch("deep_thought.stackexchange.cli.validate_config", return_value=[]),
            patch("deep_thought.stackexchange.cli._make_client_from_config", return_value=MagicMock()),
            patch("deep_thought.stackexchange.cli.initialize_database", return_value=mock_db_conn),
            patch("deep_thought.stackexchange.cli.run_collection", return_value=mock_collection_result),
        ):
            cmd_collect(args_base)

        captured_output = capsys.readouterr()
        assert "Collected" in captured_output.out
        assert "3" in captured_output.out

    @pytest.mark.error_handling
    def test_validation_failure_exits_with_code_1(
        self,
        minimal_config: StackExchangeConfig,
        args_base: argparse.Namespace,
    ) -> None:
        """cmd_collect should exit with code 1 when validation fails."""
        validation_issues = ["Some configuration error."]
        with (
            patch("deep_thought.stackexchange.cli.load_config", return_value=minimal_config),
            patch("deep_thought.stackexchange.cli.validate_config", return_value=validation_issues),
            pytest.raises(SystemExit) as exc_info,
        ):
            cmd_collect(args_base)

        assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# TestMain
# ---------------------------------------------------------------------------


class TestMain:
    def test_dispatches_to_cmd_collect_when_no_subcommand(self) -> None:
        """main() with no subcommand should dispatch to cmd_collect via _run_command."""
        with (
            patch("sys.argv", ["stackexchange"]),
            patch("deep_thought.stackexchange.cli._run_command") as mock_run,
            patch("deep_thought.stackexchange.cli.load_dotenv"),
        ):
            main()
            mock_run.assert_called_once()
            handler_arg = mock_run.call_args[0][0]
            assert handler_arg is cmd_collect

    def test_dispatches_to_cmd_init_for_init_subcommand(self) -> None:
        """main() with 'init' subcommand should dispatch to cmd_init via _run_command."""
        with (
            patch("sys.argv", ["stackexchange", "init"]),
            patch("deep_thought.stackexchange.cli._run_command") as mock_run,
            patch("deep_thought.stackexchange.cli.load_dotenv"),
        ):
            main()
            mock_run.assert_called_once()
            handler_arg = mock_run.call_args[0][0]
            assert handler_arg is cmd_init

    def test_dispatches_to_cmd_config_for_config_subcommand(self) -> None:
        """main() with 'config' subcommand should dispatch to cmd_config via _run_command."""
        with (
            patch("sys.argv", ["stackexchange", "config"]),
            patch("deep_thought.stackexchange.cli._run_command") as mock_run,
            patch("deep_thought.stackexchange.cli.load_dotenv"),
        ):
            main()
            mock_run.assert_called_once()
            handler_arg = mock_run.call_args[0][0]
            assert handler_arg is cmd_config
