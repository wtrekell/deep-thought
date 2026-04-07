# Tools Overview

The **deep-thought** namespace contains 8 CLI tools that collect, convert, and structure data from external services into LLM-optimized markdown. All tools export to a canonical SQLite database (or state table) and write markdown that Claude can consume.

## All 8 Tools

| Tool         | CLI Entry Point       | Purpose                                                                                                                                        |
| ------------ | --------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| **Audio**    | `audio`               | Transcribes audio files to markdown using Whisper or MLX-Whisper. Supports speaker diarization and hallucination detection.                    |
| **File-txt** | `file-txt`            | Converts PDF and Office files (Word, Excel, PowerPoint) to LLM-optimized markdown. No OCR — native text extraction only.                       |
| **GCal**     | `gcal`                | Pulls Google Calendar events and stores them in SQLite. Supports creating, updating, and deleting events from markdown frontmatter.            |
| **GDrive**   | `gdrive`              | Incremental Google Drive backup: compares local files against SQLite state, uploads new/changed files, skips unchanged ones.                   |
| **Gmail**    | `gmail`               | Rule-based email collection via Gmail API with optional AI extraction, post-collection actions (archive, label, forward), and markdown export. |
| **Reddit**   | `reddit`              | Collects Reddit posts and comments via PRAW with rate-limit retry/backoff, score and age filters, and image extraction.                        |
| **Research** | `search` / `research` | AI-powered web research via Perplexity API. Two modes: `search` (fast lookups) and `research` (deep research with async polling).              |
| **Web**      | `web`                 | Rule-based web crawler with three modes (blog, documentation, direct). Converts pages to markdown using Playwright for JavaScript rendering.   |

## Documentation by Tool

Each tool has documentation stored in its own directory: `docs/tools/{tool}/`

### Standard Files (Most Tools)

Every tool has:

- **`CHANGELOG.md`** — Version history and all notable changes
- **`ISSUES.md`** — Known bugs, workarounds, version-specific notes, and debugging tips
- **`260XXX-requirements.md`** — Product brief describing the tool's design, API model, data flow, and SQLite schema

### Tool-Specific Documentation

Some tools have additional files:

- **Reddit** — `api-model.md` (PRAW SDK reference), `ENHANCEMENTS.md` (future work)
- **Todoist** — `api-model.md` (Todoist SDK reference)
- **Web** — `README.md` (comprehensive usage guide with examples)
- **Embeddings** — `260402-qdrant-schema.md` (vector store design used by Reddit, Web, Research)

### Private Requirements

Tools with requirements that are not yet implemented or are still being researched are documented in `docs/tools/00-requirements/`. These are exploration documents — not active tool directories.

## How to Find What You Need

### By Task

| Task                                   | Tool     | Start here                                   |
| -------------------------------------- | -------- | -------------------------------------------- |
| Collect posts and comments from Reddit | Reddit   | `docs/tools/reddit/260322-requirements.md`   |
| Crawl a blog or documentation site     | Web      | `docs/tools/web/README.md`                   |
| Transcribe audio files                 | Audio    | `docs/tools/audio/260322-requirements.md`    |
| Convert PDFs or Word docs to markdown  | File-txt | `docs/tools/file-txt/260321-requirements.md` |
| Sync email messages from Gmail         | Gmail    | `docs/tools/gmail/260323-requirements.md`    |
| Sync events from Google Calendar       | GCal     | `docs/tools/gcal/260323-requirements.md`     |
| Run web research queries               | Research | `docs/tools/research/260323-requirements.md` |
| Backup a Google Drive folder           | GDrive   | `docs/tools/gdrive/260404-requirements.md`   |

### By Documentation Type

| Type                           | Where to Find                                                                   |
| ------------------------------ | ------------------------------------------------------------------------------- |
| How to use a tool              | `docs/tools/{tool}/README.md` (if it exists) or `{tool}/260XXX-requirements.md` |
| Recent changes and fixes       | `docs/tools/{tool}/CHANGELOG.md`                                                |
| Known bugs and workarounds     | `docs/tools/{tool}/ISSUES.md`                                                   |
| API reference for a tool's SDK | `docs/tools/{tool}/api-model.md` (if available)                                 |
| Full design and architecture   | `docs/tools/{tool}/260XXX-requirements.md`                                      |

## Tool Types and Data Flow

All tools follow one of four patterns:

**Collector** (Reddit, Web, Research, Gmail, Audio, GCal)

- Periodically fetches content from an external source
- Tracks state (SQLite) to avoid reprocessing
- Exports LLM-optimized markdown
- No write-back to source

**Bidirectional Collector** (Todoist, GCal with create/update/delete)

- Fetches and writes back to the source
- Full relational schema with sync semantics
- Tracks state across pull-push cycles

**Converter** (File-txt, Audio in one-off mode)

- Processes input you explicitly provide
- No state needed — if you give it the same input again, it just converts again
- No polling or periodicity

**Generative** (Krea, ElevenLabs, APNG — requirements-only, not yet implemented)

- Creates output via an external API from a prompt or spec
- Tracks state to support idempotency
- No polling for external content

For details, see [`../spec/260402-tooling-evolution.md`](../spec/260402-tooling-evolution.md).

## Shared Infrastructure

### SQLite

Most tools store canonical data in SQLite, with one database per tool:

- Location: `data/{tool}/{tool}.db` (default)
- Override: Set `DEEP_THOUGHT_DATA_DIR` environment variable
- Mode: WAL (write-ahead logging) for concurrent access

### Embeddings (Qdrant Vector Store)

Knowledge-content tools (Reddit, Web, Research) write embeddings to a shared Qdrant instance:

- Collection: `deep_thought_db`
- Local server: `localhost:6333`
- Model: `mlx-community/bge-small-en-v1.5-mlx`
- Details: [`embeddings/260402-qdrant-schema.md`](embeddings/260402-qdrant-schema.md)

### Shared Utilities

All tools use:

- **`src/deep_thought/text_utils.py`** — `slugify()` function (consistent text normalization)
- **`src/deep_thought/progress.py`** — Rich-based progress bars and spinners

## Questions?

- **How do I use a specific tool?** → Check that tool's directory in `docs/tools/{tool}/`
- **What's changed recently?** → Read `docs/tools/{tool}/CHANGELOG.md`
- **Is something a bug or expected?** → See `docs/tools/{tool}/ISSUES.md`
- **How does the system work?** → Start at [`../spec/260401-agent-design.md`](../spec/260401-agent-design.md) and [`../spec/260402-tooling-evolution.md`](../spec/260402-tooling-evolution.md)
