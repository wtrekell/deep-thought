# Changelog — Web Tool

## [Unreleased]

### Changed

- `web init` now scaffolds the full workspace: copies default config, creates starter batch configs from templates, creates both output directories (`output/web/` and `docs/`), and initializes the database
- Default output directories: `output/web/` for blog/direct modes, `docs/` for documentation mode (was `data/web/export/` for all)

### Removed

- Removed `web setup` subcommand (site analysis and config generation)

### Added

- Initial implementation of the web crawl tool
- Blog, documentation, and direct crawl modes
- Playwright-based JavaScript rendering
- HTML to markdown conversion via html2text
- SQLite state tracking with WAL mode
- llms.txt and llms-full.txt generation
- URL include/exclude regex filtering
- Stealth mode with user-agent and viewport randomization
- Image extraction and download
- Batch mode via auto-discovered YAML configs
