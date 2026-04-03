"""Speaker diarization using PyAnnote.

Provides functions to load a PyAnnote diarization pipeline, run it against
an audio file to produce speaker-labeled time ranges, and merge those ranges
with transcript segments produced by the transcription engines.

The pyannote.audio dependency is optional — it is lazily imported inside
load_diarization_pipeline so this module can be imported without it installed.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path  # noqa: TC003
from typing import Any

from deep_thought.audio.models import SpeakerSegment, TranscriptSegment

logger = logging.getLogger(__name__)


def load_diarization_pipeline(hf_token_env: str = "HF_TOKEN") -> Any:
    """Load the PyAnnote speaker diarization pipeline.

    Args:
        hf_token_env: Name of the environment variable holding the HuggingFace token.

    Returns:
        A loaded PyAnnote Pipeline instance.

    Raises:
        OSError: If the HuggingFace token env var is not set.
        ImportError: If pyannote.audio is not installed.
    """
    token = os.environ.get(hf_token_env)
    if not token:
        raise OSError(f"Environment variable {hf_token_env!r} is not set. Required for speaker diarization.")

    from pyannote.audio import Pipeline  # Lazy import — optional dependency

    logger.info("Loading PyAnnote diarization pipeline...")
    pipeline: Any = Pipeline.from_pretrained(
        "pyannote/speaker-diarization-3.1",
        use_auth_token=token,
    )
    return pipeline


def diarize(audio_path: Path, pipeline: Any) -> list[SpeakerSegment]:
    """Run speaker diarization on an audio file.

    Args:
        audio_path: Path to the audio file.
        pipeline: A loaded PyAnnote Pipeline instance.

    Returns:
        List of SpeakerSegment with speaker labels and time ranges.
    """
    logger.info("Running diarization on: %s", audio_path)
    annotation = pipeline(str(audio_path))

    speaker_segments: list[SpeakerSegment] = []
    for turn, _, speaker in annotation.itertracks(yield_label=True):
        speaker_segments.append(
            SpeakerSegment(
                speaker_label=str(speaker),
                start=turn.start,
                end=turn.end,
            )
        )

    logger.info("Diarization complete: %d speaker segments found", len(speaker_segments))
    return speaker_segments


def merge_transcript_with_speakers(
    segments: list[TranscriptSegment],
    speaker_segments: list[SpeakerSegment],
) -> list[TranscriptSegment]:
    """Assign speaker labels to transcript segments based on time overlap.

    For each transcript segment, finds the speaker segment with the most
    temporal overlap and assigns that speaker's label.

    Args:
        segments: Transcript segments from the engine.
        speaker_segments: Speaker segments from diarization.

    Returns:
        New list of TranscriptSegment with speaker field populated.
        Segments with no overlapping speaker have speaker set to None.
    """
    labeled_segments: list[TranscriptSegment] = []

    for seg in segments:
        best_speaker: str | None = None
        best_overlap: float = 0.0

        for spk in speaker_segments:
            # Calculate temporal overlap between transcript segment and speaker segment
            overlap_start = max(seg.start, spk.start)
            overlap_end = min(seg.end, spk.end)
            overlap = max(0.0, overlap_end - overlap_start)

            if overlap > best_overlap:
                best_overlap = overlap
                best_speaker = spk.speaker_label

        labeled_segments.append(
            TranscriptSegment(
                start=seg.start,
                end=seg.end,
                text=seg.text,
                confidence=seg.confidence,
                words=seg.words,
                no_speech_prob=seg.no_speech_prob,
                compression_ratio=seg.compression_ratio,
                speaker=best_speaker,
            )
        )

    return labeled_segments
