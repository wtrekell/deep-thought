# Product Brief — YouTube Tool

## Name and Purpose

**YouTube Tool** — collects metadata and transcripts from YouTube videos, channels, and playlists. No video downloads — only text content (title, description, transcript) and metadata are saved. Rule-based configuration supports multiple targets with independent filtering.

## Operations

1. **CLI Command** — `youtube` (entry point)
2. **Collect** — Fetch metadata and transcripts for all videos matching rules (default operation)

## Requirements

1. Python 3.12 using `uv` as the package manager.
2. **yt-dlp** (`yt-dlp`) for metadata extraction and transcript retrieval.
3. SQLite for local state tracking (WAL mode, foreign keys enabled).
4. No API keys required — yt-dlp handles YouTube access without an API key.
5. A changelog is maintained in `files/tools/youtube/CHANGELOG.md`.

## Data Storage

### State Database

Located at `data/youtube/youtube.db` by default; respects the `DEEP_THOUGHT_DATA_DIR` env var to redirect the data root at runtime.

- Table: `collected_videos` — columns: `state_key TEXT PRIMARY KEY`, `video_id TEXT`, `channel_id TEXT`, `rule_name TEXT`, `output_path TEXT`, `status TEXT`, `created_at TEXT`, `updated_at TEXT`, `synced_at TEXT`
- **State key:** `{video_id}:{rule_name}`
- Schema version tracked in a `key_value` table
- Migrations stored in `db/migrations/` with numeric prefixes

## Data Models

### `CollectedVideoLocal`

Local representation of a collected YouTube video stored in SQLite:

| Field | Type | Description |
| --- | --- | --- |
| `state_key` | `str` | Composite primary key (`{video_id}:{rule_name}`) |
| `video_id` | `str` | YouTube video ID |
| `channel_id` | `str` | YouTube channel ID |
| `rule_name` | `str` | Name of the matching rule |
| `output_path` | `str` | Path to written markdown file |
| `status` | `str` | `ok`, `error`, `skipped`, etc. |
| `created_at` | `str` | ISO timestamp of first insert |
| `updated_at` | `str` | ISO timestamp of last update |
| `synced_at` | `str` | ISO timestamp of last sync |

Methods: `to_dict()` for database insertion; `from_sdk()` to construct from a yt-dlp `info_dict` object.

## Command List

Running `youtube` with no arguments shows help. Collect is the default operation — no subcommand required.

| Subcommand | Description |
| --- | --- |
| `youtube config` | Validate and display current YAML configuration |
| `youtube init` | Create config file and directory structure |

| Flag | Description |
| --- | --- |
| `--config PATH` | YAML configuration file (default: `src/config/youtube-configuration.yaml`) |
| `--output PATH` | Output directory override |
| `--dry-run` | Preview without fetching |
| `--verbose`, `-v` | Detailed logging |
| `--force` | Clear state and reprocess all |
| `--save-config PATH` | Generate example config and exit |
| `--version` | Show version and exit |

## File & Output Map

```
files/tools/youtube/
├── requirements.md              # This document
└── CHANGELOG.md                 # Release history

src/deep_thought/youtube/
├── __init__.py
├── cli.py                       # CLI entry point
├── config.py                    # YAML config loader and rule validation
├── models.py                    # Local dataclasses for collection state
├── processor.py                 # Rule engine, metadata fetching, output orchestration
├── db/
│   ├── __init__.py
│   ├── schema.py                # Table creation and migration runner
│   ├── queries.py               # All SQL operations
│   └── migrations/
│       └── 001_init_schema.sql
├── filters.py                   # Age, view count, keyword filtering
├── output.py                    # Markdown + YAML frontmatter generation
├── llms.py                      # .llms.txt / .llms-full.txt generation
└── client.py                    # yt-dlp wrapper for metadata and transcript extraction

data/youtube/
├── youtube.db                   # SQLite state database
└── export/                      # Generated markdown files

src/config/
└── youtube-configuration.yaml   # Tool configuration and rules
```

## Configuration

Configuration is stored in `src/config/youtube-configuration.yaml`. All values below are required unless marked optional.

```yaml
# Output
output_dir: 'data/youtube/export/'
generate_llms_files: true

rules:
  - name: 'ml_channel'
    targets:
      - type: 'channel'
        url: 'https://www.youtube.com/@channelname'
      - type: 'playlist'
        url: 'https://www.youtube.com/playlist?list=PLxxxxxx'
      - type: 'video'
        url: 'https://www.youtube.com/watch?v=xxxxxx'
    max_videos: 50
    max_age_days: 90
    min_views: 1000
    include_keywords: ['machine learning', 'neural network']
    exclude_keywords: ['sponsored', 'ad']
    prefer_manual_transcript: true   # Manual subtitles preferred; auto-generated fallback
    strip_timestamps: true           # Remove [HH:MM:SS] tags from transcript text
```

### Target Types

| Type | URL Format |
| --- | --- |
| `channel` | `https://www.youtube.com/@handle` or `/channel/UCxxx` |
| `playlist` | `https://www.youtube.com/playlist?list=PLxxx` |
| `video` | `https://www.youtube.com/watch?v=xxxx` |

Multiple target types can be mixed in one rule.

## Data Format

### Markdown Output

```
data/youtube/export/{rule_name}/
├── {date}_{video_id}_{title_slug}.md
└── llm/
    ├── {date}_{video_id}_{title_slug}.llms.txt
    └── {date}_{video_id}_{title_slug}.llms-full.txt
```

### Frontmatter Schema

```markdown
---
tool: youtube
state_key: dQw4w9WgXcQ:ml_channel
video_id: dQw4w9WgXcQ
rule: ml_channel
title: "Introduction to Transformers"
channel: "ML Explained"
channel_id: UCxxxxxx
upload_date: "2026-02-10"
duration_seconds: 2418
view_count: 124500
like_count: 3820
tags: [machine learning, transformers, attention]
categories: [Education]
thumbnail_url: https://i.ytimg.com/vi/dQw4w9WgXcQ/maxresdefault.jpg
transcript_type: manual
processed_date: 2026-03-18T10:00:00Z
---
```

### Content Structure

```markdown
# Introduction to Transformers

**Channel:** ML Explained | **Published:** Feb 10, 2026 | **Views:** 124,500

## Description

Full video description here...

## Transcript

The transformer architecture was introduced in the paper "Attention is All You Need"
by Vaswani et al. in 2017. The key insight is the self-attention mechanism which...
```

## Error Handling

Errors are caught per-video and logged without halting the overall run:

- `yt-dlp` extraction errors — geo-blocked, private, or deleted videos that cannot be fetched
- Transcript unavailable errors — videos with no manual or auto-generated subtitles

Failed items are recorded with `status: error` in the state database and reported in the run summary.

- Top-level `try/except` in CLI entry point catches all above and prints descriptive messages.
- Exit codes: `0` all items succeeded, `1` fatal error, `2` partial failure (some items errored)

## Testing

- **Mock targets:** `yt-dlp` (patch the `YoutubeDL` class and its `extract_info` method)
- **Test fixtures:** mock yt-dlp `info_dict` objects with realistic field values (video ID, title, description, transcript segments)
- **Markers:** `slow` for full channel crawls, `integration` for live yt-dlp calls, `error_handling` for fault injection
- Unit tests cover: filter logic (age, view count, keywords), state key generation, frontmatter serialization, transcript text cleaning
- Integration tests (skipped by default) require network access and a valid yt-dlp installation
- Test directory: `tests/youtube/` with `conftest.py` for shared fixtures
- Fixture data files stored in `tests/youtube/fixtures/`

## Embeddings Integration

Video transcripts collected via YouTube are written to the embedding store for semantic search.

- **When:** At collection time, immediately after markdown write
- **Content:** Video title, description, and transcript text
- **Payload fields:**
  - `source_tool: "youtube"`
  - `source_type: "video_transcript"`
  - `rule_name` — which config rule collected this video
  - `collected_date` — ISO timestamp
  - `video_id`, `channel_id` — for filtered queries
  - `output_path` — path to the markdown file on disk

**Error handling:** Embedding failure does not fail the collection run. The video is recorded as collected in the state DB; if embedding fails, it can be re-embedded in a repair run.
