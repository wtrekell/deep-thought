# Changelog — GDrive Tool

All notable changes to the gdrive tool will be documented in this file.

## [Unreleased]

### Added

- `backup.exclude_patterns` config field: an optional list of fnmatch glob patterns for files and directories to skip during backup. Patterns are matched against the entry name and the path relative to `source_dir`. Matching directories are pruned entirely during traversal; matching files are skipped before upload. Defaults to `[]` when omitted from the config.

### Fixed

- Skipped files now write a `"skipped"` status row to `backed_up_files` on each run, so `gdrive status` accurately reflects which files were evaluated and left unchanged (previously skipped files retained their last `"uploaded"` or `"updated"` status indefinitely).
- `upload_file()` in `client.py` now uses `Path(local_path).name` to extract the filename instead of `local_path.split("/")[-1]`, consistent with the rest of the codebase.

## [0.1.0] — Initial Release

### Added

- Incremental Google Drive backup: walks a local source directory, compares file mtime against SQLite state, uploads new files, updates changed files, and skips unchanged ones
- OAuth 2.0 authentication with token persistence and auto-refresh (`_auth.py`)
- Drive API v3 wrapper with configurable rate limiting (token-bucket) and exponential backoff retry on 429/500/503 errors (`client.py`)
- Hidden file/directory exclusion and skip list for `__pycache__`, `.git`, `.venv`, `node_modules`, `.mypy_cache` (`walker.py`)
- Drive folder hierarchy mirroring: creates matching folder structure in Drive with local-to-folder-ID caching to avoid redundant API calls
- `--dry-run` flag: logs what would be uploaded/updated without making API calls or writing to the database
- `--force` flag: clears all cached state and re-uploads all files from scratch
- `--verbose` / `-v` flag: emits per-file SKIP/UPLOAD/UPDATE log lines during a run
- Subcommands: `init` (bootstrap database and data directories), `config` (display current configuration), `auth` (run OAuth consent flow), `status` (print file counts by status), `backup` (default — run incremental backup)
- SQLite state layer: `backed_up_files` (tracks upload status and Drive file IDs), `drive_folders` (caches local path → Drive folder ID), `key_value` (schema version)
- Exit codes: 0 (success), 1 (fatal error), 2 (partial failure with per-file errors)
