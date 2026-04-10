# Audio Tool

Transcribes audio files to LLM-optimized markdown using Whisper or MLX-Whisper, with optional speaker diarization and hallucination detection.

## Overview

The Audio Tool processes audio files (MP3, WAV, M4A, etc.), transcribes them using either OpenAI Whisper or MLX-Whisper (optimized for Apple Silicon), detects speakers via diarization, checks for hallucinated text, and exports structured markdown files. All metadata and transcripts are stored in a local SQLite database.

## Data Flow

```
Audio File → Transcription Engine → Diarization → Hallucination Check → SQLite DB → Markdown Export
```

## Setup

1. Configure which audio files to process in `src/config/audio-configuration.yaml`.

2. Initialize the database:

   ```bash
   audio init
   ```

3. Run transcription on a directory or file:

   ```bash
   audio transcribe --input /path/to/audio/files
   ```

## CLI Reference

```
audio [--config PATH] [--verbose]
audio transcribe [flags]    # Transcribe audio files (default when no subcommand given)
audio config                # Validate and display the current configuration
audio init [--save-config PATH]  # Create config file, output directory, and database
```

### Transcription flags

| Flag                                          | Description                                                                         |
| --------------------------------------------- | ----------------------------------------------------------------------------------- |
| `--input PATH`                                | Input file or directory (default: `input/`)                                         |
| `--output PATH`                               | Output directory (overrides config)                                                 |
| `--engine mlx\|whisper\|auto`                 | Transcription engine                                                                |
| `--model SIZE`                                | Whisper model size: `tiny`, `base`, `small`, `medium`, `large-v3`, `large-v3-turbo` |
| `--language TEXT`                             | Force language code (e.g., `en`, `fr`); omit for auto-detect                        |
| `--output-mode paragraph\|segment\|timestamp` | Transcript format                                                                   |
| `--pause-threshold SECS`                      | Pause duration that triggers a paragraph break                                      |
| `--diarize / --no-diarize`                    | Enable or disable speaker identification                                            |
| `--remove-fillers / --no-remove-fillers`      | Strip filler words                                                                  |
| `--llm`                                       | Generate `llms.txt` / `llms-full.txt` aggregate files                               |
| `--force`                                     | Reprocess files already in the database                                             |
| `--nuke`                                      | Delete input files after successful processing                                      |
| `--dry-run`                                   | Preview files that would be processed without transcribing                          |

## Configuration

Configuration lives at `src/config/audio-configuration.yaml`. All fields are at the top level except hallucination detection, which is nested under `hallucination_detection`.

| Field                                                 | Description                                                  |
| ----------------------------------------------------- | ------------------------------------------------------------ |
| `engine`                                              | Transcription backend: `mlx`, `whisper`, or `auto`           |
| `model`                                               | Whisper model size (e.g., `large-v3-turbo`)                  |
| `language`                                            | Language code for transcription; `null` for auto-detect      |
| `output_mode`                                         | Transcript format: `paragraph`, `segment`, or `timestamp`    |
| `pause_threshold`                                     | Seconds of silence to trigger a paragraph break              |
| `output_dir`                                          | Directory for markdown export                                |
| `generate_llms_files`                                 | Generate aggregate `llms.txt` / `llms-full.txt` files        |
| `diarize`                                             | Enable speaker detection (requires HuggingFace token)        |
| `hf_token_env`                                        | Env var holding the HuggingFace token for diarization        |
| `remove_fillers`                                      | Strip filler words from transcripts                          |
| `max_file_size_mb`                                    | Skip files above this size                                   |
| `chunk_duration_minutes`                              | Split audio into chunks of this length (MLX only)            |
| `hallucination_detection.score_threshold`             | Number of signals that must flag before action is taken      |
| `hallucination_detection.action`                      | What to do with flagged segments: `remove`, `flag`, or `log` |
| `hallucination_detection.blocklist_enabled`           | Check against known hallucination phrases                    |
| `hallucination_detection.repetition_threshold`        | Max allowed phrase repetitions in a window                   |
| `hallucination_detection.compression_ratio_threshold` | Flag segments above this compression ratio                   |
| `hallucination_detection.confidence_floor`            | Average log-probability floor per segment                    |
| `hallucination_detection.no_speech_prob_threshold`    | Flag segments above this no-speech probability               |
| `hallucination_detection.duration_chars_per_sec_max`  | Flag segments exceeding this text density                    |
| `hallucination_detection.duration_chars_per_sec_min`  | Flag segments below this text density                        |

## Module Structure

| Module                          | Role                                                                                         |
| ------------------------------- | -------------------------------------------------------------------------------------------- |
| `cli.py`                        | CLI entry point with argparse subcommands                                                    |
| `config.py`                     | YAML config loader with .env integration                                                     |
| `models.py`                     | Local dataclasses for transcription results and metadata                                     |
| `processor.py`                  | Orchestration: filter files → transcribe → diarize → hallucination check → export → DB write |
| `engines/whisper_engine.py`     | OpenAI Whisper API wrapper                                                                   |
| `engines/mlx_whisper_engine.py` | MLX-Whisper (Apple Silicon) implementation                                                   |
| `diarization.py`                | Speaker detection and clustering                                                             |
| `hallucination.py`              | Multi-signal hallucination detection and scoring                                             |
| `filters.py`                    | Input file filtering and validation                                                          |
| `output.py`                     | Markdown export formatting                                                                   |
| `llms.py`                       | LLM aggregate file generation                                                                |
| `db/`                           | SQLite schema, migrations, and query functions                                               |

## Data Storage

All paths are rooted at `data/audio/` by default. Set `DEEP_THOUGHT_DATA_DIR` to redirect everything to a different location.

- **SQLite database** — `<data_dir>/audio.db` (canonical store)
- **Markdown export** — `<data_dir>/export/<filename>.md`

## Tool-Specific Notes

- **Apple Silicon optimized:** MLX-Whisper runs natively on M-series chips without GPU overhead; requires `mlx` and `mlx-whisper` extras
- **Diarization:** Requires `pyannote.audio` and a HuggingFace token set in the env var named by `hf_token_env`
- **Hallucination detection:** Multi-signal scoring system; segments that exceed `score_threshold` active signals are acted on per the `action` setting
- **Rate limiting:** Local Whisper runs fully offline; no API rate limits apply
