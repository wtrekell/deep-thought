"""Tests for deep_thought.gdrive.cli — subcommand dispatch and exit codes."""

from __future__ import annotations

import contextlib
import sys
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from deep_thought.gdrive.cli import _build_argument_parser, main

if TYPE_CHECKING:
    from pathlib import Path

# ---------------------------------------------------------------------------
# Argument parser tests
# ---------------------------------------------------------------------------


def test_parser_parses_dry_run_flag() -> None:
    """--dry-run flag is parsed correctly."""
    parser = _build_argument_parser()
    args = parser.parse_args(["--dry-run"])
    assert args.dry_run is True


def test_parser_parses_force_flag() -> None:
    """--force flag is parsed correctly."""
    parser = _build_argument_parser()
    args = parser.parse_args(["--force"])
    assert args.force is True


def test_parser_parses_verbose_short_flag() -> None:
    """-v short flag is parsed as verbose."""
    parser = _build_argument_parser()
    args = parser.parse_args(["-v"])
    assert args.verbose is True


def test_parser_parses_verbose_long_flag() -> None:
    """--verbose long flag is parsed correctly."""
    parser = _build_argument_parser()
    args = parser.parse_args(["--verbose"])
    assert args.verbose is True


def test_parser_parses_config_path() -> None:
    """--config PATH is stored in args.config."""
    parser = _build_argument_parser()
    args = parser.parse_args(["--config", "/some/path.yaml"])
    assert args.config == "/some/path.yaml"


def test_parser_subcommand_init() -> None:
    """'init' subcommand is dispatched correctly."""
    parser = _build_argument_parser()
    args = parser.parse_args(["init"])
    assert args.subcommand == "init"


def test_parser_subcommand_config() -> None:
    """'config' subcommand is dispatched correctly."""
    parser = _build_argument_parser()
    args = parser.parse_args(["config"])
    assert args.subcommand == "config"


def test_parser_subcommand_auth() -> None:
    """'auth' subcommand is dispatched correctly."""
    parser = _build_argument_parser()
    args = parser.parse_args(["auth"])
    assert args.subcommand == "auth"


def test_parser_subcommand_status() -> None:
    """'status' subcommand is dispatched correctly."""
    parser = _build_argument_parser()
    args = parser.parse_args(["status"])
    assert args.subcommand == "status"


def test_parser_no_subcommand_has_none_subcommand() -> None:
    """With no subcommand, args.subcommand is None (triggers default backup)."""
    parser = _build_argument_parser()
    args = parser.parse_args([])
    assert args.subcommand is None


# ---------------------------------------------------------------------------
# cmd_backup exit code tests
# ---------------------------------------------------------------------------


def _patch_backup_for_cli(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    drive_folder_id: str = "root-folder",
    backup_side_effect: object = None,
) -> None:
    """Patch config, client, and DB for CLI backup tests."""
    from deep_thought.gdrive.config import GDriveConfig
    from deep_thought.gdrive.models import BackupResult

    mock_config = GDriveConfig(
        credentials_file=str(tmp_path / "credentials.json"),
        token_file=str(tmp_path / "token.json"),
        scopes=["https://www.googleapis.com/auth/drive.file"],
        source_dir=str(tmp_path / "source"),
        drive_folder_id=drive_folder_id,
        exclude_patterns=[],
        api_rate_limit_rpm=0,
        retry_max_attempts=1,
        retry_base_delay_seconds=0.0,
    )

    mock_client = MagicMock()
    mock_db = MagicMock()
    mock_db.commit.return_value = None

    if backup_side_effect is None:
        default_result = BackupResult(uploaded=1, updated=0, skipped=0, errors=0)
        backup_side_effect = default_result

    monkeypatch.setattr("deep_thought.gdrive.cli.load_config", lambda _path: mock_config)
    monkeypatch.setattr("deep_thought.gdrive.cli._make_client_from_config", lambda _cfg: mock_client)
    monkeypatch.setattr("deep_thought.gdrive.cli.open_database", lambda: mock_db)
    monkeypatch.setattr(
        "deep_thought.gdrive.cli.run_backup",
        lambda **_kwargs: backup_side_effect,
    )


def test_cmd_backup_exits_0_on_success(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """cmd_backup returns normally (exit code 0) when backup succeeds with no errors."""
    from deep_thought.gdrive.models import BackupResult

    _patch_backup_for_cli(monkeypatch, tmp_path, backup_side_effect=BackupResult(uploaded=3))

    # A successful backup returns normally without calling sys.exit(),
    # which is equivalent to an exit code of 0.
    sys.argv = ["gdrive"]
    main()  # Must not raise


def test_cmd_backup_exits_2_on_partial_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """cmd_backup exits with code 2 when errors > 0."""
    from deep_thought.gdrive.models import BackupResult

    partial_failure_result = BackupResult(uploaded=2, errors=1, error_paths=["source/bad.txt"])
    _patch_backup_for_cli(monkeypatch, tmp_path, backup_side_effect=partial_failure_result)

    with pytest.raises(SystemExit) as exc_info:
        sys.argv = ["gdrive"]
        main()

    assert exc_info.value.code == 2


def test_cmd_backup_exits_1_when_drive_folder_id_empty(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """cmd_backup exits with code 1 when drive_folder_id is empty."""
    _patch_backup_for_cli(monkeypatch, tmp_path, drive_folder_id="")

    with pytest.raises(SystemExit) as exc_info:
        sys.argv = ["gdrive"]
        main()

    assert exc_info.value.code == 1


def test_cmd_backup_dry_run_flag_is_passed_through(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """--dry-run flag is forwarded to run_backup."""
    from deep_thought.gdrive.models import BackupResult

    captured_kwargs: dict[str, object] = {}

    def capture_run_backup(**kwargs: object) -> BackupResult:
        captured_kwargs.update(kwargs)
        return BackupResult()

    _patch_backup_for_cli(monkeypatch, tmp_path)
    monkeypatch.setattr("deep_thought.gdrive.cli.run_backup", capture_run_backup)

    sys.argv = ["gdrive", "--dry-run"]
    with contextlib.suppress(SystemExit):
        main()

    assert captured_kwargs.get("dry_run") is True


def test_cmd_backup_force_flag_is_passed_through(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """--force flag is forwarded to run_backup."""
    from deep_thought.gdrive.models import BackupResult

    captured_kwargs: dict[str, object] = {}

    def capture_run_backup(**kwargs: object) -> BackupResult:
        captured_kwargs.update(kwargs)
        return BackupResult()

    _patch_backup_for_cli(monkeypatch, tmp_path)
    monkeypatch.setattr("deep_thought.gdrive.cli.run_backup", capture_run_backup)

    sys.argv = ["gdrive", "--force"]
    with contextlib.suppress(SystemExit):
        main()

    assert captured_kwargs.get("force") is True


# ---------------------------------------------------------------------------
# Subcommand dispatch via main()
# ---------------------------------------------------------------------------


def _patch_subcommand_infrastructure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Patch the infrastructure that every subcommand or default backup run touches.

    Patches load_dotenv, open_database, load_config, and _make_client_from_config
    so that subcommand handlers can reach their dispatch point without hitting
    the filesystem or network.
    """
    from deep_thought.gdrive.config import GDriveConfig

    mock_config = GDriveConfig(
        credentials_file=str(tmp_path / "credentials.json"),
        token_file=str(tmp_path / "token.json"),
        scopes=["https://www.googleapis.com/auth/drive.file"],
        source_dir=str(tmp_path / "source"),
        drive_folder_id="root-folder-id",
        exclude_patterns=[],
        api_rate_limit_rpm=0,
        retry_max_attempts=1,
        retry_base_delay_seconds=0.0,
    )

    monkeypatch.setattr("deep_thought.gdrive.cli.load_dotenv", lambda: None)
    monkeypatch.setattr("deep_thought.gdrive.cli.load_config", lambda _path: mock_config)
    monkeypatch.setattr("deep_thought.gdrive.cli.open_database", lambda: MagicMock())
    monkeypatch.setattr("deep_thought.gdrive.cli._make_client_from_config", lambda _cfg: MagicMock())


def test_main_dispatches_to_cmd_status(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """main() with 'status' subcommand dispatches to cmd_status via _run_command."""
    _patch_subcommand_infrastructure(monkeypatch, tmp_path)

    dispatched_handlers: list[str] = []

    def capture_run_command(handler: object, args: object) -> None:
        import deep_thought.gdrive.cli as cli_module

        if handler is cli_module.cmd_status:
            dispatched_handlers.append("cmd_status")

    monkeypatch.setattr("deep_thought.gdrive.cli._run_command", capture_run_command)

    sys.argv = ["gdrive", "status"]
    main()

    assert "cmd_status" in dispatched_handlers


def test_main_dispatches_to_cmd_init(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """main() with 'init' subcommand dispatches to cmd_init via _run_command."""
    _patch_subcommand_infrastructure(monkeypatch, tmp_path)

    dispatched_handlers: list[str] = []

    def capture_run_command(handler: object, args: object) -> None:
        import deep_thought.gdrive.cli as cli_module

        if handler is cli_module.cmd_init:
            dispatched_handlers.append("cmd_init")

    monkeypatch.setattr("deep_thought.gdrive.cli._run_command", capture_run_command)

    sys.argv = ["gdrive", "init"]
    main()

    assert "cmd_init" in dispatched_handlers


def test_main_with_prune_flag_calls_run_prune(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """main() with --prune flag calls run_prune instead of run_backup."""
    from deep_thought.gdrive.models import PruneResult

    _patch_subcommand_infrastructure(monkeypatch, tmp_path)

    prune_was_called = False

    def fake_run_prune(**kwargs: object) -> PruneResult:
        nonlocal prune_was_called
        prune_was_called = True
        return PruneResult(deleted=0)

    monkeypatch.setattr("deep_thought.gdrive.cli.run_prune", fake_run_prune)

    sys.argv = ["gdrive", "--prune"]
    with contextlib.suppress(SystemExit):
        main()

    assert prune_was_called, "run_prune should have been called when --prune flag is set"


def test_main_save_config_calls_handle_save_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """main() with --save-config PATH calls _handle_save_config with the given path."""
    _patch_subcommand_infrastructure(monkeypatch, tmp_path)

    captured_paths: list[str] = []

    def fake_handle_save_config(destination_path_str: str) -> None:
        captured_paths.append(destination_path_str)

    monkeypatch.setattr("deep_thought.gdrive.cli._handle_save_config", fake_handle_save_config)

    target_path = str(tmp_path / "output.yaml")
    sys.argv = ["gdrive", "--save-config", target_path]
    main()

    assert captured_paths == [target_path]


# ---------------------------------------------------------------------------
# _get_version
# ---------------------------------------------------------------------------


def test_get_version_returns_unknown_on_package_not_found() -> None:
    """_get_version returns 'unknown' when the package is not installed.

    Patches importlib.metadata.version (the function _get_version imports
    locally) to raise PackageNotFoundError, exercising the narrowed except
    clause added in the source fix.
    """
    from importlib.metadata import PackageNotFoundError

    from deep_thought.gdrive.cli import _get_version

    with patch("importlib.metadata.version", side_effect=PackageNotFoundError("deep-thought")):
        result = _get_version()

    assert result == "unknown"
