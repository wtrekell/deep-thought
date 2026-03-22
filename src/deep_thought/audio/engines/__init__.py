"""Transcription engine protocol and factory.

Defines the interface that all transcription engines must satisfy
and provides a factory function to create the right engine based on config.
"""

from __future__ import annotations

import platform
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from pathlib import Path

    from deep_thought.audio.models import TranscriptionResult


class TranscriptionEngine(Protocol):
    """Protocol that all transcription engines must implement."""

    def transcribe(self, audio_path: Path, *, language: str | None = None) -> TranscriptionResult:
        """Transcribe an audio file and return structured results."""
        ...


def create_engine(engine_name: str, model: str, chunk_duration_minutes: int = 5) -> TranscriptionEngine:
    """Create a transcription engine instance.

    Args:
        engine_name: "mlx", "whisper", or "auto"
        model: Whisper model name (e.g., "large-v3-turbo")
        chunk_duration_minutes: Audio chunk size for MLX engine

    Returns:
        A TranscriptionEngine instance.

    Raises:
        ValueError: If engine_name is not recognized.
        ImportError: If the required engine package is not installed.
    """
    # "auto" detection: use MLX on Apple Silicon (arm64 + darwin), whisper otherwise
    if engine_name == "auto":
        engine_name = "mlx" if platform.system() == "Darwin" and platform.machine() == "arm64" else "whisper"

    if engine_name == "mlx":
        from deep_thought.audio.engines.mlx_whisper_engine import MlxWhisperEngine

        return MlxWhisperEngine(model=model, chunk_duration_minutes=chunk_duration_minutes)
    elif engine_name == "whisper":
        from deep_thought.audio.engines.whisper_engine import WhisperEngine

        return WhisperEngine(model=model)
    else:
        raise ValueError(f"Unknown engine: {engine_name!r}. Use 'mlx', 'whisper', or 'auto'.")
