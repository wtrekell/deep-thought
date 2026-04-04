"""CLI entry point for the Reddit Tool.

Provides the `reddit` command with subcommands for configuration management
and directory initialisation. The default operation (no subcommand) collects
posts according to the configured rules.

Usage:
    reddit [--dry-run] [--verbose] [--config PATH] [--rule NAME] [--output PATH]
    reddit config
    reddit init
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Callable  # noqa: TC003
from pathlib import Path

from dotenv import load_dotenv

from deep_thought.reddit.client import RedditClient
from deep_thought.reddit.config import (
    RedditConfig,
    get_bundled_config_path,
    get_credentials,
    get_default_config_path,
    load_config,
    validate_config,
)
from deep_thought.reddit.db.schema import get_database_path, initialize_database
from deep_thought.reddit.processor import CollectionResult, run_collection

logger = logging.getLogger(__name__)


def _get_version() -> str:
    """Return the installed package version, with a fallback for development installs.

    Returns:
        The version string from package metadata, or "0.1.0" if not found.
    """
    try:
        from importlib.metadata import version  # noqa: PLC0415

        return version("deep-thought")
    except Exception:
        return "0.1.0"


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


def _load_config_from_args(args: argparse.Namespace) -> RedditConfig:
    """Load and return the Reddit configuration, honouring any --config override in args.

    Args:
        args: Parsed argparse namespace which may contain a 'config' attribute.

    Returns:
        A fully parsed RedditConfig.

    Raises:
        FileNotFoundError: If the config file does not exist at the resolved path.
    """
    config_path: Path | None = Path(args.config) if args.config else None
    return load_config(config_path)


def _make_client_from_config(config: RedditConfig) -> RedditClient:
    """Instantiate a RedditClient using credentials from environment variables.

    Args:
        config: A loaded RedditConfig specifying which env vars hold the credentials.

    Returns:
        A fully initialised RedditClient.

    Raises:
        OSError: If any required credential environment variable is not set.
    """
    client_id, client_secret, user_agent = get_credentials(config)
    return RedditClient(client_id=client_id, client_secret=client_secret, user_agent=user_agent)


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------


def cmd_init(args: argparse.Namespace) -> None:
    """Bootstrap the Reddit tool for first use in the calling repo.

    Copies the bundled default config template from the package to
    ``src/config/reddit-configuration.yaml`` (relative to cwd), creates
    the database and required data directories, and prints a summary.

    Never attempts to load the project-level config — it does not exist yet.

    Creates:
    - ``src/config/reddit-configuration.yaml`` (skipped if already present)
    - The SQLite database at <data_dir>/reddit.db
    - <data_dir>/snapshots/ for raw JSON backups per collection run
    - <data_dir>/export/ for generated markdown files

    <data_dir> defaults to data/reddit/ at the project root but can be
    overridden by setting the DEEP_THOUGHT_DATA_DIR environment variable.

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

    data_root = Path(os.environ.get("DEEP_THOUGHT_DATA_DIR", "data"))
    data_dir = data_root / "reddit"

    database_path = get_database_path()
    connection = initialize_database(database_path)
    connection.close()
    logger.debug("Database initialised at: %s", database_path)
    created_items.append(f"  Database: {database_path}")

    snapshots_directory = data_dir / "snapshots"
    export_directory = data_dir / "export"

    snapshots_directory.mkdir(parents=True, exist_ok=True)
    created_items.append(f"  Snapshots: {snapshots_directory}")

    export_directory.mkdir(parents=True, exist_ok=True)
    created_items.append(f"  Export: {export_directory}")

    print("Reddit Tool initialised successfully.")
    print()
    for item in created_items:
        print(item)
    print()
    print("Next steps:")
    print(f"  1. Edit the configuration file:  {project_config}")
    print("  2. Add your Reddit API credentials to a .env file at the project root:")
    print("       REDDIT_CLIENT_ID=your_client_id_here")
    print("       REDDIT_CLIENT_SECRET=your_client_secret_here")
    print("       REDDIT_USER_AGENT=your_user_agent_here")
    print("  3. Run `reddit` to start collecting posts.")


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
    print(f"  client_id_env:       {config.client_id_env}")
    print(f"  client_secret_env:   {config.client_secret_env}")
    print(f"  user_agent_env:      {config.user_agent_env}")
    print(f"  max_posts_per_run:   {config.max_posts_per_run}")
    print(f"  output_dir:          {config.output_dir}")
    print()
    print(f"  rules ({len(config.rules)} configured):")
    for rule in config.rules:
        print(f"    - {rule.name}: r/{rule.subreddit} ({rule.sort}, limit={rule.limit})")


def cmd_collect(args: argparse.Namespace) -> None:
    """Collect posts from Reddit according to the configured rules.

    Fetches submissions, applies filters, generates markdown files, and
    updates the local database. Supports incremental updates — posts with
    new comments are re-fetched and their files regenerated.

    Args:
        args: Parsed argparse namespace with global flags and collect-specific flags.
    """
    config = _load_config_from_args(args)

    validation_issues = validate_config(config)
    if validation_issues:
        for issue_message in validation_issues:
            print(f"ERROR: {issue_message}", file=sys.stderr)
        sys.exit(1)

    reddit_client = _make_client_from_config(config)

    output_override: Path | None = Path(args.output) if args.output else None

    embedding_model = None
    embedding_qdrant_client = None
    if not args.dry_run:
        try:
            from deep_thought.embeddings import create_embedding_model, create_qdrant_client  # noqa: PLC0415

            embedding_model = create_embedding_model()
            embedding_qdrant_client = create_qdrant_client()
        except Exception as init_err:
            logger.error("Embedding infrastructure unavailable, continuing without embeddings: %s", init_err)

    connection = initialize_database()
    try:
        collection_result: CollectionResult = run_collection(
            reddit_client=reddit_client,
            config=config,
            db_conn=connection,
            dry_run=args.dry_run,
            force=args.force,
            rule_name_filter=args.rule,
            output_override=output_override,
            embedding_model=embedding_model,
            embedding_qdrant_client=embedding_qdrant_client,
        )
        connection.commit()
    finally:
        connection.close()

    dry_run_prefix = "[dry-run] " if args.dry_run else ""
    print(f"{dry_run_prefix}Collection complete:")
    print(f"  Collected: {collection_result.posts_collected}")
    print(f"  Updated:   {collection_result.posts_updated}")
    print(f"  Skipped:   {collection_result.posts_skipped}")
    print(f"  Errored:   {collection_result.posts_errored}")

    if collection_result.errors:
        print(f"  Errors ({len(collection_result.errors)}):")
        for error_message in collection_result.errors:
            print(f"    - {error_message}")

    # Exit with code 2 if there were partial failures
    if collection_result.posts_errored > 0 and collection_result.posts_collected + collection_result.posts_updated > 0:
        sys.exit(2)
    elif collection_result.posts_errored > 0:
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
        prog="reddit",
        description="Collect Reddit posts and comments into structured markdown files.",
    )

    # Global flags — available on every subcommand and the default collect mode
    root_parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {_get_version()}",
        help="Show version and exit.",
    )
    root_parser.add_argument(
        "--config",
        metavar="PATH",
        default=None,
        help="Override the default configuration file path.",
    )
    root_parser.add_argument(
        "--rule",
        metavar="NAME",
        default=None,
        help="Run only the named rule (default: all rules).",
    )
    root_parser.add_argument(
        "--output",
        metavar="PATH",
        default=None,
        help="Override the output directory from configuration.",
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
        help="Clear per-post state and reprocess all matching posts.",
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

    return root_parser


# ---------------------------------------------------------------------------
# Command dispatch table
# ---------------------------------------------------------------------------

_COMMAND_HANDLERS = {
    "init": cmd_init,
    "config": cmd_config,
}


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Parse arguments and dispatch to the appropriate command handler.

    When no subcommand is given and the --save-config flag is not set,
    the default collect operation runs. All handlers are wrapped in
    consistent error handling so failures exit with a clear message.
    """
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
    source_path = get_bundled_config_path()

    if not source_path.exists():
        print(f"ERROR: Default config template not found at {source_path}.", file=sys.stderr)
        sys.exit(1)

    if destination_path.exists():
        print(f"ERROR: File already exists at {destination_path}. Remove it manually to regenerate.", file=sys.stderr)
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
        # Covers EnvironmentError / missing credentials
        print(f"ERROR: {os_error}", file=sys.stderr)
        sys.exit(1)
    except ValueError as value_error:
        print(f"ERROR: {value_error}", file=sys.stderr)
        sys.exit(1)
    except Exception as unexpected_error:
        print(f"ERROR: An unexpected error occurred — {unexpected_error}", file=sys.stderr)
        logger.debug("Full traceback:", exc_info=True)
        sys.exit(1)
