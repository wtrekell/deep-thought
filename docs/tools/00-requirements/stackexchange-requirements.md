# Product Brief — Stack Exchange Tool

## Name and Purpose

**Stack Exchange Tool** — collects Q&A threads from 200+ Stack Exchange sites via the Stack Exchange API v2.3. Tag-based discovery fetches complete threads (question + answers + comments) and saves them as LLM-optimized markdown. Quota tracking prevents hitting daily API limits.

## Operations

1. **CLI Command** — `stackexchange` (entry point)
2. **Collect** — Fetch threads matching rule filters from configured sites (default operation)

## Requirements

1. Python 3.12 using `uv` as the package manager.
2. **httpx** for HTTP requests to the Stack Exchange API.
3. SQLite for local state tracking (WAL mode, foreign keys enabled).
4. `STACKEXCHANGE_API_KEY` in `.env` or system environment (optional; increases quota from 300 to 10,000 requests/day).
5. A changelog is maintained in `docs/tools/stackexchange/CHANGELOG.md`.

## Data Storage

### State Database

Located at `data/stackexchange/stackexchange.db` by default; respects the `DEEP_THOUGHT_DATA_DIR` env var to redirect the data root at runtime.

- Table: `collected_questions` — columns: `state_key TEXT PRIMARY KEY`, `question_id INT`, `site TEXT`, `rule_name TEXT`, `answer_count INT`, `output_path TEXT`, `status TEXT`, `created_at TEXT`, `updated_at TEXT`
- Table: `quota_usage` — columns: `date TEXT PRIMARY KEY`, `requests_used INT`, `quota_remaining INT`, `created_at TEXT`, `updated_at TEXT`
- **State key:** `{question_id}:{site}:{rule_name}`
- **Incremental updates:** A previously-collected question is re-processed when its live `answer_count` exceeds the stored value. Otherwise skipped unless `--force`.
- **Upsert pattern:** `INSERT ... ON CONFLICT(state_key) DO UPDATE SET` — `created_at` is explicitly excluded from the update clause to preserve the original collection timestamp.
- Schema version tracked in a `key_value` table
- Migrations stored in `db/migrations/` with numeric prefixes

## Data Models

### CollectedQuestionLocal

| Field | Type | Description |
| --- | --- | --- |
| `state_key` | `str` | Composite primary key: `{question_id}:{site}:{rule_name}` |
| `question_id` | `int` | Stack Exchange question ID |
| `site` | `str` | Stack Exchange site slug (e.g., `stackoverflow`) |
| `rule_name` | `str` | Name of the rule that collected this question |
| `title` | `str` | Question title |
| `link` | `str` | Canonical URL to the question on the SE site |
| `tags` | `str` | JSON-encoded list of tags (e.g., `["python", "asyncio"]`) |
| `score` | `int` | Question score at time of collection |
| `answer_count` | `int` | Number of answers at time of collection |
| `accepted_answer_id` | `int \| None` | ID of the accepted answer, if any |
| `output_path` | `str` | Path to the generated markdown file |
| `status` | `str` | Processing status (e.g., `ok`, `error`) |
| `created_at` | `str` | ISO 8601 timestamp of first collection |
| `updated_at` | `str` | ISO 8601 timestamp of last update |

Methods: `from_api()` for API response conversion, `to_dict()` for database insertion.

### QuotaUsageLocal

| Field | Type | Description |
| --- | --- | --- |
| `date` | `str` | Date of the quota record (primary key, `YYYY-MM-DD`) |
| `requests_used` | `int` | Number of API requests made on this date |
| `quota_remaining` | `int` | Remaining API quota for the day |
| `created_at` | `str` | ISO 8601 timestamp of record creation |
| `updated_at` | `str` | ISO 8601 timestamp of last update |

Methods: `from_api()` for API response conversion, `to_dict()` for database insertion.

## Command List

Running `stackexchange` with no arguments shows help. Collect is the default operation — no subcommand required. The collect handler calls `validate_config()` before any API work begins; validation failures exit with code 1.

| Subcommand | Description |
| --- | --- |
| `stackexchange config` | Validate and display current YAML configuration |
| `stackexchange init` | Create config file and directory structure |

| Flag | Description |
| --- | --- |
| `--config PATH` | YAML configuration file (default: `src/config/stackexchange-configuration.yaml`) |
| `--output PATH` | Output directory override |
| `--dry-run` | Preview without fetching |
| `--verbose`, `-v` | Detailed logging with quota tracking |
| `--rule NAME` | Run only the named rule |
| `--force` | Clear state and reprocess all |
| `--save-config PATH` | Generate example config and exit |
| `--version` | Show version and exit |

## File & Output Map

```
docs/tools/stackexchange/
├── CHANGELOG.md                 # Release history
└── ISSUES.md                    # Known issues

src/deep_thought/stackexchange/
├── __init__.py
├── cli.py                       # CLI entry point
├── default-config.yaml          # Bundled config template (source of truth for defaults)
├── config.py                    # YAML config loader, rule validation, path helpers
├── models.py                    # Local dataclasses for collection state
├── processor.py                 # Rule engine, thread fetching, output orchestration
├── db/
│   ├── __init__.py
│   ├── schema.py                # Table creation and migration runner
│   ├── queries.py               # All SQL operations (composite key aware)
│   └── migrations/
│       └── 001_init_schema.sql
├── filters.py                   # Score, age, keyword, answer-count filtering
├── output.py                    # Markdown + YAML frontmatter generation
├── llms.py                      # .llms.txt / .llms-full.txt generation
├── client.py                    # Stack Exchange API v2.3 client (thin httpx wrapper)
└── embeddings.py                # Per-tool embedding integration

data/stackexchange/
├── stackexchange.db             # SQLite state database
└── export/                      # Generated markdown files

src/config/
└── stackexchange-configuration.yaml  # Tool configuration and rules
```

## Configuration

### Config Path Helpers

`config.py` defines these module-level constants and public helpers per the standard pattern:

- `_PACKAGE_DIR = Path(__file__).resolve().parent` — resolves to the package directory (follows symlinks)
- `_BUNDLED_DEFAULT_CONFIG = _PACKAGE_DIR / "default-config.yaml"` — bundled template
- `_PROJECT_CONFIG_RELATIVE_PATH = Path("src") / "config" / "stackexchange-configuration.yaml"`
- `get_bundled_config_path() -> Path` — returns `_BUNDLED_DEFAULT_CONFIG` (for `init` and `--save-config`)
- `get_default_config_path() -> Path` — returns `Path.cwd() / _PROJECT_CONFIG_RELATIVE_PATH` (for all runtime commands)

The `init` subcommand copies the bundled `default-config.yaml` to the project-level location. All other commands read from the project-level config.

### Configuration File

Configuration is stored in `src/config/stackexchange-configuration.yaml`. All values below are required unless marked optional.

```yaml
# API
api_key_env: "STACKEXCHANGE_API_KEY"  # Optional; 300/day without, 10K/day with

# Collection
max_questions_per_run: 500           # Global cap across all rules

# Output
output_dir: 'data/stackexchange/export/'
generate_llms_files: true
qdrant_collection: "deep_thought_db"  # Optional; defaults to "deep_thought_db"

rules:
  - name: 'python_async'
    site: 'stackoverflow'          # Any Stack Exchange site slug
    tags:
      include: ['python', 'asyncio']  # AND: passed to API as semicolon-separated `tagged` param
      any: ['aiohttp', 'anyio']       # OR: client-side filter; question must have at least one
    sort: 'votes'                  # 'activity', 'votes', 'creation'
    order: 'desc'
    min_score: 10
    min_answers: 1
    only_answered: true
    max_age_days: 365
    keywords: ['async', 'await']   # Client-side post-fetch filter against body_markdown and title
    max_questions: 50
    max_answers_per_question: 5
    include_comments: true
    max_comments_per_question: 30

  - name: 'unix_shell'
    site: 'unix'
    tags:
      include: ['bash']
    sort: 'activity'
    min_score: 5
    max_questions: 25
    include_comments: true
    max_comments_per_question: 30
```

### Supported Sites (Sample)

`stackoverflow`, `serverfault`, `superuser`, `askubuntu`, `unix`, `math`, `physics`, `cooking`, `gaming` — and 200+ more. Use the site slug from the Stack Exchange URL.

## Data Format

### Markdown Output

```
data/stackexchange/export/{rule_name}/
├── {date}_{question_id}_{title_slug}.md
├── .llms.txt
└── .llms-full.txt
```

### Frontmatter Schema

```markdown
---
tool: stackexchange
state_key: 1234567:stackoverflow:python_async
question_id: 1234567
site: stackoverflow
rule: python_async
title: "How does asyncio event loop work?"
link: "https://stackoverflow.com/questions/1234567/how-does-asyncio-event-loop-work"
score: 342
answer_count: 8
accepted_answer: true
tags:
  - python
  - asyncio
  - event-loop
word_count: 2450
processed_date: 2026-03-18T10:00:00Z
---
```

### Content Structure

```markdown
# How does asyncio event loop work?

**Score:** 342 | **Answers:** 8 | **Tags:** python, asyncio, event-loop

## Question

Question body with code blocks preserved...

---

## ✓ Accepted Answer (↑ 287) — answered by username

Answer content...

## Answer (↑ 145) — answered by username2

Answer content...

### Comments

> **username3 (↑ 12):** Comment text here.
```

## API Client

`client.py` is a thin wrapper around `httpx` for the Stack Exchange API v2.3.

- Base URL: `https://api.stackexchange.com/2.3/`
- **Custom API filter:** A hardcoded filter string (created via the SE API filter editor) is passed on every request to include `body_markdown` on questions and answers, and `body` on comments. Without this filter, the API returns titles and metadata only — no content.
- Collapses paginated responses into flat lists, respecting `has_more` and batching IDs up to 100 per call (SE API limit)
- Passes the API key (if configured) as the `key` query parameter
- Keeps the client free of business logic — filtering, scoring, and output decisions live in `processor.py` and `filters.py`
- Stores the `httpx.Client` instance as a private attribute
- httpx handles gzip/deflate decompression natively; no additional configuration required
- Tracks `quota_remaining` from API response wrappers for quota management
- **Rate limiting:** 3 retries with exponential backoff (`10 * 2^attempt` seconds). The SE API `backoff` field in the response wrapper takes priority when present — the client must wait that many seconds before the next request.
- **Comment fetching:** Comments require separate API calls (`GET /questions/{ids}/comments`, `GET /answers/{ids}/comments`). These are only made when `include_comments` is enabled in the rule config.

## Type Safety

- Use `from __future__ import annotations` in all modules
- Use `TYPE_CHECKING` blocks for expensive imports (e.g., `httpx`)
- Annotate all function signatures (mypy strict mode)
- Use 120-character line length
- Prefix private functions with underscore
- Prefix module-level constants with underscore
- Suffix result types with `Result` (e.g., `CollectResult`)

## Error Handling

- `Stack Exchange API errors` (rate limits, quota exceeded, 404) — caught per-question; the question is skipped, the failure is logged with the state key, and collection continues. Quota-exceeded errors halt the run early and log remaining quota from `quota_usage`.
- `HTML-to-markdown conversion errors` — caught per-question during content rendering; raw HTML is written as a fallback and a warning is logged.
- Rule names are validated against `^[a-zA-Z0-9_-]+$` since they become directory names.
- Missing config file raises `FileNotFoundError`. Invalid config content raises `ValueError`. Missing required env vars raise `OSError`.
- Top-level `try/except` in CLI entry point catches all above and prints descriptive messages.
- Exit codes: `0` all items succeeded, `1` fatal error, `2` partial failure (some items errored)

## Testing

- Use in-memory SQLite for all database tests.
- Mock targets: `httpx` — use `MagicMock` or `respx` to mock HTTP responses from the Stack Exchange API.
- Test fixtures: sample API response JSON covering questions with accepted answers, questions with no answers, and partial quota responses.
- Organize tests in classes by feature area (collection, filtering, composite key logic, quota tracking, output).
- Mark slow or network-dependent tests with `@pytest.mark.integration`.
- Mark error path tests with `@pytest.mark.error_handling`.
- Write docstrings on every test method.
- Test directory: `tests/stackexchange/` with `conftest.py` for shared fixtures
- Fixture data files stored in `tests/stackexchange/fixtures/`

## Embeddings Integration

Questions and answers collected via Stack Exchange are written to the embedding store for semantic search.

- **When:** At collection time, immediately after markdown write
- **Content:** Question title, body text, and the accepted answer (if present)
- **Payload fields:**
  - `source_tool: "stackexchange"`
  - `source_type: "q_and_a"`
  - `rule_name` — which config rule collected this question
  - `collected_date` — ISO timestamp
  - `question_id`, `site` — for filtered queries
  - `output_path` — path to the markdown file on disk

**Error handling:** Embedding failure does not fail the collection run. The question is recorded as collected in the state DB; if embedding fails, it can be re-embedded in a repair run.
