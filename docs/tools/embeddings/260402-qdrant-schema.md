# Qdrant Schema Reference — deep_thought_documents

**Date:** 2026-04-02
**Audience:** Python Developer implementing per-tool `embeddings.py` modules
**Source of truth for:** collection configuration, payload contract, `write_embedding()` call patterns, query patterns, and error handling expectations

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

The `deep_thought_documents` collection must be created before any tool can write embeddings. There is no auto-creation — `write_embedding()` calls `upsert()` directly and will fail if the collection does not exist.

Run this once on a fresh Qdrant instance:

```bash
uv run python - <<'EOF'
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PayloadSchemaType

client = QdrantClient(host="localhost", port=6333)

client.create_collection(
    collection_name="deep_thought_documents",
    vectors_config=VectorParams(size=384, distance=Distance.COSINE),
)

indexed_fields = {
    "output_path":    PayloadSchemaType.KEYWORD,
    "source_tool":    PayloadSchemaType.KEYWORD,
    "source_type":    PayloadSchemaType.KEYWORD,
    "rule_name":      PayloadSchemaType.KEYWORD,
    "collected_date": PayloadSchemaType.DATETIME,
    "title":          PayloadSchemaType.KEYWORD,
    "mode":           PayloadSchemaType.KEYWORD,
}

for field, schema in indexed_fields.items():
    client.create_payload_index(
        collection_name="deep_thought_documents",
        field_name=field,
        field_schema=schema,
    )

print("Collection and payload indexes created.")
EOF
```

This is a one-time operation. Running it again on an existing collection will raise `UnexpectedResponse` — that is safe to ignore if you know the collection already exists. To check:

```bash
uv run python -c "
from qdrant_client import QdrantClient
c = QdrantClient(host='localhost', port=6333)
print(c.get_collection('deep_thought_documents'))
"
```

---

## 1. Collection Overview

| Property | Value |
|---|---|
| Collection name | `deep_thought_documents` |
| Vector dimensions | `384` |
| Distance metric | `Cosine` |
| Storage type | Dense |
| Embedding model | `mlx-community/bge-small-en-v1.5-bf16` |
| Qdrant host | `localhost` |
| Qdrant port | `6333` |
| Qdrant server version | `1.17.1` |
| qdrant-client version | `1.17.1` |

The collection is shared across all tools. There is one collection, not one per tool. Tool identity is carried in the `source_tool` payload field and filtered at query time.

---

## 2. Payload Field Table

Every point stored in `deep_thought_documents` carries a payload. The fields below are the full contract. Fields marked **indexed** have a Qdrant payload index and can be used in filtered searches efficiently.

| Field name | Type | Indexed | Populated by | Example value |
|---|---|---|---|---|
| `output_path` | keyword | yes | all | `/Users/wt/data/reddit/rust/260402-some-post.md` |
| `source_tool` | keyword | yes | all | `reddit` |
| `source_type` | keyword | yes | all | `forum_post` |
| `rule_name` | keyword | yes | all | `rust_jobs` |
| `collected_date` | datetime | yes | all | `2026-04-02T14:30:00Z` |
| `title` | keyword | yes | all | `Ask HN: What does your Rust stack look like?` |
| `subreddit` | keyword | yes | reddit | `rust` |
| `post_id` | keyword | no | reddit | `1abcdef` |
| `author` | keyword | no | reddit | `ferris_the_crab` |
| `score` | integer | no | reddit | `842` |
| `upvote_ratio` | float | no | reddit | `0.97` |
| `comment_count` | integer | no | reddit | `134` |
| `flair` | keyword | no | reddit | `Discussion` |
| `url` | keyword | no | web, reddit | `https://www.reddit.com/r/rust/comments/1abcdef/` |
| `status_code` | integer | no | web | `200` |
| `word_count` | integer | no | reddit, web | `1204` |
| `query` | keyword | no | research | `What are the best practices for Rust async?` |
| `mode` | keyword | yes | research | `search` |
| `model` | keyword | no | research | `sonar` |
| `recency` | keyword | no | research | `month` |
| `source_count` | integer | no | research | `8` |

**Notes:**

- `output_path` is injected automatically by `write_embedding()` — do not include it in the `payload` dict passed to the function. It will be merged in by the function itself.
- `collected_date` must be an ISO 8601 UTC string (e.g., `"2026-04-02T14:30:00Z"`). Qdrant's datetime index requires this format.
- Fields that are `no` for indexed are stored in the payload and returned with results, but cannot be used in efficient filtered searches. If a new query pattern emerges that filters on an unindexed field, a payload index must be added to the collection before that filter will perform acceptably.
- `flair`, `recency`, `status_code`, and `url` are nullable — omit from the payload dict when the value is `None` rather than passing `None` explicitly.

---

## 3. `write_embedding()` Call Pattern

### Function signature (from `src/deep_thought/embeddings.py`)

```python
def write_embedding(
    content: str,
    payload: dict[str, Any],
    output_path: str,
    model: Any,
    qdrant_client: Any,
) -> None:
```

**Critical constraint:** Do not include `output_path` in the `payload` dict. The function injects it automatically. Duplicating it will result in the payload carrying two `output_path` keys.

The `model` and `qdrant_client` arguments should be constructed once per collection run using `create_embedding_model()` and `create_qdrant_client()`, then reused for every `write_embedding()` call. Do not instantiate them inside a loop.

---

### Reddit tool

**What gets embedded (`content`):** The full markdown body of the post file, with YAML frontmatter stripped using `strip_frontmatter()` from `embeddings.py`.

**`output_path`:** The value from `CollectedPostLocal.output_path`.

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
    output_path=collected_post.output_path,
    model=embedding_model,
    qdrant_client=qdrant_connection,
)
```

---

### Web tool

**What gets embedded (`content`):** The full markdown body of the crawled page file, with YAML frontmatter stripped using `strip_frontmatter()`.

**`output_path`:** The value from `CrawledPageLocal.output_path`.

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
    output_path=crawled_page.output_path,
    model=embedding_model,
    qdrant_client=qdrant_connection,
)
```

---

### Research tool

**What gets embedded (`content`):** `ResearchResult.answer` — the synthesized answer text returned by the Perplexity API. This is the substantive content to retrieve; source URLs are metadata, not the document body.

**`output_path`:** The path where the markdown output file was written, from `SearchCommandResult.output_path` or `ResearchCommandResult.output_path`.

**`rule_name`:** The research tool is stateless (no SQLite, no rule config file driving collection). Use the slugified query as a stable stand-in, or pass an explicit label if the calling context has one. A reasonable default is `"research"` when no rule context exists.

```python
from deep_thought.embeddings import write_embedding

research_payload: dict[str, Any] = {
    "source_tool": "research",
    "source_type": source_type_for_mode,  # see section 4
    "rule_name": rule_label,              # slugified query or caller-supplied label
    "collected_date": research_result.processed_date,
    "title": research_result.query,
    "query": research_result.query,
    "mode": research_result.mode,
    "model": research_result.model,
    "source_count": len(research_result.search_results),
}
if research_result.recency is not None:
    research_payload["recency"] = research_result.recency

write_embedding(
    content=research_result.answer,
    payload=research_payload,
    output_path=output_file_path,
    model=embedding_model,
    qdrant_client=qdrant_connection,
)
```

---

## 4. `source_type` Values

`source_type` encodes both the originating tool and the nature of the content. It is a primary filter dimension for Claude when narrowing retrieval to a content category.

| Tool | Condition | `source_type` value |
|---|---|---|
| reddit | all posts | `forum_post` |
| web | mode `blog` | `blog_post` |
| web | mode `documentation` | `documentation` |
| web | mode `direct` | `article` |
| research | mode `search` | `research_search` |
| research | mode `research` | `research_deep` |

The web tool's mode is available from the rule configuration that drove the crawl. Map it at the call site before constructing the payload.

---

## 5. Query Patterns

All search calls follow the same three-step structure: embed the query text, build an optional filter, call `search` on the client.

```python
from deep_thought.embeddings import (
    COLLECTION_NAME,
    create_embedding_model,
    create_qdrant_client,
    embed_text,
)
from qdrant_client.models import Filter, FieldCondition, MatchValue

embedding_model = create_embedding_model()
qdrant_connection = create_qdrant_client(host="localhost", port=6333)

query_text = "best practices for async error handling in Rust"
query_vector = embed_text(query_text, embedding_model)
```

### (a) Unfiltered search across all tools

Returns the top 10 most semantically similar documents regardless of source.

```python
unfiltered_results = qdrant_connection.search(
    collection_name=COLLECTION_NAME,
    query_vector=query_vector,
    limit=10,
)
```

### (b) Filtered search by `source_tool`

Returns results only from the reddit tool.

```python
source_tool_filter = Filter(
    must=[
        FieldCondition(
            key="source_tool",
            match=MatchValue(value="reddit"),
        )
    ]
)

reddit_results = qdrant_connection.search(
    collection_name=COLLECTION_NAME,
    query_vector=query_vector,
    query_filter=source_tool_filter,
    limit=10,
)
```

### (c) Filtered search by `source_type`

Returns results only from deep research queries.

```python
source_type_filter = Filter(
    must=[
        FieldCondition(
            key="source_type",
            match=MatchValue(value="research_deep"),
        )
    ]
)

deep_research_results = qdrant_connection.search(
    collection_name=COLLECTION_NAME,
    query_vector=query_vector,
    query_filter=source_type_filter,
    limit=10,
)
```

Each result object has a `.payload` dict containing all stored metadata and a `.score` float (cosine similarity, higher is more similar). The `output_path` in the payload is the canonical pointer back to the markdown file on disk.

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
            output_path=collected_item.output_path,
            model=embedding_model,
            qdrant_client=qdrant_connection,
        )
    except Exception as embedding_error:
        logger.warning(
            "Embedding failed for %s — skipping. Error: %s",
            collected_item.output_path,
            embedding_error,
        )
        continue
```

**Rules:**

- Never let a single embedding failure abort the collection run. Log and continue.
- Use `logger.warning`, not `logger.error`, for individual point failures. Reserve `logger.error` for failures that make the entire embedding pass impossible (e.g., model failed to load, Qdrant unreachable at startup).
- Do not retry failed embeddings inline. If retry logic is needed, handle it at a higher level with a queue of failed paths, not inside the per-item loop.
- Log the `output_path` in every warning so failures are traceable without further investigation.

---

## 7. Point ID Scheme

```python
import uuid

point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, output_path))
```

This is computed inside `write_embedding()` — callers do not provide a point ID. The ID is derived deterministically from `output_path`.

**Why this matters:**

- **Idempotent re-embedding.** If a document is collected again (re-crawl, re-run), calling `write_embedding()` with the same `output_path` will upsert the existing point rather than create a duplicate. The vector and payload are updated in place.
- **No ID management required.** Callers never need to query Qdrant to look up an existing ID before writing. The same path always produces the same UUID.
- **Stable cross-session references.** Claude can store a point ID from one query and retrieve the same point later, because the ID does not change as long as the file path does not change.

If a file is moved or renamed, its `output_path` changes and `write_embedding()` will create a new point. The old point with the original path-derived ID will remain in the collection and should be deleted explicitly if the old path is no longer valid.
