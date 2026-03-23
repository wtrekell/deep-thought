"""CLI entry point for the audio tool.

Transcribes audio files to LLM-optimized markdown using Whisper or MLX-Whisper.

Usage:
    audio [flags]                     # Transcribe with defaults
    audio --input file.mp3            # Transcribe a specific file
    audio config                      # Show configuration
    audio init                        # Create dirs, config, DB

Subcommands:
    config  — Validate and print the current configuration
    init    — Write default config, create output directory and database
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any

from deep_thought.audio.config import (
    AudioConfig,
    get_default_config_path,
    load_config,
    save_default_config,
    validate_config,
)

logger = logging.getLogger(__name__)

_VERSION = "0.1.0"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _setup_logging(verbose: bool) -> None:
    """Configure root logger based on the verbosity flag.

    Uses basicConfig to attach a handler if none exists, then sets the level
    directly on the root logger so the level is always applied even when pytest
    or another framework has already installed a handler.

    Args:
        verbose: If True, set log level to DEBUG; otherwise INFO.
    """
    log_level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(format="%(levelname)s: %(message)s")
    logging.getLogger().setLevel(log_level)


def _load_config_from_args(args: argparse.Namespace) -> AudioConfig:
    """Load and return config, honouring any --config override in args.

    Args:
        args: Parsed argparse namespace which may contain a 'config' attribute.

    Returns:
        A fully parsed AudioConfig.

    Raises:
        FileNotFoundError: If the config file does not exist at the resolved path.
    """
    config_path: Path | None = Path(args.config) if args.config else None
    return load_config(config_path)


def _resolve_output_root(args: argparse.Namespace, config: AudioConfig) -> Path:
    """Determine the output root directory from CLI args or config.

    CLI --output overrides config.output.output_dir.

    Args:
        args: Parsed argparse namespace which may contain an 'output' attribute.
        config: The loaded AudioConfig.

    Returns:
        A Path for the output root (may not yet exist on disk).
    """
    if args.output:
        return Path(args.output)
    return Path(config.output.output_dir)


def _build_config_with_overrides(args: argparse.Namespace, config: AudioConfig) -> AudioConfig:
    """Return a new AudioConfig with CLI flag overrides applied.

    CLI flags override YAML config values so ad-hoc invocations do not require
    editing the config file. Only non-None values from args replace the config —
    unset flags (None) leave the loaded config value intact.

    Args:
        args: Parsed argparse namespace.
        config: The base loaded AudioConfig.

    Returns:
        A new AudioConfig with CLI overrides applied.
    """
    from dataclasses import replace

    updated_engine = replace(
        config.engine,
        engine=args.engine if args.engine is not None else config.engine.engine,
        model=args.model if args.model is not None else config.engine.model,
        language=args.language if args.language is not None else config.engine.language,
    )
    updated_output = replace(
        config.output,
        output_mode=args.output_mode if args.output_mode is not None else config.output.output_mode,
        pause_threshold=args.pause_threshold if args.pause_threshold is not None else config.output.pause_threshold,
    )
    updated_diarization = replace(
        config.diarization,
        diarize=args.diarize if args.diarize is not None else config.diarization.diarize,
    )
    updated_filler = replace(
        config.filler,
        remove_fillers=args.remove_fillers if args.remove_fillers is not None else config.filler.remove_fillers,
    )

    return replace(
        config,
        engine=updated_engine,
        output=updated_output,
        diarization=updated_diarization,
        filler=updated_filler,
    )


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------


def cmd_transcribe(args: argparse.Namespace) -> None:
    """Transcribe audio files and generate markdown output.

    This is the main operation. Loads config, applies CLI overrides, initializes
    the DB, creates the transcription engine, runs batch processing, optionally
    generates LLM aggregate files, and prints a summary.

    Exits with code 0 on full success, 1 when all files errored, and 2 when
    some files succeeded and some errored (partial failure).

    Args:
        args: Parsed argparse namespace containing all transcription flags.
    """
    config = _load_config_from_args(args)
    config = _build_config_with_overrides(args, config)

    issues = validate_config(config)
    if issues:
        for config_issue in issues:
            print(f"  WARNING: {config_issue}", file=sys.stderr)

    input_path = Path(args.input)
    output_root = _resolve_output_root(args, config)

    if args.dry_run:
        print(f"[dry-run] Input:  {input_path}")
        print(f"[dry-run] Output: {output_root}")
        print(f"[dry-run] Engine: {config.engine.engine} ({config.engine.model})")

    # Initialize DB
    from deep_thought.audio.db.schema import initialize_database

    conn = initialize_database()

    # Create engine
    from deep_thought.audio.engines import create_engine

    transcription_engine = create_engine(
        config.engine.engine,
        config.engine.model,
        config.limits.chunk_duration_minutes,
    )

    # Run batch processing
    from deep_thought.audio.processor import process_batch

    results = process_batch(
        input_path,
        config,
        conn,
        output_root,
        engine=transcription_engine,
        dry_run=args.dry_run,
        force=args.force,
        nuke=args.nuke,
    )

    conn.commit()
    conn.close()

    if not results:
        print("No audio files found.")
        sys.exit(0)

    # Generate LLM aggregate files if configured (or --llm flag) and processing produced output
    successful_results = [result for result in results if result.status == "success"]
    generate_llms = args.llm if args.llm is not None else config.output.generate_llms_files
    if generate_llms and successful_results and not args.dry_run:
        from deep_thought.audio.llms import (
            TranscriptSummary,
            _strip_frontmatter,  # noqa: PLC2701
            write_llms_full,
            write_llms_index,
        )

        summaries: list[TranscriptSummary] = []
        for successful_result in successful_results:
            if successful_result.output_path is not None:
                md_files = list(successful_result.output_path.glob("*.md"))
                for md_file in md_files:
                    raw_content = md_file.read_text(encoding="utf-8")
                    content = _strip_frontmatter(raw_content)
                    try:
                        md_relative = md_file.relative_to(output_root).as_posix()
                    except ValueError:
                        md_relative = md_file.name
                    summaries.append(
                        TranscriptSummary(
                            name=successful_result.source_path.stem,
                            md_relative_path=md_relative,
                            source_file=successful_result.source_path.name,
                            duration_seconds=successful_result.duration_seconds,
                            word_count=len(content.split()),
                            content=content,
                        )
                    )

        if summaries:
            llms_full_path = write_llms_full(summaries, output_root)
            llms_index_path = write_llms_index(summaries, output_root)
            print(f"  LLM full:  {llms_full_path}")
            print(f"  LLM index: {llms_index_path}")

    # Print summary
    success_count = sum(1 for result in results if result.status == "success")
    skipped_count = sum(1 for result in results if result.status == "skipped")
    error_count = sum(1 for result in results if result.status == "error")

    dry_prefix = "[dry-run] " if args.dry_run else ""
    print(f"{dry_prefix}Processing complete:")
    print(f"  Success: {success_count}")
    print(f"  Skipped: {skipped_count}")
    print(f"  Errors:  {error_count}")

    # Exit codes: 0 = all ok, 1 = all errored, 2 = partial failure (some ok + some errored)
    if error_count > 0 and success_count > 0:
        sys.exit(2)
    elif error_count > 0:
        sys.exit(1)


def cmd_config(args: argparse.Namespace) -> None:
    """Validate and display the current configuration.

    Any validation issues are listed before the config values so they are
    immediately visible. Exits with code 0 even when there are warnings —
    the tool can still run with a questionable config; we just surface it.

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
    print(f"  engine:                {config.engine.engine}")
    print(f"  model:                 {config.engine.model}")
    print(f"  language:              {config.engine.language or '(auto-detect)'}")
    print()
    print(f"  output_mode:           {config.output.output_mode}")
    print(f"  pause_threshold:       {config.output.pause_threshold}")
    print(f"  output_dir:            {config.output.output_dir}")
    print(f"  generate_llms_files:   {config.output.generate_llms_files}")
    print()
    print(f"  diarize:               {config.diarization.diarize}")
    print(f"  hf_token_env:          {config.diarization.hf_token_env}")
    print()
    print(f"  remove_fillers:        {config.filler.remove_fillers}")
    print()
    print(f"  max_file_size_mb:      {config.limits.max_file_size_mb}")
    print(f"  chunk_duration_minutes: {config.limits.chunk_duration_minutes}")
    print()
    print("  Hallucination detection:")
    print(f"    score_threshold:     {config.hallucination.score_threshold}")
    print(f"    action:              {config.hallucination.action}")
    print(f"    use_vad:             {config.hallucination.use_vad}")
    print(f"    blocklist_enabled:   {config.hallucination.blocklist_enabled}")


def cmd_init(args: argparse.Namespace) -> None:
    """Create configuration file, output directory, and database.

    Writes the bundled default config to the standard location (or --save-config
    path), creates the output directory, and initialises the SQLite database.

    Args:
        args: Parsed argparse namespace.
    """
    destination_path: Path = Path(args.save_config) if args.save_config else get_default_config_path()

    try:
        save_default_config(destination_path)
        print(f"Configuration written to: {destination_path}")
    except FileExistsError:
        print(f"Configuration already exists at: {destination_path}")

    config = load_config(destination_path)
    output_dir = Path(config.output.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"Output directory ready:   {output_dir}")

    # Initialize database
    from deep_thought.audio.db.schema import get_data_dir, initialize_database

    db_conn = initialize_database()
    db_conn.close()
    print(f"Database initialized:     {get_data_dir() / 'audio.db'}")

    print()
    print("Next steps:")
    print(f"  1. Review configuration:  {destination_path}")
    print("  2. Run: audio --input <path-to-audio-files>")


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def _add_transcribe_arguments(parser: argparse.ArgumentParser) -> None:
    """Attach all transcription flags to a parser.

    Shared between the root-level fallback and the explicit 'transcribe'
    subcommand parser so both paths expose identical flags.

    Args:
        parser: The parser to add arguments to.
    """
    parser.add_argument(
        "--input",
        metavar="PATH",
        default="input/",
        help="Input file or directory (default: input/).",
    )
    parser.add_argument(
        "--output",
        metavar="PATH",
        default=None,
        help="Output directory.",
    )
    parser.add_argument(
        "--engine",
        choices=["mlx", "whisper", "auto"],
        default=None,
        help="Transcription engine.",
    )
    parser.add_argument(
        "--model",
        choices=["tiny", "base", "small", "medium", "large-v3", "large-v3-turbo"],
        default=None,
        help="Whisper model size.",
    )
    parser.add_argument(
        "--language",
        metavar="TEXT",
        default=None,
        help="Force language code (e.g., en, fr).",
    )
    parser.add_argument(
        "--output-mode",
        choices=["paragraph", "segment", "timestamp"],
        default=None,
        help="Transcript format.",
    )
    parser.add_argument(
        "--diarize",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Enable speaker identification (--no-diarize to disable).",
    )
    parser.add_argument(
        "--pause-threshold",
        type=float,
        default=None,
        metavar="SECS",
        help="Pause duration for paragraph breaks.",
    )
    parser.add_argument(
        "--remove-fillers",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Strip filler words (--no-remove-fillers to disable).",
    )
    parser.add_argument(
        "--llm",
        action="store_true",
        default=None,
        help="Generate .llms.txt and .llms-full.txt aggregate files (overrides config).",
    )
    parser.add_argument(
        "--nuke",
        action="store_true",
        default=False,
        help="Delete input files after successful processing.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Preview without processing.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Reprocess files even if already in DB.",
    )


def _build_argument_parser() -> argparse.ArgumentParser:
    """Construct and return the top-level argument parser with all subcommands.

    Returns:
        A fully configured argparse.ArgumentParser instance.
    """
    root_parser = argparse.ArgumentParser(
        prog="audio",
        description="Transcribe audio files to LLM-optimized markdown.",
    )

    root_parser.add_argument(
        "--version",
        action="version",
        version=f"audio {_VERSION}",
    )
    root_parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        default=False,
        help="Detailed logging.",
    )
    root_parser.add_argument(
        "--config",
        metavar="PATH",
        default=None,
        help="Override config file path.",
    )

    subparsers = root_parser.add_subparsers(dest="subcommand", metavar="<command>")

    # Transcribe subcommand (explicit)
    transcribe_parser = subparsers.add_parser(
        "transcribe",
        help="Transcribe audio files (default operation).",
    )
    _add_transcribe_arguments(transcribe_parser)

    # Config subcommand
    subparsers.add_parser(
        "config",
        help="Validate and display the current YAML configuration.",
    )

    # Init subcommand
    init_parser = subparsers.add_parser(
        "init",
        help="Create config file, output directory, and database.",
    )
    init_parser.add_argument(
        "--save-config",
        metavar="PATH",
        default=None,
        help="Write config to this path instead of the default location.",
    )

    return root_parser


def _build_root_parser_with_transcribe_defaults() -> argparse.ArgumentParser:
    """Build a parser that accepts transcribe flags directly at the root level.

    When no subcommand is provided, audio treats all top-level flag arguments
    as transcription arguments. This parser is used for that fallback path.

    Returns:
        A fully configured argparse.ArgumentParser for root-level transcription.
    """
    root_parser = argparse.ArgumentParser(
        prog="audio",
        description="Transcribe audio files to LLM-optimized markdown.",
        add_help=False,
    )

    root_parser.add_argument("--version", action="version", version=f"audio {_VERSION}")
    root_parser.add_argument("--verbose", "-v", action="store_true", default=False)
    root_parser.add_argument("--config", metavar="PATH", default=None)

    _add_transcribe_arguments(root_parser)

    return root_parser


# ---------------------------------------------------------------------------
# Command dispatch table
# ---------------------------------------------------------------------------

_COMMAND_HANDLERS: dict[str, Any] = {
    "transcribe": cmd_transcribe,
    "config": cmd_config,
    "init": cmd_init,
}


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Parse arguments and dispatch to the appropriate command handler.

    When no subcommand is given, the tool operates in transcription mode,
    treating all flags as transcription arguments. This mirrors the behaviour
    of tools like ffmpeg and pandoc.

    Wraps each handler in consistent error handling so all user-facing
    failures exit with a clear message.
    """
    argument_parser = _build_argument_parser()
    args, _remaining = argument_parser.parse_known_args()

    _setup_logging(args.verbose)

    if _remaining and args.subcommand is not None:
        logger.warning("Unrecognized arguments ignored: %s", " ".join(_remaining))

    if args.subcommand is None:
        # No subcommand: re-parse the full argv as a direct transcription call
        fallback_parser = _build_root_parser_with_transcribe_defaults()
        args = fallback_parser.parse_args()
        args.subcommand = "transcribe"

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


# Expose parser and handlers for test introspection
__all__ = [
    "main",
    "cmd_transcribe",
    "cmd_config",
    "cmd_init",
    "_build_argument_parser",
    "_COMMAND_HANDLERS",
]
