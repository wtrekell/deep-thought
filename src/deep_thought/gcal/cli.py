"""CLI entry point for the GCal Tool.

Provides the `gcal` command with subcommands for configuration management,
OAuth authentication, pulling events, creating events, updating events,
and deleting events. The default operation (no subcommand) pulls events
from all configured calendars.

Usage:
    gcal [--dry-run] [--verbose] [--config PATH] [--output PATH]
    gcal init
    gcal config
    gcal auth
    gcal pull
    gcal create event.md
    gcal update event.md
    gcal delete <event_id> [--calendar-id <id>]
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Callable  # noqa: TC003
from pathlib import Path
from typing import TYPE_CHECKING

from dotenv import load_dotenv

from deep_thought.gcal.config import (
    GcalConfig,
    get_bundled_config_path,
    get_default_config_path,
    load_config,
    validate_config,
)
from deep_thought.gcal.db.schema import get_database_path, initialize_database

if TYPE_CHECKING:
    from deep_thought.gcal.client import GcalClient
    from deep_thought.gcal.models import CreateResult, PullResult, UpdateResult

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


def _load_config_from_args(args: argparse.Namespace) -> GcalConfig:
    """Load and return the GCal configuration, honouring any CLI overrides.

    Loads the config file (from --config if given, otherwise the default path)
    then applies any flag-level overrides for output directory, calendar list,
    lookback days, and lookahead days.

    Args:
        args: Parsed argparse namespace which may contain override attributes.

    Returns:
        A fully parsed and overridden GcalConfig.
    """
    config_path: Path | None = Path(args.config) if args.config else None
    config = load_config(config_path)

    if args.output:
        config.output_dir = args.output

    if args.calendar:
        config.calendars = [calendar_id.strip() for calendar_id in args.calendar.split(",") if calendar_id.strip()]

    if args.days_back is not None:
        if args.days_back < 0:
            print("ERROR: --days-back must be >= 0.", file=sys.stderr)
            sys.exit(1)
        config.lookback_days = args.days_back

    if args.days_ahead is not None:
        if args.days_ahead < 0:
            print("ERROR: --days-ahead must be >= 0.", file=sys.stderr)
            sys.exit(1)
        config.lookahead_days = args.days_ahead

    return config


def _make_client_from_config(config: GcalConfig) -> GcalClient:
    """Instantiate and authenticate a GcalClient using config settings.

    Args:
        config: A loaded GcalConfig.

    Returns:
        An authenticated GcalClient ready for API calls.
    """
    from deep_thought.gcal.client import GcalClient

    client = GcalClient(
        credentials_path=config.credentials_path,
        token_path=config.token_path,
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
    """Bootstrap the GCal tool for first use in the calling repo.

    Copies the bundled default config template from the package to
    ``src/config/gcal-configuration.yaml`` (relative to cwd), creates the
    data directory and subdirectories, initialises the database, and prints
    a summary of what was created.

    Never attempts to load the project-level config — it does not exist yet.

    Args:
        args: Parsed argparse namespace.
    """
    import os
    import shutil

    bundled_config = get_bundled_config_path()
    project_config = get_default_config_path()
    data_root = Path(os.environ.get("DEEP_THOUGHT_DATA_DIR", "data"))
    data_dir = data_root / "gcal"
    output_dir = Path(args.output) if args.output else data_dir / "export"

    if not bundled_config.exists():
        print(f"ERROR: Bundled config template not found at {bundled_config}.", file=sys.stderr)
        sys.exit(1)

    created_items: list[str] = []

    if project_config.exists():
        print(f"  Configuration file already exists: {project_config}")
    else:
        project_config.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(bundled_config, project_config)
        created_items.append(f"  Configuration file: {project_config}")

    database_path = get_database_path()
    connection = initialize_database(database_path)
    connection.close()
    logger.debug("Database initialised at: %s", database_path)
    created_items.append(f"  Database: {database_path}")

    snapshots_directory = data_dir / "snapshots"
    input_directory = data_dir / "input"

    snapshots_directory.mkdir(parents=True, exist_ok=True)
    created_items.append(f"  Snapshots directory: {snapshots_directory}")

    output_dir.mkdir(parents=True, exist_ok=True)
    created_items.append(f"  Export directory: {output_dir}")

    input_directory.mkdir(parents=True, exist_ok=True)
    created_items.append(f"  Input directory: {input_directory}")

    print("GCal Tool initialised successfully.")
    print()
    for created_item in created_items:
        print(created_item)
    print()
    print("Next steps:")
    print(f"  1. Edit the configuration file: {project_config}")
    print("  2. Place credentials.json at the path set in the config.")
    print("  3. Run `gcal auth` to authenticate with Google.")
    print("  4. Run `gcal` to start pulling calendar events.")


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
    print(f"  credentials_path:        {config.credentials_path}")
    print(f"  token_path:              {config.token_path}")
    print(f"  scopes:                  {config.scopes}")
    print(f"  api_rate_limit_rpm:      {config.api_rate_limit_rpm}")
    print(f"  retry_max_attempts:      {config.retry_max_attempts}")
    print(f"  retry_base_delay_seconds:{config.retry_base_delay_seconds}")
    print(f"  calendars:               {config.calendars}")
    print(f"  lookback_days:           {config.lookback_days}")
    print(f"  lookahead_days:          {config.lookahead_days}")
    print(f"  include_cancelled:       {config.include_cancelled}")
    print(f"  single_events:           {config.single_events}")
    print(f"  output_dir:              {config.output_dir}")
    print(f"  generate_llms_files:     {config.generate_llms_files}")
    print(f"  flat_output:             {config.flat_output}")


def cmd_auth(args: argparse.Namespace) -> None:
    """Run the OAuth 2.0 Desktop app flow.

    Args:
        args: Parsed argparse namespace.
    """
    config = _load_config_from_args(args)
    _make_client_from_config(config)
    print("Authentication successful. Token saved.")


def cmd_pull(args: argparse.Namespace) -> None:
    """Pull events from all configured calendars and export to markdown.

    Args:
        args: Parsed argparse namespace with global flags.
    """
    from deep_thought.gcal.pull import run_pull

    config = _load_config_from_args(args)
    gcal_client = _make_client_from_config(config)

    calendar_override: list[str] | None = None
    if args.calendar:
        calendar_override = [calendar_id.strip() for calendar_id in args.calendar.split(",")]

    output_override: str | None = args.output if args.output else None

    connection = initialize_database()
    try:
        pull_result: PullResult = run_pull(
            client=gcal_client,
            config=config,
            db_conn=connection,
            dry_run=args.dry_run,
            force=args.force,
            calendar_override=calendar_override,
            output_override=output_override,
        )
        connection.commit()
    finally:
        connection.close()

    dry_run_prefix = "[dry-run] " if args.dry_run else ""
    print(f"{dry_run_prefix}Pull complete:")
    print(f"  Calendars synced: {pull_result.calendars_synced}")
    print(f"  Created:          {pull_result.created}")
    print(f"  Updated:          {pull_result.updated}")
    print(f"  Cancelled:        {pull_result.cancelled}")
    print(f"  Unchanged:        {pull_result.unchanged}")


def cmd_create(args: argparse.Namespace) -> None:
    """Create a new Google Calendar event from a markdown file.

    Args:
        args: Parsed argparse namespace with file_path positional argument.
    """
    from deep_thought.gcal.create import run_create

    if not args.file_path:
        print("ERROR: file_path argument is required for the create command.", file=sys.stderr)
        sys.exit(1)

    event_file_path = Path(args.file_path)
    if not event_file_path.exists():
        print(f"ERROR: File not found — {event_file_path}", file=sys.stderr)
        sys.exit(1)

    config = _load_config_from_args(args)
    gcal_client = _make_client_from_config(config)

    output_override: Path | None = Path(args.output) if args.output else None

    connection = initialize_database()
    try:
        create_result: CreateResult = run_create(
            client=gcal_client,
            config=config,
            db_conn=connection,
            file_path=event_file_path,
            dry_run=args.dry_run,
            output_dir=output_override,
        )
        connection.commit()
    finally:
        connection.close()

    print("Event created successfully.")
    print(f"  Event ID:  {create_result.event_id}")
    print(f"  Link:      {create_result.html_link}")


def cmd_update(args: argparse.Namespace) -> None:
    """Update an existing Google Calendar event from a markdown file.

    Args:
        args: Parsed argparse namespace with file_path positional argument.
    """
    from deep_thought.gcal.update import run_update

    if not args.file_path:
        print("ERROR: file_path argument is required for the update command.", file=sys.stderr)
        sys.exit(1)

    event_file_path = Path(args.file_path)
    if not event_file_path.exists():
        print(f"ERROR: File not found — {event_file_path}", file=sys.stderr)
        sys.exit(1)

    config = _load_config_from_args(args)
    gcal_client = _make_client_from_config(config)

    output_override: Path | None = Path(args.output) if args.output else None

    connection = initialize_database()
    try:
        update_result: UpdateResult = run_update(
            client=gcal_client,
            config=config,
            db_conn=connection,
            file_path=event_file_path,
            dry_run=args.dry_run,
            output_dir=output_override,
        )
        connection.commit()
    finally:
        connection.close()

    print("Event updated successfully.")
    print(f"  Event ID:      {update_result.event_id}")
    print(f"  Link:          {update_result.html_link}")
    if update_result.fields_changed:
        print(f"  Fields changed: {', '.join(update_result.fields_changed)}")
    else:
        print("  No fields changed.")


def cmd_delete(args: argparse.Namespace) -> None:
    """Delete a Google Calendar event by ID and remove its local export file.

    Args:
        args: Parsed argparse namespace with event_id positional and optional
              calendar_id flag.
    """
    from deep_thought.gcal.db.queries import delete_event, get_calendar, get_event
    from deep_thought.gcal.models import DeleteResult
    from deep_thought.gcal.output import delete_event_file

    event_id: str = args.event_id
    calendar_id: str = args.calendar_id

    config = _load_config_from_args(args)
    gcal_client = _make_client_from_config(config)

    connection = initialize_database()
    try:
        # Delete from Google Calendar API
        gcal_client.delete_event(calendar_id, event_id)

        # Look up the local event record before deleting it so we can remove the file
        local_event_record = get_event(connection, event_id, calendar_id)

        # Look up calendar name for file path resolution
        calendar_record = get_calendar(connection, calendar_id)
        calendar_display_name = calendar_record["summary"] if calendar_record else calendar_id

        if local_event_record is not None:
            from deep_thought.gcal.models import EventLocal

            # Reconstruct an EventLocal for the file deletion helper
            local_event = EventLocal(
                event_id=local_event_record["event_id"],
                calendar_id=local_event_record["calendar_id"],
                summary=local_event_record["summary"],
                description=local_event_record.get("description"),
                location=local_event_record.get("location"),
                start_time=local_event_record["start_time"],
                end_time=local_event_record["end_time"],
                all_day=bool(local_event_record["all_day"]),
                status=local_event_record["status"],
                organizer=local_event_record.get("organizer"),
                attendees=local_event_record.get("attendees"),
                recurrence=local_event_record.get("recurrence"),
                html_link=local_event_record.get("html_link"),
                created_at=local_event_record["created_at"],
                updated_at=local_event_record["updated_at"],
                synced_at=local_event_record["synced_at"],
            )
            output_directory = Path(config.output_dir)
            delete_event_file(
                output_dir=output_directory,
                calendar_name=calendar_display_name,
                event=local_event,
                flat_output=config.flat_output,
            )

        delete_event(connection, event_id, calendar_id)
        connection.commit()
    finally:
        connection.close()

    delete_result = DeleteResult(event_id=event_id, calendar_id=calendar_id)
    print("Event deleted successfully.")
    print(f"  Event ID:    {delete_result.event_id}")
    print(f"  Calendar ID: {delete_result.calendar_id}")


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def _build_argument_parser() -> argparse.ArgumentParser:
    """Construct and return the top-level argument parser with all subcommands.

    Returns:
        A fully configured argparse.ArgumentParser instance.
    """
    root_parser = argparse.ArgumentParser(
        prog="gcal",
        description="Pull, create, update, and delete Google Calendar events via OAuth 2.0.",
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
        "--calendar",
        metavar="ID",
        default=None,
        help="Comma-separated list of calendar IDs to target (default: all configured).",
    )
    root_parser.add_argument(
        "--days-back",
        metavar="INT",
        type=int,
        default=None,
        dest="days_back",
        help="Number of days back to include when pulling events.",
    )
    root_parser.add_argument(
        "--days-ahead",
        metavar="INT",
        type=int,
        default=None,
        dest="days_ahead",
        help="Number of days ahead to include when pulling events.",
    )
    root_parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Preview what would change without writing any files or calling the API.",
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
        help="Clear sync state and re-pull all events from scratch.",
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
    subparsers.add_parser(
        "pull",
        help="Pull events from configured calendars and export to markdown.",
    )

    create_parser = subparsers.add_parser(
        "create",
        help="Create a new calendar event from a markdown file.",
    )
    create_parser.add_argument(
        "file_path",
        nargs="?",
        default=None,
        help="Path to the markdown file describing the event to create.",
    )

    update_parser = subparsers.add_parser(
        "update",
        help="Update an existing calendar event from a markdown file.",
    )
    update_parser.add_argument(
        "file_path",
        nargs="?",
        default=None,
        help="Path to the markdown file describing the event to update.",
    )

    delete_parser = subparsers.add_parser(
        "delete",
        help="Delete a calendar event by ID.",
    )
    delete_parser.add_argument(
        "event_id",
        help="The Google Calendar event ID to delete.",
    )
    delete_parser.add_argument(
        "--calendar-id",
        metavar="ID",
        default="primary",
        dest="calendar_id",
        help="The calendar containing the event (default: primary).",
    )

    return root_parser


# ---------------------------------------------------------------------------
# Command dispatch table
# ---------------------------------------------------------------------------

_COMMAND_HANDLERS: dict[str, Callable[[argparse.Namespace], None]] = {
    "init": cmd_init,
    "config": cmd_config,
    "auth": cmd_auth,
    "pull": cmd_pull,
    "create": cmd_create,
    "update": cmd_update,
    "delete": cmd_delete,
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
        # No subcommand → default pull operation
        if len(sys.argv) == 1:
            argument_parser.print_help()
            sys.exit(0)
        _run_command(cmd_pull, args)
        return

    handler = _COMMAND_HANDLERS.get(args.subcommand)
    if handler is None:
        argument_parser.print_help()
        sys.exit(1)

    _run_command(handler, args)


def _handle_save_config(destination_path_str: str) -> None:
    """Write the bundled default configuration template to the specified path and exit.

    Args:
        destination_path_str: String path where the default config should be written.
    """
    destination_path = Path(destination_path_str)
    source_path = get_bundled_config_path()

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
