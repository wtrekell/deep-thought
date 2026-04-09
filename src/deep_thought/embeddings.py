"""Shared embedding infrastructure for deep-thought knowledge collectors.

Provides the canonical embedding function, Qdrant client factory, and helper
utilities consumed by all tools that ingest content into the shared
``deep_thought_db`` Qdrant collection.

All third-party imports are lazy (inside function bodies) so the module can
be imported without requiring mlx-embeddings or qdrant-client to be installed.
"""

from __future__ import annotations

import uuid
from typing import Any, cast

COLLECTION_NAME: str = "deep_thought_db"
EMBEDDING_MODEL_ID: str = "mlx-community/bge-small-en-v1.5-bf16"
VECTOR_DIMENSIONS: int = 384

# Payload fields that must have a Qdrant index for efficient filtered queries.
# Values are PayloadSchemaType member names resolved lazily inside ensure_collection().
PAYLOAD_INDEX_FIELDS: dict[str, str] = {
    "output_path": "KEYWORD",
    "source_tool": "KEYWORD",
    "source_type": "KEYWORD",
    "rule_name": "KEYWORD",
    "collected_date": "DATETIME",
    "title": "KEYWORD",
}


def create_embedding_model() -> Any:
    """Load the MLX embedding model used for all document vectorization.

    Returns a ``(model, tokenizer)`` tuple that should be passed to
    :func:`embed_text` and :func:`write_embedding` for generating vectors.

    Returns:
        A tuple of ``(model, tokenizer)`` for the configured embedding model.

    Raises:
        ImportError: If the ``mlx-embeddings`` package is not installed.
    """
    import mlx_embeddings

    embedding_model_and_tokenizer: Any = mlx_embeddings.load(EMBEDDING_MODEL_ID)
    return embedding_model_and_tokenizer


def create_qdrant_client(host: str = "localhost", port: int = 6333) -> Any:
    """Create a Qdrant client connected to the specified host and port.

    Args:
        host: Hostname of the Qdrant server.
        port: HTTP port of the Qdrant server.

    Returns:
        A connected ``QdrantClient`` instance.
    """
    from qdrant_client import QdrantClient

    qdrant_connection: QdrantClient = QdrantClient(host=host, port=port)
    return qdrant_connection


def embed_text(text: str, model: Any) -> list[float]:
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
    output_path: str,
    model: Any,
    qdrant_client: Any,
    collection_name: str = COLLECTION_NAME,
) -> None:
    """Embed content and upsert it into the specified Qdrant collection.

    Generates a deterministic point ID from ``output_path`` using UUID5,
    making repeated calls with the same path idempotent (upsert semantics).

    Args:
        content: The text content to embed and store.
        payload: Metadata dictionary to attach to the Qdrant point.
            Must not include ``output_path`` — it is injected automatically.
        output_path: Filesystem path of the source document, used both as
            the deterministic ID seed and as a payload field.
        model: The MLX embedding model returned by :func:`create_embedding_model`.
        qdrant_client: A Qdrant client returned by :func:`create_qdrant_client`.
        collection_name: The Qdrant collection to upsert into. Defaults to
            :data:`COLLECTION_NAME` (``"deep_thought_db"``).

    Raises:
        Any exception from embedding generation or Qdrant upsert is propagated
        to the caller without modification.
    """
    from qdrant_client.models import PointStruct

    vector = embed_text(content, model)

    point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, output_path))

    full_payload = {**payload, "output_path": output_path}

    qdrant_client.upsert(
        collection_name=collection_name,
        points=[PointStruct(id=point_id, vector=vector, payload=full_payload)],
    )


def search_embeddings(
    query: str,
    model: Any,
    qdrant_client: Any,
    collection_name: str = COLLECTION_NAME,
    limit: int = 10,
    source_tool: str | None = None,
    source_type: str | None = None,
) -> list[Any]:
    """Search the Qdrant collection for documents semantically similar to query.

    Embeds the query text and performs a vector similarity search against the
    specified collection.  Optional ``source_tool`` and ``source_type`` filters
    narrow results to a specific origin or content category using the indexed
    payload fields.

    Args:
        query: The natural-language query string to embed and search with.
        model: The ``(model, tokenizer)`` tuple returned by
            :func:`create_embedding_model`.
        qdrant_client: A Qdrant client returned by :func:`create_qdrant_client`.
        collection_name: The Qdrant collection to search. Defaults to
            :data:`COLLECTION_NAME` (``"deep_thought_db"``).
        limit: Maximum number of results to return. Defaults to 10.
        source_tool: Optional filter — restrict results to a single tool.
            Valid values: ``"reddit"``, ``"web"``, ``"research"``.
        source_type: Optional filter — restrict results to a single content type.
            Valid values: ``"forum_post"``, ``"blog_post"``, ``"documentation"``,
            ``"article"``, ``"research_search"``, ``"research_deep"``.

    Returns:
        A list of Qdrant ``ScoredPoint`` objects. Each has a ``.payload`` dict
        with all stored metadata and a ``.score`` float (cosine similarity,
        higher is more similar). The ``output_path`` in the payload is the
        canonical pointer back to the source markdown file on disk.
    """
    from qdrant_client.models import FieldCondition, Filter, MatchValue  # noqa: PLC0415

    query_vector = embed_text(query, model)

    must_conditions: list[Any] = []
    if source_tool is not None:
        must_conditions.append(FieldCondition(key="source_tool", match=MatchValue(value=source_tool)))
    if source_type is not None:
        must_conditions.append(FieldCondition(key="source_type", match=MatchValue(value=source_type)))

    query_filter: Any = Filter(must=must_conditions) if must_conditions else None

    results: list[Any] = qdrant_client.search(
        collection_name=collection_name,
        query_vector=query_vector,
        query_filter=query_filter,
        limit=limit,
    )
    return results
