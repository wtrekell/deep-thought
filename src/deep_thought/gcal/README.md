# GCal Tool

Pulls events from Google Calendar, stores them in SQLite, and exports structured markdown. Supports creating, updating, and deleting events from markdown files.

## Overview

The GCal Tool syncs Google Calendar events from one or more calendars into a local SQLite database and exports LLM-optimized markdown. Events can be created, modified, or deleted via markdown files with YAML frontmatter, and changes are pushed back to Google Calendar.

## Data Flow

```
Google Calendar API → Local Models → Filters → SQLite DB → Markdown Export
                                                               ↑
                                          create/update/delete (markdown → API)
```

## Setup

1. Initialize the database, config file, and directory structure:

   ```bash
   gcal init
   ```

2. Edit the configuration file at `src/config/gcal-configuration.yaml`. At minimum, set `credentials_path` and `calendars`.

3. Authenticate with Google OAuth 2.0:

   ```bash
   gcal auth
   ```

4. Pull your first sync:

   ```bash
   gcal
   ```

## CLI Reference

```
gcal [--config PATH] [--output PATH] [--calendar ID] [--days-back INT] [--days-ahead INT]
     [--dry-run] [--force] [--verbose] [--save-config PATH]
gcal init
gcal config
gcal auth
gcal pull
gcal create <file.md>
gcal update <file.md>
gcal delete <event_id> [--calendar-id ID]
```

| Flag / Subcommand    | Description                                                      |
| -------------------- | ---------------------------------------------------------------- |
| _(no subcommand)_    | Pull events from all configured calendars (same as `pull`)       |
| `init`               | Create database, config template, and directory structure        |
| `config`             | Validate and display the current configuration                   |
| `auth`               | Run the OAuth 2.0 Desktop app flow                               |
| `pull`               | Pull events and export to markdown                               |
| `create <file.md>`   | Create a new event from a markdown file                          |
| `update <file.md>`   | Update an existing event from a markdown file                    |
| `delete <event_id>`  | Delete an event by ID                                            |
| `--config PATH`      | Override the default config file path                            |
| `--output PATH`      | Override the output directory                                    |
| `--calendar ID`      | Comma-separated calendar IDs to target (default: all configured) |
| `--days-back INT`    | Number of days back to include                                   |
| `--days-ahead INT`   | Number of days ahead to include                                  |
| `--dry-run`          | Preview changes without writing files or calling the API         |
| `--force`            | Clear sync state and re-pull all events from scratch             |
| `--verbose` / `-v`   | Enable debug logging                                             |
| `--save-config PATH` | Write the default config template to PATH and exit               |

## Configuration

Configuration lives at `src/config/gcal-configuration.yaml`. All fields and their defaults:

| Field                      | Default                            | Description                                                           |
| -------------------------- | ---------------------------------- | --------------------------------------------------------------------- |
| `credentials_path`         | `src/config/gcal/credentials.json` | Path to OAuth 2.0 client credentials                                  |
| `token_path`               | `data/gcal/token.json`             | Path to cached OAuth token                                            |
| `scopes`                   | `[...calendar]`                    | OAuth scopes list                                                     |
| `api_rate_limit_rpm`       | `250`                              | API request rate limit (requests per minute)                          |
| `retry_max_attempts`       | `3`                                | Maximum retry attempts on transient errors                            |
| `retry_base_delay_seconds` | `1`                                | Base delay in seconds between retries                                 |
| `calendars`                | `["primary"]`                      | Calendar IDs to sync                                                  |
| `lookback_days`            | `7`                                | Days in the past to fetch                                             |
| `lookahead_days`           | `30`                               | Days in the future to fetch                                           |
| `include_cancelled`        | `false`                            | Whether to include cancelled events                                   |
| `single_events`            | `true`                             | Expand recurring events into individual instances                     |
| `output_dir`               | `data/gcal/export/`                | Root directory for markdown exports                                   |
| `generate_llms_files`      | `false`                            | Generate `llms.txt` index files                                       |
| `flat_output`              | `false`                            | Write all files directly to `output_dir` (no calendar subdirectories) |

## Module Structure

| Module       | Role                                                  |
| ------------ | ----------------------------------------------------- |
| `cli.py`     | CLI entry point with argparse subcommands             |
| `client.py`  | Google Calendar API v3 wrapper                        |
| `config.py`  | YAML config loader with .env integration              |
| `models.py`  | Local dataclasses mirroring Calendar API events       |
| `filters.py` | Event filtering and selection logic                   |
| `pull.py`    | API → models → filters → DB upsert → markdown export  |
| `create.py`  | Markdown file → API create → DB upsert                |
| `update.py`  | Markdown file → API update → DB upsert                |
| `output.py`  | DB → structured markdown files                        |
| `llms.py`    | `llms.txt` index file generation                      |
| `_auth.py`   | OAuth 2.0 token lifecycle (acquire, refresh, persist) |
| `db/`        | SQLite schema, migrations, and query functions        |

## Data Storage

All paths are rooted at `data/gcal/` by default. Set `DEEP_THOUGHT_DATA_DIR` to redirect.

- **SQLite database** — `<data_dir>/gcal.db` (canonical store)
- **Markdown export** — `<output_dir>/<calendar-slug>/<YYMMDD>-<event-slug>.md`
- **Flat mode** — `<output_dir>/<YYMMDD>-<event-slug>.md` (when `flat_output: true`)

## Tool-Specific Notes

- **OAuth 2.0 flow:** Credentials are cached in a local token file; refresh tokens are handled automatically
- **All-day events:** Stored as separate from timed events; date representation differs in frontmatter
- **Attendee list:** Extracted and stored; used for filtering and LLM context
- **Timezone handling:** Events respect the calendar's timezone; local times are standardized in export
