"""CLI entry point for the Stack Exchange Tool.

Provides the `stackexchange` command with subcommands for configuration
management and directory initialisation. The default operation (no subcommand)
collects questions according to the configured rules.

Usage:
    stackexchange [--dry-run] [--verbose] [--config PATH] [--rule NAME] [--output PATH]
    stackexchange config
    stackexchange init
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Callable  # noqa: TC003
from pathlib import Path

from dotenv import load_dotenv

from deep_thought.stackexchange.client import StackExchangeClient
from deep_thought.stackexchange.config import (
    StackExchangeConfig,
    get_api_key,
    get_bundled_config_path,
    get_default_config_path,
    load_config,
    validate_config,
)
from deep_thought.stackexchange.db.schema import get_database_path, initialize_database
from deep_thought.stackexchange.processor import CollectionResult, run_collection

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


def _load_config_from_args(args: argparse.Namespace) -> StackExchangeConfig:
    """Load and return the Stack Exchange configuration, honouring any --config override in args.

    Args:
        args: Parsed argparse namespace which may contain a 'config' attribute.

    Returns:
        A fully parsed StackExchangeConfig.

    Raises:
        FileNotFoundError: If the config file does not exist at the resolved path.
    """
    config_path: Path | None = Path(args.config) if args.config is not None else None
    return load_config(config_path)


def _make_client_from_config(config: StackExchangeConfig) -> StackExchangeClient:
    """Instantiate a StackExchangeClient using the API key from config.

    The API key is optional — the Stack Exchange API works without one at a
    reduced quota. If no key is configured, the client still works.

    Args:
        config: A loaded StackExchangeConfig specifying the env var name for the API key.

    Returns:
        A fully initialised StackExchangeClient.
    """
    api_key = get_api_key(config)
    return StackExchangeClient(api_key=api_key)


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------


def cmd_init(args: argparse.Namespace) -> None:
    """Bootstrap the Stack Exchange tool for first use in the calling repo.

    Copies the bundled default config template from the package to
    ``src/config/stackexchange-configuration.yaml`` (relative to cwd), creates
    the database and required data directories, and prints a summary.

    Never attempts to load the project-level config — it does not exist yet.

    Creates:
    - ``src/config/stackexchange-configuration.yaml`` (skipped if already present)
    - The SQLite database at <data_dir>/stackexchange.db
    - <data_dir>/export/ for generated markdown files

    <data_dir> defaults to data/stackexchange/ at the project root but can be
    overridden by setting the DEEP_THOUGHT_DATA_DIR environment variable.

    Args:
        args: Parsed argparse namespace (no subcommand-specific flags).
    """
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

    export_directory = database_path.parent / "export"
    export_directory.mkdir(parents=True, exist_ok=True)
    created_items.append(f"  Export: {export_directory}")

    print("Stack Exchange Tool initialised successfully.")
    print()
    for item_description in created_items:
        print(item_description)
    print()
    print("Next steps:")
    print(f"  1. Edit the configuration file:  {project_config}")
    print("  2. (Optional) Add your Stack Exchange API key to a .env file at the project root:")
    print("       STACKEXCHANGE_API_KEY=your_api_key_here")
    print("     Without a key the API still works at a reduced quota (300 requests/day).")
    print("  3. Run `stackexchange` to start collecting questions.")


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
        for issue_message in validation_issues:
            print(f"  WARNING: {issue_message}")
        print()
    else:
        print("Configuration is valid.")
        print()

    print("Loaded configuration:")
    print(f"  api_key_env:            {config.api_key_env}")
    print(f"  max_questions_per_run:  {config.max_questions_per_run}")
    print(f"  output_dir:             {config.output_dir}")
    print(f"  qdrant_collection:      {config.qdrant_collection}")
    print(f"  generate_llms_files:    {config.generate_llms_files}")
    print()
    print(f"  rules ({len(config.rules)} configured):")
    for rule in config.rules:
        include_tags_display = ", ".join(rule.tags.include) if rule.tags.include else "none"
        print(
            f"    - {rule.name}: {rule.site} "
            f"(sort={rule.sort}, limit={rule.max_questions}, tags={include_tags_display})"
        )


def cmd_collect(args: argparse.Namespace) -> None:
    """Collect questions from Stack Exchange according to the configured rules.

    Fetches questions, applies filters, generates markdown files, and
    updates the local database. Supports incremental updates — questions with
    new answers are re-fetched and their files regenerated.

    Args:
        args: Parsed argparse namespace with global flags and collect-specific flags.
    """
    config = _load_config_from_args(args)

    validation_issues = validate_config(config)
    if validation_issues:
        for issue_message in validation_issues:
            print(f"ERROR: {issue_message}", file=sys.stderr)
        sys.exit(1)

    se_client = _make_client_from_config(config)

    output_override: Path | None = Path(args.output) if args.output is not None else None

    embedding_model = None
    embedding_qdrant_client = None
    if not args.dry_run:
        try:
            from deep_thought.embeddings import (  # noqa: PLC0415
                create_embedding_model,
                create_qdrant_client,
                ensure_collection,
            )

            embedding_model = create_embedding_model()
            embedding_qdrant_client = create_qdrant_client()
            ensure_collection(embedding_qdrant_client, config.qdrant_collection)
        except Exception as init_err:
            logger.error("Embedding infrastructure unavailable, continuing without embeddings: %s", init_err)

    connection = initialize_database()
    try:
        collection_result: CollectionResult = run_collection(
            se_client=se_client,
            config=config,
            db_conn=connection,
            dry_run=args.dry_run,
            force=args.force,
            rule_name_filter=args.rule,
            output_override=output_override,
            embedding_model=embedding_model,
            embedding_qdrant_client=embedding_qdrant_client,
            qdrant_collection=config.qdrant_collection,
        )
        connection.commit()
    finally:
        connection.close()
        if embedding_qdrant_client is not None:
            try:
                embedding_qdrant_client.close()
            except Exception as qdrant_close_err:
                logger.debug("QdrantClient close() raised: %s", qdrant_close_err)

    dry_run_prefix = "[dry-run] " if args.dry_run else ""
    print(f"{dry_run_prefix}Collection complete:")
    print(f"  Collected: {collection_result.questions_collected}")
    print(f"  Updated:   {collection_result.questions_updated}")
    print(f"  Skipped:   {collection_result.questions_skipped}")
    print(f"  Errored:   {collection_result.questions_errored}")

    if collection_result.errors:
        print(f"  Errors ({len(collection_result.errors)}):")
        for error_message in collection_result.errors:
            print(f"    - {error_message}")

    # Exit with code 2 for partial failure, 1 for total failure
    if (
        collection_result.questions_errored > 0
        and collection_result.questions_collected + collection_result.questions_updated > 0
    ):
        sys.exit(2)
    elif collection_result.questions_errored > 0:
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
        prog="stackexchange",
        description="Collect Stack Exchange questions and answers into structured markdown files.",
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
        help="Ignore per-question state and reprocess all matching questions.",
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

_COMMAND_HANDLERS: dict[str, Callable[[argparse.Namespace], None]] = {
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
    if args.save_config is not None:
        _handle_save_config(args.save_config)
        return

    if args.subcommand is None:
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
