# Product Brief — GCal Tool

## Name and Purpose

**GCal Tool** — pulls events from Google Calendar, stores them in SQLite, and exports LLM-optimized markdown. Supports creating and updating events from markdown files with YAML frontmatter. Uses the same Google Cloud project and OAuth 2.0 pattern as the Gmail tool but manages its own token and scope independently.

## Sync Modes

1. **CLI Command** — `gcal` (entry point)
2. **Pull** — Fetch events from configured calendars, store in SQLite, export to markdown (default operation)
3. **Create** — Create a calendar event from a markdown file with YAML frontmatter
4. **Update** — Update an existing event from a modified markdown file with YAML frontmatter
5. **Delete** — Delete an event by event ID
6. **Auth** — Run or refresh the OAuth 2.0 browser flow

## Requirements

1. Python 3.12 using `uv` as the package manager.
2. **Google API Python Client** ([`google-api-python-client`](https://github.com/googleapis/google-api-python-client)) for Calendar API access. API reference: [Calendar API v3](https://developers.google.com/workspace/calendar/api/v3/reference).
3. **Google Auth** ([`google-auth-oauthlib`](https://google-auth-oauthlib.readthedocs.io/), `google-auth-httplib2`) for OAuth 2.0.
4. SQLite for local state tracking (WAL mode, foreign keys enabled).
5. `credentials.json` (OAuth 2.0 client secret) — shared with the Gmail tool at `src/config/gmail/credentials.json`. See the Gmail spec's [Google Cloud Setup](../gmail/260323-requirements.md#google-cloud-setup) for initial project creation.
6. A changelog is maintained in `files/tools/gcal/CHANGELOG.md`.

## Google Cloud Setup

The GCal tool shares a Google Cloud project with the Gmail tool. The only additional step is:

1. Enable the **Google Calendar API** in the same Google Cloud Console project used for Gmail.
2. Add the Calendar scope (below) to the OAuth consent screen.

No new `credentials.json` is needed — the existing Desktop app credential works for both APIs. Each tool maintains its own `token.json` so scopes are managed independently.

### Publishing Status and Token Expiry

Same as Gmail: projects in **Testing** mode expire refresh tokens after **7 days**. Publish to **Production** to avoid this. See the Gmail spec for details.

## OAuth 2.0 Scopes

| Scope                                      | Why                                                                            |
| ------------------------------------------ | ------------------------------------------------------------------------------ |
| `https://www.googleapis.com/auth/calendar` | Full read/write access — required for creating, updating, and deleting events. |

If only reading events (no create/update/delete), the scope can be narrowed to `https://www.googleapis.com/auth/calendar.readonly`.

**Scope changes:** If scopes are changed after initial authorization, `token.json` must be deleted so the next `gcal auth` run triggers a new consent screen with the updated permissions.

## Data Storage

### State Database

Located at `data/gcal/gcal.db` by default; respects the `DEEP_THOUGHT_DATA_DIR` env var to redirect the data root at runtime.

- Table: `events` — columns: `event_id TEXT`, `calendar_id TEXT`, `summary TEXT`, `description TEXT`, `location TEXT`, `start_time TEXT`, `end_time TEXT`, `all_day INTEGER`, `status TEXT`, `organizer TEXT`, `attendees TEXT`, `recurrence TEXT`, `html_link TEXT`, `created_at TEXT`, `updated_at TEXT`, `synced_at TEXT`, `PRIMARY KEY (event_id, calendar_id)`
- Table: `calendars` — columns: `calendar_id TEXT PRIMARY KEY`, `summary TEXT`, `description TEXT`, `time_zone TEXT`, `primary_calendar INTEGER`, `created_at TEXT`, `updated_at TEXT`, `synced_at TEXT`
- Table: `sync_state` — columns: `calendar_id TEXT PRIMARY KEY`, `sync_token TEXT`, `last_sync_time TEXT`
- Table: `key_value` — schema version tracking
- Foreign key: `events.calendar_id` references `calendars.calendar_id` with `ON DELETE CASCADE`
- Foreign key: `sync_state.calendar_id` references `calendars.calendar_id` with `ON DELETE CASCADE`
- Index on `events.calendar_id` for join performance
- Index on `events.start_time` for time-range queries
- Use `INSERT OR REPLACE` for upsert operations
- Schema version tracked in a `key_value` table
- Migrations stored in `db/migrations/` with numeric prefixes

## Data Models

### EventLocal

| Field         | Type          | Description                                                       |
| ------------- | ------------- | ----------------------------------------------------------------- |
| `event_id`    | `str`         | Google Calendar event ID (composite PK with `calendar_id`)        |
| `calendar_id` | `str`         | Calendar the event belongs to (composite PK with `event_id`)      |
| `summary`     | `str`         | Event title                                                       |
| `description` | `str \| None` | Event description / notes                                         |
| `location`    | `str \| None` | Event location (free text or address)                             |
| `start_time`  | `str`         | ISO 8601 start time (datetime for timed events, date for all-day) |
| `end_time`    | `str`         | ISO 8601 end time                                                 |
| `all_day`     | `bool`        | `True` if the event uses `date` rather than `dateTime`            |
| `status`      | `str`         | `confirmed`, `tentative`, or `cancelled`                          |
| `organizer`   | `str \| None` | Organizer email address                                           |
| `attendees`   | `str \| None` | Serialized JSON list of attendee objects                          |
| `recurrence`  | `str \| None` | Serialized JSON list of RRULE strings                             |
| `html_link`   | `str \| None` | URL to event in Google Calendar web UI                            |
| `created_at`  | `str`         | ISO 8601 timestamp of first sync                                  |
| `updated_at`  | `str`         | ISO 8601 timestamp from Google (`updated` field)                  |
| `synced_at`   | `str`         | ISO 8601 timestamp of last local sync                             |

Methods: `from_api_response()` for API dict conversion, `to_dict()` for database insertion.

### CalendarLocal

| Field              | Type          | Description                                   |
| ------------------ | ------------- | --------------------------------------------- |
| `calendar_id`      | `str`         | Google Calendar ID (primary key)              |
| `summary`          | `str`         | Calendar display name                         |
| `description`      | `str \| None` | Calendar description                          |
| `time_zone`        | `str`         | IANA time zone (e.g., `America/Chicago`)      |
| `primary_calendar` | `bool`        | `True` if this is the user's primary calendar |
| `created_at`       | `str`         | ISO 8601 timestamp of first sync              |
| `updated_at`       | `str`         | ISO 8601 timestamp of last update             |
| `synced_at`        | `str`         | ISO 8601 timestamp of last API sync           |

Methods: `from_api_response()` for API dict conversion, `to_dict()` for database insertion.

### PullResult

| Field              | Type  | Description                           |
| ------------------ | ----- | ------------------------------------- |
| `created`          | `int` | Number of new events added locally    |
| `updated`          | `int` | Number of existing events updated     |
| `cancelled`        | `int` | Number of events marked as cancelled  |
| `unchanged`        | `int` | Number of events skipped (no changes) |
| `calendars_synced` | `int` | Number of calendars processed         |

Printed to stdout on pull completion. Used to determine exit code (0 if no errors, 2 if partial failure).

### CreateResult

| Field       | Type  | Description                                   |
| ----------- | ----- | --------------------------------------------- |
| `event_id`  | `str` | Google Calendar event ID of the created event |
| `html_link` | `str` | URL to the event in Google Calendar web UI    |

Printed to stdout on create completion.

### UpdateResult

| Field            | Type        | Description                                   |
| ---------------- | ----------- | --------------------------------------------- |
| `event_id`       | `str`       | Google Calendar event ID of the updated event |
| `html_link`      | `str`       | URL to the event in Google Calendar web UI    |
| `fields_changed` | `list[str]` | List of fields that were modified             |

Printed to stdout on update completion.

### DeleteResult

| Field         | Type  | Description                                   |
| ------------- | ----- | --------------------------------------------- |
| `event_id`    | `str` | Google Calendar event ID of the deleted event |
| `calendar_id` | `str` | Calendar the event was deleted from           |

Printed to stdout on delete completion.

## Command List

Running `gcal` with no arguments shows help. Running `gcal` with flags but no subcommand triggers a pull operation.

| Subcommand    | Description                                                                                                                                                                                                                             |
| ------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `gcal config` | Validate and display current YAML configuration                                                                                                                                                                                         |
| `gcal init`   | Create data directories (`data/gcal/`, `data/gcal/export/`, `data/gcal/input/`, `data/gcal/snapshots/`), generate a starter `gcal-configuration.yaml` if missing, and verify that `credentials.json` exists at the configured path      |
| `gcal create` | Create a calendar event from a markdown file with YAML frontmatter                                                                                                                                                                      |
| `gcal update` | Update an existing event from a markdown file containing an `event_id` in its frontmatter                                                                                                                                               |
| `gcal delete` | Delete an event by ID: `gcal delete EVENT_ID`                                                                                                                                                                                           |
| `gcal auth`   | Run the OAuth 2.0 Desktop app flow — opens a browser for consent on first run, refreshes the token silently on subsequent runs. Stores the resulting access + refresh token in `token.json`. Re-run after scope changes or token expiry |

| Flag                 | Description                                                             |
| -------------------- | ----------------------------------------------------------------------- |
| `--config PATH`      | YAML configuration file (default: `src/config/gcal-configuration.yaml`) |
| `--output PATH`      | Output directory override                                               |
| `--calendar ID`      | Override which calendar(s) to pull (comma-separated IDs)                |
| `--days-back INT`    | Override lookback window (default from config)                          |
| `--days-ahead INT`   | Override lookahead window (default from config)                         |
| `--dry-run`          | Preview without writing files or making API changes                     |
| `--verbose`, `-v`    | Detailed logging                                                        |
| `--force`            | Clear sync state and re-pull all events                                 |
| `--save-config PATH` | Generate example config and exit                                        |
| `--version`          | Show version and exit                                                   |

### Create Subcommand

```
gcal create event.md
```

Accepts a positional path to the markdown file. If omitted, defaults to looking in `data/gcal/input/`. The markdown file must have a YAML frontmatter block with `summary`, `start`, `end`, and optionally `location`, `description`, `calendar_id`, `attendees`, `recurrence`. See [Create Event Frontmatter](#create-event-frontmatter) below.

### Update Subcommand

```
gcal update event.md
```

Accepts a positional path to the markdown file. The file must include `event_id` in the frontmatter to identify which event to update. Only fields present in the frontmatter are modified; omitted fields are left unchanged. Accepts the same frontmatter fields as create plus `event_id` (required) and `calendar_id` (defaults to `primary`).

### Delete Subcommand

```
gcal delete EVENT_ID
gcal delete EVENT_ID --calendar-id work@group.calendar.google.com
```

Accepts a positional event ID. Deletes the event from Google Calendar and removes the local database row and exported markdown file. `--calendar-id` defaults to `primary`.

## File & Output Map

```
files/tools/gcal/
├── 260323-requirements.md       # This document
└── CHANGELOG.md                 # Release history

src/deep_thought/gcal/
├── __init__.py
├── cli.py                       # CLI entry point (pull, create, update, delete subcommands)
├── config.py                    # YAML config loader and validation
├── models.py                    # Local dataclasses for calendar/event state
├── pull.py                      # Sync orchestration: fetch, diff, upsert, export
├── create.py                    # Event creation from markdown frontmatter
├── update.py                    # Event update from markdown frontmatter
├── filters.py                   # Post-fetch filtering: include/exclude logic on event metadata (calendar, status, organizer) applied after API fetch, before database write
├── db/
│   ├── __init__.py
│   ├── schema.py                # Table creation and migration runner
│   ├── queries.py               # All SQL operations
│   └── migrations/
│       └── 001_init_schema.sql
├── output.py                    # Markdown + YAML frontmatter generation
├── llms.py                      # .llms.txt / .llms-full.txt generation
└── client.py                    # Calendar API client wrapper (OAuth 2.0); collapses paginated list responses into flat lists

data/gcal/
├── gcal.db                      # SQLite state database
├── token.json                   # OAuth 2.0 access + refresh token (auto-managed, NEVER committed — contains sensitive refresh token)
├── input/                       # Default location for create/update input files
├── snapshots/                   # Raw JSON blobs per pull run (YYYY-MM-DDTHHMMSS.json)
└── export/                      # Generated markdown files

src/config/
└── gcal-configuration.yaml      # Tool configuration
```

## Configuration

Configuration is stored in `src/config/gcal-configuration.yaml`. All values below are required unless marked optional.

```yaml
# Auth
credentials_path: "src/config/gmail/credentials.json" # Shared with Gmail tool
token_path: "data/gcal/token.json"
scopes:
  - "https://www.googleapis.com/auth/calendar" # Use 'calendar.readonly' if no create/update needed

# Calendar API
api_rate_limit_rpm: 250 # Calendar API default quota; lower to be conservative
retry_max_attempts: 3 # Retry failed API calls with exponential backoff
retry_base_delay_seconds: 1 # Initial delay doubles on each retry

# Pull
calendars:
  - "primary" # Calendar IDs to sync; 'primary' is the user's main calendar
lookback_days: 7 # Pull events starting this many days in the past
lookahead_days: 30 # Pull events up to this many days in the future
include_cancelled: false # Whether to include cancelled events in export
single_events: true # Expand recurring events into individual instances

# Output
output_dir: "data/gcal/export/"
generate_llms_files: false # Set true to generate .llms.txt / .llms-full.txt files
flat_output: false # true = all files in one directory; false = organized by calendar
```

## Sync Strategy

### Incremental Sync

The Calendar API supports sync tokens for efficient incremental pulls:

1. **First pull:** Fetch all events in the configured time window. Store the `nextSyncToken` from the response in the `sync_state` table.
2. **Subsequent pulls:** Pass the stored `syncToken` to `events().list()`. The API returns only events that changed since the last sync.
3. **Sync token invalidation:** If the API returns HTTP 410 (Gone), the sync token has expired. Clear it from `sync_state` and perform a full pull.

### Change Detection

- Use the event's `updated` timestamp from Google to detect modifications.
- Upsert logic: if `event_id` + `calendar_id` exists locally and the remote `updated` is newer, update the local row. Otherwise skip.
- Cancelled events: if `status` is `cancelled`, mark the local row accordingly and remove the exported markdown file if it exists.

## Data Format

### Markdown Output

```
data/gcal/export/{calendar_name}/
├── {date}_{summary_slug}.md           # Event with YAML frontmatter
└── llm/
    ├── {date}_{summary_slug}.llms.txt
    └── {date}_{summary_slug}.llms-full.txt
```

When `flat_output: true`, all events export to `data/gcal/export/` without calendar subdirectories.

**Filename sanitization:** `{summary_slug}` and `{calendar_name}` are generated by lowercasing, replacing non-alphanumeric characters with hyphens, collapsing consecutive hyphens, stripping leading/trailing hyphens, and truncating to 80 characters. Only include metadata fields with non-null, non-empty values in the frontmatter.

### Event Frontmatter Schema

```markdown
---
tool: gcal
event_id: abc123def456
calendar: "Primary"
summary: "Team standup"
start: "2026-03-24T09:00:00-05:00"
end: "2026-03-24T09:30:00-05:00"
all_day: false
location: "Conference Room B"
status: confirmed
organizer: "manager@example.com"
attendees:
  - "colleague@example.com"
  - "teammate@example.com"
recurrence: null
html_link: "https://calendar.google.com/event?eid=abc123"
synced_date: "2026-03-23T12:00:00Z"
---

Team standup meeting notes and agenda items.
```

For all-day events, `start` and `end` use date-only format (`2026-03-24`) rather than datetime.

### Create Event Frontmatter

```markdown
---
summary: "Project review"
start: "2026-03-25T14:00:00-05:00"
end: "2026-03-25T15:00:00-05:00"
location: "Zoom"
calendar_id: "primary"
description: "Monthly review of project milestones"
attendees:
  - "reviewer@example.com"
---

Optional body text becomes the event description if `description` is not set in frontmatter.
```

| Frontmatter Field | Required | Description                                                |
| ----------------- | -------- | ---------------------------------------------------------- |
| `summary`         | Yes      | Event title                                                |
| `start`           | Yes      | ISO 8601 datetime or date (for all-day)                    |
| `end`             | Yes      | ISO 8601 datetime or date (for all-day)                    |
| `location`        | No       | Event location                                             |
| `calendar_id`     | No       | Target calendar (default: `primary`)                       |
| `description`     | No       | Event description; if absent, markdown body is used        |
| `attendees`       | No       | List of email addresses to invite                          |
| `recurrence`      | No       | List of RRULE strings (e.g., `RRULE:FREQ=WEEKLY;COUNT=10`) |

## Error Handling

- `Google API authentication errors` — caught at the client level; surfaces descriptive message and exits with code 1.
- `OAuth token refresh failures` — caught during client initialization; prompts user to re-run `gcal auth`.
- `Calendar API rate limit / transient errors` (HTTP 429, 500, 503) — retried with exponential backoff up to `retry_max_attempts` (default 3). Initial delay is `retry_base_delay_seconds`, doubling on each retry. Permanent failures (4xx other than 429) are not retried.
- `Sync token expired` (HTTP 410 Gone) — clear the stored sync token and fall back to a full pull. Log a warning but do not exit.
- `Event creation/update failures` — caught per-event; surfaces descriptive message with the event summary and exits with code 1.
- `Event deletion failures` (e.g., event not found, HTTP 404) — surfaces descriptive message with the event ID and exits with code 1.
- Missing config file raises `FileNotFoundError`. Invalid config content raises `ValueError`. Missing required env vars (e.g., `DEEP_THOUGHT_DATA_DIR` if referenced but unset) raise `OSError`.
- Top-level `try/except` in CLI entry point catches all above and prints descriptive messages.
- Exit codes: `0` all items succeeded, `1` fatal error, `2` partial failure (some items errored)

## Testing

- Use in-memory SQLite for all database tests.
- Provide populated database fixtures with seed data (sample calendars, events across time ranges, sync state entries).
- Mock targets: `google-api-python-client`, `google-auth` — use `MagicMock` for SDK objects.
- Create helper functions for building test event objects (e.g., `make_event(summary=..., start=..., all_day=...)`).
- Test fixtures: sample event objects covering timed events, all-day events, recurring events, multi-attendee events, and cancelled events.
- Organize tests in classes by feature area (pull, create, update, delete, sync state, export, auth).
- Mark slow or network-dependent tests with `@pytest.mark.integration`.
- Mark error path tests with `@pytest.mark.error_handling`.
- Write docstrings on every test method.
- Test directory: `tests/gcal/` with `conftest.py` for shared fixtures
- Fixture data files stored in `tests/gcal/fixtures/`

## User Questions

_(None yet — record questions raised during requirements gathering and their answers here.)_

## Claude Questions

1. **`from_sdk()` → `from_api_response()`** — The Google Calendar API via `googleapiclient` returns plain Python dicts, not typed SDK objects. Renamed the classmethod to reflect this, consistent with the Gmail tool's `from_message()` pattern.
2. **No-argument behavior** — Clarified: bare `gcal` shows help; `gcal` with flags (e.g. `--verbose`) triggers pull as default operation.

## Pre-Build Tasks

1. Enable Google Calendar API in the existing Google Cloud project (shared with Gmail tool)
2. Add Calendar scope to the OAuth consent screen
3. Verify `credentials.json` exists at `src/config/gmail/credentials.json`
4. Verify `.gitignore` covers `data/gcal/token.json` and `data/gcal/`
