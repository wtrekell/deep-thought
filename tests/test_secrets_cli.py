"""Tests for deep_thought.secrets_cli — Keychain management CLI."""

from __future__ import annotations

import argparse
from unittest.mock import patch

import pytest

from deep_thought.secrets_cli import (
    _SECRET_REGISTRY,
    build_parser,
    cmd_delete,
    cmd_migrate,
    cmd_set,
    cmd_status,
)

# ---------------------------------------------------------------------------
# Registry sanity
# ---------------------------------------------------------------------------


def test_registry_has_expected_tools() -> None:
    """The secret registry should contain entries for all tools that use API keys."""
    expected_tools = {"todoist", "reddit", "research", "audio", "gmail"}
    assert set(_SECRET_REGISTRY.keys()) == expected_tools


def test_registry_entries_are_triples() -> None:
    """Each registry entry must be a (service, key_name, env_var) triple."""
    for tool_name, entries in _SECRET_REGISTRY.items():
        for entry in entries:
            assert len(entry) == 3, f"{tool_name}: expected 3-tuple, got {len(entry)}"
            service, key_name, env_var = entry
            assert isinstance(service, str) and service
            assert isinstance(key_name, str) and key_name
            assert isinstance(env_var, str) and env_var


# ---------------------------------------------------------------------------
# build_parser
# ---------------------------------------------------------------------------


def test_parser_parses_status() -> None:
    """The parser should accept 'status' as a subcommand."""
    parser = build_parser()
    args = parser.parse_args(["status"])
    assert args.command == "status"


def test_parser_parses_migrate() -> None:
    """The parser should accept 'migrate' as a subcommand."""
    parser = build_parser()
    args = parser.parse_args(["migrate"])
    assert args.command == "migrate"


def test_parser_parses_set_with_value() -> None:
    """The parser should accept 'set' with tool, key_name, and --value."""
    parser = build_parser()
    args = parser.parse_args(["set", "todoist", "api-token", "--value", "secret123"])
    assert args.command == "set"
    assert args.tool == "todoist"
    assert args.key_name == "api-token"
    assert args.value == "secret123"


def test_parser_parses_delete() -> None:
    """The parser should accept 'delete' with tool and key_name."""
    parser = build_parser()
    args = parser.parse_args(["delete", "todoist", "api-token"])
    assert args.command == "delete"
    assert args.tool == "todoist"
    assert args.key_name == "api-token"


# ---------------------------------------------------------------------------
# cmd_status
# ---------------------------------------------------------------------------


def test_status_reports_keychain_and_env(capsys: pytest.CaptureFixture[str]) -> None:
    """cmd_status should report secrets found in keychain and .env."""
    args = argparse.Namespace()

    with (
        patch("deep_thought.secrets_cli.keychain_available", return_value=True),
        patch("deep_thought.secrets_cli.dotenv_values", return_value={"TODOIST_API_TOKEN": "tok123"}),
        patch("deep_thought.secrets_cli.keyring.get_password", return_value="keychain-value"),
    ):
        cmd_status(args)

    output = capsys.readouterr().out
    assert "available" in output
    assert "keychain" in output


def test_status_reports_missing_when_not_found(capsys: pytest.CaptureFixture[str]) -> None:
    """cmd_status should show MISSING when a secret is in neither keychain nor .env."""
    args = argparse.Namespace()

    with (
        patch("deep_thought.secrets_cli.keychain_available", return_value=False),
        patch("deep_thought.secrets_cli.dotenv_values", return_value={}),
    ):
        cmd_status(args)

    output = capsys.readouterr().out
    assert "MISSING" in output


# ---------------------------------------------------------------------------
# cmd_migrate
# ---------------------------------------------------------------------------


def test_migrate_stores_env_secrets_in_keychain(capsys: pytest.CaptureFixture[str]) -> None:
    """cmd_migrate should call set_secret for each .env secret found."""
    args = argparse.Namespace()

    with (
        patch("deep_thought.secrets_cli.keychain_available", return_value=True),
        patch("deep_thought.secrets_cli.dotenv_values", return_value={"TODOIST_API_TOKEN": "tok123"}),
        patch("deep_thought.secrets_cli.set_secret") as mock_set,
    ):
        cmd_migrate(args)

    # Should have been called for todoist/api-token
    mock_set.assert_any_call("todoist", "api-token", "tok123")
    output = capsys.readouterr().out
    assert "Migrated" in output


def test_migrate_skips_missing_env_vars(capsys: pytest.CaptureFixture[str]) -> None:
    """cmd_migrate should skip secrets not present in .env."""
    args = argparse.Namespace()

    with (
        patch("deep_thought.secrets_cli.keychain_available", return_value=True),
        patch("deep_thought.secrets_cli.dotenv_values", return_value={}),
        patch("deep_thought.secrets_cli.set_secret") as mock_set,
    ):
        cmd_migrate(args)

    mock_set.assert_not_called()
    output = capsys.readouterr().out
    assert "No secrets found" in output


def test_migrate_exits_when_keychain_unavailable() -> None:
    """cmd_migrate should exit with error when keychain is not available."""
    args = argparse.Namespace()

    with (
        patch("deep_thought.secrets_cli.keychain_available", return_value=False),
        pytest.raises(SystemExit, match="1"),
    ):
        cmd_migrate(args)


# ---------------------------------------------------------------------------
# cmd_set
# ---------------------------------------------------------------------------


def test_set_stores_value_from_flag() -> None:
    """cmd_set should store the secret from --value flag."""
    args = argparse.Namespace(tool="todoist", key_name="api-token", value="secret123")

    with (
        patch("deep_thought.secrets_cli.keychain_available", return_value=True),
        patch("deep_thought.secrets_cli.set_secret") as mock_set,
    ):
        cmd_set(args)

    mock_set.assert_called_once_with("todoist", "api-token", "secret123")


def test_set_prompts_when_no_value_flag() -> None:
    """cmd_set should prompt for input when --value is not given."""
    args = argparse.Namespace(tool="reddit", key_name="client-id", value=None)

    with (
        patch("deep_thought.secrets_cli.keychain_available", return_value=True),
        patch("deep_thought.secrets_cli.getpass.getpass", return_value="prompted-value"),
        patch("deep_thought.secrets_cli.set_secret") as mock_set,
    ):
        cmd_set(args)

    mock_set.assert_called_once_with("reddit", "client-id", "prompted-value")


def test_set_exits_on_empty_value() -> None:
    """cmd_set should exit with error when the value is empty."""
    args = argparse.Namespace(tool="todoist", key_name="api-token", value="")

    with (
        patch("deep_thought.secrets_cli.keychain_available", return_value=True),
        pytest.raises(SystemExit, match="1"),
    ):
        cmd_set(args)


def test_set_exits_when_keychain_unavailable() -> None:
    """cmd_set should exit with error when keychain is not available."""
    args = argparse.Namespace(tool="todoist", key_name="api-token", value="secret")

    with (
        patch("deep_thought.secrets_cli.keychain_available", return_value=False),
        pytest.raises(SystemExit, match="1"),
    ):
        cmd_set(args)


# ---------------------------------------------------------------------------
# cmd_delete
# ---------------------------------------------------------------------------


def test_delete_removes_secret() -> None:
    """cmd_delete should call delete_secret with the correct args."""
    args = argparse.Namespace(tool="todoist", key_name="api-token")

    with (
        patch("deep_thought.secrets_cli.keychain_available", return_value=True),
        patch("deep_thought.secrets_cli.delete_secret") as mock_del,
    ):
        cmd_delete(args)

    mock_del.assert_called_once_with("todoist", "api-token")


def test_delete_exits_when_keychain_unavailable() -> None:
    """cmd_delete should exit with error when keychain is not available."""
    args = argparse.Namespace(tool="todoist", key_name="api-token")

    with (
        patch("deep_thought.secrets_cli.keychain_available", return_value=False),
        pytest.raises(SystemExit, match="1"),
    ):
        cmd_delete(args)
