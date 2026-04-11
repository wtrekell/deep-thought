# src/ CLAUDE.md

Tool-specific architecture, code style, and key requirements for the `deep_thought` namespace package.

## Architecture

- **Package layout:** `src/deep_thought/` — standard Python src layout using hatchling as the build backend. Tools are subpackages (e.g., `src/deep_thought/todoist/`).
- **Todoist tool structure:** CLI entry point (`cli.py`), SDK wrapper (`client.py`), YAML config (`config.py`), task creation (`create.py`), SQLite layer (`db/schema.py`, `db/queries.py`, `db/migrations/`), local models (`models.py`), sync orchestration (`pull.py`, `push.py`, `sync.py`), markdown export (`export.py`), filter engine (`filters.py`).
- **Data flow:** Todoist API → SQLite (canonical store) → markdown export. The AI reads only from SQLite/exports, never directly from Todoist.
- **Configuration:** `src/config/todoist-configuration.yaml` holds API token env var name, project opt-in list, pull/push filter rules (based on Todoist Meta class), and Claude involvement markers.
- **Data directory:** `data/todoist/` by default — contains `todoist.db`, JSON snapshots per sync, and exported markdown organized by project/section. Override with the `DEEP_THOUGHT_DATA_DIR` env var to redirect all data to a different path.
- **file-txt tool:** `src/deep_thought/file_txt/` — converts PDF and Office files to markdown using `pymupdf4llm` (PDF) and `markitdown` (Office/HTML). No OCR — native PDF text extraction only. CLI entry point: `file-txt`. Config: `src/config/file-txt-configuration.yaml`.
- **Gmail tool:** `src/deep_thought/gmail/` — rule-based email collection via Gmail API with OAuth 2.0, optional Gemini AI extraction (via `google-genai`), post-collection actions (archive, label, forward, delete), and markdown output with optional Qdrant embeddings. Per-rule `save_mode` field (default `"individual"`) controls file output: `individual`, `append`, `both`, or `none`. CLI entry point: `gmail`. Config: `src/config/gmail-configuration.yaml`. SQLite layer at `db/schema.py`, `db/queries.py`, `db/migrations/`.
- **GCal tool:** `src/deep_thought/gcal/` — pulls events from Google Calendar, stores in SQLite, exports LLM-optimized markdown. Supports creating, updating, and deleting events from markdown with YAML frontmatter. CLI entry point: `gcal`. Config: `src/config/gcal-configuration.yaml`. SQLite layer at `db/schema.py`, `db/queries.py`, `db/migrations/`.
- **Research tool:** `src/deep_thought/research/` — AI-powered web research via Perplexity API, saves LLM-optimized markdown. Two CLI entry points: `search` (fast lookups via sonar) and `research` (deep research with async polling via sonar-deep-research). Config: `src/config/research-configuration.yaml`. Stateless — no SQLite database.
- **Web tool:** `src/deep_thought/web/` — rule-based web crawler that converts pages to LLM-optimized markdown. Supports blog, documentation, and direct crawl modes with optional batch processing. CLI entry point: `web`. Config: `src/config/web-configuration.yaml`; batch configs in `src/config/web/`. SQLite layer at `db/schema.py`, `db/queries.py`, `db/migrations/`. Key modules: `crawler.py` (Playwright-based fetching), `converter.py` (HTML → markdown), `processor.py`, `filters.py`, `image_extractor.py`, `llms.py`.
- **Audio tool:** `src/deep_thought/audio/` — transcribes audio files to LLM-optimized markdown using Whisper (CPU/GPU) or MLX-Whisper (Apple Silicon). CLI entry point: `audio`. Config: `src/config/audio-configuration.yaml`. SQLite layer at `db/schema.py`, `db/queries.py`, `db/migrations/`. Key modules: `engines/mlx_whisper_engine.py`, `engines/whisper_engine.py`, `diarization.py`, `hallucination.py`, `processor.py`, `output.py`, `llms.py`.
- **Reddit tool:** `src/deep_thought/reddit/` — rule-based collection of Reddit posts and comments via PRAW, with rate-limit retry/backoff. CLI entry point: `reddit`. Config: `src/config/reddit-configuration.yaml`. SQLite layer at `db/schema.py`, `db/queries.py`, `db/migrations/`. Key modules: `client.py` (PRAW wrapper), `processor.py` (rule engine, retry logic), `output.py` (markdown + YAML frontmatter), `image_extractor.py` (downloads post images to `img/` when `include_images: true`), `filters.py` (score, age, keyword, flair, stickied, locked), `utils.py`.
- **Stack Exchange tool:** `src/deep_thought/stackexchange/` — rule-based collection of Q&A threads from Stack Exchange sites via API v2.3, with tag-based discovery, incremental updates (re-process on new answers), quota tracking, and rate-limit retry/backoff. CLI entry point: `stackexchange`. Config: `src/config/stackexchange-configuration.yaml`. SQLite layer at `db/schema.py`, `db/queries.py`, `db/migrations/`. Key modules: `client.py` (httpx wrapper with pagination and backoff), `processor.py` (rule engine, batch answer/comment fetching), `output.py` (markdown + YAML frontmatter for Q&A threads), `filters.py` (score, age, keyword, tag, answered), `llms.py`, `embeddings.py`.
- **GDrive tool:** `src/deep_thought/gdrive/` — incremental Google Drive backup. Walks a local source directory, compares mtime against SQLite state, uploads new files, updates changed files, and skips unchanged ones. CLI entry point: `gdrive`. Subcommands: `init`, `config`, `auth`, `status`, and default `backup` (with `--dry-run`, `--force`, `--verbose`). Config: `src/config/gdrive-configuration.yaml`. SQLite layer at `db/schema.py`, `db/queries.py`, `db/migrations/`. Key modules: `client.py` (Drive API v3 wrapper with rate limiting and retry), `walker.py` (directory traversal), `uploader.py` (backup orchestration), `_auth.py` (OAuth 2.0 token lifecycle).

## Multi-Repo Symlinks

Tool source code is shared via symlinks, not duplication. The single copy lives in `deep-thought/src/deep_thought/`. Consuming repos point into it. Symlinks are not tracked by git — create them manually after cloning.

**magrathea** (run from magrathea root):

```bash
ln -s ../../deep-thought/src/deep_thought src/deep_thought
ln -s ../../deep-thought/docs 00-reference/10-dt-docs
ln -s ../../deep-thought/files 00-reference/10-dt-files
```

Any change to tool source in deep-thought is immediately reflected in magrathea with no additional steps.

## Shared Utilities

- **`src/deep_thought/text_utils.py`** — canonical `slugify(text, max_length=80)` function used by all tools. Tools pass their preferred `max_length` explicitly. Replaces per-tool private implementations that had diverged.
- **`src/deep_thought/progress.py`** — Rich-based progress bar and spinner, used by all tools. Orange spinner, purple progress bar. Degrades gracefully when output is piped.
- **`src/deep_thought/secrets.py`** — Keychain-first secret storage with `.env` fallback. Provides `get_secret()` for API keys (checks keychain then env var) and `get_oauth_credentials()` for Google OAuth tokens (keychain with file fallback and auto-migration). All tools use this module — do not use `os.environ.get()` directly for secrets. Google OAuth uses a shared token: all three Google tools (gmail, gcal, gdrive) call `get_oauth_credentials()` with `service=GOOGLE_SERVICE` (`"google"`) and the combined `GOOGLE_OAUTH_SCOPES` list, storing a single entry under the `deep-thought-google` keychain key. Running `auth` on any one of the three tools authenticates all three. On first use with the shared service name, legacy per-tool keychain entries (`deep-thought-gmail`, `deep-thought-gcal`, `deep-thought-gdrive`) are removed automatically.

## Embedding Infrastructure

Gmail, Reddit, Web, Stack Exchange, and Research write embeddings to a shared Qdrant vector store at runtime. The shared module is `src/deep_thought/embeddings.py`. Each tool has its own `embeddings.py` that calls the shared `write_embedding()` function.

- **Shared module:** `src/deep_thought/embeddings.py` — `write_embedding()`, `ensure_collection()`, `create_embedding_model()`, `create_qdrant_client()`, `strip_frontmatter()`
- **Per-tool modules:** `gmail/embeddings.py`, `reddit/embeddings.py`, `web/embeddings.py`, `stackexchange/embeddings.py`, `research/embeddings.py`
- **Collection:** configurable per tool via `qdrant_collection` in each tool's YAML config (default: `deep_thought_db`); web batch configs in `src/config/web/` can each specify a different collection to separate corpora. The Qdrant server runs at `localhost:6333` (binary at `~/bin/qdrant` v1.17.1, managed by LaunchAgent `com.williamtrekell.qdrant` — starts automatically at login, logs to `~/qdrant_storage/qdrant.log`). Collections are created automatically on first write via `ensure_collection()`.
- **Model:** `mlx-community/bge-small-en-v1.5-bf16` via `mlx-embeddings`
- **Error handling:** embedding failure never aborts a collection run — logged as a warning, processing continues
- **Install:** `qdrant-client` and `mlx-embeddings` are core dependencies — installed automatically via `uv sync`

## Code Style & Tooling Configuration

- **Line length:** 120 characters (both ruff and prettier)
- **Python:** Double quotes, space indentation, ruff handles isort
- **mypy:** Strict mode — all functions must have type annotations, no untyped defs, no implicit optionals. Must be run with `--python-executable .venv/bin/python` (see CLAUDE.md) so mypy resolves project dependencies; without it all third-party imports appear unresolved.
- **Test markers:** `slow`, `integration`, `error_handling`
- **Coverage:** Auto-enabled via pytest addopts — use `--no-cov` to disable

## Key Requirements

### Shared SQLite Conventions

All tools with a SQLite layer follow the same conventions:
- Tables include `created_at` and `updated_at` columns; `synced_at` is added only for bidirectional sync tools (e.g., Todoist, GCal) — read-only Collectors (Reddit, Stack Exchange, Web) omit it
- Bidirectional tools use a `sync_state` table to track the last successful sync
- Secrets are stored in macOS Keychain (primary) with `.env` as fallback; see `src/deep_thought/secrets.py`

### Todoist-Specific

- Uses the [official Todoist SDK for Python](https://doist.github.io/todoist-api-python/)
- Tables mirror Todoist entities: `projects`, `sections`, `tasks`, `labels`, `task_labels`, `comments`, `sync_state`
- All rows use `id` as the primary key (the Todoist-issued string ID)
