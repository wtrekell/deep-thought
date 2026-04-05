# Product Brief — Web Tool

## Name and Purpose

**Web Tool** — crawls web pages and converts them to LLM-optimized markdown using Playwright for JavaScript rendering. Supports three crawl modes, stealth configuration, URL filtering, image extraction, and batch operation via auto-discovered config files.

## Crawl Modes

1. **CLI Command** — `web` (entry point)
2. **Documentation mode** — crawls a site hierarchically from a root URL, following internal links up to a configurable depth; output mirrors site structure
3. **Blog mode** — fetches a flat list of URLs from a blog/article listing page; output is a single directory per post
4. **Direct mode** — fetches a specific list of URLs provided in a text file; no link-following
5. **Batch mode** — auto-discovers all `src/config/web/*.yaml` files and runs each in sequence

## Requirements

1. Python 3.12 using `uv` as the package manager.
2. **Playwright** (`playwright` + Chromium browser) for JavaScript rendering.
3. **html2text** or equivalent for HTML-to-markdown conversion.
4. SQLite for local state tracking (WAL mode, foreign keys enabled).
5. No API keys required — fully local processing.
6. A changelog is maintained in `files/tools/web/CHANGELOG.md`.

## Data Storage

### State Database

Located at `data/web/web.db` by default; respects the `DEEP_THOUGHT_DATA_DIR` env var to redirect the data root at runtime.

- Table: `crawled_pages` — columns: `url TEXT PRIMARY KEY`, `rule_name TEXT`, `title TEXT`, `status_code INT`, `word_count INT`, `output_path TEXT`, `status TEXT`, `created_at TEXT`, `updated_at TEXT`, `synced_at TEXT`
- State key: URL
- Incremental: on subsequent runs, already-crawled URLs are skipped unless `--force`
- Schema version tracked in a `web_schema_version` table
- Migrations stored in `db/migrations/` with numeric prefixes (e.g., `001_init_schema.sql`)

## Data Models

### CrawledPageLocal

Local dataclass representing a crawled page result.

| Field         | Type          | Description                            |
| ------------- | ------------- | -------------------------------------- |
| `url`         | `str`         | Page URL (primary key)                 |
| `rule_name`   | `str \| None` | Batch config rule that triggered crawl |
| `title`       | `str \| None` | Extracted page title                   |
| `status_code` | `int`         | HTTP response status                   |
| `word_count`  | `int`         | Word count of converted markdown       |
| `output_path` | `str`         | Relative path to output file           |
| `status`      | `str`         | `success`, `error`, `skipped`          |
| `created_at`  | `str`         | ISO 8601 timestamp                     |
| `updated_at`  | `str`         | ISO 8601 timestamp                     |
| `synced_at`   | `str`         | ISO 8601 timestamp                     |

Methods: `to_dict()` for database insertion.

## Command List

Running `web` with no arguments shows help. Crawling is the default operation — no subcommand required.

| Subcommand   | Description                                                              |
| ------------ | ------------------------------------------------------------------------ |
| `web crawl`  | Crawl web pages and convert to markdown (same as running `web` directly) |
| `web config` | Validate and display current YAML configuration                          |
| `web init`   | Scaffold configs, output directories, and database                       |

| Flag                                   | Description                                                                          |
| -------------------------------------- | ------------------------------------------------------------------------------------ |
| `--input URL`                          | Root URL for documentation/blog mode                                                 |
| `--input-file PATH`                    | Text file of URLs, one per line (direct mode)                                        |
| `--mode [documentation\|blog\|direct]` | Crawl mode (default: `blog`)                                                         |
| `--output PATH`                        | Output directory (default: `output/web/` for blog/direct, `docs/` for documentation) |
| `--config PATH`                        | Override default config file path                                                    |
| `--max-depth INT`                      | Max link-following depth (documentation mode; default: 3)                            |
| `--max-pages INT`                      | Max pages per run (default: 100)                                                     |
| `--js-wait FLOAT`                      | Seconds to wait for JS to render (default: 1.0)                                      |
| `--browser-channel TEXT`               | Chromium channel for WAF bypass (e.g., `chrome`)                                     |
| `--stealth`                            | Randomize user-agent, viewport, and inter-request delays                             |
| `--include-pattern REGEX`              | Only crawl URLs matching this pattern (repeatable)                                   |
| `--exclude-pattern REGEX`              | Skip URLs matching this pattern (repeatable)                                         |
| `--retry-attempts INT`                 | Max retries per URL (default: 2)                                                     |
| `--retry-delay FLOAT`                  | Seconds between retries (default: 5.0)                                               |
| `--extract-images`                     | Extract images found on crawled pages                                                |
| `--batch`                              | Auto-discover and run all `src/config/web/*.yaml`                                    |
| `--dry-run`                            | Preview without fetching                                                             |
| `--verbose`, `-v`                      | Detailed logging                                                                     |
| `--force`                              | Clear state and recrawl                                                              |
| `--save-config PATH`                   | Generate example config and exit                                                     |
| `--version`                            | Show version and exit                                                                |

## File & Output Map

```
files/tools/web/
├── 260322-requirements.md       # This document
├── CHANGELOG.md                 # Release history
└── ISSUES.md                    # Open issues tracker

src/config/
├── web-configuration.yaml       # Tool configuration
├── examples/
│   └── web-example.yaml         # Fully documented example config
└── web/                         # Batch mode config files
    ├── blog.yaml
    ├── docs.yaml
    ├── docs-site.yaml
    └── templates/
        ├── blog-template.yaml   # Starting point template for blog sites
        └── docs-template.yaml   # Starting point template for documentation sites

src/deep_thought/web/
├── __init__.py
├── cli.py                       # CLI entry point and argument parsing
├── config.py                    # YAML config loader and validation
├── models.py                    # Local dataclasses for crawl results
├── processor.py                 # Crawl orchestration and output
├── filters.py                   # URL include/exclude regex filtering
├── output.py                    # Markdown + YAML frontmatter generation
├── llms.py                      # .llms.txt / .llms-full.txt generation
├── image_extractor.py           # Image URL extraction and download
├── crawler.py                   # Playwright-based page fetching
├── converter.py                 # HTML → markdown conversion
├── default-config.yaml          # Bundled default configuration
└── db/
    ├── __init__.py
    ├── schema.py                # Table creation and migration runner
    ├── queries.py               # All SQL operations
    └── migrations/
        └── 001_init_schema.sql  # Initial schema

data/web/
└── web.db                       # SQLite state database

output/web/                      # Blog/direct mode markdown output
docs/                            # Documentation mode markdown output

```

## Configuration

Configuration is stored in `src/config/web-configuration.yaml`. All values below are required unless marked optional.

```yaml
# Crawl behavior
mode: "blog" # 'blog', 'documentation', or 'direct'
max_depth: 3
max_pages: 100

# Rendering
js_wait: 1.0 # Seconds to wait after page load
browser_channel: null # e.g., 'chrome' to bypass WAF fingerprinting

# Browser
headless: true # Run the browser without a visible window
stealth: false # Randomize user-agent, viewport, delays

# Index structure
index_depth: 1 # Levels of listing/nav pages before article content
min_article_words: 200 # Pages below this word count are treated as index pages
changelog_url: null # Documentation mode only: URL of changelog for incremental re-crawls

# URL filtering
include_patterns: [] # Only crawl URLs matching these regexes
exclude_patterns: # Skip URLs matching these regexes
  - '.*\.pdf$'
  - ".*login.*"

# Content stripping
strip_boilerplate: [] # Regex patterns to remove from converted markdown (e.g., nav menus, footers)

# Retry
retry_attempts: 2
retry_delay: 5.0

# Output — blog/direct default: "output/web/", documentation default: "docs/"
output_dir: "output/web/"
strip_path_prefix: null # Strip this URL path prefix from output file paths
strip_domain: false # Omit the domain directory from output file paths
extract_images: false
generate_llms_files: true
llms_lookback_days: 30 # Days of history to include in llms.txt / llms-full.txt (0 = current run only)
```

## Data Format

### Markdown Output

Blog and direct modes write to `output/web/` by default. Documentation mode writes to `docs/` by default.

```
output/web/{domain}/{path}/          # Blog/direct mode
├── {page_title}.md
└── img/

docs/{domain}/{path}/                # Documentation mode
├── {page_title}.md
└── img/
```

Documentation mode mirrors the site hierarchy. Blog and direct modes use a flat directory.

### Frontmatter Schema

```markdown
---
tool: web
url: https://docs.example.com/guide/intro
mode: documentation
title: "Introduction"
word_count: 1240
processed_date: 2026-03-18T10:00:00Z
---
```

### llms-full.txt (generate_llms_files only)

One file in the export root. When `llms_lookback_days > 0` (default: 30), includes all successfully crawled pages from the database within that time window — not just pages from the current run. Set to `0` for current-run-only behavior. Each page is separated by a delimiter block:

```
# {Page Title}

url: https://docs.example.com/guide/intro
mode: documentation
crawled: 2026-03-18T10:00:00Z

{full markdown content, frontmatter stripped}

---

# {Next Page}
...
```

### llms.txt (generate_llms_files only)

Index file in the export root, following the llmstxt.org convention:

```
# Page Index

> Crawled by web on 2026-03-18. {N} pages.

## Pages

- [{page_title}.md]({domain}/{path}/{page_title}.md): {url}, {word_count} words
- [{page_title}.md]({domain}/{path}/{page_title}.md): {url}, {word_count} words
```

## Error Handling

- `FileNotFoundError` — missing config file or input file (direct mode)
- `OSError` — missing environment variables (e.g., `DEEP_THOUGHT_DATA_DIR` set but path invalid)
- `ValueError` — invalid configuration content (bad regex patterns, unknown mode)
- `PlaywrightError` — browser launch failures, navigation timeouts; caught and logged per-URL with retry
- `ConnectionError` — network failures; caught per-URL with retry, logged with URL context
- Top-level `try/except` in CLI entry point catches all above and prints descriptive messages
- Per-URL errors do not halt the crawl; failed URLs are recorded with `status: error` in the database
- Exit codes: `0` all pages succeeded, `1` fatal error, `2` partial failure (some pages errored)

## Testing

- Use in-memory SQLite for database tests
- Mock Playwright browser context and page objects with `MagicMock`
- Provide fixture HTML pages for converter tests
- Organize tests in classes by feature area (crawling, filtering, conversion, output, CLI)
- Write docstrings on every test method
- Test markers: `slow` (full browser tests), `integration` (real network), `error_handling`
- Test directory: `tests/web/` with `conftest.py` for shared fixtures
- Fixture data files stored in `tests/web/fixtures/`
