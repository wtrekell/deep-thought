# GCal Tool — Changelog

## [Unreleased]

### Changed

- Secret retrieval now checks macOS Keychain first, falling back to environment variables. Uses the shared `deep_thought.secrets` module.
- OAuth token storage now uses macOS Keychain (primary) with file fallback, including auto-migration from file to Keychain on first run.
- Google OAuth token is now shared across gmail, gcal, and gdrive — one auth flow covers all three tools. Token stored under `deep-thought-google` keychain entry with combined Gmail + Calendar + Drive scopes.

## 0.1.2 — 2026-04-02

### Changed

- Attendees in exported frontmatter are now rendered as a proper YAML list (`- email: ...` / `display_name: ...`) instead of a JSON-encoded string. `display_name` is omitted when the Calendar API returns no display name for the attendee.
- `_build_api_event_body` (create) and `_diff_event_fields` (update) now filter attendees through `_validate_attendee_emails` before sending to the API. Invalid entries (missing `@` or `.`) are dropped with a warning log.

### Fixed

- Token file `chmod(0o600)` was already applied after write — confirmed present and covered by `test_saves_token_with_restricted_permissions`.

## 0.1.1 — 2026-03-30

### Changed

- Standardized export filename date prefix from `YYYY-MM-DD_` to `YYMMDD-` (e.g., `260324-team-standup.md`).

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
