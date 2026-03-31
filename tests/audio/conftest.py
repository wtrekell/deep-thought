"""Shared fixtures for the audio tool test suite."""

from __future__ import annotations

import struct
import wave
from pathlib import Path  # noqa: TC003
from typing import TYPE_CHECKING

import pytest

from deep_thought.audio.config import (
    AudioConfig,
    DiarizationConfig,
    EngineConfig,
    FillerConfig,
    HallucinationConfig,
    LimitsConfig,
    OutputConfig,
)

if TYPE_CHECKING:
    import sqlite3

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture()
def sample_config() -> AudioConfig:
    """Return an AudioConfig with safe, predictable test defaults."""
    return AudioConfig(
        engine=EngineConfig(
            engine="mlx",
            model="small",
            language="en",
        ),
        output=OutputConfig(
            output_mode="paragraph",
            pause_threshold=1.5,
            output_dir="data/audio/export/",
            generate_llms_files=True,
        ),
        diarization=DiarizationConfig(
            diarize=False,
            hf_token_env="HF_TOKEN",
        ),
        filler=FillerConfig(
            remove_fillers=False,
        ),
        limits=LimitsConfig(
            max_file_size_mb=100,
            chunk_duration_minutes=5,
        ),
        hallucination=HallucinationConfig(
            repetition_threshold=3,
            compression_ratio_threshold=2.4,
            confidence_floor=-1.0,
            no_speech_prob_threshold=0.6,
            duration_chars_per_sec_max=25,
            duration_chars_per_sec_min=2,
            blocklist_enabled=True,
            score_threshold=2,
            action="remove",
        ),
    )


@pytest.fixture()
def in_memory_db() -> sqlite3.Connection:
    """Return an in-memory SQLite connection with the audio schema initialised."""
    from deep_thought.audio.db.schema import initialize_database

    return initialize_database(":memory:")


@pytest.fixture()
def sample_wav(tmp_path: Path) -> Path:
    """Create a minimal valid WAV file (1 second of silence, 16 kHz, mono, 16-bit).

    Uses Python's stdlib wave module — no external dependencies required.
    """
    sample_rate = 16000
    num_channels = 1
    sample_width_bytes = 2  # 16-bit
    num_frames = sample_rate  # 1 second of audio

    wav_path = tmp_path / "sample.wav"

    with wave.open(str(wav_path), "wb") as wav_file:
        wav_file.setnchannels(num_channels)
        wav_file.setsampwidth(sample_width_bytes)
        wav_file.setframerate(sample_rate)
        # Write silence: num_frames * num_channels * sample_width_bytes zero bytes
        silent_frames = struct.pack("<" + "h" * num_frames, *([0] * num_frames))
        wav_file.writeframes(silent_frames)

    return wav_path


@pytest.fixture()
def tmp_config_file(tmp_path: Path) -> Path:
    """Write the test fixture YAML config to a temporary path and return it."""
    source = FIXTURES_DIR / "test_config.yaml"
    destination = tmp_path / "audio-configuration.yaml"
    destination.write_bytes(source.read_bytes())
    return destination
