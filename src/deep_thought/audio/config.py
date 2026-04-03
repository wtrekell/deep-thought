"""YAML configuration loader for the audio tool."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

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

_PACKAGE_DIR = Path(__file__).resolve().parent
_BUNDLED_DEFAULT_CONFIG = _PACKAGE_DIR / "default-config.yaml"
_PROJECT_CONFIG_RELATIVE_PATH = Path("src") / "config" / "audio-configuration.yaml"


def get_bundled_config_path() -> Path:
    """Return the absolute path to the bundled default config template.

    This resolves via ``__file__`` so it always finds the template inside the
    package, regardless of symlinks or the current working directory.

    Returns:
        Absolute path to the ``default-config.yaml`` bundled in the package.
    """
    return _BUNDLED_DEFAULT_CONFIG


def get_default_config_path() -> Path:
    """Return the absolute path to the project-level configuration file.

    Resolves relative to the current working directory so it targets the
    *calling repo*, not the source repo (deep-thought).

    Returns:
        Absolute path to src/config/audio-configuration.yaml in the calling repo.
    """
    return Path.cwd() / _PROJECT_CONFIG_RELATIVE_PATH


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def _parse_engine_config(raw: dict[str, Any]) -> EngineConfig:
    """Parse engine-related fields from the top-level YAML mapping.

    Args:
        raw: The full YAML mapping as a dict.

    Returns:
        An EngineConfig with engine, model, and language populated.

    Raises:
        ValueError: If any field is of the wrong type.
    """
    raw_engine = raw.get("engine", "mlx")
    if not isinstance(raw_engine, str):
        raise ValueError(f"engine must be a string, got: {type(raw_engine).__name__}")
    engine: str = raw_engine

    raw_model = raw.get("model", "large-v3-turbo")
    if not isinstance(raw_model, str):
        raise ValueError(f"model must be a string, got: {type(raw_model).__name__}")
    model: str = raw_model

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

    Raises:
        ValueError: If any field is of the wrong type.
    """
    raw_output_mode = raw.get("output_mode", "paragraph")
    if not isinstance(raw_output_mode, str):
        raise ValueError(f"output_mode must be a string, got: {type(raw_output_mode).__name__}")
    output_mode: str = raw_output_mode

    raw_pause_threshold = raw.get("pause_threshold", 1.5)
    if not isinstance(raw_pause_threshold, (int, float)):
        raise ValueError(f"pause_threshold must be a number, got: {type(raw_pause_threshold).__name__}")
    pause_threshold: float = float(raw_pause_threshold)

    raw_output_dir = raw.get("output_dir", "data/audio/export/")
    if not isinstance(raw_output_dir, str):
        raise ValueError(f"output_dir must be a string, got: {type(raw_output_dir).__name__}")
    output_dir: str = raw_output_dir

    raw_generate_llms = raw.get("generate_llms_files", False)
    if not isinstance(raw_generate_llms, bool):
        raise ValueError(f"generate_llms_files must be a boolean, got: {type(raw_generate_llms).__name__}")
    generate_llms_files: bool = raw_generate_llms

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

    Raises:
        ValueError: If any field is of the wrong type.
    """
    raw_diarize = raw.get("diarize", False)
    if not isinstance(raw_diarize, bool):
        raise ValueError(f"diarize must be a boolean, got: {type(raw_diarize).__name__}")
    diarize: bool = raw_diarize

    raw_hf_token_env = raw.get("hf_token_env", "HF_TOKEN")
    if not isinstance(raw_hf_token_env, str):
        raise ValueError(f"hf_token_env must be a string, got: {type(raw_hf_token_env).__name__}")
    hf_token_env: str = raw_hf_token_env

    return DiarizationConfig(diarize=diarize, hf_token_env=hf_token_env)


def _parse_filler_config(raw: dict[str, Any]) -> FillerConfig:
    """Parse filler-word-related fields from the top-level YAML mapping.

    Args:
        raw: The full YAML mapping as a dict.

    Returns:
        A FillerConfig with remove_fillers populated.

    Raises:
        ValueError: If any field is of the wrong type.
    """
    raw_remove_fillers = raw.get("remove_fillers", False)
    if not isinstance(raw_remove_fillers, bool):
        raise ValueError(f"remove_fillers must be a boolean, got: {type(raw_remove_fillers).__name__}")
    remove_fillers: bool = raw_remove_fillers
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

    Raises:
        ValueError: If any field is of the wrong type.
    """
    nested: dict[str, Any] = raw.get("hallucination_detection", {})
    if not isinstance(nested, dict):
        nested = {}

    # Warn if the deprecated use_vad field is present in the config
    if "use_vad" in nested:
        logger.warning(
            "hallucination_detection.use_vad is deprecated and has no effect. Remove it from your configuration file."
        )

    raw_repetition_threshold = nested.get("repetition_threshold", 3)
    if not isinstance(raw_repetition_threshold, int):
        raise ValueError(
            f"hallucination_detection.repetition_threshold must be an integer, "
            f"got: {type(raw_repetition_threshold).__name__}"
        )
    repetition_threshold: int = raw_repetition_threshold

    raw_compression_ratio = nested.get("compression_ratio_threshold", 2.4)
    if not isinstance(raw_compression_ratio, (int, float)):
        raise ValueError(
            f"hallucination_detection.compression_ratio_threshold must be a number, "
            f"got: {type(raw_compression_ratio).__name__}"
        )
    compression_ratio_threshold: float = float(raw_compression_ratio)

    raw_confidence_floor = nested.get("confidence_floor", -1.0)
    if not isinstance(raw_confidence_floor, (int, float)):
        raise ValueError(
            f"hallucination_detection.confidence_floor must be a number, got: {type(raw_confidence_floor).__name__}"
        )
    confidence_floor: float = float(raw_confidence_floor)

    raw_no_speech_prob = nested.get("no_speech_prob_threshold", 0.6)
    if not isinstance(raw_no_speech_prob, (int, float)):
        raise ValueError(
            f"hallucination_detection.no_speech_prob_threshold must be a number, "
            f"got: {type(raw_no_speech_prob).__name__}"
        )
    no_speech_prob_threshold: float = float(raw_no_speech_prob)

    raw_chars_max = nested.get("duration_chars_per_sec_max", 25)
    if not isinstance(raw_chars_max, int):
        raise ValueError(
            f"hallucination_detection.duration_chars_per_sec_max must be an integer, "
            f"got: {type(raw_chars_max).__name__}"
        )
    duration_chars_per_sec_max: int = raw_chars_max

    raw_chars_min = nested.get("duration_chars_per_sec_min", 2)
    if not isinstance(raw_chars_min, int):
        raise ValueError(
            f"hallucination_detection.duration_chars_per_sec_min must be an integer, "
            f"got: {type(raw_chars_min).__name__}"
        )
    duration_chars_per_sec_min: int = raw_chars_min

    raw_blocklist_enabled = nested.get("blocklist_enabled", True)
    if not isinstance(raw_blocklist_enabled, bool):
        raise ValueError(
            f"hallucination_detection.blocklist_enabled must be a boolean, got: {type(raw_blocklist_enabled).__name__}"
        )
    blocklist_enabled: bool = raw_blocklist_enabled

    raw_score_threshold = nested.get("score_threshold", 2)
    if not isinstance(raw_score_threshold, int):
        raise ValueError(
            f"hallucination_detection.score_threshold must be an integer, got: {type(raw_score_threshold).__name__}"
        )
    score_threshold: int = raw_score_threshold

    raw_action = nested.get("action", "remove")
    if not isinstance(raw_action, str):
        raise ValueError(f"hallucination_detection.action must be a string, got: {type(raw_action).__name__}")
    action: str = raw_action

    return HallucinationConfig(
        repetition_threshold=repetition_threshold,
        compression_ratio_threshold=compression_ratio_threshold,
        confidence_floor=confidence_floor,
        no_speech_prob_threshold=no_speech_prob_threshold,
        duration_chars_per_sec_max=duration_chars_per_sec_max,
        duration_chars_per_sec_min=duration_chars_per_sec_min,
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

    source_path = get_bundled_config_path()
    if not source_path.exists():
        raise FileNotFoundError(f"Bundled default config not found: {source_path}")

    destination_path.parent.mkdir(parents=True, exist_ok=True)
    destination_path.write_bytes(source_path.read_bytes())
