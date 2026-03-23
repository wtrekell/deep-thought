# Product Brief — Research Tool

## Name and Purpose

**Research Tool** — performs AI-powered web research via the Perplexity API and saves results as LLM-optimized markdown. Two separate CLI commands select the research depth: `search` for fast lookups and `research` for thorough multi-source synthesis. Context-aware follow-up queries reuse prior research files to avoid redundant searches.

## CLI Entry Points

| Command    | Perplexity Model    | Typical Time | Approx. Cost  |
| ---------- | ------------------- | ------------ | ------------- |
| `search`   | sonar               | 2–10 seconds | ~$0.006/query |
| `research` | sonar-deep-research | 2–4 minutes  | ~$0.24/query  |

Both commands share the same query format, flags, configuration, and output structure. The only difference is which Perplexity model is called.

### Query Input

The first positional argument is the query. It can be either:

- **Inline text:** `search "What are the latest developments in MLX?"`
- **Path to a query file:** `search query.md`

If the argument is a path to an existing file, the file's contents are read as the query text. Otherwise the argument is treated as inline text. Query files are plain text or markdown — no frontmatter parsing is performed on input files.

## Requirements

1. Python 3.12 using `uv` as the package manager.
2. **httpx** for HTTP requests to the Perplexity API.
3. `PERPLEXITY_API_KEY` stored in `.env` or system environment. Loaded via `load_dotenv()`.
4. No SQLite state — the tool is stateless; each query always runs.
5. No `auth` subcommand — authentication is handled entirely by the API key in the environment. No OAuth flow is needed.
6. A changelog is maintained in `files/tools/research/CHANGELOG.md`.

## Design Notes

- **Two commands, one package:** `search` and `research` are separate `pyproject.toml` entry points that both route into `cli.py`. Each sets the Perplexity model internally — there is no `--mode` flag.
- **API endpoint:** Both commands use the Perplexity Chat Completions endpoint (`POST https://api.perplexity.ai/chat/completions`), which follows the OpenAI-compatible format. The request sends `messages` (system + user) and receives `choices[0].message.content` as the answer. The `search_results` array and `usage.cost` object are included in the response metadata.
- **Stateless by design:** Research results are always fresh. No deduplication or skip logic. No `--force` flag is needed because there is no cached state to clear.
- **Context flag:** `--context PATH` reads one or more prior research `.md` files and includes their content in the query, enabling informed follow-up questions without re-asking what was already covered.
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
| `QUERY` (positional)                       | Research question as inline text, or path to a query file (required)          |
| `--output PATH`                            | Output directory override                                                     |
| `--config PATH`                            | YAML configuration file (default: `src/config/research-configuration.yaml`)   |
| `--context PATH`                           | Prior research file(s) to include as context (repeatable)                     |
| `--domains TEXT`                           | Comma-separated domains to filter search (max 20; prefix with `-` to exclude) |
| `--recency [hour\|day\|week\|month\|year]` | Filter results by recency                                                     |
| `--rate-limit INT`                         | Max requests per minute (default from config)                                 |
| `--dry-run`                                | Show query that would be sent without calling API                             |
| `--verbose`, `-v`                          | Detailed logging                                                              |
| `--save-config PATH`                       | Generate example config and exit                                              |
| `--version`                                | Show version and exit                                                         |

### Subcommands

Each entry point has the same subcommands:

| Subcommand | Description                                                                                                                         |
| ---------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| `config`   | Validate and display current YAML configuration                                                                                     |
| `init`     | Create data directories (`data/research/`, `data/research/export/`) and generate a starter `research-configuration.yaml` if missing |

### Usage Examples

```bash
# Quick search with inline query
search "What are the latest developments in MLX?"

# Deep research with inline query
research "Compare MLX vs PyTorch performance on Apple Silicon"

# Search using a query file
search queries/mlx-question.md

# Deep research with context from prior search results
research "What are the performance implications?" --context data/research/export/2026-03-23_mlx-developments.md

# Search with domain filtering
search "site reliability engineering best practices" --domains google.com,aws.amazon.com

# Dry run to preview query
search "test query" --dry-run
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
├── models.py                    # ResearchResult and Source dataclasses
├── researcher.py                # Perplexity API client and query logic
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
rate_limit_rpm: 20
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

- `rate_limit_rpm` must be > 0
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
domains: []
context_files: []
cost_usd: 0.006
processed_date: 2026-03-18T10:00:00Z
---
```

Only include metadata fields with non-null, non-empty values in the frontmatter. The `context_files` field records which prior research files were passed via `--context` for traceability.

### Content Structure

```markdown
# What are the latest developments in MLX on Apple Silicon?

## Answer

Synthesized answer from multiple sources...

## Sources

1. [Source Title](https://example.com/article) — excerpt
2. [Another Source](https://another.com/post) — excerpt

## Related Questions

- How does MLX compare to PyTorch on Apple Silicon?
- What models are currently supported by MLX?
```

## Error Handling

- `Perplexity API errors` (auth, rate limits, content filtering) — caught per-query; logs the error with the query text and exits with code 1.
- `Perplexity API rate limit / transient errors` (HTTP 429, 500, 503) — retried with exponential backoff up to `retry_max_attempts` (default 3). Initial delay is `retry_base_delay_seconds`, doubling on each retry. Permanent failures (4xx other than 429) are not retried.
- `Context file loading errors` — caught per context file specified with `--context`; logs the offending path and aborts before calling the API.
- `Query file loading errors` — if the positional argument looks like a file path but the file does not exist, exit with code 1 and a descriptive message.
- Missing config file raises `FileNotFoundError`. Invalid config content raises `ValueError`. Missing required env vars (e.g., `PERPLEXITY_API_KEY`) raise `OSError`.
- Top-level `try/except` in CLI entry point catches all above and prints descriptive messages.
- Exit codes: `0` success, `1` fatal error

Note: Exit code `2` (partial failure) is not used because each command processes a single query per invocation. If batch/multi-query support is added in the future, exit code `2` should be introduced for partial failures.

## Testing

- Mock target: **httpx** — mock at the transport layer to return fixture JSON responses without real network calls.
- Test fixtures: mock Perplexity API response JSON covering search, deep research, and error responses.
- Test both entry points (`search_main`, `research_main`) to verify correct model selection.
- Test query input from inline text and from file paths.
- Test classes organized by feature area: query construction, query file loading, context file loading, output formatting, config validation, retry logic.
- Mark slow or network-dependent tests with `@pytest.mark.slow` and `@pytest.mark.integration`.
- Mark error path tests with `@pytest.mark.error_handling`.
- Write docstrings on every test method.
- Test directory: `tests/research/` with `conftest.py` for shared fixtures
- Fixture data files stored in `tests/research/fixtures/`

## User Questions

_(None yet — record questions raised during requirements gathering and their answers here.)_

## Claude Questions

1. **Stdout output for quick searches** — For `search "quick question"`, should the answer be printed to stdout in addition to writing the file? Currently you'd have to open the exported file to see results. A `--stdout` flag or default stdout behavior for `search` would improve the quick-lookup UX.
2. **Streaming for deep research** — `research` queries take 2–4 minutes. The API supports SSE streaming. Should the `research` command stream progress to stderr while building the final output file? This would avoid a silent multi-minute wait.
3. **Entry point name collision** — `search` is a generic name that could collide with other packages or user scripts. Alternatives like `websearch` or `pplx-search` would be safer but less ergonomic. Is the collision risk acceptable?
4. **`--rate-limit` flag usefulness** — For a single-query stateless tool, a per-minute rate limit CLI flag has limited value (it only matters if running the command in a loop). Consider removing the flag and keeping the config-only setting.
5. **Subcommand duplication** — `search init`, `search config`, `research init`, `research config` are identical. Should `init` and `config` live on only one entry point to reduce duplication, or is having them on both preferable for discoverability?
6. **How `--context` is sent to the API** — The spec says context files are "included in the query" but doesn't specify the mechanics. Options: (a) prepend context to the user message, (b) send context as a system message, (c) send context as separate user messages. This affects token usage, cost, and model behavior.
7. **Query file detection ambiguity** — If someone runs `search "README.md"` and a file named `README.md` exists in the current directory, the tool reads the file instead of searching for the literal text "README.md". Should this be documented as a known behavior, or should a `--file` flag be added to make file input explicit?
8. **Async mode for deep research** — Perplexity offers an async endpoint (`POST /async/chat/completions`) where you submit a job and poll for results (retained 7 days). This may be more reliable than a synchronous 2–4 minute HTTP request. Should `research` use the async endpoint instead of (or as a fallback for) synchronous requests?

## Pre-Build Tasks

1. Obtain a Perplexity API key from [perplexity.ai](https://docs.perplexity.ai/)
2. Add `PERPLEXITY_API_KEY` to `.env`
3. Verify `.gitignore` covers `data/research/`
4. Add `httpx` to project dependencies in `pyproject.toml` if not already present
