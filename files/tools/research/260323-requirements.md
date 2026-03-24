# Product Brief — Research Tool

## Name and Purpose

**Research Tool** — performs AI-powered web research via the Perplexity API and saves results as LLM-optimized markdown. Two separate CLI commands select the research depth: `search` for fast lookups and `research` for thorough multi-source synthesis. Context-aware follow-up queries reuse prior research files to avoid redundant searches.

## CLI Entry Points

| Command    | Perplexity Model    | Typical Time | Approx. Cost  |
| ---------- | ------------------- | ------------ | ------------- |
| `search`   | sonar               | 2–10 seconds | ~$0.006/query |
| `research` | sonar-deep-research | 2–4 minutes  | ~$0.24/query  |

Both commands share the same query format, flags, configuration, and output structure. The only difference is which Perplexity model is called. The `search` command additionally supports a `--quick` flag that prints the answer to stdout without writing a file — useful for rapid lookups from the terminal.

### Query Input

The first positional argument is the query text — always sent directly to Perplexity as-is.

```bash
search "What are the latest developments in MLX?"
```

There is no file detection or file-reading behavior. The positional argument is always treated as a query string.

## Requirements

1. Python 3.12 using `uv` as the package manager.
2. **httpx** for HTTP requests to the Perplexity API.
3. `PERPLEXITY_API_KEY` stored in `.env` or system environment. Loaded via `load_dotenv()`.
4. No SQLite state — the tool is stateless; each query always runs.
5. No `auth` subcommand — authentication is handled entirely by the API key in the environment. No OAuth flow is needed.
6. A changelog is maintained in `files/tools/research/CHANGELOG.md`.

## Design Notes

- **Two commands, one package:** `search` and `research` are separate `pyproject.toml` entry points that both route into `cli.py`. Each sets the Perplexity model internally — there is no `--mode` flag.
- **API endpoints:** The `search` command uses the synchronous Chat Completions endpoint (`POST https://api.perplexity.ai/chat/completions`), which follows the OpenAI-compatible format. The `research` command uses the async endpoint (`POST https://api.perplexity.ai/async/chat/completions`) — it submits a job and polls for results, which is more reliable for the 2–4 minute deep research queries. Async polling uses a 5-second interval with a 10-minute timeout. Both endpoints return `choices[0].message.content` as the answer, with the `search_results` array and `usage.cost` object in the response metadata.
- **Related questions:** All requests send `return_related_questions: true` — always enabled, not configurable.
- **Stateless by design:** Research results are always fresh. No deduplication or skip logic. No `--force` flag is needed because there is no cached state to clear.
- **Context flag:** `--context PATH` reads one or more prior research `.md` files and prepends their content to the user message sent to the API. Context is wrapped in structured XML tags so the model can distinguish prior research from the new query:

  ```xml
  <prior_research>
  <file path="data/research/export/2026-03-23_mlx-developments.md">
  ...file contents...
  </file>
  </prior_research>

  <query>What are the performance implications?</query>
  ```

- **Domain filtering:** Up to 20 domains can be specified to restrict search scope. Prefix a domain with `-` to exclude it (denylist mode). Allowlist and denylist domains cannot be mixed in the same request.
- **No `.llms.txt` generation:** Each output file is already LLM-optimized markdown with structured frontmatter, so separate `.llms.txt` / `.llms-full.txt` files are not generated.

## Data Storage

Output files are written to `data/research/export/` by default. Respects the `DEEP_THOUGHT_DATA_DIR` env var to redirect the data root at runtime. No SQLite database is used — the tool is stateless.

## Data Models

### ResearchResult

| Field               | Type                 | Description                                                                             |
| ------------------- | -------------------- | --------------------------------------------------------------------------------------- |
| `query`             | `str`                | The research question submitted                                                         |
| `mode`              | `str`                | Research mode used (`search` or `research`)                                             |
| `model`             | `str`                | Perplexity model name (e.g., `sonar`, `sonar-deep-research`)                            |
| `recency`           | `str \| None`        | Recency filter applied (`hour`, `day`, `week`, `month`, `year`, or `None`)              |
| `domains`           | `list[str]`          | Domain filters applied (empty list if none)                                             |
| `context_files`     | `list[str]`          | Paths to context files included in the query (empty list if none)                       |
| `answer`            | `str`                | Synthesized answer text from Perplexity                                                 |
| `search_results`    | `list[SearchResult]` | Structured source citations from the API `search_results` field                         |
| `related_questions` | `list[str]`          | Follow-up questions from the API (requires `return_related_questions: true` in request) |
| `cost_usd`          | `float`              | Total cost in USD from the API `usage.cost.total_cost` field                            |
| `processed_date`    | `str`                | ISO 8601 timestamp of when the query was executed                                       |

Methods: `from_api_response()` for Perplexity response dict conversion, `to_frontmatter_dict()` for YAML frontmatter generation.

### SearchResult

Maps to the `search_results` array in the Perplexity API response. The older `citations` field (plain URL list) was deprecated in May 2025 — use `search_results` exclusively.

| Field     | Type          | Description                                   |
| --------- | ------------- | --------------------------------------------- |
| `title`   | `str`         | Source page title                             |
| `url`     | `str`         | Source URL                                    |
| `snippet` | `str \| None` | Relevant snippet from the source              |
| `date`    | `str \| None` | Publication date of the source (if available) |

## Command List

Running either command with no arguments shows help.

### Shared Flags

Both `search` and `research` accept the same flags:

| Flag                                       | Description                                                                   |
| ------------------------------------------ | ----------------------------------------------------------------------------- |
| `QUERY` (positional)                       | Research question as inline text (required)                                   |
| `--output PATH`                            | Output directory override                                                     |
| `--config PATH`                            | YAML configuration file (default: `src/config/research-configuration.yaml`)   |
| `--context PATH`                           | Prior research file(s) to include as context (repeatable)                     |
| `--domains TEXT`                           | Comma-separated domains to filter search (max 20; prefix with `-` to exclude) |
| `--recency [hour\|day\|week\|month\|year]` | Filter results by recency                                                     |
| `--dry-run`                                | Show query that would be sent without calling API                             |
| `--verbose`, `-v`                          | Detailed logging                                                              |
| `--save-config PATH`                       | Generate example config and exit                                              |
| `--version`                                | Show version and exit                                                         |

### search-only Flags

| Flag      | Description                                                        |
| --------- | ------------------------------------------------------------------ |
| `--quick` | Print the answer to stdout and exit without writing an output file |

### Subcommands (research only)

The `research` entry point has the following subcommands. The `search` entry point has no subcommands — it only accepts a query.

| Subcommand        | Description                                                                                                                         |
| ----------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| `research config` | Validate and display current YAML configuration                                                                                     |
| `research init`   | Create data directories (`data/research/`, `data/research/export/`) and generate a starter `research-configuration.yaml` if missing |

### Usage Examples

```bash
# Quick search — print answer to stdout, no file written
search "What are the latest developments in MLX?" --quick

# Search with file output (default)
search "What are the latest developments in MLX?"

# Deep research with inline query (uses async API, writes file)
research "Compare MLX vs PyTorch performance on Apple Silicon"

# Deep research with context from prior search results
research "What are the performance implications?" --context data/research/export/2026-03-23_mlx-developments.md

# Search with domain filtering
search "site reliability engineering best practices" --domains google.com,aws.amazon.com

# Dry run to preview query
search "test query" --dry-run

# Setup and configuration (research entry point only)
research init
research config
```

## File & Output Map

```
files/tools/research/
├── 260323-requirements.md       # This document
└── CHANGELOG.md                 # Release history

src/deep_thought/research/
├── __init__.py
├── cli.py                       # CLI entry points (search_main, research_main)
├── config.py                    # YAML config loader and validation
├── models.py                    # ResearchResult and SearchResult dataclasses
├── researcher.py                # Perplexity API client (sync for search, async polling for research)
└── output.py                    # Markdown + YAML frontmatter generation

data/research/
└── export/                      # Generated research files (no state DB)

src/config/
└── research-configuration.yaml  # Tool configuration
```

### Entry Points (pyproject.toml)

```toml
[project.scripts]
search = "deep_thought.research.cli:search_main"
research = "deep_thought.research.cli:research_main"
```

## Configuration

Configuration is stored in `src/config/research-configuration.yaml`. All values below are required unless marked optional.

```yaml
# API
api_key_env: "PERPLEXITY_API_KEY"
retry_max_attempts: 3 # Retry failed API calls with exponential backoff
retry_base_delay_seconds: 1 # Initial delay doubles on each retry

# Models
search_model: "sonar" # Model used by the search command
research_model: "sonar-deep-research" # Model used by the research command

# Defaults
default_recency: null # null, "hour", "day", "week", "month", "year" (optional)

# Output
output_dir: "data/research/export/"
```

### Configuration Validation

- `retry_max_attempts` must be > 0
- `retry_base_delay_seconds` must be > 0
- `default_recency` must be one of `null`, `hour`, `day`, `week`, `month`, `year`
- `api_key_env` must be a non-empty string
- `search_model` and `research_model` must be non-empty strings

## Data Format

### Markdown Output

Each query produces one file:

```
data/research/export/
└── {date}_{slug}.md             # Research results with YAML frontmatter
```

**Filename sanitization:** `{slug}` is generated by lowercasing, replacing non-alphanumeric characters with hyphens, collapsing consecutive hyphens, stripping leading/trailing hyphens, and truncating to 80 characters.

### Frontmatter Schema

```markdown
---
tool: research
query: "What are the latest developments in MLX on Apple Silicon?"
mode: search
model: sonar
recency: week
cost_usd: 0.006
processed_date: 2026-03-18T10:00:00Z
---
```

Only include metadata fields with non-null, non-empty values in the frontmatter. Empty lists (e.g., `domains`, `context_files`) are omitted. When present, `context_files` records which prior research files were passed via `--context` for traceability.

### Content Structure

```markdown
# What are the latest developments in MLX on Apple Silicon?

## Answer

Synthesized answer from multiple sources...

## Sources

1. [Source Title](https://example.com/article) — snippet
2. [Another Source](https://another.com/post) — snippet

## Related Questions

- How does MLX compare to PyTorch on Apple Silicon?
- What models are currently supported by MLX?
```

## Error Handling

- `Perplexity API errors` (auth, rate limits, content filtering) — caught per-query; logs the error with the query text and exits with code 1.
- `Perplexity API rate limit / transient errors` (HTTP 429, 500, 503) — retried with exponential backoff up to `retry_max_attempts` (default 3). Initial delay is `retry_base_delay_seconds`, doubling on each retry. Permanent failures (4xx other than 429) are not retried.
- `Async polling timeout` — if the `research` command's async job does not complete within 10 minutes, exit with code 1 and a descriptive message.
- `Context file loading errors` — caught per context file specified with `--context`; logs the offending path and aborts before calling the API.
- Missing config file raises `FileNotFoundError`. Invalid config content raises `ValueError`. Missing required env vars (e.g., `PERPLEXITY_API_KEY`) raise `OSError`.
- Top-level `try/except` in CLI entry point catches all above and prints descriptive messages.
- Exit codes: `0` success, `1` fatal error

Note: Exit code `2` (partial failure) is not used because each command processes a single query per invocation. If batch/multi-query support is added in the future, exit code `2` should be introduced for partial failures.

## Testing

- Mock target: **httpx** — mock at the transport layer to return fixture JSON responses without real network calls.
- Test fixtures: mock Perplexity API response JSON covering search, deep research, async polling responses, and error responses.
- Test both entry points (`search_main`, `research_main`) to verify correct model and endpoint selection.
- Test `search --quick` prints to stdout and does not write a file.
- Test that the positional query argument is sent directly to the API as-is.
- Test context XML formatting — verify `<prior_research>`, `<file>`, and `<query>` tags are correctly structured.
- Test async polling flow for `research` — job submission, polling, and result retrieval.
- Test classes organized by feature area: query construction, context file loading, output formatting, config validation, retry logic, async polling.
- Mark slow or network-dependent tests with `@pytest.mark.slow` and `@pytest.mark.integration`.
- Mark error path tests with `@pytest.mark.error_handling`.
- Write docstrings on every test method.
- Test directory: `tests/research/` with `conftest.py` for shared fixtures
- Fixture data files stored in `tests/research/fixtures/`

## User Questions

_(None yet — record questions raised during requirements gathering and their answers here.)_

## Claude Questions

1. **Stdout output for quick searches** — Should the answer be printed to stdout for quick lookups?
   **Decision:** Yes — added `--quick` flag to `search` that prints the answer to stdout without writing a file.

2. **Streaming for deep research** — Should the `research` command stream progress to stderr during 2–4 minute queries?
   **Decision:** No. No streaming.

3. **Entry point name collision** — `search` is generic. Is the collision risk acceptable?
   **Decision:** Yes. Single-user tool, known command environment.

4. **`--rate-limit` flag usefulness** — Should there be a CLI flag for rate limiting?
   **Decision:** Removed. Rate limit is config-only (`rate_limit_rpm` in YAML).

5. **Subcommand duplication** — Should `init` and `config` exist on both entry points?
   **Decision:** No duplication. Subcommands live on `research` only. `search` has no subcommands.

6. **How `--context` is sent to the API** — How are context files incorporated into the request?
   **Decision:** Prepend to the user message with structured XML tags (`<prior_research>`, `<file>`, `<query>`) so the model can distinguish prior research from the new query.

7. **Query file detection ambiguity** — What if a query string matches an existing filename?
   **Decision:** No file detection. The positional argument is always a query string sent directly to Perplexity. This is a web search tool, not a file system tool.

8. **Async mode for deep research** — Should `research` use the async endpoint?
   **Decision:** Yes. The `research` command uses `POST /async/chat/completions` (submit + poll) for reliability over long-running queries. The `search` command uses the synchronous endpoint.

## Pre-Build Tasks

1. Obtain a Perplexity API key from [perplexity.ai](https://docs.perplexity.ai/)
2. Add `PERPLEXITY_API_KEY` to `.env`
3. Verify `.gitignore` covers `data/research/`
4. Add `httpx` to project dependencies in `pyproject.toml` if not already present
