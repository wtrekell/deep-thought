"""Embedding integration for the Stack Exchange Tool.

Constructs the Qdrant payload for a collected Stack Exchange question and
delegates to the shared deep_thought.embeddings.write_embedding() function.

All third-party imports are lazy so this module can be imported without
mlx-embeddings or qdrant-client installed.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from deep_thought.embeddings import COLLECTION_NAME

if TYPE_CHECKING:
    from deep_thought.stackexchange.models import CollectedQuestionLocal


def write_embedding(
    content: str,
    question: CollectedQuestionLocal,
    model: Any,
    qdrant_client: Any,
    collection_name: str = COLLECTION_NAME,
) -> None:
    """Embed a collected Stack Exchange question and upsert into Qdrant.

    Constructs the payload from the question's metadata fields and calls the
    shared ``deep_thought.embeddings.write_embedding()`` function. The
    ``output_path`` field is injected automatically by that function — do not
    include it in the payload dict here.

    Args:
        content: Text to embed (typically title + stripped markdown body).
        question: The CollectedQuestionLocal whose metadata populates the payload.
        model: The MLX embedding model returned by ``create_embedding_model()``.
        qdrant_client: A Qdrant client returned by ``create_qdrant_client()``.
        collection_name: The Qdrant collection to upsert into. Defaults to
            :data:`~deep_thought.embeddings.COLLECTION_NAME`.
    """
    from deep_thought.embeddings import write_embedding as _shared_write_embedding  # noqa: PLC0415

    collected_timestamp: str = datetime.now(UTC).isoformat()

    question_payload: dict[str, Any] = {
        "source_tool": "stackexchange",
        "source_type": "q_and_a",
        "rule_name": question.rule_name,
        "collected_date": collected_timestamp,
        "title": question.title,
        "question_id": question.question_id,
        "site": question.site,
        "score": question.score,
        "answer_count": question.answer_count,
    }

    _shared_write_embedding(
        content=content,
        payload=question_payload,
        output_path=question.output_path,
        model=model,
        qdrant_client=qdrant_client,
        collection_name=collection_name,
    )
