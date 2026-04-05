"""Embedding integration for the Web crawl Tool.

Constructs the Qdrant payload for a crawled web page and delegates to
the shared ``deep_thought.embeddings.write_embedding()`` function.

All third-party imports are lazy so this module can be imported without
``mlx-embeddings`` or ``qdrant-client`` installed.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from deep_thought.embeddings import COLLECTION_NAME

if TYPE_CHECKING:
    from deep_thought.web.models import CrawledPageLocal

logger = logging.getLogger(__name__)

# Maps crawl mode strings to Qdrant source_type values.
_SOURCE_TYPE_MAP: dict[str, str] = {
    "blog": "blog_post",
    "documentation": "documentation",
    "direct": "article",
}


def write_embedding(
    content: str,
    page: CrawledPageLocal,
    mode: str,
    model: Any,
    qdrant_client: Any,
    collection_name: str = COLLECTION_NAME,
) -> None:
    """Embed a crawled web page and upsert it into the specified Qdrant collection.

    Constructs the payload from the page's metadata fields and calls the shared
    ``deep_thought.embeddings.write_embedding()`` function. The ``output_path``
    field is injected automatically by that function — do not include it in the
    payload dict here.

    Args:
        content: The text to embed (typically title + stripped markdown body).
        page: The CrawledPageLocal instance whose metadata populates the payload.
        mode: The crawl mode string (``"blog"``, ``"documentation"``, or ``"direct"``).
            Controls the ``source_type`` value written to the payload.
        model: The MLX embedding model returned by ``create_embedding_model()``.
        qdrant_client: A Qdrant client returned by ``create_qdrant_client()``.
        collection_name: The Qdrant collection to upsert into. Defaults to
            :data:`~deep_thought.embeddings.COLLECTION_NAME`.

    Raises:
        Any exception from the shared ``write_embedding()`` function is propagated
        to the caller without modification.
    """
    from deep_thought.embeddings import write_embedding as _shared_write_embedding  # noqa: PLC0415

    source_type: str = _SOURCE_TYPE_MAP.get(mode, "article")
    collected_timestamp: str = datetime.now(UTC).isoformat()
    domain: str = urlparse(page.url).netloc

    page_payload: dict[str, Any] = {
        "source_tool": "web",
        "source_type": source_type,
        "rule_name": page.rule_name or "",
        "collected_date": collected_timestamp,
        "domain": domain,
        "url": page.url,
        "word_count": page.word_count,
    }

    if page.title is not None:
        page_payload["title"] = page.title

    if page.status_code is not None:
        page_payload["status_code"] = page.status_code

    _shared_write_embedding(
        content=content,
        payload=page_payload,
        output_path=page.output_path,
        model=model,
        qdrant_client=qdrant_client,
        collection_name=collection_name,
    )
