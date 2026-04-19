"""Shared embedding infrastructure for deep-thought knowledge collectors.

Provides the canonical embedding function, Qdrant client factory, chunking
helper, and search interface consumed by all tools that ingest content into
the shared ``deep_thought_db`` Qdrant collection.

All third-party imports are lazy (inside function bodies) so the module can
be imported without requiring mlx-embeddings or qdrant-client to be installed.

Schema versioning:
    The ``INGEST_VERSION`` constant is bumped whenever the chunking or payload
    schema changes in a way that should trigger a full re-ingest. Every point
    written by :func:`write_embedding` carries this version in its payload so
    a future cleanup pass can identify and remove stale-schema points.
"""

from __future__ import annotations

import re
import uuid
from typing import Any, cast

COLLECTION_NAME: str = "deep_thought_db"
EMBEDDING_MODEL_ID: str = "mlx-community/bge-small-en-v1.5-bf16"
EMBEDDING_MODEL_NAME: str = "bge-small-en-v1.5"
VECTOR_DIMENSIONS: int = 384

# Bump when the chunking strategy or payload schema changes in a way that
# should invalidate older points and trigger a re-ingest.
INGEST_VERSION: int = 2

# Chunking parameters. Word-based approximation of token budget — bge-small has
# a 512-token cap, so 350 words (~460 tokens) keeps full chunks below truncation
# with a 50-word overlap that preserves cross-chunk context.
DEFAULT_CHUNK_WORDS: int = 350
DEFAULT_CHUNK_OVERLAP_WORDS: int = 50

# Payload fields that must have a Qdrant index for efficient filtered queries.
# Values are PayloadSchemaType member names resolved lazily inside ensure_collection().
# ``output_path`` is intentionally absent — it is advisory metadata, not a filter key.
PAYLOAD_INDEX_FIELDS: dict[str, str] = {
    "source_tool": "KEYWORD",
    "source_type": "KEYWORD",
    "rule_name": "KEYWORD",
    "collected_date": "DATETIME",
    "title": "KEYWORD",
    "parent_id": "KEYWORD",
    "embedding_model": "KEYWORD",
}


def create_embedding_model() -> tuple[Any, Any]:
    """Load the MLX embedding model used for all document vectorization.

    Returns a ``(model, tokenizer)`` tuple that should be passed to
    :func:`embed_text` and :func:`write_embedding` for generating vectors.

    Returns:
        A tuple of ``(model, tokenizer)`` for the configured embedding model.

    Raises:
        ImportError: If the ``mlx-embeddings`` package is not installed.
    """
    import mlx_embeddings

    embedding_model_and_tokenizer: tuple[Any, Any] = mlx_embeddings.load(EMBEDDING_MODEL_ID)
    return embedding_model_and_tokenizer


def create_qdrant_client(host: str = "localhost", port: int = 6333) -> Any:
    """Create a Qdrant client connected to the specified host and port.

    Args:
        host: Hostname of the Qdrant server.
        port: HTTP port of the Qdrant server.

    Returns:
        A connected ``QdrantClient`` instance. Callers are responsible for
        closing the client (use ``contextlib.closing`` or a try/finally).
    """
    from qdrant_client import QdrantClient

    qdrant_connection: QdrantClient = QdrantClient(host=host, port=port)
    return qdrant_connection


def embed_text(text: str, model: tuple[Any, Any]) -> list[float]:
    """Generate an embedding vector for a single text string.

    Args:
        text: The text content to embed.
        model: The ``(model, tokenizer)`` tuple returned by
            :func:`create_embedding_model`.

    Returns:
        A list of floats representing the embedding vector with
        :data:`VECTOR_DIMENSIONS` elements.
    """
    import mlx.core as mx
    from mlx_embeddings.utils import prepare_inputs

    mlx_model, tokenizer = model
    inputs: Any = prepare_inputs(tokenizer, None, [text], 512, True, True)
    output: Any = mlx_model(**inputs)
    last_hidden_state: Any = output.last_hidden_state[0]
    embedding_vector: list[float] = cast("list[float]", mx.mean(last_hidden_state, axis=0).tolist())
    return embedding_vector


def strip_frontmatter(markdown_text: str) -> str:
    """Remove YAML frontmatter from the top of a markdown string.

    Frontmatter is delimited by ``---`` on its own line at the very start
    of the string and a closing ``---`` line. If the string does not begin
    with ``---``, it is returned unchanged.

    Args:
        markdown_text: Raw markdown content, possibly with YAML frontmatter.

    Returns:
        The markdown content with frontmatter removed and leading whitespace
        after the closing delimiter stripped.
    """
    if not markdown_text.startswith("---"):
        return markdown_text

    closing_delimiter_position = markdown_text.find("\n---", 3)
    if closing_delimiter_position == -1:
        return markdown_text

    end_of_frontmatter = closing_delimiter_position + 4
    remaining_content = markdown_text[end_of_frontmatter:]
    return remaining_content.lstrip("\n")


def chunk_text(
    text: str,
    max_words: int = DEFAULT_CHUNK_WORDS,
    overlap_words: int = DEFAULT_CHUNK_OVERLAP_WORDS,
) -> list[str]:
    """Split ``text`` into overlapping chunks of approximately ``max_words`` words.

    Paragraphs (separated by blank lines) are kept together when possible:
    chunks accumulate paragraphs until adding the next one would exceed
    ``max_words``. A paragraph longer than ``max_words`` on its own is
    split mid-paragraph on word boundaries. Successive chunks share the last
    ``overlap_words`` words of the prior chunk so cross-chunk semantics are
    preserved.

    Word counts are an approximation of the bge-small tokenizer's output
    (~1.3 tokens per English word). The default 350-word chunk maps to
    roughly 460 tokens — comfortably under the model's 512-token cap.

    Args:
        text: The text to split. An empty string returns an empty list.
        max_words: Soft upper bound on words per chunk.
        overlap_words: Words shared between consecutive chunks.

    Returns:
        A list of chunk strings. A short input (≤ ``max_words``) returns a
        single-element list containing the original text (whitespace
        normalized).
    """
    normalized_text = text.strip()
    if not normalized_text:
        return []

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", normalized_text) if p.strip()]
    if not paragraphs:
        return []

    chunks: list[str] = []
    current_words: list[str] = []

    def emit_current() -> None:
        if current_words:
            chunks.append(" ".join(current_words))

    for paragraph in paragraphs:
        paragraph_words = paragraph.split()
        if not paragraph_words:
            continue

        # Whole paragraph longer than the chunk budget — split on word
        # boundaries inside the paragraph itself.
        if len(paragraph_words) > max_words:
            emit_current()
            current_words = []
            window_start = 0
            while window_start < len(paragraph_words):
                window_end = window_start + max_words
                chunks.append(" ".join(paragraph_words[window_start:window_end]))
                if window_end >= len(paragraph_words):
                    break
                window_start = window_end - overlap_words
            continue

        # Adding this paragraph would overflow the current chunk — close out
        # the current chunk and seed the next chunk with the overlap window.
        if len(current_words) + len(paragraph_words) > max_words and current_words:
            emit_current()
            tail_overlap = current_words[-overlap_words:] if overlap_words > 0 else []
            current_words = [*tail_overlap, *paragraph_words]
        else:
            current_words.extend(paragraph_words)

    emit_current()
    return chunks


def ensure_collection(qdrant_client: Any, collection_name: str) -> None:
    """Create the Qdrant collection and all required payload indexes if absent.

    Checks for the collection by name before attempting creation, and inspects
    the existing payload schema before creating each index, making the function
    fully idempotent and safe to call on every run.  Any collection created
    through this function — including named collections configured via
    ``qdrant_collection`` in per-tool YAML configs — will have the correct
    payload indexes for efficient filtered queries.

    Args:
        qdrant_client: A Qdrant client returned by :func:`create_qdrant_client`.
        collection_name: The name of the collection to create if absent.
    """
    from qdrant_client.models import Distance, PayloadSchemaType, VectorParams  # noqa: PLC0415

    existing_collection_names = [c.name for c in qdrant_client.get_collections().collections]
    if collection_name not in existing_collection_names:
        qdrant_client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=VECTOR_DIMENSIONS, distance=Distance.COSINE),
        )

    collection_info = qdrant_client.get_collection(collection_name)
    existing_indexed_fields = set(collection_info.payload_schema.keys())

    schema_type_map: dict[str, Any] = {
        "KEYWORD": PayloadSchemaType.KEYWORD,
        "DATETIME": PayloadSchemaType.DATETIME,
    }
    for field_name, schema_type_key in PAYLOAD_INDEX_FIELDS.items():
        if field_name not in existing_indexed_fields:
            qdrant_client.create_payload_index(
                collection_name=collection_name,
                field_name=field_name,
                field_schema=schema_type_map[schema_type_key],
            )


def write_embedding(
    content: str,
    payload: dict[str, Any],
    canonical_id: str,
    model: Any,
    qdrant_client: Any,
    output_path: str | None = None,
    collection_name: str = COLLECTION_NAME,
) -> None:
    """Embed ``content`` (chunked) and upsert all chunks into the Qdrant collection.

    The text is split into overlapping chunks via :func:`chunk_text`. One Qdrant
    point is written per chunk, with a deterministic ID derived from
    ``canonical_id`` and the chunk index — re-ingesting the same canonical_id
    overwrites the prior chunks rather than creating duplicates. Any chunks
    that previously existed for ``canonical_id`` but are no longer produced
    (e.g. the source content shrank) are deleted before the upsert so the
    collection cannot accumulate orphan chunks.

    Each point's payload carries:

    - All fields from the caller-supplied ``payload`` dict
    - ``chunk_text`` — the literal text of this chunk
    - ``canonical_id`` — the stable document identifier
    - ``parent_id`` — same as ``canonical_id`` (indexed for chunk-group filters)
    - ``chunk_index`` / ``chunk_count`` — position and total
    - ``embedding_model`` — short marker (``"bge-small-en-v1.5"``) for
      migration-aware filtering when the model is upgraded
    - ``ingest_version`` — schema version bumped on breaking changes
    - ``output_path`` — advisory only when supplied; not indexed

    Args:
        content: The text content to embed and store.
        payload: Caller-supplied metadata fields. Must not include any of the
            reserved keys listed above — they are injected by this function.
        canonical_id: Stable, non-filesystem identifier for the source
            document (e.g. URL, message-id, question_id+site). Used as the
            UUID5 seed for every chunk's point ID.
        model: The MLX embedding model returned by :func:`create_embedding_model`.
        qdrant_client: A Qdrant client returned by :func:`create_qdrant_client`.
        output_path: Optional filesystem path of the source document. Stored
            as advisory metadata only.
        collection_name: The Qdrant collection to upsert into. Defaults to
            :data:`COLLECTION_NAME` (``"deep_thought_db"``).

    Raises:
        Any exception from chunking, embedding generation, or Qdrant
        delete/upsert is propagated to the caller without modification.
    """
    from qdrant_client.models import (  # noqa: PLC0415
        FieldCondition,
        Filter,
        FilterSelector,
        MatchValue,
        PointStruct,
    )

    chunks = chunk_text(content)
    if not chunks:
        return

    chunk_count = len(chunks)
    points: list[Any] = []
    for chunk_index, chunk_content in enumerate(chunks):
        vector = embed_text(chunk_content, model)
        point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{canonical_id}#chunk-{chunk_index}"))
        chunk_payload: dict[str, Any] = {
            **payload,
            "chunk_text": chunk_content,
            "canonical_id": canonical_id,
            "parent_id": canonical_id,
            "chunk_index": chunk_index,
            "chunk_count": chunk_count,
            "embedding_model": EMBEDDING_MODEL_NAME,
            "ingest_version": INGEST_VERSION,
        }
        if output_path is not None:
            chunk_payload["output_path"] = output_path
        points.append(PointStruct(id=point_id, vector=vector, payload=chunk_payload))

    # Drop any stale chunks left over from a prior ingest of the same canonical_id
    # (handles the chunk-count-shrank case and re-ingest of edited content).
    parent_id_filter = Filter(must=[FieldCondition(key="parent_id", match=MatchValue(value=canonical_id))])
    qdrant_client.delete(
        collection_name=collection_name,
        points_selector=FilterSelector(filter=parent_id_filter),
    )

    qdrant_client.upsert(collection_name=collection_name, points=points)


def search_embeddings(
    query: str,
    model: Any,
    qdrant_client: Any,
    collection_name: str = COLLECTION_NAME,
    limit: int = 10,
    source_tool: str | None = None,
    source_type: str | None = None,
) -> list[Any]:
    """Search the Qdrant collection for chunks semantically similar to query.

    Embeds the query text and performs a vector similarity search against the
    specified collection.  Optional ``source_tool`` and ``source_type`` filters
    narrow results to a specific origin or content category using the indexed
    payload fields.

    Each returned hit is a single chunk, not a whole document — multiple chunks
    of the same document may appear if they all match. Consumers that want
    one-result-per-document should deduplicate on ``payload["canonical_id"]``.

    Args:
        query: The natural-language query string to embed and search with.
        model: The ``(model, tokenizer)`` tuple returned by
            :func:`create_embedding_model`.
        qdrant_client: A Qdrant client returned by :func:`create_qdrant_client`.
        collection_name: The Qdrant collection to search. Defaults to
            :data:`COLLECTION_NAME` (``"deep_thought_db"``).
        limit: Maximum number of results to return. Defaults to 10.
        source_tool: Optional filter — restrict results to a single tool.
            Valid values: ``"reddit"``, ``"web"``, ``"research"``,
            ``"gmail"``, ``"stackexchange"``.
        source_type: Optional filter — restrict results to a single content type.
            Valid values: ``"forum_post"``, ``"blog_post"``, ``"documentation"``,
            ``"article"``, ``"research_search"``, ``"research_deep"``,
            ``"q_and_a"``, ``"email"``.

    Returns:
        A list of Qdrant ``ScoredPoint`` objects. Each has a ``.payload`` dict
        with all stored metadata (including ``chunk_text``) and a ``.score``
        float (cosine similarity, higher is more similar).
    """
    from qdrant_client.models import FieldCondition, Filter, MatchValue  # noqa: PLC0415

    query_vector = embed_text(query, model)

    must_conditions: list[Any] = []
    if source_tool is not None:
        must_conditions.append(FieldCondition(key="source_tool", match=MatchValue(value=source_tool)))
    if source_type is not None:
        must_conditions.append(FieldCondition(key="source_type", match=MatchValue(value=source_type)))

    query_filter: Any = Filter(must=must_conditions) if must_conditions else None

    results: list[Any] = qdrant_client.query_points(
        collection_name=collection_name,
        query=query_vector,
        query_filter=query_filter,
        limit=limit,
    ).points
    return results
