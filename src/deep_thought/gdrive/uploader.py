"""Backup orchestration for the GDrive Tool.

Coordinates the full backup run: walk the source tree, compare against the
database, upload new files, update changed files, skip unchanged files, and
record results. Returns a BackupResult summary.
"""

from __future__ import annotations

import logging
import mimetypes
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from deep_thought.gdrive.db.queries import (
    clear_backed_up_files,
    clear_drive_folders,
    delete_backed_up_file,
    get_all_backed_up_files,
    get_backed_up_file,
    get_drive_folder,
    mark_file_status,
    upsert_backed_up_file,
    upsert_drive_folder,
)
from deep_thought.gdrive.models import BackedUpFile, BackupResult, PruneResult
from deep_thought.gdrive.walker import _is_excluded, walk_tree

if TYPE_CHECKING:
    import sqlite3

    from deep_thought.gdrive.client import DriveClient
    from deep_thought.gdrive.config import GDriveConfig

logger = logging.getLogger(__name__)

_DEFAULT_MIME_TYPE = "application/octet-stream"


def _get_mime_type(file_path: str) -> str:
    """Guess the MIME type of a file from its extension.

    Falls back to application/octet-stream when the type cannot be determined.

    Args:
        file_path: The file path (extension is used for guessing).

    Returns:
        A MIME type string.
    """
    guessed_type, _ = mimetypes.guess_type(file_path)
    return guessed_type if guessed_type else _DEFAULT_MIME_TYPE


def _ensure_parent_folder_hierarchy(
    relative_file_path: str,
    root_drive_folder_id: str,
    client: DriveClient,
    conn: sqlite3.Connection,
    dry_run: bool,
) -> str:
    """Ensure the full folder hierarchy on Drive exists for a given file path.

    Creates each directory segment on Drive (if not already cached) and
    caches the folder IDs in the drive_folders table.

    Args:
        relative_file_path: The relative path of the file (from parent of source_dir).
        root_drive_folder_id: The top-level Drive folder ID from config.
        client: Authenticated DriveClient.
        conn: Open SQLite connection.
        dry_run: If True, skip API calls and return a placeholder folder ID.

    Returns:
        The Drive folder ID of the immediate parent folder for the file.
    """
    # Get the directory part of the relative path (e.g. "project/notes" for "project/notes/todo.md")
    relative_path_object = Path(relative_file_path)
    parent_path_parts = relative_path_object.parts[:-1]  # exclude the file name

    if not parent_path_parts:
        # File is at the root of the source directory — parent is the root Drive folder
        return root_drive_folder_id

    if dry_run:
        return "[dry-run-folder-id]"

    # Walk down the path segments, ensuring each folder exists
    current_drive_folder_id = root_drive_folder_id
    accumulated_path = ""

    for path_segment in parent_path_parts:
        accumulated_path = f"{accumulated_path}/{path_segment}" if accumulated_path else path_segment

        # Check the cache first
        cached_folder_id = get_drive_folder(conn, accumulated_path)
        if cached_folder_id is not None:
            current_drive_folder_id = cached_folder_id
            continue

        # Not cached — call Drive API and cache the result
        segment_drive_folder_id = client.ensure_folder(
            folder_name=path_segment,
            parent_folder_id=current_drive_folder_id,
        )
        upsert_drive_folder(conn, accumulated_path, segment_drive_folder_id)
        current_drive_folder_id = segment_drive_folder_id

    return current_drive_folder_id


def run_backup(
    config: GDriveConfig,
    client: DriveClient,
    db_conn: sqlite3.Connection,
    dry_run: bool = False,
    force: bool = False,
    verbose: bool = False,
) -> BackupResult:
    """Execute an incremental backup of source_dir to Google Drive.

    Steps:
    1. If force is True, clear backed_up_files and drive_folders tables.
    2. Walk the source tree via walk_tree().
    3. For each file:
       a. Look up the existing DB record.
       b. If the record exists and mtime is unchanged, skip it.
       c. If no record exists, upload as a new file.
       d. If record exists but mtime has changed, update the file in-place.
    4. Errors per file are caught, logged, and recorded without halting the run.
    5. Return a BackupResult with counts of uploaded, updated, skipped, errors.

    Args:
        config: Loaded GDriveConfig with source and destination settings.
        client: Authenticated DriveClient.
        db_conn: Open SQLite connection to the gdrive database.
        dry_run: If True, walk the tree and log what would happen but skip
                 all Drive API calls and DB writes.
        force: If True, clear all cached state and re-upload everything. Has no
               effect when combined with ``dry_run``.
        verbose: If True, log each file's disposition at DEBUG level.

    Returns:
        A BackupResult summarising the run.
    """
    backup_result = BackupResult()

    if force and dry_run:
        logger.info("--force has no effect in --dry-run mode: cached state will not be cleared.")
    elif force:
        logger.info("--force: clearing backed_up_files and drive_folders tables.")
        clear_backed_up_files(db_conn)
        clear_drive_folders(db_conn)
        db_conn.commit()

    if not Path(config.source_dir).exists():
        logger.warning("Source directory does not exist: %s — skipping backup.", config.source_dir)
        return backup_result

    logger.info("Walking source directory: %s", config.source_dir)
    walked_files = walk_tree(config.source_dir, config.exclude_patterns)
    logger.info("Found %d file(s) to consider.", len(walked_files))

    now_iso = datetime.now(UTC).isoformat()

    for relative_file_path, file_mtime, file_size_bytes in walked_files:
        absolute_file_path = str(Path(config.source_dir).parent / relative_file_path)

        existing_record: BackedUpFile | None = None
        try:
            existing_record = get_backed_up_file(db_conn, relative_file_path)

            # Skip if mtime is unchanged
            if existing_record is not None and existing_record.mtime == file_mtime:
                backup_result.skipped += 1
                mark_file_status(db_conn, relative_file_path, "skipped")
                db_conn.commit()
                if verbose:
                    logger.debug("SKIP  %s (mtime unchanged)", relative_file_path)
                continue

            file_mime_type = _get_mime_type(absolute_file_path)
            parent_drive_folder_id = _ensure_parent_folder_hierarchy(
                relative_file_path=relative_file_path,
                root_drive_folder_id=config.drive_folder_id,
                client=client,
                conn=db_conn,
                dry_run=dry_run,
            )

            if existing_record is None:
                # New file — upload
                if dry_run:
                    logger.info("[dry-run] UPLOAD %s", relative_file_path)
                    backup_result.uploaded += 1
                    continue

                new_drive_file_id = client.upload_file(
                    local_path=absolute_file_path,
                    drive_folder_id=parent_drive_folder_id,
                    mime_type=file_mime_type,
                )
                backed_up_file = BackedUpFile(
                    local_path=relative_file_path,
                    drive_file_id=new_drive_file_id,
                    drive_folder_id=parent_drive_folder_id,
                    mtime=file_mtime,
                    size_bytes=file_size_bytes,
                    status="uploaded",
                    uploaded_at=now_iso,
                    updated_at=now_iso,
                )
                upsert_backed_up_file(db_conn, backed_up_file)
                db_conn.commit()
                backup_result.uploaded += 1
                if verbose:
                    logger.debug("UPLOAD %s → %s", relative_file_path, new_drive_file_id)

            else:
                # Existing file with changed mtime — update in-place
                if dry_run:
                    logger.info("[dry-run] UPDATE %s", relative_file_path)
                    backup_result.updated += 1
                    continue

                client.update_file(
                    drive_file_id=existing_record.drive_file_id,
                    local_path=absolute_file_path,
                    mime_type=file_mime_type,
                )
                updated_record = BackedUpFile(
                    local_path=relative_file_path,
                    drive_file_id=existing_record.drive_file_id,
                    drive_folder_id=parent_drive_folder_id,
                    mtime=file_mtime,
                    size_bytes=file_size_bytes,
                    status="updated",
                    uploaded_at=existing_record.uploaded_at,
                    updated_at=now_iso,
                )
                upsert_backed_up_file(db_conn, updated_record)
                db_conn.commit()
                backup_result.updated += 1
                if verbose:
                    logger.debug("UPDATE %s", relative_file_path)

        except Exception as file_error:
            logger.error("Error processing %s: %s", relative_file_path, file_error)
            backup_result.errors += 1
            backup_result.error_paths.append(relative_file_path)

            # Record the error in the DB so gdrive status reflects it after the session ends
            try:
                if not dry_run:
                    if existing_record is None:
                        # No row exists yet — insert a placeholder so the error is visible
                        error_record = BackedUpFile(
                            local_path=relative_file_path,
                            drive_file_id="",
                            drive_folder_id="",
                            mtime=file_mtime,
                            size_bytes=file_size_bytes,
                            status="error",
                            uploaded_at=now_iso,
                            updated_at=now_iso,
                        )
                        upsert_backed_up_file(db_conn, error_record)
                    else:
                        mark_file_status(db_conn, relative_file_path, "error")
                    db_conn.commit()
            except Exception as mark_error:
                logger.debug("Could not mark error status for %s: %s", relative_file_path, mark_error)

    return backup_result


def run_prune(
    config: GDriveConfig,
    client: DriveClient,
    db_conn: sqlite3.Connection,
    dry_run: bool = False,
    verbose: bool = False,
) -> PruneResult:
    """Delete Drive files whose local paths match any exclude_pattern.

    Scans the backed_up_files table and removes any entry whose path matches
    a pattern in config.exclude_patterns. The file is permanently deleted from
    Drive and its row is removed from the database so a future backup would
    re-upload it if the pattern is later removed.

    Args:
        config: Loaded GDriveConfig with exclude_patterns to match against.
        client: Authenticated DriveClient.
        db_conn: Open SQLite connection to the gdrive database.
        dry_run: If True, log what would be deleted without making API calls
                 or modifying the database.
        verbose: If True, log each deleted file at DEBUG level.

    Returns:
        A PruneResult summarising the run.
    """
    prune_result = PruneResult()

    if not config.exclude_patterns:
        logger.info("No exclude_patterns configured — nothing to prune.")
        return prune_result

    source_dir_name = Path(config.source_dir).name
    all_files = get_all_backed_up_files(db_conn)
    logger.info("Scanning %d backed-up file(s) against exclude_patterns.", len(all_files))

    for backed_up_file in all_files:
        local_path = backed_up_file.local_path

        # DB paths are relative to parent of source_dir: "source-dir-name/subdir/file.md"
        # Strip the source dir prefix to match against path relative to source_dir: "subdir/file.md"
        prefix = source_dir_name + "/"
        path_from_source = local_path[len(prefix) :] if local_path.startswith(prefix) else local_path
        file_name = Path(local_path).name

        if not _is_excluded(file_name, path_from_source, config.exclude_patterns):
            continue

        if dry_run:
            logger.info("[dry-run] PRUNE %s", local_path)
            prune_result.deleted += 1
            continue

        try:
            client.delete_file(backed_up_file.drive_file_id)
            delete_backed_up_file(db_conn, local_path)
            db_conn.commit()
            prune_result.deleted += 1
            if verbose:
                logger.debug("PRUNE %s (Drive ID: %s)", local_path, backed_up_file.drive_file_id)
        except Exception as prune_error:
            logger.error("Error pruning %s: %s", local_path, prune_error)
            prune_result.errors += 1
            prune_result.error_paths.append(local_path)

    return prune_result
