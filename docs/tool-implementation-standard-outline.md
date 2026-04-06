# Tool Implementation Standard — Outline

Expanded document to standardize future tool builds in deep-thought.

---

## Tool Taxonomy

All tools in the deep-thought namespace fall into one of four types. Identify the type before writing requirements — it determines which sections of this outline apply.

### Collector

Periodically fetches content from an external source. Tracks what has been seen to avoid reprocessing. No write-back to the source.

Examples: Reddit, Web, Stack Exchange, YouTube, Gmail, GCal (read-only mode), Audio

| Attribute      | Value                                                                                                                       |
| -------------- | --------------------------------------------------------------------------------------------------------------------------- |
| State DB       | Yes — flat state tracking table, not relational                                                                             |
| Sync direction | Read-only                                                                                                                   |
| Embeddings     | Yes, if the content is knowledge (informs Claude's reasoning). No, if the content is operational or personal (Gmail, GCal). |

### Bidirectional Collector

A collector that can also write back to the source. Requires full relational schema, sync semantics, and conflict detection.

Examples: Todoist, GCal (create/update/delete)

| Attribute      | Value                                                  |
| -------------- | ------------------------------------------------------ |
| State DB       | Yes — relational, multiple tables, sync state tracking |
| Sync direction | Read + write                                           |
| Embeddings     | No — operational/personal data, not knowledge content  |

### Converter

Processes input you explicitly provide (files, URLs). Does not poll for new content. No state needed — if you give it the same input again, it just converts again.

Examples: File-txt, Audio (one-off conversion mode)

| Attribute      | Value                              |
| -------------- | ---------------------------------- |
| State DB       | No                                 |
| Sync direction | None — triggered by explicit input |
| Embeddings     | No                                 |

### Generative

Creates output via an external API from a prompt or spec. Tracks what has been generated to support idempotency and avoid re-generating identical output.

Examples: Krea, ElevenLabs, APNG

| Attribute      | Value                                                         |
| -------------- | ------------------------------------------------------------- |
| State DB       | Yes — flat table keyed by a hash of the generation parameters |
| Sync direction | Write-only (to external API)                                  |
| Embeddings     | No — tracks output, not knowledge content                     |

### Which Tools Write to the Embedding Store

Only collectors that produce knowledge content write embeddings to Qdrant. The distinction is whether the content is meant to inform Claude's reasoning about a topic versus tracking personal, operational, or generated output.

| Tool           | Type                  | State DB    | Embeddings |
| -------------- | --------------------- | ----------- | ---------- |
| Reddit         | Collector             | Yes         | Yes        |
| Web            | Collector             | Yes         | Yes        |
| Stack Exchange | Collector             | Yes         | Yes        |
| Research       | Collector (stateless) | No          | Yes        |
| Gmail          | Collector             | Yes         | No         |
| GCal           | Bidirectional         | Yes         | No         |
| Todoist        | Bidirectional         | Yes         | No         |
| YouTube        | Collector             | Yes         | TBD        |
| Audio          | Converter / Collector | Conditional | No         |
| File-txt       | Converter             | No          | No         |
| Krea           | Generative            | Yes         | No         |
| ElevenLabs     | Generative            | Yes         | No         |

---

## Section Applicability by Tool Type

Not every section below applies to every tool type. Use this matrix to determine which sections are relevant.

| Section              | Collector                 | Bidirectional | Converter | Generative |
| -------------------- | ------------------------- | ------------- | --------- | ---------- |
| 1. Planning          | ✓                         | ✓             | ✓         | ✓          |
| 2. Project Structure | ✓                         | ✓             | ✓         | ✓          |
| 3. Configuration     | ✓                         | ✓             | ✓         | ✓          |
| 4. Data Models       | ✓                         | ✓             | ✓         | ✓          |
| 5. Database Layer    | Flat only                 | Relational    | —         | Flat only  |
| 6. API Client        | ✓                         | ✓             | If needed | ✓          |
| 7. Sync Operations   | —                         | ✓             | —         | —          |
| 8. Filtering         | ✓                         | ✓             | —         | —          |
| 9. Export            | ✓                         | ✓             | ✓         | —          |
| 10. CLI              | ✓                         | ✓             | ✓         | ✓          |
| 11. Error Handling   | ✓                         | ✓             | ✓         | ✓          |
| 12. Type Safety      | ✓                         | ✓             | ✓         | ✓          |
| 13. Testing          | ✓                         | ✓             | ✓         | ✓          |
| 14. Embeddings       | Knowledge collectors only | —             | —         | —          |
| 15. Documentation    | ✓                         | ✓             | ✓         | ✓          |

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

- Tool names use hyphens (e.g., `file-txt`); Python package and module names translate hyphens to underscores as required (e.g., `file_txt`); all other names — directories, config filenames, CLI entry points — follow the tool name using hyphens
- Create subpackage under `src/deep_thought/<tool>/` (underscored)
- Follow src layout with hatchling build backend
- Separate database layer into `db/` subpackage
- Place migrations in `db/migrations/` with numeric prefixes
- Store configuration YAML in `src/config/` named `<tool>-configuration.yaml`
- Store tool-specific additional configs (alternative rule sets, batch configs, credentials) in `src/config/<tool>/`
- Store data artifacts in `data/<tool>/`; support `DEEP_THOUGHT_DATA_DIR` env var to redirect the data root at runtime
- Tools that accept local file input default to `data/<tool>/input/` so the input path benefits from `DEEP_THOUGHT_DATA_DIR` redirection; note that this convention places user-provided files alongside tool-generated artifacts — revisit per tool if the distinction matters
- Place documentation in `files/tools/<tool>/`
- Include `models.py` for local dataclasses when the tool defines data models
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
- Bundle a default config template inside the tool's package (`src/deep_thought/<tool>/default-config.yaml`); this is the source of truth for defaults and the file that `init` copies out to the project-level location (`src/config/<tool>-configuration.yaml`)
- The `init` command must reference the bundled template — never the project-level config, which does not exist yet when `init` runs
- All other commands (`config`, tool-specific subcommands) read from the project-level config at `src/config/<tool>-configuration.yaml`
- **Symlink-aware path resolution:** Tools in deep-thought may be referenced from other repos via symlink. Config and data paths that target the _calling repo_ (project-level config, data directories) must resolve relative to the current working directory — never by traversing `__file__` parent directories, which would follow symlinks back to deep-thought. Paths that target files _bundled inside the package_ (e.g., `default-config.yaml`, source templates) should use `__file__`-relative resolution so they always find the template regardless of where the tool is invoked
- **config.py path helper pattern:** Every tool's `config.py` must define these module-level constants and two public helpers:
  - `_PACKAGE_DIR = Path(__file__).resolve().parent` — resolves to the package directory inside deep-thought (follows symlinks)
  - `_BUNDLED_DEFAULT_CONFIG = _PACKAGE_DIR / "default-config.yaml"` — bundled template
  - `_PROJECT_CONFIG_RELATIVE_PATH = Path("src") / "config" / "<tool>-configuration.yaml"` — relative path from any repo root
  - `get_bundled_config_path() -> Path` — returns `_BUNDLED_DEFAULT_CONFIG` (for `init` and `--save-config`)
  - `get_default_config_path() -> Path` — returns `Path.cwd() / _PROJECT_CONFIG_RELATIVE_PATH` (for all runtime commands)
- Tools with additional bundled source files (e.g., batch config templates) should locate those via `_PACKAGE_DIR`-relative paths, and write copies to cwd-relative destinations

## 4. Data Models

- Create local dataclasses mirroring API entities
- Add `from_sdk()` classmethod for API conversion (API tools only; omit for local processing tools)
- Add `to_dict()` method for database insertion
- Unpack nested API objects into scalar fields
- Rename API reserved words consistently (e.g., `order`)
- Use type-safe helper functions for conversions
- Suffix local model names with `Local`

## 5. Database Layer

> **Collector / Generative:** Use a flat single-table schema — one row per tracked item, keyed by a stable ID (Collectors) or a hash of generation parameters (Generative). No foreign keys, no cascading deletes, no relational complexity.
>
> **Bidirectional Collector:** Use a full relational schema with multiple entity tables, foreign keys, and sync state tracking as described below.
>
> **Converter:** No database layer.

- Use SQLite with WAL mode and foreign keys
- Store all IDs as TEXT (API string IDs)
- Include `created_at` and `updated_at` on all tables; add `synced_at` only for bidirectional sync tools
- Use `INSERT OR REPLACE` for upsert operations
- Set `synced_at` locally on API sync; preserve API timestamps
- Add indexes on all foreign key columns (relational schemas only)
- Use cascading deletes for referential integrity (relational schemas only)
- Track schema version in a key-value table
- Apply migrations sequentially by numeric prefix
- Locate database at `data/<tool>/<tool>.db` (underscored path, consistent with `DEEP_THOUGHT_DATA_DIR` override)

## 6. API Client

- Wrap SDK in thin client class
- Collapse pagination into flat list returns
- Pass write operations through with `**kwargs`
- Keep client free of business logic
- Store SDK instance as private attribute

## 7. Sync Operations

> **Bidirectional Collector only.** Collectors use a simpler fetch-and-store loop; Converters and Generative tools have no sync concept.

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
- Generate `.llms.txt` / `.llms-full.txt` files controlled by a `generate_llms_files` config setting, defaulting to `false`

## 10. CLI

- Use argparse with subparsers for commands
- Define global flags: `--dry-run`, `--verbose`, `--config`
- Map subcommands to handler functions via dispatch dict
- Print typed result objects to stdout
- Catch specific exceptions with descriptive messages
- Return proper exit codes: `0` success, `1` fatal error, `2` partial failure (some items errored)
- The `init` subcommand bootstraps a tool for first use in the _calling repo_: locates the bundled `default-config.yaml` inside the package (via `__file__`), copies it to `src/config/<tool>-configuration.yaml` relative to the current working directory, creates data directories under `data/<tool>/` (also cwd-relative, respecting `DEEP_THOUGHT_DATA_DIR`), and prints a summary of what was created — it must never attempt to load the project-level config as a prerequisite, since that file does not yet exist

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
- Include `conftest.py` for shared fixtures in each test directory
- Store test data files in `tests/<tool>/fixtures/`

## 14. Embeddings

> **Knowledge collectors only** (Reddit, Web, Stack Exchange, Research). All other tool types skip this section.

- Add a `embeddings.py` module to the tool's package (`src/deep_thought/<tool>/embeddings.py`)
- Call `write_embedding()` from `src/deep_thought/embeddings.py` (shared infrastructure) after each successful markdown write
- Embedding failures are isolated: log as a warning and continue — documents exist on disk regardless of embedding outcome
- The shared infrastructure handles model init, Qdrant client init, and `strip_frontmatter()` — the per-tool module only needs to call `write_embedding()` with the right payload fields
- Collection: `deep_thought_documents` (384-dim COSINE, 6 indexed payload fields — see `files/tools/embeddings/260402-qdrant-schema.md`)
- Embedding model: `mlx-community/bge-small-en-v1.5-bf16` via `mlx-embeddings` (`[embeddings]` optional extra)
- Install with `uv sync --extra embeddings`; Qdrant v1.17.1 runs as a persistent local binary service managed by a macOS LaunchAgent (`com.williamtrekell.qdrant`) — starts automatically at login, no manual startup required. Logs at `~/qdrant_storage/qdrant.log`.

## 15. Documentation

- Write requirements doc before implementation
- Document API model reference for SDK entities; link to official SDK documentation in requirements
- Maintain changelog with unreleased section
- Keep CLAUDE.md updated with tool-specific commands
- Store all docs in `files/tools/<tool>/`
