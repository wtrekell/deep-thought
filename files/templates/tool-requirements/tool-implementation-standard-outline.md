# Tool Implementation Standard — Outline

Expanded document to standardize future tool builds in deep-thought.

---

## 1. Planning and Requirements

- Define the tool's purpose and scope
- Identify external API or data source
- Specify sync direction: read, write, or bidirectional
- List entities the tool must model
- Document CLI subcommands and their behavior
- Define configuration options and defaults
- Specify LLM-optimized export format requirements
- Write requirements doc before any code

## 2. Project Structure

- Create subpackage under `src/deep_thought/<tool>/`
- Follow src layout with hatchling build backend
- Separate database layer into `db/` subpackage
- Place migrations in `db/migrations/` with numeric prefixes
- Store configuration YAML in `src/config/`
- Store data artifacts in `data/<tool>/`
- Place documentation in `docs/tools/<tool>/`
- Add test directory mirroring source structure

## 3. Configuration

- Use YAML for all tool configuration
- Reference secrets by env var name, never values
- Load `.env` automatically via `load_dotenv()`
- Build dataclass hierarchy mirroring YAML structure
- Write separate parser per config section
- Default to permissive settings (empty filters)
- Separate validation from loading; return issue lists
- Support CLI overrides for key config values

## 4. Data Models

- Create local dataclasses mirroring API entities
- Add `from_sdk()` classmethod for API conversion
- Add `to_dict()` method for database insertion
- Unpack nested API objects into scalar fields
- Rename API reserved words consistently (e.g., `order`)
- Use type-safe helper functions for conversions
- Suffix local model names with `Local`

## 5. Database Layer

- Use SQLite with WAL mode and foreign keys
- Store all IDs as TEXT (API string IDs)
- Include `created_at`, `updated_at`, `synced_at` on all tables
- Use `INSERT OR REPLACE` for upsert operations
- Set `synced_at` locally; preserve API timestamps
- Add indexes on all foreign key columns
- Use cascading deletes for referential integrity
- Track schema version in a key-value table
- Apply migrations sequentially by numeric prefix
- Locate database at `data/<tool>/<tool>.db`

## 6. API Client

- Wrap SDK in thin client class
- Collapse pagination into flat list returns
- Pass write operations through with `**kwargs`
- Keep client free of business logic
- Store SDK instance as private attribute

## 7. Sync Operations

- Pull: API to local models to DB
- Push: modified DB rows to API
- Sync: pull then push sequentially
- Detect modifications via timestamp comparison (`updated_at > synced_at`)
- Write JSON snapshots after each pull
- Commit database in single transaction per operation
- Return typed result dataclasses with operation counts

## 8. Filtering

- Apply filters after fetch, before database write
- Use include/exclude semantics for all filter types
- Empty filter lists mean no constraint applied
- List fields: match if any value present
- Scalar fields: match exact value in list
- Null values never satisfy non-empty include lists
- Keep filter logic as pure functions

## 9. Export

- Optimize output format for Claude, not humans
- Write one file per logical grouping (e.g., section)
- Include metadata only when values are non-null
- Sanitize directory and file names for filesystem safety
- Use consistent key-value syntax in output
- Place exports in `data/<tool>/export/`

## 10. CLI

- Use argparse with subparsers for commands
- Define global flags: `--dry-run`, `--verbose`, `--config`
- Map subcommands to handler functions via dispatch dict
- Print typed result objects to stdout
- Catch specific exceptions with descriptive messages
- Return proper exit codes (0 success, 1 error)

## 11. Error Handling

- Raise `FileNotFoundError` for missing config files
- Raise `OSError` for missing environment variables
- Raise `ValueError` for invalid configuration content
- Use top-level try/except in CLI entry point
- Let database errors bubble up from migrations
- Never silently swallow exceptions

## 12. Type Safety and Code Style

- Use `from __future__ import annotations` everywhere
- Use `TYPE_CHECKING` blocks for expensive imports
- Annotate all function signatures (mypy strict)
- Use 120-character line length
- Prefix private functions with underscore
- Prefix module-level constants with underscore
- Suffix result types with `Result`

## 13. Testing

- Use in-memory SQLite for database tests
- Provide populated database fixtures with seed data
- Mock external SDK objects with `MagicMock`
- Organize tests in classes by feature area
- Write docstrings on every test method
- Mark tests: `slow`, `integration`, `error_handling`
- Create helper functions for building test objects

## 14. Documentation

- Write requirements doc before implementation
- Document API model reference for SDK entities
- Maintain changelog with unreleased section
- Keep CLAUDE.md updated with tool-specific commands
- Store all docs in `docs/tools/<tool>/`
