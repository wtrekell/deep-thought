"""File filtering functions for the file-txt tool.

Pure functions that determine which files should be processed based on
extension allowlists, exclusion patterns, and file size limits.
"""

from __future__ import annotations

import fnmatch
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from deep_thought.file_txt.config import FilterConfig


def is_allowed_extension(path: Path, allowed: list[str]) -> bool:
    """Return True if path's extension is in the allowed list (case-insensitive).

    An empty allowed list means all extensions are permitted.

    Args:
        path: The file path whose extension is checked.
        allowed: List of permitted extensions including the leading dot,
                 e.g. ['.pdf', '.docx']. Empty list permits everything.

    Returns:
        True if the extension is permitted, False otherwise.
    """
    if not allowed:
        return True

    file_extension = path.suffix.lower()
    normalised_allowed = [ext.lower() for ext in allowed]
    return file_extension in normalised_allowed


def is_excluded(path: Path, patterns: list[str]) -> bool:
    """Return True if path's filename matches any exclusion pattern.

    Patterns use Unix shell-style wildcards (fnmatch semantics):
    - ``*`` matches any sequence of characters
    - ``?`` matches any single character
    - ``[seq]`` matches any character in seq

    Only the filename component is matched, not the full path.

    Args:
        path: The file path whose name is checked against patterns.
        patterns: List of glob-style patterns. An empty list means nothing
                  is excluded.

    Returns:
        True if the file should be excluded, False otherwise.
    """
    if not patterns:
        return False

    filename = path.name
    return any(fnmatch.fnmatch(filename, pattern) for pattern in patterns)


def is_within_size_limit(path: Path, max_mb: int) -> bool:
    """Return True if path's file size does not exceed the limit in megabytes.

    Args:
        path: The file path whose size is checked. The file must exist.
        max_mb: Maximum permitted size in megabytes. Must be positive.

    Returns:
        True if the file is at or below the limit, False if it exceeds it.
    """
    max_bytes = max_mb * 1024 * 1024
    file_size_bytes = path.stat().st_size
    return file_size_bytes <= max_bytes


def collect_input_files(input_path: Path, config: FilterConfig) -> list[Path]:
    """Return all processable files at input_path, applying all filters.

    If input_path is a file, it is returned as a single-item list (if it
    passes all filters). If input_path is a directory, it is walked
    recursively and all matching files are returned.

    Files are excluded when any of the following conditions apply:
    - Extension is not in config.allowed_extensions
    - Filename matches any pattern in config.exclude_patterns

    Size limits are NOT applied here — they are checked per-file during
    conversion so that useful skip diagnostics can be reported.

    Args:
        input_path: A file or directory to collect from.
        config: FilterConfig specifying which files are allowed.

    Returns:
        Sorted list of Path objects for all matching files.

    Raises:
        FileNotFoundError: If input_path does not exist.
    """
    if not input_path.exists():
        raise FileNotFoundError(f"Input path does not exist: {input_path}")

    if input_path.is_file():
        candidate_files: list[Path] = [input_path]
    else:
        candidate_files = [entry for entry in input_path.rglob("*") if entry.is_file()]

    matching_files: list[Path] = []
    for candidate_path in candidate_files:
        if not is_allowed_extension(candidate_path, config.allowed_extensions):
            continue
        if is_excluded(candidate_path, config.exclude_patterns):
            continue
        matching_files.append(candidate_path)

    return sorted(matching_files)
