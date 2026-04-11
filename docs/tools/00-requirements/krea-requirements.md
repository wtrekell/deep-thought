# Product Brief — Krea Tool

## Name and Purpose

**Krea Tool** — generates images using the Krea API (Flux model family). Supports single prompts, batch generation from a text file, style transfer via reference images, LoRA style models, and preset aspect ratios. Each image is paired with a companion markdown file containing full generation metadata.

**Tool type:** Generative (generates output, no write-back, no embeddings).

## Operations

1. **CLI Command** — `krea` (entry point)
2. **Single Generation** — One prompt → one image
3. **Batch Generation** — Text file of prompts → one image per prompt
4. **Style Transfer** — Reference image URL guides generation style

## Requirements

1. Python 3.12 using `uv` as the package manager.
2. **httpx** for HTTP requests to the Krea API.
3. SQLite for local state tracking (skip already-generated prompts) (WAL mode, foreign keys enabled).
4. `KREA_API_KEY` stored in `.env` or system environment.
5. A changelog is maintained in `files/tools/krea/CHANGELOG.md`.

## Data Storage

### State Database

Located at `data/krea/krea.db` by default; respects the `DEEP_THOUGHT_DATA_DIR` env var to redirect the data root at runtime.

- Table: `generated_images` — columns: `state_key TEXT PRIMARY KEY`, `prompt_hash TEXT`, `model TEXT`, `job_id TEXT`, `output_path TEXT`, `status TEXT`, `created_at TEXT`, `updated_at TEXT`
- **State key:** SHA-256 hash of prompt + model + key generation parameters
- On `--force`, state is cleared so the same prompt can be re-generated
- Schema version tracked in a `key_value` table
- Migrations stored in `db/migrations/` with numeric prefixes

## Data Models

### `GeneratedImageLocal`

Local representation of a generated image stored in SQLite:

| Field | Type | Description |
| --- | --- | --- |
| `state_key` | `str` | SHA-256 hash of prompt + model + key parameters |
| `prompt_hash` | `str` | SHA-256 of the prompt text alone |
| `model` | `str` | Flux model path used for generation |
| `job_id` | `str` | Krea API job identifier |
| `output_path` | `str` | Path to the generated image file |
| `status` | `str` | `ok`, `error`, `pending`, etc. |
| `created_at` | `str` | ISO timestamp of first insert |
| `updated_at` | `str` | ISO timestamp of last update |

`to_dict()` returns a plain `dict[str, Any]` suitable for JSON serialization and frontmatter embedding.

## Command List

Running `krea` with no arguments shows help. Single generation is the default operation — no subcommand required.

| Subcommand | Description |
| --- | --- |
| `krea config` | Validate and display current YAML configuration |
| `krea init` | Create config file and directory structure |

| Flag | Description |
| --- | --- |
| `[PROMPT]` | Prompt text (positional argument; mutually exclusive with `--prompts-file`) |
| `--prompts-file PATH` | Text file of prompts, one per line (`#` = comment) |
| `--model TEXT` | Flux model path (default: `bfl/flux-1-dev`) |
| `--aspect-ratio [square\|landscape\|portrait\|widescreen\|ultrawide\|tall]` | Preset ratio (overrides `--width`/`--height`) |
| `--width INT` | Image width in pixels (512–2368, divisible by 8; default: 1024) |
| `--height INT` | Image height in pixels (512–2368, divisible by 8; default: 1024) |
| `--steps INT` | Inference steps 1–100 (recommended: 28–40; default: 25) |
| `--guidance FLOAT` | CFG guidance scale 0–24 (default: 3.0) |
| `--seed TEXT` | Fixed seed for reproducibility |
| `--image-url TEXT` | Reference image URL for style transfer |
| `--relaxed` | Use relaxed mode access flag |
| `--output PATH` | Output directory (default: `data/krea/export/`) |
| `--config PATH` | YAML configuration file |
| `--force` | Re-generate even if in state DB |
| `--dry-run` | Preview without calling API |
| `--verbose`, `-v` | Detailed logging |
| `--no-progress` | Disable spinner |
| `--save-config PATH` | Generate example config and exit |
| `--version` | Show version and exit |

### Available Models

| Model | Description |
| --- | --- |
| `bfl/flux-1-dev` | Default development model |
| `bfl/flux-2-flex` | Flexible generation |
| `bfl/flux-2-klein` | Lightweight model |
| `bfl/flux-2-max` | Maximum quality |
| `bfl/flux-2-pro` | Professional quality |
| `bfl/flux-kontext` | Context-aware generation |
| `bfl/flux-kontext-pro` | Professional context-aware |

### Aspect Ratio Presets

| Preset | Dimensions |
| --- | --- |
| `square` | 1024 × 1024 |
| `landscape` | 1536 × 1024 |
| `portrait` | 1024 × 1536 |
| `widescreen` | 1920 × 1088 |
| `ultrawide` | 2048 × 1088 |
| `tall` | 1024 × 1792 |

## File & Output Map

```
files/tools/krea/
├── requirements.md              # This document
└── CHANGELOG.md                 # Release history

src/deep_thought/krea/
├── __init__.py
├── cli.py                       # CLI entry point
├── config.py                    # YAML config loader
├── models.py                    # Local dataclasses for generation state
├── generator.py                 # API client, job submission, polling
├── db/
│   ├── __init__.py
│   ├── schema.py                # Table creation and migration runner
│   ├── queries.py               # All SQL operations
│   └── migrations/
│       └── 001_init_schema.sql
└── output.py                    # Companion markdown + YAML frontmatter

data/krea/
├── krea.db                      # SQLite state database
└── export/                      # Generated images and companion files

src/config/
└── krea-configuration.yaml      # Tool configuration
```

## Configuration

Configuration is stored in `src/config/krea-configuration.yaml`. All values below are required unless marked optional.

```yaml
# API
api_key_env: "KREA_API_KEY"
timeout: 120                     # HTTP timeout in seconds
poll_interval: 2.0               # Seconds between job-status polls
max_poll_attempts: 150           # 150 × 2s = 5 minutes max wait

# Generation defaults
model: 'bfl/flux-1-dev'
width: 1024
height: 1024
aspect_ratio: null               # Overrides width/height if set
steps: 25
guidance_scale_flux: 3.0
seed: null                       # null = random

# Style transfer
image_url: null                  # Single reference image URL
style_images:                    # Multiple style refs with strength
  - url: 'https://example.com/style.jpg'
    strength: 0.8

# LoRA styles
styles:
  - model_id: 'style-model-id'
    strength: 0.7                # -2.0 to 2.0

# Output
output_dir: 'data/krea/export/'
```

## Data Format

### Output Structure

Each generated image gets a timestamped directory:

```
data/krea/export/
└── {date}-{time}-{title_slug}/
    ├── {title_slug}.png         # Generated image
    └── {title_slug}.md          # Companion markdown with generation metadata
```

### Companion Markdown Frontmatter

```markdown
---
tool: krea
prompt: "a cat astronaut floating in space, photorealistic"
model: bfl/flux-1-dev
job_id: abc123def456
width: 1024
height: 1024
steps: 25
guidance_scale: 3.0
seed: null
style_images: []
styles: []
generation_time_seconds: 12.4
processed_date: 2026-03-18T10:00:00Z
---

# a cat astronaut floating in space, photorealistic

![Generated image](cat-astronaut.png)
```

### Batch File Format

```text
# Lines starting with # are comments and are skipped
a photorealistic mountain lake at sunrise
an impressionist painting of a Paris street
a flat design icon of a coffee cup
```

## Error Handling

Errors are caught per-prompt and logged without halting the overall batch run:

- Krea API errors — auth failures (401), rate limits (429), job failures (non-success job status), timeout after `max_poll_attempts` exceeded
- Image download errors — network failures or unexpected content types when retrieving the generated image

Failed items are recorded with `status: error` in the state database and reported in the run summary.

- Top-level `try/except` in CLI entry point catches all above and prints descriptive messages.
- Exit codes: `0` all items succeeded, `1` fatal error, `2` partial failure (some items errored)

## Testing

- **Mock targets:** `httpx` (patch `httpx.Client` or `httpx.AsyncClient` for all Krea API calls)
- **Test fixtures:** mock API response JSON objects for job submission, job status polling, and image URL responses
- **Markers:** `slow` for full generation cycles with polling, `integration` for live API calls, `error_handling` for fault injection
- Unit tests cover: state key hashing, aspect ratio resolution, config validation, batch file parsing (comment skipping)
- Integration tests (skipped by default) require `KREA_API_KEY` in the environment
- Test directory: `tests/krea/` with `conftest.py` for shared fixtures
- Fixture data files stored in `tests/krea/fixtures/`
