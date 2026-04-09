"""CLI entry point for the Todoist Tool.

Provides the `todoist` command with subcommands for syncing, inspecting,
exporting, and configuring the tool.

Usage:
    todoist [--dry-run] [--verbose] [--config PATH] [--project NAME] <subcommand>

Subcommands:
    init      — Create DB, config file, and directory structure
    config    — Validate and display current YAML configuration
    pull      — Pull tasks and projects from Todoist API
    push      — Push local changes back to Todoist
    sync      — Run pull then push sequentially
    status    — Show last sync time and pending local changes
    diff      — Show locally modified tasks
    export    — Export current DB state to markdown files
    create    — Create a new task in Todoist
    complete  — Mark a task as completed
    attach    — Upload a local file and attach it to a task as a comment
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

from deep_thought.todoist.attach import AttachResult, attach_file
from deep_thought.todoist.client import TodoistClient
from deep_thought.todoist.config import (
    TodoistConfig,
    get_api_token,
    get_bundled_config_path,
    get_default_config_path,
    load_config,
    validate_config,
)
from deep_thought.todoist.create import CreateResult, create_task
from deep_thought.todoist.db.queries import (
    get_all_projects,
    get_modified_tasks,
    get_sync_value,
    get_task_by_id,
    mark_task_completed,
)
from deep_thought.todoist.db.schema import get_database_path, initialize_database
from deep_thought.todoist.export import ExportResult, export_to_markdown
from deep_thought.todoist.pull import PullResult, pull
from deep_thought.todoist.push import PushResult, push
from deep_thought.todoist.sync import SyncResult, sync

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers shared across command handlers
# ---------------------------------------------------------------------------


def _setup_logging(verbose: bool) -> None:
    """Configure the root logger based on the verbosity flag.

    Uses basicConfig to attach a handler if none exists, then sets the level
    directly on the root logger so the level is always applied even when pytest
    or another framework has already installed a handler.

    Args:
        verbose: If True, set log level to DEBUG; otherwise INFO.
    """
    log_level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(format="%(levelname)s: %(message)s")
    logging.getLogger().setLevel(log_level)


def _load_config_from_args(args: argparse.Namespace) -> TodoistConfig:
    """Load and return config, honouring any --config override in args.

    Args:
        args: Parsed argparse namespace which may contain a 'config' attribute.

    Returns:
        A fully parsed TodoistConfig.

    Raises:
        FileNotFoundError: If the config file does not exist at the resolved path.
    """
    config_path: Path | None = Path(args.config) if args.config else None
    return load_config(config_path)


def _make_client_from_config(config: TodoistConfig) -> TodoistClient:
    """Instantiate a TodoistClient using the API token from the environment.

    Args:
        config: A loaded TodoistConfig containing the env-var name for the token.

    Returns:
        A fully initialised TodoistClient.

    Raises:
        OSError: If the API token environment variable is not set.
    """
    api_token = get_api_token(config)
    return TodoistClient(api_token)


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------


def cmd_init(args: argparse.Namespace) -> None:
    """Bootstrap the Todoist Tool for first use in the calling repo.

    Copies the bundled default config template from the package to
    ``src/config/todoist-configuration.yaml`` (relative to cwd), creates the
    SQLite database, snapshot and export directories, and prints a summary.

    Never attempts to load the project-level config — it does not exist yet.

    Args:
        args: Parsed argparse namespace (no subcommand-specific flags).
    """
    import os
    import shutil

    bundled_config = get_bundled_config_path()
    project_config = get_default_config_path()

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

    snapshots_directory = database_path.parent / "snapshots"
    export_directory = database_path.parent / "export"

    snapshots_directory.mkdir(parents=True, exist_ok=True)
    created_items.append(f"  Snapshots directory: {snapshots_directory}")

    export_directory.mkdir(parents=True, exist_ok=True)
    created_items.append(f"  Export directory: {export_directory}")

    # Honour DEEP_THOUGHT_DATA_DIR override in the summary line
    data_root = Path(os.environ.get("DEEP_THOUGHT_DATA_DIR", "data"))
    _ = data_root  # referenced only for documentation; get_database_path handles it

    print("Todoist Tool initialised successfully.")
    print()
    for item in created_items:
        print(item)
    print()
    print("Next steps:")
    print(f"  1. Edit the configuration file: {project_config}")
    print("  2. Add your Todoist API token to a .env file at the project root:")
    print("       TODOIST_API_TOKEN=your_token_here")
    print("  3. Run `todoist pull` to fetch your tasks.")


def cmd_config(args: argparse.Namespace) -> None:
    """Load the configuration file, validate it, and print all settings.

    Any validation issues are listed before the config values so they are
    immediately visible.

    Args:
        args: Parsed argparse namespace, may contain 'config' path override.
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
    print(f"  api_token_env:          {config.api_token_env}")
    print(f"  projects:               {config.projects or '(none configured)'}")
    print()
    print("  pull_filters:")
    print(f"    labels.include:       {config.pull_filters.labels.include or '(any)'}")
    print(f"    labels.exclude:       {config.pull_filters.labels.exclude or '(none)'}")
    print(f"    sections.include:     {config.pull_filters.sections.include or '(any)'}")
    print(f"    sections.exclude:     {config.pull_filters.sections.exclude or '(none)'}")
    print(f"    assignee.include:     {config.pull_filters.assignee.include or '(any)'}")
    print(f"    has_due_date:         {config.pull_filters.has_due_date!r}")
    print()
    print("  push_filters:")
    print(f"    labels.include:       {config.push_filters.labels.include or '(any)'}")
    print(f"    labels.exclude:       {config.push_filters.labels.exclude or '(none)'}")
    print(f"    assignee.include:     {config.push_filters.assignee.include or '(any)'}")
    print(f"    conflict_resolution:  {config.push_filters.conflict_resolution}")
    print(f"    require_confirmation: {config.push_filters.require_confirmation}")
    print()
    print("  comments:")
    print(f"    sync:                 {config.comments.sync}")
    print(f"    include_attachments:  {config.comments.include_attachments}")
    print()
    print("  claude:")
    print(f"    label:                {config.claude.label or '(not set)'}")
    print(f"    repo:                 {config.claude.repo or '(not set)'}")
    print(f"    branch:               {config.claude.branch}")


def _warn_on_config_issues(config: TodoistConfig) -> None:
    """Run validate_config and print any warnings to stdout.

    This is a non-fatal check. Warnings are printed so the user is aware
    of potential misconfigurations, but the operation continues regardless.

    Args:
        config: The loaded TodoistConfig to validate.
    """
    config_issues = validate_config(config)
    if config_issues:
        for issue in config_issues:
            print(f"WARNING: {issue}")


def cmd_pull(args: argparse.Namespace) -> None:
    """Pull projects and tasks from the Todoist API and store them locally.

    Applies pull filter rules from the configuration, writes to the SQLite
    database, and saves a JSON snapshot for debugging.

    Args:
        args: Parsed argparse namespace with global flags (dry_run, verbose,
              config, project).
    """
    config = _load_config_from_args(args)
    _warn_on_config_issues(config)
    todoist_client = _make_client_from_config(config)

    connection = initialize_database()
    try:
        pull_result: PullResult = pull(
            todoist_client,
            config,
            connection,
            dry_run=args.dry_run,
            verbose=args.verbose,
            project_filter=args.project,
            keep_snapshots=getattr(args, "keep_snapshots", 10),
        )
    finally:
        connection.close()

    dry_run_prefix = "[dry-run] " if args.dry_run else ""
    print(f"{dry_run_prefix}Pull complete:")
    print(f"  Projects:  {pull_result.projects_synced}")
    print(f"  Sections:  {pull_result.sections_synced}")
    print(f"  Tasks:     {pull_result.tasks_synced} synced, {pull_result.tasks_filtered_out} filtered")
    print(f"  Comments:  {pull_result.comments_synced}")
    print(f"  Labels:    {pull_result.labels_synced}")
    if pull_result.snapshot_path:
        print(f"  Snapshot:  {pull_result.snapshot_path}")
    if pull_result.errors:
        print(f"  Errors ({len(pull_result.errors)}):")
        for error_message in pull_result.errors:
            print(f"    - {error_message}")


def cmd_push(args: argparse.Namespace) -> None:
    """Push locally modified tasks back to the Todoist API.

    Finds tasks where local updated_at is newer than synced_at, applies push
    filter rules, optionally prompts for confirmation, then calls the API.

    Args:
        args: Parsed argparse namespace with global flags (dry_run, verbose,
              config, project).
    """
    config = _load_config_from_args(args)
    _warn_on_config_issues(config)
    todoist_client = _make_client_from_config(config)

    connection = initialize_database()
    try:
        push_result: PushResult = push(
            todoist_client,
            config,
            connection,
            dry_run=args.dry_run,
            verbose=args.verbose,
            project_filter=args.project,
        )
    finally:
        connection.close()

    dry_run_prefix = "[dry-run] " if args.dry_run else ""
    print(f"{dry_run_prefix}Push complete:")
    print(f"  Pushed:   {push_result.tasks_pushed}")
    print(f"  Filtered: {push_result.tasks_filtered_out}")
    print(f"  Failed:   {push_result.tasks_failed}")
    if push_result.errors:
        print(f"  Errors ({len(push_result.errors)}):")
        for error_message in push_result.errors:
            print(f"    - {error_message}")


def cmd_sync(args: argparse.Namespace) -> None:
    """Run a full bidirectional sync: pull from Todoist, then push local changes.

    Args:
        args: Parsed argparse namespace with global flags (dry_run, verbose,
              config, project).
    """
    config = _load_config_from_args(args)
    _warn_on_config_issues(config)
    todoist_client = _make_client_from_config(config)

    connection = initialize_database()
    try:
        sync_result: SyncResult = sync(
            todoist_client,
            config,
            connection,
            dry_run=args.dry_run,
            verbose=args.verbose,
            project_filter=args.project,
            keep_snapshots=getattr(args, "keep_snapshots", 10),
        )
    finally:
        connection.close()

    dry_run_prefix = "[dry-run] " if args.dry_run else ""
    pull_result = sync_result.pull_result
    push_result = sync_result.push_result

    print(f"{dry_run_prefix}Sync complete:")
    print("  Pull:")
    print(f"    Projects:  {pull_result.projects_synced}")
    print(f"    Sections:  {pull_result.sections_synced}")
    print(f"    Tasks:     {pull_result.tasks_synced} synced, {pull_result.tasks_filtered_out} filtered")
    print(f"    Comments:  {pull_result.comments_synced}")
    print(f"    Labels:    {pull_result.labels_synced}")
    if pull_result.snapshot_path:
        print(f"    Snapshot:  {pull_result.snapshot_path}")
    print("  Push:")
    print(f"    Pushed:    {push_result.tasks_pushed}")
    print(f"    Filtered:  {push_result.tasks_filtered_out}")
    print(f"    Failed:    {push_result.tasks_failed}")

    all_errors = pull_result.errors + push_result.errors
    if all_errors:
        print(f"  Errors ({len(all_errors)}):")
        for error_message in all_errors:
            print(f"    - {error_message}")


def cmd_status(args: argparse.Namespace) -> None:
    """Display the current sync state: last sync time, modified tasks, projects.

    Reads from the local database only — no API calls are made.

    Args:
        args: Parsed argparse namespace (no subcommand-specific flags).
    """
    connection = initialize_database()
    try:
        last_sync_time = get_sync_value(connection, "last_sync_time")
        schema_version = get_sync_value(connection, "schema_version")
        modified_tasks = get_modified_tasks(connection)
        all_projects = get_all_projects(connection)
    finally:
        connection.close()

    print("Todoist Tool — Status")
    print()
    print(f"  Schema version:    {schema_version or 'unknown'}")
    print(f"  Last sync:         {last_sync_time or 'never'}")
    print(f"  Projects in DB:    {len(all_projects)}")
    print(f"  Modified tasks:    {len(modified_tasks)}")

    if modified_tasks:
        print()
        print("  Tasks with local changes:")
        for task_row in modified_tasks:
            task_id: str = task_row.get("id") or ""
            task_content: str = task_row.get("content") or "(no content)"
            print(f"    - [{task_id}] {task_content}")


def cmd_diff(args: argparse.Namespace) -> None:
    """Show tasks that have been locally modified since the last sync.

    Compares updated_at against synced_at in the database. No API calls
    are made.

    Args:
        args: Parsed argparse namespace (no subcommand-specific flags).
    """
    connection = initialize_database()
    try:
        modified_tasks = get_modified_tasks(connection)
    finally:
        connection.close()

    if not modified_tasks:
        print("No local changes.")
        return

    print(f"Locally modified tasks ({len(modified_tasks)}):")
    print()

    for task_row in modified_tasks:
        task_id: str = task_row.get("id") or ""
        task_content: str = task_row.get("content") or "(no content)"
        updated_at: str = task_row.get("updated_at") or "unknown"
        synced_at: str = task_row.get("synced_at") or "never"
        raw_priority = task_row.get("priority")
        priority: int = raw_priority if raw_priority is not None else 1
        due_date: str | None = task_row.get("due_date")

        print(f"  [{task_id}] {task_content}")
        print(f"    updated_at: {updated_at}")
        print(f"    synced_at:  {synced_at}")
        print(f"    priority:   {priority}")
        if due_date:
            print(f"    due:        {due_date}")
        print()


def cmd_export(args: argparse.Namespace) -> None:
    """Export the current database state to structured markdown files.

    Writes one file per section per project under <data_dir>/export/
    (see DEEP_THOUGHT_DATA_DIR for override).

    Args:
        args: Parsed argparse namespace with global flags (config, verbose,
              project).
    """
    config = _load_config_from_args(args)
    _warn_on_config_issues(config)

    connection = initialize_database()
    try:
        export_result: ExportResult = export_to_markdown(
            connection,
            config,
            project_filter=args.project,
            verbose=args.verbose,
        )
    finally:
        connection.close()

    print("Export complete:")
    print(f"  Projects: {export_result.projects_exported}")
    print(f"  Files:    {export_result.files_written}")
    print(f"  Tasks:    {export_result.tasks_exported}")


def cmd_create(args: argparse.Namespace) -> None:
    """Create a new task in Todoist and write it to the local database immediately.

    Resolves the project (and optionally section and labels) against the local
    database before calling the API. Use --dry-run to verify names resolve
    without making any changes.

    Args:
        args: Parsed argparse namespace with the content positional argument
              and optional task attribute flags.
    """
    if args.project is None:
        print("ERROR: --project is required for the create subcommand.", file=sys.stderr)
        sys.exit(1)

    config = _load_config_from_args(args)
    todoist_client = _make_client_from_config(config)

    connection = initialize_database()
    try:
        create_result: CreateResult = create_task(
            todoist_client,
            connection,
            args.content,
            args.project,
            description=args.description,
            due_string=args.due,
            priority=args.priority,
            label_names=args.label or [],
            section_name=args.section,
            dry_run=args.dry_run,
        )
    finally:
        connection.close()

    if create_result.dry_run:
        print(f"[dry-run] Would create task in '{args.project}': {create_result.task_content}")
    else:
        print(f"Created task [{create_result.task_id}]: {create_result.task_content}")


def cmd_complete(args: argparse.Namespace) -> None:
    """Mark a task as completed in Todoist and update the local database.

    Closes the task via the API first, then records the completion locally.
    Supports --dry-run to preview without making changes.

    Args:
        args: Parsed argparse namespace with the task_id positional argument
              and global flags (dry_run, verbose, config).
    """
    config = _load_config_from_args(args)
    todoist_client = _make_client_from_config(config)

    connection = initialize_database()
    try:
        task_row = get_task_by_id(connection, args.task_id)
        if task_row is None:
            print(f"ERROR: No task found with ID '{args.task_id}'.", file=sys.stderr)
            sys.exit(1)

        task_content: str = task_row.get("content") or "(no content)"

        if args.dry_run:
            print(f"[dry-run] Would complete task [{args.task_id}]: {task_content}")
            return

        todoist_client.close_task(args.task_id)
        mark_task_completed(connection, args.task_id)
        connection.commit()

        print(f"Completed task [{args.task_id}]: {task_content}")
    finally:
        connection.close()


def cmd_attach(args: argparse.Namespace) -> None:
    """Upload a local file to Todoist and attach it to a task as a comment.

    Validates that the task exists in the local database before uploading.
    Use --dry-run to verify the task ID and file path without making any
    API calls.

    Args:
        args: Parsed argparse namespace with task_id and file_path positional
              arguments, and optional --message and global --dry-run flags.
    """
    config = _load_config_from_args(args)
    file_path = Path(args.file_path)

    # Defer token resolution until after dry-run validation so that
    # --dry-run works without a configured API token.
    todoist_client = None if args.dry_run else _make_client_from_config(config)

    connection = initialize_database()
    try:
        attach_result: AttachResult = attach_file(
            todoist_client,
            connection,
            args.task_id,
            file_path,
            message=args.message,
            dry_run=args.dry_run,
        )
    finally:
        connection.close()

    size_kb = round(attach_result.file_size / 1024, 1)
    file_summary = f"'{attach_result.file_name}' ({size_kb} KB)"
    task_summary = f"[{attach_result.task_id}]: {attach_result.task_content}"
    if attach_result.dry_run:
        print(f"[dry-run] Would attach {file_summary} to task {task_summary}")
    else:
        print(f"Attached {file_summary} to task {task_summary}")
        print(f"Comment ID: {attach_result.comment_id}")


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def _build_argument_parser() -> argparse.ArgumentParser:
    """Construct and return the top-level argument parser with all subcommands.

    Returns:
        A fully configured argparse.ArgumentParser instance.
    """
    root_parser = argparse.ArgumentParser(
        prog="todoist",
        description="Bidirectional sync between Todoist and local SQLite/markdown.",
    )

    # Global flags — available on every subcommand
    root_parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Show what would change without writing to Todoist or the local database.",
    )
    root_parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        default=False,
        help="Increase log output.",
    )
    root_parser.add_argument(
        "--config",
        metavar="PATH",
        default=None,
        help="Override the default configuration file path.",
    )
    root_parser.add_argument(
        "--project",
        metavar="NAME",
        default=None,
        help="Limit the operation to a single project by name.",
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
    pull_parser = subparsers.add_parser(
        "pull",
        help="Pull tasks and projects from Todoist, applying filter rules.",
    )
    pull_parser.add_argument(
        "--keep-snapshots",
        metavar="N",
        type=int,
        default=10,
        dest="keep_snapshots",
        help="Number of most-recent snapshot files to keep (default: 10). Pass 0 to keep all.",
    )

    subparsers.add_parser(
        "push",
        help="Push local changes back to Todoist.",
    )

    sync_parser = subparsers.add_parser(
        "sync",
        help="Run pull then push sequentially (full bidirectional sync).",
    )
    sync_parser.add_argument(
        "--keep-snapshots",
        metavar="N",
        type=int,
        default=10,
        dest="keep_snapshots",
        help="Number of most-recent snapshot files to keep (default: 10). Pass 0 to keep all.",
    )
    subparsers.add_parser(
        "status",
        help="Show sync state: last sync time, pending local changes.",
    )
    subparsers.add_parser(
        "diff",
        help="Show differences between the local database and the last pull.",
    )
    subparsers.add_parser(
        "export",
        help="Export current database state to structured markdown files.",
    )

    complete_parser = subparsers.add_parser(
        "complete",
        help="Mark a task as completed in Todoist.",
    )
    complete_parser.add_argument(
        "task_id",
        help="Todoist task ID (shown in export output after 'id:').",
    )

    create_parser = subparsers.add_parser(
        "create",
        help="Create a new task in Todoist and store it locally.",
    )
    create_parser.add_argument(
        "content",
        help="Task content text.",
    )
    create_parser.add_argument(
        "--description",
        default=None,
        help="Optional longer description for the task.",
    )
    create_parser.add_argument(
        "--due",
        metavar="DATE_STRING",
        default=None,
        help="Natural language due date, e.g. 'tomorrow'.",
    )
    create_parser.add_argument(
        "--priority",
        type=int,
        choices=[1, 2, 3, 4],
        default=None,
        help="1=normal, 4=urgent.",
    )
    create_parser.add_argument(
        "--label",
        action="append",
        metavar="LABEL_NAME",
        dest="label",
        default=None,
        help="Repeat for multiple labels.",
    )
    create_parser.add_argument(
        "--section",
        metavar="SECTION_NAME",
        default=None,
        help="Section within the project to place the task in.",
    )

    attach_parser = subparsers.add_parser(
        "attach",
        help="Upload a local file and attach it to a task as a comment.",
    )
    attach_parser.add_argument(
        "task_id",
        help="Todoist task ID to attach the file to (shown in export output after 'id:').",
    )
    attach_parser.add_argument(
        "file_path",
        help="Path to the local file to upload.",
    )
    attach_parser.add_argument(
        "--message",
        metavar="TEXT",
        default="File attachment",
        help="Comment text to accompany the attachment (default: 'File attachment').",
    )

    return root_parser


# ---------------------------------------------------------------------------
# Command dispatch table
# ---------------------------------------------------------------------------

_COMMAND_HANDLERS = {
    "init": cmd_init,
    "config": cmd_config,
    "pull": cmd_pull,
    "push": cmd_push,
    "sync": cmd_sync,
    "status": cmd_status,
    "diff": cmd_diff,
    "export": cmd_export,
    "create": cmd_create,
    "complete": cmd_complete,
    "attach": cmd_attach,
}


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Parse arguments and dispatch to the appropriate command handler.

    Wraps each handler in consistent error handling so that all user-facing
    failures exit with code 1 and a clear message.
    """
    load_dotenv()

    argument_parser = _build_argument_parser()
    args = argument_parser.parse_args()

    _setup_logging(args.verbose)

    if args.subcommand is None:
        argument_parser.print_help()
        sys.exit(0)

    handler = _COMMAND_HANDLERS.get(args.subcommand)
    if handler is None:
        # Should not be reachable because argparse validates subcommand choices,
        # but guard defensively.
        argument_parser.print_help()
        sys.exit(1)

    try:
        handler(args)
    except FileNotFoundError as missing_file_error:
        print(f"ERROR: File not found — {missing_file_error}", file=sys.stderr)
        sys.exit(1)
    except OSError as os_error:
        # Covers EnvironmentError / API token missing
        print(f"ERROR: {os_error}", file=sys.stderr)
        sys.exit(1)
    except ValueError as value_error:
        print(f"ERROR: {value_error}", file=sys.stderr)
        sys.exit(1)
    except Exception as unexpected_error:
        print(f"ERROR: An unexpected error occurred — {unexpected_error}", file=sys.stderr)
        logger.debug("Full traceback:", exc_info=True)
        sys.exit(1)
