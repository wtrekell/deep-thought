"""Shared utilities for the Reddit Tool.

Small, stateless helper functions used across models.py, output.py,
processor.py, and llms.py. Centralised here to avoid duplication.
"""

from __future__ import annotations

import re
from typing import Any


def slugify_title(title: str, max_length: int = 80) -> str:
    """Convert a post title to a filesystem-safe slug.

    Lowercases, replaces non-alphanumeric characters with hyphens, collapses
    repeated hyphens, and strips leading/trailing hyphens.

    Args:
        title: The raw post title string.
        max_length: Maximum slug length before truncation. Defaults to 80.

    Returns:
        A cleaned slug suitable for use in a filename or link.
    """
    slug = title.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug[:max_length] if len(slug) > max_length else slug


def get_author_name(author_object: Any) -> str:
    """Extract the author username from a PRAW Submission or Comment safely.

    PRAW's author attribute is a Redditor object, or None for deleted accounts.
    Calling ``str()`` on a Redditor returns its username; on ``None`` it would
    give the string ``"None"``, so we check explicitly first.

    Args:
        author_object: The ``.author`` attribute from a PRAW Submission or
            Comment object — either a Redditor instance or None.

    Returns:
        The author's username string, or "[deleted]" if the account is gone.
    """
    if author_object is None:
        return "[deleted]"
    return str(author_object)
