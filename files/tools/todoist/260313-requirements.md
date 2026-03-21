# Product Brief — Todoist Tool

## Name and Purpose

**Todoist Tool** — bidirectional sync between Todoist and LLM-optimized markdown files.

## Sync Modes

1. **CLI Command** — `todoist` (entry point with subcommands)
2. **Pull** — Pull tasks and projects from Todoist API, filter by rules documented in a YAML configuration file. (`todoist pull`)
3. **Push** — Push tasks and projects with changes back to Todoist. (`todoist push`)
4. **Bidirectional sync** — Run **pull then push** sequentially. (`todoist sync`)

## Requirements

1. Python 3.12 using `uv` as the package manager.
2. Use the official [Todoist SDK for Python](https://doist.github.io/todoist-api-python/).
3. Use SQLite for local **data storage**.
4. [Meta class](https://doist.github.io/todoist-api-python/models/#todoist_api_python.models.Meta) filtering rules for **push** and **pull** are user defined and stored in `src/config/todoist_configuration.yaml`.
5. All secrets are stored in `.env` file in the root directory or GitHub Secrets.
6. A changelog is maintained in the `docs/tools/todoist/CHANGELOG.md` file.

## Data Storage

### Database Requirements

1. Design tables around **Todoist entities**:
   - `projects`, `sections`, `tasks`, `labels`, `task_labels` (many‑to‑many), `comments`.
   - Each entity table uses the Todoist-issued string ID as primary key (`id TEXT NOT NULL PRIMARY KEY`).
   - Include timestamps (`created_at`, `updated_at` from API; `synced_at` set locally on write) for change tracking.
   - Keep a `sync_state` key-value table that stores:
     - Last sync time.
     - Schema version (migration number) for forward-only migration tracking.

2. Persist the raw SDK state:
   - Store a **JSON blob** of the full Todoist state per sync as a flat file as a debugging/backup mechanism, but treat the relational schema as canonical for queries.

## Command List

All operations use subcommands (not flags). Running `todoist` with no subcommand shows help.

| Subcommand       | Description                                              |
| ---------------- | -------------------------------------------------------- |
| `todoist pull`   | Pull tasks and projects from Todoist, apply filter rules |
| `todoist push`   | Push local changes back to Todoist                       |
| `todoist sync`   | Run pull then push sequentially                          |
| `todoist status` | Show sync state: last sync time, pending local changes   |
| `todoist diff`   | Show differences between local DB and last pull          |
| `todoist export` | Export current DB state to markdown files                |
| `todoist config` | Validate and display current YAML configuration          |
| `todoist init`   | Create DB, config file, and directory structure          |

| Global Flag        | Description                                             |
| ------------------ | ------------------------------------------------------- |
| `--dry-run`        | Show what would change without writing to Todoist or DB |
| `--verbose` / `-v` | Increase log output                                     |
| `--config <path>`  | Override default config file path                       |
| `--project <name>` | Limit operation to a specific project                   |

## File & Output Map

```
docs/tools/todoist/
├── 260313-requirements.md           # This document
├── api-model.md                     # SDK model reference
├── api-model-html.md                # Raw HTML source
└── CHANGELOG.md                     # Release history

src/config/
└── todoist_configuration.yaml       # Filter rules and sync settings

src/deep_thought/todoist/
├── __init__.py
├── cli.py                           # CLI entry point and argument parsing
├── client.py                        # Todoist SDK wrapper
├── config.py                        # YAML config loader and validation
├── models.py                        # Local dataclasses mirroring SDK models
├── pull.py                          # Pull logic: API → DB → markdown
├── push.py                          # Push logic: DB diff → API
├── sync.py                          # Orchestrates pull + push
├── export.py                        # DB → markdown file generation
├── filters.py                       # Meta-based filter rule engine
├── create.py                        # Create task via API and write to DB
└── db/
    ├── __init__.py
    ├── schema.py                    # Schema definitions and table creation
    ├── queries.py                   # Query functions consumed by app code
    └── migrations/                  # Forward-only migration SQL files
        └── 001_init_schema.sql

data/todoist/                        # Default root; override with DEEP_THOUGHT_DATA_DIR
├── todoist.db                       # SQLite database
├── snapshots/                       # Raw JSON blobs per sync
│   └── YYYY-MM-DDTHHMMSS.json
└── export/                          # Generated markdown files
    └── <project-name>/
        └── <section-name>.md
```

## Configuration

Configuration is stored in `src/config/todoist_configuration.yaml`. All values below are required unless marked optional.

```yaml
# Todoist API
todoist:
  api_token_env: "TODOIST_API_TOKEN" # Name of env var holding the API token

# Projects to sync (opt-in list)
projects:
  - name: "Project Name"
  - name: "Another Project"

# Meta class filter rules for pull and push
# These map to the Meta model attributes: assignee, deadline, due, labels, project, section
filters:
  pull:
    labels:
      include: [] # Only pull tasks with these labels (empty = all)
      exclude: [] # Exclude tasks with these labels
    projects:
      include: [] # Redundant with projects list above, but allows pull-specific overrides
    sections:
      include: [] # Only pull tasks in these sections by Todoist section ID (empty = all)
      exclude: []
    assignee:
      include: [] # Only pull tasks assigned to these Todoist user IDs (empty = all)
    due:
      has_due_date: null # true = only tasks with due dates, false = only without, null = all
  push:
    labels:
      include: []
      exclude: []
    assignee:
      include: [] # Only push tasks assigned to these Todoist user IDs (empty = all)
    conflict_resolution: "prompt" # How to handle conflicts: "prompt", "remote_wins", "local_wins"
    require_confirmation: true # Prompt user before pushing changes

# Comment sync settings (pull-only in v0.1; push not yet implemented)
comments:
  sync: true # Pull comments on synced tasks
  include_attachments: false # Include attachment metadata in comment sync (optional)

# Claude involvement markers
claude:
  label: "claude-code" # Label applied to tasks involving Claude
  role:
    repo: "" # Repository name (required when label is present)
    branch: "main" # Branch name (defaults to main if not provided)
```

## Data Format

All exported data is consumed exclusively by Claude via CLI. Formats are optimized for machine parsing, not human readability.

### Markdown Export

Each project produces a directory. Each section produces a file. Tasks use a structured, parseable format:

```markdown
# Project Name

## Section Name

- [ ] Task content
  - id: 1234567890
  - priority: 1
  - labels: label1, label2
  - due: 2026-03-15
  - recurring: every week
  - deadline: 2026-03-20
  - assignee: collaborator-name
  - claude: repo=deep-thought, branch=main
  - description: Task description text
  - comments:
    - [2026-03-10 poster-name] First comment text
    - [2026-03-11 poster-name] Second comment text
  - [ ] Subtask content
    - id: 1234567891
    - priority: 2
```

**Implementation notes:**

- Only one level of subtask nesting is rendered (grandchild tasks are not exported).
- The `assignee` and comment `poster-name` fields display Todoist user IDs (no local collaborator table exists).
- Only fields with non-null, non-empty values are included in the metadata list.

### JSON Snapshot

Full API response stored as-is per sync, named by ISO timestamp.

### SQLite Schema

Tables mirror the Todoist entities listed in the requirements: `projects`, `sections`, `tasks`, `labels`, `task_labels`, `comments`, and `sync_state`. Each entity table uses `id` (the Todoist-issued string ID) as the primary key. Entity tables include `synced_at` for tracking when the local database last received each record. `projects` and `tasks` additionally include `created_at` and `updated_at` from the API. The `tasks` table flattens nested SDK objects (`Due`, `Deadline`, `Duration`) into scalar columns (e.g., `due_date`, `due_string`, `deadline_date`). The SQL reserved word `order` is stored as `order_index` throughout.

## User Questions

1. Is it possible to create non-human collaborators?
   1. Example: Collaborator name: Claude
   2. **Answer:** No. The Todoist API ties collaborators to real user accounts via email. There is no endpoint to create a synthetic or non-human collaborator. The label-based approach in your answer to question 6 is the right workaround.
2. Is there a reason for /src to have a deep thought layer?
   1. **Answer:** Yes — `src/deep_thought/` exists because `pyproject.toml` names the package `deep-thought`, and hatchling (the build backend) expects a matching `src/deep_thought/` directory. This is the standard Python `src` layout: `src/<package_name>/`. The todoist tool would live at `src/deep_thought/todoist/`, making it importable as `deep_thought.todoist`. If you'd prefer a flatter structure (e.g., `src/todoist_tool/`), we'd need to rename the package — but since this repo may eventually hold multiple tools, nesting under `deep_thought` keeps things organized.

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

1. ~~Update data format section to reflect that data is only consumed by Claude.~~ Done — data format updated to note Claude-only consumption, markdown switched to key-value metadata for machine parsing.
2. ~~Add a configuration section to the requirements.~~ Done — Configuration section added above.
   1. ~~Add the configuration values indicated by the Todoist API class indicated in the requirements.~~ Done — Meta class filters (assignee, deadline, due, labels, project, section) mapped to pull/push filter rules.
   2. ~~Add the values that identify claude's involvement on a task or project.~~ Done — `claude.label`, `claude.role.repo`, `claude.role.branch` added.
   3. ~~Ensure it is clear that the branch value is main by default if none is provided.~~ Done — `branch: "main"` with comment noting the default.
