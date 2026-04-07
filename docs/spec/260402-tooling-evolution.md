# Tooling Evolution

## Context

This document captures the changes required to the tool architecture and the tool implementation standard outline based on decisions made in April 2026. The original standard was written from the Todoist perspective and applied uniformly to all tools. This document introduces a tool taxonomy, identifies what each type requires, and specifies how the standard outline must be updated to accommodate the differences.

---

## Tool Taxonomy

Tools in the deep-thought namespace are not all the same shape. The standard outline needs to guide implementation based on what type of tool is being built.

### Collector

Periodically fetches content from an external source, tracks what has been seen to avoid reprocessing, and writes output to markdown files. No write-back to the source.

Examples: Reddit, Web, Stack Exchange, YouTube, Gmail, GCal (read-only mode), Audio

State DB: Yes — flat state tracking table, not relational  
Embeddings: Depends on content type (see below)

### Bidirectional Collector

A collector that can also write back to the source. Requires full relational schema, sync semantics, and conflict detection.

Examples: Todoist, GCal (create/update/delete)

State DB: Yes — relational, multiple tables, sync state tracking  
Embeddings: No — operational/personal data, not knowledge content

### Converter

Processes input you explicitly provide (files, URLs). Does not poll for new content. No state needed — if you give it the same input again, it just converts again.

Examples: File-txt, Audio (when used as a one-off converter)

State DB: No  
Embeddings: No

### Generative

Creates output via an external API based on a prompt or spec. Tracks what has been generated to support idempotency and avoid re-generating the same thing.

Examples: Krea, ElevenLabs, APNG

State DB: Yes — flat table keyed by a hash of the generation parameters  
Embeddings: No — tracks output, not knowledge content

---

## Which Tools Write to the Embedding Store

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

## Changes to the Tool Implementation Standard Outline

The following describes how each section of `files/templates/tool-requirements/tool-implementation-standard-outline.md` must be updated.

### Section 1 — Planning and Requirements

**Add:** Identify the tool type (Collector, Bidirectional Collector, Converter, Generative) as a required step before specifying storage or sync behavior. Tool type determines which sections of the outline apply.

**Add:** Specify whether the tool writes to the embedding store. This is a requirements-time decision, not an implementation detail.

---

### Section 2 — Project Structure

**Add:** The `db/` subdirectory is only present for tools that require a state database. Converters do not have a `db/` subdirectory.

**Add:** Tools that write embeddings include an `embeddings.py` module responsible for content preparation and Qdrant writes. This module follows the interface established by the Workflow Architect.

Updated structure for a collector with embeddings:

```
src/deep_thought/{tool}/
├── __init__.py
├── cli.py
├── config.py
├── models.py
├── processor.py
├── filters.py
├── output.py
├── llms.py
├── client.py
├── embeddings.py          ← new: content prep + Qdrant write
└── db/
    ├── __init__.py
    ├── schema.py
    ├── queries.py
    └── migrations/
        └── 001_init_schema.sql
```

---

### Section 5 — Database Layer

**Current behavior:** Mandates SQLite for all tools with WAL mode, FK enabled, migration system, and the full `created_at` / `updated_at` / `synced_at` timestamp pattern.

**Required change:** Section 5 must be gated by tool type.

**Bidirectional Collectors** — full relational schema applies as-is. Multiple entity tables, foreign keys, cascades, `created_at` / `updated_at` / `synced_at` timestamps, migration system, sync state tracking. This is the Todoist pattern and it is correct for this type.

**Collectors (knowledge and operational)** — flat state tracking only. One table with a composite `state_key` primary key, `output_path`, `status`, and minimal timestamps. WAL mode and FK pragma are still applied but FK relationships are rarely needed. No JSON snapshots required. The elaborate schema ceremony inherited from Todoist is not warranted here.

**Generative tools** — flat table keyed by a hash of the generation parameters. Tracks what was generated, where output lives, and current status. No timestamps beyond `created_at` and `updated_at`. No `synced_at` — there is no external source to sync against.

**Converters** — no database. Skip this section entirely.

---

### Section 7 — Sync Operations

**Current behavior:** Describes pull, push, and sync as standard operations implying all tools support bidirectional sync.

**Required change:** This section applies only to Bidirectional Collectors. All other types either collect only (no push) or process on demand (no sync concept at all).

Rename or reframe as: "Sync Operations (Bidirectional Collectors only)."

For standard Collectors, replace with a simpler "Collection Operation" note: fetch, filter, write state, write output. No push, no sync token, no conflict detection.

---

### Section 9 — Export

No structural change required. Clarify that "export" for Collectors means the markdown file written at collection time — it is not a separate step run after the fact. The Todoist pattern (collect to DB, then export from DB as a separate command) is specific to bidirectional tools where the DB is the canonical store. For Collectors, the markdown file is written during the collection run.

---

### New Section — Embedding Integration

Insert after Section 9. Applies only to tools that write to the embedding store.

**When to embed.** At collection time, immediately after the markdown file is written. Embedding is part of the collection pipeline, not a post-processing step.

**What to embed.** The content that represents the document's meaning: title, body text, and the most substantive portion of any threaded content (top comments, accepted answers, etc.). Strip frontmatter before embedding — metadata is stored as Qdrant payload, not embedded into the vector.

**The `embeddings.py` module.**

- `prepare_content(document) -> str` — extracts and formats the text to embed
- `write_embedding(content, payload, output_path)` — calls the embedding model and upserts to Qdrant
- The embedding model and Qdrant client are initialized once and passed in — not instantiated inside the module

**Payload fields written to Qdrant** (in addition to the shared fields defined by the Workflow Architect):

- `source_tool` — the tool name
- `source_type` — content category for the tool (blog, article, forum_post, q_and_a, research)
- `output_path` — path to the markdown file
- `rule_name` — which config rule collected this document
- `collected_date` — ISO timestamp
- Tool-specific filter fields (e.g. `subreddit`, `site`, `domain`) — only those expected to be used in filtered queries

**Interface contract.** The Workflow Architect defines the shared embedding interface: which model, which Qdrant collection, how to initialize the client, what the upsert call looks like. The tool's `embeddings.py` calls that interface — it does not configure infrastructure.

**Error handling.** An embedding failure must not fail the collection run. Log the error, record the document as collected in the state DB, and continue. The document exists on disk even if the embedding failed; it can be re-embedded in a repair run.

---

### Section 13 — Testing

**Add:** For tools with embedding integration, tests must mock the Qdrant client and the embedding model call. Verify that `embeddings.py` prepares content correctly and calls the interface with the right payload fields. Do not test the embedding model itself or the Qdrant infrastructure — those are integration concerns.

**Add:** For Converters with no state DB, the existing in-memory SQLite fixture pattern does not apply. Tests operate directly on input/output without any database setup.

---

## What Does Not Change

Sections 3 (Configuration), 4 (Data Models), 6 (API Client), 8 (Filtering), 10 (CLI), 11 (Error Handling), 12 (Type Safety and Code Style), 14 (Documentation), and 15 (Progress Display) apply uniformly across all tool types with no structural changes required.

---

## Refactoring vs. Rebuilding Assessment

### Framing

"Rebuilding" means discarding the existing implementations and writing them again from scratch. "Refactoring" means modifying existing code to align with the new architecture. Both are worth evaluating before committing to either.

The existing tools are working. The quality gate has run 13 times and the codebase is at 2094 passing tests. The patterns are over-engineered in places but not wrong — they function correctly and are well tested. Any refactoring decision must weigh the cost of disrupting stable, tested code against the benefit gained.

---

### Two Categories of Change

The changes implied by this document fall into two categories with very different risk profiles.

**Additive changes** — new capability layered onto existing tools without altering what already exists. Low risk. Existing tests continue to pass untouched.

**Invasive changes** — modifying the internals of existing tools: the DB layer, the data models, the query interfaces. High risk. Existing tests break and must be rewritten.

These are not the same decision. They should be evaluated and sequenced independently.

---

### Additive Changes: Embedding Integration

**Status: Complete (2026-04-02)**

Added embedding support to Reddit, Web, and Research:

- `src/deep_thought/embeddings.py` — shared infrastructure module (model init, Qdrant client init, `write_embedding()`, `strip_frontmatter()`)
- `src/deep_thought/reddit/embeddings.py`, `web/embeddings.py`, `research/embeddings.py` — per-tool modules
- One guarded call added to each processor/CLI after the markdown write
- 44 new tests across 6 test files
- Schema reference at `files/tools/embeddings/260402-qdrant-schema.md`

Infrastructure established by the cross-tool-architect:

- Qdrant running as a persistent binary service (`~/bin/qdrant`, storage at `~/qdrant_storage`)
- Collection: `deep_thought_db`, 384-dim COSINE, 6 indexed payload fields
- Embedding model: `mlx-community/bge-small-en-v1.5-bf16` via `mlx-embeddings` (optional extra)
- Both `qdrant-client` and `mlx-embeddings` in `[embeddings]` optional extra — install with `uv sync --extra embeddings`

Embedding failures are isolated: logged as a warning, collection continues. Documents exist on disk regardless of embedding outcome.

---

### Invasive Changes: DB Layer Simplification

The five existing collectors (Reddit, Web, Gmail, GCal, Audio) all carry SQLite infrastructure that is heavier than their actual needs. Each has `schema.py`, `queries.py`, `migrations/`, and tests that fixture against the database. The data they track is flat — a single table with a primary key — but they were built following the Todoist pattern which assumes relational complexity.

Simplifying these would mean:

- Rewriting `db/schema.py`, `db/queries.py`, and migration files per tool
- Updating processors to use the new query interfaces
- Rewriting all DB-touching tests per tool — which is a significant portion of each tool's test suite
- Running Quality Gate after each tool to verify nothing regressed

**Per tool this is non-trivial.** The test rewrite is the dominant cost. Tests that fixture against the DB are numerous and interconnected — changing the schema means changing every fixture, every mock, every assertion that touches stored data.

**What is gained:** Less code, simpler maintenance, clearer architecture. What is not gained: any new capability. The tools work correctly today. Simplifying the DB layer does not make them faster, more reliable, or able to do anything they cannot currently do.

**Assessment:** The cost is high and the benefit is architectural cleanliness, not functional improvement. This is not worth doing as a dedicated refactoring effort.

---

### New Tools: Build Forward

Tools not yet built — Stack Exchange, YouTube, Krea, ElevenLabs, APNG — have no legacy to respect. They are built once, correctly, following the updated taxonomy and standard outline from day one.

Stack Exchange is a Collector with embeddings: flat state DB, `embeddings.py` included from the start, no migration ceremony beyond what the pattern requires.

Krea, ElevenLabs, APNG are Generative: flat state DB keyed by parameter hash, no embeddings, no sync operations.

YouTube is a Collector: flat state DB, embeddings TBD based on content type decision.

**Assessment:** No cost. New tools simply follow the right pattern. This is where the updated standard outline pays its dividend — every new tool is built leaner than the existing ones without any refactoring effort.

---

### Tool-by-Tool Summary

| Tool           | Status    | Additive work                    | Invasive work               | Recommendation                                          |
| -------------- | --------- | -------------------------------- | --------------------------- | ------------------------------------------------------- |
| Reddit         | Built     | ~~Add `embeddings.py`~~ **Done** | Simplify DB layer           | Skip DB simplification.                                 |
| Web            | Built     | ~~Add `embeddings.py`~~ **Done** | Simplify DB layer           | Skip DB simplification.                                 |
| Research       | Built     | ~~Add `embeddings.py`~~ **Done** | Nothing (already stateless) | Complete.                                               |
| Gmail          | Built     | None                             | Simplify DB layer           | No changes needed.                                      |
| GCal           | Built     | None                             | Simplify DB layer           | No changes needed.                                      |
| Audio          | Built     | None                             | Simplify DB layer           | No changes needed.                                      |
| File-txt       | Built     | None                             | None                        | Complete. (`marker-pdf` → `pymupdf4llm`, 2026-04-02)    |
| Todoist        | Built     | None                             | None                        | No changes needed. Schema is correct for its type.      |
| Stack Exchange | Not built | N/A                              | N/A                         | Build correctly from start: Collector with embeddings.  |
| YouTube        | Not built | N/A                              | N/A                         | Build correctly from start: Collector, embeddings TBD.  |
| Krea           | Not built | N/A                              | N/A                         | Build correctly from start: Generative, no embeddings.  |
| ElevenLabs     | Not built | N/A                              | N/A                         | Build correctly from start: Generative, no embeddings.  |
| APNG           | Not built | N/A                              | N/A                         | Build correctly from start: type TBD from requirements. |

---

### Recommendation

**Do not rebuild anything.** The existing tools are correct, tested, and in use. Rebuilding eight working tools to gain architectural cleanliness is not justified.

**Do not refactor the DB layer as a dedicated effort.** The invasive changes are high cost, zero functional gain, and high risk to a stable test suite. If a tool is being significantly modified for another reason — a new feature that requires touching the DB layer anyway — that is the right moment to simplify it. Not before.

**DB simplification reviewed 2026-04-05 — deferred decision stands.** Verified that Reddit, Web, Gmail, GCal, and Audio all retain the full `created_at` / `updated_at` / `synced_at` timestamp pattern and migration system. No simplification was performed. The deferred recommendation above remains the correct call.

**Embedding integration is complete** for Reddit, Web, and Research. Cross-tool semantic search is now available via `uv sync --extra embeddings`. The Qdrant collection `deep_thought_db` is running locally.

**Build all new tools following the updated taxonomy.** The standard outline changes pay off entirely on new builds. Stack Exchange, YouTube, Krea, ElevenLabs, and any future tools get the right architecture from the start without any refactoring cost ever being incurred.
