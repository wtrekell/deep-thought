"""Tests for deep_thought.gdrive.cli — subcommand dispatch and exit codes."""

from __future__ import annotations

import contextlib
import sys
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

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
