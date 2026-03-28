# Web Tool

Crawls web pages and converts them to LLM-optimized markdown using Playwright for JavaScript rendering. Supports three crawl modes, stealth configuration, URL filtering, image extraction, and batch operation via auto-discovered config files.

## Quick Start

```bash
# Scaffold configs, output directories, and database
web init

# Copy a batch config and edit for your site
cp src/config/web/blog.yaml src/config/web/my-site.yaml
# Edit input_url and patterns in the new config file

# Run all configs at once
web crawl --batch
```

## Commands

### `web crawl` — Fetch pages and convert to markdown

```bash
web crawl --input URL [flags]
web crawl --input-file PATH [flags]
web crawl --batch [flags]
```

Running `web` with no arguments also triggers a crawl (same as `web crawl`).

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
| `--save-config PATH`                   | Save resolved configuration to a YAML file and exit                                  |
| `--version`                            | Show version and exit                                                                |

### `web config` — Validate and display configuration

```bash
web config [--config PATH]
```

Prints all resolved settings and any validation warnings.

### `web init` — Scaffold the web tool workspace

```bash
web init [--save-config PATH]
```

Sets up everything needed for first use:

1. Writes the default configuration to `src/config/web-configuration.yaml`
2. Copies starter batch configs from templates to `src/config/web/`
3. Creates output directories: `output/web/` and `docs/`
4. Initializes the database at `data/web/web.db`

Safe to re-run — existing files are never overwritten.

## Crawl Modes

| Mode            | Behavior                                                                                                                                                                 |
| --------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `blog`          | Fetches a root URL, follows listing links `index_depth` levels deep, then captures articles. Typical: depth=1 (root → articles), depth=2 (root → categories → articles). |
| `documentation` | BFS link-following from a root URL up to `max_depth`. Optional `changelog_url` enables incremental re-crawls — only pages linked from the changelog are re-fetched.      |
| `direct`        | Fetches a specific list of URLs from a text file; no link-following.                                                                                                     |
| `batch`         | Auto-discovers all `src/config/web/*.yaml` files and runs each in sequence.                                                                                              |

## Configuration

Default config file: `src/config/web-configuration.yaml`

```yaml
# Crawl behavior
mode: "blog"
max_depth: 3
max_pages: 100

# Rendering
js_wait: 1.0
browser_channel: null # e.g., 'chrome' to bypass WAF fingerprinting

# Browser
headless: true # Run the browser without a visible window
stealth: false # Randomize user-agent, viewport, delays

# Index structure
index_depth: 1 # Levels of listing/nav pages before article content
min_article_words: 200 # Pages below this word count are treated as index pages
changelog_url: null # Documentation mode only: URL of changelog for incremental re-crawls

# URL filtering
include_patterns: []
exclude_patterns:
  - '.*\.pdf$'
  - ".*login.*"

# Content stripping
strip_boilerplate: [] # Regex patterns to remove from converted markdown

# Retry
retry_attempts: 2
retry_delay: 5.0

# Output — blog/direct default: "output/web/", documentation default: "docs/"
output_dir: "output/web/"
extract_images: false
generate_llms_files: true
llms_lookback_days: 30 # 0 = current run only, N = include pages from last N days
strip_path_prefix: null # Strip this URL path prefix from output file paths
strip_domain: false # Omit the domain directory from output file paths
```

### Per-site batch configs

Place YAML files in `src/config/web/` for use with `--batch`. Each file is one crawl rule. `web init` copies starter configs from the templates in `src/config/web/templates/`:

- `blog-template.yaml` — for blog/article sites (copied as `blog.yaml`)
- `docs-template.yaml` — for documentation sites with optional changelog awareness (copied as `docs.yaml`)

### Key config fields

**`index_depth`** — how many levels of navigation/listing pages the crawler must traverse before reaching article content. Set this manually based on the site structure.

- `1` — root URL links directly to articles (most blogs)
- `2` — root → category pages → articles
- `3` — root → section → category → articles

**`min_article_words`** — pages below this word count are treated as index pages and skipped (not written to disk, not included in LLM files). Prevents navigation pages from polluting the export.

**`changelog_url`** — documentation mode only. If set, subsequent runs fetch this URL first and only re-crawl pages linked from it. Pages not mentioned in the changelog are skipped. Set to `null` to force a full re-crawl.

**`headless`** — when `true` (default), runs the browser without a visible window. Set to `false` to show the browser window during crawling, which can help with debugging or sites that detect headless browsers.

**`stealth`** — when `true`, randomizes the user-agent string, browser viewport, and inter-request delays to reduce the chance of bot detection. Can be set in the YAML config so it applies automatically without passing `--stealth` on every run.

**`llms_lookback_days`** — controls how much history is included in `llms-full.txt` and `llms.txt`. Set to `30` (default) to include all successfully crawled pages from the last 30 days, regardless of whether they were fetched in the current run. Set to `0` to only include pages from the current run.

**`strip_path_prefix`** — removes a URL path prefix when computing output file paths. For example, setting `strip_path_prefix: "/docs/en"` turns `https://example.com/docs/en/guide/setup` into `example.com/guide/setup.md` instead of `example.com/docs/en/guide/setup.md`.

**`strip_domain`** — when `true`, omits the domain directory from output file paths. For example, `example.com/guide/setup.md` becomes `guide/setup.md`.

**`strip_boilerplate`** — a list of regex patterns applied to the converted markdown before saving. Matches are removed before word counting, so boilerplate text (nav menus, cookie banners, "Subscribe" blocks, footer links) doesn't inflate word counts or trigger the `min_article_words` quality gate. Patterns use `re.DOTALL`, so `.` matches newlines for multi-line blocks. Use `[^\n]*` instead of `.*` to match within a single line only.

## Output

Blog and direct modes write to `output/web/` by default. Documentation mode writes to `docs/` by default.

```
output/web/{domain}/{path}/          # Blog/direct mode
├── {page_title}.md
└── img/

docs/{domain}/{path}/                # Documentation mode
├── {page_title}.md
└── img/
```

Blog and direct modes use a flat directory. Documentation mode mirrors the site hierarchy.

### Frontmatter

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

### LLM files (generate_llms_files: true)

Two files are written to the export root per run:

- **`llms-full.txt`** — all page content concatenated, frontmatter stripped, separated by `---` delimiters
- **`llms.txt`** — index of all pages with URLs and word counts, following the [llmstxt.org](https://llmstxt.org) convention

When `llms_lookback_days` is set to a value greater than 0 (default: 30), these files include all successfully crawled pages from the database within that time window — not just pages fetched in the current run. Pages from the current run take precedence over historical versions when the same URL appears in both. Set to `0` to only include pages from the current run.

## State Database

Located at `data/web/web.db`. Uses SQLite WAL mode. Tracks crawled URLs so subsequent runs skip already-processed pages unless `--force` is passed.

Override the data directory with the `DEEP_THOUGHT_DATA_DIR` environment variable.

## Error Handling

Per-URL errors do not halt the crawl — failed URLs are recorded with `status: error` and the run continues.

Exit codes: `0` all pages succeeded, `1` fatal error, `2` partial failure (some pages errored).

## Requirements

- Python 3.12, `uv` as the package manager
- Playwright + Chromium (`playwright install chromium` after install)
- No API keys required
