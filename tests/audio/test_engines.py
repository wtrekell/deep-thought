"""Tests for transcription engine protocol, factory, and engine implementations.

All external calls (mlx_whisper.transcribe, whisper.load_model, subprocess.run)
are mocked so no real audio libraries or system tools are required.

Lazy imports (mlx_whisper, whisper) are mocked via sys.modules injection
so that local `import` statements inside function bodies are intercepted.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path  # noqa: TC003
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from deep_thought.audio.engines import create_engine
from deep_thought.audio.engines.mlx_whisper_engine import (
    MlxWhisperEngine,
    _get_audio_duration,
    _parse_mlx_segments,
    _split_audio,
)
from deep_thought.audio.engines.whisper_engine import WhisperEngine, _parse_whisper_segments
from deep_thought.audio.models import TranscriptionResult, TranscriptSegment

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_raw_segment(
    start: float = 0.0,
    end: float = 3.0,
    text: str = " Hello world",
    avg_logprob: float | None = -0.3,
    no_speech_prob: float | None = 0.05,
    compression_ratio: float | None = 1.2,
    words: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    """Return a raw segment dict as returned by mlx_whisper or whisper."""
    seg: dict[str, object] = {
        "start": start,
        "end": end,
        "text": text,
    }
    if avg_logprob is not None:
        seg["avg_logprob"] = avg_logprob
    if no_speech_prob is not None:
        seg["no_speech_prob"] = no_speech_prob
    if compression_ratio is not None:
        seg["compression_ratio"] = compression_ratio
    if words is not None:
        seg["words"] = words
    return seg


def _make_ffprobe_output(duration: float) -> str:
    """Return a JSON string matching ffprobe's format output."""
    return json.dumps({"format": {"duration": str(duration)}})


def _make_mlx_module_mock(
    segments: list[dict[str, object]] | None = None,
    language: str = "en",
) -> MagicMock:
    """Return a MagicMock that behaves like the mlx_whisper module.

    Injects the mock into sys.modules so that `import mlx_whisper` inside
    function bodies resolves to this mock.
    """
    mock_mlx = MagicMock()
    mock_mlx.transcribe.return_value = {
        "segments": segments if segments is not None else [_make_raw_segment()],
        "language": language,
    }
    return mock_mlx


def _make_whisper_module_mock(
    segments: list[dict[str, object]] | None = None,
    language: str = "en",
) -> tuple[MagicMock, MagicMock]:
    """Return (whisper_module_mock, model_mock) pair.

    The module mock's load_model returns model_mock.
    model_mock.transcribe returns a result dict.
    Injects the module mock into sys.modules.
    """
    mock_model = MagicMock()
    mock_model.transcribe.return_value = {
        "segments": segments if segments is not None else [_make_raw_segment()],
        "language": language,
    }
    mock_whisper = MagicMock()
    mock_whisper.load_model.return_value = mock_model
    return mock_whisper, mock_model


# ---------------------------------------------------------------------------
# TestCreateEngine
# ---------------------------------------------------------------------------


class TestCreateEngine:
    def test_factory_creates_mlx_engine_for_mlx(self) -> None:
        """create_engine('mlx', ...) must return an MlxWhisperEngine."""
        engine = create_engine("mlx", model="small")
        assert isinstance(engine, MlxWhisperEngine)

    def test_factory_creates_whisper_engine_for_whisper(self) -> None:
        """create_engine('whisper', ...) must return a WhisperEngine."""
        engine = create_engine("whisper", model="small")
        assert isinstance(engine, WhisperEngine)

    def test_factory_raises_value_error_for_unknown_engine(self) -> None:
        """create_engine with an unknown name must raise ValueError."""
        with pytest.raises(ValueError, match="Unknown engine"):
            create_engine("does_not_exist", model="small")

    def test_auto_selects_mlx_on_apple_silicon(self) -> None:
        """On Darwin arm64, 'auto' must select the MLX engine."""
        with (
            patch("deep_thought.audio.engines.platform.system", return_value="Darwin"),
            patch("deep_thought.audio.engines.platform.machine", return_value="arm64"),
        ):
            engine = create_engine("auto", model="small")
        assert isinstance(engine, MlxWhisperEngine)

    def test_auto_selects_whisper_on_non_apple_silicon(self) -> None:
        """On non-Darwin or non-arm64, 'auto' must select the Whisper engine."""
        with (
            patch("deep_thought.audio.engines.platform.system", return_value="Linux"),
            patch("deep_thought.audio.engines.platform.machine", return_value="x86_64"),
        ):
            engine = create_engine("auto", model="small")
        assert isinstance(engine, WhisperEngine)

    def test_auto_selects_whisper_on_darwin_x86(self) -> None:
        """On Darwin x86_64 (Intel Mac), 'auto' must select the Whisper engine."""
        with (
            patch("deep_thought.audio.engines.platform.system", return_value="Darwin"),
            patch("deep_thought.audio.engines.platform.machine", return_value="x86_64"),
        ):
            engine = create_engine("auto", model="small")
        assert isinstance(engine, WhisperEngine)

    def test_factory_passes_chunk_duration_to_mlx_engine(self) -> None:
        """The chunk_duration_minutes argument must be forwarded to MlxWhisperEngine."""
        engine = create_engine("mlx", model="small", chunk_duration_minutes=10)
        assert isinstance(engine, MlxWhisperEngine)
        assert engine._chunk_duration_minutes == 10  # noqa: SLF001


# ---------------------------------------------------------------------------
# TestMlxWhisperEngine
# ---------------------------------------------------------------------------


class TestMlxWhisperEngine:
    def test_transcribe_calls_mlx_whisper_with_correct_args(self, tmp_path: Path) -> None:
        """transcribe() must call mlx_whisper.transcribe with path_or_hf_repo and word_timestamps."""
        audio_file = tmp_path / "audio.wav"
        audio_file.touch()
        engine = MlxWhisperEngine(model="small", chunk_duration_minutes=5)
        mock_mlx = _make_mlx_module_mock()

        with (
            patch("deep_thought.audio.engines.mlx_whisper_engine.subprocess.run") as mock_subprocess,
            patch.dict(sys.modules, {"mlx_whisper": mock_mlx}),
        ):
            mock_subprocess.return_value = MagicMock(stdout=_make_ffprobe_output(10.0))
            engine.transcribe(audio_file, language="en")

        mock_mlx.transcribe.assert_called_once_with(
            str(audio_file),
            path_or_hf_repo="mlx-community/whisper-small",
            language="en",
            word_timestamps=True,
        )

    def test_transcribe_returns_transcription_result(self, tmp_path: Path) -> None:
        """transcribe() must return a TranscriptionResult instance."""
        audio_file = tmp_path / "audio.wav"
        audio_file.touch()
        engine = MlxWhisperEngine(model="small")
        mock_mlx = _make_mlx_module_mock(language="fr")

        with (
            patch("deep_thought.audio.engines.mlx_whisper_engine.subprocess.run") as mock_subprocess,
            patch.dict(sys.modules, {"mlx_whisper": mock_mlx}),
        ):
            mock_subprocess.return_value = MagicMock(stdout=_make_ffprobe_output(10.0))
            result = engine.transcribe(audio_file)

        assert isinstance(result, TranscriptionResult)
        assert result.language == "fr"
        assert result.duration_seconds == 10.0

    def test_transcribe_parses_segments_correctly(self, tmp_path: Path) -> None:
        """Segments from mlx_whisper must be parsed into TranscriptSegment objects."""
        audio_file = tmp_path / "audio.wav"
        audio_file.touch()
        engine = MlxWhisperEngine(model="small")

        raw_segs = [
            _make_raw_segment(start=0.0, end=2.0, text=" Hello"),
            _make_raw_segment(start=2.5, end=5.0, text=" world"),
        ]
        mock_mlx = _make_mlx_module_mock(segments=raw_segs)

        with (
            patch("deep_thought.audio.engines.mlx_whisper_engine.subprocess.run") as mock_subprocess,
            patch.dict(sys.modules, {"mlx_whisper": mock_mlx}),
        ):
            mock_subprocess.return_value = MagicMock(stdout=_make_ffprobe_output(5.0))
            result = engine.transcribe(audio_file)

        assert len(result.segments) == 2
        assert result.segments[0].text == "Hello"
        assert result.segments[0].start == 0.0
        assert result.segments[1].text == "world"
        assert result.segments[1].end == 5.0

    def test_chunked_transcription_triggered_when_duration_exceeds_threshold(self, tmp_path: Path) -> None:
        """transcribe() must call _transcribe_chunked when duration > threshold."""
        audio_file = tmp_path / "long_audio.wav"
        audio_file.touch()
        engine = MlxWhisperEngine(model="small", chunk_duration_minutes=5)

        with (
            patch.object(engine, "_transcribe_chunked") as mock_chunked,
            patch("deep_thought.audio.engines.mlx_whisper_engine.subprocess.run") as mock_subprocess,
        ):
            mock_chunked.return_value = TranscriptionResult(segments=[], language="en", duration_seconds=400.0)
            # Duration of 400 seconds > 5 minutes (300 seconds) threshold
            mock_subprocess.return_value = MagicMock(stdout=_make_ffprobe_output(400.0))
            result = engine.transcribe(audio_file)

        mock_chunked.assert_called_once_with(audio_file, language=None, total_duration=400.0)
        assert result.duration_seconds == 400.0

    def test_chunked_transcription_not_triggered_for_short_audio(self, tmp_path: Path) -> None:
        """transcribe() must not call _transcribe_chunked for audio shorter than threshold."""
        audio_file = tmp_path / "short_audio.wav"
        audio_file.touch()
        engine = MlxWhisperEngine(model="small", chunk_duration_minutes=5)
        mock_mlx = _make_mlx_module_mock()

        with (
            patch.object(engine, "_transcribe_chunked") as mock_chunked,
            patch("deep_thought.audio.engines.mlx_whisper_engine.subprocess.run") as mock_subprocess,
            patch.dict(sys.modules, {"mlx_whisper": mock_mlx}),
        ):
            mock_subprocess.return_value = MagicMock(stdout=_make_ffprobe_output(60.0))
            engine.transcribe(audio_file)

        mock_chunked.assert_not_called()

    def test_chunk_timestamps_are_offset_correctly(self, tmp_path: Path) -> None:
        """Segments from chunk N must have timestamps offset by N * chunk_duration * 60."""
        audio_file = tmp_path / "long.wav"
        audio_file.touch()
        chunk_minutes = 5
        engine = MlxWhisperEngine(model="small", chunk_duration_minutes=chunk_minutes)

        chunk_0 = tmp_path / "chunk_000.wav"
        chunk_1 = tmp_path / "chunk_001.wav"
        chunk_0.touch()
        chunk_1.touch()

        # Chunk 0 has a segment from 0-10s, chunk 1 has a segment from 0-10s
        # After offsetting, chunk 1's segment should start at 300s (5 min * 60)
        chunk_0_seg = _make_raw_segment(start=0.0, end=10.0, text=" First chunk")
        chunk_1_seg = _make_raw_segment(start=0.0, end=10.0, text=" Second chunk")

        call_count = 0

        def mock_transcribe_side_effect(*args: object, **kwargs: object) -> dict[str, Any]:
            nonlocal call_count
            seg = chunk_0_seg if call_count == 0 else chunk_1_seg
            call_count += 1
            return {"segments": [seg], "language": "en"}

        mock_mlx = MagicMock()
        mock_mlx.transcribe.side_effect = mock_transcribe_side_effect

        with (
            patch("deep_thought.audio.engines.mlx_whisper_engine._split_audio") as mock_split,
            patch("deep_thought.audio.engines.mlx_whisper_engine._get_audio_duration") as mock_duration,
            patch.dict(sys.modules, {"mlx_whisper": mock_mlx}),
        ):
            mock_split.return_value = [chunk_0, chunk_1]
            # First call: total duration > threshold; subsequent calls: chunk durations
            mock_duration.side_effect = [400.0, 60.0, 60.0]

            result = engine.transcribe(audio_file)

        assert result.segments[0].text == "First chunk"
        assert result.segments[0].start == 0.0  # Chunk 0: no offset
        assert result.segments[1].text == "Second chunk"
        assert result.segments[1].start == chunk_minutes * 60  # Chunk 1: offset by 300s

    def test_chunk_temp_files_cleaned_up(self, tmp_path: Path) -> None:
        """Temporary chunk files must be deleted after chunked transcription."""
        audio_file = tmp_path / "long.wav"
        audio_file.touch()
        engine = MlxWhisperEngine(model="small", chunk_duration_minutes=5)

        chunk_0 = tmp_path / "chunk_000.wav"
        chunk_1 = tmp_path / "chunk_001.wav"
        chunk_0.touch()
        chunk_1.touch()

        mock_mlx = MagicMock()
        mock_mlx.transcribe.return_value = {"segments": [], "language": "en"}

        with (
            patch("deep_thought.audio.engines.mlx_whisper_engine._split_audio") as mock_split,
            patch("deep_thought.audio.engines.mlx_whisper_engine._get_audio_duration") as mock_duration,
            patch.dict(sys.modules, {"mlx_whisper": mock_mlx}),
        ):
            mock_split.return_value = [chunk_0, chunk_1]
            mock_duration.side_effect = [400.0, 60.0, 60.0]

            engine.transcribe(audio_file)

        # Both chunk files should have been deleted by the finally block
        assert not chunk_0.exists()
        assert not chunk_1.exists()

    def test_chunk_temp_files_cleaned_up_even_on_error(self, tmp_path: Path) -> None:
        """Chunk files must be deleted even when transcription raises an exception."""
        audio_file = tmp_path / "long.wav"
        audio_file.touch()
        engine = MlxWhisperEngine(model="small", chunk_duration_minutes=5)

        chunk_0 = tmp_path / "chunk_000.wav"
        chunk_0.touch()

        mock_mlx = MagicMock()
        mock_mlx.transcribe.side_effect = RuntimeError("MLX failure")

        with (
            patch("deep_thought.audio.engines.mlx_whisper_engine._split_audio") as mock_split,
            patch("deep_thought.audio.engines.mlx_whisper_engine._get_audio_duration") as mock_duration,
            patch.dict(sys.modules, {"mlx_whisper": mock_mlx}),
        ):
            mock_split.return_value = [chunk_0]
            mock_duration.side_effect = [400.0]

            with pytest.raises(RuntimeError, match="MLX failure"):
                engine.transcribe(audio_file)

        assert not chunk_0.exists()


# ---------------------------------------------------------------------------
# TestWhisperEngine
# ---------------------------------------------------------------------------


class TestWhisperEngine:
    def test_transcribe_loads_model_lazily(self) -> None:
        """The whisper model must not be loaded at construction time."""
        engine = WhisperEngine(model="small")
        assert engine._model is None  # noqa: SLF001

    def test_transcribe_returns_transcription_result(self, tmp_path: Path) -> None:
        """transcribe() must return a TranscriptionResult instance."""
        audio_file = tmp_path / "audio.wav"
        audio_file.touch()
        engine = WhisperEngine(model="small")
        mock_whisper, mock_model = _make_whisper_module_mock(language="de")

        with patch.dict(sys.modules, {"whisper": mock_whisper}):
            result = engine.transcribe(audio_file)

        assert isinstance(result, TranscriptionResult)
        assert result.language == "de"

    def test_transcribe_loads_model_on_first_call(self, tmp_path: Path) -> None:
        """whisper.load_model must be called exactly once on the first transcribe call."""
        audio_file = tmp_path / "audio.wav"
        audio_file.touch()
        engine = WhisperEngine(model="large-v3")
        mock_whisper, mock_model = _make_whisper_module_mock()

        with patch.dict(sys.modules, {"whisper": mock_whisper}):
            engine.transcribe(audio_file)
            engine.transcribe(audio_file)  # Second call — should reuse model

        mock_whisper.load_model.assert_called_once_with("large-v3")

    def test_model_is_cached_after_first_load(self, tmp_path: Path) -> None:
        """The model must be stored on _model after first load."""
        audio_file = tmp_path / "audio.wav"
        audio_file.touch()
        engine = WhisperEngine(model="small")
        mock_whisper, mock_model = _make_whisper_module_mock()

        with patch.dict(sys.modules, {"whisper": mock_whisper}):
            engine.transcribe(audio_file)

        assert engine._model is mock_model  # noqa: SLF001

    def test_transcribe_passes_language_when_provided(self, tmp_path: Path) -> None:
        """transcribe() must pass language to the model when it is not None."""
        audio_file = tmp_path / "audio.wav"
        audio_file.touch()
        engine = WhisperEngine(model="small")
        mock_whisper, mock_model = _make_whisper_module_mock()

        with patch.dict(sys.modules, {"whisper": mock_whisper}):
            engine.transcribe(audio_file, language="es")

        call_kwargs = mock_model.transcribe.call_args[1]
        assert call_kwargs["language"] == "es"

    def test_transcribe_omits_language_when_none(self, tmp_path: Path) -> None:
        """transcribe() must not pass a language key when language is None."""
        audio_file = tmp_path / "audio.wav"
        audio_file.touch()
        engine = WhisperEngine(model="small")
        mock_whisper, mock_model = _make_whisper_module_mock()

        with patch.dict(sys.modules, {"whisper": mock_whisper}):
            engine.transcribe(audio_file, language=None)

        call_kwargs = mock_model.transcribe.call_args[1]
        assert "language" not in call_kwargs

    def test_duration_calculated_from_last_segment(self, tmp_path: Path) -> None:
        """duration_seconds must equal the end time of the final segment."""
        audio_file = tmp_path / "audio.wav"
        audio_file.touch()
        engine = WhisperEngine(model="small")
        raw_segs = [
            _make_raw_segment(start=0.0, end=5.0),
            _make_raw_segment(start=5.5, end=12.3),
        ]
        mock_whisper, _ = _make_whisper_module_mock(segments=raw_segs)

        with patch.dict(sys.modules, {"whisper": mock_whisper}):
            result = engine.transcribe(audio_file)

        assert result.duration_seconds == pytest.approx(12.3)

    def test_duration_is_zero_for_empty_segments(self, tmp_path: Path) -> None:
        """duration_seconds must be 0.0 when there are no segments."""
        audio_file = tmp_path / "audio.wav"
        audio_file.touch()
        engine = WhisperEngine(model="small")
        mock_whisper, _ = _make_whisper_module_mock(segments=[])

        with patch.dict(sys.modules, {"whisper": mock_whisper}):
            result = engine.transcribe(audio_file)

        assert result.duration_seconds == 0.0


# ---------------------------------------------------------------------------
# Test _parse_mlx_segments
# ---------------------------------------------------------------------------


class TestParseMlxSegments:
    def test_empty_input_returns_empty_list(self) -> None:
        """_parse_mlx_segments([]) must return an empty list."""
        assert _parse_mlx_segments([]) == []

    def test_text_is_stripped(self) -> None:
        """Leading/trailing whitespace in text must be stripped."""
        raw = [_make_raw_segment(text="  Hello world  ")]
        result = _parse_mlx_segments(raw)
        assert result[0].text == "Hello world"

    def test_all_fields_populated(self) -> None:
        """All optional fields must be populated from matching dict keys."""
        words = [{"word": "Hi", "start": 0.0, "end": 0.3, "probability": 0.99}]
        raw = [_make_raw_segment(avg_logprob=-0.2, no_speech_prob=0.1, compression_ratio=1.5, words=words)]
        result = _parse_mlx_segments(raw)
        assert result[0].confidence == -0.2
        assert result[0].no_speech_prob == 0.1
        assert result[0].compression_ratio == 1.5
        assert result[0].words == words

    def test_missing_optional_fields_default_to_none(self) -> None:
        """Fields absent from the raw dict must default to None."""
        raw = [{"start": 0.0, "end": 1.0, "text": "Hi"}]
        result = _parse_mlx_segments(raw)
        assert result[0].confidence is None
        assert result[0].no_speech_prob is None
        assert result[0].compression_ratio is None
        assert result[0].words is None

    def test_start_end_cast_to_float(self) -> None:
        """start and end must be cast to float even when provided as int."""
        raw = [{"start": 0, "end": 5, "text": "Test"}]
        result = _parse_mlx_segments(raw)
        assert isinstance(result[0].start, float)
        assert isinstance(result[0].end, float)

    def test_multiple_segments_preserved_in_order(self) -> None:
        """All segments must be present in the result, in original order."""
        raw = [
            _make_raw_segment(start=0.0, end=2.0, text=" First"),
            _make_raw_segment(start=2.5, end=5.0, text=" Second"),
            _make_raw_segment(start=5.5, end=8.0, text=" Third"),
        ]
        result = _parse_mlx_segments(raw)
        assert len(result) == 3
        assert result[0].text == "First"
        assert result[2].text == "Third"

    def test_returns_list_of_transcript_segment(self) -> None:
        """All items in the result must be TranscriptSegment instances."""
        raw = [_make_raw_segment()]
        result = _parse_mlx_segments(raw)
        assert all(isinstance(s, TranscriptSegment) for s in result)


# ---------------------------------------------------------------------------
# Test _parse_whisper_segments
# ---------------------------------------------------------------------------


class TestParseWhisperSegments:
    def test_empty_input_returns_empty_list(self) -> None:
        """_parse_whisper_segments([]) must return an empty list."""
        assert _parse_whisper_segments([]) == []

    def test_text_is_stripped(self) -> None:
        """Leading/trailing whitespace in text must be stripped."""
        raw = [_make_raw_segment(text="  Stripped  ")]
        result = _parse_whisper_segments(raw)
        assert result[0].text == "Stripped"

    def test_all_fields_populated(self) -> None:
        """All optional fields must be populated from matching dict keys."""
        words = [{"word": "Hi", "start": 0.0, "end": 0.5}]
        raw = [_make_raw_segment(avg_logprob=-0.5, no_speech_prob=0.02, compression_ratio=1.1, words=words)]
        result = _parse_whisper_segments(raw)
        assert result[0].confidence == -0.5
        assert result[0].no_speech_prob == 0.02
        assert result[0].compression_ratio == 1.1
        assert result[0].words == words

    def test_missing_optional_fields_default_to_none(self) -> None:
        """Fields absent from the raw dict must default to None."""
        raw = [{"start": 1.0, "end": 2.0, "text": "Test"}]
        result = _parse_whisper_segments(raw)
        assert result[0].confidence is None
        assert result[0].words is None

    def test_returns_list_of_transcript_segment(self) -> None:
        """All items in the result must be TranscriptSegment instances."""
        raw = [_make_raw_segment()]
        result = _parse_whisper_segments(raw)
        assert all(isinstance(s, TranscriptSegment) for s in result)


# ---------------------------------------------------------------------------
# Test _get_audio_duration
# ---------------------------------------------------------------------------


class TestGetAudioDuration:
    def test_parses_duration_from_ffprobe_output(self, tmp_path: Path) -> None:
        """_get_audio_duration must parse the duration from ffprobe JSON output."""
        audio_file = tmp_path / "audio.wav"
        audio_file.touch()

        with patch("deep_thought.audio.engines.mlx_whisper_engine.subprocess.run") as mock_subprocess:
            mock_subprocess.return_value = MagicMock(stdout=_make_ffprobe_output(123.456))
            duration = _get_audio_duration(audio_file)

        assert duration == pytest.approx(123.456)

    def test_calls_ffprobe_with_correct_args(self, tmp_path: Path) -> None:
        """_get_audio_duration must invoke ffprobe with the expected flags."""
        audio_file = tmp_path / "audio.wav"
        audio_file.touch()

        with patch("deep_thought.audio.engines.mlx_whisper_engine.subprocess.run") as mock_subprocess:
            mock_subprocess.return_value = MagicMock(stdout=_make_ffprobe_output(10.0))
            _get_audio_duration(audio_file)

        call_args = mock_subprocess.call_args[0][0]
        assert call_args[0] == "ffprobe"
        assert "-show_entries" in call_args
        assert "format=duration" in call_args
        assert "-of" in call_args
        assert "json" in call_args
        assert str(audio_file) in call_args

    def test_duration_returned_as_float(self, tmp_path: Path) -> None:
        """_get_audio_duration must return a float."""
        audio_file = tmp_path / "audio.wav"
        audio_file.touch()

        with patch("deep_thought.audio.engines.mlx_whisper_engine.subprocess.run") as mock_subprocess:
            mock_subprocess.return_value = MagicMock(stdout=_make_ffprobe_output(60.0))
            result = _get_audio_duration(audio_file)

        assert isinstance(result, float)

    @pytest.mark.error_handling
    def test_raises_runtime_error_when_ffprobe_not_found(self, tmp_path: Path) -> None:
        """_get_audio_duration must raise RuntimeError when ffprobe is not on PATH."""
        audio_file = tmp_path / "audio.wav"
        audio_file.touch()

        with (
            patch(
                "deep_thought.audio.engines.mlx_whisper_engine.subprocess.run",
                side_effect=FileNotFoundError("ffprobe: No such file or directory"),
            ),
            pytest.raises(RuntimeError, match="ffprobe"),
        ):
            _get_audio_duration(audio_file)


# ---------------------------------------------------------------------------
# Test _split_audio
# ---------------------------------------------------------------------------


class TestSplitAudio:
    def test_calls_ffmpeg_with_correct_args(self, tmp_path: Path) -> None:
        """_split_audio must invoke ffmpeg with segment muxer and correct duration."""
        audio_file = tmp_path / "long.wav"
        audio_file.touch()

        # Create a fake chunk in the expected temp directory to avoid RuntimeError
        fake_chunk = tmp_path / "chunk_000.wav"
        fake_chunk.touch()

        with (
            patch("deep_thought.audio.engines.mlx_whisper_engine.subprocess.run") as mock_subprocess,
            patch("deep_thought.audio.engines.mlx_whisper_engine.tempfile.mkdtemp") as mock_mkdtemp,
        ):
            mock_mkdtemp.return_value = str(tmp_path)
            mock_subprocess.return_value = MagicMock(returncode=0)

            chunks = _split_audio(audio_file, chunk_minutes=5)

        call_args = mock_subprocess.call_args[0][0]
        assert call_args[0] == "ffmpeg"
        assert "-f" in call_args
        assert "segment" in call_args
        assert "-segment_time" in call_args
        assert "300" in call_args  # 5 minutes * 60 seconds
        assert str(audio_file) in call_args
        assert len(chunks) == 1

    def test_raises_runtime_error_when_ffmpeg_produces_no_chunks(self, tmp_path: Path) -> None:
        """_split_audio must raise RuntimeError when no chunk files are produced."""
        audio_file = tmp_path / "audio.wav"
        audio_file.touch()

        with (
            patch("deep_thought.audio.engines.mlx_whisper_engine.subprocess.run"),
            patch("deep_thought.audio.engines.mlx_whisper_engine.tempfile.mkdtemp") as mock_mkdtemp,
        ):
            # Use a fresh empty directory so no chunks are found
            empty_dir = tmp_path / "empty_chunks"
            empty_dir.mkdir()
            mock_mkdtemp.return_value = str(empty_dir)

            with pytest.raises(RuntimeError, match="FFmpeg produced no chunks"):
                _split_audio(audio_file, chunk_minutes=5)

    def test_returns_sorted_chunk_paths(self, tmp_path: Path) -> None:
        """_split_audio must return chunk files in sorted order."""
        audio_file = tmp_path / "audio.mp3"
        audio_file.touch()

        chunk_dir = tmp_path / "chunk_output"
        chunk_dir.mkdir()
        # Create chunks out of order
        (chunk_dir / "chunk_002.mp3").touch()
        (chunk_dir / "chunk_000.mp3").touch()
        (chunk_dir / "chunk_001.mp3").touch()

        with (
            patch("deep_thought.audio.engines.mlx_whisper_engine.subprocess.run"),
            patch("deep_thought.audio.engines.mlx_whisper_engine.tempfile.mkdtemp") as mock_mkdtemp,
        ):
            mock_mkdtemp.return_value = str(chunk_dir)
            chunks = _split_audio(audio_file, chunk_minutes=5)

        names = [c.name for c in chunks]
        assert names == sorted(names)
