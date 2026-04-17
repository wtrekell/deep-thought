# Changelog — GDrive Tool

All notable changes to the gdrive tool will be documented in this file.

## [Unreleased]

### Fixed

- `ensure_folder()` in `client.py` now issues a post-create re-query to detect TOCTOU duplicates. If two same-named folders are found under the same parent after a create (caused by a concurrent run or an external Drive create), a `WARNING` is logged identifying the duplicate IDs and the oldest folder (by `createdTime`, ID as tiebreak) is returned as the deterministic winner. Previously the race was silent — no error, no log, no exit-code change. (#38)
- `walker.py`: Symlinked directories inside `source_dir` are now detected and logged at INFO (e.g. `Skipping symlinked directory (followlinks=False): /path/to/link`) instead of being silently excluded. Symlinks are still not followed (cycle safety preserved). The symlink is also pruned from the traversal set so `os.walk` does not attempt the subtree. (#39)
- `db/schema.py` + new migration `003_backfill_schema_version_updated_at.sql`: The `schema_version` row in `key_value` now always has a non-NULL `updated_at`. `_set_schema_version()` writes `updated_at = datetime('now')` for version >= 2 (version 1 predates the column). Migration 003 backfills existing databases where migration 002 left `updated_at` NULL on that row. (#39)

### Changed

- Secret retrieval now checks macOS Keychain first, falling back to environment variables. Uses the shared `deep_thought.secrets` module.
- OAuth token management refactored to delegate to the shared `deep_thought.secrets` module (behavior unchanged).
- Google OAuth token is now shared across gmail, gcal, and gdrive — one auth flow covers all three tools. Token stored under `deep-thought-google` keychain entry with combined Gmail + Calendar + Drive scopes.
- **gdrive OAuth reverted to a self-contained plain-file flow.** `gdrive/_auth.py` no longer calls `deep_thought.secrets` and no longer touches the macOS keychain. The OAuth token is read from and written to the path set in `auth.token_file` (plain JSON, mode `0o600`), with `google-auth` handling refresh and `google-auth-oauthlib` running the browser consent flow when needed. `auth.token_file` is now required (empty or missing values are rejected by config validation). Gmail and gcal continue to use the shared keychain-backed token and are unaffected. After upgrading, run `gdrive auth` once to populate the token file.

### Added

- `backup.exclude_patterns` config field: an optional list of fnmatch glob patterns for files and directories to skip during backup. Patterns are matched against the entry name and the path relative to `source_dir`. Matching directories are pruned entirely during traversal; matching files are skipped before upload. Defaults to `[]` when omitted from the config.

### Fixed

- SQLite sidecar files (`*.db-wal`, `*.db-shm`, `*.db-journal`) are now hard-excluded in `walker.py`. These are ephemeral runtime artifacts that mutate on every database connection — including the gdrive tool's own `gdrive.db-wal` / `gdrive.db-shm` files — which caused every backup run to re-upload two files that carry no user content. The exclusion lives alongside `_EXCLUDED_DIR_NAMES` and cannot be disabled via config because backing these files up is never meaningful.
- Files deleted or renamed between walker enumeration and the upload step are now logged at WARNING and counted in a new `BackupResult.vanished` field instead of being recorded as errors that flip the exit code to 2. The backup summary prints a `Vanished:` count and, when non-zero, lists the affected paths. Real OS errors (permission denied, etc.) continue to be counted as errors and still exit 2. No DB row is written for vanished files. Resolves issue #34.
- Post-commit hook now sends a macOS notification on backup failure instead of silently discarding the exit code.
- Missing `source_dir` now raises `FileNotFoundError` (exit code 1) instead of returning empty success.
- `gdrive status` now displays `last_run_at` timestamp so stale backups are immediately visible.
- DB error-status write failures now logged at WARNING instead of DEBUG.
- `walker.py` now logs WARNING for `stat()` errors other than `FileNotFoundError` instead of silently skipping.
- `upload_file` and `update_file` now stream from disk via `MediaFileUpload` instead of buffering entire files in memory.
- `_project_root` fallback corrected from `parents[5]` to `parents[4]`.
- `_get_version` bare `except Exception` narrowed to `except PackageNotFoundError`.
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
