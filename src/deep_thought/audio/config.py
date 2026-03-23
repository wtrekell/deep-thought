"""YAML configuration loader for the audio tool."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class EngineConfig:
    """Configuration for the transcription engine selection and model."""

    engine: str
    model: str
    language: str | None


@dataclass
class OutputConfig:
    """Configuration for transcript output formatting and destination."""

    output_mode: str
    pause_threshold: float
    output_dir: str
    generate_llms_files: bool


@dataclass
class DiarizationConfig:
    """Configuration for speaker diarization."""

    diarize: bool
    hf_token_env: str


@dataclass
class FillerConfig:
    """Configuration for filler word removal."""

    remove_fillers: bool


@dataclass
class LimitsConfig:
    """Configuration for processing limits and chunking behaviour."""

    max_file_size_mb: int
    chunk_duration_minutes: int


@dataclass
class HallucinationConfig:
    """Configuration for the multi-signal hallucination detection system."""

    repetition_threshold: int
    compression_ratio_threshold: float
    confidence_floor: float
    no_speech_prob_threshold: float
    duration_chars_per_sec_max: int
    duration_chars_per_sec_min: int
    use_vad: bool
    blocklist_enabled: bool
    score_threshold: int
    action: str


@dataclass
class AudioConfig:
    """Top-level configuration for the audio tool."""

    engine: EngineConfig
    output: OutputConfig
    diarization: DiarizationConfig
    filler: FillerConfig
    limits: LimitsConfig
    hallucination: HallucinationConfig


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
_DEFAULT_CONFIG_RELATIVE_PATH = Path("src") / "config" / "audio-configuration.yaml"


def get_default_config_path() -> Path:
    """Return the absolute path to the default YAML configuration file."""
    return _PROJECT_ROOT / _DEFAULT_CONFIG_RELATIVE_PATH


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def _parse_engine_config(raw: dict[str, Any]) -> EngineConfig:
    """Parse engine-related fields from the top-level YAML mapping.

    Args:
        raw: The full YAML mapping as a dict.

    Returns:
        An EngineConfig with engine, model, and language populated.
    """
    engine: str = raw.get("engine", "mlx")
    model: str = raw.get("model", "large-v3-turbo")
    language_raw = raw.get("language")
    language: str | None = str(language_raw) if language_raw is not None else None
    return EngineConfig(engine=engine, model=model, language=language)


def _parse_output_config(raw: dict[str, Any]) -> OutputConfig:
    """Parse output-related fields from the top-level YAML mapping.

    Args:
        raw: The full YAML mapping as a dict.

    Returns:
        An OutputConfig with output_mode, pause_threshold, output_dir, and
        generate_llms_files populated.
    """
    output_mode: str = raw.get("output_mode", "paragraph")
    pause_threshold: float = raw.get("pause_threshold", 1.5)
    output_dir: str = raw.get("output_dir", "data/audio/export/")
    generate_llms_files: bool = raw.get("generate_llms_files", False)
    return OutputConfig(
        output_mode=output_mode,
        pause_threshold=pause_threshold,
        output_dir=output_dir,
        generate_llms_files=generate_llms_files,
    )


def _parse_diarization_config(raw: dict[str, Any]) -> DiarizationConfig:
    """Parse diarization-related fields from the top-level YAML mapping.

    Args:
        raw: The full YAML mapping as a dict.

    Returns:
        A DiarizationConfig with diarize and hf_token_env populated.
    """
    diarize: bool = raw.get("diarize", False)
    hf_token_env: str = raw.get("hf_token_env", "HF_TOKEN")
    return DiarizationConfig(diarize=diarize, hf_token_env=hf_token_env)


def _parse_filler_config(raw: dict[str, Any]) -> FillerConfig:
    """Parse filler-word-related fields from the top-level YAML mapping.

    Args:
        raw: The full YAML mapping as a dict.

    Returns:
        A FillerConfig with remove_fillers populated.
    """
    remove_fillers: bool = raw.get("remove_fillers", False)
    return FillerConfig(remove_fillers=remove_fillers)


def _parse_limits_config(raw: dict[str, Any]) -> LimitsConfig:
    """Parse limits-related fields from the top-level YAML mapping.

    Args:
        raw: The full YAML mapping as a dict.

    Returns:
        A LimitsConfig with max_file_size_mb and chunk_duration_minutes populated.

    Raises:
        ValueError: If max_file_size_mb or chunk_duration_minutes is not an integer.
    """
    raw_max_mb = raw.get("max_file_size_mb", 500)
    if not isinstance(raw_max_mb, int):
        raise ValueError(f"max_file_size_mb must be an integer, got: {type(raw_max_mb).__name__}")

    raw_chunk_minutes = raw.get("chunk_duration_minutes", 5)
    if not isinstance(raw_chunk_minutes, int):
        raise ValueError(f"chunk_duration_minutes must be an integer, got: {type(raw_chunk_minutes).__name__}")

    return LimitsConfig(max_file_size_mb=raw_max_mb, chunk_duration_minutes=raw_chunk_minutes)


def _parse_hallucination_config(raw: dict[str, Any]) -> HallucinationConfig:
    """Parse hallucination detection fields from the nested 'hallucination_detection' key.

    Args:
        raw: The full YAML mapping as a dict.

    Returns:
        A HallucinationConfig with all detection thresholds populated.
    """
    nested: dict[str, Any] = raw.get("hallucination_detection", {})
    if not isinstance(nested, dict):
        nested = {}

    repetition_threshold: int = nested.get("repetition_threshold", 3)
    compression_ratio_threshold: float = nested.get("compression_ratio_threshold", 2.4)
    confidence_floor: float = nested.get("confidence_floor", -1.0)
    no_speech_prob_threshold: float = nested.get("no_speech_prob_threshold", 0.6)
    duration_chars_per_sec_max: int = nested.get("duration_chars_per_sec_max", 25)
    duration_chars_per_sec_min: int = nested.get("duration_chars_per_sec_min", 2)
    use_vad: bool = nested.get("use_vad", True)
    blocklist_enabled: bool = nested.get("blocklist_enabled", True)
    score_threshold: int = nested.get("score_threshold", 2)
    action: str = nested.get("action", "remove")

    return HallucinationConfig(
        repetition_threshold=repetition_threshold,
        compression_ratio_threshold=compression_ratio_threshold,
        confidence_floor=confidence_floor,
        no_speech_prob_threshold=no_speech_prob_threshold,
        duration_chars_per_sec_max=duration_chars_per_sec_max,
        duration_chars_per_sec_min=duration_chars_per_sec_min,
        use_vad=use_vad,
        blocklist_enabled=blocklist_enabled,
        score_threshold=score_threshold,
        action=action,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_config(config_path: Path | None = None) -> AudioConfig:
    """Load the YAML configuration and return a typed AudioConfig.

    If config_path is None the default path is used
    (src/config/audio-configuration.yaml relative to the project root).

    Calls load_dotenv() so that environment variable references in the config
    (e.g. hf_token_env) resolve correctly at runtime.

    Args:
        config_path: Optional explicit path to the YAML configuration file.

    Returns:
        A fully parsed AudioConfig.

    Raises:
        FileNotFoundError: If the configuration file does not exist.
        ValueError: If the file does not contain a valid YAML mapping, or if
                    any field value is of the wrong type.
    """
    load_dotenv()

    resolved_path = config_path if config_path is not None else get_default_config_path()

    if not resolved_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {resolved_path}")

    with resolved_path.open("r", encoding="utf-8") as config_file:
        raw: Any = yaml.safe_load(config_file)

    if not isinstance(raw, dict):
        raise ValueError(f"Configuration file must contain a YAML mapping, got: {type(raw).__name__}")

    raw_dict: dict[str, Any] = raw

    engine_config = _parse_engine_config(raw_dict)
    output_config = _parse_output_config(raw_dict)
    diarization_config = _parse_diarization_config(raw_dict)
    filler_config = _parse_filler_config(raw_dict)
    limits_config = _parse_limits_config(raw_dict)
    hallucination_config = _parse_hallucination_config(raw_dict)

    return AudioConfig(
        engine=engine_config,
        output=output_config,
        diarization=diarization_config,
        filler=filler_config,
        limits=limits_config,
        hallucination=hallucination_config,
    )


_VALID_ENGINES = {"mlx", "whisper", "auto"}
_VALID_MODELS = {"tiny", "base", "small", "medium", "large-v3", "large-v3-turbo"}
_VALID_OUTPUT_MODES = {"paragraph", "segment", "timestamp"}
_VALID_HALLUCINATION_ACTIONS = {"remove", "flag", "log"}


def validate_config(config: AudioConfig) -> list[str]:
    """Validate the loaded configuration and return a list of warning/error messages.

    An empty list means the configuration is valid.

    Args:
        config: A loaded AudioConfig to validate.

    Returns:
        A list of human-readable issue strings. Empty list means no issues.
    """
    issues: list[str] = []

    if config.engine.engine not in _VALID_ENGINES:
        issues.append(f"engine '{config.engine.engine}' is not valid. Must be one of: {sorted(_VALID_ENGINES)}.")

    if config.engine.model not in _VALID_MODELS:
        issues.append(f"model '{config.engine.model}' is not valid. Must be one of: {sorted(_VALID_MODELS)}.")

    if config.output.output_mode not in _VALID_OUTPUT_MODES:
        issues.append(
            f"output_mode '{config.output.output_mode}' is not valid. Must be one of: {sorted(_VALID_OUTPUT_MODES)}."
        )

    if config.hallucination.action not in _VALID_HALLUCINATION_ACTIONS:
        issues.append(
            f"hallucination action '{config.hallucination.action}' is not valid. "
            f"Must be one of: {sorted(_VALID_HALLUCINATION_ACTIONS)}."
        )

    if config.hallucination.score_threshold < 1:
        issues.append(f"hallucination score_threshold must be >= 1, got: {config.hallucination.score_threshold}.")

    if config.limits.max_file_size_mb <= 0:
        issues.append(f"max_file_size_mb must be greater than 0, got: {config.limits.max_file_size_mb}.")

    if config.output.pause_threshold <= 0:
        issues.append(f"output.pause_threshold must be positive, got: {config.output.pause_threshold}.")

    if config.limits.chunk_duration_minutes <= 0:
        issues.append(f"limits.chunk_duration_minutes must be positive, got: {config.limits.chunk_duration_minutes}.")

    return issues


def save_default_config(destination_path: Path) -> None:
    """Write the bundled default configuration YAML to destination_path.

    Creates parent directories as needed.

    Args:
        destination_path: Where to write the default config file.

    Raises:
        FileExistsError: If a file already exists at destination_path.
        FileNotFoundError: If the bundled default config cannot be located.
    """
    if destination_path.exists():
        raise FileExistsError(f"Configuration file already exists: {destination_path}")

    source_path = get_default_config_path()
    if not source_path.exists():
        raise FileNotFoundError(f"Bundled default config not found: {source_path}")

    destination_path.parent.mkdir(parents=True, exist_ok=True)
    destination_path.write_bytes(source_path.read_bytes())
