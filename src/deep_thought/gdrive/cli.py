"""CLI entry point for the GDrive Tool.

Provides the ``gdrive`` command with subcommands for configuration management,
OAuth authentication, backup execution, and status reporting. The default
operation (no subcommand) runs the backup.

Usage:
    gdrive [--config PATH] [--dry-run] [--force] [--verbose/-v] [--version]
    gdrive init
    gdrive config
    gdrive auth
    gdrive status
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import google.auth.exceptions
from dotenv import load_dotenv
from googleapiclient.errors import HttpError  # type: ignore[import-untyped]

from deep_thought.gdrive.config import GDriveConfig, get_default_config_path, load_config
from deep_thought.gdrive.db.schema import get_data_dir, get_database_path, init_db, open_database
from deep_thought.gdrive.uploader import run_backup, run_prune

if TYPE_CHECKING:
    from collections.abc import Callable

    from deep_thought.gdrive.client import DriveClient

logger = logging.getLogger(__name__)


def _get_version() -> str:
    """Return the installed package version, falling back to 'unknown'."""
    try:
        from importlib.metadata import PackageNotFoundError, version  # noqa: PLC0415

        return version("deep-thought")
    except PackageNotFoundError:
        return "unknown"


_VERSION = _get_version()


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _setup_logging(verbose: bool) -> None:
    """Configure the root logger based on the verbosity flag.

    Args:
        verbose: If True, set log level to DEBUG; otherwise WARNING.
    """
    log_level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(format="%(levelname)s: %(message)s")
    logging.getLogger().setLevel(log_level)


def _load_config_from_args(args: argparse.Namespace) -> GDriveConfig:
    """Load and return the GDrive configuration, honouring the --config flag.

    Args:
        args: Parsed argparse namespace which may contain a config override.

    Returns:
        A fully parsed GDriveConfig.

    Raises:
        FileNotFoundError: If the config file does not exist.
        ValueError: If the config file has invalid content.
    """
    config_path: Path | None = Path(args.config) if args.config else None
    return load_config(config_path)


def _make_client_from_config(config: GDriveConfig) -> DriveClient:
    """Instantiate and authenticate a DriveClient using config settings.

    Args:
        config: A loaded GDriveConfig.

    Returns:
        An authenticated DriveClient ready for API calls.
    """
    from deep_thought.gdrive.client import DriveClient

    client = DriveClient(
        credentials_path=config.credentials_file,
        token_path=config.token_file,
        scopes=config.scopes,
        rate_limit_rpm=config.api_rate_limit_rpm,
        retry_max_attempts=config.retry_max_attempts,
        retry_base_delay=config.retry_base_delay_seconds,
    )
    client.authenticate()
    return client


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------


def cmd_init(args: argparse.Namespace) -> None:
    """Bootstrap the GDrive tool for first use.

    Creates the data directory, initialises the database, and prints the path
    to the config template that needs to be edited before first run.

    Args:
        args: Parsed argparse namespace.
    """
    import sqlite3

    data_dir = get_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)

    database_path = get_database_path()

    raw_connection = sqlite3.connect(str(database_path))
    raw_connection.row_factory = sqlite3.Row
    init_db(raw_connection)
    raw_connection.close()

    default_config_path = get_default_config_path()

    print("GDrive Tool initialised.")
    print()
    print(f"  Database:           {database_path}")
    print(f"  Data directory:     {data_dir}")
    print()
    print("Next steps:")
    print(f"  1. Edit the configuration file: {default_config_path}")
    print("  2. Place credentials.json at the path set under auth.credentials_file.")
    print("  3. Run `gdrive auth` to authenticate with Google.")
    print("  4. Set backup.drive_folder_id to the ID of your target Drive folder.")
    print("  5. Run `gdrive` to start backing up.")


def cmd_config(args: argparse.Namespace) -> None:
    """Load the configuration file and pretty-print all settings.

    Args:
        args: Parsed argparse namespace.
    """
    config = _load_config_from_args(args)

    print("Loaded configuration:")
    print(f"  credentials_file:       {config.credentials_file}")
    print(f"  token_file:             {config.token_file}")
    print(f"  scopes:                 {config.scopes}")
    print(f"  source_dir:             {config.source_dir}")
    print(f"  drive_folder_id:        {config.drive_folder_id!r}")
    print(f"  api_rate_limit_rpm:     {config.api_rate_limit_rpm}")
    print(f"  retry_max_attempts:     {config.retry_max_attempts}")
    print(f"  retry_base_delay_secs:  {config.retry_base_delay_seconds}")

    if not config.drive_folder_id:
        print()
        print("WARNING: backup.drive_folder_id is empty — set it before running a backup.")


def cmd_auth(args: argparse.Namespace) -> None:
    """Run the OAuth 2.0 browser consent flow and save the token.

    Args:
        args: Parsed argparse namespace.
    """
    from deep_thought.gdrive._auth import get_credentials

    config = _load_config_from_args(args)
    get_credentials(
        credentials_path=config.credentials_file,
        token_path=config.token_file,
        scopes=config.scopes,
    )
    print("Authentication successful. Token saved.")


def cmd_status(args: argparse.Namespace) -> None:
    """Print file counts grouped by status and last run timestamp from the database.

    Args:
        args: Parsed argparse namespace.
    """
    from deep_thought.gdrive.db.queries import count_by_status, get_key_value

    connection = open_database()
    try:
        status_counts = count_by_status(connection)
        last_run_at = get_key_value(connection, "last_run_at")
    finally:
        connection.close()

    if not status_counts:
        print("No files recorded yet. Run `gdrive` to start a backup.")
        return

    total = sum(status_counts.values())
    print("Backup status:")
    print(f"  Last run:  {last_run_at or 'never'}")
    for status_name, file_count in sorted(status_counts.items()):
        print(f"  {status_name:<12} {file_count}")
    print(f"  {'total':<12} {total}")


def cmd_backup(args: argparse.Namespace) -> None:
    """Run an incremental backup of the configured source directory to Drive.

    Validates that drive_folder_id is set, then orchestrates the full backup
    via uploader.run_backup().

    Exit codes:
        0 — all files processed successfully
        1 — fatal error (config invalid, auth failed, etc.)
        2 — partial failure (one or more files encountered errors)

    Args:
        args: Parsed argparse namespace with dry_run, force, verbose flags.
    """
    config = _load_config_from_args(args)

    if not config.drive_folder_id:
        print(
            "ERROR: backup.drive_folder_id is empty in the configuration. "
            "Set it to the ID of your root Google Drive backup folder.",
            file=sys.stderr,
        )
        sys.exit(1)

    drive_client = _make_client_from_config(config)

    db_connection = open_database()
    try:
        if args.prune:
            prune_result = run_prune(
                config=config,
                client=drive_client,
                db_conn=db_connection,
                dry_run=args.dry_run,
                verbose=args.verbose,
            )
            db_connection.commit()

            dry_run_prefix = "[dry-run] " if args.dry_run else ""
            print(f"{dry_run_prefix}Prune complete:")
            print(f"  Deleted: {prune_result.deleted}")
            print(f"  Errors:  {prune_result.errors}")

            if prune_result.errors > 0:
                print()
                print("Files with errors:")
                for error_path in prune_result.error_paths:
                    print(f"  {error_path}")
                # SystemExit propagates through finally: db_connection.close() still runs
                sys.exit(2)
            return

        backup_result = run_backup(
            config=config,
            client=drive_client,
            db_conn=db_connection,
            dry_run=args.dry_run,
            force=args.force,
            verbose=args.verbose,
        )
        db_connection.commit()
    finally:
        db_connection.close()

    dry_run_prefix = "[dry-run] " if args.dry_run else ""
    print(f"{dry_run_prefix}Backup complete:")
    print(f"  Uploaded: {backup_result.uploaded}")
    print(f"  Updated:  {backup_result.updated}")
    print(f"  Skipped:  {backup_result.skipped}")
    print(f"  Vanished: {backup_result.vanished}")
    print(f"  Errors:   {backup_result.errors}")

    if backup_result.vanished > 0:
        print()
        print("Files that vanished during backup:")
        for vanished_path in backup_result.vanished_paths:
            print(f"  {vanished_path}")

    if backup_result.errors > 0:
        print()
        print("Files with errors:")
        for error_path in backup_result.error_paths:
            print(f"  {error_path}")
        sys.exit(2)


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def _build_argument_parser() -> argparse.ArgumentParser:
    """Construct and return the top-level argument parser with all subcommands.

    Returns:
        A fully configured argparse.ArgumentParser instance.
    """
    root_parser = argparse.ArgumentParser(
        prog="gdrive",
        description="Incremental backup of local files to Google Drive via OAuth 2.0.",
    )

    root_parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {_VERSION}",
        help="Show version and exit.",
    )
    root_parser.add_argument(
        "--config",
        metavar="PATH",
        default=None,
        help="Override the default configuration file path.",
    )
    root_parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Preview what would change without uploading files or writing to the database.",
    )
    root_parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        default=False,
        help="Enable debug-level log output.",
    )
    root_parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Clear all cached state and re-upload all files from scratch.",
    )
    root_parser.add_argument(
        "--prune",
        action="store_true",
        default=False,
        help="Delete Drive files whose local paths match any configured exclude_pattern.",
    )
    root_parser.add_argument(
        "--save-config",
        metavar="PATH",
        default=None,
        help="Write a default example configuration file to PATH and exit.",
    )

    subparsers = root_parser.add_subparsers(dest="subcommand", metavar="<command>")

    subparsers.add_parser(
        "init",
        help="Create the database and data directory for first use.",
    )
    subparsers.add_parser(
        "config",
        help="Validate and display the current YAML configuration.",
    )
    subparsers.add_parser(
        "auth",
        help="Run the OAuth 2.0 browser consent flow.",
    )
    subparsers.add_parser(
        "status",
        help="Show counts of backed-up, updated, skipped, and failed files.",
    )

    return root_parser


# ---------------------------------------------------------------------------
# Command dispatch table
# ---------------------------------------------------------------------------

_COMMAND_HANDLERS: dict[str, Callable[[argparse.Namespace], None]] = {
    "init": cmd_init,
    "config": cmd_config,
    "auth": cmd_auth,
    "status": cmd_status,
}


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Parse arguments and dispatch to the appropriate command handler."""
    load_dotenv()

    argument_parser = _build_argument_parser()
    args = argument_parser.parse_args()

    _setup_logging(args.verbose)

    if args.save_config:
        _handle_save_config(args.save_config)
        return

    if args.subcommand is None:
        # No subcommand → run backup by default
        _run_command(cmd_backup, args)
        return

    handler = _COMMAND_HANDLERS.get(args.subcommand)
    if handler is None:
        argument_parser.print_help()
        sys.exit(1)

    _run_command(handler, args)


def _handle_save_config(destination_path_str: str) -> None:
    """Write the example configuration template to the specified path and exit.

    Args:
        destination_path_str: String path where the config should be written.
    """
    destination_path = Path(destination_path_str)
    example_config_content = """\
# GDrive Tool — example configuration
# Copy to src/config/gdrive-configuration.yaml and edit before first use.
#
# The OAuth token is stored as a plain JSON file at `auth.token_file`.
# gdrive does not use the macOS keychain and does not share a token with
# the gmail or gcal tools — auth.token_file is required.

auth:
  credentials_file: "src/config/gdrive/credentials.json"
  token_file: "src/config/gdrive/token.json"
  scopes:
    - "https://www.googleapis.com/auth/drive.file"

backup:
  source_dir: "/path/to/your/documents"
  drive_folder_id: ""  # Required: ID of the root backup folder on Drive

api_rate_limit_rpm: 100

retry:
  max_attempts: 3
  base_delay_seconds: 2.0
"""
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with destination_path.open("xb") as destination_file:
            destination_file.write(example_config_content.encode())
    except FileExistsError:
        print(f"ERROR: File already exists at {destination_path}.", file=sys.stderr)
        sys.exit(1)
    print(f"Example configuration written to: {destination_path}")


def _run_command(handler: Callable[[argparse.Namespace], None], args: argparse.Namespace) -> None:
    """Run a command handler with consistent error catching and exit codes.

    Args:
        handler: A callable accepting an argparse.Namespace.
        args: The parsed argument namespace to pass to the handler.
    """
    try:
        handler(args)
    except HttpError as http_error:
        status_code = http_error.resp.status if http_error.resp else "unknown"
        print(
            f"ERROR: Google Drive API returned HTTP {status_code} — {http_error}",
            file=sys.stderr,
        )
        logger.debug("Full traceback:", exc_info=True)
        sys.exit(1)
    except FileNotFoundError as missing_file_error:
        print(f"ERROR: File not found — {missing_file_error}", file=sys.stderr)
        sys.exit(1)
    except OSError as os_error:
        print(f"ERROR: {os_error}", file=sys.stderr)
        sys.exit(1)
    except ValueError as value_error:
        print(f"ERROR: {value_error}", file=sys.stderr)
        sys.exit(1)
    except google.auth.exceptions.RefreshError:
        print(
            "ERROR: Your authentication token has expired or is invalid. Run `gdrive auth` to re-authorize.",
            file=sys.stderr,
        )
        sys.exit(1)
    except SystemExit:
        raise
    except Exception as unexpected_error:
        print(f"ERROR: An unexpected error occurred — {unexpected_error}", file=sys.stderr)
        logger.debug("Full traceback:", exc_info=True)
        sys.exit(1)
