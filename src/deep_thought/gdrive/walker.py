"""Directory tree walker for the GDrive backup tool.

Provides walk_tree(), which traverses a source directory and returns metadata
(relative path, mtime, size) for each eligible file. Hidden files/directories
and common generated directories (e.g. .git, __pycache__) are excluded.
"""

from __future__ import annotations

import fnmatch
import os
from pathlib import Path

# Directory names to skip entirely during traversal
_EXCLUDED_DIR_NAMES: frozenset[str] = frozenset(
    {
        "__pycache__",
        ".git",
        ".venv",
        "node_modules",
        ".mypy_cache",
    }
)


def _is_excluded(name: str, path_from_source: str, patterns: list[str]) -> bool:
    """Return True if name or path_from_source matches any fnmatch pattern.

    Patterns are checked against both the bare name (last path component) and
    the full path relative to source_dir, so a pattern like ``output`` matches
    any directory or file named ``output`` anywhere in the tree, while
    ``deep-thought/output`` matches only that specific location.

    Args:
        name: The directory or file name (last path component only).
        path_from_source: The path relative to source_dir (e.g. ``notes/todo.md``).
        patterns: fnmatch-style patterns from the config's exclude_patterns list.

    Returns:
        True if any pattern matches, False otherwise.
    """
    for pattern in patterns:
        if fnmatch.fnmatch(name, pattern):
            return True
        if fnmatch.fnmatch(path_from_source, pattern):
            return True
    return False


def walk_tree(source_dir: str, exclude_patterns: list[str] | None = None) -> list[tuple[str, float, int]]:
    """Walk source_dir and return (relative_path, mtime, size_bytes) for each file.

    Hidden files and directories (names starting with '.') are skipped.
    The directories in _EXCLUDED_DIR_NAMES are also skipped entirely.
    Any additional patterns in exclude_patterns are matched via fnmatch against
    the entry name and the path relative to source_dir.

    The returned ``relative_path`` is relative to the *parent* of source_dir,
    not source_dir itself. This matches how paths are stored in the database
    and mirrored on Drive, so the source directory name itself appears as the
    top-level folder on Drive.

    Example:
        source_dir = "/Users/alice/Documents/project"
        A file at "/Users/alice/Documents/project/notes/todo.md" is returned as:
        relative_path = "project/notes/todo.md"

    Args:
        source_dir: Absolute path to the root directory to back up.
        exclude_patterns: Optional list of fnmatch patterns. Each pattern is
            tested against the entry name and the path relative to source_dir.
            Matching directories are pruned entirely; matching files are skipped.

    Returns:
        A list of tuples: (relative_local_path, mtime_float, size_bytes_int).
        Empty list if source_dir is empty or does not exist.
    """
    source_path = Path(source_dir)
    parent_path = source_path.parent
    active_patterns: list[str] = exclude_patterns if exclude_patterns else []
    collected_files: list[tuple[str, float, int]] = []

    for directory_path, subdirectory_names, file_names in os.walk(str(source_path)):
        current_directory = Path(directory_path)

        # Prune hidden directories and excluded directories in-place so os.walk
        # does not descend into them. Modifying subdirectory_names in-place is
        # the documented os.walk pattern for controlling traversal.
        subdirectory_names[:] = [
            subdir_name
            for subdir_name in subdirectory_names
            if not subdir_name.startswith(".") and subdir_name not in _EXCLUDED_DIR_NAMES
        ]

        # Prune directories matching user-configured exclude_patterns.
        if active_patterns:
            relative_current = current_directory.relative_to(source_path)
            subdirectory_names[:] = [
                subdir_name
                for subdir_name in subdirectory_names
                if not _is_excluded(subdir_name, str(relative_current / subdir_name), active_patterns)
            ]

        for file_name in file_names:
            # Skip hidden files
            if file_name.startswith("."):
                continue

            absolute_file_path = current_directory / file_name

            # Skip files matching user-configured exclude_patterns.
            if active_patterns:
                relative_from_source = str(absolute_file_path.relative_to(source_path))
                if _is_excluded(file_name, relative_from_source, active_patterns):
                    continue

            try:
                file_stat = absolute_file_path.stat()
            except OSError:
                # File may have disappeared between the directory listing and
                # the stat call — skip it gracefully.
                continue

            relative_file_path = absolute_file_path.relative_to(parent_path)
            collected_files.append(
                (
                    str(relative_file_path),
                    file_stat.st_mtime,
                    file_stat.st_size,
                )
            )

    return collected_files
