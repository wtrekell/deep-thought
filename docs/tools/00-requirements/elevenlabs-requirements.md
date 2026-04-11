# Product Brief — ElevenLabs Tool

## Name and Purpose

**ElevenLabs Tool** — text-to-speech synthesis and audio transcription via the ElevenLabs API. Three operations: `tts` converts markdown files to MP3, `transcribe` converts audio files to markdown via Scribe v2, and `voices` lists available voices.

**Tool type:** Generative (TTS generates audio output; transcribe is a converter; no embeddings).

## Operations

1. **CLI Command** — `elevenlabs` (entry point with subcommands)
2. **TTS** — Markdown → MP3 audio; long texts are chunked and stitched into a single file
3. **Transcribe** — Audio → markdown with optional speaker diarization and word-level timestamps
4. **Voices** — List available ElevenLabs voices with ID and category
5. Five subcommands under a single entry point: `tts`, `transcribe`, `voices`, `config`, `init`

## Requirements

1. Python 3.12 using `uv` as the package manager.
2. **httpx** for HTTP requests to the ElevenLabs API.
3. **pydub** (`pydub`) for stitching chunked MP3 audio parts.
4. **FFmpeg** (system dependency) required by pydub for audio concatenation.
5. SQLite for local state tracking (WAL mode, foreign keys enabled).
6. `ELEVENLABS_API_KEY` stored in `.env` or system environment.
7. A changelog is maintained in `files/tools/elevenlabs/CHANGELOG.md`.

## Data Storage

### State Database

- Database file: `data/elevenlabs/elevenlabs.db`
- Supports `DEEP_THOUGHT_DATA_DIR` env var to redirect the data root at runtime
- WAL mode and foreign keys enabled
- Table: `processed_files` — tracks TTS and transcription operations (see Data Models)
- Table: `key_value` — stores schema version and tool metadata
- Migrations applied sequentially from `db/migrations/` by numeric prefix

## Data Models

### ProcessedFileLocal

Represents a file that has been processed by the tool (TTS or transcription).

| Field | Type | Description |
| --- | --- | --- |
| `file_path` | `str` | Absolute path to the source file (primary key) |
| `file_hash` | `str` | Hash of the source file contents |
| `operation` | `str` | `tts` or `transcribe` |
| `voice_id` | `str` | Voice ID used (TTS only) |
| `output_path` | `str` | Path to the generated output file |
| `status` | `str` | Processing status |
| `created_at` | `str` | ISO 8601 timestamp of record creation |
| `updated_at` | `str` | ISO 8601 timestamp of last update |

`to_dict()` returns a plain `dict[str, Any]` suitable for JSON serialization.

## Command List

| Subcommand | Description |
| --- | --- |
| `elevenlabs tts` | Convert markdown file(s) to MP3 audio |
| `elevenlabs transcribe` | Transcribe audio file(s) to markdown |
| `elevenlabs voices` | List available ElevenLabs voices |
| `elevenlabs config` | Validate and display current YAML configuration |
| `elevenlabs init` | Create config file and directory structure |

### tts

| Flag | Description |
| --- | --- |
| `--input PATH` | Markdown file or directory (default: `input/`) |
| `--voice TEXT` | Voice ID override |
| `--output PATH` | Output directory (default: `data/elevenlabs/export/tts/`) |
| `--config PATH` | YAML configuration file |
| `--force` | Re-generate even if in state DB |
| `--dry-run` | Preview without calling API |
| `--verbose`, `-v` | Detailed logging |
| `--no-progress` | Disable progress spinner |
| `--save-config PATH` | Generate example config and exit |
| `--version` | Show version and exit |

### transcribe

| Flag | Description |
| --- | --- |
| `--input PATH` | Audio file or directory (default: `input/`) |
| `--diarize` | Enable speaker diarization |
| `--no-timestamps` | Disable word-level timestamps |
| `--output PATH` | Output directory (default: `data/elevenlabs/export/transcribe/`) |
| `--config PATH` | YAML configuration file |
| `--force` | Re-transcribe even if in state DB |
| `--dry-run` | Preview without calling API |
| `--verbose`, `-v` | Detailed logging |
| `--no-progress` | Disable progress spinner |

### voices

| Flag | Description |
| --- | --- |
| `--config PATH` | Config file (for API key) |

## File & Output Map

```
files/tools/elevenlabs/
├── requirements.md              # This document
└── CHANGELOG.md                 # Release history

src/deep_thought/elevenlabs/
├── __init__.py
├── cli.py                       # CLI entry point (tts, transcribe, voices subcommands)
├── config.py                    # YAML config loader
├── models.py                    # Local dataclasses for processing state
├── db/                          # SQLite database layer
│   ├── __init__.py
│   ├── schema.py                # Table definitions and setup
│   ├── queries.py               # Read/write query functions
│   └── migrations/
│       └── 001_init_schema.sql   # Initial schema migration
├── output.py                    # Markdown + YAML frontmatter generation for transcriptions
├── tts.py                       # TTS logic: markdown stripping, chunking, API calls, stitching
└── transcriber.py               # Scribe v2 API wrapper

data/elevenlabs/
├── elevenlabs.db                # SQLite state database
└── export/                      # Generated MP3s and transcription markdown files

src/config/
└── elevenlabs-configuration.yaml  # Tool configuration
```

## Configuration

Configuration is stored in `src/config/elevenlabs-configuration.yaml`. All values below are required unless marked optional.

```yaml
# API
api_key_env: "ELEVENLABS_API_KEY"
timeout: 120                     # HTTP timeout in seconds

# TTS defaults
voice_id: 'JBFqnCBsd6RMkjVDRZzb'   # Default: George
tts_model: 'eleven_multilingual_v2'
output_format: 'mp3_44100_128'      # See output format options below
chunk_size_chars: 9500               # Split texts longer than this at sentence boundaries

# Transcription defaults
transcribe_model: 'scribe_v2'
diarize: false
word_timestamps: true

# Output
output_dir: 'data/elevenlabs/export/'
```

### TTS Output Format Options

| Format | Description |
| --- | --- |
| `mp3_22050_32` | MP3, 22.05 kHz, 32 kbps |
| `mp3_44100_32` | MP3, 44.1 kHz, 32 kbps |
| `mp3_44100_64` | MP3, 44.1 kHz, 64 kbps |
| `mp3_44100_96` | MP3, 44.1 kHz, 96 kbps |
| `mp3_44100_128` | MP3, 44.1 kHz, 128 kbps (default) |
| `mp3_44100_192` | MP3, 44.1 kHz, 192 kbps (Creator+ tier only) |
| `pcm_16000` | PCM, 16 kHz |
| `pcm_22050` | PCM, 22.05 kHz |
| `pcm_24000` | PCM, 24 kHz |
| `pcm_44100` | PCM, 44.1 kHz |
| `ulaw_8000` | μ-law, 8 kHz |

## Data Format

### TTS Output

```
data/elevenlabs/export/tts/
└── {source_filename}.mp3        # Synthesized audio (stitched from chunks if needed)
```

For chunked files, intermediate parts (`{filename}-part-01.mp3`, etc.) are automatically deleted after stitching.

### Transcription Output

```
data/elevenlabs/export/transcribe/
└── {audio_filename}.md          # Transcript with YAML frontmatter
```

### Transcription Frontmatter Schema

```markdown
---
tool: elevenlabs
operation: transcribe
source_file: interview.mp3
model: scribe_v2
diarized: true
word_timestamps: true
processed_date: 2026-03-18T10:00:00Z
---
```

### Transcription Content

Without diarization:
```markdown
The meeting started with a discussion of the quarterly results. Revenue was up
fifteen percent compared to the prior year...
```

With diarization:
```markdown
**Speaker 1:** The meeting started with a discussion of the quarterly results.

**Speaker 2:** Revenue was up fifteen percent compared to the prior year.
```

### TTS Preprocessing

Before synthesis, the tool strips from the markdown source:
- YAML frontmatter blocks (`---`)
- Fenced code blocks (` ``` `)
- Inline code (`` ` ``)
- Image references (`![alt](url)`)
- Markdown link syntax (replaces `[text](url)` with `text`)
- ATX heading markers (`#`, `##`, etc. → kept as plain text)

## Error Handling

- `ElevenLabs API errors` (auth, rate limits, voice not found) — caught per-file; logs the error with the source filename and continues processing remaining files in a batch.
- `pydub/FFmpeg stitching errors` — caught per-file; intermediate audio parts are cleaned up before the error is reported.
- `Scribe v2 transcription errors` — caught per-file; logs the error with the source filename and continues processing remaining files in a batch.
- Top-level `try/except` in CLI entry point catches all above and prints descriptive messages.
- Exit codes: `0` all items succeeded, `1` fatal error, `2` partial failure (some items errored)

## Testing

- Mock targets: **httpx** (API calls), **pydub** (audio stitching) — mock at the transport layer to avoid real network calls and FFmpeg dependency in unit tests.
- Test fixtures: sample markdown files (TTS input), sample audio files (transcription input).
- Use in-memory SQLite for all database tests; provide populated fixtures with seed `processed_files` rows.
- Test classes organized by feature area: TTS chunking, transcription output, state DB reads/writes, config validation.
- Mark slow or API-dependent tests with `@pytest.mark.slow` and `@pytest.mark.integration`.
- Mark error path tests with `@pytest.mark.error_handling`.
- Test directory: `tests/elevenlabs/` with `conftest.py` for shared fixtures
- Fixture data files stored in `tests/elevenlabs/fixtures/`
