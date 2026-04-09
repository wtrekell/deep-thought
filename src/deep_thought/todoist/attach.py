"""Business logic for the `todoist attach` subcommand.

Uploads a local file to Todoist via the Sync API v9, then creates a comment
on the specified task with the uploaded file as an attachment. The new comment
is written to the local SQLite database immediately so it is visible in exports
without requiring a full pull.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from deep_thought.todoist.db.queries import get_task_by_id, upsert_comment

if TYPE_CHECKING:
    import sqlite3
    from pathlib import Path

    from deep_thought.todoist.client import TodoistClient


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class AttachResult:
    """Summary of a file attachment operation."""

    task_id: str = ""
    task_content: str = ""
    file_name: str = ""
    file_size: int = 0
    comment_id: str = ""
    dry_run: bool = False


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------


def attach_file(
    client: TodoistClient | None,
    conn: sqlite3.Connection,
    task_id: str,
    file_path: Path,
    message: str = "File attachment",
    dry_run: bool = False,
) -> AttachResult:
    """Upload a local file to Todoist and attach it to a task as a comment.

    Validates that the task exists in the local database and that the file
    exists on disk before making any API calls. In dry-run mode, returns a
    result describing what would happen without contacting Todoist.

    After a successful upload, writes the new comment (including attachment
    metadata) to the local SQLite database so it appears in exports immediately.

    Args:
        client: An authenticated TodoistClient instance. May be None only when
            dry_run is True — passing None with dry_run=False raises ValueError.
        conn: An open SQLite connection to the local database.
        task_id: Todoist task ID to attach the file to.
        file_path: Path to the local file to upload.
        message: Text body for the comment that carries the attachment.
        dry_run: When True, validate inputs but skip API calls and DB writes.

    Returns:
        An AttachResult describing the operation.

    Raises:
        ValueError: If the task ID is not found in the local database, or if
            client is None and dry_run is False.
        FileNotFoundError: If file_path does not exist on disk.
    """
    task_row = get_task_by_id(conn, task_id)
    if task_row is None:
        raise ValueError(f"Task '{task_id}' not found in local database. Run 'todoist pull' first.")

    task_content: str = task_row.get("content") or "(no content)"

    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    if dry_run:
        logger.debug("dry-run: skipping upload for %s", file_path.name)
        return AttachResult(
            task_id=task_id,
            task_content=task_content,
            file_name=file_path.name,
            file_size=file_path.stat().st_size,
            comment_id="",
            dry_run=True,
        )

    if client is None:
        raise ValueError("client must not be None when dry_run is False.")

    logger.debug("Uploading %s to Todoist…", file_path.name)
    attachment: dict[str, Any] = client.upload_attachment(file_path)
    logger.debug("Upload complete: %s", attachment.get("file_url"))

    comment = client.add_comment_with_attachment(task_id, message, attachment)

    comment_data: dict[str, Any] = {
        "id": comment.id,
        "task_id": task_id,
        "project_id": None,
        "content": message,
        "posted_at": comment.posted_at,
        "poster_id": comment.poster_id,
        "attachment_json": json.dumps(attachment),
    }
    upsert_comment(conn, comment_data)
    conn.commit()

    return AttachResult(
        task_id=task_id,
        task_content=task_content,
        file_name=attachment.get("file_name") or file_path.name,
        file_size=int(attachment.get("file_size") or 0),
        comment_id=comment.id,
        dry_run=False,
    )
