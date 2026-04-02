---
title: deep-thought — Repository Overview
date: 2026-04-01
type: spec
status: current
---

# deep-thought — Repository Overview

**deep-thought** is a personal data pipeline. Its purpose is to collect, convert, and structure information from external services into LLM-optimized markdown files that Claude can read as context. It is not a user-facing product.

Every tool in this repo exists to answer a single question: *what does Claude need to know?* Data flows in one direction — from external APIs and local files into a local SQLite database, then exported as markdown. The consumer of all output is Claude. Formats are optimized for machine parsing, not human readability.

The repo is installed system-wide as a set of CLI tools and consumed by downstream private repos where Claude agents run scheduled collection tasks, query the knowledge base, and take action on behalf of the user.

---

## What This Repo Is

| Dimension | Description |
|---|---|
| **Primary output** | LLM-optimized markdown files |
| **Consumer** | Claude (not humans) |
| **Tech stack** | Python 3.12, uv, SQLite, Playwright, Whisper |
| **Installed via** | `uv tool install --editable` — CLI tools available system-wide |
| **Platform** | M4 Pro Mac mini, 48GB RAM; headless access via SSH/tmux/Tailscale |
| **Linked repos** | `magrathea` (private config + workflows), `quiet-evolution` (public content) |

---

## Directory Structure

```
deep-thought/
├── src/deep_thought/       # All tool source code (namespace package)
├── src/config/             # User-edited YAML configuration files
├── tests/                  # 84 test files across all tools
├── files/                  # Documentation: changelogs, issues, requirements
├── spec/                   # Architecture and design documents
├── data/                   # Runtime data — SQLite DBs and exports (git-ignored)
├── pyproject.toml          # Dependencies and project config
└── .env                    # Secrets (git-ignored)
```

---

## Tools

Eight independent CLI tools live under the `deep_thought` namespace package. Each has its own configuration file, SQLite database (where applicable), and output directory under `data/`.

### Todoist

Bidirectional sync between Todoist and local markdown. The only tool with a push capability — all others are read-only collectors.

- **CLI**: `todoist`
- **Commands**: `init`, `config`, `pull`, `push`, `sync`, `status`, `diff`, `export`, `create`, `complete`
- **Data flow**: Todoist API → SQLite → markdown organized by project/section
- **Key features**: Incremental sync via Todoist sync token, task/label/project filtering, comment support
- **API**: Todoist REST API v1 via `todoist-api-python` SDK

### File-txt

Converts local files to markdown. Stateless — no database, no rules, no scheduling.

- **CLI**: `file-txt`
- **Supported formats**: PDF (via Marker), DOCX/PPTX/XLSX/HTML (via MarkItDown), EML/MSG (email)
- **Key features**: PDF OCR forcing, hardware acceleration (MPS/CUDA/CPU), email thread formatting

### Web

Rule-based web crawler that converts pages to markdown.

- **CLI**: `web`
- **Commands**: `init`, `config`, default crawl via `--input` or `--input-file`
- **Data flow**: URL(s) → Playwright headless browser → html2text → SQLite dedup → markdown
- **Key features**: Link recursion, JavaScript rendering, bot-detection bypass, batch configs per site, image extraction
- **Modes**: `blog`, `documentation`, `direct`

### Audio

Transcribes audio files to markdown using local Whisper models.

- **CLI**: `audio`
- **Commands**: `init`, `config`, default transcribe
- **Engines**: MLX-Whisper (Apple Silicon, default), OpenAI Whisper (optional cross-platform)
- **Key features**: Chunked processing for long files, multi-signal hallucination detection, optional speaker diarization via pyannote.audio, filler word removal

### Reddit

Collects Reddit posts and full comment threads based on configurable rules.

- **CLI**: `reddit`
- **Commands**: `init`, `config`, default collect
- **Data flow**: PRAW → submission + comment tree → SQLite → markdown per rule
- **Key features**: Sort/time filter, score/comment thresholds, keyword and flair matching (glob patterns), configurable comment depth
- **API**: Reddit API via PRAW (read-only OAuth, no Reddit account required)

### Gmail

Collects emails based on Gmail search queries, with optional Gemini AI extraction for non-text content.

- **CLI**: `gmail`
- **Commands**: `init`, `config`, `auth`, `send`, default collect
- **Data flow**: Gmail API → optional Gemini extraction → SQLite → markdown per rule
- **Key features**: Post-collection actions (archive, label, forward, delete), HTML newsletter cleaning, Gemini AI decision caching, rate limiting
- **APIs**: Gmail API (OAuth 2.0), Gemini API (`gemini-2.5-flash`) for attachment/HTML extraction

### GCal

Pulls Google Calendar events locally and supports creating, updating, and deleting events from markdown.

- **CLI**: `gcal`
- **Commands**: `init`, `config`, `auth`, `pull`, `create`, `update`, `delete`
- **Data flow**: Google Calendar API → SQLite → markdown per calendar
- **Key features**: Incremental sync via nextSyncToken, recurring event expansion, multiple calendar support, event creation from markdown frontmatter
- **API**: Google Calendar API (OAuth 2.0)

### Research

Stateless AI-powered web research via the Perplexity API. No database — each query produces one output file.

- **CLI**: `search` (fast lookup), `research` (deep async job)
- **Commands**: `init`, `config`, `search "query"`, `research "query"`
- **Key features**: Domain include/exclude filters, recency filtering, async polling for deep research (up to 10 minutes), context file injection for follow-up queries
- **API**: Perplexity API — `sonar` model for search, `sonar-deep-research` for research

---

## Tool Architecture

Every tool follows the same internal structure:

| File | Role |
|---|---|
| `cli.py` | Argument parsing, command dispatch, error handling, exit codes |
| `config.py` | YAML → dataclass, validation, env var resolution |
| `models.py` | Local data types (dataclasses only, no API calls) |
| `client.py` | API wrapper — SDK calls, retry logic, rate limiting |
| `db/schema.py` | SQLite connection factory, migration runner |
| `db/queries.py` | All database reads and writes |
| `db/migrations/*.sql` | Forward-only numbered schema migrations |
| `pull.py` / `processor.py` | API → DB transformation, filter application |
| `output.py` | DB → markdown with YAML frontmatter |
| `filters.py` | Rule matching logic |
| `llms.py` | Aggregate `.llms.txt` and `.llms-full.txt` generation |

---

## Configuration

All configuration is YAML. User-edited files live in `src/config/`. Each tool ships a `default-config.yaml` inside its package as a starting template.

Secrets are never stored in YAML — they are referenced by environment variable name and resolved from `.env` at runtime.

Common sections across all tools:

| Section | Purpose |
|---|---|
| **Authentication** | Credentials paths, token paths, OAuth scopes, API key env var names |
| **Rules** | Collection rules: queries, subreddits, URLs, filters, thresholds |
| **Retry** | `max_attempts`, `base_delay_seconds` (exponential backoff) |
| **Rate limits** | Requests per minute |
| **Output** | Export directory, flat vs. nested layout, `generate_llms_files` toggle |
| **Limits** | Max items per run, age windows, score thresholds |

---

## Database Layer

Six tools use SQLite. File-txt and Research are stateless and use no database.

All databases share the same connection settings:

```python
PRAGMA journal_mode = WAL   # Better concurrent reads
PRAGMA foreign_keys = ON    # Referential integrity
row_factory = sqlite3.Row   # Column access by name
```

Schema changes use forward-only numbered migration files (`001_initial.sql`, `002_*.sql`, etc.). The current schema version is tracked in a `key_value` or `sync_state` table per database.

---

## Output Format

All exports are markdown files with YAML frontmatter. Frontmatter carries machine-readable metadata; the body carries content. Example:

```markdown
---
tool: reddit
post_id: abc123
subreddit: MachineLearning
author: username
score: 847
post_date: 2026-03-15T14:22:00Z
rule: ml-daily
---

# Post title

Post body and full comment thread...
```

Each tool organizes exports into subdirectories by logical grouping (calendar name, subreddit, Gmail label, Todoist project, etc.).

**Aggregate context files** (optional, `generate_llms_files: true`):
- `.llms.txt` — Navigable index, one entry per document
- `.llms-full.txt` — Complete content of all collected documents concatenated

These are intended to be loaded wholesale as Claude context for a given topic area.

---

## Shared Infrastructure

**`progress.py`** — Used by all tools. Rich-based progress bar and spinner with graceful TTY degradation (no ANSI codes when output is piped). Orange spinner, purple progress bar.

**Result dataclasses** — Every sync or collect operation returns a typed result (`PullResult`, `CollectResult`, etc.) capturing counts of synced, filtered, skipped, and failed items, enabling consistent CLI output across tools.

---

## files/ — Documentation

`files/` is tracked in git but separate from source code. Per project convention, `CHANGELOG.md` and `ISSUES.md` for each tool live here — not in the source directory.

```
files/
├── tools/{tool}/
│   ├── CHANGELOG.md              # Release notes
│   ├── ISSUES.md                 # Known bugs and limitations
│   └── 260XXX-requirements.md   # Feature specification
├── tools/00-requirements/        # Future tool specs (private, 00- prefix)
├── templates/                    # Templates for new tool specs
├── future-enhancements/          # Longer-horizon ideas
└── api-mcp-sdk.md                # API, MCP server, and SDK reference
```

---

## Development

```bash
uv sync                                           # Install dependencies
uv sync --extra dev                               # Add dev tools
ruff check .                                      # Lint
ruff check --fix .                                # Auto-fix
ruff format .                                     # Format
mypy --python-executable .venv/bin/python src/   # Type check (strict mode)
pytest                                            # Tests + coverage
npm run format                                    # Prettier for markdown, YAML, JSON
```

Code style: ruff (line-length 120, double quotes), mypy strict, `from __future__ import annotations` in every file, all public functions typed.

**Testing**: 84 test files, coverage auto-enabled. In-memory SQLite for unit tests. Markers: `slow`, `integration`, `error_handling`.

---

## Multi-Repo Architecture

This repo is one of three:

| Repo | Purpose |
|---|---|
| **deep-thought** (this repo) | Build and maintain the tools |
| **magrathea** (private) | Personal configuration, collected data, Claude agent workflows |
| **quiet-evolution** (public) | Public-facing content and documentation |

deep-thought is installed into the other repos via `uv tool install --editable`, making all CLI entry points available system-wide without copying code.

---

## Private Content

Directories and files with a `00-` prefix are strictly private to this repository. They must never be referenced, linked, imported, or exposed outside of it — no cross-repo references, no documentation links, no API exposure.

Current private content: `files/tools/00-requirements/` — specifications for tools not yet built.

---

## Key Relationships

```
External services (Todoist, Reddit, Gmail, Google Calendar, Perplexity)
    ↓ collected by
CLI tools (todoist, reddit, gmail, gcal, research, web, audio, file-txt)
    ↓ stored in
SQLite databases (data/{tool}/{tool}.db)
    ↓ exported as
Markdown + YAML frontmatter (data/{tool}/export/)
    ↓ aggregated into
.llms.txt / .llms-full.txt context files
    ↓ read by
Claude agents (in magrathea and other consuming repos)
```

The next major phase adds a vector layer: Qdrant (local) + an MLX embedding model for semantic retrieval across collected documents, enabling Claude to query the knowledge base rather than loading all files as context.
