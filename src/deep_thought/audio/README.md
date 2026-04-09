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
   audio --input /path/to/audio/files
   ```

## Configuration

Configuration lives at `src/config/audio-configuration.yaml`. Key settings:

- **engine** — Which transcription backend to use: `whisper` (OpenAI API) or `mlx-whisper` (Apple Silicon native)
- **diarization** — Enable/disable speaker detection
- **language** — Language code for transcription (e.g., `en`, `es`)
- **detect_hallucinations** — Enable/disable hallucination scoring on transcripts

## Module Structure

| Module                          | Role                                                                                       |
| ------------------------------- | ------------------------------------------------------------------------------------------ |
| `cli.py`                        | CLI entry point with argparse subcommands                                                  |
| `config.py`                     | YAML config loader with .env integration                                                   |
| `models.py`                     | Local dataclasses for transcription results and metadata                                   |
| `processor.py`                  | Orchestration: filter files → transcribe → diarize → hallucinate check → export → DB write |
| `engines/whisper_engine.py`     | OpenAI Whisper API wrapper                                                                 |
| `engines/mlx_whisper_engine.py` | MLX-Whisper (Apple Silicon) implementation                                                 |
| `diarization.py`                | Speaker detection and clustering                                                           |
| `hallucination.py`              | Detects and scores hallucinated/repeated segments                                          |
| `filters.py`                    | Input file filtering and validation                                                        |
| `output.py`                     | Markdown export formatting                                                                 |
| `llms.py`                       | LLM-specific output aggregation                                                            |
| `db/`                           | SQLite schema, migrations, and query functions                                             |

## Data Storage

All paths are rooted at `data/audio/` by default. Set `DEEP_THOUGHT_DATA_DIR` to redirect everything to a different location.

- **SQLite database** — `<data_dir>/audio.db` (canonical store)
- **Markdown export** — `<data_dir>/export/<filename>.md`

## Tool-Specific Notes

- **Apple Silicon optimized:** MLX-Whisper runs natively on M-series chips without GPU overhead; requires `mlx` and `mlx-whisper` extras
- **Diarization:** Requires `pyannote.audio` (specify in config; handles speaker boundaries within transcripts)
- **Hallucination detection:** Scores repeated or incoherent segments; threshold is configurable
- **Rate limiting:** Local Whisper runs fully offline; no API rate limits apply
