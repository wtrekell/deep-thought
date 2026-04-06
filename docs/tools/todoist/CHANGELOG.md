# Changelog

All notable changes to the Todoist Tool will be documented in this file.

## 2026-04-05

### Added

- `todoist attach TASK_ID FILE_PATH` subcommand — uploads a local file to Todoist via the
  Sync API v9 and creates a comment with the attachment on the specified task. The new comment
  is written to the local SQLite database immediately so it appears in exports without a pull.
  Accepts `--message TEXT` (default: `"File attachment"`) and supports `--dry-run`.

### Fixed

- `comments.include_attachments` configuration flag was parsed and shown in `todoist config`
  output but never checked in any code path. It now controls whether attachment metadata
  (file name, MIME type, size in KB, and download URL) appears in exported markdown.
  Attachment data is always downloaded and stored in SQLite during pull; this flag only
  affects export rendering.

## 2026-04-02

### Changed

- Claude involvement block in exported markdown is now a structured YAML-style block (`- claude:` / `      repo: ...` / `      branch: ...`) instead of an inline comma-separated string. This makes repo and branch directly parseable without string splitting.
- Priority values passed to the Todoist API (both `create` and `push`) are now validated through `_validate_priority`. Values outside 1–4 are clamped to 1 with a warning log rather than sending an invalid value to the API.

## [Unreleased]

### Added

- Initial project scaffolding and directory structure
- Database schema with tables for projects, sections, tasks, labels, task_labels, comments, and sync_state
- Configuration loader with YAML and .env support
- Local data models mirroring Todoist SDK entities
- Todoist API client wrapper
- Pull, push, and sync operations
- Meta-based filter engine
- Markdown export for LLM consumption
- CLI with subcommands: pull, push, sync, status, diff, export, config, init, create, complete
- `create` subcommand — create a new task via the Todoist API and write it to the local database immediately
- `complete` subcommand — close a task via the Todoist API and update the local database (sets is_completed, completed_at, updated_at, synced_at); accepts the task ID shown in export output after `id:`; supports the global `--dry-run` flag
- `DEEP_THOUGHT_DATA_DIR` environment variable — redirects all data storage (database, snapshots, export) to a specified path; defaults to `data/todoist/` at the project root
