# Product Brief — Audio Tool

## Name and Purpose

**Audio Tool** — transcribes audio files to LLM-optimized markdown using Whisper or MLX-Whisper. Supports speaker diarization, three output modes, and multi-layer hallucination detection for reliable transcriptions.

**Data flow:** Audio files → Whisper/MLX engine → (optional diarization) → hallucination detection → SQLite state tracking → markdown export.

## Processing Modes

1. **CLI Command** — `audio` (entry point)
2. **Standard Transcription** — Whisper engine (universal, all platforms)
3. **Optimized Transcription** — MLX-Whisper engine (Apple Silicon, 2–3x faster; required for chunked processing)
4. **With Diarization** — PyAnnote speaker identification runs in parallel with transcription

## Requirements

1. Python 3.12 using `uv` as the package manager.
2. **MLX-Whisper** (`mlx-whisper`) for Apple Silicon transcription (default engine).
3. **Whisper** (`openai-whisper`) for standard transcription (optional extra; cross-platform fallback).
4. **PyAnnote** (`pyannote.audio`) for speaker diarization (optional extra); requires HuggingFace token.
5. **FFmpeg** (system dependency) for audio chunking (MLX path) and format conversion.
6. SQLite for local state tracking (WAL mode, foreign keys enabled).
7. HuggingFace token stored in `.env` as `HF_TOKEN` (diarization only).
8. A changelog is maintained in `files/tools/audio/CHANGELOG.md`.

## Data Storage

### State Database

Tracks processed files to support resume and incremental operation. Located at `data/audio/audio.db` by default; respects the `DEEP_THOUGHT_DATA_DIR` env var to redirect the data root at runtime.

- Table: `processed_files` — columns: `file_path TEXT PRIMARY KEY`, `file_hash TEXT`, `engine TEXT`, `model TEXT`, `duration_seconds REAL`, `speaker_count INT`, `output_path TEXT`, `status TEXT`, `created_at TEXT`, `updated_at TEXT`
- State key: file path
- Schema version tracked in a `key_value` table
- Migrations stored in `db/migrations/` with numeric prefixes, applied forward-only in sequential order

#### Database Conventions

- WAL mode and foreign keys enabled at connection time
- `INSERT OR REPLACE` for upsert operations on `processed_files`
- Indexes on columns used for lookups (e.g., `status`, `file_hash`)
- `updated_at` set locally on write; `created_at` set on first insert
- Cascading deletes where referential integrity applies

### Raw Output Snapshots

After each processing run, store the raw engine output (segments with timestamps, confidence scores, and word-level data) as a JSON file in `data/audio/snapshots/` named by ISO timestamp. These serve as a debugging and backup mechanism; the SQLite database and markdown exports remain canonical.

## Data Models

### ProcessedFileLocal

| Field              | Type    | Description                                                |
| ------------------ | ------- | ---------------------------------------------------------- |
| `file_path`        | `str`   | Absolute or relative path to the source file (primary key) |
| `file_hash`        | `str`   | Hash of file contents for change detection                 |
| `engine`           | `str`   | Engine used for transcription (`whisper` or `mlx`)         |
| `model`            | `str`   | Whisper model size used (e.g., `base`, `large`)            |
| `duration_seconds` | `float` | Duration of the audio file in seconds                      |
| `speaker_count`    | `int`   | Number of identified speakers (diarization)                |
| `output_path`      | `str`   | Path to the generated output directory                     |
| `status`           | `str`   | Processing status (`success`, `error`, `skipped`)          |
| `created_at`       | `str`   | ISO 8601 timestamp when the record was created             |
| `updated_at`       | `str`   | ISO 8601 timestamp when the record was last updated        |

Methods: `to_dict()` for database insertion.

### Intermediate Models

These models represent data flowing through the processing pipeline. They are not persisted directly but are used between engine output and final export.

| Model                 | Description                                                                                                                            |
| --------------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| `TranscriptSegment`   | A single transcription segment: `start` (float), `end` (float), `text` (str), `confidence` (float, optional), `words` (list, optional) |
| `SpeakerSegment`      | Diarization result: `speaker_label` (str), `start` (float), `end` (float)                                                              |
| `ChunkResult`         | Result from a single audio chunk (MLX path): `chunk_index` (int), `segments` (list[TranscriptSegment]), `duration` (float)             |
| `TranscriptionResult` | Aggregated engine output: `segments` (list[TranscriptSegment]), `language` (str), `duration_seconds` (float)                           |

## Hallucination Detection

MLX-Whisper can produce hallucinated output — repeated phrases, fabricated text during silence, or garbled segments. The audio tool uses a multi-layer detection strategy applied after transcription and before export. Layers are used as a scoring system rather than independent hard filters — a segment flagged by two or more detectors is far more likely to be a genuine hallucination than one flagged by a single detector alone.

### Detection Layers

1. **Repetition detection** — flag segments where the same phrase repeats more than a configurable threshold within a sliding window. Normalize text (lowercase, strip punctuation) before comparison. Use bigram and trigram matching. Complement with Whisper's internal `compression_ratio` metric (segments above 2.4 are suspect). This is the single most common hallucination pattern — the decoder enters a loop generating phrases like "Thank you for watching" or repeating the last real sentence.
2. **Silence-gap detection** — use a Voice Activity Detector (Silero VAD or similar) to identify segments where no speech was detected, rather than raw audio energy which cannot distinguish speech from background noise. Also check Whisper's `no_speech_prob` field per segment — values above 0.6 are suspect. Whisper commonly fills silent passages with fabricated text from its YouTube training data.
3. **Confidence filtering** — use average log-probability per segment and word-level confidence scores as a weighting signal, not a hard cutoff. Segments with low confidence AND another hallucination signal get higher priority for removal. Note: some hallucinations (e.g., memorized phrases like "Subscribe to my channel") are produced with high confidence, so this layer is not reliable standalone.
4. **Duration anomaly detection** — flag segments whose text length is disproportionate to their time span. Normal speech is roughly 12–18 characters per second. Flag segments above ~25 chars/sec (text burst) or below ~2 chars/sec for segments longer than 1 second. Apply a minimum duration threshold (0.5s) before computing the ratio.
5. **Compression ratio check** — Whisper computes a `compression_ratio` per segment measuring how compressible the text is. Highly repetitive or formulaic text has a high ratio. Flag segments with ratio above 2.4 (Whisper's own internal threshold).
6. **Known-phrase blocklist** — maintain a list of common Whisper hallucination phrases from its YouTube training data (e.g., "Thank you for watching", "Please subscribe", "Subtitled by...", "Transcribed by..."). Flag segments matching these phrases, especially when they appear near silence or at the end of audio.

### Scoring

Each detection layer contributes a score. Segments exceeding a combined threshold are actioned according to the `hallucination_detection.action` configuration value: `remove`, `flag` (mark in output), or `log` (record in snapshot only). Detection results are always included in the raw output snapshot for debugging.

### Known Limitations

- **Language-switching hallucinations** — Whisper may switch languages mid-transcription on accented or multilingual audio. These can evade all detectors. Future mitigation: per-segment language identification.
- **Phantom proper nouns** — Whisper fabricates specific names, URLs, or phone numbers that were never spoken. Difficult to detect without a reference transcript.
- **Timestamp drift** — overlapping or backwards-jumping segment timestamps can corrupt downstream analysis. Detect by checking for non-monotonic timestamps.

## Filtering

The `filters.py` module controls which files are accepted for processing. Filters are applied before transcription; rejected files are logged and recorded with `status: skipped` in the database.

### Supported File Extensions

Audio formats accepted: `.mp3`, `.wav`, `.m4a`, `.flac`, `.ogg`, `.wma`, `.aac`, `.webm`.

### Filter Rules

| Filter              | Behavior                                                                                          |
| ------------------- | ------------------------------------------------------------------------------------------------- |
| File extension      | Only files with supported extensions are processed; others are skipped                            |
| File size           | Files exceeding `max_file_size_mb` (default: 500 MB) are skipped                                  |
| Duplicate detection | Files whose `file_hash` matches an existing `success` record are skipped unless `--force` is used |
| Empty files         | Zero-byte files are skipped                                                                       |

Filter functions are pure — they accept file metadata and return a pass/fail result with a reason string.

## Command List

Running `audio` with no arguments shows help. Standard transcription is the default operation — no subcommand required.

| Subcommand     | Description                                     |
| -------------- | ----------------------------------------------- |
| `audio config` | Validate and display current YAML configuration |
| `audio init`   | Create config file and directory structure      |

| Flag                                                            | Description                                                  |
| --------------------------------------------------------------- | ------------------------------------------------------------ |
| `--input PATH`                                                  | Input file or directory (default: `input/`)                  |
| `--output PATH`                                                 | Output directory (default: `data/audio/export/`)             |
| `--config PATH`                                                 | YAML configuration file                                      |
| `--engine [whisper\|mlx]`                                       | Transcription engine (auto-selects MLX on Apple Silicon)     |
| `--model [tiny\|base\|small\|medium\|large-v3\|large-v3-turbo]` | Whisper model size (default: `large-v3-turbo`)               |
| `--language TEXT`                                               | Force language code (e.g., `en`, `fr`); default: auto-detect |
| `--output-mode [paragraph\|segment\|timestamp]`                 | Transcript format (default: `paragraph`)                     |
| `--diarize`                                                     | Enable speaker identification (requires HuggingFace token)   |
| `--pause-threshold FLOAT`                                       | Pause duration (seconds) that triggers a paragraph break     |
| `--remove-fillers`                                              | Strip filler words (um, uh, like, you know)                  |
| `--nuke`                                                        | Delete input files after successful processing               |
| `--dry-run`                                                     | Preview without processing                                   |
| `--verbose`, `-v`                                               | Detailed logging                                             |
| `--force`                                                       | Clear state and reprocess                                    |
| `--save-config PATH`                                            | Generate example config and exit                             |
| `--version`                                                     | Show version and exit                                        |

## File & Output Map

```
files/tools/audio/
├── 260322-requirements.md       # This document
└── CHANGELOG.md                 # Release history

src/config/
└── audio-configuration.yaml    # Tool configuration

src/deep_thought/audio/
├── __init__.py
├── cli.py                       # CLI entry point
├── config.py                    # YAML config loader
├── models.py                    # Local dataclasses for processing state
├── processor.py                 # Orchestrates engine, diarization, output
├── db/
│   ├── __init__.py
│   ├── schema.py                # Table creation and migration runner
│   ├── queries.py               # All SQL operations
│   └── migrations/
│       └── 001_init_schema.sql
├── filters.py                   # File size, extension, duration filtering
├── hallucination.py             # Multi-layer hallucination detection and scoring
├── output.py                    # Markdown + YAML frontmatter generation
├── llms.py                      # .llms.txt / .llms-full.txt generation
├── engines/
│   ├── whisper_engine.py        # Standard Whisper transcription
│   └── mlx_whisper_engine.py    # MLX-Whisper with chunking + hallucination detection
└── diarization.py               # PyAnnote speaker identification

data/audio/
├── audio.db                     # SQLite state database
├── snapshots/                   # Raw engine output per run
│   └── YYYY-MM-DDTHHMMSS.json
└── export/                      # Generated markdown files
```

## Configuration

Configuration is stored in `src/config/audio-configuration.yaml`. All values below are required unless marked optional.

```yaml
# Engine
engine: "mlx" # 'mlx' (default), 'whisper', or 'auto' (selects MLX on Apple Silicon)
model: "large-v3-turbo" # See Pre-Build Tasks for model comparison; 'tiny', 'base', 'small', 'medium', 'large-v3', 'large-v3-turbo'
language: null # null = auto-detect, or language code e.g. 'en'

# Output mode
output_mode: "paragraph" # 'paragraph', 'segment', or 'timestamp'
pause_threshold: 1.5 # Seconds of silence to trigger paragraph break

# Diarization
diarize: false
hf_token_env: "HF_TOKEN" # Env var holding HuggingFace token

# Filler words
remove_fillers: false

# Output
output_dir: "data/audio/export/"
generate_llms_files: false # Set true to generate .llms.txt / .llms-full.txt per file

# Limits
max_file_size_mb: 500
chunk_duration_minutes: 5 # MLX only: split audio longer than this

# Hallucination detection (multi-signal scoring system)
hallucination_detection:
  repetition_threshold: 3 # Max allowed phrase repetitions in a window
  compression_ratio_threshold: 2.4 # Flag segments above this ratio
  confidence_floor: -1.0 # Average log-probability floor per segment
  no_speech_prob_threshold: 0.6 # Flag segments above this no-speech probability
  duration_chars_per_sec_max: 25 # Flag segments exceeding this text density
  duration_chars_per_sec_min: 2 # Flag segments below this (for segments > 0.5s)
  use_vad: true # Use Voice Activity Detector for silence detection
  blocklist_enabled: true # Check against known hallucination phrases
  score_threshold: 2 # Number of layers that must flag before action is taken
  action: "remove" # 'remove', 'flag', or 'log'
```

## Data Format

### Markdown Output

```
data/audio/export/{filename}/
├── {filename}.md                # Transcript with YAML frontmatter
└── llm/
    ├── {filename}.llms.txt      # Navigation index
    └── {filename}.llms-full.txt # Full content for LLM consumption
```

### Frontmatter Schema

```markdown
---
tool: audio
source_file: interview.mp3
engine: mlx
model: base
language: en
duration_seconds: 1842.5
speaker_count: 2
output_mode: paragraph
processed_date: 2026-03-18T10:00:00Z
---
```

### Output Mode Examples

**paragraph** — continuous prose grouped by speaker and pause:

```
John spoke about the project timeline and the challenges they faced during Q1.
The team struggled with resource allocation but ultimately delivered on time.

Sarah responded with concerns about the budget implications for Q2.
```

**segment** — one segment per line with optional speaker label:

```
[Speaker 1] John spoke about the project timeline.
[Speaker 2] Sarah responded with concerns about the budget.
```

**timestamp** — timestamped segments:

```
[00:00] John spoke about the project timeline.
[00:08] Sarah responded with concerns about the budget.
```

### SQLite Schema

One table tracks processing state. Uses `file_path` (the local file path) as the primary key rather than an API-issued ID, since this tool processes local files rather than syncing with an external service. All records include `created_at` and `updated_at` timestamps. Schema version is tracked in the `key_value` table to support forward-only migrations.

## Error Handling

- `FileNotFoundError` — missing config file or input file/directory
- `OSError` — missing environment variables or invalid `DEEP_THOUGHT_DATA_DIR` path
- `ValueError` — invalid configuration content
- Whisper/MLX-Whisper transcription errors, PyAnnote diarization failures, FFmpeg chunking errors — caught per-file
- Top-level `try/except` in CLI entry point catches all above and prints descriptive messages
- Per-file errors do not halt batch processing; failed files are recorded with `status: error` in the database
- Exit codes: `0` all files succeeded, `1` fatal error, `2` partial failure (some files errored)

## Testing

- Use in-memory SQLite for database tests
- Mock Whisper, MLX-Whisper engines, PyAnnote, FFmpeg with `MagicMock`
- Provide fixture sample audio files for processing tests
- Organize tests in classes by feature area
- Write docstrings on every test method
- Test markers: `slow`, `integration`, `error_handling`
- Test directory: `tests/audio/` with `conftest.py` for shared fixtures
- Fixture data files stored in `tests/audio/fixtures/`
