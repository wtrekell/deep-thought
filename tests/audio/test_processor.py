"""Tests for the audio processing pipeline orchestrator in deep_thought.audio.processor."""

from __future__ import annotations

import json
from pathlib import Path  # noqa: TC003
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from deep_thought.audio.hallucination import HallucinationScore
from deep_thought.audio.models import TranscriptionResult, TranscriptSegment
from deep_thought.audio.processor import ProcessResult, _save_snapshot, process_batch, process_file

if TYPE_CHECKING:
    import sqlite3

    from deep_thought.audio.config import AudioConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_transcription_result(
    text: str = "Hello world.",
    language: str = "en",
    duration_seconds: float = 10.0,
) -> TranscriptionResult:
    """Return a TranscriptionResult with sensible test defaults."""
    segment = TranscriptSegment(start=0.0, end=duration_seconds, text=text)
    return TranscriptionResult(segments=[segment], language=language, duration_seconds=duration_seconds)


def _make_hallucination_score(segment_index: int = 0) -> HallucinationScore:
    """Return a HallucinationScore with sensible test defaults."""
    return HallucinationScore(segment_index=segment_index, layer_scores={}, total_score=0.0, action_taken="none")


def _make_mock_engine(transcription_result: TranscriptionResult | None = None) -> MagicMock:
    """Return a mock TranscriptionEngine that returns a preset result."""
    mock_engine = MagicMock()
    mock_engine.transcribe.return_value = transcription_result or _make_transcription_result()
    return mock_engine


# ---------------------------------------------------------------------------
# TestSaveSnapshot
# ---------------------------------------------------------------------------


class TestSaveSnapshot:
    def test_creates_json_file_in_snapshots_dir(self, tmp_path: Path) -> None:
        """_save_snapshot() must create a JSON file inside the given directory."""
        snapshots_dir = tmp_path / "snapshots"
        transcription_result = _make_transcription_result()

        snapshot_path = _save_snapshot(transcription_result, [], Path("audio.mp3"), snapshots_dir)

        assert snapshot_path.exists()
        assert snapshot_path.suffix == ".json"

    def test_snapshot_contains_segments_and_hallucination_scores(self, tmp_path: Path) -> None:
        """The snapshot JSON must include both segment data and hallucination score data."""
        snapshots_dir = tmp_path / "snapshots"
        transcription_result = _make_transcription_result(text="Test speech.", duration_seconds=5.0)
        hallucination_scores = [_make_hallucination_score(segment_index=0)]

        snapshot_path = _save_snapshot(transcription_result, hallucination_scores, Path("audio.mp3"), snapshots_dir)

        snapshot_data = json.loads(snapshot_path.read_text(encoding="utf-8"))
        assert len(snapshot_data["segments"]) == 1
        assert snapshot_data["segments"][0]["text"] == "Test speech."
        assert len(snapshot_data["hallucination_scores"]) == 1
        assert snapshot_data["hallucination_scores"][0]["segment_index"] == 0

    def test_creates_snapshots_dir_if_it_does_not_exist(self, tmp_path: Path) -> None:
        """_save_snapshot() must create the snapshots directory if it is missing."""
        snapshots_dir = tmp_path / "deeply" / "nested" / "snapshots"
        assert not snapshots_dir.exists()

        _save_snapshot(_make_transcription_result(), [], Path("audio.mp3"), snapshots_dir)

        assert snapshots_dir.exists()

    def test_snapshot_records_source_file_path(self, tmp_path: Path) -> None:
        """The snapshot must record the source audio file path."""
        snapshots_dir = tmp_path / "snapshots"
        source_path = Path("/recordings/meeting.mp3")

        snapshot_path = _save_snapshot(_make_transcription_result(), [], source_path, snapshots_dir)

        snapshot_data = json.loads(snapshot_path.read_text(encoding="utf-8"))
        assert snapshot_data["source_file"] == str(source_path)

    def test_snapshot_records_language_and_duration(self, tmp_path: Path) -> None:
        """The snapshot must record the detected language and duration."""
        snapshots_dir = tmp_path / "snapshots"
        transcription_result = _make_transcription_result(language="fr", duration_seconds=42.0)

        snapshot_path = _save_snapshot(transcription_result, [], Path("audio.mp3"), snapshots_dir)

        snapshot_data = json.loads(snapshot_path.read_text(encoding="utf-8"))
        assert snapshot_data["language"] == "fr"
        assert snapshot_data["duration_seconds"] == 42.0


# ---------------------------------------------------------------------------
# TestProcessFile
#
# The processor uses inline imports (from X import Y inside the function body).
# Patch targets must reference the *source* module where each name is defined,
# not "deep_thought.audio.processor.*", because inline imports look up the
# name in sys.modules at call time rather than binding it at module level.
# ---------------------------------------------------------------------------


class TestProcessFile:
    def test_successful_processing_returns_success_status(
        self, sample_config: AudioConfig, in_memory_db: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """A file that passes all pipeline steps must produce status='success'."""
        audio_file = tmp_path / "interview.wav"
        audio_file.write_bytes(b"fake audio data")
        output_root = tmp_path / "output"
        mock_engine = _make_mock_engine()

        with (
            patch("deep_thought.audio.filters.compute_file_hash", return_value="abc123"),
            patch("deep_thought.audio.filters.check_file", return_value=(True, "")),
            patch("deep_thought.audio.hallucination.apply_hallucination_detection") as mock_hal,
            patch("deep_thought.audio.output.write_transcript") as mock_write,
            patch("deep_thought.audio.db.queries.upsert_processed_file"),
            patch("deep_thought.audio.db.schema.get_data_dir", return_value=tmp_path),
            patch("deep_thought.audio.processor._save_snapshot"),
        ):
            mock_hal.return_value = (mock_engine.transcribe.return_value.segments, [])
            output_md = output_root / "interview" / "interview.md"
            mock_write.return_value = output_md

            result = process_file(
                audio_file,
                sample_config,
                in_memory_db,
                output_root,
                engine=mock_engine,
            )

        assert result.status == "success"
        assert result.source_path == audio_file

    def test_file_that_fails_filter_check_returns_skipped(
        self, sample_config: AudioConfig, in_memory_db: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """A file rejected by check_file must return status='skipped' with a reason."""
        audio_file = tmp_path / "interview.wav"
        audio_file.write_bytes(b"fake audio data")

        with (
            patch("deep_thought.audio.filters.compute_file_hash", return_value="abc123"),
            patch("deep_thought.audio.filters.check_file", return_value=(False, "Already processed")),
            patch("deep_thought.audio.db.queries.upsert_processed_file"),
        ):
            result = process_file(
                audio_file,
                sample_config,
                in_memory_db,
                tmp_path / "output",
                engine=_make_mock_engine(),
            )

        assert result.status == "skipped"
        assert result.skip_reason == "Already processed"

    def test_dry_run_returns_skipped_with_dry_run_reason(
        self, sample_config: AudioConfig, in_memory_db: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """With dry_run=True the pipeline must stop after filter checks and report 'dry-run'."""
        audio_file = tmp_path / "interview.wav"
        audio_file.write_bytes(b"fake audio data")

        with (
            patch("deep_thought.audio.filters.compute_file_hash", return_value="abc123"),
            patch("deep_thought.audio.filters.check_file", return_value=(True, "")),
        ):
            result = process_file(
                audio_file,
                sample_config,
                in_memory_db,
                tmp_path / "output",
                engine=_make_mock_engine(),
                dry_run=True,
            )

        assert result.status == "skipped"
        assert result.skip_reason == "dry-run"

    def test_force_flag_bypasses_duplicate_filter(
        self, sample_config: AudioConfig, in_memory_db: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """With force=True, check_file must not be called even for known files."""
        audio_file = tmp_path / "interview.wav"
        audio_file.write_bytes(b"fake audio data")
        mock_engine = _make_mock_engine()

        with (
            patch("deep_thought.audio.filters.compute_file_hash", return_value="abc123"),
            patch("deep_thought.audio.filters.check_file") as mock_check,
            patch("deep_thought.audio.hallucination.apply_hallucination_detection") as mock_hal,
            patch("deep_thought.audio.output.write_transcript") as mock_write,
            patch("deep_thought.audio.db.queries.upsert_processed_file"),
            patch("deep_thought.audio.db.schema.get_data_dir", return_value=tmp_path),
            patch("deep_thought.audio.processor._save_snapshot"),
        ):
            mock_hal.return_value = (mock_engine.transcribe.return_value.segments, [])
            mock_write.return_value = tmp_path / "output" / "interview" / "interview.md"

            process_file(
                audio_file,
                sample_config,
                in_memory_db,
                tmp_path / "output",
                engine=mock_engine,
                force=True,
            )

        mock_check.assert_not_called()

    def test_transcription_error_is_caught_and_recorded_as_error_status(
        self, sample_config: AudioConfig, in_memory_db: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """An exception during transcription must produce status='error' without propagating."""
        audio_file = tmp_path / "interview.wav"
        audio_file.write_bytes(b"fake audio data")
        mock_engine = MagicMock()
        mock_engine.transcribe.side_effect = RuntimeError("Engine crashed")

        with (
            patch("deep_thought.audio.filters.compute_file_hash", return_value="abc123"),
            patch("deep_thought.audio.filters.check_file", return_value=(True, "")),
            patch("deep_thought.audio.db.queries.upsert_processed_file"),
        ):
            result = process_file(
                audio_file,
                sample_config,
                in_memory_db,
                tmp_path / "output",
                engine=mock_engine,
            )

        assert result.status == "error"
        assert any("Engine crashed" in error_message for error_message in result.errors)

    def test_diarization_error_is_caught_but_processing_continues(
        self, sample_config: AudioConfig, in_memory_db: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """A diarization failure must be recorded as a warning but not abort the pipeline."""
        from dataclasses import replace

        diarize_config = replace(sample_config, diarization=replace(sample_config.diarization, diarize=True))
        audio_file = tmp_path / "interview.wav"
        audio_file.write_bytes(b"fake audio data")
        mock_engine = _make_mock_engine()

        with (
            patch("deep_thought.audio.filters.compute_file_hash", return_value="abc123"),
            patch("deep_thought.audio.filters.check_file", return_value=(True, "")),
            patch(
                "deep_thought.audio.diarization.load_diarization_pipeline",
                side_effect=ImportError("pyannote not installed"),
            ),
            patch("deep_thought.audio.hallucination.apply_hallucination_detection") as mock_hal,
            patch("deep_thought.audio.output.write_transcript") as mock_write,
            patch("deep_thought.audio.db.queries.upsert_processed_file"),
            patch("deep_thought.audio.db.schema.get_data_dir", return_value=tmp_path),
            patch("deep_thought.audio.processor._save_snapshot"),
        ):
            mock_hal.return_value = (mock_engine.transcribe.return_value.segments, [])
            mock_write.return_value = tmp_path / "output" / "interview" / "interview.md"

            result = process_file(
                audio_file,
                diarize_config,
                in_memory_db,
                tmp_path / "output",
                engine=mock_engine,
            )

        # Processing must still succeed despite diarization failure
        assert result.status == "success"
        assert any("Diarization failed" in error_message for error_message in result.errors)

    def test_hallucination_detection_is_called_with_correct_config_params(
        self, sample_config: AudioConfig, in_memory_db: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """apply_hallucination_detection must be called with all config thresholds."""
        audio_file = tmp_path / "interview.wav"
        audio_file.write_bytes(b"fake audio data")
        mock_engine = _make_mock_engine()

        with (
            patch("deep_thought.audio.filters.compute_file_hash", return_value="abc123"),
            patch("deep_thought.audio.filters.check_file", return_value=(True, "")),
            patch("deep_thought.audio.hallucination.apply_hallucination_detection") as mock_hal,
            patch("deep_thought.audio.output.write_transcript") as mock_write,
            patch("deep_thought.audio.db.queries.upsert_processed_file"),
            patch("deep_thought.audio.db.schema.get_data_dir", return_value=tmp_path),
            patch("deep_thought.audio.processor._save_snapshot"),
        ):
            mock_hal.return_value = (mock_engine.transcribe.return_value.segments, [])
            mock_write.return_value = tmp_path / "output" / "interview" / "interview.md"

            process_file(
                audio_file,
                sample_config,
                in_memory_db,
                tmp_path / "output",
                engine=mock_engine,
            )

        hal_config = sample_config.hallucination
        mock_hal.assert_called_once_with(
            mock_engine.transcribe.return_value.segments,
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

    def test_filler_removal_is_applied_when_configured(
        self, sample_config: AudioConfig, in_memory_db: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """remove_fillers must be called on each segment text when the filler flag is set."""
        from dataclasses import replace

        filler_config = replace(sample_config, filler=replace(sample_config.filler, remove_fillers=True))
        audio_file = tmp_path / "interview.wav"
        audio_file.write_bytes(b"fake audio data")
        mock_engine = _make_mock_engine(_make_transcription_result(text="Um, hello world. Uh, yes."))

        with (
            patch("deep_thought.audio.filters.compute_file_hash", return_value="abc123"),
            patch("deep_thought.audio.filters.check_file", return_value=(True, "")),
            patch("deep_thought.audio.hallucination.apply_hallucination_detection") as mock_hal,
            patch("deep_thought.audio.output.remove_fillers") as mock_remove_fillers,
            patch("deep_thought.audio.output.write_transcript") as mock_write,
            patch("deep_thought.audio.db.queries.upsert_processed_file"),
            patch("deep_thought.audio.db.schema.get_data_dir", return_value=tmp_path),
            patch("deep_thought.audio.processor._save_snapshot"),
        ):
            mock_hal.return_value = (mock_engine.transcribe.return_value.segments, [])
            mock_remove_fillers.return_value = "hello world. yes."
            mock_write.return_value = tmp_path / "output" / "interview" / "interview.md"

            process_file(
                audio_file,
                filler_config,
                in_memory_db,
                tmp_path / "output",
                engine=mock_engine,
            )

        mock_remove_fillers.assert_called()

    def test_filler_removal_is_not_called_when_disabled(
        self, sample_config: AudioConfig, in_memory_db: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """remove_fillers must not be called when remove_fillers is False in config."""
        audio_file = tmp_path / "interview.wav"
        audio_file.write_bytes(b"fake audio data")
        mock_engine = _make_mock_engine()

        with (
            patch("deep_thought.audio.filters.compute_file_hash", return_value="abc123"),
            patch("deep_thought.audio.filters.check_file", return_value=(True, "")),
            patch("deep_thought.audio.hallucination.apply_hallucination_detection") as mock_hal,
            patch("deep_thought.audio.output.remove_fillers") as mock_remove_fillers,
            patch("deep_thought.audio.output.write_transcript") as mock_write,
            patch("deep_thought.audio.db.queries.upsert_processed_file"),
            patch("deep_thought.audio.db.schema.get_data_dir", return_value=tmp_path),
            patch("deep_thought.audio.processor._save_snapshot"),
        ):
            mock_hal.return_value = (mock_engine.transcribe.return_value.segments, [])
            mock_write.return_value = tmp_path / "output" / "interview" / "interview.md"

            process_file(
                audio_file,
                sample_config,  # remove_fillers=False in sample_config
                in_memory_db,
                tmp_path / "output",
                engine=mock_engine,
            )

        mock_remove_fillers.assert_not_called()

    def test_database_upsert_is_called_with_correct_data_on_success(
        self, sample_config: AudioConfig, in_memory_db: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """upsert_processed_file must be called with status='success' on a successful run."""
        audio_file = tmp_path / "interview.wav"
        audio_file.write_bytes(b"fake audio data")
        mock_engine = _make_mock_engine(_make_transcription_result(duration_seconds=30.0))

        with (
            patch("deep_thought.audio.filters.compute_file_hash", return_value="deadbeef"),
            patch("deep_thought.audio.filters.check_file", return_value=(True, "")),
            patch("deep_thought.audio.hallucination.apply_hallucination_detection") as mock_hal,
            patch("deep_thought.audio.output.write_transcript") as mock_write,
            patch("deep_thought.audio.db.queries.upsert_processed_file") as mock_upsert,
            patch("deep_thought.audio.db.schema.get_data_dir", return_value=tmp_path),
            patch("deep_thought.audio.processor._save_snapshot"),
        ):
            mock_hal.return_value = (mock_engine.transcribe.return_value.segments, [])
            mock_write.return_value = tmp_path / "output" / "interview" / "interview.md"

            process_file(
                audio_file,
                sample_config,
                in_memory_db,
                tmp_path / "output",
                engine=mock_engine,
            )

        # The last upsert call should reflect success
        upsert_calls = mock_upsert.call_args_list
        success_calls = [c for c in upsert_calls if c[0][1].get("status") == "success"]
        assert len(success_calls) == 1
        success_data = success_calls[0][0][1]
        assert success_data["file_hash"] == "deadbeef"
        assert success_data["duration_seconds"] == 30.0
        assert success_data["engine"] == sample_config.engine.engine

    def test_database_upsert_records_error_status_on_failure(
        self, sample_config: AudioConfig, in_memory_db: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """upsert_processed_file must be called with status='error' when transcription fails."""
        audio_file = tmp_path / "interview.wav"
        audio_file.write_bytes(b"fake audio data")
        mock_engine = MagicMock()
        mock_engine.transcribe.side_effect = RuntimeError("Transcription failed")

        with (
            patch("deep_thought.audio.filters.compute_file_hash", return_value="deadbeef"),
            patch("deep_thought.audio.filters.check_file", return_value=(True, "")),
            patch("deep_thought.audio.db.queries.upsert_processed_file") as mock_upsert,
        ):
            process_file(
                audio_file,
                sample_config,
                in_memory_db,
                tmp_path / "output",
                engine=mock_engine,
            )

        upsert_calls = mock_upsert.call_args_list
        error_calls = [c for c in upsert_calls if c[0][1].get("status") == "error"]
        assert len(error_calls) == 1


# ---------------------------------------------------------------------------
# TestProcessBatch
# ---------------------------------------------------------------------------


class TestProcessBatch:
    def test_processes_multiple_files_and_returns_result_for_each(
        self, sample_config: AudioConfig, in_memory_db: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """process_batch must return one ProcessResult per discovered audio file."""
        input_dir = tmp_path / "audio"
        input_dir.mkdir()
        (input_dir / "file_a.wav").write_bytes(b"audio a")
        (input_dir / "file_b.wav").write_bytes(b"audio b")
        output_root = tmp_path / "output"

        mock_result = ProcessResult(source_path=input_dir / "file_a.wav", status="success")

        with patch("deep_thought.audio.processor.process_file", return_value=mock_result) as mock_process:
            results = process_batch(
                input_dir,
                sample_config,
                in_memory_db,
                output_root,
                engine=_make_mock_engine(),
            )

        assert len(results) == 2
        assert mock_process.call_count == 2

    def test_empty_input_returns_empty_list(
        self, sample_config: AudioConfig, in_memory_db: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """When no audio files are found, process_batch must return an empty list."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        results = process_batch(
            empty_dir,
            sample_config,
            in_memory_db,
            tmp_path / "output",
            engine=_make_mock_engine(),
        )

        assert results == []

    def test_nuke_deletes_source_files_after_success(
        self, sample_config: AudioConfig, in_memory_db: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """With nuke=True, successfully processed source files must be deleted."""
        input_dir = tmp_path / "audio"
        input_dir.mkdir()
        audio_file = input_dir / "interview.wav"
        audio_file.write_bytes(b"audio data")
        output_root = tmp_path / "output"

        success_result = ProcessResult(source_path=audio_file, status="success")

        with patch("deep_thought.audio.processor.process_file", return_value=success_result):
            process_batch(
                input_dir,
                sample_config,
                in_memory_db,
                output_root,
                engine=_make_mock_engine(),
                nuke=True,
            )

        assert not audio_file.exists()

    def test_nuke_does_not_delete_files_that_errored(
        self, sample_config: AudioConfig, in_memory_db: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """With nuke=True, files that produced an error status must not be deleted."""
        input_dir = tmp_path / "audio"
        input_dir.mkdir()
        audio_file = input_dir / "broken.wav"
        audio_file.write_bytes(b"audio data")
        output_root = tmp_path / "output"

        error_result = ProcessResult(source_path=audio_file, status="error")

        with patch("deep_thought.audio.processor.process_file", return_value=error_result):
            process_batch(
                input_dir,
                sample_config,
                in_memory_db,
                output_root,
                engine=_make_mock_engine(),
                nuke=True,
            )

        assert audio_file.exists()

    def test_nuke_does_not_delete_files_in_dry_run_mode(
        self, sample_config: AudioConfig, in_memory_db: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """With nuke=True and dry_run=True, no source files must be deleted."""
        input_dir = tmp_path / "audio"
        input_dir.mkdir()
        audio_file = input_dir / "interview.wav"
        audio_file.write_bytes(b"audio data")
        output_root = tmp_path / "output"

        # Even if status reports success, dry_run prevents deletion
        dry_run_result = ProcessResult(source_path=audio_file, status="success")

        with patch("deep_thought.audio.processor.process_file", return_value=dry_run_result):
            process_batch(
                input_dir,
                sample_config,
                in_memory_db,
                output_root,
                engine=_make_mock_engine(),
                nuke=True,
                dry_run=True,
            )

        assert audio_file.exists()

    def test_batch_continues_after_per_file_error(
        self, sample_config: AudioConfig, in_memory_db: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """An error on one file must not prevent the remaining files from being processed."""
        input_dir = tmp_path / "audio"
        input_dir.mkdir()
        (input_dir / "file_a.wav").write_bytes(b"audio a")
        (input_dir / "file_b.wav").write_bytes(b"audio b")
        output_root = tmp_path / "output"

        error_result = ProcessResult(source_path=input_dir / "file_a.wav", status="error")
        success_result = ProcessResult(source_path=input_dir / "file_b.wav", status="success")

        with patch(
            "deep_thought.audio.processor.process_file",
            side_effect=[error_result, success_result],
        ):
            results = process_batch(
                input_dir,
                sample_config,
                in_memory_db,
                output_root,
                engine=_make_mock_engine(),
            )

        assert len(results) == 2
        statuses = {result.status for result in results}
        assert statuses == {"error", "success"}
