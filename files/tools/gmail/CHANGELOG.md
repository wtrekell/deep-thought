# Gmail Tool — Changelog

## Unreleased

### Changed

- Standardized export filename date prefix from `YYYY-MM-DD_` to `YYMMDD-` (e.g., `260330-weekly-digest.md`).

### Added

- Initial release: collect, send, auth commands
- Rule-based email collection with Gmail search queries
- Gemini AI extraction with decision caching
- Newsletter HTML cleaning
- Post-collection actions: archive, label, forward, mark_read, trash, delete
- OAuth 2.0 Desktop app flow
- Append mode for aggregating emails per rule
- Markdown output with YAML frontmatter
- SQLite state tracking
