# GCal Tool

Pulls events from Google Calendar, stores them in SQLite, and exports structured markdown. Supports creating, updating, and deleting events from markdown files.

## Overview

The GCal Tool syncs Google Calendar events from one or more calendars into a local SQLite database and exports LLM-optimized markdown. Events can be created, modified, or deleted via markdown files with YAML frontmatter, and changes are pushed back to Google Calendar. Bidirectional sync is supported with configurable conflict resolution.

## Data Flow

```
Google Calendar API → Local Models → Filters → SQLite DB → Markdown Export
                                       ↑
                              Push (modified events back to API)
```

## Setup

1. Authenticate with Google OAuth 2.0:

   ```bash
   gcal auth
   ```

2. Configure which calendars to sync in `src/config/gcal-configuration.yaml`.

3. Initialize the database:

   ```bash
   gcal init
   ```

4. Pull your first sync:

   ```bash
   gcal pull
   ```

## Configuration

Configuration lives at `src/config/gcal-configuration.yaml`. Key settings:

- **calendars** — List of calendar IDs to include in sync
- **lookback_days** — How many days in the past to fetch
- **lookahead_days** — How many days in the future to fetch
- **event_filters** — Rules for including/excluding events by summary, attendees, or other properties

## Module Structure

| Module       | Role                                                 |
| ------------ | ---------------------------------------------------- |
| `cli.py`     | CLI entry point with argparse subcommands            |
| `client.py`  | Google Calendar API v3 wrapper                       |
| `config.py`  | YAML config loader with .env integration             |
| `models.py`  | Local dataclasses mirroring Calendar API events      |
| `filters.py` | Event filtering and selection logic                  |
| `pull.py`    | API → models → filters → DB upsert → markdown export |
| `push.py`    | Markdown → API updates (create, update, delete)      |
| `output.py`  | DB → structured markdown files                       |
| `db/`        | SQLite schema, migrations, and query functions       |

## Data Storage

All paths are rooted at `data/gcal/` by default. Set `DEEP_THOUGHT_DATA_DIR` to redirect.

- **SQLite database** — `<data_dir>/gcal.db` (canonical store)
- **Markdown export** — `<data_dir>/export/<calendar_id>/<date_range>.md`

## Tool-Specific Notes

- **OAuth 2.0 flow:** Credentials are cached in a local token file; refresh tokens are handled automatically
- **All-day events:** Stored as separate from timed events; date representation differs in frontmatter
- **Attendee list:** Extracted and stored; used for filtering and LLM context
- **Timezone handling:** Events respect the calendar's timezone; local times are standardized in export
- **Push conflicts:** Configurable conflict resolution (local-wins, remote-wins, merge)
