"""Embedding integration for the Gmail Tool.

Constructs the Qdrant payload for a collected email and delegates to
the shared ``deep_thought.embeddings.write_embedding()`` function.

All third-party imports are lazy so this module can be imported without
``mlx-embeddings`` or ``qdrant-client`` installed.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from deep_thought.embeddings import COLLECTION_NAME

if TYPE_CHECKING:
    from deep_thought.gmail.models import ProcessedEmailLocal


def write_embedding(
    content: str,
    email: ProcessedEmailLocal,
    model: Any,
    qdrant_client: Any,
    collection_name: str = COLLECTION_NAME,
) -> None:
    """Embed a collected email and upsert it into the specified Qdrant collection.

    Constructs the payload from the email's metadata fields and calls the shared
    ``deep_thought.embeddings.write_embedding()`` function. The ``output_path``
    field is injected automatically by that function — do not include it in the
    payload dict here.

    Args:
        content: The text to embed (typically subject + stripped markdown body).
        email: The ProcessedEmailLocal instance whose metadata populates the payload.
        model: The MLX embedding model returned by ``create_embedding_model()``.
        qdrant_client: A Qdrant client returned by ``create_qdrant_client()``.
        collection_name: The Qdrant collection to upsert into. Defaults to
            :data:`~deep_thought.embeddings.COLLECTION_NAME`.

    Raises:
        Any exception from the shared ``write_embedding()`` function is propagated
        to the caller without modification.
    """
    from deep_thought.embeddings import write_embedding as _shared_write_embedding  # noqa: PLC0415

    collected_timestamp: str = datetime.now(UTC).isoformat()

    email_payload: dict[str, Any] = {
        "source_tool": "gmail",
        "source_type": "email",
        "rule_name": email.rule_name,
        "collected_date": collected_timestamp,
        "title": email.subject,
        "message_id": email.message_id,
        "from_address": email.from_address,
        "word_count": len(content.split()),
    }

    _shared_write_embedding(
        content=content,
        payload=email_payload,
        output_path=email.output_path,
        model=model,
        qdrant_client=qdrant_client,
        collection_name=collection_name,
    )
