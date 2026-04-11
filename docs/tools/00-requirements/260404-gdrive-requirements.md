# Product Brief — Google Drive Tool

## Name and Purpose

**Google Drive Tool** — incrementally backs up the `dont-panic` workspace to Google Drive as offsite cold storage. Mirrors the full directory tree to a configured Drive folder, uploading only new or modified files on each run. No filtering, no conversion — files are uploaded as-is.

**Tool type:** Backup (walks local file tree; uploads new and modified files to Google Drive; records state in a local SQLite database).

## Operations

1. **CLI Command** — `gdrive` (entry point)
2. **Backup** — Walk `dont-panic`, upload new or changed files to Drive (default operation)
3. **Status** — Report counts of pending, uploaded, and failed files without uploading

## Requirements

1. Python 3.12 using `uv` as the package manager.
2. **google-api-python-client** (`google-api-python-client>=2.100.0`) for Drive API v3 access.
3. **google-auth-oauthlib** (`google-auth-oauthlib>=1.2.0`) for OAuth 2.0 browser flow.
4. **google-auth-httplib2** (`google-auth-httplib2>=0.2.0`) for HTTP transport.
5. SQLite for local state tracking (WAL mode, foreign keys enabled).
6. No API key required — uses OAuth 2.0 with user consent flow.
7. A changelog is maintained in `files/tools/gdrive/CHANGELOG.md`.

## Data Storage

### State Database

Located at `data/gdrive/gdrive.db` by default; respects the `DEEP_THOUGHT_DATA_DIR` env var to redirect the data root at runtime.

- Table: `backed_up_files` — columns: `local_path TEXT PRIMARY KEY`, `drive_file_id TEXT`, `drive_folder_id TEXT`, `mtime REAL`, `size_bytes INTEGER`, `status TEXT`, `uploaded_at TEXT`, `updated_at TEXT`
- **Primary key:** `local_path` — relative path from the `dont-panic` root (e.g., `magrathea/src/cli.py`)
- `mtime` is the local file modification time (Unix timestamp); changes trigger re-upload
- Schema version tracked in a `key_value` table
- Migrations stored in `db/migrations/` with numeric prefixes

### Drive Folder Structure

Files are uploaded to a configured root folder on Drive, preserving the local directory structure. A subfolder is created on Drive for each directory in the local tree.

- Drive folder IDs for created subdirectories are cached in a `drive_folders` table: `local_path TEXT PRIMARY KEY`, `drive_folder_id TEXT`
- Avoids redundant folder-creation API calls on subsequent runs

## Data Models

### BackedUpFile

| Field | Type | Description |
| --- | --- | --- |
| `local_path` | `str` | Relative path from `dont-panic` root — primary key |
| `drive_file_id` | `str` | Drive file ID of the uploaded copy |
| `drive_folder_id` | `str` | Drive folder ID where the file lives |
| `mtime` | `float` | Local file modification time at last upload (Unix timestamp) |
| `size_bytes` | `int` | File size at last upload |
| `status` | `str` | `uploaded`, `updated`, `skipped`, `error` |
| `uploaded_at` | `str` | ISO 8601 timestamp of first upload |
| `updated_at` | `str` | ISO 8601 timestamp of last upload or update attempt |

Methods: `to_dict()` for database insertion.

## Command List

Running `gdrive` with no arguments runs the backup. Use `--help` to list options.

| Subcommand | Description |
| --- | --- |
| `gdrive config` | Validate and display current YAML configuration |
| `gdrive init` | Create config file and directory structure |
| `gdrive auth` | Start OAuth 2.0 browser flow to authorize the tool |
| `gdrive status` | Show counts of pending, uploaded, and failed files |

| Flag | Description |
| --- | --- |
| `--config PATH` | YAML configuration file (default: `src/config/gdrive-configuration.yaml`) |
| `--dry-run` | Walk the tree and report what would be uploaded, without uploading |
| `--verbose`, `-v` | Detailed logging |
| `--force` | Clear state and re-upload all files |
| `--save-config PATH` | Generate example config and exit |
| `--version` | Show version and exit |

## File & Output Map

```
files/tools/00-requirements/
└── 260404-gdrive-requirements.md # This document

files/tools/gdrive/
└── CHANGELOG.md                 # Release history

src/deep_thought/gdrive/
├── __init__.py
├── _auth.py                     # OAuth 2.0 token management
├── cli.py                       # CLI entry point
├── config.py                    # YAML config loader and validation
├── models.py                    # Local dataclasses for backup state
├── walker.py                    # Directory tree walker and change detection
├── uploader.py                  # Drive upload, update, and folder management
├── db/
│   ├── __init__.py
│   ├── schema.py                # Table creation and migration runner
│   ├── queries.py               # All SQL operations
│   └── migrations/
│       └── 001_init_schema.sql
└── client.py                    # Drive API v3 client wrapper

data/gdrive/
└── gdrive.db                    # SQLite state database

tests/gdrive/
├── conftest.py                  # Shared fixtures (mock Drive service, temp directories)
├── test_cli.py
├── test_client.py
├── test_config.py
├── test_models.py
├── test_queries.py
├── test_schema.py
├── test_uploader.py
└── test_walker.py

src/config/
└── gdrive-configuration.yaml   # Tool configuration
```

## Configuration

Configuration is stored in `src/config/gdrive-configuration.yaml`. All values below are required unless marked optional.

```yaml
# OAuth credentials
auth:
  credentials_file: "src/config/gdrive/credentials.json"
  token_file: "src/config/gdrive/token.json"
  scopes:
    - "https://www.googleapis.com/auth/drive.file"

# Backup source and destination
backup:
  source_dir: "/Users/williamtrekell/Documents/dont-panic"
  drive_folder_id: ""          # Required: ID of the root backup folder on Drive

# API
api_rate_limit_rpm: 100           # Drive API calls per minute

# Retry behavior
retry:
  max_attempts: 3
  base_delay_seconds: 2.0
```

## Incremental Sync Logic

On each run:

1. Walk the `source_dir` tree recursively, collecting all file paths and their `mtime` and `size_bytes`.
2. For each file, look up the `local_path` in `backed_up_files`.
   - **Not found** → new file, upload and record.
   - **Found, `mtime` unchanged** → skip.
   - **Found, `mtime` changed** → re-upload using the existing `drive_file_id` (Drive update, not a new file).
3. Ensure the Drive subfolder exists before uploading (create if absent, use cached ID if present).
4. Record the result (`success` or `error`) in the state DB after each file.

`--force` clears `backed_up_files` and `drive_folders` before the walk, causing a full re-upload.

## Error Handling

- `OAuth authentication failures` — missing or invalid credentials; halts the run and instructs user to run `gdrive auth`
- `Drive API errors` (rate limits, permission denied) — caught per-file; file marked `status: error`; backup continues with remaining files
- `File read errors` — caught per-file; file marked `status: error`; backup continues
- Missing config file raises `FileNotFoundError`. Invalid config content raises `ValueError`. Missing required env vars raise `OSError`.
- Top-level `try/except` in CLI entry point catches all above and prints descriptive messages.
- Exit codes: `0` all files succeeded, `1` fatal error, `2` partial failure (some files errored)

## Testing

- Use in-memory SQLite for all database tests.
- Mock targets: `google.oauth2`, `google.auth`, `googleapiclient.discovery` — mock the Drive service, file upload, update, and folder creation calls
- Test fixtures: mock Drive API response objects; temporary directories with known file trees for walker tests
- Organize tests in classes by feature area (walking, change detection, upload, folder management, state tracking)
- Mark slow or network-dependent tests with `@pytest.mark.integration`.
- Mark error path tests with `@pytest.mark.error_handling`.
- Test directory: `tests/gdrive/` with `conftest.py` for shared fixtures
- Test fixtures are created programmatically using `tmp_path`
