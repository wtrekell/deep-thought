# Changelog — Web Tool

## [0.3.0] — 2026-04-06

### Added

- `inherits` field for batch configs. Set `inherits: "_base-filename.yaml"` in
  any batch config to load shared settings from a base file in the same
  directory. List fields (`include_patterns`, `exclude_patterns`,
  `strip_boilerplate`, `unwrap_tags`) are concatenated parent-first; all other
  fields use last-write-wins (child overrides parent).

### Changed

- Batch auto-discovery now skips YAML files with a `_` prefix. Place base
  config files in `src/config/web/` using a `_` name (e.g. `_base-docs.yaml`)
  to prevent them from being executed as standalone crawl configs.

## [0.2.0] — 2026-04-05

### Added

- `qdrant_collection` config option: name of the Qdrant collection to write embeddings to (default: `"deep_thought_db"`). Can be set in `web-configuration.yaml` for all crawls or overridden per batch config in `src/config/web/`, enabling separate corpora for different sites or consumers.

- JS pagination support for index/listing pages: new `pagination` config option (`"none"` / `"scroll"` / `"click"`) controls how the crawler expands JS-rendered content before extracting article links; scroll mode scrolls to the page bottom and waits for height growth up to `max_paginations` iterations; click mode clicks the element matching `pagination_selector` until it disappears or `max_paginations` is reached; errors in individual pagination steps log a warning and return the HTML accumulated so far rather than crashing; pagination applies only to index pages, not individual article pages
- `pagination_selector` config option: CSS selector string for the "load more" button (required when `pagination` is `"click"`)
- `pagination_wait` config option: seconds to wait after each scroll or click before checking for new content (default: `2.0`)
- `max_paginations` config option: maximum number of scroll/click iterations per index page (default: `10`)
- `unwrap_tags` config option: list of `tag.class` patterns (e.g. `div.word`) to strip wrapper tags from HTML while preserving their text content — applied before HTML→markdown conversion; solves sites that wrap every word in animation divs (e.g. `claude.com/blog`); matching is case-insensitive and works with both single- and double-quoted class attributes; invalid HTML tag names in patterns are caught by `validate_config()`; excess newlines left after unwrapping are collapsed (same normalization as `strip_boilerplate`)
- `strip_boilerplate` config option: list of regex patterns to remove from converted markdown before saving (applied after HTML→markdown conversion, before word counting)
- `llms_lookback_days` config option: controls how many days of history to include in `llms-full.txt` and `llms.txt` (default: 30, set to 0 for current-run-only behavior)
- `strip_path_prefix` config option: strips a URL path prefix from output file paths (e.g., `/docs/en` → files written without that prefix)
- `strip_domain` config option: omits the domain directory from output file paths

### Fixed

- Added `_check_playwright_driver()` pre-flight check to `cmd_crawl()` — detects when `env.js` is missing from the Playwright bundled driver (a known `uv sync` install issue) and exits immediately with a clear error and the fix command (`uv pip install --reinstall playwright`) instead of the cryptic `Cannot find module './env'` Node.js error.
- BFS graph broken on incremental re-crawls: when a cached page was skipped, its child links were never discovered, silently truncating the crawl tree at that node. Fixed by storing extracted child links as JSON in a new `child_links` column (migration `002_add_child_links.sql`) and implementing `_enqueue_children_from_db()` to re-enqueue them on cache hits without re-fetching the page. Pre-migration rows (`child_links` is `NULL`) are silently skipped at DEBUG level.

### Changed

- `web init` now scaffolds the full workspace: copies default config, creates starter batch configs from templates, creates both output directories (`output/web/` and `docs/`), and initializes the database
- Default output directories: `output/web/` for blog/direct modes, `docs/` for documentation mode (was `data/web/export/` for all)
- `headless` config option: controls whether the browser runs with or without a visible window (default: `true`)
- Browser always launches headless by default (was headed in stealth mode); works on headless servers without a display

### Removed

- Removed `web setup` subcommand (site analysis and config generation)

## [0.1.0] — Initial Release

### Added

- Blog, documentation, and direct crawl modes
- Playwright-based JavaScript rendering with configurable wait times
- HTML to markdown conversion via html2text
- SQLite state tracking with WAL mode for incremental crawling
- llms.txt and llms-full.txt aggregate file generation
- URL include/exclude regex filtering
- Stealth mode with user-agent and viewport randomization
- Image extraction and download with size limits
- Batch mode via auto-discovered YAML configs in `src/config/web/`
- `web crawl`, `web config`, and `web init` subcommands
- Cloudflare challenge detection and wait logic
- Per-URL error isolation (failed URLs don't halt the crawl)
- Index depth configuration for multi-level blog/listing sites
- Minimum article word count quality gate
- Documentation mode changelog-based incremental re-crawling
