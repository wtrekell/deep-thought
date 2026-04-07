# Embeddings Infrastructure Changelog

## 2026-04-06

### Added

- `search_embeddings(query, model, qdrant_client, collection_name, limit, source_tool, source_type)` in `src/deep_thought/embeddings.py` — performs semantic vector search against the Qdrant collection. Embeds the query, applies optional `source_tool` and `source_type` filters, and returns a list of `ScoredPoint` objects with `.payload` metadata and `.score` cosine similarity. Replaces the hand-written query patterns documented in the schema reference with a single callable interface.

### Changed

- `mode` field removed from `PAYLOAD_INDEX_FIELDS` in `src/deep_thought/embeddings.py`. Only the research tool writes this field, and its two values (`search`, `research`) are already fully covered by the cross-tool `source_type` field (`research_search`, `research_deep`). The index was redundant. Existing collections retain their `mode` index; new collections will not have one. The field still appears in research payloads as unindexed metadata.
- Web tool now always writes `title` to embedding payloads (previously omitted when a page had no HTML title). Defaults to an empty string, consistent with the `rule_name` field. Prevents silent misses when querying by `title`.

## 2026-04-05

### Added

- `ensure_collection(qdrant_client, collection_name)` in `src/deep_thought/embeddings.py` — checks whether the named collection exists and creates it with the configured vector dimensions and cosine distance if not. Called once per run from each tool's CLI after the client is initialized. Eliminates the need for manual collection setup.
- `collection_name` parameter on `write_embedding()` (default: `COLLECTION_NAME`) — replaces the previously hardcoded module constant. All per-tool embedding modules (`web/embeddings.py`, `reddit/embeddings.py`, `research/embeddings.py`) accept and thread this parameter through to the shared function.

### Changed

- Qdrant collection name is now configurable per tool via a `qdrant_collection` field in each tool's YAML config. All three tools default to `"deep_thought_db"` — no existing configs require changes. Web batch configs in `src/config/web/` can each specify a different collection, enabling separate corpora per crawl.

## 2026-04-04

### Changed

- Updated Qdrant server binary from v1.14.0 to v1.17.1 to match the installed `qdrant-client` version and resolve a compatibility warning raised on every connection. The 3-minor-version gap exceeded Qdrant's supported tolerance (client and server major versions must match; minor version difference must not exceed 1). Old binary retained at `~/bin/qdrant.1.14.0.bak`.
- `qdrant-client` 1.17.1 is now the confirmed working client version (installed via `uv sync --extra embeddings`).
- Configured Qdrant to start automatically at login via a macOS LaunchAgent (`~/Library/LaunchAgents/com.williamtrekell.qdrant.plist`). The service runs from `~/qdrant_storage`, restarts automatically on crash, and logs to `~/qdrant_storage/qdrant.log`. No manual startup required after this change.
- Fixed `EMBEDDING_MODEL_ID` in `src/deep_thought/embeddings.py` — changed from `mlx-community/bge-small-en-v1.5-mlx` (non-existent HuggingFace repo) to `mlx-community/bge-small-en-v1.5-bf16`. The `-mlx` suffix variant was never published; all four available variants (`4bit`, `6bit`, `8bit`, `bf16`) output 384-dim embeddings matching the Qdrant collection config. `bf16` selected as the full-precision option closest to the original intent.
- Updated `create_embedding_model()` and `embed_text()` in `src/deep_thought/embeddings.py` to match the current `mlx-embeddings` API. `load()` now returns a `(model, tokenizer)` tuple; the previous `mlx_embeddings.embed()` function no longer exists. `embed_text()` now uses `prepare_inputs()` + model forward pass + mean pooling over the token dimension to produce 384-dim vectors. All callers are unchanged.
