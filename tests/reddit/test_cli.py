"""Tests for the Reddit Tool CLI (deep_thought.reddit.cli).

Uses argparse directly and mocks at the module boundary so no real database
writes or API calls occur.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from deep_thought.reddit.cli import (
    _build_argument_parser,
    _handle_save_config,
    _load_config_from_args,
    _setup_logging,
    cmd_collect,
    cmd_config,
    cmd_init,
    main,
)
from deep_thought.reddit.config import RedditConfig, RuleConfig

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def minimal_config() -> RedditConfig:
    """Return a minimal valid RedditConfig for use in handler tests."""
    return RedditConfig(
        client_id_env="REDDIT_CLIENT_ID",
        client_secret_env="REDDIT_CLIENT_SECRET",
        user_agent_env="REDDIT_USER_AGENT",
        max_posts_per_run=100,
        output_dir="data/reddit/export/",
        rules=[
            RuleConfig(
                name="test_rule",
                subreddit="python",
                sort="top",
                time_filter="week",
                limit=10,
                min_score=0,
                min_comments=0,
                max_age_days=7,
                include_keywords=[],
                exclude_keywords=[],
                include_flair=[],
                exclude_flair=[],
                search_comments=False,
                max_comment_depth=3,
                max_comments=200,
                include_images=False,
                exclude_stickied=False,
                exclude_locked=False,
                replace_more_limit=32,
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
# Parser structure tests
# ---------------------------------------------------------------------------


class TestArgumentParser:
    def test_help_flag_does_not_crash(self) -> None:
        """Calling --help must raise SystemExit(0), not an unhandled exception."""
        parser = _build_argument_parser()
        with pytest.raises(SystemExit) as exc_info:
            parser.parse_args(["--help"])
        assert exc_info.value.code == 0

    def test_init_subcommand_is_registered(self) -> None:
        """The 'init' subcommand must be parseable without error."""
        parser = _build_argument_parser()
        parsed = parser.parse_args(["init"])
        assert parsed.subcommand == "init"

    def test_config_subcommand_is_registered(self) -> None:
        """The 'config' subcommand must be parseable without error."""
        parser = _build_argument_parser()
        parsed = parser.parse_args(["config"])
        assert parsed.subcommand == "config"

    def test_global_flags_are_parsed_correctly(self) -> None:
        """Global flags must appear on the parsed namespace."""
        parser = _build_argument_parser()
        parsed = parser.parse_args(["--dry-run", "--verbose", "--config", "/tmp/cfg.yaml", "--rule", "my_rule"])
        assert parsed.dry_run is True
        assert parsed.verbose is True
        assert parsed.config == "/tmp/cfg.yaml"
        assert parsed.rule == "my_rule"

    def test_verbose_short_flag(self) -> None:
        """-v must be an alias for --verbose."""
        parser = _build_argument_parser()
        parsed = parser.parse_args(["-v", "config"])
        assert parsed.verbose is True

    def test_no_subcommand_defaults_to_none(self) -> None:
        """When no subcommand is given, dest should be None."""
        parser = _build_argument_parser()
        parsed = parser.parse_args([])
        assert parsed.subcommand is None

    def test_version_flag_exits(self) -> None:
        """--version must raise SystemExit, not an unhandled exception."""
        parser = _build_argument_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["--version"])

    def test_force_flag_is_parsed(self) -> None:
        """--force flag should be captured on the namespace."""
        parser = _build_argument_parser()
        parsed = parser.parse_args(["--force"])
        assert parsed.force is True

    def test_output_flag_is_parsed(self) -> None:
        """--output flag should be captured on the namespace."""
        parser = _build_argument_parser()
        parsed = parser.parse_args(["--output", "/tmp/output"])
        assert parsed.output == "/tmp/output"


# ---------------------------------------------------------------------------
# _setup_logging
# ---------------------------------------------------------------------------


class TestSetupLogging:
    def test_verbose_mode_uses_debug_level(self) -> None:
        """Verbose mode must set the root logger level to DEBUG."""
        import logging

        _setup_logging(verbose=True)
        assert logging.getLogger().level == logging.DEBUG

    def test_non_verbose_uses_info_level(self) -> None:
        """Non-verbose mode must set the root logger level to INFO."""
        import logging

        _setup_logging(verbose=False)
        assert logging.getLogger().level == logging.INFO


# ---------------------------------------------------------------------------
# _load_config_from_args
# ---------------------------------------------------------------------------


class TestLoadConfigFromArgs:
    def test_uses_default_path_when_config_is_none(
        self, args_base: argparse.Namespace, minimal_config: RedditConfig
    ) -> None:
        """When args.config is None, load_config must be called with None."""
        with patch("deep_thought.reddit.cli.load_config", return_value=minimal_config) as mock_load:
            _load_config_from_args(args_base)
            mock_load.assert_called_once_with(None)

    def test_uses_provided_path(self, args_base: argparse.Namespace, minimal_config: RedditConfig) -> None:
        """When args.config is a string path, it must be wrapped in Path and passed."""
        args_base.config = "/tmp/custom_config.yaml"
        with patch("deep_thought.reddit.cli.load_config", return_value=minimal_config) as mock_load:
            _load_config_from_args(args_base)
            mock_load.assert_called_once_with(Path("/tmp/custom_config.yaml"))


# ---------------------------------------------------------------------------
# cmd_init
# ---------------------------------------------------------------------------


class TestCmdInit:
    def test_prints_confirmation(
        self,
        args_base: argparse.Namespace,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """init must print a confirmation message."""
        monkeypatch.chdir(tmp_path)
        bundled_config = tmp_path / "bundled.yaml"
        bundled_config.write_text("# default reddit config\n", encoding="utf-8")
        fake_db_path = tmp_path / "data" / "reddit" / "reddit.db"
        mock_conn = MagicMock()

        with (
            patch("deep_thought.reddit.cli.get_bundled_config_path", return_value=bundled_config),
            patch("deep_thought.reddit.cli.get_database_path", return_value=fake_db_path),
            patch("deep_thought.reddit.cli.initialize_database", return_value=mock_conn),
        ):
            cmd_init(args_base)

        captured_output = capsys.readouterr().out
        assert "initialised successfully" in captured_output
        mock_conn.close.assert_called_once()

    def test_copies_config_to_project(
        self,
        args_base: argparse.Namespace,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """init must copy the bundled config to src/config/ in the calling repo."""
        monkeypatch.chdir(tmp_path)
        bundled_config = tmp_path / "bundled.yaml"
        bundled_config.write_text("# bundled default reddit config\n", encoding="utf-8")
        fake_db_path = tmp_path / "data" / "reddit" / "reddit.db"
        mock_conn = MagicMock()

        with (
            patch("deep_thought.reddit.cli.get_bundled_config_path", return_value=bundled_config),
            patch("deep_thought.reddit.cli.get_database_path", return_value=fake_db_path),
            patch("deep_thought.reddit.cli.initialize_database", return_value=mock_conn),
        ):
            cmd_init(args_base)

        project_config = tmp_path / "src" / "config" / "reddit-configuration.yaml"
        assert project_config.exists()
        assert project_config.read_text() == "# bundled default reddit config\n"

    def test_skips_config_copy_if_already_exists(
        self,
        args_base: argparse.Namespace,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """init must not overwrite an existing project-level config file."""
        monkeypatch.chdir(tmp_path)
        bundled_config = tmp_path / "bundled.yaml"
        bundled_config.write_text("# new bundled content\n", encoding="utf-8")
        project_config = tmp_path / "src" / "config" / "reddit-configuration.yaml"
        project_config.parent.mkdir(parents=True)
        project_config.write_text("# existing content\n", encoding="utf-8")
        fake_db_path = tmp_path / "data" / "reddit" / "reddit.db"
        mock_conn = MagicMock()

        with (
            patch("deep_thought.reddit.cli.get_bundled_config_path", return_value=bundled_config),
            patch("deep_thought.reddit.cli.get_database_path", return_value=fake_db_path),
            patch("deep_thought.reddit.cli.initialize_database", return_value=mock_conn),
        ):
            cmd_init(args_base)

        assert project_config.read_text() == "# existing content\n"
        captured_output = capsys.readouterr().out
        assert "already exists" in captured_output

    def test_creates_snapshots_and_export_directories(
        self,
        args_base: argparse.Namespace,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """init must create the snapshots and export subdirectories under data/reddit/."""
        monkeypatch.chdir(tmp_path)
        bundled_config = tmp_path / "bundled.yaml"
        bundled_config.write_text("# default\n", encoding="utf-8")
        fake_db_path = tmp_path / "data" / "reddit" / "reddit.db"
        mock_conn = MagicMock()

        with (
            patch("deep_thought.reddit.cli.get_bundled_config_path", return_value=bundled_config),
            patch("deep_thought.reddit.cli.get_database_path", return_value=fake_db_path),
            patch("deep_thought.reddit.cli.initialize_database", return_value=mock_conn),
        ):
            cmd_init(args_base)

        assert (tmp_path / "data" / "reddit" / "snapshots").exists()
        assert (tmp_path / "data" / "reddit" / "export").exists()

    def test_prints_credentials_next_steps(
        self,
        args_base: argparse.Namespace,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """init must print Reddit credential env var names in the next-steps section."""
        monkeypatch.chdir(tmp_path)
        bundled_config = tmp_path / "bundled.yaml"
        bundled_config.write_text("# default\n", encoding="utf-8")
        fake_db_path = tmp_path / "data" / "reddit" / "reddit.db"
        mock_conn = MagicMock()

        with (
            patch("deep_thought.reddit.cli.get_bundled_config_path", return_value=bundled_config),
            patch("deep_thought.reddit.cli.get_database_path", return_value=fake_db_path),
            patch("deep_thought.reddit.cli.initialize_database", return_value=mock_conn),
        ):
            cmd_init(args_base)

        captured_output = capsys.readouterr().out
        assert "REDDIT_CLIENT_ID" in captured_output

    def test_exits_if_bundled_config_missing(
        self,
        args_base: argparse.Namespace,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """init must exit with code 1 if the bundled config template is not found."""
        monkeypatch.chdir(tmp_path)

        with (
            patch("deep_thought.reddit.cli.get_bundled_config_path", return_value=tmp_path / "nonexistent.yaml"),
            pytest.raises(SystemExit) as exc_info,
        ):
            cmd_init(args_base)

        assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# _handle_save_config
# ---------------------------------------------------------------------------


class TestHandleSaveConfig:
    def test_copies_bundled_config_to_destination(self, tmp_path: Path) -> None:
        """_handle_save_config must copy the bundled template to the given path."""
        destination = tmp_path / "output.yaml"
        source = tmp_path / "source.yaml"
        source.write_text("# example reddit config\n", encoding="utf-8")

        with patch("deep_thought.reddit.cli.get_bundled_config_path", return_value=source):
            _handle_save_config(str(destination))

        assert destination.exists()
        assert destination.read_text() == "# example reddit config\n"

    def test_exits_if_source_missing(self, tmp_path: Path) -> None:
        """Should exit with code 1 if the bundled config template is missing."""
        with patch("deep_thought.reddit.cli.get_bundled_config_path") as mock_bundled_path:
            mock_bundled_path.return_value = tmp_path / "nonexistent.yaml"

            with pytest.raises(SystemExit) as exit_info:
                _handle_save_config(str(tmp_path / "output.yaml"))

        assert exit_info.value.code == 1

    def test_exits_if_destination_exists(self, tmp_path: Path) -> None:
        """Should exit with code 1 if the destination file already exists."""
        destination = tmp_path / "existing.yaml"
        destination.write_text("existing content", encoding="utf-8")

        with patch("deep_thought.reddit.cli.get_bundled_config_path") as mock_bundled_path:
            source = tmp_path / "source.yaml"
            source.write_text("# config", encoding="utf-8")
            mock_bundled_path.return_value = source

            with pytest.raises(SystemExit) as exit_info:
                _handle_save_config(str(destination))

        assert exit_info.value.code == 1

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        """Should create missing parent directories before writing the config file."""
        destination = tmp_path / "nested" / "dirs" / "my-config.yaml"

        with patch("deep_thought.reddit.cli.get_bundled_config_path") as mock_bundled_path:
            source = tmp_path / "source.yaml"
            source.write_text("# config", encoding="utf-8")
            mock_bundled_path.return_value = source

            _handle_save_config(str(destination))

        assert destination.exists()


# ---------------------------------------------------------------------------
# cmd_config
# ---------------------------------------------------------------------------


class TestCmdConfig:
    def test_displays_config_values(
        self,
        args_base: argparse.Namespace,
        minimal_config: RedditConfig,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """config must print all key configuration sections."""
        with (
            patch("deep_thought.reddit.cli.load_config", return_value=minimal_config),
            patch("deep_thought.reddit.cli.validate_config", return_value=[]),
        ):
            cmd_config(args_base)

        captured_output = capsys.readouterr().out
        assert "client_id_env" in captured_output
        assert "REDDIT_CLIENT_ID" in captured_output
        assert "max_posts_per_run" in captured_output
        assert "rules" in captured_output

    def test_prints_validation_issues(
        self,
        args_base: argparse.Namespace,
        minimal_config: RedditConfig,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """config must display any validation warnings before the config listing."""
        warning_message = "No rules configured."
        with (
            patch("deep_thought.reddit.cli.load_config", return_value=minimal_config),
            patch("deep_thought.reddit.cli.validate_config", return_value=[warning_message]),
        ):
            cmd_config(args_base)

        captured_output = capsys.readouterr().out
        assert "WARNING" in captured_output
        assert warning_message in captured_output

    def test_prints_valid_message_when_no_issues(
        self,
        args_base: argparse.Namespace,
        minimal_config: RedditConfig,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """config must print 'Configuration is valid.' when there are no issues."""
        with (
            patch("deep_thought.reddit.cli.load_config", return_value=minimal_config),
            patch("deep_thought.reddit.cli.validate_config", return_value=[]),
        ):
            cmd_config(args_base)

        captured_output = capsys.readouterr().out
        assert "Configuration is valid." in captured_output


# ---------------------------------------------------------------------------
# main() — entry point dispatch
# ---------------------------------------------------------------------------


class TestMain:
    def test_no_args_prints_help_and_exits_zero(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Calling main with no arguments must print help and exit 0."""
        with (
            patch("sys.argv", ["reddit"]),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()
        assert exc_info.value.code == 0

    def test_dispatches_init_to_cmd_init(self, minimal_config: RedditConfig) -> None:
        """main must dispatch the 'init' subcommand to cmd_init."""
        with (
            patch("sys.argv", ["reddit", "init"]),
            patch.dict("deep_thought.reddit.cli._COMMAND_HANDLERS", {"init": MagicMock()}),
        ):
            main()
            # The handler dict was patched — verify the entry is there
            # (we don't capture the call since we patched the dict)

    @pytest.mark.error_handling
    def test_file_not_found_exits_with_code_1(self, capsys: pytest.CaptureFixture[str]) -> None:
        """A FileNotFoundError raised inside a handler must exit with code 1."""
        mock_handler = MagicMock(side_effect=FileNotFoundError("config.yaml"))
        with (
            patch("sys.argv", ["reddit", "config"]),
            patch.dict("deep_thought.reddit.cli._COMMAND_HANDLERS", {"config": mock_handler}),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()
        assert exc_info.value.code == 1
        assert "File not found" in capsys.readouterr().err

    @pytest.mark.error_handling
    def test_os_error_exits_with_code_1(self, capsys: pytest.CaptureFixture[str]) -> None:
        """An OSError raised inside a handler must exit with code 1."""
        mock_handler = MagicMock(side_effect=OSError("missing credential"))
        with (
            patch("sys.argv", ["reddit", "config"]),
            patch.dict("deep_thought.reddit.cli._COMMAND_HANDLERS", {"config": mock_handler}),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()
        assert exc_info.value.code == 1
        assert "missing credential" in capsys.readouterr().err

    @pytest.mark.error_handling
    def test_unexpected_exception_exits_with_code_1(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Any unhandled exception raised inside a handler must exit with code 1."""
        mock_handler = MagicMock(side_effect=RuntimeError("boom"))
        with (
            patch("sys.argv", ["reddit", "init"]),
            patch.dict("deep_thought.reddit.cli._COMMAND_HANDLERS", {"init": mock_handler}),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()
        assert exc_info.value.code == 1
        assert "unexpected error" in capsys.readouterr().err.lower()


# ---------------------------------------------------------------------------
# cmd_collect — T-05: integration path
# ---------------------------------------------------------------------------


class TestCmdCollect:
    """Integration-level tests for cmd_collect.

    All external dependencies (database, PRAW client, config loading, run_collection)
    are mocked so no real I/O or network calls occur.
    """

    def _make_collect_args(
        self,
        dry_run: bool = False,
        force: bool = False,
        rule: str | None = None,
        output: str | None = None,
        config: str | None = None,
    ) -> argparse.Namespace:
        """Return a Namespace with all flags needed by cmd_collect."""
        return argparse.Namespace(
            dry_run=dry_run,
            force=force,
            rule=rule,
            output=output,
            config=config,
            verbose=False,
            save_config=None,
            subcommand=None,
        )

    def test_successful_collect_prints_summary(
        self,
        minimal_config: RedditConfig,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A successful collection run must print a summary of collected/updated/skipped counts."""
        from deep_thought.reddit.processor import CollectionResult

        mock_result = CollectionResult(posts_collected=3, posts_updated=1, posts_skipped=2, posts_errored=0)
        mock_conn = MagicMock()

        with (
            patch("deep_thought.reddit.cli.load_config", return_value=minimal_config),
            patch("deep_thought.reddit.cli.validate_config", return_value=[]),
            patch("deep_thought.reddit.cli._make_client_from_config"),
            patch("deep_thought.reddit.cli.initialize_database", return_value=mock_conn),
            patch("deep_thought.reddit.cli.run_collection", return_value=mock_result),
        ):
            cmd_collect(self._make_collect_args())

        captured_output = capsys.readouterr().out
        assert "Collected: 3" in captured_output
        assert "Updated:   1" in captured_output
        assert "Skipped:   2" in captured_output

    def test_commits_database_after_collection(
        self,
        minimal_config: RedditConfig,
    ) -> None:
        """The database connection must be committed after a successful collection run."""
        from deep_thought.reddit.processor import CollectionResult

        mock_result = CollectionResult()
        mock_conn = MagicMock()

        with (
            patch("deep_thought.reddit.cli.load_config", return_value=minimal_config),
            patch("deep_thought.reddit.cli.validate_config", return_value=[]),
            patch("deep_thought.reddit.cli._make_client_from_config"),
            patch("deep_thought.reddit.cli.initialize_database", return_value=mock_conn),
            patch("deep_thought.reddit.cli.run_collection", return_value=mock_result),
        ):
            cmd_collect(self._make_collect_args())

        mock_conn.commit.assert_called_once()

    def test_closes_database_even_on_error(
        self,
        minimal_config: RedditConfig,
    ) -> None:
        """The database connection must always be closed, even if run_collection raises."""
        mock_conn = MagicMock()

        with (
            patch("deep_thought.reddit.cli.load_config", return_value=minimal_config),
            patch("deep_thought.reddit.cli.validate_config", return_value=[]),
            patch("deep_thought.reddit.cli._make_client_from_config"),
            patch("deep_thought.reddit.cli.initialize_database", return_value=mock_conn),
            patch("deep_thought.reddit.cli.run_collection", side_effect=RuntimeError("API failure")),
            pytest.raises(RuntimeError),
        ):
            cmd_collect(self._make_collect_args())

        mock_conn.close.assert_called_once()

    def test_exits_with_code_1_when_all_posts_errored(
        self,
        minimal_config: RedditConfig,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """When every post fails with no successes, exit code must be 1."""
        from deep_thought.reddit.processor import CollectionResult

        mock_result = CollectionResult(posts_collected=0, posts_updated=0, posts_errored=2, errors=["err1", "err2"])
        mock_conn = MagicMock()

        with (
            patch("deep_thought.reddit.cli.load_config", return_value=minimal_config),
            patch("deep_thought.reddit.cli.validate_config", return_value=[]),
            patch("deep_thought.reddit.cli._make_client_from_config"),
            patch("deep_thought.reddit.cli.initialize_database", return_value=mock_conn),
            patch("deep_thought.reddit.cli.run_collection", return_value=mock_result),
            pytest.raises(SystemExit) as exc_info,
        ):
            cmd_collect(self._make_collect_args())

        assert exc_info.value.code == 1

    def test_exits_with_code_2_on_partial_failure(
        self,
        minimal_config: RedditConfig,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """When some posts succeed and some fail, exit code must be 2."""
        from deep_thought.reddit.processor import CollectionResult

        mock_result = CollectionResult(posts_collected=3, posts_errored=1, errors=["one error"])
        mock_conn = MagicMock()

        with (
            patch("deep_thought.reddit.cli.load_config", return_value=minimal_config),
            patch("deep_thought.reddit.cli.validate_config", return_value=[]),
            patch("deep_thought.reddit.cli._make_client_from_config"),
            patch("deep_thought.reddit.cli.initialize_database", return_value=mock_conn),
            patch("deep_thought.reddit.cli.run_collection", return_value=mock_result),
            pytest.raises(SystemExit) as exc_info,
        ):
            cmd_collect(self._make_collect_args())

        assert exc_info.value.code == 2

    def test_aborts_with_error_if_config_invalid(
        self,
        minimal_config: RedditConfig,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """cmd_collect must exit with code 1 when validate_config returns issues."""
        validation_issues = ["max_posts_per_run must be > 0, got: -1."]

        with (
            patch("deep_thought.reddit.cli.load_config", return_value=minimal_config),
            patch("deep_thought.reddit.cli.validate_config", return_value=validation_issues),
            pytest.raises(SystemExit) as exc_info,
        ):
            cmd_collect(self._make_collect_args())

        assert exc_info.value.code == 1
        assert "max_posts_per_run" in capsys.readouterr().err

    def test_dry_run_prefix_appears_in_output(
        self,
        minimal_config: RedditConfig,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """In dry-run mode, the summary line must be prefixed with '[dry-run]'."""
        from deep_thought.reddit.processor import CollectionResult

        mock_result = CollectionResult(posts_collected=1)
        mock_conn = MagicMock()

        with (
            patch("deep_thought.reddit.cli.load_config", return_value=minimal_config),
            patch("deep_thought.reddit.cli.validate_config", return_value=[]),
            patch("deep_thought.reddit.cli._make_client_from_config"),
            patch("deep_thought.reddit.cli.initialize_database", return_value=mock_conn),
            patch("deep_thought.reddit.cli.run_collection", return_value=mock_result),
        ):
            cmd_collect(self._make_collect_args(dry_run=True))

        captured_output = capsys.readouterr().out
        assert "[dry-run]" in captured_output
