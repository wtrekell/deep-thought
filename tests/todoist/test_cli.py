"""Tests for the Todoist Tool CLI (deep_thought.todoist.cli).

Uses argparse directly and mocks at the module boundary so no real database
writes or API calls occur. Integration-style tests for init and status use
a real in-memory database to verify the full call path.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from deep_thought.todoist.cli import (
    _build_argument_parser,
    _load_config_from_args,
    _setup_logging,
    cmd_complete,
    cmd_config,
    cmd_create,
    cmd_diff,
    cmd_export,
    cmd_init,
    cmd_pull,
    cmd_push,
    cmd_status,
    cmd_sync,
    main,
)
from deep_thought.todoist.config import (
    ClaudeConfig,
    CommentConfig,
    FilterConfig,
    PullFilters,
    PushFilters,
    TodoistConfig,
)
from deep_thought.todoist.create import CreateResult
from deep_thought.todoist.export import ExportResult
from deep_thought.todoist.pull import PullResult
from deep_thought.todoist.push import PushResult
from deep_thought.todoist.sync import SyncResult

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def minimal_config() -> TodoistConfig:
    """Return a minimal valid TodoistConfig for use in handler tests."""
    return TodoistConfig(
        api_token_env="TODOIST_API_TOKEN",
        projects=["Work"],
        pull_filters=PullFilters(
            labels=FilterConfig(include=[], exclude=[]),
            projects=FilterConfig(include=[], exclude=[]),
            sections=FilterConfig(include=[], exclude=[]),
            assignee=FilterConfig(include=[], exclude=[]),
            has_due_date=None,
        ),
        push_filters=PushFilters(
            labels=FilterConfig(include=[], exclude=[]),
            assignee=FilterConfig(include=[], exclude=[]),
            conflict_resolution="prompt",
            require_confirmation=False,
        ),
        comments=CommentConfig(sync=True, include_attachments=False),
        claude=ClaudeConfig(label="claude-code", repo="deep-thought", branch="main"),
    )


@pytest.fixture()
def args_base() -> argparse.Namespace:
    """Return a Namespace with all global flags at their defaults."""
    return argparse.Namespace(
        dry_run=False,
        verbose=False,
        config=None,
        project=None,
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

    def test_all_subcommands_are_registered(self) -> None:
        """Every expected subcommand must be parseable without error."""
        expected_subcommands = [
            "init",
            "config",
            "pull",
            "push",
            "sync",
            "status",
            "diff",
            "export",
        ]
        parser = _build_argument_parser()
        for subcommand_name in expected_subcommands:
            parsed = parser.parse_args([subcommand_name])
            assert parsed.subcommand == subcommand_name

    def test_create_and_complete_subcommands_are_registered(self) -> None:
        """create and complete must be parseable with their required positional arguments."""
        parser = _build_argument_parser()

        parsed_create = parser.parse_args(["create", "Write unit tests"])
        assert parsed_create.subcommand == "create"
        assert parsed_create.content == "Write unit tests"

        parsed_complete = parser.parse_args(["complete", "task-99"])
        assert parsed_complete.subcommand == "complete"
        assert parsed_complete.task_id == "task-99"

    def test_global_flags_are_parsed_correctly(self) -> None:
        """Global flags must appear on the parsed namespace for any subcommand."""
        parser = _build_argument_parser()
        parsed = parser.parse_args(["--dry-run", "--verbose", "--config", "/tmp/cfg.yaml", "--project", "Work", "pull"])
        assert parsed.dry_run is True
        assert parsed.verbose is True
        assert parsed.config == "/tmp/cfg.yaml"
        assert parsed.project == "Work"

    def test_verbose_short_flag(self) -> None:
        """-v must be an alias for --verbose."""
        parser = _build_argument_parser()
        parsed = parser.parse_args(["-v", "status"])
        assert parsed.verbose is True

    def test_no_subcommand_defaults_to_none(self) -> None:
        """When no subcommand is given, dest should be None (main prints help)."""
        parser = _build_argument_parser()
        parsed = parser.parse_args([])
        assert parsed.subcommand is None


# ---------------------------------------------------------------------------
# _setup_logging
# ---------------------------------------------------------------------------


class TestSetupLogging:
    def test_verbose_mode_uses_debug_level(self) -> None:
        """Verbose mode must set the root logger level to DEBUG."""
        import logging

        _setup_logging(verbose=True)
        # setLevel is called directly on the root logger, so this is reliable
        # even when pytest has already installed a handler via basicConfig.
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
        self, args_base: argparse.Namespace, minimal_config: TodoistConfig
    ) -> None:
        """When args.config is None, load_config must be called with no path argument."""
        with patch("deep_thought.todoist.cli.load_config", return_value=minimal_config) as mock_load:
            _load_config_from_args(args_base)
            mock_load.assert_called_once_with(None)

    def test_uses_provided_path(self, args_base: argparse.Namespace, minimal_config: TodoistConfig) -> None:
        """When args.config is a string path, it must be wrapped in Path and passed."""
        args_base.config = "/tmp/custom_config.yaml"
        with patch("deep_thought.todoist.cli.load_config", return_value=minimal_config) as mock_load:
            _load_config_from_args(args_base)
            mock_load.assert_called_once_with(Path("/tmp/custom_config.yaml"))


# ---------------------------------------------------------------------------
# cmd_init
# ---------------------------------------------------------------------------


class TestCmdInit:
    def test_prints_confirmation_and_paths(
        self,
        args_base: argparse.Namespace,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """init must print a success message and the paths it created."""
        monkeypatch.chdir(tmp_path)
        bundled = tmp_path / "bundled.yaml"
        bundled.write_text("# bundled config\n", encoding="utf-8")

        fake_db_path = tmp_path / "data" / "todoist" / "todoist.db"
        mock_conn = MagicMock()

        with (
            patch("deep_thought.todoist.cli.get_bundled_config_path", return_value=bundled),
            patch("deep_thought.todoist.cli.get_database_path", return_value=fake_db_path),
            patch("deep_thought.todoist.cli.initialize_database", return_value=mock_conn),
        ):
            cmd_init(args_base)

        captured_output = capsys.readouterr().out
        assert "initialised successfully" in captured_output
        assert str(fake_db_path) in captured_output
        assert "TODOIST_API_TOKEN" in captured_output
        mock_conn.close.assert_called_once()

    def test_copies_config_to_project_when_missing(
        self,
        args_base: argparse.Namespace,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """init must copy the bundled config template to src/config/ when absent."""
        monkeypatch.chdir(tmp_path)
        bundled = tmp_path / "bundled.yaml"
        bundled.write_text("# bundled default\napi_token_env: TODOIST_API_TOKEN\n", encoding="utf-8")

        fake_db_path = tmp_path / "data" / "todoist" / "todoist.db"
        mock_conn = MagicMock()

        with (
            patch("deep_thought.todoist.cli.get_bundled_config_path", return_value=bundled),
            patch("deep_thought.todoist.cli.get_database_path", return_value=fake_db_path),
            patch("deep_thought.todoist.cli.initialize_database", return_value=mock_conn),
        ):
            cmd_init(args_base)

        project_config = tmp_path / "src" / "config" / "todoist-configuration.yaml"
        assert project_config.exists()
        assert project_config.read_text() == "# bundled default\napi_token_env: TODOIST_API_TOKEN\n"

    def test_skips_config_copy_when_already_exists(
        self,
        args_base: argparse.Namespace,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """init must not overwrite an existing project-level config file."""
        monkeypatch.chdir(tmp_path)
        bundled = tmp_path / "bundled.yaml"
        bundled.write_text("# new content\n", encoding="utf-8")

        project_config = tmp_path / "src" / "config" / "todoist-configuration.yaml"
        project_config.parent.mkdir(parents=True)
        project_config.write_text("# existing content\n", encoding="utf-8")

        fake_db_path = tmp_path / "data" / "todoist" / "todoist.db"
        mock_conn = MagicMock()

        with (
            patch("deep_thought.todoist.cli.get_bundled_config_path", return_value=bundled),
            patch("deep_thought.todoist.cli.get_database_path", return_value=fake_db_path),
            patch("deep_thought.todoist.cli.initialize_database", return_value=mock_conn),
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
        """init must create the snapshots and export directories next to the database."""
        monkeypatch.chdir(tmp_path)
        bundled = tmp_path / "bundled.yaml"
        bundled.write_text("# config\n", encoding="utf-8")

        data_dir = tmp_path / "data" / "todoist"
        fake_db_path = data_dir / "todoist.db"
        mock_conn = MagicMock()

        with (
            patch("deep_thought.todoist.cli.get_bundled_config_path", return_value=bundled),
            patch("deep_thought.todoist.cli.get_database_path", return_value=fake_db_path),
            patch("deep_thought.todoist.cli.initialize_database", return_value=mock_conn),
        ):
            cmd_init(args_base)

        assert (data_dir / "snapshots").exists()
        assert (data_dir / "export").exists()

    def test_exits_with_code_1_when_bundled_config_missing(
        self,
        args_base: argparse.Namespace,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """init must exit with code 1 if the bundled config template is not found."""
        monkeypatch.chdir(tmp_path)
        missing_bundled = tmp_path / "nonexistent.yaml"

        with (
            patch("deep_thought.todoist.cli.get_bundled_config_path", return_value=missing_bundled),
            pytest.raises(SystemExit) as exc_info,
        ):
            cmd_init(args_base)

        assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# cmd_config
# ---------------------------------------------------------------------------


class TestCmdConfig:
    def test_displays_config_values(
        self,
        args_base: argparse.Namespace,
        minimal_config: TodoistConfig,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """config must print all key configuration sections."""
        with (
            patch("deep_thought.todoist.cli.load_config", return_value=minimal_config),
            patch("deep_thought.todoist.cli.validate_config", return_value=[]),
        ):
            cmd_config(args_base)

        captured_output = capsys.readouterr().out
        assert "api_token_env" in captured_output
        assert "TODOIST_API_TOKEN" in captured_output
        assert "pull_filters" in captured_output
        assert "push_filters" in captured_output
        assert "claude" in captured_output

    def test_prints_validation_issues(
        self,
        args_base: argparse.Namespace,
        minimal_config: TodoistConfig,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """config must display any validation warnings before the config listing."""
        warning_message = "No projects configured."
        with (
            patch("deep_thought.todoist.cli.load_config", return_value=minimal_config),
            patch("deep_thought.todoist.cli.validate_config", return_value=[warning_message]),
        ):
            cmd_config(args_base)

        captured_output = capsys.readouterr().out
        assert "WARNING" in captured_output
        assert warning_message in captured_output


# ---------------------------------------------------------------------------
# cmd_pull
# ---------------------------------------------------------------------------


class TestCmdPull:
    def test_prints_pull_summary(
        self,
        args_base: argparse.Namespace,
        minimal_config: TodoistConfig,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """pull must print the PullResult counts after a successful run."""
        fake_result = PullResult(
            projects_synced=2,
            sections_synced=5,
            tasks_synced=20,
            tasks_filtered_out=3,
            comments_synced=10,
            labels_synced=4,
            snapshot_path="/tmp/snap.json",
        )
        mock_conn = MagicMock()

        with (
            patch("deep_thought.todoist.cli.load_config", return_value=minimal_config),
            patch("deep_thought.todoist.cli.get_api_token", return_value="tok"),
            patch("deep_thought.todoist.cli.TodoistClient"),
            patch("deep_thought.todoist.cli.initialize_database", return_value=mock_conn),
            patch("deep_thought.todoist.cli.pull", return_value=fake_result),
        ):
            cmd_pull(args_base)

        captured_output = capsys.readouterr().out
        assert "Pull complete" in captured_output
        assert "Projects:  2" in captured_output
        assert "Tasks:     20 synced, 3 filtered" in captured_output
        assert "/tmp/snap.json" in captured_output
        mock_conn.close.assert_called_once()

    def test_dry_run_prefix_shown(
        self,
        args_base: argparse.Namespace,
        minimal_config: TodoistConfig,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """When --dry-run is set, output must start with [dry-run]."""
        args_base.dry_run = True
        fake_result = PullResult()
        mock_conn = MagicMock()

        with (
            patch("deep_thought.todoist.cli.load_config", return_value=minimal_config),
            patch("deep_thought.todoist.cli.get_api_token", return_value="tok"),
            patch("deep_thought.todoist.cli.TodoistClient"),
            patch("deep_thought.todoist.cli.initialize_database", return_value=mock_conn),
            patch("deep_thought.todoist.cli.pull", return_value=fake_result),
        ):
            cmd_pull(args_base)

        assert "[dry-run]" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# cmd_push
# ---------------------------------------------------------------------------


class TestCmdPush:
    def test_prints_push_summary(
        self,
        args_base: argparse.Namespace,
        minimal_config: TodoistConfig,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """push must print the PushResult counts after a successful run."""
        fake_result = PushResult(tasks_pushed=3, tasks_filtered_out=1, tasks_failed=0)
        mock_conn = MagicMock()

        with (
            patch("deep_thought.todoist.cli.load_config", return_value=minimal_config),
            patch("deep_thought.todoist.cli.get_api_token", return_value="tok"),
            patch("deep_thought.todoist.cli.TodoistClient"),
            patch("deep_thought.todoist.cli.initialize_database", return_value=mock_conn),
            patch("deep_thought.todoist.cli.push", return_value=fake_result),
        ):
            cmd_push(args_base)

        captured_output = capsys.readouterr().out
        assert "Push complete" in captured_output
        assert "Pushed:   3" in captured_output
        mock_conn.close.assert_called_once()


# ---------------------------------------------------------------------------
# cmd_sync
# ---------------------------------------------------------------------------


class TestCmdSync:
    def test_prints_combined_sync_summary(
        self,
        args_base: argparse.Namespace,
        minimal_config: TodoistConfig,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """sync must print pull and push result sections."""
        fake_sync_result = SyncResult(
            pull_result=PullResult(
                projects_synced=1,
                sections_synced=2,
                tasks_synced=5,
                tasks_filtered_out=0,
                comments_synced=1,
                labels_synced=2,
            ),
            push_result=PushResult(tasks_pushed=2, tasks_filtered_out=0, tasks_failed=0),
        )
        mock_conn = MagicMock()

        with (
            patch("deep_thought.todoist.cli.load_config", return_value=minimal_config),
            patch("deep_thought.todoist.cli.get_api_token", return_value="tok"),
            patch("deep_thought.todoist.cli.TodoistClient"),
            patch("deep_thought.todoist.cli.initialize_database", return_value=mock_conn),
            patch("deep_thought.todoist.cli.sync", return_value=fake_sync_result),
        ):
            cmd_sync(args_base)

        captured_output = capsys.readouterr().out
        assert "Sync complete" in captured_output
        assert "Pull:" in captured_output
        assert "Push:" in captured_output
        assert "Pushed:    2" in captured_output
        mock_conn.close.assert_called_once()


# ---------------------------------------------------------------------------
# cmd_status
# ---------------------------------------------------------------------------


class TestCmdStatus:
    def test_prints_status_when_never_synced(
        self,
        args_base: argparse.Namespace,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """status must report 'never' for last sync and zero counts on a fresh DB."""
        mock_conn = MagicMock()

        with (
            patch("deep_thought.todoist.cli.initialize_database", return_value=mock_conn),
            patch("deep_thought.todoist.cli.get_sync_value", return_value=None),
            patch("deep_thought.todoist.cli.get_modified_tasks", return_value=[]),
            patch("deep_thought.todoist.cli.get_all_projects", return_value=[]),
        ):
            cmd_status(args_base)

        captured_output = capsys.readouterr().out
        assert "never" in captured_output
        assert "Modified tasks:    0" in captured_output
        mock_conn.close.assert_called_once()

    def test_lists_modified_task_ids_when_present(
        self,
        args_base: argparse.Namespace,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """status must list task IDs when modified tasks exist."""
        mock_conn = MagicMock()
        fake_tasks = [{"id": "abc123", "content": "Write tests"}]

        with (
            patch("deep_thought.todoist.cli.initialize_database", return_value=mock_conn),
            patch("deep_thought.todoist.cli.get_sync_value", return_value=None),
            patch("deep_thought.todoist.cli.get_modified_tasks", return_value=fake_tasks),
            patch("deep_thought.todoist.cli.get_all_projects", return_value=[]),
        ):
            cmd_status(args_base)

        captured_output = capsys.readouterr().out
        assert "abc123" in captured_output
        assert "Write tests" in captured_output


# ---------------------------------------------------------------------------
# cmd_diff
# ---------------------------------------------------------------------------


class TestCmdDiff:
    def test_no_changes_message(
        self,
        args_base: argparse.Namespace,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """diff must print 'No local changes.' when no tasks are modified."""
        mock_conn = MagicMock()

        with (
            patch("deep_thought.todoist.cli.initialize_database", return_value=mock_conn),
            patch("deep_thought.todoist.cli.get_modified_tasks", return_value=[]),
        ):
            cmd_diff(args_base)

        assert "No local changes." in capsys.readouterr().out

    def test_shows_modified_task_details(
        self,
        args_base: argparse.Namespace,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """diff must display task ID, content, updated_at, and synced_at."""
        mock_conn = MagicMock()
        fake_tasks = [
            {
                "id": "task99",
                "content": "Fix the bug",
                "updated_at": "2026-03-10T10:00:00",
                "synced_at": "2026-03-09T09:00:00",
                "priority": 2,
                "due_date": "2026-03-15",
            }
        ]

        with (
            patch("deep_thought.todoist.cli.initialize_database", return_value=mock_conn),
            patch("deep_thought.todoist.cli.get_modified_tasks", return_value=fake_tasks),
        ):
            cmd_diff(args_base)

        captured_output = capsys.readouterr().out
        assert "task99" in captured_output
        assert "Fix the bug" in captured_output
        assert "2026-03-10T10:00:00" in captured_output
        assert "2026-03-15" in captured_output


# ---------------------------------------------------------------------------
# cmd_export
# ---------------------------------------------------------------------------


class TestCmdExport:
    def test_prints_export_summary(
        self,
        args_base: argparse.Namespace,
        minimal_config: TodoistConfig,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """export must print counts from ExportResult."""
        fake_result = ExportResult(projects_exported=1, files_written=3, tasks_exported=12)
        mock_conn = MagicMock()

        with (
            patch("deep_thought.todoist.cli.load_config", return_value=minimal_config),
            patch("deep_thought.todoist.cli.initialize_database", return_value=mock_conn),
            patch("deep_thought.todoist.cli.export_to_markdown", return_value=fake_result),
        ):
            cmd_export(args_base)

        captured_output = capsys.readouterr().out
        assert "Export complete" in captured_output
        assert "Projects: 1" in captured_output
        assert "Files:    3" in captured_output
        assert "Tasks:    12" in captured_output
        mock_conn.close.assert_called_once()


# ---------------------------------------------------------------------------
# cmd_create
# ---------------------------------------------------------------------------


class TestCmdCreate:
    def test_prints_created_task_id_and_content(
        self,
        args_base: argparse.Namespace,
        minimal_config: TodoistConfig,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """create must print the new task ID and content on success."""
        args_base.project = "Work"
        args_base.content = "Write release notes"
        args_base.description = None
        args_base.due = None
        args_base.priority = None
        args_base.label = None
        args_base.section = None
        fake_result = CreateResult(task_id="task-42", task_content="Write release notes", created=True, dry_run=False)
        mock_conn = MagicMock()

        with (
            patch("deep_thought.todoist.cli.load_config", return_value=minimal_config),
            patch("deep_thought.todoist.cli.get_api_token", return_value="tok"),
            patch("deep_thought.todoist.cli.TodoistClient"),
            patch("deep_thought.todoist.cli.initialize_database", return_value=mock_conn),
            patch("deep_thought.todoist.cli.create_task", return_value=fake_result),
        ):
            cmd_create(args_base)

        captured_output = capsys.readouterr().out
        assert "task-42" in captured_output
        assert "Write release notes" in captured_output
        mock_conn.close.assert_called_once()

    def test_dry_run_prints_would_create_message(
        self,
        args_base: argparse.Namespace,
        minimal_config: TodoistConfig,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """create --dry-run must print a [dry-run] prefix without creating the task."""
        args_base.dry_run = True
        args_base.project = "Work"
        args_base.content = "A dry-run task"
        args_base.description = None
        args_base.due = None
        args_base.priority = None
        args_base.label = None
        args_base.section = None
        fake_result = CreateResult(task_id="", task_content="A dry-run task", created=False, dry_run=True)
        mock_conn = MagicMock()

        with (
            patch("deep_thought.todoist.cli.load_config", return_value=minimal_config),
            patch("deep_thought.todoist.cli.get_api_token", return_value="tok"),
            patch("deep_thought.todoist.cli.TodoistClient"),
            patch("deep_thought.todoist.cli.initialize_database", return_value=mock_conn),
            patch("deep_thought.todoist.cli.create_task", return_value=fake_result),
        ):
            cmd_create(args_base)

        captured_output = capsys.readouterr().out
        assert "[dry-run]" in captured_output
        assert "A dry-run task" in captured_output

    def test_exits_when_project_flag_missing(
        self,
        args_base: argparse.Namespace,
        minimal_config: TodoistConfig,
    ) -> None:
        """create must exit with code 1 when --project is not provided."""
        args_base.project = None
        args_base.content = "Task without project"

        with (
            patch("deep_thought.todoist.cli.load_config", return_value=minimal_config),
            pytest.raises(SystemExit) as exc_info,
        ):
            cmd_create(args_base)

        assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# cmd_complete
# ---------------------------------------------------------------------------


class TestCmdComplete:
    def test_prints_completed_task_content(
        self,
        args_base: argparse.Namespace,
        minimal_config: TodoistConfig,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """complete must print the task ID and content when the task is closed."""
        args_base.task_id = "task-55"
        fake_task_row = {"id": "task-55", "content": "Deploy to production"}
        mock_conn = MagicMock()

        with (
            patch("deep_thought.todoist.cli.load_config", return_value=minimal_config),
            patch("deep_thought.todoist.cli.get_api_token", return_value="tok"),
            patch("deep_thought.todoist.cli.TodoistClient") as mock_client_class,
            patch("deep_thought.todoist.cli.initialize_database", return_value=mock_conn),
            patch("deep_thought.todoist.cli.get_task_by_id", return_value=fake_task_row),
            patch("deep_thought.todoist.cli.mark_task_completed"),
        ):
            mock_api_client = mock_client_class.return_value
            cmd_complete(args_base)

        captured_output = capsys.readouterr().out
        assert "task-55" in captured_output
        assert "Deploy to production" in captured_output
        mock_api_client.close_task.assert_called_once_with("task-55")
        mock_conn.close.assert_called_once()

    def test_dry_run_does_not_close_task(
        self,
        args_base: argparse.Namespace,
        minimal_config: TodoistConfig,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """complete --dry-run must print [dry-run] and not call close_task or commit."""
        args_base.dry_run = True
        args_base.task_id = "task-55"
        fake_task_row = {"id": "task-55", "content": "Deploy to production"}
        mock_conn = MagicMock()

        with (
            patch("deep_thought.todoist.cli.load_config", return_value=minimal_config),
            patch("deep_thought.todoist.cli.get_api_token", return_value="tok"),
            patch("deep_thought.todoist.cli.TodoistClient") as mock_client_class,
            patch("deep_thought.todoist.cli.initialize_database", return_value=mock_conn),
            patch("deep_thought.todoist.cli.get_task_by_id", return_value=fake_task_row),
        ):
            mock_api_client = mock_client_class.return_value
            cmd_complete(args_base)

        captured_output = capsys.readouterr().out
        assert "[dry-run]" in captured_output
        mock_api_client.close_task.assert_not_called()
        mock_conn.commit.assert_not_called()

    @pytest.mark.error_handling
    def test_exits_when_task_not_found(
        self,
        args_base: argparse.Namespace,
        minimal_config: TodoistConfig,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """complete must exit with code 1 when the task ID is not in the database."""
        args_base.task_id = "nonexistent-task"
        mock_conn = MagicMock()

        with (
            patch("deep_thought.todoist.cli.load_config", return_value=minimal_config),
            patch("deep_thought.todoist.cli.get_api_token", return_value="tok"),
            patch("deep_thought.todoist.cli.TodoistClient"),
            patch("deep_thought.todoist.cli.initialize_database", return_value=mock_conn),
            patch("deep_thought.todoist.cli.get_task_by_id", return_value=None),
            pytest.raises(SystemExit) as exc_info,
        ):
            cmd_complete(args_base)

        assert exc_info.value.code == 1
        assert "nonexistent-task" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# main() — entry point dispatch
# ---------------------------------------------------------------------------


class TestMain:
    def test_no_subcommand_prints_help_and_exits_zero(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Calling main with no subcommand must print help and exit 0."""
        with (
            patch("sys.argv", ["todoist"]),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()
        assert exc_info.value.code == 0

    def test_dispatches_to_correct_handler(self) -> None:
        """main must call the handler registered for the given subcommand.

        The dispatch dict (_COMMAND_HANDLERS) holds references captured at
        import time, so we must patch the dict entry rather than the module
        attribute for the mock to be invoked.
        """
        mock_handler = MagicMock()
        with (
            patch("sys.argv", ["todoist", "status"]),
            patch.dict("deep_thought.todoist.cli._COMMAND_HANDLERS", {"status": mock_handler}),
        ):
            main()
            mock_handler.assert_called_once()

    @pytest.mark.error_handling
    def test_file_not_found_exits_with_code_1(self, capsys: pytest.CaptureFixture[str]) -> None:
        """A FileNotFoundError raised inside a handler must exit with code 1."""
        mock_handler = MagicMock(side_effect=FileNotFoundError("config.yaml"))
        with (
            patch("sys.argv", ["todoist", "config"]),
            patch.dict("deep_thought.todoist.cli._COMMAND_HANDLERS", {"config": mock_handler}),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()
        assert exc_info.value.code == 1
        assert "File not found" in capsys.readouterr().err

    @pytest.mark.error_handling
    def test_os_error_exits_with_code_1(self, capsys: pytest.CaptureFixture[str]) -> None:
        """An OSError raised inside a handler (e.g., missing API token) must exit with code 1."""
        mock_handler = MagicMock(side_effect=OSError("token not set"))
        with (
            patch("sys.argv", ["todoist", "pull"]),
            patch.dict("deep_thought.todoist.cli._COMMAND_HANDLERS", {"pull": mock_handler}),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()
        assert exc_info.value.code == 1
        assert "token not set" in capsys.readouterr().err

    @pytest.mark.error_handling
    def test_unexpected_exception_exits_with_code_1(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Any unhandled exception raised inside a handler must exit with code 1."""
        mock_handler = MagicMock(side_effect=RuntimeError("boom"))
        with (
            patch("sys.argv", ["todoist", "sync"]),
            patch.dict("deep_thought.todoist.cli._COMMAND_HANDLERS", {"sync": mock_handler}),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()
        assert exc_info.value.code == 1
        assert "unexpected error" in capsys.readouterr().err.lower()

    def test_dispatches_to_attach_handler(self) -> None:
        """main must dispatch the 'attach' subcommand to cmd_attach.

        The dispatch dict (_COMMAND_HANDLERS) holds references captured at import
        time, so we patch the dict entry rather than the module-level attribute.
        """
        mock_handler = MagicMock()
        with (
            patch("sys.argv", ["todoist", "attach", "task-42", "/tmp/report.pdf"]),
            patch.dict("deep_thought.todoist.cli._COMMAND_HANDLERS", {"attach": mock_handler}),
        ):
            main()
            mock_handler.assert_called_once()
