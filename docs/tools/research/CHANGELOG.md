# Research Tool — Changelog

## 0.1.2 — 2026-04-05

### Added

- `qdrant_collection` config option in `research-configuration.yaml`: name of the Qdrant collection to write embeddings to (default: `"deep_thought_documents"`). Enables routing research results to a separate collection from other tools.

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
