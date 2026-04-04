"""Shared embedding infrastructure for deep-thought knowledge collectors.

Provides the canonical embedding function, Qdrant client factory, and helper
utilities consumed by all tools that ingest content into the shared
``deep_thought_documents`` Qdrant collection.

All third-party imports are lazy (inside function bodies) so the module can
be imported without requiring mlx-embeddings or qdrant-client to be installed.
"""

from __future__ import annotations

import uuid
from typing import Any

COLLECTION_NAME: str = "deep_thought_documents"
EMBEDDING_MODEL_ID: str = "mlx-community/bge-small-en-v1.5-bf16"
VECTOR_DIMENSIONS: int = 384


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
    embedding_vector: list[float] = mx.mean(last_hidden_state, axis=0).tolist()
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

    closing_delimiter_position = markdown_text.find("---", 3)
    if closing_delimiter_position == -1:
        return markdown_text

    end_of_frontmatter = closing_delimiter_position + 3
    remaining_content = markdown_text[end_of_frontmatter:]
    return remaining_content.lstrip("\n")


def write_embedding(
    content: str,
    payload: dict[str, Any],
    output_path: str,
    model: Any,
    qdrant_client: Any,
) -> None:
    """Embed content and upsert it into the shared Qdrant collection.

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

    Raises:
        Any exception from embedding generation or Qdrant upsert is propagated
        to the caller without modification.
    """
    from qdrant_client.models import PointStruct

    vector = embed_text(content, model)

    point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, output_path))

    full_payload = {**payload, "output_path": output_path}

    qdrant_client.upsert(
        collection_name=COLLECTION_NAME,
        points=[PointStruct(id=point_id, vector=vector, payload=full_payload)],
    )
