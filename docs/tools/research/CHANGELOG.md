# Research Tool — Changelog

## [Unreleased]

### Changed

- Secret retrieval now checks macOS Keychain first, falling back to environment variables. Uses the shared `deep_thought.secrets` module.

## 0.1.3 — 2026-04-05

### Added

- `"3 months"` and `"6 months"` as valid `default_recency` values (and `--recency` CLI flag values).
  Both map to `"year"` at the Perplexity API level, which is the closest supported superset —
  Perplexity's `search_recency_filter` has no native sub-year option between `month` and `year`.
  The user-specified value is preserved in output frontmatter and Qdrant payloads for transparency.

## 0.1.2 — 2026-04-05

### Added

- `qdrant_collection` config option in `research-configuration.yaml`: name of the Qdrant collection to write embeddings to (default: `"deep_thought_db"`). Enables routing research results to a separate collection from other tools.

## 0.1.1 — 2026-03-30

### Changed

- Standardized export filename date prefix from `YYYY-MM-DD_` to `YYMMDD-` (e.g., `260323-what-is-mlx.md`).

## 0.1.0 — 2026-03-23

### Added

- Initial implementation of the Research Tool.
- `search` command: fast single-query web search via the Perplexity API.
- `research` command: deeper multi-step research with extended context.
- Perplexity API integration with configurable model selection.
- YAML frontmatter output with query metadata, model, cost, and processed date.
- Context file support: pass one or more local files to augment the query.
- `--quick` flag for printing results directly to stdout without saving a file.
- Recency filter option to restrict results to recent content.
- Domain filter option to restrict or exclude specific sources.
- Structured source citations and related follow-up questions in output.
