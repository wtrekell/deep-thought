"""File filtering functions for the audio tool.

Pure functions that determine which audio files should be processed, based on
extension allowlists, file size limits, emptiness checks, and duplicate
detection via SHA-256 hashing.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import sqlite3
    from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SUPPORTED_EXTENSIONS: frozenset[str] = frozenset({".mp3", ".wav", ".m4a", ".flac", ".ogg", ".wma", ".aac", ".webm"})


# ---------------------------------------------------------------------------
# Individual filter predicates
# ---------------------------------------------------------------------------


def is_supported_extension(path: Path) -> bool:
    """Return True if path's extension is a supported audio format (case-insensitive).

    Args:
        path: The file path whose extension is checked.

    Returns:
        True if the extension is in the supported set, False otherwise.
    """
    return path.suffix.lower() in _SUPPORTED_EXTENSIONS


def is_within_size_limit(path: Path, max_size_mb: int) -> bool:
    """Return True if path's file size does not exceed the limit in megabytes.

    Args:
        path: The file path whose size is checked. The file must exist.
        max_size_mb: Maximum permitted size in megabytes. Must be positive.

    Returns:
        True if the file is at or below the limit, False if it exceeds it.
    """
    max_bytes = max_size_mb * 1024 * 1024
    file_size_bytes = path.stat().st_size
    return file_size_bytes <= max_bytes


def is_empty_file(path: Path) -> bool:
    """Return True if the file has zero bytes.

    Args:
        path: The file path to check. The file must exist.

    Returns:
        True if the file is empty, False otherwise.
    """
    return path.stat().st_size == 0


def compute_file_hash(path: Path) -> str:
    """Compute the SHA-256 hash of a file's contents.

    Reads the file in 64 KB chunks to avoid loading large audio files into
    memory all at once.

    Args:
        path: The file path to hash. The file must exist.

    Returns:
        Lowercase hexadecimal SHA-256 digest string.
    """
    sha256_hasher = hashlib.sha256()
    chunk_size_bytes = 65536  # 64 KB

    with path.open("rb") as audio_file:
        while True:
            chunk = audio_file.read(chunk_size_bytes)
            if not chunk:
                break
            sha256_hasher.update(chunk)

    return sha256_hasher.hexdigest()


# ---------------------------------------------------------------------------
# Composite check
# ---------------------------------------------------------------------------


def check_file(
    path: Path,
    file_hash: str,
    max_size_mb: int,
    conn: sqlite3.Connection | None = None,
) -> tuple[bool, str]:
    """Run all filters against a single file and return whether it should be processed.

    Checks are performed in this order:
    1. Extension is supported
    2. File is not empty
    3. File is within the size limit
    4. File has not already been processed (duplicate check via DB, if conn provided)

    Args:
        path: The audio file path to evaluate. The file must exist.
        file_hash: Pre-computed SHA-256 hash of the file (avoids re-reading the
                   file here when the caller already has the hash).
        max_size_mb: Maximum permitted file size in megabytes.
        conn: Optional SQLite connection. When provided, a DB lookup is performed
              to detect previously processed files with the same hash.

    Returns:
        A tuple of (should_process, reason). When should_process is True, reason
        is an empty string. When False, reason is a human-readable explanation.
    """
    if not is_supported_extension(path):
        return False, f"Unsupported extension '{path.suffix}' — supported: {sorted(_SUPPORTED_EXTENSIONS)}"

    if is_empty_file(path):
        return False, "File is empty (0 bytes)"

    if not is_within_size_limit(path, max_size_mb):
        file_size_mb = path.stat().st_size / (1024 * 1024)
        return False, f"File size {file_size_mb:.1f} MB exceeds limit of {max_size_mb} MB"

    if conn is not None:
        from deep_thought.audio.db.queries import get_file_hash_with_success

        existing_row = get_file_hash_with_success(conn, file_hash)
        if existing_row is not None:
            existing_path = existing_row["file_path"]
            return False, f"Duplicate: already processed as '{existing_path}' with status 'success'"

    return True, ""


# ---------------------------------------------------------------------------
# Directory walker
# ---------------------------------------------------------------------------


def collect_input_files(input_path: Path) -> list[Path]:
    """Return all supported audio files at input_path.

    If input_path is a file, it is returned as a single-item list (regardless
    of extension — callers are responsible for validation via check_file).
    If input_path is a directory, it is walked recursively and all files with
    a supported audio extension are returned.

    Args:
        input_path: A file or directory to collect from.

    Returns:
        Sorted list of Path objects for all matching audio files.

    Raises:
        FileNotFoundError: If input_path does not exist.
    """
    if not input_path.exists():
        raise FileNotFoundError(f"Input path does not exist: {input_path}")

    if input_path.is_file():
        return [input_path]

    candidate_files: list[Path] = [entry for entry in input_path.rglob("*") if entry.is_file()]

    matching_files: list[Path] = [
        candidate_path for candidate_path in candidate_files if is_supported_extension(candidate_path)
    ]

    return sorted(matching_files)
