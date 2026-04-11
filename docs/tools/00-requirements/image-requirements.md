# Product Brief — Image Tool

## Name and Purpose

**Image Tool** — extracts text and AI-generated descriptions from image files using Tesseract OCR and Google Gemini 2.0 Flash. Includes image preprocessing, per-request rate limiting, and cumulative cost tracking.

## Processing Modes

1. **CLI Command** — `image` (entry point)
2. **OCR Only** — Tesseract text extraction (no API cost)
3. **AI Description** — Gemini 2.0 Flash visual description
4. **Combined** — OCR text + AI description in one pass

## Requirements

1. Python 3.12 using `uv` as the package manager.
2. **Tesseract OCR** (`pytesseract` + system `tesseract`) for text extraction.
3. **Pillow** (`Pillow`) for image preprocessing (grayscale, contrast, sharpening).
4. **Google Generative AI** (`google-genai>=1.0.0`) for Gemini descriptions.
5. SQLite for local state tracking (WAL mode, foreign keys enabled).
6. `GEMINI_API_KEY` stored in `.env` or system environment.
7. A changelog is maintained in `files/tools/image/CHANGELOG.md`.

## Data Storage

### State Database

Located at `data/image/image.db` by default; respects the `DEEP_THOUGHT_DATA_DIR` env var to redirect the data root at runtime.

- Table: `processed_files` — columns: `file_path TEXT PRIMARY KEY`, `file_hash TEXT`, `ocr_used INT`, `gemini_used INT`, `gemini_cost_usd REAL`, `output_path TEXT`, `status TEXT`, `created_at TEXT`, `updated_at TEXT`
- Cumulative cost tracked across runs for budget monitoring
- Schema version tracked in a `key_value` table
- Migrations stored in `db/migrations/` with numeric prefixes

## Data Models

### ProcessedFileLocal

| Field | Type | Description |
| --- | --- | --- |
| `file_path` | `str` | Absolute path to the source image file (primary key) |
| `file_hash` | `str` | SHA-256 hash of the file for change detection |
| `ocr_used` | `int` | Whether Tesseract OCR was run (1 = yes, 0 = no) |
| `gemini_used` | `int` | Whether Gemini description was requested (1 = yes, 0 = no) |
| `gemini_cost_usd` | `float` | API cost for this file in USD |
| `output_path` | `str` | Path to the generated markdown file |
| `status` | `str` | Processing status (`pending`, `done`, `error`) |
| `created_at` | `str` | ISO 8601 timestamp — record creation |
| `updated_at` | `str` | ISO 8601 timestamp — last modification |

Methods: `to_dict()` for database insertion.

## Command List

Running `image` with no arguments shows help. Standard processing is the default operation — no subcommand required.

| Subcommand | Description |
| --- | --- |
| `image config` | Validate and display current YAML configuration |
| `image init` | Create config file and directory structure |

| Flag | Description |
| --- | --- |
| `--input PATH` | Input file or directory (default: `input/`) |
| `--output PATH` | Output directory (default: `data/image/export/`) |
| `--config PATH` | YAML configuration file |
| `--ocr` | Enable Tesseract OCR (default: true) |
| `--no-ocr` | Disable OCR |
| `--describe` | Enable Gemini AI description (default: true) |
| `--no-describe` | Disable AI description |
| `--rate-limit INT` | Max Gemini requests per minute (default: 5 for free tier) |
| `--nuke` | Delete input files after successful processing |
| `--dry-run` | Preview without processing; shows cost estimate |
| `--verbose`, `-v` | Detailed logging with per-file cost |
| `--force` | Clear state and reprocess |
| `--save-config PATH` | Generate example config and exit |
| `--version` | Show version and exit |

**Supported formats:** `.png`, `.jpg`, `.jpeg`, `.gif`, `.bmp`, `.tiff`, `.webp`

## File & Output Map

```
files/tools/image/
├── requirements.md              # This document
└── CHANGELOG.md                 # Release history

src/config/
└── image-configuration.yaml     # Tool configuration

src/deep_thought/image/
├── __init__.py
├── cli.py                       # CLI entry point
├── config.py                    # YAML config loader
├── models.py                    # Local dataclasses for processing state
├── processor.py                 # Orchestrates OCR, description, output
├── db/
│   ├── __init__.py
│   ├── schema.py                # Table creation and migration runner
│   ├── queries.py               # All SQL operations
│   └── migrations/
│       └── 001_init_schema.sql
├── filters.py                   # File size, extension, exclude-pattern filtering
├── output.py                    # Markdown + YAML frontmatter generation
├── llms.py                      # .llms.txt / .llms-full.txt generation
├── ocr.py                       # Tesseract OCR with image preprocessing
└── describer.py                 # Gemini 2.0 Flash visual description

data/image/
├── image.db                     # SQLite state database
└── export/                      # Generated markdown files
```

## Configuration

Configuration is stored in `src/config/image-configuration.yaml`. All values below are required unless marked optional.

```yaml
# OCR
ocr_enabled: true

# Gemini AI
describe_enabled: true
gemini_api_key_env: "GEMINI_API_KEY"
gemini_model: 'gemini-2.0-flash'
rate_limit_rpm: 5                # Free tier: 5/min; paid: higher

# Image preprocessing
preprocess: true                 # Grayscale + 2x contrast + sharpening before OCR

# Output
output_dir: 'data/image/export/'
generate_llms_files: true

# Limits
max_file_size_mb: 50
budget_limit_usd: null           # null = no limit; set to cap spend
```

## Data Format

### Markdown Output

```
data/image/export/{filename}/
├── {filename}.md                # Description + OCR text with YAML frontmatter
└── llm/
    ├── {filename}.llms.txt      # Navigation index
    └── {filename}.llms-full.txt # Full content for LLM consumption
```

### Frontmatter Schema

```markdown
---
tool: image
source_file: diagram.png
width_px: 1920
height_px: 1080
ocr_used: true
describe_used: true
gemini_cost_usd: 0.0003
processed_date: 2026-03-18T10:00:00Z
---
```

### Content Structure

```markdown
## AI Description

A flowchart showing three decision nodes connected by labeled arrows...

## OCR Text

STEP 1: INPUT DATA
↓
STEP 2: VALIDATE
```

### Cost Reference

- Gemini 2.0 Flash: billed per token at published API rates
- Dry-run mode estimates cost before processing
- Cumulative spend is logged per run and stored in state

## Error Handling

- `Tesseract OCR failures` — caught per-file; OCR result omitted; processing continues with remaining files
- `Gemini API errors` (rate limits, auth) — caught per-file; description omitted; processing continues with remaining files
- `Pillow image loading errors` — caught per-file; file marked with `status = error`; processing continues with remaining files
- `FileNotFoundError` — raised for missing config files
- `OSError` — raised for missing `GEMINI_API_KEY` environment variable
- `ValueError` — raised for invalid configuration content
- Top-level CLI entry point wraps execution in try/except and returns exit code 1 on failure
- Exit codes: `0` all files succeeded, `1` fatal error, `2` partial failure (some files errored)

## Testing

- Database tests use in-memory SQLite
- Mock targets: pytesseract, google-generativeai, Pillow
- Test fixtures: sample image files (PNG, JPG with text)
- Tests organized in classes by feature area (CLI, processor, OCR, describer, database, filters)
- All test methods include docstrings
- Test markers: `slow`, `integration`, `error_handling`
- Test directory: `tests/image/` with `conftest.py` for shared fixtures
- Fixture data files stored in `tests/image/fixtures/`
