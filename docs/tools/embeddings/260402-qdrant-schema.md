# Qdrant Schema Reference — deep_thought_db

**Date:** 2026-04-19
**Audience:** Python Developer implementing per-tool `embeddings.py` modules
**Source of truth for:** collection configuration, payload contract, `write_embedding()` call patterns, query patterns, and error handling expectations
**Ingest version:** `INGEST_VERSION = 2` (see `src/deep_thought/embeddings.py`). Increment when the payload contract changes in a way that breaks downstream consumers.

---

## 0. Collection Setup

### Server prerequisites

The Qdrant server (v1.17.1) runs as a macOS LaunchAgent and starts automatically at login. Binary is at `~/bin/qdrant`, storage at `~/qdrant_storage`, logs at `~/qdrant_storage/qdrant.log`.

To manage the service manually:

```bash
launchctl start com.williamtrekell.qdrant   # start
launchctl stop com.williamtrekell.qdrant    # stop
launchctl list | grep qdrant                # check status
```

The LaunchAgent plist is at `~/Library/LaunchAgents/com.williamtrekell.qdrant.plist`. The `qdrant-client` Python package (v1.17.1) must match the server's minor version — install via `uv sync --extra embeddings`.

### Collection initialization

`ensure_collection()` in `src/deep_thought/embeddings.py` handles all initialization automatically. Every tool calls it before writing embeddings. It is fully idempotent:

- Creates the collection if it does not exist
- Inspects the collection's existing payload schema and creates any missing indexes
- Safe to call on every run — no manual bootstrap required

This applies to every collection name, including named collections configured via `qdrant_collection` in per-tool YAML configs. No separate setup step is needed when pointing a tool at a new collection.

To verify the current state of any collection:

```bash
uv run python -c "
from qdrant_client import QdrantClient
c = QdrantClient(host='localhost', port=6333)
print(c.get_collection('deep_thought_db'))
"
```

---

## 1. Collection Overview

| Property              | Value                                  |
| --------------------- | -------------------------------------- |
| Collection name       | `deep_thought_db`               |
| Vector dimensions     | `384`                                  |
| Distance metric       | `Cosine`                               |
| Storage type          | Dense                                  |
| Embedding model       | `mlx-community/bge-small-en-v1.5-bf16` |
| Qdrant host           | `localhost`                            |
| Qdrant port           | `6333`                                 |
| Qdrant server version | `1.17.1`                               |
| qdrant-client version | `1.17.1`                               |

The collection is shared across all tools. There is one collection, not one per tool. Tool identity is carried in the `source_tool` payload field and filtered at query time.

---

## 2. Payload Field Table

Every point stored in `deep_thought_db` carries a payload. A document is split into one or more **chunks** at ingest, and each chunk is its own Qdrant point. All chunks of a document share the same `canonical_id` and `parent_id` and differ by `chunk_index`. The fields below are the full contract. Fields marked **indexed** have a Qdrant payload index and can be used in filtered searches efficiently.

| Field name         | Type     | Indexed | Populated by  | Example value                                     |
| ------------------ | -------- | ------- | ------------- | ------------------------------------------------- |
| `source_tool`      | keyword  | yes     | all           | `reddit`                                          |
| `source_type`      | keyword  | yes     | all           | `forum_post`                                      |
| `rule_name`        | keyword  | yes     | all           | `rust_jobs`                                       |
| `collected_date`   | datetime | yes     | all           | `2026-04-02T14:30:00Z`                            |
| `title`            | keyword  | yes     | all           | `Ask HN: What does your Rust stack look like?`    |
| `parent_id`        | keyword  | yes     | all (auto)    | `https://www.reddit.com/r/rust/comments/1abcdef/` |
| `embedding_model`  | keyword  | yes     | all (auto)    | `bge-small-en-v1.5`                               |
| `canonical_id`     | keyword  | no      | all (auto)    | `https://www.reddit.com/r/rust/comments/1abcdef/` |
| `chunk_index`      | integer  | no      | all (auto)    | `0`                                               |
| `chunk_count`      | integer  | no      | all (auto)    | `3`                                               |
| `chunk_text`       | text     | no      | all (auto)    | `In Rust async, errors propagate via Result…`     |
| `ingest_version`   | integer  | no      | all (auto)    | `2`                                               |
| `output_path`      | keyword  | no      | all (when given) | `/Users/wt/data/reddit/rust/260402-some-post.md` |
| `subreddit`        | keyword  | no      | reddit        | `rust`                                            |
| `post_id`          | keyword  | no      | reddit        | `1abcdef`                                         |
| `author`           | keyword  | no      | reddit        | `ferris_the_crab`                                 |
| `score`            | integer  | no      | reddit, stackexchange | `842`                                     |
| `upvote_ratio`     | float    | no      | reddit        | `0.97`                                            |
| `comment_count`    | integer  | no      | reddit        | `134`                                             |
| `flair`            | keyword  | no      | reddit        | `Discussion`                                      |
| `url`              | keyword  | no      | web, reddit, stackexchange | `https://www.reddit.com/r/rust/comments/1abcdef/` |
| `domain`           | keyword  | no      | web           | `docs.rust-lang.org`                              |
| `status_code`      | integer  | no      | web           | `200`                                             |
| `word_count`       | integer  | no      | reddit, web, gmail | `1204`                                       |
| `message_id`       | keyword  | no      | gmail         | `<CAFx…@mail.gmail.com>`                          |
| `from_address`     | keyword  | no      | gmail         | `noreply@example.com`                             |
| `question_id`      | integer  | no      | stackexchange | `12345`                                           |
| `site`             | keyword  | no      | stackexchange | `stackoverflow`                                   |
| `answer_count`     | integer  | no      | stackexchange | `5`                                               |
| `query`            | keyword  | no      | research      | `What are the best practices for Rust async?`     |
| `mode`             | keyword  | no      | research      | `search`                                          |
| `model`            | keyword  | no      | research      | `sonar`                                           |
| `recency`          | keyword  | no      | research      | `month`                                           |
| `source_count`     | integer  | no      | research      | `8`                                               |

**Notes:**

- Fields marked **all (auto)** are added to every chunk's payload by `write_embedding()` itself — callers must not set them in the per-tool payload dict. They are: `canonical_id`, `parent_id`, `chunk_index`, `chunk_count`, `chunk_text`, `embedding_model`, `ingest_version`. `parent_id` always equals `canonical_id` and exists as a separate, indexed field for efficient chunk-group lookups.
- `output_path` is **advisory metadata only** as of `INGEST_VERSION = 2`. It is no longer indexed (filesystem paths are an implementation detail, not a query key). When the caller passes `output_path=` to `write_embedding()`, it is written into the payload of every chunk so existing readers continue to work; pass `None` to omit it.
- `collected_date` must be an ISO 8601 UTC string (e.g., `"2026-04-02T14:30:00Z"`). Qdrant's datetime index requires this format.
- Fields that are `no` for indexed are stored in the payload and returned with results, but cannot be used in efficient filtered searches. If a new query pattern emerges that filters on an unindexed field, a payload index must be added to the collection before that filter will perform acceptably.
- `flair`, `recency`, `status_code`, and `url` are nullable — omit from the payload dict when the value is `None` rather than passing `None` explicitly.
- All fields marked `indexed: yes` are created automatically by `ensure_collection()`. No manual bootstrap is required.
- Payload storage uses `on_disk_payload: true` to keep RAM bounded while still letting `chunk_text` be returned with hits.

---

## 3. `write_embedding()` Call Pattern

### Function signature (from `src/deep_thought/embeddings.py`)

```python
def write_embedding(
    content: str,
    payload: dict[str, Any],
    canonical_id: str,
    model: Any,
    qdrant_client: Any,
    output_path: str | None = None,
    collection_name: str = COLLECTION_NAME,
) -> None:
```

**Critical constraints:**

- `canonical_id` is **required** and must be a stable identifier for the source document — the URL of a web page, the permalink of a Reddit post, the Gmail message-id, the Stack Exchange question link, or for the research tool the synthesized `f"{mode}:{query}@{processed_date}"`. It is what makes re-ingest idempotent across file moves and what groups all chunks of a document together.
- Do not include `canonical_id`, `parent_id`, `chunk_index`, `chunk_count`, `chunk_text`, `embedding_model`, or `ingest_version` in the `payload` dict — `write_embedding()` adds them to every chunk's payload itself. Setting them in the caller's dict is redundant and will be overwritten.
- Do not include `output_path` in the `payload` dict either. Pass it as the `output_path=` kwarg if you have one; the function copies it into each chunk's payload. Pass `None` (or omit) to leave it out entirely.

`write_embedding()` chunks `content` into ~350-word chunks with 50-word overlap (paragraph-boundary aware via `chunk_text()`), embeds each chunk separately, and upserts each as its own Qdrant point. Before upserting it deletes any prior chunks for the same `canonical_id`, so a re-ingest replaces the document atomically and never accumulates stale chunks when content shrinks.

The `model` and `qdrant_client` arguments should be constructed once per collection run using `create_embedding_model()` and `create_qdrant_client()`, then reused for every `write_embedding()` call. Do not instantiate them inside a loop.

---

### Reddit tool

**What gets embedded (`content`):** The full markdown body of the post file, with YAML frontmatter stripped using `strip_frontmatter()` from `embeddings.py`.

**`canonical_id`:** `CollectedPostLocal.url` — the post's permalink, stable across file moves.

**`output_path`:** The value from `CollectedPostLocal.output_path` (advisory metadata only).

```python
from deep_thought.embeddings import strip_frontmatter, write_embedding

reddit_payload: dict[str, Any] = {
    "source_tool": "reddit",
    "source_type": "forum_post",
    "rule_name": collected_post.rule_name,
    "collected_date": collected_post.created_at,
    "title": collected_post.title,
    "subreddit": collected_post.subreddit,
    "post_id": collected_post.post_id,
    "author": collected_post.author,
    "score": collected_post.score,
    "upvote_ratio": collected_post.upvote_ratio,
    "comment_count": collected_post.comment_count,
    "url": collected_post.url,
    "word_count": collected_post.word_count,
}
if collected_post.flair is not None:
    reddit_payload["flair"] = collected_post.flair

markdown_content = output_file_path.read_text(encoding="utf-8")

write_embedding(
    content=strip_frontmatter(markdown_content),
    payload=reddit_payload,
    canonical_id=collected_post.url,
    output_path=collected_post.output_path,
    model=embedding_model,
    qdrant_client=qdrant_connection,
    collection_name=COLLECTION_NAME,
)
```

---

### Web tool

**What gets embedded (`content`):** The full markdown body of the crawled page file, with YAML frontmatter stripped using `strip_frontmatter()`.

**`canonical_id`:** `CrawledPageLocal.url` — the page URL, stable across file moves.

**`output_path`:** The value from `CrawledPageLocal.output_path` (advisory metadata only).

**`source_type`** depends on the crawl mode that produced the page (see section 4).

```python
from deep_thought.embeddings import strip_frontmatter, write_embedding

web_payload: dict[str, Any] = {
    "source_tool": "web",
    "source_type": source_type_for_mode,  # see section 4
    "rule_name": crawled_page.rule_name or "",
    "collected_date": crawled_page.created_at,
    "title": crawled_page.title or "",
    "url": crawled_page.url,
    "word_count": crawled_page.word_count,
}
if crawled_page.status_code is not None:
    web_payload["status_code"] = crawled_page.status_code

markdown_content = output_file_path.read_text(encoding="utf-8")

write_embedding(
    content=strip_frontmatter(markdown_content),
    payload=web_payload,
    canonical_id=crawled_page.url,
    output_path=crawled_page.output_path,
    model=embedding_model,
    qdrant_client=qdrant_connection,
    collection_name=COLLECTION_NAME,
)
```

---

### Gmail tool

**What gets embedded (`content`):** The full markdown body of the exported message file, with YAML frontmatter stripped.

**`canonical_id`:** `ProcessedEmailLocal.message_id` — the Gmail message-id, stable across file moves.

**`output_path`:** The value from `ProcessedEmailLocal.output_path` (advisory metadata only).

```python
from deep_thought.embeddings import strip_frontmatter, write_embedding

gmail_payload: dict[str, Any] = {
    "source_tool": "gmail",
    "source_type": "email",
    "rule_name": processed_email.rule_name,
    "collected_date": processed_email.created_at,
    "title": processed_email.subject,
    "message_id": processed_email.message_id,
    "from_address": processed_email.from_address,
    "word_count": len(stripped_content.split()),
}

write_embedding(
    content=stripped_content,
    payload=gmail_payload,
    canonical_id=processed_email.message_id,
    output_path=processed_email.output_path,
    model=embedding_model,
    qdrant_client=qdrant_connection,
    collection_name=COLLECTION_NAME,
)
```

---

### Stack Exchange tool

**What gets embedded (`content`):** The full markdown body of the exported Q&A file, with YAML frontmatter stripped.

**`canonical_id`:** `CollectedQuestionLocal.link` — the question's canonical URL, stable across file moves.

**`output_path`:** The value from `CollectedQuestionLocal.output_path` (advisory metadata only).

```python
from deep_thought.embeddings import strip_frontmatter, write_embedding

stackexchange_payload: dict[str, Any] = {
    "source_tool": "stackexchange",
    "source_type": "q_and_a",
    "rule_name": collected_question.rule_name,
    "collected_date": collected_question.created_at,
    "title": collected_question.title,
    "url": collected_question.link,
    "question_id": collected_question.question_id,
    "site": collected_question.site,
    "score": collected_question.score,
    "answer_count": collected_question.answer_count,
}

write_embedding(
    content=stripped_content,
    payload=stackexchange_payload,
    canonical_id=collected_question.link,
    output_path=collected_question.output_path,
    model=embedding_model,
    qdrant_client=qdrant_connection,
    collection_name=COLLECTION_NAME,
)
```

---

### Research tool

**What gets embedded (`content`):** `ResearchResult.answer` — the synthesized answer text returned by the Perplexity API. This is the substantive content to retrieve; source URLs are metadata, not the document body.

**`canonical_id`:** `f"{result.mode}:{result.query}@{result.processed_date}"` — encodes the mode, query, and processed timestamp so each research run is its own document. Re-running the exact same search at a different time produces a new canonical_id (and a new chunk set), which is the intended behavior — research answers reflect a point-in-time view of the web.

**`output_path`:** The path where the markdown output file was written (advisory metadata only).

**`rule_name`:** The research tool has no rule system (no SQLite, no rule config file). `rule_name` is always `""` (empty string). Do not pass a slugified query or any other label — the implementation always stores the empty string.

```python
from deep_thought.embeddings import write_embedding

research_payload: dict[str, Any] = {
    "source_tool": "research",
    "source_type": source_type_for_mode,  # see section 4
    "rule_name": "",
    "collected_date": research_result.processed_date,
    "title": research_result.query,
    "query": research_result.query,
    "mode": research_result.mode,
    "model": research_result.model,
    "source_count": len(research_result.search_results),
}
if research_result.recency is not None:
    research_payload["recency"] = research_result.recency

canonical_id = f"{research_result.mode}:{research_result.query}@{research_result.processed_date}"

write_embedding(
    content=research_result.answer,
    payload=research_payload,
    canonical_id=canonical_id,
    output_path=output_file_path,
    model=embedding_model,
    qdrant_client=qdrant_connection,
    collection_name=COLLECTION_NAME,
)
```

---

## 4. `source_type` Values

`source_type` encodes both the originating tool and the nature of the content. It is a primary filter dimension for Claude when narrowing retrieval to a content category.

| Tool          | Condition            | `source_type` value |
| ------------- | -------------------- | ------------------- |
| reddit        | all posts            | `forum_post`        |
| web           | mode `blog`          | `blog_post`         |
| web           | mode `documentation` | `documentation`     |
| web           | mode `direct`        | `article`           |
| gmail         | all messages         | `email`             |
| stackexchange | all questions        | `q_and_a`           |
| research      | mode `search`        | `research_search`   |
| research      | mode `research`      | `research_deep`     |

The web tool's mode is available from the rule configuration that drove the crawl. Map it at the call site before constructing the payload.

---

## 5. Query Patterns

Use `search_embeddings()` from `src/deep_thought/embeddings.py` for all retrieval. It handles embedding generation, optional filtering, and the Qdrant call in one step.

### Function signature

```python
def search_embeddings(
    query: str,
    model: Any,
    qdrant_client: Any,
    collection_name: str = COLLECTION_NAME,
    limit: int = 10,
    source_tool: str | None = None,
    source_type: str | None = None,
) -> list[Any]:
```

### Setup

```python
from deep_thought.embeddings import (
    create_embedding_model,
    create_qdrant_client,
    search_embeddings,
)

embedding_model = create_embedding_model()
qdrant_connection = create_qdrant_client()
```

**Note on results:** Each Qdrant point is a chunk, not a whole document. A single document with three chunks can return up to three hits sharing the same `parent_id`. To deduplicate by document, group results by `result.payload["parent_id"]` and keep the highest-scoring chunk per group. To pull all chunks for a single document, filter on `parent_id == <canonical_id>` (this is an indexed field).

### (a) Unfiltered search across all tools

Returns the top 10 most semantically similar chunks regardless of source.

```python
results = search_embeddings(
    query="best practices for async error handling in Rust",
    model=embedding_model,
    qdrant_client=qdrant_connection,
    limit=10,
)
```

### (b) Filtered search by `source_tool`

Returns results only from the reddit tool.

```python
results = search_embeddings(
    query="best practices for async error handling in Rust",
    model=embedding_model,
    qdrant_client=qdrant_connection,
    source_tool="reddit",
    limit=10,
)
```

### (c) Filtered search by `source_type`

Returns results only from deep research queries.

```python
results = search_embeddings(
    query="best practices for async error handling in Rust",
    model=embedding_model,
    qdrant_client=qdrant_connection,
    source_type="research_deep",
    limit=10,
)
```

Each result object has a `.payload` dict containing all stored metadata (including `chunk_text` for the matched chunk) and a `.score` float (cosine similarity, higher is more similar). `parent_id` is the canonical document identifier; `output_path`, when present, is an advisory pointer back to the markdown file on disk and may be stale if the file has since moved.

---

## 6. Error Handling Contract

`write_embedding()` does not catch exceptions internally. Any failure in embedding generation (MLX model error, out-of-memory) or Qdrant upsert (connection refused, timeout, schema mismatch) propagates directly to the caller.

**Required pattern in every per-tool embeddings module:**

```python
import logging

logger = logging.getLogger(__name__)

for collected_item in items_to_embed:
    try:
        write_embedding(
            content=content_for_item,
            payload=payload_for_item,
            canonical_id=canonical_id_for_item,
            output_path=collected_item.output_path,
            model=embedding_model,
            qdrant_client=qdrant_connection,
        )
    except Exception as embedding_error:
        logger.warning(
            "Embedding failed for %s — skipping. Error: %s",
            canonical_id_for_item,
            embedding_error,
        )
        continue
```

**Rules:**

- Never let a single embedding failure abort the collection run. Log and continue.
- Use `logger.warning`, not `logger.error`, for individual point failures. Reserve `logger.error` for failures that make the entire embedding pass impossible (e.g., model failed to load, Qdrant unreachable at startup).
- Do not retry failed embeddings inline. If retry logic is needed, handle it at a higher level with a queue of failed canonical_ids, not inside the per-item loop.
- Log the `canonical_id` in every warning so failures are traceable without further investigation. Logging the `output_path` as well is fine if the caller has it.

### Client lifecycle

Every CLI that creates a `QdrantClient` must close it explicitly in a `finally` block so Qdrant's `__del__` does not emit a `RuntimeWarning: Unable to close http connection` at interpreter shutdown.

```python
qdrant_client = None
try:
    qdrant_client = create_qdrant_client()
    # … run the collection …
finally:
    if qdrant_client is not None:
        try:
            qdrant_client.close()
        except Exception as qdrant_close_err:
            logger.debug("QdrantClient close() raised: %s", qdrant_close_err)
```

The `qdrant_client = None` declaration must be **outside** the try block so the `finally` clause can always reference it, even if `create_qdrant_client()` itself raises. Close failures are logged at DEBUG and never surfaced to the user — the run has already succeeded by the time `finally` runs.

---

## 7. Point ID Scheme

A document is split into N chunks and each chunk is its own Qdrant point. Each chunk's ID is derived deterministically from the document's `canonical_id` plus the chunk index:

```python
import uuid

# Computed inside write_embedding() per chunk:
point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{canonical_id}#chunk-{chunk_index}"))
```

Callers do not provide a point ID — they pass the `canonical_id` (the URL of the source page, the Reddit permalink, the Gmail message-id, the Stack Exchange question link, or the research tool's `f"{mode}:{query}@{processed_date}"`) and `write_embedding()` derives every chunk's ID from it.

**Why this matters:**

- **Idempotent re-embedding across file moves.** Because the ID is anchored to the canonical source identifier (not the disk path), re-ingesting a document after its markdown file has been renamed or relocated updates the same chunks rather than orphaning the old points and creating a duplicate set. This was the schema-fragility problem fixed in #46.
- **Stale-chunk cleanup is automatic.** Before upserting the new chunk set, `write_embedding()` issues a `delete` filtered by `parent_id == canonical_id`. If a re-ingest produces fewer chunks than the previous version (e.g., the source content was edited down), the leftover points from the prior write are removed in the same call. No manual cleanup or chunk-count tracking is required.
- **Chunks of a document are queryable as a group.** All chunks share `parent_id = canonical_id` (an indexed field). To pull every chunk of a document, filter on `parent_id`.
- **No ID management required.** Callers never query Qdrant to look up an existing ID before writing. The same canonical_id always produces the same set of chunk UUIDs (for the same chunk count).

**Migration note.** Pre-#46 points written under `INGEST_VERSION = 1` derived their IDs from `output_path` and have no `chunk_text`, `parent_id`, or `ingest_version` fields. They coexist with new points if the same collection is reused — they will surface in searches but lack the new payload fields. Recommended one-time clean-up: delete the old collection (or all points missing `ingest_version`) and re-run each tool's collection to re-ingest from the canonical SQLite stores. The `embedding_model` and `ingest_version` fields make this filterable from a future cleanup script.
