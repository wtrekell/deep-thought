"""Audio processing pipeline orchestrator.

Coordinates the full transcription pipeline: filtering, transcription,
diarization, hallucination detection, output formatting, and database
state tracking.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import sqlite3
    from pathlib import Path

    from deep_thought.audio.config import AudioConfig
    from deep_thought.audio.engines import TranscriptionEngine
    from deep_thought.audio.hallucination import HallucinationScore
    from deep_thought.audio.models import TranscriptionResult

logger = logging.getLogger(__name__)


@dataclass
class ProcessResult:
    """Result from processing a single audio file."""

    source_path: Path
    output_path: Path | None = None
    status: str = "pending"  # "success", "error", "skipped"
    skip_reason: str | None = None
    duration_seconds: float = 0.0
    speaker_count: int = 0
    language: str = "unknown"
    hallucination_scores: list[HallucinationScore] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _now_utc_iso() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(UTC).isoformat()


def _save_snapshot(
    transcription_result: TranscriptionResult,
    hallucination_scores: list[HallucinationScore],
    source_path: Path,
    snapshots_dir: Path,
) -> Path:
    """Save raw engine output and hallucination scores as a JSON snapshot.

    Creates snapshots_dir if needed. File is named by ISO timestamp.

    Args:
        transcription_result: The raw output from the transcription engine.
        hallucination_scores: Scored results from hallucination detection.
        source_path: The original audio file path (recorded in the snapshot).
        snapshots_dir: Directory to write snapshot files into.

    Returns:
        Path to the saved snapshot file.
    """
    snapshots_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H%M%S")
    snapshot_path = snapshots_dir / f"{timestamp}.json"

    snapshot_data: dict[str, Any] = {
        "source_file": str(source_path),
        "language": transcription_result.language,
        "duration_seconds": transcription_result.duration_seconds,
        "segments": [
            {
                "start": seg.start,
                "end": seg.end,
                "text": seg.text,
                "confidence": seg.confidence,
                "no_speech_prob": seg.no_speech_prob,
                "compression_ratio": seg.compression_ratio,
                "speaker": seg.speaker,
            }
            for seg in transcription_result.segments
        ],
        "hallucination_scores": [
            {
                "segment_index": hallucination_score.segment_index,
                "layer_scores": hallucination_score.layer_scores,
                "total_score": hallucination_score.total_score,
                "action_taken": hallucination_score.action_taken,
            }
            for hallucination_score in hallucination_scores
        ],
    }

    snapshot_path.write_text(json.dumps(snapshot_data, indent=2), encoding="utf-8")
    logger.debug("Snapshot saved: %s", snapshot_path)
    return snapshot_path


def process_file(
    source_path: Path,
    config: AudioConfig,
    conn: sqlite3.Connection,
    output_root: Path,
    *,
    engine: TranscriptionEngine,
    dry_run: bool = False,
    force: bool = False,
) -> ProcessResult:
    """Process a single audio file through the full transcription pipeline.

    Pipeline steps:
    1. Compute file hash
    2. Run filters (extension, size, empty, duplicate — unless force=True)
    3. If dry_run, return early with skip_reason="dry-run"
    4. Transcribe via engine
    5. Save raw snapshot with hallucination scores
    6. Optionally run diarization
    7. Run hallucination detection
    8. Apply filler removal if configured
    9. Write markdown output with frontmatter
    10. Upsert to database
    11. Return ProcessResult

    Per-file errors are caught and recorded — they do not halt batch processing.

    Args:
        source_path: Path to the audio file to process.
        config: Loaded AudioConfig controlling all pipeline behaviour.
        conn: Open SQLite connection for recording results.
        output_root: Root directory where markdown output is written.
        engine: Transcription engine to use for this file.
        dry_run: If True, skip actual processing and return a "dry-run" skip.
        force: If True, bypass the duplicate-hash filter and reprocess.

    Returns:
        A ProcessResult describing the outcome for this file.
    """
    result = ProcessResult(source_path=source_path)

    try:
        # Step 1: Hash
        from deep_thought.audio.filters import check_file, compute_file_hash

        file_hash = compute_file_hash(source_path)

        # Step 2: Filters (skip if --force)
        if not force:
            passed, skip_reason = check_file(source_path, file_hash, config.limits.max_file_size_mb, conn)
            if not passed:
                result.status = "skipped"
                result.skip_reason = skip_reason
                # Record skip in DB so we have a history of skipped files
                from deep_thought.audio.db.queries import upsert_processed_file

                upsert_processed_file(
                    conn,
                    {
                        "file_path": str(source_path),
                        "file_hash": file_hash,
                        "engine": config.engine.engine,
                        "model": config.engine.model,
                        "duration_seconds": 0.0,
                        "speaker_count": 0,
                        "output_path": "",
                        "status": "skipped",
                        "created_at": _now_utc_iso(),
                        "updated_at": _now_utc_iso(),
                    },
                )
                return result

        # Step 3: Dry run
        if dry_run:
            result.status = "skipped"
            result.skip_reason = "dry-run"
            return result

        # Step 4: Transcribe
        logger.info("Transcribing: %s", source_path)
        transcription_result = engine.transcribe(source_path, language=config.engine.language)
        result.duration_seconds = transcription_result.duration_seconds
        result.language = transcription_result.language

        # Step 5 (snapshot) is deferred until after hallucination detection
        # so the snapshot captures both raw segments and scores together.

        # Step 6: Diarization (optional)
        segments = transcription_result.segments
        if config.diarization.diarize:
            try:
                from deep_thought.audio.diarization import (
                    diarize,
                    load_diarization_pipeline,
                    merge_transcript_with_speakers,
                )

                diarization_pipeline = load_diarization_pipeline(config.diarization.hf_token_env)
                speaker_segments = diarize(source_path, diarization_pipeline)
                segments = merge_transcript_with_speakers(segments, speaker_segments)
                result.speaker_count = len({speaker_seg.speaker_label for speaker_seg in speaker_segments})
            except (ImportError, OSError) as diarize_error:
                logger.warning("Diarization failed: %s. Continuing without speaker labels.", diarize_error)
                result.errors.append(f"Diarization failed: {diarize_error}")

        # Step 7: Hallucination detection
        from deep_thought.audio.hallucination import apply_hallucination_detection

        hal_config = config.hallucination
        filtered_segments, hallucination_scores = apply_hallucination_detection(
            segments,
            repetition_threshold=hal_config.repetition_threshold,
            compression_ratio_threshold=hal_config.compression_ratio_threshold,
            confidence_floor=hal_config.confidence_floor,
            no_speech_prob_threshold=hal_config.no_speech_prob_threshold,
            duration_chars_per_sec_max=hal_config.duration_chars_per_sec_max,
            duration_chars_per_sec_min=hal_config.duration_chars_per_sec_min,
            blocklist_enabled=hal_config.blocklist_enabled,
            score_threshold=hal_config.score_threshold,
            action=hal_config.action,
        )
        result.hallucination_scores = hallucination_scores

        # Step 5: Save snapshot (includes raw segments + hallucination scores)
        from deep_thought.audio.db.schema import get_data_dir

        snapshots_dir = get_data_dir() / "snapshots"
        _save_snapshot(transcription_result, hallucination_scores, source_path, snapshots_dir)

        # Step 8: Filler removal (mutates segment text — pipeline-internal copies only)
        if config.filler.remove_fillers:
            from deep_thought.audio.output import remove_fillers

            for seg in filtered_segments:
                seg.text = remove_fillers(seg.text)

        # Step 9: Write markdown output
        from deep_thought.audio.output import write_transcript

        output_file = write_transcript(
            filtered_segments,
            source_path,
            output_root,
            engine=config.engine.engine,
            model=config.engine.model,
            language=transcription_result.language,
            duration_seconds=transcription_result.duration_seconds,
            speaker_count=result.speaker_count,
            output_mode=config.output.output_mode,
            pause_threshold=config.output.pause_threshold,
        )
        result.output_path = output_file.parent  # directory containing the markdown file

        # Step 10: Upsert to database
        from deep_thought.audio.db.queries import upsert_processed_file

        now = _now_utc_iso()
        upsert_processed_file(
            conn,
            {
                "file_path": str(source_path),
                "file_hash": file_hash,
                "engine": config.engine.engine,
                "model": config.engine.model,
                "duration_seconds": transcription_result.duration_seconds,
                "speaker_count": result.speaker_count,
                "output_path": str(result.output_path),
                "status": "success",
                "created_at": now,
                "updated_at": now,
            },
        )

        result.status = "success"
        logger.info("Successfully processed: %s", source_path)

    except Exception as pipeline_error:
        result.status = "error"
        result.errors.append(str(pipeline_error))
        logger.error("Error processing %s: %s", source_path, pipeline_error, exc_info=True)

        # Attempt to record the error in the DB so it appears in status queries
        try:
            from deep_thought.audio.db.queries import upsert_processed_file
            from deep_thought.audio.filters import compute_file_hash

            upsert_processed_file(
                conn,
                {
                    "file_path": str(source_path),
                    "file_hash": compute_file_hash(source_path),
                    "engine": config.engine.engine,
                    "model": config.engine.model,
                    "duration_seconds": 0.0,
                    "speaker_count": 0,
                    "output_path": "",
                    "status": "error",
                    "created_at": _now_utc_iso(),
                    "updated_at": _now_utc_iso(),
                },
            )
        except Exception:
            logger.debug("Could not record error state in database", exc_info=True)

    return result


def process_batch(
    input_path: Path,
    config: AudioConfig,
    conn: sqlite3.Connection,
    output_root: Path,
    *,
    engine: TranscriptionEngine,
    dry_run: bool = False,
    force: bool = False,
    nuke: bool = False,
) -> list[ProcessResult]:
    """Process all audio files found at input_path.

    Walks input_path (file or directory) to collect audio files, then runs
    each through process_file. The nuke flag deletes source files only after
    a confirmed success — errors and dry-run mode never trigger deletion.

    Args:
        input_path: File or directory containing audio files to process.
        config: Loaded AudioConfig controlling all pipeline behaviour.
        conn: Open SQLite connection for recording results.
        output_root: Root directory where markdown output is written.
        engine: Transcription engine to use for each file.
        dry_run: If True, show what would be processed without doing it.
        force: If True, reprocess files even if already recorded in the DB.
        nuke: If True, delete source files after each successful processing run.

    Returns:
        List of ProcessResult, one per file attempted. Empty list if no files found.
    """
    from deep_thought.audio.filters import collect_input_files

    input_files = collect_input_files(input_path)

    if not input_files:
        logger.info("No audio files found in: %s", input_path)
        return []

    logger.info("Found %d audio file(s) to process", len(input_files))
    results: list[ProcessResult] = []

    for source_file in input_files:
        file_result = process_file(
            source_file,
            config,
            conn,
            output_root,
            engine=engine,
            dry_run=dry_run,
            force=force,
        )
        results.append(file_result)

        # Delete source file only on confirmed success — never on error or dry-run
        if nuke and not dry_run and file_result.status == "success":
            try:
                source_file.unlink()
                logger.debug("Deleted source file: %s", source_file)
            except OSError as delete_error:
                logger.warning("Could not delete %s: %s", source_file, delete_error)

    return results
