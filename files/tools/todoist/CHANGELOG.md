# Changelog

All notable changes to the Todoist Tool will be documented in this file.

## [Unreleased]

### Added

- Initial project scaffolding and directory structure
- Database schema with tables for projects, sections, tasks, labels, task_labels, comments, and sync_state
- Configuration loader with YAML and .env support
- Local data models mirroring Todoist SDK entities
- Todoist API client wrapper
- Pull, push, and sync operations
- Meta-based filter engine
- Markdown export for LLM consumption
- CLI with subcommands: pull, push, sync, status, diff, export, config, init, create, complete
- `create` subcommand — create a new task via the Todoist API and write it to the local database immediately
- `complete` subcommand — close a task via the Todoist API and update the local database (sets is_completed, completed_at, updated_at, synced_at); accepts the task ID shown in export output after `id:`; supports the global `--dry-run` flag
- `DEEP_THOUGHT_DATA_DIR` environment variable — redirects all data storage (database, snapshots, export) to a specified path; defaults to `data/todoist/` at the project root
