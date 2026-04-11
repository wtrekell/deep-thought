# Gmail Tool — Changelog

## Unreleased

### Changed

- Replaced per-rule `save_local` (bool) and `append_mode` (bool) fields with a single `save_mode` string field. Valid values: `individual` (default, one file per email), `append` (single combined file per rule), `both` (individual files + combined file), `none` (no files written). Old fields still work with a deprecation warning (#32).

### Fixed

- Global `gmail` entry point failed with `No module named 'keyring'` when the uv tool environment was stale. Resolved by reinstalling the global tool environment (#28).
- Migrated Gemini AI extraction from deprecated `google-generativeai` SDK to `google-genai`. Client initialization and generation call updated in `extractor.py`.
- Added service initialization guard to `client._execute()`: calling any API method before `authenticate()` now raises `RuntimeError("Must call authenticate() before making API requests.")` instead of a cryptic `AttributeError`.

### Changed

- Secret retrieval now checks macOS Keychain first, falling back to environment variables. Uses the shared `deep_thought.secrets` module.
- OAuth token storage now uses macOS Keychain (primary) with file fallback, including auto-migration from file to Keychain on first run.
- Google OAuth token is now shared across gmail, gcal, and gdrive — one auth flow covers all three tools. Token stored under `deep-thought-google` keychain entry with combined Gmail + Calendar + Drive scopes.
- Standardized export filename date prefix from `YYYY-MM-DD_` to `YYMMDD-` (e.g., `260330-weekly-digest.md`).

### Added

- Per-rule `save_local` option (default `true`). Set to `false` to skip local markdown output for action-only rules like forwarding (#29).
- Qdrant vector store integration. Collected emails are embedded into the shared `deep_thought_db` collection for semantic search. Configure via `qdrant_collection` in config. Embedding failures are non-fatal (#30).
- Initial release: collect, send, auth commands
- Rule-based email collection with Gmail search queries
- Gemini AI extraction with decision caching
- Newsletter HTML cleaning
- Post-collection actions: archive, label, forward, mark_read, trash, delete
- OAuth 2.0 Desktop app flow
- Append mode for aggregating emails per rule
- Markdown output with YAML frontmatter
- SQLite state tracking
