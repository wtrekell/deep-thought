"""Embedding integration for the Reddit Tool.

Constructs the Qdrant payload for a collected Reddit post and delegates to
the shared ``deep_thought.embeddings.write_embedding()`` function.

All third-party imports are lazy so this module can be imported without
``mlx-embeddings`` or ``qdrant-client`` installed.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from deep_thought.embeddings import COLLECTION_NAME

if TYPE_CHECKING:
    from deep_thought.reddit.models import CollectedPostLocal


def write_embedding(
    content: str,
    post: CollectedPostLocal,
    model: Any,
    qdrant_client: Any,
    collection_name: str = COLLECTION_NAME,
) -> None:
    """Embed a collected Reddit post and upsert it into the specified Qdrant collection.

    Constructs the payload from the post's metadata fields and calls the shared
    ``deep_thought.embeddings.write_embedding()`` function. The Reddit post URL
    is the canonical identifier — re-collecting the same post updates the same
    chunks rather than creating duplicates. ``output_path`` is passed as
    advisory metadata only.

    Args:
        content: The text to embed (typically title + stripped markdown body).
        post: The CollectedPostLocal instance whose metadata populates the payload.
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
        "upvote_ratio": post.upvote_ratio,
        "comment_count": post.comment_count,
        "url": post.url,
        "word_count": post.word_count,
    }

    if post.flair is not None:
        post_payload["flair"] = post.flair

    _shared_write_embedding(
        content=content,
        payload=post_payload,
        canonical_id=post.url,
        output_path=post.output_path,
        model=model,
        qdrant_client=qdrant_client,
        collection_name=collection_name,
    )
