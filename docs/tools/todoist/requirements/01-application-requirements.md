# Product Brief — Todoist Tool

## Name and Purpose

**Todoist Tool** — bidirectional sync between Todoist and LLM-optimized markdown files.

## Sync Modes

1. **CLI Command** - `todoist`
2. **Pull** — Pull tasks and projects from Todoist API, filter by rules documented in a YAML configuration file. (`--pull`)
3. **Push** — Push tasks and projects with changes back to Todoist. (`--push`)
4. **Bidirectional sync** — Run **pull then push** (`--full-sync`)

## Requirements

1. Python 3.12 using `uv` as the package manager.
2. Use the official [Todoist SDK for Python](https://doist.github.io/todoist-api-python/).
3. Use SQLite for local **data storage**.
4. [Meta class](https://doist.github.io/todoist-api-python/models/#todoist_api_python.models.Meta) filtering rules for **push** and **pull** are user defined and stored in `configuration/todoist_configuration.yaml`.
5. All secrets are stored in `.env` file in the root directory or GitHub Secrets.
6. A changelog is maintained in the `/tool/todoist/CHANGELOG.md` file.

## Data Storage

### Database Requirements

1. Design tables around **Todoist entities**:
   - `projects`, `sections`, `tasks`, `labels`, `task_labels` (many‑to‑many), `comments`.
   - Include Todoist IDs and timestamps so you can map remote objects and reason about changes.
   - Keep a `sync_state` or `metadata` table that stores:
     - Last sync token from the SDK.
     - Versioning info in case you change your schema.

2. Persist the raw SDK state:
   - Store a **JSON blob** of the full Todoist state per sync as a flat file as a debugging/backup mechanism, but treat the relational schema as canonical for queries.

## Command List

| Command          | Flag          | Description                                              |
| ---------------- | ------------- | -------------------------------------------------------- |
| `todoist`        |               | Show help and available commands                         |
| `todoist pull`   | `--pull`      | Pull tasks and projects from Todoist, apply filter rules |
| `todoist push`   | `--push`      | Push local changes back to Todoist                       |
| `todoist sync`   | `--full-sync` | Run pull then push sequentially                          |
| `todoist status` |               | Show sync state: last sync time, pending local changes   |
| `todoist diff`   |               | Show differences between local DB and last pull          |
| `todoist export` |               | Export current DB state to markdown files                |
| `todoist config` |               | Validate and display current YAML configuration          |
| `todoist init`   |               | Create DB, config file, and directory structure          |

| Global Flag        | Description                                             |
| ------------------ | ------------------------------------------------------- |
| `--dry-run`        | Show what would change without writing to Todoist or DB |
| `--verbose` / `-v` | Increase log output                                     |
| `--config <path>`  | Override default config file path                       |
| `--project <name>` | Limit operation to a specific project                   |

## File & Output Map

```
docs/tools/todoist/
├── api-model.md                     # SDK model reference
├── api-model-html.md                # Raw HTML source
├── requirements/
│   └── 01-application-requirements.md
├── CHANGELOG.md                     # Release history
└── configuration/
    └── todoist_configuration.yaml   # Filter rules and sync settings

src/deep_thought/todoist/
├── __init__.py
├── cli.py                           # CLI entry point and argument parsing
├── client.py                        # Todoist SDK wrapper
├── config.py                        # YAML config loader and validation
├── database.py                      # SQLite schema, queries, migrations
├── models.py                        # Local dataclasses mirroring SDK models
├── pull.py                          # Pull logic: API → DB → markdown
├── push.py                          # Push logic: DB diff → API
├── sync.py                          # Orchestrates pull + push
├── export.py                        # DB → markdown file generation
└── filters.py                       # Meta-based filter rule engine

data/todoist/
├── todoist.db                       # SQLite database
├── snapshots/                       # Raw JSON blobs per sync
│   └── YYYY-MM-DDTHHMMSS.json
└── export/                          # Generated markdown files
    └── <project-name>/
        └── <section-name>.md
```

## Data Format

### Markdown Export

Each project produces a directory. Each section produces a file. Tasks are rendered as checkbox lists with metadata in a consistent format:

```markdown
# Project Name

## Section Name

- [ ] Task content `p1` `@label1` `@label2`
  - **Due:** 2026-03-15 (every week)
  - **Deadline:** 2026-03-20
  - **Assignee:** collaborator-name
  - **Description:** Task description text
  - [ ] Subtask content `p2`
```

### JSON Snapshot

Full API response stored as-is per sync, named by ISO timestamp.

### SQLite Schema

Tables mirror the Todoist entities listed in the requirements: `projects`, `sections`, `tasks`, `labels`, `task_labels`, `comments`, and `sync_state`. All tables include `todoist_id`, `created_at`, `updated_at`, and `synced_at` columns for change tracking.

## User Questions

1. Is it possible to create non-human collaborators?
   1. Example: Collaborator name: Claude
2. Is there a reason for /src to have a deep thought layer?

## Claude Questions

1. **Which projects should sync?** Opt in by listing projects in the config file.
2. **Conflict resolution on push:** Prompt the user.
3. **Comment handling:** Sync bidirectionally.
4. **Completed tasks:** Only pull active tasks.
5. **How should I interact with this tool?** You will run CLI commands directly and be the only consumer of the data.
6. **Collaborator question context:** Labels defined in config file are used to represent Claude's involvement on a task or project.
   ```yaml
   claude-code-role:
     - repo: { repo_name }
     - branch: { branch_name }
   ```

## Pre-Build Tasks

1. Update data format section to reflect that data is only consumed by Claude.
2. Add a configuration section to the requirements.
   1. Add the configuration values indicated by the Todoist API class indicated in the requirements.
   2. Add the values that identify claude's involvement on a task or project.
   3. Ensure it is clear that the branch value is main by default if none is provided.
