# Product Brief — {Tool Name}

## Name and Purpose

**{Tool Name}** — {one-sentence description of what the tool does}.

## Sync Modes

<!-- List all sync directions the tool supports. Remove rows that don't apply. -->

1. **CLI Command** — `{tool}` (entry point with subcommands)
2. **Pull** — {Describe what pull does and where data comes from}. (`{tool} pull`)
3. **Push** — {Describe what push does and where data goes}. (`{tool} push`)
4. **Bidirectional sync** — Run **pull then push** sequentially. (`{tool} sync`)

## Requirements

1. Python 3.12 using `uv` as the package manager.
2. {External SDK or API dependency, with link to docs}.
3. Use SQLite for local **data storage**.
4. {Filtering or rule system, if applicable — describe what drives include/exclude logic and where rules are stored}.
5. All secrets are stored in `.env` file in the root directory or GitHub Secrets.
6. A changelog is maintained in `docs/tools/{tool}/CHANGELOG.md`.

## Data Storage

### Database Requirements

1. Design tables around **{source} entities**:
   - {List entity tables, e.g. `projects`, `tasks`, `items`}.
   - Each entity table uses the {source}-issued string ID as primary key (`id TEXT NOT NULL PRIMARY KEY`).
   - Include timestamps (`created_at`, `updated_at` from API; `synced_at` set locally on write) for change tracking.
   - Keep a `sync_state` key-value table that stores:
     - Last sync time.
     - Schema version (migration number) for forward-only migration tracking.

2. Persist the raw SDK state:
   - Store a **JSON blob** of the full {source} state per sync as a flat file as a debugging/backup mechanism, but treat the relational schema as canonical for queries.

## Command List

All operations use subcommands (not flags). Running `{tool}` with no subcommand shows help.

| Subcommand         | Description                                              |
| ------------------ | -------------------------------------------------------- |
| `{tool} pull`      | Pull data from {source}, apply filter rules              |
| `{tool} push`      | Push local changes back to {source}                      |
| `{tool} sync`      | Run pull then push sequentially                          |
| `{tool} status`    | Show sync state: last sync time, pending local changes   |
| `{tool} diff`      | Show differences between local DB and last pull          |
| `{tool} export`    | Export current DB state to markdown files                |
| `{tool} config`    | Validate and display current YAML configuration          |
| `{tool} init`      | Create DB, config file, and directory structure          |

<!-- Add or remove subcommands as needed. -->

| Global Flag        | Description                                             |
| ------------------ | ------------------------------------------------------- |
| `--dry-run`        | Show what would change without writing to {source} or DB |
| `--verbose` / `-v` | Increase log output                                     |
| `--config <path>`  | Override default config file path                       |

<!-- Add tool-specific global flags as needed. -->

## File & Output Map

```
docs/tools/{tool}/
├── {YYMMDD}-requirements.md          # This document
├── api-model.md                      # SDK/API model reference
├── CHANGELOG.md                      # Release history
└── configuration/
    └── {tool}_configuration.yaml     # Filter rules and sync settings

src/deep_thought/{tool}/
├── __init__.py
├── cli.py                            # CLI entry point and argument parsing
├── client.py                         # {Source} SDK/API wrapper
├── config.py                         # YAML config loader and validation
├── models.py                         # Local dataclasses mirroring SDK models
├── pull.py                           # Pull logic: API → DB → markdown
├── push.py                           # Push logic: DB diff → API
├── sync.py                           # Orchestrates pull + push
├── export.py                         # DB → markdown file generation
├── filters.py                        # Filter rule engine
└── db/
    ├── __init__.py
    ├── schema.py                     # Schema definitions and table creation
    ├── queries.py                    # Query functions consumed by app code
    └── migrations/                   # Forward-only migration SQL files
        └── 001_init_schema.sql

data/{tool}/
├── {tool}.db                         # SQLite database
├── snapshots/                        # Raw JSON blobs per sync
│   └── YYYY-MM-DDTHHMMSS.json
└── export/                           # Generated markdown files
    └── {grouping}/                   # Organized by logical grouping
        └── {subgrouping}.md
```

<!-- Adjust the file tree to match the tool's actual structure. Remove modules that don't apply (e.g. push.py if write-only). -->

## Configuration

Configuration is stored in `configuration/{tool}_configuration.yaml`. All values below are required unless marked optional.

```yaml
# {Source} API
{tool}:
  api_token_env: "{TOOL}_API_TOKEN"   # Name of env var holding the API token

# {Entities} to sync (opt-in list)
{entities}:
  - name: "Entity Name"

# Filter rules for pull and push
# Map these to the API model attributes relevant to this tool
filters:
  pull:
    # {describe pull filter dimensions}
    example_field:
      include: []                     # Only pull items matching these values (empty = all)
      exclude: []                     # Exclude items matching these values
  push:
    # {describe push filter dimensions}
    conflict_resolution: "prompt"     # How to handle conflicts: "prompt", "remote_wins", "local_wins"
    require_confirmation: true        # Prompt user before pushing changes

# Claude involvement markers
claude:
  label: "claude-code"                # Label applied to items involving Claude
  role:
    repo: ""                          # Repository name (required when label is present)
    branch: "main"                    # Branch name (defaults to main if not provided)
```

<!-- Replace placeholders with tool-specific config values. Add or remove sections as needed. -->

## Data Format

All exported data is consumed exclusively by Claude via CLI. Formats are optimized for machine parsing, not human readability.

### Markdown Export

<!-- Define the export format. Use structured key-value metadata for machine parsing. -->

```markdown
# {Top-Level Grouping}

## {Sub-Grouping}

- [ ] Item content
  - id: 1234567890
  - {field}: {value}
  - {field}: {value}
```

**Implementation notes:**

- {Note any nesting limits, field display rules, or omission logic.}
- Only fields with non-null, non-empty values are included in the metadata list.

### JSON Snapshot

Full API response stored as-is per sync, named by ISO timestamp.

### SQLite Schema

<!-- Summarize the schema: list tables, primary key convention, timestamp columns, and any field-flattening or renaming decisions. -->

Tables mirror the {source} entities listed in the requirements: {list tables}. Each entity table uses `id` (the {source}-issued string ID) as the primary key. Entity tables include `synced_at` for tracking when the local database last received each record.

## User Questions

<!-- Record questions raised during requirements gathering and their answers. Number sequentially. -->

1. {Question}
   1. **Answer:** {Answer}

## Claude Questions

<!-- Record questions Claude asked during planning and the decisions made. -->

1. **{Question}** {Answer or decision.}

## Pre-Build Tasks

<!-- Checklist of tasks to complete before implementation begins. Strike through when done. -->

1. {Task description}
