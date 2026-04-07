# Research Tool

AI-powered web research via Perplexity API with two CLI entry points: `search` for quick lookups and `research` for deep, multi-source investigation.

## Overview

The Research Tool provides two modes of web research via the Perplexity API:

- **`search`** — Fast synchronous queries via sonar model (5-30 seconds)
- **`research`** — Deep asynchronous research via sonar-deep-research (minutes to hours)

Both modes accept domain filters, recency constraints, and optional context documents, and output LLM-optimized markdown. No SQLite layer — stateless operation optimized for quick insight generation.

## Data Flow

```
Query + Context → Perplexity API (sonar or sonar-deep-research)
                         ↓
                  (async polling for deep research)
                         ↓
                   Markdown Export → [Optional: Embeddings to Qdrant]
```

## Setup

1. Add your Perplexity API key to `.env` at the project root:

   ```
   PERPLEXITY_API_KEY=your_api_key_here
   ```

2. Configure optional defaults in `src/config/research-configuration.yaml`.

3. Run a quick search:

   ```bash
   search "What is MLX?"
   ```

4. Run a deep research job:

   ```bash
   research "Compare MLX vs PyTorch performance"
   ```

## Configuration

Configuration lives at `src/config/research-configuration.yaml`. Key settings:

- **api_key** — Perplexity API key (read from `PERPLEXITY_API_KEY` env var if not specified)
- **sonar_model** — Model for `search` command (default: `sonar`)
- **sonar_deep_model** — Model for `research` command (default: `sonar-deep-research`)
- **embeddings** — Enable/disable Qdrant embedding writes

## CLI Usage

```bash
# Quick search (synchronous)
search "What is MLX?" --recency month

# Deep research (asynchronous, with polling)
research "Compare MLX vs PyTorch" --domains github.com,pytorch.org

# With context documents and domain filters
research "Explain tokenization" --context path/to/file.md --domains huggingface.co

# Initialize config and output directories
research init
research config
```

## Module Structure

| Module          | Role                                                  |
| --------------- | ----------------------------------------------------- |
| `cli.py`        | CLI entry points: `search` and `research` subcommands |
| `config.py`     | YAML config loader with Perplexity API key resolution |
| `models.py`     | Result dataclasses with source and citation metadata  |
| `researcher.py` | Perplexity API client with async polling and retry    |
| `output.py`     | Markdown generation with citations and metadata       |
| `embeddings.py` | Writes research results to Qdrant vector store        |

## Data Storage

All paths are rooted at `data/research/` by default. Set `DEEP_THOUGHT_DATA_DIR` to redirect.

- **Markdown export** — `<data_dir>/export/<query_slug>.md`
- **Embeddings** — Written to Qdrant at `localhost:6333`; collection name set by `qdrant_collection` in `research-configuration.yaml` (default: `deep_thought_db`)

## Tool-Specific Notes

- **Stateless:** No SQLite layer; tool is optimized for one-off queries and context generation
- **Two modes:** `search` is fast and cacheable; `research` is thorough but slower (use for complex questions)
- **Async polling:** Deep research jobs are submitted and polled; timeout is 10 minutes
- **Domain filters:** Use to constrain results to specific sites (max 20 domains per query)
- **Recency filters:** Choose from `hour`, `day`, `week`, `month`, `year`, `3 months`, or `6 months`. The last two are
  aliases that map to `"year"` at the Perplexity API level (the closest supported superset); the user-specified value
  is preserved in output frontmatter and Qdrant payloads for transparency.
- **Context documents:** Pass markdown files to include as reference (improves relevance)
- **Embeddings:** Requires MLX embeddings (optional extra) and Qdrant running at `localhost:6333`
- **Citations:** Research results include source URLs and publication metadata
- **Rate limiting:** Perplexity API quotas respected; backoff applied on 429 responses
