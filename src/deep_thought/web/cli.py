"""CLI entry point for the web crawl tool.

Crawls web pages and converts them to LLM-optimized markdown. Supports
blog, documentation, and direct crawl modes with optional batch processing.

Usage:
    web [flags] --input URL
    web [flags] --input-file PATH

Subcommands:
    config  — Validate and print the current configuration
    init    — Scaffold configs, output directories, and database
"""

from __future__ import annotations

import argparse
import importlib.metadata
import logging
import sys
from dataclasses import replace
from pathlib import Path

from deep_thought.web.config import (
    CrawlConfig,
    WebConfig,
    copy_default_templates,
    get_batch_config_dir,
    get_bundled_config_path,
    get_default_config_path,
    load_config,
    save_default_config,
    validate_config,
)
from deep_thought.web.db.schema import get_data_dir, initialize_database
from deep_thought.web.processor import process

logger = logging.getLogger(__name__)


def _get_version() -> str:
    """Return the installed package version, falling back to a dev sentinel.

    Returns:
        The version string from package metadata, or "0.0.0-dev" if the
        package is not installed in the current environment.
    """
    try:
        return importlib.metadata.version("deep-thought")
    except importlib.metadata.PackageNotFoundError:
        return "0.0.0-dev"


_VERSION = _get_version()


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


def _load_config_from_args(args: argparse.Namespace) -> WebConfig:
    """Load and return config, honouring any --config override in args.

    Args:
        args: Parsed argparse namespace which may contain a 'config' attribute.

    Returns:
        A fully parsed WebConfig.

    Raises:
        FileNotFoundError: If the config file does not exist at the resolved path.
    """
    config_path: Path | None = Path(args.config) if args.config else None
    return load_config(config_path)


def _resolve_output_root(args: argparse.Namespace, config: WebConfig) -> Path:
    """Determine the output root directory from CLI args or config.

    CLI --output overrides config.crawl.output_dir.

    Args:
        args: Parsed argparse namespace which may contain an 'output' attribute.
        config: The loaded WebConfig.

    Returns:
        A Path for the output root (may not yet exist on disk).
    """
    if getattr(args, "output", None):
        return Path(args.output)
    return Path(config.crawl.output_dir)


def _build_config_with_overrides(args: argparse.Namespace, config: WebConfig) -> WebConfig:
    """Return a new WebConfig with CLI flag overrides applied.

    Applies any CLI flags that were explicitly provided, leaving config
    values unchanged for flags that were not set.

    Args:
        args: Parsed argparse namespace.
        config: The base loaded WebConfig.

    Returns:
        A new WebConfig with CLI overrides applied.
    """
    original_crawl = config.crawl

    cli_mode: str | None = getattr(args, "mode", None)
    updated_mode: str = cli_mode if cli_mode is not None else original_crawl.mode

    cli_max_depth: int | None = getattr(args, "max_depth", None)
    updated_max_depth: int = cli_max_depth if cli_max_depth is not None else original_crawl.max_depth

    cli_max_pages: int | None = getattr(args, "max_pages", None)
    updated_max_pages: int = cli_max_pages if cli_max_pages is not None else original_crawl.max_pages

    cli_js_wait: float | None = getattr(args, "js_wait", None)
    updated_js_wait: float = cli_js_wait if cli_js_wait is not None else original_crawl.js_wait

    cli_browser_channel: str | None = getattr(args, "browser_channel", None)
    updated_browser_channel: str | None = (
        cli_browser_channel if cli_browser_channel is not None else original_crawl.browser_channel
    )

    cli_stealth: bool | None = getattr(args, "stealth", None)
    updated_stealth: bool = cli_stealth if cli_stealth is not None else original_crawl.stealth

    cli_retry_attempts: int | None = getattr(args, "retry_attempts", None)
    updated_retry_attempts: int = (
        cli_retry_attempts if cli_retry_attempts is not None else original_crawl.retry_attempts
    )

    cli_retry_delay: float | None = getattr(args, "retry_delay", None)
    updated_retry_delay: float = cli_retry_delay if cli_retry_delay is not None else original_crawl.retry_delay

    cli_extract_images: bool | None = getattr(args, "extract_images", None)
    updated_extract_images: bool = (
        cli_extract_images if cli_extract_images is not None else original_crawl.extract_images
    )

    cli_include_patterns: list[str] | None = getattr(args, "include_patterns", None)
    updated_include_patterns: list[str] = (
        cli_include_patterns if cli_include_patterns is not None else original_crawl.include_patterns
    )

    cli_exclude_patterns: list[str] | None = getattr(args, "exclude_patterns", None)
    updated_exclude_patterns: list[str] = (
        cli_exclude_patterns if cli_exclude_patterns is not None else original_crawl.exclude_patterns
    )

    updated_crawl: CrawlConfig = replace(
        original_crawl,
        mode=updated_mode,
        max_depth=updated_max_depth,
        max_pages=updated_max_pages,
        js_wait=updated_js_wait,
        browser_channel=updated_browser_channel,
        stealth=updated_stealth,
        include_patterns=updated_include_patterns,
        exclude_patterns=updated_exclude_patterns,
        retry_attempts=updated_retry_attempts,
        retry_delay=updated_retry_delay,
        extract_images=updated_extract_images,
    )

    return replace(config, crawl=updated_crawl)


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------


def cmd_crawl(args: argparse.Namespace) -> None:
    """Crawl web pages and convert them to markdown.

    Validates that either --input or --input-file is provided (or --batch),
    initializes the database, dispatches to process(), and prints a summary.
    Exits with code 0 on full success, 1 on fatal error, 2 on partial failure.

    Args:
        args: Parsed argparse namespace containing all crawl flags.
    """
    save_config_path_str: str | None = getattr(args, "save_config", None)
    if save_config_path_str is not None:
        save_default_config(Path(save_config_path_str))
        print(f"Default configuration written to: {save_config_path_str}")
        return

    config = _load_config_from_args(args)
    config = _build_config_with_overrides(args, config)

    validation_issues = validate_config(config)
    if validation_issues:
        for issue_text in validation_issues:
            logger.warning("Config issue: %s", issue_text)

    input_url: str | None = getattr(args, "input", None)
    input_file_str: str | None = getattr(args, "input_file", None)
    input_file: Path | None = Path(input_file_str) if input_file_str else None
    batch_mode: bool = getattr(args, "batch", False)
    dry_run: bool = getattr(args, "dry_run", False)
    force: bool = getattr(args, "force", False)

    if not batch_mode and input_url is None and input_file is None:
        print("ERROR: --input URL or --input-file PATH is required (or use --batch).", file=sys.stderr)
        sys.exit(1)

    output_root = _resolve_output_root(args, config)

    if dry_run:
        print(f"[dry-run] Output root: {output_root}")

    embedding_model = None
    embedding_qdrant_client = None
    if not dry_run:
        try:
            from deep_thought.embeddings import create_embedding_model, create_qdrant_client  # noqa: PLC0415

            embedding_model = create_embedding_model()
            embedding_qdrant_client = create_qdrant_client()
        except Exception as init_err:
            logger.error("Embedding infrastructure unavailable, continuing without embeddings: %s", init_err)

    database_path = get_data_dir() / "web.db"
    conn = initialize_database(database_path)

    total_succeeded = 0
    total_failed = 0
    total_skipped = 0

    try:
        if batch_mode:
            batch_configs_dir = get_batch_config_dir()
            if not batch_configs_dir.exists():
                print(f"ERROR: Batch config directory not found: {batch_configs_dir}", file=sys.stderr)
                sys.exit(1)

            batch_config_files = sorted(batch_configs_dir.glob("*.yaml"))
            if not batch_config_files:
                print(f"No batch config files found in: {batch_configs_dir}")
                sys.exit(0)

            for batch_config_path in batch_config_files:
                batch_config = load_config(batch_config_path)
                batch_rule_name = batch_config_path.stem
                batch_input_url: str | None = getattr(batch_config.crawl, "input_url", None)
                batch_output_root = Path(batch_config.crawl.output_dir)

                if dry_run:
                    print(f"[dry-run] Would process batch rule: {batch_rule_name}")

                try:
                    crawl_result = process(
                        input_url=batch_input_url,
                        input_file=None,
                        mode=batch_config.crawl.mode,
                        config=batch_config,
                        conn=conn,
                        output_root=batch_output_root,
                        dry_run=dry_run,
                        force=force,
                        rule_name=batch_rule_name,
                        embedding_model=embedding_model,
                        embedding_qdrant_client=embedding_qdrant_client,
                    )
                    total_succeeded += crawl_result.succeeded
                    total_failed += crawl_result.failed
                    total_skipped += crawl_result.skipped
                except Exception as batch_error:
                    print(f"  ERROR [{batch_rule_name}]: {batch_error}", file=sys.stderr)
                    total_failed += 1
        else:
            crawl_result = process(
                input_url=input_url,
                input_file=input_file,
                mode=config.crawl.mode,
                config=config,
                conn=conn,
                output_root=output_root,
                dry_run=dry_run,
                force=force,
                rule_name=None,
                embedding_model=embedding_model,
                embedding_qdrant_client=embedding_qdrant_client,
            )
            total_succeeded = crawl_result.succeeded
            total_failed = crawl_result.failed
            total_skipped = crawl_result.skipped
    finally:
        conn.close()

    dry_run_prefix = "[dry-run] " if dry_run else ""
    print(f"{dry_run_prefix}Crawl complete:")
    print(f"  Succeeded: {total_succeeded}")
    print(f"  Failed:    {total_failed}")
    print(f"  Skipped:   {total_skipped}")

    if total_failed > 0 and total_succeeded == 0:
        sys.exit(1)
    elif total_failed > 0:
        sys.exit(2)


def cmd_config(args: argparse.Namespace) -> None:
    """Load the configuration file, validate it, and print all settings.

    Args:
        args: Parsed argparse namespace, may contain 'config' path override.
    """
    config = _load_config_from_args(args)

    validation_issues = validate_config(config)
    if validation_issues:
        print(f"Configuration issues ({len(validation_issues)} found):")
        for issue_text in validation_issues:
            print(f"  WARNING: {issue_text}")
        print()
    else:
        print("Configuration is valid.")
        print()

    crawl = config.crawl
    print("Loaded configuration:")
    print(f"  mode:                  {crawl.mode}")
    print(f"  max_depth:             {crawl.max_depth}")
    print(f"  max_pages:             {crawl.max_pages}")
    print()
    print(f"  js_wait:               {crawl.js_wait}")
    print(f"  browser_channel:       {crawl.browser_channel or '(none)'}")
    print(f"  stealth:               {crawl.stealth}")
    print()
    print(f"  include_patterns:      {crawl.include_patterns or '(none)'}")
    print(f"  exclude_patterns:      {crawl.exclude_patterns or '(none)'}")
    print()
    print(f"  retry_attempts:        {crawl.retry_attempts}")
    print(f"  retry_delay:           {crawl.retry_delay}")
    print()
    print(f"  output_dir:            {crawl.output_dir}")
    print(f"  extract_images:        {crawl.extract_images}")
    print(f"  generate_llms_files:   {crawl.generate_llms_files}")
    print()
    print(f"  index_depth:           {crawl.index_depth}")
    print(f"  min_article_words:     {crawl.min_article_words}")
    print(f"  changelog_url:         {crawl.changelog_url or '(none)'}")


def cmd_init(args: argparse.Namespace) -> None:
    """Bootstrap the web tool for first use in the calling repo.

    Copies the bundled default config template from the package to
    ``src/config/web-configuration.yaml`` (relative to cwd), copies batch
    config templates to ``src/config/web/``, creates output directories,
    and initializes the SQLite database.

    Never attempts to load the project-level config — it may not exist yet.
    Safe to re-run — existing files are never overwritten.

    Args:
        args: Parsed argparse namespace.
    """
    import os
    import shutil

    bundled_config_path = get_bundled_config_path()
    project_config_path: Path = Path(args.save_config) if args.save_config else get_default_config_path()

    if not bundled_config_path.exists():
        print(f"ERROR: Bundled config template not found at {bundled_config_path}.", file=sys.stderr)
        sys.exit(1)

    # 1. Default configuration file
    if project_config_path.exists():
        print(f"Configuration already exists:  {project_config_path}")
    else:
        project_config_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(bundled_config_path, project_config_path)
        print(f"Configuration written to:      {project_config_path}")

    # 2. Batch configs from templates
    template_results = copy_default_templates()
    for status, filename in template_results:
        if status == "created":
            print(f"Batch config created:         src/config/web/{filename}")
        else:
            print(f"Batch config already exists:  src/config/web/{filename}")

    # 3. Output directories
    project_root = Path.cwd()
    article_output_dir = project_root / "output" / "web"
    docs_output_dir = project_root / "docs"

    article_output_dir.mkdir(parents=True, exist_ok=True)
    print(f"Output directory ready:        {article_output_dir}")

    docs_output_dir.mkdir(parents=True, exist_ok=True)
    print(f"Output directory ready:        {docs_output_dir}")

    # 4. Database
    data_root = Path(os.environ.get("DEEP_THOUGHT_DATA_DIR", str(project_root / "data")))
    database_path = data_root / "web" / "web.db"
    initialize_database(database_path)
    print(f"Database initialized:          {database_path}")

    print()
    print("Next steps:")
    print("  1. Copy a batch config and edit for your site:")
    print("       cp src/config/web/blog.yaml src/config/web/my-site.yaml")
    print("  2. Edit input_url and patterns in the new config file")
    print("  3. Run: web crawl --batch")


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def _build_argument_parser() -> argparse.ArgumentParser:
    """Construct and return the top-level argument parser with all subcommands.

    Returns:
        A fully configured argparse.ArgumentParser instance.
    """
    root_parser = argparse.ArgumentParser(
        prog="web",
        description="Crawl web pages and convert them to LLM-optimized markdown.",
    )

    root_parser.add_argument(
        "--version",
        action="version",
        version=f"web {_VERSION}",
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

    subparsers = root_parser.add_subparsers(dest="subcommand", metavar="<command>")

    # -------------------------
    # Default crawl mode
    # -------------------------
    crawl_parser = subparsers.add_parser(
        "crawl",
        help="Crawl web pages and convert to markdown (default operation).",
    )
    _add_crawl_arguments(crawl_parser)

    # -------------------------
    # config subcommand
    # -------------------------
    subparsers.add_parser(
        "config",
        help="Validate and display the current YAML configuration.",
    )

    # -------------------------
    # init subcommand
    # -------------------------
    init_parser = subparsers.add_parser(
        "init",
        help="Scaffold configs, output directories, and database.",
    )
    init_parser.add_argument(
        "--save-config",
        metavar="PATH",
        default=None,
        help="Write default config to this path instead of the default location.",
    )

    return root_parser


def _build_root_parser_with_crawl_defaults() -> argparse.ArgumentParser:
    """Build a parser that accepts crawl flags directly at the root level.

    When no subcommand is provided, web treats all top-level flags as crawl
    arguments. This parser is used for that fallback path.

    Returns:
        A fully configured argparse.ArgumentParser for root-level crawling.
    """
    root_parser = argparse.ArgumentParser(
        prog="web",
        description="Crawl web pages and convert them to LLM-optimized markdown.",
        add_help=False,
    )

    root_parser.add_argument("--version", action="version", version=f"web {_VERSION}")
    root_parser.add_argument("--verbose", "-v", action="store_true", default=False)
    root_parser.add_argument("--config", metavar="PATH", default=None)

    _add_crawl_arguments(root_parser)

    return root_parser


def _add_crawl_arguments(parser: argparse.ArgumentParser) -> None:
    """Attach all crawl-mode flags to an argument parser.

    Shared between the root-level fallback and the explicit 'crawl'
    subcommand parser.

    Args:
        parser: The parser to add arguments to.
    """
    parser.add_argument(
        "--input",
        metavar="URL",
        default=None,
        help="Starting URL to crawl (blog and documentation modes).",
    )
    parser.add_argument(
        "--input-file",
        metavar="PATH",
        default=None,
        dest="input_file",
        help="Text file containing URLs to crawl, one per line (direct mode).",
    )
    parser.add_argument(
        "--mode",
        metavar="MODE",
        default=None,
        choices=["blog", "documentation", "direct"],
        help="Crawl mode: blog, documentation, or direct (default: blog).",
    )
    parser.add_argument(
        "--output",
        metavar="PATH",
        default=None,
        help="Output directory (overrides config output_dir).",
    )
    parser.add_argument(
        "--max-depth",
        metavar="INT",
        type=int,
        default=None,
        dest="max_depth",
        help="Maximum link depth to follow in documentation mode.",
    )
    parser.add_argument(
        "--max-pages",
        metavar="INT",
        type=int,
        default=None,
        dest="max_pages",
        help="Maximum number of pages to crawl.",
    )
    parser.add_argument(
        "--js-wait",
        metavar="FLOAT",
        type=float,
        default=None,
        dest="js_wait",
        help="Seconds to wait after page load for JavaScript to render.",
    )
    parser.add_argument(
        "--browser-channel",
        metavar="TEXT",
        default=None,
        dest="browser_channel",
        help="Playwright browser channel (e.g., 'chrome', 'msedge').",
    )
    parser.add_argument(
        "--stealth",
        action="store_true",
        default=None,
        help="Enable stealth mode (random user-agent and viewport).",
    )
    parser.add_argument(
        "--include-pattern",
        metavar="REGEX",
        action="append",
        dest="include_patterns",
        default=None,
        help="Regex pattern URLs must match to be crawled (repeatable).",
    )
    parser.add_argument(
        "--exclude-pattern",
        metavar="REGEX",
        action="append",
        dest="exclude_patterns",
        default=None,
        help="Regex pattern URLs matching this are skipped (repeatable).",
    )
    parser.add_argument(
        "--retry-attempts",
        metavar="INT",
        type=int,
        default=None,
        dest="retry_attempts",
        help="Number of retry attempts on fetch failure.",
    )
    parser.add_argument(
        "--retry-delay",
        metavar="FLOAT",
        type=float,
        default=None,
        dest="retry_delay",
        help="Seconds to wait between retry attempts.",
    )
    parser.add_argument(
        "--extract-images",
        action="store_true",
        default=None,
        dest="extract_images",
        help="Download images found on crawled pages.",
    )
    parser.add_argument(
        "--batch",
        action="store_true",
        default=False,
        help="Process all batch YAML configs in src/config/web/.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        dest="dry_run",
        help="Show what would be crawled without writing any files.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Re-crawl URLs that were previously crawled successfully.",
    )
    parser.add_argument(
        "--save-config",
        metavar="PATH",
        default=None,
        dest="save_config",
        help="Save the resolved configuration to a YAML file and exit.",
    )


# ---------------------------------------------------------------------------
# Command dispatch table
# ---------------------------------------------------------------------------

_COMMAND_HANDLERS = {
    "crawl": cmd_crawl,
    "config": cmd_config,
    "init": cmd_init,
}


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Parse arguments and dispatch to the appropriate command handler.

    When no subcommand is given, the tool operates in crawl mode. This
    mirrors the behaviour of tools like ffmpeg and pandoc.

    Wraps each handler in consistent error handling so all user-facing
    failures exit with code 1 and a clear message.
    """
    argument_parser = _build_argument_parser()
    args, remaining_args = argument_parser.parse_known_args()

    _setup_logging(args.verbose)

    if remaining_args:
        logger.warning(
            "Unrecognised arguments ignored: %s — check for typos.",
            " ".join(remaining_args),
        )

    if args.subcommand is None:
        fallback_parser = _build_root_parser_with_crawl_defaults()
        args = fallback_parser.parse_args()
        args.subcommand = "crawl"

    handler = _COMMAND_HANDLERS.get(args.subcommand)
    if handler is None:
        argument_parser.print_help()
        sys.exit(1)

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


# Expose for test introspection
__all__ = [
    "main",
    "cmd_crawl",
    "cmd_config",
    "cmd_init",
    "_build_argument_parser",
    "_COMMAND_HANDLERS",
]
