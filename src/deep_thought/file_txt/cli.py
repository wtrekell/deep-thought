"""CLI entry point for the file-txt tool.

Converts PDF and Office files to markdown. With --llm, also generates
aggregate llms-full.txt and llms.txt files for LLM context loading.

Usage:
    file-txt [flags] PATH

Subcommands:
    config  — Validate and print the current configuration
    init    — Write default config and create the output directory
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from deep_thought.file_txt.config import (
    FileTxtConfig,
    get_bundled_config_path,
    get_default_config_path,
    load_config,
    validate_config,
)
from deep_thought.file_txt.convert import ConvertResult, convert_file
from deep_thought.file_txt.filters import collect_input_files
from deep_thought.file_txt.llms import DocumentSummary, write_llms_full, write_llms_index
from deep_thought.progress import track_items

logger = logging.getLogger(__name__)


def _get_version() -> str:
    """Return the package version from metadata, falling back to a default."""
    try:
        from importlib.metadata import version

        return version("deep-thought")
    except Exception:
        return "0.1.0"


_VERSION = _get_version()


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


def _load_config_from_args(args: argparse.Namespace) -> FileTxtConfig:
    """Load and return config, honouring any --config override in args.

    Args:
        args: Parsed argparse namespace which may contain a 'config' attribute.

    Returns:
        A fully parsed FileTxtConfig.

    Raises:
        FileNotFoundError: If the config file does not exist at the resolved path.
    """
    config_path: Path | None = Path(args.config) if args.config else None
    return load_config(config_path)


def _resolve_output_root(args: argparse.Namespace, config: FileTxtConfig) -> Path:
    """Determine the output root directory from CLI args or config.

    CLI --output overrides config.output.output_dir.

    Args:
        args: Parsed argparse namespace which may contain an 'output' attribute.
        config: The loaded FileTxtConfig.

    Returns:
        A Path for the output root (may not yet exist on disk).
    """
    if args.output:
        return Path(args.output)
    return Path(config.output.output_dir)


def _build_config_with_overrides(args: argparse.Namespace, config: FileTxtConfig) -> FileTxtConfig:
    """Return a new FileTxtConfig with CLI flag overrides applied.

    --force-ocr, --torch-device, and email flags override config settings
    so that ad-hoc CLI invocations do not require editing the YAML file.

    Args:
        args: Parsed argparse namespace.
        config: The base loaded FileTxtConfig.

    Returns:
        A new FileTxtConfig with CLI overrides applied.
    """
    from dataclasses import replace

    updated_marker = replace(
        config.marker,
        force_ocr=args.force_ocr if args.force_ocr is not None else config.marker.force_ocr,
        torch_device=args.torch_device if args.torch_device else config.marker.torch_device,
    )
    updated_output = replace(
        config.output,
        include_page_numbers=(
            args.include_page_numbers if args.include_page_numbers is not None else config.output.include_page_numbers
        ),
        extract_images=args.extract_images if args.extract_images is not None else config.output.extract_images,
    )
    updated_email = replace(
        config.email,
        prefer_html=args.prefer_html if args.prefer_html is not None else config.email.prefer_html,
        full_headers=args.full_headers if args.full_headers is not None else config.email.full_headers,
        include_attachments=(
            args.include_attachments if args.include_attachments is not None else config.email.include_attachments
        ),
    )
    return replace(config, marker=updated_marker, output=updated_output, email=updated_email)


def _result_to_document_summary(result: ConvertResult, output_root: Path) -> DocumentSummary | None:
    """Convert a successful ConvertResult to a DocumentSummary for LLM output.

    Returns None when the result has no output_path (skipped or errored).

    Args:
        result: A ConvertResult from convert_file.
        output_root: The output root directory, used to compute relative paths.

    Returns:
        A DocumentSummary or None if the result should not be included.
    """
    if result.output_path is None:
        return None

    try:
        md_relative_path = result.output_path.relative_to(output_root).as_posix()
    except ValueError:
        md_relative_path = result.output_path.name

    raw_content = result.output_path.read_text(encoding="utf-8")

    # Strip frontmatter for LLM context — import inline to avoid circular
    from deep_thought.file_txt.llms import strip_frontmatter

    content = strip_frontmatter(raw_content)

    return DocumentSummary(
        name=result.source_path.stem,
        md_relative_path=md_relative_path,
        source_file=result.source_path.name,
        file_type=result.file_type,
        word_count=result.word_count,
        content=content,
    )


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------


def cmd_convert(args: argparse.Namespace) -> None:
    """Convert input files to markdown and optionally generate LLM aggregates.

    Walks the input PATH (file or directory), applies configured filters,
    converts each file, and writes per-document markdown output. When
    --llm is set, writes llms-full.txt and llms.txt to the output root.
    When --nuke is set (and not --dry-run), source files are deleted after
    successful conversion.

    Args:
        args: Parsed argparse namespace containing all conversion flags.
    """
    config = _load_config_from_args(args)
    config = _build_config_with_overrides(args, config)

    validation_issues = validate_config(config)
    if validation_issues:
        for issue_text in validation_issues:
            print(f"WARNING: {issue_text}", file=sys.stderr)

    input_path = Path(args.path)
    output_root = _resolve_output_root(args, config)

    if args.dry_run:
        print(f"[dry-run] Would process: {input_path}")
        print(f"[dry-run] Output root:   {output_root}")

    try:
        input_files = collect_input_files(input_path, config.filter)
    except FileNotFoundError as not_found_error:
        print(f"ERROR: {not_found_error}", file=sys.stderr)
        sys.exit(1)

    if not input_files:
        print("No matching files found.")
        sys.exit(0)

    converted_count = 0
    skipped_count = 0
    error_count = 0
    successful_results: list[ConvertResult] = []

    for source_path in track_items(input_files, description="Converting files"):
        if args.verbose:
            dry_run_label = "[dry-run] " if args.dry_run else ""
            print(f"{dry_run_label}Converting: {source_path}")

        result = convert_file(source_path, output_root, config, dry_run=args.dry_run)

        if result.skipped:
            skipped_count += 1
            logger.debug("Skipped %s: %s", source_path, result.skip_reason)
        elif result.errors:
            error_count += 1
            for error_message in result.errors:
                print(f"  ERROR [{source_path.name}]: {error_message}", file=sys.stderr)
        else:
            converted_count += 1
            successful_results.append(result)

            if args.nuke and not args.dry_run:
                try:
                    source_path.unlink()
                    logger.debug("Deleted source file: %s", source_path)
                except OSError as delete_error:
                    print(f"  WARNING: Could not delete {source_path}: {delete_error}", file=sys.stderr)

    if args.llm and successful_results and not args.dry_run:
        summaries: list[DocumentSummary] = []
        for result in successful_results:
            summary = _result_to_document_summary(result, output_root)
            if summary is not None:
                summaries.append(summary)

        if summaries:
            llms_full_path = write_llms_full(summaries, output_root)
            llms_index_path = write_llms_index(summaries, output_root)
            print(f"  LLM full:  {llms_full_path}")
            print(f"  LLM index: {llms_index_path}")

    dry_run_prefix = "[dry-run] " if args.dry_run else ""
    print(f"{dry_run_prefix}Conversion complete:")
    print(f"  Converted: {converted_count}")
    print(f"  Skipped:   {skipped_count}")
    print(f"  Errors:    {error_count}")

    # Exit codes: 0 = all ok, 1 = all errored, 2 = partial failure (some ok + some errored)
    if error_count > 0 and converted_count > 0:
        sys.exit(2)
    elif error_count > 0:
        sys.exit(1)


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
        for issue_text in validation_issues:
            print(f"  WARNING: {issue_text}")
        print()
    else:
        print("Configuration is valid.")
        print()

    print("Loaded configuration:")
    print(f"  torch_device:          {config.marker.torch_device}")
    print(f"  force_ocr:             {config.marker.force_ocr}")
    print()
    print(f"  prefer_html:           {config.email.prefer_html}")
    print(f"  full_headers:          {config.email.full_headers}")
    print(f"  include_attachments:   {config.email.include_attachments}")
    print()
    print(f"  output_dir:            {config.output.output_dir}")
    print(f"  include_page_numbers:  {config.output.include_page_numbers}")
    print(f"  extract_images:        {config.output.extract_images}")
    print()
    print(f"  max_file_size_mb:      {config.limits.max_file_size_mb}")
    print()
    print(f"  allowed_extensions:    {config.filter.allowed_extensions or '(none)'}")
    print(f"  exclude_patterns:      {config.filter.exclude_patterns or '(none)'}")


def cmd_init(args: argparse.Namespace) -> None:
    """Bootstrap the file-txt tool for first use in the calling repo.

    Copies the bundled default config template from the package to
    ``src/config/file-txt-configuration.yaml`` (relative to cwd), creates
    the default output directory, and prints a summary.

    Never attempts to load the project-level config — it does not exist yet.

    Args:
        args: Parsed argparse namespace.
    """
    import shutil

    bundled_config_path = get_bundled_config_path()
    project_config_path: Path = Path(args.save_config) if args.save_config else get_default_config_path()

    if not bundled_config_path.exists():
        print(f"ERROR: Bundled config template not found at {bundled_config_path}.", file=sys.stderr)
        sys.exit(1)

    created_items: list[str] = []

    if project_config_path.exists():
        print(f"  Configuration file already exists: {project_config_path}")
    else:
        project_config_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(bundled_config_path, project_config_path)
        created_items.append(f"  Configuration file: {project_config_path}")

    output_dir = Path(args.output) if hasattr(args, "output") and args.output else Path("output")
    output_dir.mkdir(parents=True, exist_ok=True)
    created_items.append(f"  Output directory: {output_dir}")

    print("file-txt initialised successfully.")
    print()
    for item in created_items:
        print(item)
    print()
    print("Next steps:")
    print(f"  1. Review configuration:  {project_config_path}")
    print("  2. Run: file-txt <path-to-files>")


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def _build_argument_parser() -> argparse.ArgumentParser:
    """Construct and return the top-level argument parser with all subcommands.

    Returns:
        A fully configured argparse.ArgumentParser instance.
    """
    root_parser = argparse.ArgumentParser(
        prog="file-txt",
        description="Convert PDF, Office, and email files to markdown.",
    )

    root_parser.add_argument(
        "--version",
        action="version",
        version=f"file-txt {_VERSION}",
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
    # Default conversion mode
    # -------------------------
    convert_parser = subparsers.add_parser(
        "convert",
        help="Convert files to markdown (default operation).",
    )
    _add_convert_arguments(convert_parser)

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
        help="Write default config and create the output directory.",
    )
    init_parser.add_argument(
        "--save-config",
        metavar="PATH",
        default=None,
        help="Write default config to this path instead of the default location.",
    )

    return root_parser


def _build_root_parser_with_convert_defaults() -> argparse.ArgumentParser:
    """Build a parser that accepts convert flags directly at the root level.

    When no subcommand is provided, file-txt treats all top-level positional
    and flag arguments as conversion arguments. This parser is used for that
    fallback path.

    Returns:
        A fully configured argparse.ArgumentParser for root-level conversion.
    """
    root_parser = argparse.ArgumentParser(
        prog="file-txt",
        description="Convert PDF, Office, and email files to markdown.",
        add_help=False,
    )

    root_parser.add_argument("--version", action="version", version=f"file-txt {_VERSION}")
    root_parser.add_argument("--verbose", "-v", action="store_true", default=False)
    root_parser.add_argument("--config", metavar="PATH", default=None)

    _add_convert_arguments(root_parser)

    return root_parser


def _add_convert_arguments(parser: argparse.ArgumentParser) -> None:
    """Attach all conversion-mode flags to an argument parser.

    Shared between the root-level fallback and the explicit 'convert'
    subcommand parser.

    Args:
        parser: The parser to add arguments to.
    """
    parser.add_argument(
        "path",
        metavar="PATH",
        help="File or directory to convert.",
    )
    parser.add_argument(
        "--output",
        metavar="PATH",
        default=None,
        help="Output directory (default: output/).",
    )
    parser.add_argument(
        "--llm",
        action="store_true",
        default=False,
        help="Also generate llms-full.txt and llms.txt aggregate files.",
    )
    parser.add_argument(
        "--force-ocr",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Force OCR for PDF files even when text is extractable directly.",
    )
    parser.add_argument(
        "--torch-device",
        choices=["mps", "cuda", "cpu"],
        default=None,
        help="Hardware device for Marker: 'mps', 'cuda', or 'cpu'.",
    )
    parser.add_argument(
        "--include-page-numbers",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Retain page number markers in PDF output.",
    )
    parser.add_argument(
        "--extract-images",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Extract embedded images to img/ subdirectories.",
    )
    parser.add_argument(
        "--prefer-html",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="For email files: prefer HTML body (converted to markdown) over plain text.",
    )
    parser.add_argument(
        "--full-headers",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Include additional headers beyond From/To/Date (email only).",
    )
    parser.add_argument(
        "--include-attachments",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="For email files: include attachment metadata in output (default: from config).",
    )
    parser.add_argument(
        "--nuke",
        action="store_true",
        default=False,
        help="Delete source files after successful conversion.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Show what would be converted without writing any files.",
    )


# ---------------------------------------------------------------------------
# Command dispatch table
# ---------------------------------------------------------------------------

_COMMAND_HANDLERS = {
    "convert": cmd_convert,
    "config": cmd_config,
    "init": cmd_init,
}


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Parse arguments and dispatch to the appropriate command handler.

    When no subcommand is given, the tool operates in conversion mode,
    treating the first positional argument as the input path. This mirrors
    the behaviour of tools like ffmpeg and pandoc.

    Wraps each handler in consistent error handling so all user-facing
    failures exit with code 1 and a clear message.
    """
    argument_parser = _build_argument_parser()
    args, remaining_args = argument_parser.parse_known_args()

    _setup_logging(args.verbose)

    if remaining_args and args.subcommand is not None:
        print(f"WARNING: Unrecognized arguments ignored: {' '.join(remaining_args)}", file=sys.stderr)

    if args.subcommand is None:
        # No subcommand: re-parse the full argv as a direct conversion call
        fallback_parser = _build_root_parser_with_convert_defaults()
        args = fallback_parser.parse_args()

        if not hasattr(args, "path") or args.path is None:
            argument_parser.print_help()
            sys.exit(0)

        args.subcommand = "convert"

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


# Expose _build_argument_parser and helpers for test introspection
__all__ = [
    "main",
    "cmd_convert",
    "cmd_config",
    "cmd_init",
    "_build_argument_parser",
    "_COMMAND_HANDLERS",
]
