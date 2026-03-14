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
- CLI with subcommands: pull, push, sync, status, diff, export, config, init
