"""Shared text-processing utilities for the deep_thought namespace package.

Small, stateless helpers used across multiple tools. Functions here must have
no side effects and no tool-specific imports.
"""

from __future__ import annotations

import re


def slugify(text: str, max_length: int = 80, empty_fallback: str = "") -> str:
    """Convert a string to a URL-safe, filesystem-safe slug.

    Lowercases the text, replaces any run of non-alphanumeric characters with
    a single hyphen, strips leading and trailing hyphens, truncates to
    ``max_length`` characters, then strips any trailing hyphen introduced by
    the truncation boundary.

    Args:
        text: The input string to slugify.
        max_length: Maximum number of characters in the returned slug.
            Defaults to 80. Pass a different value when a caller requires a
            different length limit (e.g. 100 for web page filenames).
        empty_fallback: Value to return when the slug reduces to an empty
            string (e.g. empty input or all-special-character input).
            Defaults to ``""``; pass ``"no-title"`` for callers that need a
            non-empty sentinel.

    Returns:
        A slug string of at most ``max_length`` characters, containing only
        lowercase alphanumerics and hyphens, or ``empty_fallback`` when the
        result would otherwise be empty.
    """
    if max_length < 1:
        raise ValueError("max_length must be >= 1")
    lowercased = text.lower()
    non_alnum_replaced = re.sub(r"[^a-z0-9]+", "-", lowercased)
    stripped = non_alnum_replaced.strip("-")
    truncated = stripped[:max_length].rstrip("-")
    return truncated if truncated else empty_fallback
