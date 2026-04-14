"""Local dataclasses for the GDrive Tool.

BackedUpFile mirrors the backed_up_files database table and represents the
state of a single file that has been (or is being) backed up to Google Drive.

BackupResult is returned from run_backup() to summarise the outcome.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class BackedUpFile:
    """Local representation of a file backed up to Google Drive.

    Mirrors the backed_up_files database table. ``local_path`` is the primary
    key and is stored relative to the parent of the configured source_dir,
    so paths are stable regardless of where the repo is cloned.

    Status values:
        "uploaded"  — file was newly uploaded on this run
        "updated"   — file content was updated in-place on this run
        "skipped"   — file mtime was unchanged; no API call needed
        "error"     — an error occurred while processing this file
    """

    local_path: str
    drive_file_id: str
    drive_folder_id: str
    mtime: float
    size_bytes: int
    status: str
    uploaded_at: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        """Return a flat dict keyed by database column names.

        Returns:
            A plain dictionary representation suitable for passing to
            database query functions.
        """
        return {
            "local_path": self.local_path,
            "drive_file_id": self.drive_file_id,
            "drive_folder_id": self.drive_folder_id,
            "mtime": self.mtime,
            "size_bytes": self.size_bytes,
            "status": self.status,
            "uploaded_at": self.uploaded_at,
            "updated_at": self.updated_at,
        }


@dataclass
class BackupResult:
    """Summary of a backup run."""

    uploaded: int = 0
    updated: int = 0
    skipped: int = 0
    vanished: int = 0
    errors: int = 0
    error_paths: list[str] = field(default_factory=list)
    vanished_paths: list[str] = field(default_factory=list)


@dataclass
class PruneResult:
    """Summary of a prune run."""

    deleted: int = 0
    errors: int = 0
    error_paths: list[str] = field(default_factory=list)
