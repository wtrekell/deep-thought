"""Shared utilities for the Reddit Tool.

Small, stateless helper functions used across models.py, output.py,
processor.py, and llms.py. Centralised here to avoid duplication.
"""

from __future__ import annotations

from typing import Any

from deep_thought.text_utils import slugify as _shared_slugify


def slugify_title(title: str, max_length: int = 80) -> str:
    """Convert a post title to a filesystem-safe slug.

    Delegates to ``deep_thought.text_utils.slugify`` with ``max_length=80``.
    Kept here for backward compatibility with callers that import from this module.

    Args:
        title: The raw post title string.
        max_length: Maximum slug length before truncation. Defaults to 80.

    Returns:
        A cleaned slug suitable for use in a filename or link.
    """
    return _shared_slugify(title, max_length=max_length)


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
