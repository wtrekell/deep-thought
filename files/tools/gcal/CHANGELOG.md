# GCal Tool — Changelog

## 0.1.0 — 2026-03-23

### Added

- Initial implementation of the GCal tool.
- Pull events from configured Google Calendars into SQLite and export as LLM-optimized markdown.
- Incremental sync via Calendar API sync tokens (when `single_events: false`).
- Create events from markdown files with YAML frontmatter.
- Update existing events from modified markdown files.
- Delete events by ID with local cleanup.
- OAuth 2.0 Desktop app flow (shared credentials with Gmail tool, separate token).
- CLI with subcommands: `init`, `config`, `auth`, `create`, `update`, `delete`.
- YAML configuration with calendar selection, time window, and output options.
- Flat and calendar-organized output directory modes.
- `.llms.txt` / `.llms-full.txt` generation support.
- Full test suite with in-memory SQLite and mocked Google API.
