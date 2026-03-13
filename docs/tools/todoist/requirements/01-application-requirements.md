# Product Brief — Todoist Tool

## Name and Purpose

**Todoist Tool** — bidirectional sync between Todoist and LLM-optimized markdown files.

## Sync Modes

1. **CLI Command** -
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

> Provide a list of all commands and flags recommended for the Todoist tool.

## File & Output Map

> Provide a standardized directory structure for all files associated with the Todoist tool.

## Data Format

> Provide a standardized format for all data associated with the Todoist tool.

## User Questions

1. Is it possible to create non-human collaborators?
   1. Example: Collaborator name: Claude

## Claude Questions

1.
