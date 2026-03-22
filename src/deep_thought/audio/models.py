"""Data models for the audio transcription tool.

Each dataclass represents either a database record or an intermediate data
structure produced by the transcription and diarization engines.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

# ---------------------------------------------------------------------------
# Database record model
# ---------------------------------------------------------------------------


@dataclass
class ProcessedFileLocal:
    """Database record for each processed audio file."""

    file_path: str
    """Absolute or relative path to the source audio file (primary key)."""

    file_hash: str
    """SHA-256 hash of the file contents, used to detect changes between runs."""

    engine: str
    """Transcription engine used: 'whisper' or 'mlx'."""

    model: str
    """Model size used for transcription, e.g. 'large-v3-turbo'."""

    duration_seconds: float
    """Total audio duration in seconds."""

    speaker_count: int
    """Number of identified speakers; 0 when diarization was not performed."""

    output_path: str
    """Path to the directory containing all generated output files."""

    status: str
    """Processing outcome: 'success', 'error', or 'skipped'."""

    created_at: str
    """ISO 8601 timestamp for when this record was first created."""

    updated_at: str
    """ISO 8601 timestamp for when this record was last updated."""

    def to_dict(self) -> dict[str, Any]:
        """Return a flat dict keyed by column names, suitable for SQLite insertion."""
        return asdict(self)


# ---------------------------------------------------------------------------
# Engine output models
# ---------------------------------------------------------------------------


@dataclass
class TranscriptSegment:
    """A single transcription segment produced by the engine.

    Segments represent a contiguous span of speech. Optional fields are
    populated only when the relevant engine feature is enabled (e.g.
    word-level timestamps, diarization).
    """

    start: float
    """Segment start time in seconds."""

    end: float
    """Segment end time in seconds."""

    text: str
    """Transcribed text for this segment."""

    confidence: float | None = None
    """Average log-probability for the segment; lower values indicate less certainty."""

    words: list[dict[str, Any]] | None = None
    """Word-level timing and confidence data, when available."""

    no_speech_prob: float | None = None
    """Whisper no-speech probability; high values suggest the segment may be silence."""

    compression_ratio: float | None = None
    """Whisper compression ratio; high values can indicate hallucination."""

    speaker: str | None = None
    """Speaker label assigned by the diarization engine, e.g. 'SPEAKER_01'."""


@dataclass
class SpeakerSegment:
    """A labeled time range for a single speaker, produced by diarization."""

    speaker_label: str
    """Identifier for the speaker, e.g. 'SPEAKER_00'."""

    start: float
    """Segment start time in seconds."""

    end: float
    """Segment end time in seconds."""


@dataclass
class ChunkResult:
    """Result from transcribing a single audio chunk on the MLX path.

    Long audio files are split into chunks to work around memory constraints
    and to enable progress reporting during transcription.
    """

    chunk_index: int
    """Zero-based index of this chunk within the full audio file."""

    segments: list[TranscriptSegment]
    """Transcription segments produced for this chunk."""

    duration: float
    """Duration of this chunk in seconds."""


@dataclass
class TranscriptionResult:
    """Aggregated output from a complete transcription run.

    This is the top-level object passed from the engine layer to the
    output formatting layer.
    """

    segments: list[TranscriptSegment]
    """All transcription segments for the full audio file, in order."""

    language: str
    """Detected or specified language code, e.g. 'en'."""

    duration_seconds: float
    """Total audio duration in seconds."""
