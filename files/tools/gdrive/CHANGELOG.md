# Google Drive Tool — Changelog

## 0.1.0 — 2026-04-04

### Added

- Initial implementation of incremental backup to Google Drive
- Uploads new and modified files; skips unchanged files by mtime
- Drive folder structure mirrors local directory tree; folder IDs cached in SQLite
- `gdrive status` reports counts of uploaded, pending, and failed files
- `gdrive auth` runs OAuth 2.0 browser consent flow
- `gdrive init` creates local data directory and database
- `gdrive config` validates and displays current configuration
- `--dry-run`, `--force`, `--verbose` flags
- Exit codes: 0 success, 1 fatal error, 2 partial failure
