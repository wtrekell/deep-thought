"""MLX-Whisper transcription engine for Apple Silicon.

Wraps the mlx-whisper library to produce structured transcription results
from audio files. For long files, the audio is split into chunks via FFmpeg
and transcribed independently, then merged with corrected timestamps.
The mlx-whisper dependency is optional at import time — it is lazily
imported inside the transcribe method so the module can be loaded without it.
"""

from __future__ import annotations

import contextlib
import json
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from deep_thought.audio.models import ChunkResult, TranscriptionResult, TranscriptSegment

logger = logging.getLogger(__name__)

# Maps short model names to mlx-community HuggingFace model IDs
_MODEL_MAP: dict[str, str] = {
    "tiny": "mlx-community/whisper-tiny",
    "base": "mlx-community/whisper-base",
    "small": "mlx-community/whisper-small",
    "medium": "mlx-community/whisper-medium",
    "large-v3": "mlx-community/whisper-large-v3",
    "large-v3-turbo": "mlx-community/whisper-large-v3-turbo",
}


class MlxWhisperEngine:
    """Transcription engine using MLX-Whisper (Apple Silicon optimized).

    Supports automatic chunking of long audio files via FFmpeg.
    """

    def __init__(self, model: str = "large-v3-turbo", chunk_duration_minutes: int = 5) -> None:
        self._model_name = model
        self._model_id = _MODEL_MAP.get(model, model)  # Allow full HF model IDs too
        self._chunk_duration_minutes = chunk_duration_minutes

    def transcribe(self, audio_path: Path, *, language: str | None = None) -> TranscriptionResult:
        """Transcribe an audio file using MLX-Whisper.

        For files longer than chunk_duration_minutes, splits into chunks
        via FFmpeg and transcribes each independently, then merges results.

        Args:
            audio_path: Path to the audio file to transcribe.
            language: Optional BCP-47 language code to force (e.g. "en").
                      When None, language is auto-detected.

        Returns:
            A TranscriptionResult with all segments and detected language.

        Raises:
            ImportError: If mlx-whisper is not installed.
            RuntimeError: If FFmpeg fails to produce chunks.
        """
        import mlx_whisper  # type: ignore[import-untyped]  # Lazy import — may not be installed

        # Get audio duration first
        duration = _get_audio_duration(audio_path)
        chunk_threshold = self._chunk_duration_minutes * 60

        if duration > chunk_threshold:
            return self._transcribe_chunked(audio_path, language=language, total_duration=duration)

        # Single-file transcription
        result: dict[str, Any] = mlx_whisper.transcribe(
            str(audio_path),
            path_or_hf_repo=self._model_id,
            language=language,
            word_timestamps=True,
        )
        segments = _parse_mlx_segments(result.get("segments", []))
        detected_language: str = result.get("language", "unknown")

        return TranscriptionResult(
            segments=segments,
            language=detected_language,
            duration_seconds=duration,
        )

    def _transcribe_chunked(
        self,
        audio_path: Path,
        *,
        language: str | None,
        total_duration: float,
    ) -> TranscriptionResult:
        """Split audio into chunks and transcribe each.

        Args:
            audio_path: Path to the audio file to split and transcribe.
            language: Optional language code passed through to each chunk transcription.
            total_duration: Pre-computed total duration of the source file in seconds.

        Returns:
            A merged TranscriptionResult covering the entire audio file.
        """
        import mlx_whisper  # Lazy import — may not be installed

        chunks = _split_audio(audio_path, self._chunk_duration_minutes)
        chunk_results: list[ChunkResult] = []
        detected_language = "unknown"

        cumulative_offset_seconds: float = 0.0
        try:
            for index, chunk_path in enumerate(chunks):
                logger.debug("Transcribing chunk %d: %s", index, chunk_path)
                result: dict[str, Any] = mlx_whisper.transcribe(
                    str(chunk_path),
                    path_or_hf_repo=self._model_id,
                    language=language,
                    word_timestamps=True,
                )
                segments = _parse_mlx_segments(result.get("segments", []))
                chunk_duration = _get_audio_duration(chunk_path)

                # Offset timestamps by the accumulated duration of all prior chunks,
                # using the measured duration rather than the nominal chunk length so
                # the last (usually shorter) chunk is handled correctly.
                for seg in segments:
                    seg.start += cumulative_offset_seconds
                    seg.end += cumulative_offset_seconds

                chunk_results.append(
                    ChunkResult(
                        chunk_index=index,
                        segments=segments,
                        duration=chunk_duration,
                    )
                )
                cumulative_offset_seconds += chunk_duration
                if index == 0:
                    detected_language = result.get("language", "unknown")
        finally:
            # Clean up temporary chunk files
            for chunk_path in chunks:
                chunk_path.unlink(missing_ok=True)
            # Clean up the parent temp directory
            if chunks:
                chunk_dir = chunks[0].parent
                with contextlib.suppress(OSError):  # Directory not empty or already removed
                    chunk_dir.rmdir()

        # Merge all chunk segments
        all_segments = [seg for cr in chunk_results for seg in cr.segments]

        return TranscriptionResult(
            segments=all_segments,
            language=detected_language,
            duration_seconds=total_duration,
        )


def _get_audio_duration(audio_path: Path) -> float:
    """Get audio duration in seconds using FFprobe.

    Args:
        audio_path: Path to the audio file.

    Returns:
        Duration in seconds as a float.

    Raises:
        subprocess.CalledProcessError: If ffprobe exits with a non-zero status.
    """
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "quiet",
                "-show_entries",
                "format=duration",
                "-of",
                "json",
                str(audio_path),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError:
        raise RuntimeError(
            "ffprobe not found. Install FFmpeg: brew install ffmpeg (macOS) or apt install ffmpeg (Linux)"
        ) from None
    data: dict[str, Any] = json.loads(result.stdout)
    format_section: dict[str, Any] = data.get("format", {})
    raw_duration = format_section.get("duration")
    if raw_duration is None:
        raise RuntimeError(
            f"ffprobe did not return a duration for {audio_path}. The file may be corrupt or in an unsupported format."
        )
    return float(raw_duration)


def _split_audio(audio_path: Path, chunk_minutes: int) -> list[Path]:
    """Split audio into chunks using FFmpeg.

    Args:
        audio_path: Path to the source audio file.
        chunk_minutes: Maximum duration of each chunk in minutes.

    Returns:
        Sorted list of paths to the generated chunk files.

    Raises:
        subprocess.CalledProcessError: If ffmpeg exits with a non-zero status.
        RuntimeError: If FFmpeg produces no output chunk files.
    """
    chunk_dir = Path(tempfile.mkdtemp(prefix="audio_chunks_"))
    chunk_seconds = chunk_minutes * 60
    output_pattern = str(chunk_dir / f"chunk_%03d{audio_path.suffix}")

    try:
        subprocess.run(
            [
                "ffmpeg",
                "-i",
                str(audio_path),
                "-f",
                "segment",
                "-segment_time",
                str(chunk_seconds),
                "-c",
                "copy",
                "-v",
                "quiet",
                output_pattern,
            ],
            check=True,
        )
    except FileNotFoundError:
        with contextlib.suppress(OSError):
            chunk_dir.rmdir()
        raise RuntimeError(
            "ffmpeg not found. Install FFmpeg: brew install ffmpeg (macOS) or apt install ffmpeg (Linux)"
        ) from None
    except subprocess.CalledProcessError:
        # Clean up any partial output before re-raising
        for partial_chunk in chunk_dir.glob(f"chunk_*{audio_path.suffix}"):
            partial_chunk.unlink(missing_ok=True)
        with contextlib.suppress(OSError):
            chunk_dir.rmdir()
        raise

    chunks = sorted(chunk_dir.glob(f"chunk_*{audio_path.suffix}"))
    if not chunks:
        with contextlib.suppress(OSError):
            chunk_dir.rmdir()
        raise RuntimeError(f"FFmpeg produced no chunks from {audio_path}")
    return chunks


def _parse_mlx_segments(raw_segments: list[dict[str, Any]]) -> list[TranscriptSegment]:
    """Convert raw MLX-Whisper segment dicts to TranscriptSegment objects.

    Args:
        raw_segments: List of segment dicts as returned by mlx_whisper.transcribe.

    Returns:
        List of TranscriptSegment instances with all available fields populated.
    """
    segments: list[TranscriptSegment] = []
    for seg in raw_segments:
        segments.append(
            TranscriptSegment(
                start=float(seg.get("start", 0.0)),
                end=float(seg.get("end", 0.0)),
                text=seg.get("text", "").strip(),
                confidence=seg.get("avg_logprob"),
                words=seg.get("words"),
                no_speech_prob=seg.get("no_speech_prob"),
                compression_ratio=seg.get("compression_ratio"),
            )
        )
    return segments
