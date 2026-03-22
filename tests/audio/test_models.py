"""Tests for the data models in deep_thought.audio.models."""

from __future__ import annotations

from deep_thought.audio.models import (
    ProcessedFileLocal,
    TranscriptionResult,
    TranscriptSegment,
)

# ---------------------------------------------------------------------------
# ProcessedFileLocal
# ---------------------------------------------------------------------------


class TestProcessedFileLocal:
    def test_to_dict_returns_correct_keys_and_values(self) -> None:
        """to_dict() must return a flat dict matching all field names."""
        record = ProcessedFileLocal(
            file_path="/audio/interview.wav",
            file_hash="abc123",
            engine="mlx",
            model="small",
            duration_seconds=120.5,
            speaker_count=2,
            output_path="/output/interview/",
            status="success",
            created_at="2026-03-22T10:00:00",
            updated_at="2026-03-22T10:01:00",
        )
        result = record.to_dict()

        assert result["file_path"] == "/audio/interview.wav"
        assert result["file_hash"] == "abc123"
        assert result["engine"] == "mlx"
        assert result["model"] == "small"
        assert result["duration_seconds"] == 120.5
        assert result["speaker_count"] == 2
        assert result["output_path"] == "/output/interview/"
        assert result["status"] == "success"
        assert result["created_at"] == "2026-03-22T10:00:00"
        assert result["updated_at"] == "2026-03-22T10:01:00"

    def test_to_dict_contains_all_fields(self) -> None:
        """to_dict() must include every field defined on the dataclass."""
        record = ProcessedFileLocal(
            file_path="/audio/test.mp3",
            file_hash="deadbeef",
            engine="whisper",
            model="large-v3",
            duration_seconds=30.0,
            speaker_count=0,
            output_path="/output/test/",
            status="skipped",
            created_at="2026-03-22T09:00:00",
            updated_at="2026-03-22T09:00:00",
        )
        result = record.to_dict()

        expected_keys = {
            "file_path",
            "file_hash",
            "engine",
            "model",
            "duration_seconds",
            "speaker_count",
            "output_path",
            "status",
            "created_at",
            "updated_at",
        }
        assert set(result.keys()) == expected_keys

    def test_to_dict_returns_dict_type(self) -> None:
        """to_dict() must return a plain dict, not a dataclass or other type."""
        record = ProcessedFileLocal(
            file_path="/audio/x.wav",
            file_hash="ff",
            engine="mlx",
            model="tiny",
            duration_seconds=1.0,
            speaker_count=0,
            output_path="/output/x/",
            status="error",
            created_at="2026-03-22T00:00:00",
            updated_at="2026-03-22T00:00:00",
        )
        assert isinstance(record.to_dict(), dict)


# ---------------------------------------------------------------------------
# TranscriptSegment
# ---------------------------------------------------------------------------


class TestTranscriptSegment:
    def test_construction_with_required_fields_only(self) -> None:
        """TranscriptSegment must initialise with only start, end, and text."""
        segment = TranscriptSegment(start=0.0, end=3.5, text="Hello, world.")
        assert segment.start == 0.0
        assert segment.end == 3.5
        assert segment.text == "Hello, world."

    def test_optional_fields_default_to_none(self) -> None:
        """All optional fields must default to None."""
        segment = TranscriptSegment(start=0.0, end=3.5, text="Test.")
        assert segment.confidence is None
        assert segment.words is None
        assert segment.no_speech_prob is None
        assert segment.compression_ratio is None
        assert segment.speaker is None

    def test_optional_fields_can_be_set(self) -> None:
        """All optional fields must accept non-None values."""
        word_data = [{"word": "Hello", "start": 0.0, "end": 0.5, "probability": 0.99}]
        segment = TranscriptSegment(
            start=0.0,
            end=3.5,
            text="Hello.",
            confidence=-0.2,
            words=word_data,
            no_speech_prob=0.05,
            compression_ratio=1.1,
            speaker="SPEAKER_00",
        )
        assert segment.confidence == -0.2
        assert segment.words == word_data
        assert segment.no_speech_prob == 0.05
        assert segment.compression_ratio == 1.1
        assert segment.speaker == "SPEAKER_00"

    def test_speaker_label_stored_as_string(self) -> None:
        """The speaker field must store the label as a plain string."""
        segment = TranscriptSegment(start=1.0, end=2.0, text="Speaking.", speaker="SPEAKER_01")
        assert segment.speaker == "SPEAKER_01"


# ---------------------------------------------------------------------------
# TranscriptionResult
# ---------------------------------------------------------------------------


class TestTranscriptionResult:
    def test_construction_with_empty_segments(self) -> None:
        """TranscriptionResult must accept an empty segments list."""
        result = TranscriptionResult(segments=[], language="en", duration_seconds=0.0)
        assert result.segments == []
        assert result.language == "en"
        assert result.duration_seconds == 0.0

    def test_construction_with_segments(self) -> None:
        """TranscriptionResult must store all provided segments."""
        segments = [
            TranscriptSegment(start=0.0, end=2.0, text="First."),
            TranscriptSegment(start=2.5, end=5.0, text="Second."),
        ]
        result = TranscriptionResult(segments=segments, language="fr", duration_seconds=5.0)
        assert len(result.segments) == 2
        assert result.segments[0].text == "First."
        assert result.segments[1].text == "Second."
        assert result.language == "fr"
        assert result.duration_seconds == 5.0

    def test_language_stored_as_string(self) -> None:
        """The language field must be a plain string."""
        result = TranscriptionResult(segments=[], language="ja", duration_seconds=60.0)
        assert isinstance(result.language, str)

    def test_duration_seconds_stored_as_float(self) -> None:
        """The duration_seconds field must be a float."""
        result = TranscriptionResult(segments=[], language="en", duration_seconds=123.456)
        assert isinstance(result.duration_seconds, float)
        assert result.duration_seconds == 123.456
