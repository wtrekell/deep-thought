"""CLI entry points for the Research Tool.

Provides two commands:
    search  — quick web search via Perplexity sonar model
    research — deep research via Perplexity sonar-deep-research model (async)

Usage:
    search "What is MLX?" [--quick] [--context PATH] [--domains TEXT] [--recency FILTER]
    research "Compare MLX vs PyTorch" [--context PATH] [--domains TEXT] [--recency FILTER]
    research init
    research config
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Callable  # noqa: TC003
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from deep_thought.progress import spinner_context
from deep_thought.research.config import (
    _VALID_RECENCY_VALUES,
    ResearchConfig,
    get_api_key,
    get_bundled_config_path,
    get_default_config_path,
    load_config,
    validate_config,
)

logger = logging.getLogger(__name__)


def _get_version() -> str:
    """Return the installed package version, falling back to 'unknown' if not found.

    Reads the version from package metadata at runtime so it always matches
    ``pyproject.toml`` without requiring a manual sync.

    Returns:
        The package version string, or "unknown" if package metadata is unavailable.
    """
    try:
        return version("deep-thought")
    except PackageNotFoundError:
        return "unknown"


_MAX_DOMAINS = 20


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


def _load_config_from_args(args: argparse.Namespace) -> ResearchConfig:
    """Load and return the Research configuration, honouring any --config override.

    Args:
        args: Parsed argparse namespace which may contain a 'config' attribute.

    Returns:
        A fully parsed ResearchConfig.
    """
    config_path: Path | None = Path(args.config) if args.config else None
    return load_config(config_path)


def _handle_save_config(destination_path_str: str) -> None:
    """Write the default example configuration to the specified path and exit.

    Reads the bundled default config, checks the destination does not already
    exist, creates any missing parent directories, and writes the file.

    Args:
        destination_path_str: String path where the default config should be written.
    """
    destination_path = Path(destination_path_str)
    source_path = get_bundled_config_path()

    if not source_path.exists():
        print(f"ERROR: Default config template not found at {source_path}.", file=sys.stderr)
        sys.exit(1)

    if destination_path.exists():
        print(f"ERROR: File already exists at {destination_path}. Remove it first to regenerate.", file=sys.stderr)
        sys.exit(1)

    destination_path.parent.mkdir(parents=True, exist_ok=True)
    destination_path.write_bytes(source_path.read_bytes())
    print(f"Default configuration written to: {destination_path}")


def _run_command(handler: Callable[..., Any], args: argparse.Namespace) -> int:
    """Run a command handler with consistent error catching and exit codes.

    Catches FileNotFoundError, OSError, ValueError, and any unexpected
    exception. Prints an error message to stderr for each. Logs the full
    traceback at DEBUG level for unexpected errors.

    Args:
        handler: A callable accepting an argparse.Namespace.
        args: The parsed argument namespace to pass to the handler.

    Returns:
        0 on success, 1 on any error.
    """
    try:
        handler(args)
        return 0
    except FileNotFoundError as missing_file_error:
        print(f"ERROR: File not found — {missing_file_error}", file=sys.stderr)
        return 1
    except OSError as os_error:
        print(f"ERROR: {os_error}", file=sys.stderr)
        return 1
    except ValueError as value_error:
        print(f"ERROR: {value_error}", file=sys.stderr)
        return 1
    except Exception as unexpected_error:
        print(f"ERROR: An unexpected error occurred — {unexpected_error}", file=sys.stderr)
        logger.debug("Full traceback:", exc_info=True)
        return 1


# ---------------------------------------------------------------------------
# Domain validation
# ---------------------------------------------------------------------------


def _parse_domains(domains_str: str) -> list[str]:
    """Parse a comma-separated domains string into a validated list.

    Strips whitespace from each entry, drops empty strings, enforces the
    20-domain maximum, and validates that all entries are either allow-listed
    (no prefix) or deny-listed (prefixed with ``-``), but not mixed.

    Args:
        domains_str: Raw comma-separated domains string from the CLI.

    Returns:
        A cleaned list of domain filter strings.

    Raises:
        ValueError: If more than 20 domains are provided.
        ValueError: If allow-listed and deny-listed domains are mixed.
    """
    raw_entries = domains_str.split(",")
    parsed_domains = [entry.strip() for entry in raw_entries if entry.strip()]

    if len(parsed_domains) > _MAX_DOMAINS:
        raise ValueError(f"Too many domains: {len(parsed_domains)} provided, maximum is {_MAX_DOMAINS}.")

    deny_listed_domains = [domain for domain in parsed_domains if domain.startswith("-")]
    allow_listed_domains = [domain for domain in parsed_domains if not domain.startswith("-")]

    if deny_listed_domains and allow_listed_domains:
        raise ValueError(
            "Cannot mix allow-listed and exclude-listed domains. "
            "Either all domains should be prefixed with '-' (exclude) or none should be."
        )

    return parsed_domains


# ---------------------------------------------------------------------------
# Shared flag injection
# ---------------------------------------------------------------------------


def _add_shared_flags(parser: argparse.ArgumentParser) -> None:
    """Add flags that are common to both the search and research parsers.

    Adds: --output, --config, --context (repeatable), --domains,
    --recency, --dry-run, --verbose / -v, --save-config, --version.

    Args:
        parser: The ArgumentParser to add flags to.
    """
    parser.add_argument(
        "--output",
        metavar="PATH",
        default=None,
        help="Override the output directory from configuration.",
    )
    parser.add_argument(
        "--config",
        metavar="PATH",
        default=None,
        help="Override the default configuration file path.",
    )
    parser.add_argument(
        "--context",
        metavar="PATH",
        action="append",
        default=None,
        help="Path to a local file to include as prior research context. Repeatable.",
    )
    parser.add_argument(
        "--domains",
        metavar="TEXT",
        default=None,
        help=(
            "Comma-separated list of domains to restrict or exclude. "
            "Prefix a domain with '-' to exclude it (e.g. '-reddit.com'). "
            f"Maximum {_MAX_DOMAINS} domains."
        ),
    )
    parser.add_argument(
        "--recency",
        choices=_VALID_RECENCY_VALUES,
        default=None,
        help="Restrict results to content published within this time window.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Preview what would be submitted without making any API calls.",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        default=False,
        help="Increase log output.",
    )
    parser.add_argument(
        "--save-config",
        metavar="PATH",
        default=None,
        help="Write a default example configuration file to PATH and exit.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {_get_version()}",
        help="Show version and exit.",
    )


# ---------------------------------------------------------------------------
# Argument parsers
# ---------------------------------------------------------------------------


def _build_search_parser() -> argparse.ArgumentParser:
    """Construct and return the argument parser for the ``search`` command.

    Includes a required positional ``query`` argument, a ``--quick`` flag for
    stdout-only output, and all shared flags from ``_add_shared_flags``.

    Returns:
        A fully configured argparse.ArgumentParser for the search entry point.
    """
    search_parser = argparse.ArgumentParser(
        prog="search",
        description="Run a quick web search via the Perplexity sonar model.",
    )
    search_parser.add_argument(
        "query",
        help="The research question to submit.",
    )
    search_parser.add_argument(
        "--quick",
        action="store_true",
        default=False,
        help="Print answer to stdout without writing a file.",
    )
    _add_shared_flags(search_parser)
    return search_parser


def _build_research_parser() -> argparse.ArgumentParser:
    """Construct and return the argument parser for the ``research`` command.

    The positional ``query`` argument is intentionally omitted here because
    argparse cannot reliably distinguish a free-text query from a subcommand
    name when both an optional positional and subparsers are declared together.
    Instead, ``research_main`` manually filters ``sys.argv`` to extract the
    query before passing the remaining arguments to ``parse_args``. All shared
    flags are added via ``_add_shared_flags``.

    Returns:
        A fully configured argparse.ArgumentParser for the research entry point.
    """
    research_parser = argparse.ArgumentParser(
        prog="research",
        description=(
            "Run deep research via the Perplexity sonar-deep-research model (async).\n\n"
            "Usage:\n"
            '  research "Your research question here" [flags]\n'
            "  research init\n"
            "  research config"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _add_shared_flags(research_parser)

    subparsers = research_parser.add_subparsers(dest="subcommand", required=False)
    subparsers.add_parser(
        "init",
        help="Create data directories and starter configuration.",
    )
    subparsers.add_parser(
        "config",
        help="Validate and display current configuration.",
    )

    return research_parser


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------


def cmd_init(args: argparse.Namespace) -> None:
    """Bootstrap the research tool for first use in the calling repo.

    Copies the bundled default config template from the package to
    ``src/config/research-configuration.yaml`` (relative to cwd), creates
    ``data/research/`` and the default output directory, and prints a summary.

    Never attempts to load the project-level config — it does not exist yet.

    Args:
        args: Parsed argparse namespace.
    """
    import os
    import shutil

    bundled_config = get_bundled_config_path()
    project_config = get_default_config_path()
    data_root = Path(os.environ.get("DEEP_THOUGHT_DATA_DIR", "data"))
    data_dir = data_root / "research"
    output_dir = Path(args.output) if args.output else data_root / "research" / "export"

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

    data_dir.mkdir(parents=True, exist_ok=True)
    created_items.append(f"  Data directory: {data_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)
    created_items.append(f"  Output directory: {output_dir}")

    print("Research Tool initialised successfully.")
    print()
    for item in created_items:
        print(item)


def cmd_config(args: argparse.Namespace) -> None:
    """Load the configuration file, validate it, and print all settings.

    If validation issues are found, prints them to stderr and exits with
    code 1. Otherwise prints all configuration fields to stdout.

    Args:
        args: Parsed argparse namespace.
    """
    config = _load_config_from_args(args)
    validation_issues = validate_config(config)

    if validation_issues:
        print(f"Configuration issues ({len(validation_issues)} found):", file=sys.stderr)
        for issue in validation_issues:
            print(f"  WARNING: {issue}", file=sys.stderr)
        sys.exit(1)

    print("Configuration is valid.")
    print()
    print("Loaded configuration:")
    print(f"  api_key_env:              {config.api_key_env}")
    print(f"  search_model:             {config.search_model}")
    print(f"  research_model:           {config.research_model}")
    print(f"  default_recency:          {config.default_recency}")
    print(f"  retry_max_attempts:       {config.retry_max_attempts}")
    print(f"  retry_base_delay_seconds: {config.retry_base_delay_seconds}")
    print(f"  output_dir:               {config.output_dir}")


def cmd_search(args: argparse.Namespace) -> None:
    """Run a quick search query and write (or print) the result.

    Resolves recency, domains, and context files from args and config,
    then calls PerplexityClient.search(). With --quick, prints the answer
    to stdout. Otherwise writes a markdown file and prints a summary.

    Args:
        args: Parsed argparse namespace with query and optional flags.
    """
    from deep_thought.research.output import generate_research_markdown, write_research_file
    from deep_thought.research.researcher import PerplexityClient

    config = _load_config_from_args(args)

    resolved_recency: str | None = args.recency or config.default_recency
    parsed_domains: list[str] = _parse_domains(args.domains) if args.domains else []
    resolved_context_files: list[str] = args.context or []

    if args.dry_run:
        print("[dry-run] search query preview:")
        print(f"  Query:         {args.query}")
        print(f"  Context files: {resolved_context_files}")
        print(f"  Domains:       {parsed_domains}")
        print(f"  Recency:       {resolved_recency}")
        print(f"  Model:         {config.search_model}")
        return

    api_key = get_api_key(config)
    perplexity_client = PerplexityClient(api_key, config)
    try:
        with spinner_context("Searching..."):
            search_result = perplexity_client.search(
                args.query,
                recency=resolved_recency,
                domains=parsed_domains,
                context_files=resolved_context_files,
            )
    finally:
        perplexity_client.close()

    if args.quick:
        print(search_result.answer)
        return

    resolved_output_dir = Path(args.output) if args.output else Path(config.output_dir)
    markdown_content = generate_research_markdown(search_result)
    written_file_path = write_research_file(markdown_content, resolved_output_dir, search_result)

    try:
        from deep_thought.embeddings import (  # noqa: PLC0415
            create_embedding_model,
            create_qdrant_client,
            ensure_collection,
        )
        from deep_thought.research.embeddings import write_embedding as _write_research_embedding  # noqa: PLC0415

        _embedding_model = create_embedding_model()
        _qdrant_client = create_qdrant_client()
        ensure_collection(_qdrant_client, config.qdrant_collection)
        embed_content = f"Query: {search_result.query}\n\n{search_result.answer}"
        _write_research_embedding(
            embed_content,
            search_result,
            str(written_file_path),
            _embedding_model,
            _qdrant_client,
            config.qdrant_collection,
        )
    except Exception as embed_err:
        logger.warning("Embedding failed for query '%s': %s", search_result.query, embed_err)

    print("Search complete:")
    print(f"  File:    {written_file_path}")
    print(f"  Sources: {len(search_result.search_results)}")
    print(f"  Cost:    ${search_result.cost_usd:.4f}")


def cmd_research(args: argparse.Namespace) -> None:
    """Run a deep research query and write the result to a markdown file.

    Validates that a query was provided, resolves recency, domains, and
    context files, then calls PerplexityClient.research(). Prints progress
    before submitting since deep research jobs can take several minutes.

    Args:
        args: Parsed argparse namespace with query and optional flags.

    Raises:
        ValueError: If no query is provided on the command line.
    """
    from deep_thought.research.output import generate_research_markdown, write_research_file
    from deep_thought.research.researcher import PerplexityClient

    if not args.query:
        raise ValueError('A query is required for the research command. Usage: research "Your research question here"')

    config = _load_config_from_args(args)

    resolved_recency: str | None = args.recency or config.default_recency
    parsed_domains: list[str] = _parse_domains(args.domains) if args.domains else []
    resolved_context_files: list[str] = args.context or []

    if args.dry_run:
        print("[dry-run] research query preview:")
        print(f"  Query:         {args.query}")
        print(f"  Context files: {resolved_context_files}")
        print(f"  Domains:       {parsed_domains}")
        print(f"  Recency:       {resolved_recency}")
        print(f"  Model:         {config.research_model}")
        return

    api_key = get_api_key(config)
    logger.debug("Query: %s", args.query)

    perplexity_client = PerplexityClient(api_key, config)
    try:
        with spinner_context("Researching..."):
            research_result = perplexity_client.research(
                args.query,
                recency=resolved_recency,
                domains=parsed_domains,
                context_files=resolved_context_files,
            )
    finally:
        perplexity_client.close()

    resolved_output_dir = Path(args.output) if args.output else Path(config.output_dir)
    markdown_content = generate_research_markdown(research_result)
    written_file_path = write_research_file(markdown_content, resolved_output_dir, research_result)

    try:
        from deep_thought.embeddings import (  # noqa: PLC0415
            create_embedding_model,
            create_qdrant_client,
            ensure_collection,
        )
        from deep_thought.research.embeddings import write_embedding as _write_research_embedding  # noqa: PLC0415

        _embedding_model = create_embedding_model()
        _qdrant_client = create_qdrant_client()
        ensure_collection(_qdrant_client, config.qdrant_collection)
        embed_content = f"Query: {research_result.query}\n\n{research_result.answer}"
        _write_research_embedding(
            embed_content,
            research_result,
            str(written_file_path),
            _embedding_model,
            _qdrant_client,
            config.qdrant_collection,
        )
    except Exception as embed_err:
        logger.warning("Embedding failed for query '%s': %s", research_result.query, embed_err)

    print("Research complete:")
    print(f"  File:    {written_file_path}")
    print(f"  Sources: {len(research_result.search_results)}")
    print(f"  Cost:    ${research_result.cost_usd:.4f}")


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------


def search_main() -> None:
    """Parse arguments and run the search command.

    Entry point for the ``search`` CLI command. Handles --save-config before
    dispatching to cmd_search.
    """
    search_argument_parser = _build_search_parser()
    args = search_argument_parser.parse_args()

    _setup_logging(args.verbose)

    if args.save_config:
        _handle_save_config(args.save_config)
        sys.exit(0)

    sys.exit(_run_command(cmd_search, args))


_RESEARCH_SUBCOMMANDS = frozenset({"init", "config"})


def research_main() -> None:
    """Parse arguments and dispatch to the appropriate research subcommand.

    Entry point for the ``research`` CLI command. Shows help when invoked
    with no arguments at all. Handles --save-config, then routes to
    cmd_init, cmd_config, or cmd_research based on the subcommand (or
    lack thereof).

    Because argparse cannot cleanly combine a free-text positional query with
    subparsers (it treats any positional as a subcommand choice), this entry
    point inspects ``sys.argv`` to detect whether a known subcommand is
    present. If the first non-flag argument is NOT a known subcommand, the
    query is extracted before passing control to the parser.
    """
    research_argument_parser = _build_research_parser()

    if len(sys.argv) == 1:
        research_argument_parser.print_help()
        sys.exit(0)

    # Identify whether a known subcommand appears anywhere in the raw args.
    # We scan for the first non-flag token (i.e., does not start with '-').
    detected_query: str | None = None
    filtered_argv = list(sys.argv[1:])
    first_positional_index: int | None = None

    for index, token in enumerate(filtered_argv):
        if not token.startswith("-"):
            first_positional_index = index
            break

    if first_positional_index is not None:
        first_positional_token = filtered_argv[first_positional_index]
        if first_positional_token not in _RESEARCH_SUBCOMMANDS:
            # Treat it as a query string and remove it from the args we pass
            # to argparse so the subparser machinery never sees it.
            detected_query = first_positional_token
            filtered_argv.pop(first_positional_index)

    args = research_argument_parser.parse_args(filtered_argv)
    args.query = detected_query

    _setup_logging(args.verbose)

    if args.save_config:
        _handle_save_config(args.save_config)
        sys.exit(0)

    if args.subcommand == "init":
        sys.exit(_run_command(cmd_init, args))
    elif args.subcommand == "config":
        sys.exit(_run_command(cmd_config, args))
    else:
        # Default operation: deep research query.
        # If no subcommand and no query, show help.
        if not args.query:
            research_argument_parser.print_help()
            sys.exit(0)
        sys.exit(_run_command(cmd_research, args))
