"""CLI entry point for the Gmail Tool.

Provides the `gmail` command with subcommands for configuration management,
OAuth authentication, sending, and directory initialisation. The default
operation (no subcommand) collects emails according to the configured rules.

Usage:
    gmail [--dry-run] [--verbose] [--config PATH] [--output PATH] [--max-emails INT]
    gmail config
    gmail init
    gmail auth
    gmail send message.md
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Callable  # noqa: TC003
from pathlib import Path
from typing import TYPE_CHECKING

from dotenv import load_dotenv

from deep_thought.gmail.config import (
    GmailConfig,
    get_default_config_path,
    get_gemini_api_key,
    load_config,
    validate_config,
)
from deep_thought.gmail.db.schema import get_database_path, initialize_database

if TYPE_CHECKING:
    from deep_thought.gmail.client import GmailClient
    from deep_thought.gmail.models import CollectResult

logger = logging.getLogger(__name__)

_VERSION = "0.1.0"

# ---------------------------------------------------------------------------
# Helpers shared across command handlers
# ---------------------------------------------------------------------------


def _setup_logging(verbose: bool) -> None:
    """Configure the root logger based on the verbosity flag.

    Args:
        verbose: If True, set log level to DEBUG; otherwise INFO.
    """
    log_level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(format="%(levelname)s: %(message)s")
    logging.getLogger().setLevel(log_level)


def _load_config_from_args(args: argparse.Namespace) -> GmailConfig:
    """Load and return the Gmail configuration, honouring any --config override.

    Args:
        args: Parsed argparse namespace which may contain a 'config' attribute.

    Returns:
        A fully parsed GmailConfig.
    """
    config_path: Path | None = Path(args.config) if args.config else None
    return load_config(config_path)


def _make_client_from_config(config: GmailConfig) -> GmailClient:
    """Instantiate and authenticate a GmailClient using config settings.

    Args:
        config: A loaded GmailConfig.

    Returns:
        An authenticated GmailClient ready for API calls.
    """
    from deep_thought.gmail.client import GmailClient

    client = GmailClient(
        credentials_path=config.credentials_path,
        token_path=config.token_path,
        scopes=config.scopes,
        rate_limit_rpm=config.gmail_rate_limit_rpm,
        retry_max_attempts=config.retry_max_attempts,
        retry_base_delay=config.retry_base_delay_seconds,
    )
    client.authenticate()
    return client


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------


def cmd_init(args: argparse.Namespace) -> None:
    """Create the database, required directories, and print setup instructions.

    Args:
        args: Parsed argparse namespace.
    """
    database_path = get_database_path()
    connection = initialize_database(database_path)
    connection.close()
    logger.debug("Database initialised at: %s", database_path)

    data_dir = database_path.parent
    snapshots_directory = data_dir / "snapshots"
    export_directory = data_dir / "export"
    input_directory = data_dir / "input"

    snapshots_directory.mkdir(parents=True, exist_ok=True)
    export_directory.mkdir(parents=True, exist_ok=True)
    input_directory.mkdir(parents=True, exist_ok=True)

    default_config_path = get_default_config_path()

    config = _load_config_from_args(args)
    credentials_path = Path(config.credentials_path)

    print("Gmail Tool initialised successfully.")
    print()
    print(f"  Database:  {database_path}")
    print(f"  Snapshots: {snapshots_directory}")
    print(f"  Export:    {export_directory}")
    print(f"  Input:     {input_directory}")
    print()

    if credentials_path.exists():
        print(f"  Credentials found at: {credentials_path}")
    else:
        print(f"  WARNING: Credentials NOT found at: {credentials_path}")
        print("  Download credentials.json from Google Cloud Console into that path.")

    print()
    print("Next steps:")
    print(f"  1. Edit the configuration file:  {default_config_path}")
    print("  2. Ensure credentials.json is in place (see above).")
    print("  3. Run `gmail auth` to authenticate with Google.")
    print("  4. Run `gmail` to start collecting emails.")


def cmd_config(args: argparse.Namespace) -> None:
    """Load the configuration file, validate it, and print all settings.

    Args:
        args: Parsed argparse namespace.
    """
    config = _load_config_from_args(args)

    validation_issues = validate_config(config)
    if validation_issues:
        print(f"Configuration issues ({len(validation_issues)} found):")
        for issue in validation_issues:
            print(f"  WARNING: {issue}")
        print()
    else:
        print("Configuration is valid.")
        print()

    print("Loaded configuration:")
    print(f"  credentials_path:     {config.credentials_path}")
    print(f"  token_path:           {config.token_path}")
    print(f"  scopes:               {config.scopes}")
    print(f"  gemini_model:         {config.gemini_model}")
    print(f"  gmail_rate_limit_rpm: {config.gmail_rate_limit_rpm}")
    print(f"  max_emails_per_run:   {config.max_emails_per_run}")
    print(f"  clean_newsletters:    {config.clean_newsletters}")
    print(f"  output_dir:           {config.output_dir}")
    print(f"  generate_llms_files:  {config.generate_llms_files}")
    print()
    print(f"  rules ({len(config.rules)} configured):")
    for rule in config.rules:
        ai_status = "AI" if rule.ai_instructions else "no AI"
        print(f"    - {rule.name}: {rule.query} ({ai_status}, {len(rule.actions)} actions)")


def cmd_auth(args: argparse.Namespace) -> None:
    """Run the OAuth 2.0 Desktop app flow.

    Args:
        args: Parsed argparse namespace.
    """
    config = _load_config_from_args(args)
    _make_client_from_config(config)
    print("Authentication successful. Token saved.")


def cmd_send(args: argparse.Namespace) -> None:
    """Send an email from a markdown file with YAML frontmatter.

    Args:
        args: Parsed argparse namespace with message_path.
    """
    from deep_thought.gmail.processor import run_send

    config = _load_config_from_args(args)
    gmail_client = _make_client_from_config(config)

    if not args.message_path:
        print("ERROR: message_path argument is required for the send command.", file=sys.stderr)
        sys.exit(1)

    message_path = Path(args.message_path)
    result = run_send(gmail_client, message_path)

    print("Email sent successfully.")
    print(f"  Message ID: {result.message_id}")
    print(f"  Thread ID:  {result.thread_id}")


def cmd_collect(args: argparse.Namespace) -> None:
    """Collect emails according to the configured rules.

    Args:
        args: Parsed argparse namespace with global flags.
    """
    from deep_thought.gmail.processor import run_collection

    config = _load_config_from_args(args)
    gmail_client = _make_client_from_config(config)

    output_override: Path | None = Path(args.output) if args.output else None

    # Override max emails if specified
    if args.max_emails is not None:
        if args.max_emails <= 0:
            print("ERROR: --max-emails must be greater than 0.", file=sys.stderr)
            sys.exit(1)
        config.max_emails_per_run = args.max_emails

    connection = initialize_database()
    try:
        # Set up Gemini extractor if any rule uses AI
        extractor = None
        rules_need_ai = any(rule.ai_instructions for rule in config.rules)
        if rules_need_ai:
            try:
                from deep_thought.gmail.extractor import GeminiExtractor

                api_key = get_gemini_api_key(config)
                extractor = GeminiExtractor(
                    api_key=api_key,
                    model=config.gemini_model,
                    rate_limit_rpm=config.gemini_rate_limit_rpm,
                )
            except OSError as gemini_error:
                logger.warning("Gemini extractor not available: %s", gemini_error)
                logger.warning("AI extraction will be skipped for this run.")

        collection_result: CollectResult = run_collection(
            gmail_client=gmail_client,
            config=config,
            db_conn=connection,
            extractor=extractor,
            dry_run=args.dry_run,
            force=args.force,
            rule_name_filter=args.rule if hasattr(args, "rule") and args.rule else None,
            output_override=output_override,
        )
        connection.commit()
    finally:
        connection.close()

    dry_run_prefix = "[dry-run] " if args.dry_run else ""
    print(f"{dry_run_prefix}Collection complete:")
    print(f"  Processed: {collection_result.processed}")
    print(f"  Skipped:   {collection_result.skipped}")
    print(f"  Errored:   {collection_result.errors}")

    if collection_result.actions_taken:
        print("  Actions:")
        for action, count in sorted(collection_result.actions_taken.items()):
            print(f"    {action}: {count}")

    if collection_result.error_messages:
        print(f"  Errors ({len(collection_result.error_messages)}):")
        for error_message in collection_result.error_messages:
            print(f"    - {error_message}")

    # Exit codes per spec
    if collection_result.errors > 0 and collection_result.processed > 0:
        sys.exit(2)
    elif collection_result.errors > 0:
        sys.exit(1)


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def _build_argument_parser() -> argparse.ArgumentParser:
    """Construct and return the top-level argument parser with all subcommands.

    Returns:
        A fully configured argparse.ArgumentParser instance.
    """
    root_parser = argparse.ArgumentParser(
        prog="gmail",
        description="Collect, process, and send email via Gmail using OAuth 2.0.",
    )

    # Global flags
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
        "--output",
        metavar="PATH",
        default=None,
        help="Override the output directory from configuration.",
    )
    root_parser.add_argument(
        "--max-emails",
        metavar="INT",
        type=int,
        default=None,
        help="Max emails to process per run.",
    )
    root_parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Preview what would be collected without writing any files.",
    )
    root_parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        default=False,
        help="Increase log output.",
    )
    root_parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Clear state and reprocess all matching emails.",
    )
    root_parser.add_argument(
        "--rule",
        metavar="NAME",
        default=None,
        help="Run only the named rule (default: all rules).",
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
        help="Create the database, config file, and directory structure.",
    )
    subparsers.add_parser(
        "config",
        help="Validate and display the current YAML configuration.",
    )
    subparsers.add_parser(
        "auth",
        help="Run the OAuth 2.0 Desktop app flow.",
    )

    send_parser = subparsers.add_parser(
        "send",
        help="Send an email composed from a markdown file.",
    )
    send_parser.add_argument(
        "message_path",
        nargs="?",
        default=None,
        help="Path to the markdown file with YAML frontmatter. Defaults to data/gmail/input/.",
    )

    return root_parser


# ---------------------------------------------------------------------------
# Command dispatch table
# ---------------------------------------------------------------------------

_COMMAND_HANDLERS: dict[str, Callable[[argparse.Namespace], None]] = {
    "init": cmd_init,
    "config": cmd_config,
    "auth": cmd_auth,
    "send": cmd_send,
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

    # --save-config generates an example config and exits
    if args.save_config:
        _handle_save_config(args.save_config)
        return

    if args.subcommand is None:
        # No subcommand → default collect operation
        if len(sys.argv) == 1:
            argument_parser.print_help()
            sys.exit(0)
        _run_command(cmd_collect, args)
        return

    handler = _COMMAND_HANDLERS.get(args.subcommand)
    if handler is None:
        argument_parser.print_help()
        sys.exit(1)

    _run_command(handler, args)


def _handle_save_config(destination_path_str: str) -> None:
    """Write a default example configuration to the specified path and exit.

    Args:
        destination_path_str: String path where the default config should be written.
    """
    destination_path = Path(destination_path_str)
    source_path = get_default_config_path()

    if not source_path.exists():
        print(f"ERROR: Default config template not found at {source_path}.", file=sys.stderr)
        sys.exit(1)

    if destination_path.exists():
        print(f"ERROR: File already exists at {destination_path}. Use --force to overwrite.", file=sys.stderr)
        sys.exit(1)

    destination_path.parent.mkdir(parents=True, exist_ok=True)
    destination_path.write_bytes(source_path.read_bytes())
    print(f"Default configuration written to: {destination_path}")


def _run_command(handler: Callable[[argparse.Namespace], None], args: argparse.Namespace) -> None:
    """Run a command handler with consistent error catching and exit codes.

    Args:
        handler: A callable accepting an argparse.Namespace.
        args: The parsed argument namespace to pass to the handler.
    """
    try:
        handler(args)
    except FileNotFoundError as missing_file_error:
        print(f"ERROR: File not found — {missing_file_error}", file=sys.stderr)
        sys.exit(1)
    except OSError as os_error:
        print(f"ERROR: {os_error}", file=sys.stderr)
        sys.exit(1)
    except ValueError as value_error:
        print(f"ERROR: {value_error}", file=sys.stderr)
        sys.exit(1)
    except Exception as unexpected_error:
        print(f"ERROR: An unexpected error occurred — {unexpected_error}", file=sys.stderr)
        logger.debug("Full traceback:", exc_info=True)
        sys.exit(1)
