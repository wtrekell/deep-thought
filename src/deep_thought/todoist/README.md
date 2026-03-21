# Todoist Tool

Bidirectional sync between Todoist and LLM-optimized markdown files, with SQLite as the local data store.

## Overview

The Todoist Tool pulls tasks and projects from the Todoist API, stores them in a local SQLite database, and exports structured markdown files optimized for machine parsing. It can also push local changes back to Todoist.

## Data Flow

```
Todoist API → Local Models → Filters → SQLite DB → Markdown Export
                                          ↑
                                     Push (modified tasks back to API)
```

## Setup

1. Add your API token to a `.env` file at the project root:

   ```
   TODOIST_API_TOKEN=your_token_here
   ```

2. Configure which projects to sync in `src/config/todoist_configuration.yaml`.

3. Initialize the database:

   ```bash
   todoist init
   ```

4. Pull your first sync:

   ```bash
   todoist pull
   ```

## Configuration

Configuration lives at `src/config/todoist_configuration.yaml`. Key settings:

- **projects** — Opt-in list of Todoist project names to sync
- **filters.pull** — Rules for which tasks to include/exclude during pull (by label, section, assignee, due date)
- **filters.push** — Rules for which modified tasks to push back, plus conflict resolution strategy
- **comments** — Whether to sync comments (pull-only in v0.1)
- **claude** — Label and role metadata for tasks involving Claude

## Module Structure

| Module | Role |
| --- | --- |
| `cli.py` | CLI entry point with argparse subcommands |
| `client.py` | Thin wrapper around the Todoist SDK |
| `config.py` | YAML config loader with .env integration |
| `models.py` | Local dataclasses mirroring SDK models |
| `filters.py` | Meta-based filter engine for pull/push |
| `pull.py` | API → models → filters → DB upsert → JSON snapshot |
| `push.py` | DB diff → push filters → API calls → mark synced |
| `sync.py` | Orchestrator: pull then push |
| `export.py` | DB → structured markdown files |
| `create.py` | Create a new task via API and write it to DB immediately |
| `db/` | SQLite schema, migrations, and query functions |

## Data Storage

All paths are rooted at `data/todoist/` by default. Set `DEEP_THOUGHT_DATA_DIR` to redirect everything to a different location (useful for isolated test environments or running outside the repo).

- **SQLite database** — `<data_dir>/todoist.db` (canonical store)
- **JSON snapshots** — `<data_dir>/snapshots/` (one per sync, for debugging/backup)
- **Markdown export** — `<data_dir>/export/<project>/<section>.md`
