"""Standard Whisper transcription engine (cross-platform).

Wraps the openai-whisper library to produce structured transcription results.
Unlike the MLX engine, Whisper handles long audio natively without chunking.
The whisper dependency is optional at import time — it is lazily loaded on
first use so the module can be imported without the package installed.
"""

from __future__ import annotations

import logging
from pathlib import Path  # noqa: TC003
from typing import Any

from deep_thought.audio.models import TranscriptionResult, TranscriptSegment

logger = logging.getLogger(__name__)


class WhisperEngine:
    """Transcription engine using OpenAI Whisper.

    Simpler than MLX — Whisper handles long audio natively without chunking.
    """

    def __init__(self, model: str = "large-v3-turbo") -> None:
        self._model_name = model
        self._model: Any = None  # Lazy-loaded on first transcription call

    def _load_model(self) -> Any:
        """Load the Whisper model on first use.

        Returns:
            The loaded Whisper model instance.

        Raises:
            ImportError: If openai-whisper is not installed.
        """
        if self._model is None:
            import whisper  # type: ignore[import-not-found]  # Lazy import — optional dependency

            logger.info("Loading Whisper model: %s", self._model_name)
            self._model = whisper.load_model(self._model_name)
        return self._model

    def transcribe(self, audio_path: Path, *, language: str | None = None) -> TranscriptionResult:
        """Transcribe an audio file using Whisper.

        Args:
            audio_path: Path to the audio file to transcribe.
            language: Optional BCP-47 language code to force (e.g. "en").
                      When None, language is auto-detected.

        Returns:
            A TranscriptionResult with all segments and detected language.

        Raises:
            ImportError: If openai-whisper is not installed.
        """
        model = self._load_model()

        transcribe_kwargs: dict[str, Any] = {
            "word_timestamps": True,
            "verbose": False,
        }
        if language is not None:
            transcribe_kwargs["language"] = language

        result: dict[str, Any] = model.transcribe(str(audio_path), **transcribe_kwargs)

        segments = _parse_whisper_segments(result.get("segments", []))
        detected_language: str = result.get("language", "unknown")

        # Calculate total duration from the last segment's end time
        duration = segments[-1].end if segments else 0.0

        return TranscriptionResult(
            segments=segments,
            language=detected_language,
            duration_seconds=duration,
        )


def _parse_whisper_segments(raw_segments: list[dict[str, Any]]) -> list[TranscriptSegment]:
    """Convert raw Whisper segment dicts to TranscriptSegment objects.

    Args:
        raw_segments: List of segment dicts as returned by whisper model.transcribe.

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
