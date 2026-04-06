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