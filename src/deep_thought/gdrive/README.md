# GDrive Tool

Incremental Google Drive backup: walks a local directory tree, compares against SQLite state, uploads new files, updates changed files, and skips unchanged ones.

## Overview

The GDrive Tool performs incremental backup from a local directory to Google Drive. It walks the source tree, compares mtimes against the database, uploads new files, updates changed files, skips unchanged ones, and records all state in SQLite. Designed for backing up local work while avoiding redundant API calls.

## Data Flow

```
Local Directory → File Walker → mtime Comparison → SQLite State → Upload/Update/Skip → Drive API
```

## Setup

1. Authenticate with Google OAuth 2.0:

   ```bash
   gdrive auth
   ```

   This runs a one-time browser consent flow and stores a shared token under the `deep-thought-google` keychain entry. The token covers Gmail, Calendar, and Drive scopes together, so running `gdrive auth` (or `gmail auth` or `gcal auth`) authenticates all three Google tools at once. You only need to run the auth command on one of them.

2. Configure the source directory and Drive folder in `src/config/gdrive-configuration.yaml`.

3. Initialize the database:

   ```bash
   gdrive init
   ```

4. Run a backup:

   ```bash
   gdrive
   ```

   Or dry-run to preview changes:

   ```bash
   gdrive --dry-run
   ```

   Other flags available on the default backup run:

   | Flag                 | Description                                                               |
   | -------------------- | ------------------------------------------------------------------------- |
   | `--dry-run`          | Preview all changes without uploading or writing to the database          |
   | `--force`            | Clear all cached state and re-upload all files from scratch               |
   | `--prune`            | Delete Drive files whose local paths match any configured exclude_pattern |
   | `--verbose` / `-v`   | Enable debug-level log output                                             |
   | `--config PATH`      | Override the default configuration file path                              |
   | `--save-config PATH` | Write an example configuration file to PATH and exit                      |

## Configuration

Configuration lives at `src/config/gdrive-configuration.yaml`. Key settings:

| Key                  | Section   | Description                                                           |
| -------------------- | --------- | --------------------------------------------------------------------- |
| `credentials_file`   | `auth`    | Path to the OAuth client secrets JSON file                            |
| `token_file`         | `auth`    | Path to the cached OAuth token (omit to use keychain)                 |
| `scopes`             | `auth`    | List of OAuth scopes (typically `drive.file`)                         |
| `source_dir`         | `backup`  | Absolute local path to the directory being backed up                  |
| `drive_folder_id`    | `backup`  | Google Drive folder ID that receives the backup                       |
| `exclude_patterns`   | `backup`  | fnmatch glob patterns for files/dirs to skip (e.g., `output`, `*.db`) |
| `api_rate_limit_rpm` | top-level | Drive API calls per minute                                            |
| `max_attempts`       | `retry`   | Number of retry attempts on API errors                                |
| `base_delay_seconds` | `retry`   | Initial backoff delay before the first retry                          |

### Exclude Patterns

`exclude_patterns` accepts a list of fnmatch-style glob patterns. Each pattern is tested against the entry name alone and against the path relative to `source_dir`, so:

- `output` — skips any directory or file named `output` anywhere in the tree
- `*.db` — skips all `.db` files anywhere
- `deep-thought/output` — skips only that specific path relative to `source_dir`

Patterns are matched with `fnmatch` — `*` matches within a single path segment only.

## Module Structure

| Module        | Role                                                                 |
| ------------- | -------------------------------------------------------------------- |
| `cli.py`      | CLI entry point with argparse subcommands                            |
| `client.py`   | Google Drive API v3 wrapper with rate limiting and retry             |
| `config.py`   | YAML config loader with .env integration                             |
| `models.py`   | Local dataclasses for backed-up files and folders                    |
| `walker.py`   | Local directory traversal and file enumeration                       |
| `uploader.py` | Backup orchestration: walk → compare → upload/update/skip → DB write |
| `_auth.py`    | OAuth 2.0 token lifecycle management                                 |
| `db/`         | SQLite schema, migrations, and query functions                       |

## Data Storage

All paths are rooted at `data/gdrive/` by default. Set `DEEP_THOUGHT_DATA_DIR` to redirect.

- **SQLite database** — `<data_dir>/gdrive.db` (canonical store)
- **Backup state** — Tracks file IDs, mtimes, and upload status

## Tool-Specific Notes

- **Incremental sync:** Only new or changed files are uploaded; mtime comparison avoids redundant API calls
- **OAuth 2.0 flow:** A single shared token (`deep-thought-google` keychain entry) covers Gmail, Calendar, and Drive. Authenticating via any of the three tools' `auth` command grants access to all three; refresh tokens are handled automatically
- **Dry-run mode:** Preview all changes without uploading (use `--dry-run`)
- **Force mode:** Reupload all files, ignoring mtime state (use `--force`)
- **Rate limiting:** Drive API quotas respected; automatic backoff on 429 responses
- **MIME type detection:** Uses file extension to guess type; falls back to `application/octet-stream`
- **Status tracking:** Files marked as `uploaded`, `updated`, `skipped`, or `error` in database
- **Exclude patterns:** Configure `backup.exclude_patterns` in the YAML to skip directories or files by name or path glob
- **Prune mode:** `--prune` removes Drive files whose local paths match any configured exclude pattern; use `--dry-run --prune` to preview deletions
