# Changelog — Web Tool

## [Unreleased]

### Added

- `strip_boilerplate` config option: list of regex patterns to remove from converted markdown before saving (applied after HTML→markdown conversion, before word counting)
- `llms_lookback_days` config option: controls how many days of history to include in `llms-full.txt` and `llms.txt` (default: 30, set to 0 for current-run-only behavior)
- `strip_path_prefix` config option: strips a URL path prefix from output file paths (e.g., `/docs/en` → files written without that prefix)
- `strip_domain` config option: omits the domain directory from output file paths

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
