"""Embedding integration for the Research Tool.

Constructs the Qdrant payload for a research result and delegates to
the shared ``deep_thought.embeddings.write_embedding()`` function.

All third-party imports are lazy so this module can be imported without
``mlx-embeddings`` or ``qdrant-client`` installed.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from deep_thought.embeddings import COLLECTION_NAME

if TYPE_CHECKING:
    from deep_thought.research.models import ResearchResult

logger = logging.getLogger(__name__)


def write_embedding(
    content: str,
    result: ResearchResult,
    output_path: str,
    model: Any,
    qdrant_client: Any,
    collection_name: str = COLLECTION_NAME,
) -> None:
    """Embed a research result and upsert it into the specified Qdrant collection.

    Constructs the payload from the result's metadata fields and calls the shared
    ``deep_thought.embeddings.write_embedding()`` function. The ``output_path``
    field is injected automatically by that function — do not include it in the
    payload dict here.

    The research tool has no rule system, so ``rule_name`` is always the empty
    string. ``source_type`` is determined by the result's mode field:
    ``"research"`` maps to ``"research_deep"``, anything else maps to
    ``"research_search"``.

    Args:
        content: The text to embed (typically query + answer text).
        result: The ResearchResult instance whose metadata populates the payload.
        output_path: Filesystem path of the written markdown output file.
        model: The MLX embedding model returned by ``create_embedding_model()``.
        qdrant_client: A Qdrant client returned by ``create_qdrant_client()``.
        collection_name: The Qdrant collection to upsert into. Defaults to
            :data:`~deep_thought.embeddings.COLLECTION_NAME`.

    Raises:
        Any exception from the shared ``write_embedding()`` function is propagated
        to the caller without modification.
    """
    from deep_thought.embeddings import write_embedding as _shared_write_embedding  # noqa: PLC0415

    source_type: str = "research_deep" if result.mode == "research" else "research_search"

    research_payload: dict[str, Any] = {
        "source_tool": "research",
        "source_type": source_type,
        "rule_name": "",
        "collected_date": result.processed_date,
        "title": result.query,
        "query": result.query,
        "mode": result.mode,
        "model": result.model,
        "source_count": len(result.search_results),
    }

    if result.recency is not None:
        research_payload["recency"] = result.recency

    _shared_write_embedding(
        content=content,
        payload=research_payload,
        output_path=output_path,
        model=model,
        qdrant_client=qdrant_client,
        collection_name=collection_name,
    )
