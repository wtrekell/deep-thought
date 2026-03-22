"""Tests for the speaker diarization module in deep_thought.audio.diarization.

All PyAnnote calls are mocked — no real pyannote.audio installation is required.

The lazy import of pyannote.audio.Pipeline inside load_diarization_pipeline
is intercepted by injecting a mock into sys.modules["pyannote.audio"].
"""

from __future__ import annotations

import sys
from pathlib import Path  # noqa: TC003
from unittest.mock import MagicMock, patch

import pytest

from deep_thought.audio.diarization import diarize, load_diarization_pipeline, merge_transcript_with_speakers
from deep_thought.audio.models import SpeakerSegment, TranscriptSegment

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_segment(
    start: float = 0.0,
    end: float = 5.0,
    text: str = "Sample text.",
    confidence: float | None = -0.3,
    words: list[dict[str, object]] | None = None,
    no_speech_prob: float | None = 0.05,
    compression_ratio: float | None = 1.2,
    speaker: str | None = None,
) -> TranscriptSegment:
    """Return a TranscriptSegment with predictable test defaults."""
    return TranscriptSegment(
        start=start,
        end=end,
        text=text,
        confidence=confidence,
        words=words,
        no_speech_prob=no_speech_prob,
        compression_ratio=compression_ratio,
        speaker=speaker,
    )


def _make_speaker_segment(speaker_label: str, start: float, end: float) -> SpeakerSegment:
    """Return a SpeakerSegment with the given label and time range."""
    return SpeakerSegment(speaker_label=speaker_label, start=start, end=end)


def _make_mock_turn(start: float, end: float) -> MagicMock:
    """Return a mock pyannote turn object with start and end attributes."""
    turn = MagicMock()
    turn.start = start
    turn.end = end
    return turn


def _make_pyannote_module_mock() -> tuple[MagicMock, MagicMock]:
    """Return (pyannote_audio_mock, Pipeline_class_mock) pair.

    Injects into sys.modules["pyannote.audio"] so that
    `from pyannote.audio import Pipeline` inside load_diarization_pipeline
    resolves to Pipeline_class_mock.
    """
    mock_pipeline_class = MagicMock()
    mock_pyannote_audio = MagicMock()
    mock_pyannote_audio.Pipeline = mock_pipeline_class
    return mock_pyannote_audio, mock_pipeline_class


# ---------------------------------------------------------------------------
# TestLoadDiarizationPipeline
# ---------------------------------------------------------------------------


class TestLoadDiarizationPipeline:
    def test_loads_pipeline_with_valid_token(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """load_diarization_pipeline must return a pipeline when the token env var is set."""
        monkeypatch.setenv("HF_TOKEN", "test-token-abc123")
        mock_pyannote_audio, mock_pipeline_class = _make_pyannote_module_mock()
        mock_pipeline_instance = MagicMock()
        mock_pipeline_class.from_pretrained.return_value = mock_pipeline_instance

        with patch.dict(sys.modules, {"pyannote.audio": mock_pyannote_audio}):
            result = load_diarization_pipeline("HF_TOKEN")

        assert result is mock_pipeline_instance

    def test_raises_os_error_when_env_var_not_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """load_diarization_pipeline must raise OSError when the token env var is missing."""
        monkeypatch.delenv("HF_TOKEN", raising=False)

        with pytest.raises(OSError, match="HF_TOKEN"):
            load_diarization_pipeline("HF_TOKEN")

    def test_raises_os_error_for_custom_env_var_name(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """load_diarization_pipeline must raise OSError with the custom env var name in the message."""
        monkeypatch.delenv("MY_CUSTOM_TOKEN", raising=False)

        with pytest.raises(OSError, match="MY_CUSTOM_TOKEN"):
            load_diarization_pipeline("MY_CUSTOM_TOKEN")

    def test_passes_correct_auth_token_to_pipeline(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """load_diarization_pipeline must forward the token value to Pipeline.from_pretrained."""
        monkeypatch.setenv("HF_TOKEN", "my-secret-token")
        mock_pyannote_audio, mock_pipeline_class = _make_pyannote_module_mock()
        mock_pipeline_class.from_pretrained.return_value = MagicMock()

        with patch.dict(sys.modules, {"pyannote.audio": mock_pyannote_audio}):
            load_diarization_pipeline("HF_TOKEN")

        mock_pipeline_class.from_pretrained.assert_called_once_with(
            "pyannote/speaker-diarization-3.1",
            use_auth_token="my-secret-token",
        )

    def test_loads_correct_model_name(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """load_diarization_pipeline must request the pyannote/speaker-diarization-3.1 model."""
        monkeypatch.setenv("HF_TOKEN", "token-xyz")
        mock_pyannote_audio, mock_pipeline_class = _make_pyannote_module_mock()
        mock_pipeline_class.from_pretrained.return_value = MagicMock()

        with patch.dict(sys.modules, {"pyannote.audio": mock_pyannote_audio}):
            load_diarization_pipeline("HF_TOKEN")

        call_args = mock_pipeline_class.from_pretrained.call_args[0]
        assert call_args[0] == "pyannote/speaker-diarization-3.1"


# ---------------------------------------------------------------------------
# TestDiarize
# ---------------------------------------------------------------------------


class TestDiarize:
    def test_produces_speaker_segment_list_from_annotation(self, tmp_path: Path) -> None:
        """diarize() must convert annotation tracks into SpeakerSegment objects."""
        audio_file = tmp_path / "audio.wav"
        audio_file.touch()

        turn_0 = _make_mock_turn(start=0.0, end=5.0)
        turn_1 = _make_mock_turn(start=5.5, end=10.0)

        mock_annotation = MagicMock()
        mock_annotation.itertracks.return_value = [
            (turn_0, None, "SPEAKER_00"),
            (turn_1, None, "SPEAKER_01"),
        ]
        mock_pipeline = MagicMock(return_value=mock_annotation)

        result = diarize(audio_file, mock_pipeline)

        assert len(result) == 2
        assert result[0].speaker_label == "SPEAKER_00"
        assert result[0].start == 0.0
        assert result[0].end == 5.0
        assert result[1].speaker_label == "SPEAKER_01"
        assert result[1].start == 5.5
        assert result[1].end == 10.0

    def test_handles_empty_annotation(self, tmp_path: Path) -> None:
        """diarize() must return an empty list when the annotation has no tracks."""
        audio_file = tmp_path / "audio.wav"
        audio_file.touch()

        mock_annotation = MagicMock()
        mock_annotation.itertracks.return_value = []
        mock_pipeline = MagicMock(return_value=mock_annotation)

        result = diarize(audio_file, mock_pipeline)

        assert result == []

    def test_returns_list_of_speaker_segment(self, tmp_path: Path) -> None:
        """All items in the diarize() result must be SpeakerSegment instances."""
        audio_file = tmp_path / "audio.wav"
        audio_file.touch()

        turn = _make_mock_turn(start=0.0, end=3.0)
        mock_annotation = MagicMock()
        mock_annotation.itertracks.return_value = [(turn, None, "SPEAKER_00")]
        mock_pipeline = MagicMock(return_value=mock_annotation)

        result = diarize(audio_file, mock_pipeline)

        assert all(isinstance(s, SpeakerSegment) for s in result)

    def test_pipeline_called_with_audio_path_string(self, tmp_path: Path) -> None:
        """diarize() must call the pipeline with the audio path as a string."""
        audio_file = tmp_path / "recording.wav"
        audio_file.touch()

        mock_annotation = MagicMock()
        mock_annotation.itertracks.return_value = []
        mock_pipeline = MagicMock(return_value=mock_annotation)

        diarize(audio_file, mock_pipeline)

        mock_pipeline.assert_called_once_with(str(audio_file))

    def test_speaker_label_stored_as_string(self, tmp_path: Path) -> None:
        """diarize() must store speaker labels as plain strings, not MagicMock objects."""
        audio_file = tmp_path / "audio.wav"
        audio_file.touch()

        turn = _make_mock_turn(start=0.0, end=2.0)
        mock_annotation = MagicMock()
        mock_annotation.itertracks.return_value = [(turn, None, "SPEAKER_00")]
        mock_pipeline = MagicMock(return_value=mock_annotation)

        result = diarize(audio_file, mock_pipeline)

        assert isinstance(result[0].speaker_label, str)
        assert result[0].speaker_label == "SPEAKER_00"


# ---------------------------------------------------------------------------
# TestMergeTranscriptWithSpeakers
# ---------------------------------------------------------------------------


class TestMergeTranscriptWithSpeakers:
    def test_assigns_correct_speaker_label_based_on_overlap(self) -> None:
        """Segments must receive the speaker label with the most temporal overlap."""
        segments = [_make_segment(start=0.0, end=5.0)]
        speaker_segments = [
            _make_speaker_segment("SPEAKER_00", start=0.0, end=5.0),
        ]

        result = merge_transcript_with_speakers(segments, speaker_segments)

        assert result[0].speaker == "SPEAKER_00"

    def test_handles_segment_with_no_overlapping_speaker(self) -> None:
        """A segment with no overlapping speaker segment must have speaker set to None."""
        segments = [_make_segment(start=10.0, end=15.0)]
        speaker_segments = [
            _make_speaker_segment("SPEAKER_00", start=0.0, end=5.0),
        ]

        result = merge_transcript_with_speakers(segments, speaker_segments)

        assert result[0].speaker is None

    def test_picks_speaker_with_most_overlap_when_multiple_overlap(self) -> None:
        """When multiple speakers overlap a segment, the one with most overlap wins."""
        # Segment spans 0–10s
        segments = [_make_segment(start=0.0, end=10.0)]
        speaker_segments = [
            _make_speaker_segment("SPEAKER_00", start=0.0, end=3.0),  # 3s overlap
            _make_speaker_segment("SPEAKER_01", start=3.0, end=10.0),  # 7s overlap — winner
        ]

        result = merge_transcript_with_speakers(segments, speaker_segments)

        assert result[0].speaker == "SPEAKER_01"

    def test_preserves_all_transcript_segment_fields(self) -> None:
        """merge_transcript_with_speakers must not drop any TranscriptSegment fields."""
        words = [{"word": "hello", "start": 0.0, "end": 0.5}]
        original = _make_segment(
            start=1.0,
            end=4.0,
            text="Hello there.",
            confidence=-0.25,
            words=words,
            no_speech_prob=0.03,
            compression_ratio=1.1,
        )
        speaker_segments = [_make_speaker_segment("SPEAKER_00", start=1.0, end=4.0)]

        result = merge_transcript_with_speakers([original], speaker_segments)

        merged = result[0]
        assert merged.start == 1.0
        assert merged.end == 4.0
        assert merged.text == "Hello there."
        assert merged.confidence == -0.25
        assert merged.words == words
        assert merged.no_speech_prob == 0.03
        assert merged.compression_ratio == 1.1
        assert merged.speaker == "SPEAKER_00"

    def test_with_empty_speaker_segments_returns_none_speaker(self) -> None:
        """When speaker_segments is empty, all result segments must have speaker=None."""
        segments = [
            _make_segment(start=0.0, end=3.0),
            _make_segment(start=3.5, end=7.0),
        ]

        result = merge_transcript_with_speakers(segments, speaker_segments=[])

        assert all(s.speaker is None for s in result)

    def test_result_length_matches_input_length(self) -> None:
        """The result list must have the same number of items as the input segments list."""
        segments = [
            _make_segment(start=0.0, end=2.0),
            _make_segment(start=2.5, end=5.0),
            _make_segment(start=5.5, end=8.0),
        ]
        speaker_segments = [_make_speaker_segment("SPEAKER_00", start=0.0, end=8.0)]

        result = merge_transcript_with_speakers(segments, speaker_segments)

        assert len(result) == 3

    def test_empty_segments_returns_empty_list(self) -> None:
        """An empty segments list must produce an empty result."""
        speaker_segments = [_make_speaker_segment("SPEAKER_00", start=0.0, end=10.0)]

        result = merge_transcript_with_speakers([], speaker_segments)

        assert result == []

    def test_result_items_are_transcript_segment_instances(self) -> None:
        """All items in the result must be TranscriptSegment instances."""
        segments = [_make_segment(start=0.0, end=5.0)]
        speaker_segments = [_make_speaker_segment("SPEAKER_00", start=0.0, end=5.0)]

        result = merge_transcript_with_speakers(segments, speaker_segments)

        assert all(isinstance(s, TranscriptSegment) for s in result)

    def test_adjacent_non_overlapping_speakers_assigned_correctly(self) -> None:
        """Adjacent non-overlapping speaker segments must each be assigned to the right transcript segment."""
        segments = [
            _make_segment(start=0.0, end=5.0, text="First speaker."),
            _make_segment(start=5.0, end=10.0, text="Second speaker."),
        ]
        speaker_segments = [
            _make_speaker_segment("SPEAKER_00", start=0.0, end=5.0),
            _make_speaker_segment("SPEAKER_01", start=5.0, end=10.0),
        ]

        result = merge_transcript_with_speakers(segments, speaker_segments)

        assert result[0].speaker == "SPEAKER_00"
        assert result[1].speaker == "SPEAKER_01"

    def test_partial_overlap_still_assigns_speaker(self) -> None:
        """A speaker segment that only partially overlaps must still be assigned."""
        # Segment spans 0–10s, speaker only covers 7–10s
        segments = [_make_segment(start=0.0, end=10.0)]
        speaker_segments = [_make_speaker_segment("SPEAKER_00", start=7.0, end=10.0)]

        result = merge_transcript_with_speakers(segments, speaker_segments)

        assert result[0].speaker == "SPEAKER_00"
