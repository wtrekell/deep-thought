"""Embedding integration for the Reddit Tool.

Constructs the Qdrant payload for a collected Reddit post and delegates to
the shared ``deep_thought.embeddings.write_embedding()`` function.

All third-party imports are lazy so this module can be imported without
``mlx-embeddings`` or ``qdrant-client`` installed.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from deep_thought.reddit.models import CollectedPostLocal

logger = logging.getLogger(__name__)


def write_embedding(
    content: str,
    post: CollectedPostLocal,
    model: Any,
    qdrant_client: Any,
) -> None:
    """Embed a collected Reddit post and upsert it into the shared Qdrant collection.

    Constructs the payload from the post's metadata fields and calls the shared
    ``deep_thought.embeddings.write_embedding()`` function. The ``output_path``
    field is injected automatically by that function — do not include it in the
    payload dict here.

    Args:
        content: The text to embed (typically title + stripped markdown body).
        post: The CollectedPostLocal instance whose metadata populates the payload.
        model: The MLX embedding model returned by ``create_embedding_model()``.
        qdrant_client: A Qdrant client returned by ``create_qdrant_client()``.

    Raises:
        Any exception from the shared ``write_embedding()`` function is propagated
        to the caller without modification.
    """
    from deep_thought.embeddings import write_embedding as _shared_write_embedding  # noqa: PLC0415

    collected_timestamp: str = datetime.now(UTC).isoformat()

    post_payload: dict[str, Any] = {
        "source_tool": "reddit",
        "source_type": "forum_post",
        "rule_name": post.rule_name,
        "collected_date": collected_timestamp,
        "title": post.title,
        "subreddit": post.subreddit,
        "post_id": post.post_id,
        "author": post.author,
        "score": post.score,
        "comment_count": post.comment_count,
        "url": post.url,
        "word_count": post.word_count,
    }

    if post.flair is not None:
        post_payload["flair"] = post.flair

    _shared_write_embedding(
        content=content,
        payload=post_payload,
        output_path=post.output_path,
        model=model,
        qdrant_client=qdrant_client,
    )
