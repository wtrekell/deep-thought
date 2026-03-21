"""
queries.py — Parameterized SQL query functions for the Todoist Tool database layer.

All functions accept an open sqlite3.Connection as their first argument and
return plain Python types (dicts, lists, None). No business logic lives here —
these are thin wrappers over SQL that the application layer calls directly.

Upsert strategy: INSERT OR REPLACE replaces the entire row when the primary
key conflicts. This is safe because we always provide all columns.

Timestamps: `synced_at` is always set to the current UTC time at the moment
of the write, marking when the local database last received this record from
the API. `updated_at` and `created_at` come from the API and are passed in
via the data dict unchanged.
"""

from __future__ import annotations

import json
import sqlite3  # noqa: TC003 — sqlite3.Row is used at runtime in _row_to_dict/_rows_to_dicts
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from deep_thought.todoist.models import TaskLocal

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _now_utc_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(UTC).isoformat()


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    """Convert a sqlite3.Row to a plain dict, or return None if the row is None."""
    if row is None:
        return None
    return dict(row)


def _rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    """Convert a list of sqlite3.Row objects to a list of plain dicts."""
    return [dict(row) for row in rows]


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------


def upsert_project(conn: sqlite3.Connection, project_data: dict[str, Any]) -> None:
    """Insert or replace a project row from API data.

    All columns are sourced from project_data. `synced_at` is set to the
    current UTC time regardless of what is in project_data.

    Args:
        conn: An open SQLite connection.
        project_data: Dict with keys matching the projects table columns.
                      Required key: 'id'.
    """
    synced_at = _now_utc_iso()
    conn.execute(
        """
        INSERT OR REPLACE INTO projects (
            id, name, description, color,
            is_archived, is_favorite, is_inbox_project, is_shared, is_collapsed,
            order_index, parent_id, folder_id, view_style, url, workspace_id,
            can_assign_tasks, created_at, updated_at, synced_at
        ) VALUES (
            :id, :name, :description, :color,
            :is_archived, :is_favorite, :is_inbox_project, :is_shared, :is_collapsed,
            :order_index, :parent_id, :folder_id, :view_style, :url, :workspace_id,
            :can_assign_tasks, :created_at, :updated_at, :synced_at
        );
        """,
        {**project_data, "synced_at": synced_at},
    )


def get_all_projects(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Return all projects ordered by order_index ascending.

    Args:
        conn: An open SQLite connection.

    Returns:
        List of dicts, one per project row. Empty list if none exist.
    """
    cursor = conn.execute("SELECT * FROM projects ORDER BY order_index ASC;")
    return _rows_to_dicts(cursor.fetchall())


def get_project_by_id(conn: sqlite3.Connection, project_id: str) -> dict[str, Any] | None:
    """Return a single project by its Todoist ID, or None if not found.

    Args:
        conn: An open SQLite connection.
        project_id: The Todoist string ID of the project.

    Returns:
        A dict of column values, or None if no matching row exists.
    """
    cursor = conn.execute("SELECT * FROM projects WHERE id = ?;", (project_id,))
    return _row_to_dict(cursor.fetchone())


def delete_project(conn: sqlite3.Connection, project_id: str) -> None:
    """Delete a project by ID. Cascades to sections, tasks, and comments.

    Args:
        conn: An open SQLite connection.
        project_id: The Todoist string ID of the project to delete.
    """
    conn.execute("DELETE FROM projects WHERE id = ?;", (project_id,))


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------


def upsert_section(conn: sqlite3.Connection, section_data: dict[str, Any]) -> None:
    """Insert or replace a section row from API data.

    Args:
        conn: An open SQLite connection.
        section_data: Dict with keys matching the sections table columns.
                      Required keys: 'id', 'project_id'.
    """
    synced_at = _now_utc_iso()
    conn.execute(
        """
        INSERT OR REPLACE INTO sections (
            id, name, project_id, order_index, is_collapsed, synced_at
        ) VALUES (
            :id, :name, :project_id, :order_index, :is_collapsed, :synced_at
        );
        """,
        {**section_data, "synced_at": synced_at},
    )


def get_sections_by_project(conn: sqlite3.Connection, project_id: str) -> list[dict[str, Any]]:
    """Return all sections belonging to a project, ordered by order_index.

    Args:
        conn: An open SQLite connection.
        project_id: The Todoist string ID of the parent project.

    Returns:
        List of section dicts. Empty list if none exist.
    """
    cursor = conn.execute(
        "SELECT * FROM sections WHERE project_id = ? ORDER BY order_index ASC;",
        (project_id,),
    )
    return _rows_to_dicts(cursor.fetchall())


def delete_section(conn: sqlite3.Connection, section_id: str) -> None:
    """Delete a section by ID. Tasks in this section have their section_id set to NULL.

    Args:
        conn: An open SQLite connection.
        section_id: The Todoist string ID of the section to delete.
    """
    conn.execute("DELETE FROM sections WHERE id = ?;", (section_id,))


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------


def upsert_task(conn: sqlite3.Connection, task_data: dict[str, Any]) -> None:
    """Insert or replace a task row from API data.

    Due, deadline, and duration fields should be pre-flattened in task_data
    (e.g., 'due_date', 'due_string', etc.) before calling this function.

    Args:
        conn: An open SQLite connection.
        task_data: Dict with keys matching the tasks table columns.
                   Required key: 'id', 'content', 'project_id'.
    """
    synced_at = _now_utc_iso()
    conn.execute(
        """
        INSERT OR REPLACE INTO tasks (
            id, content, description,
            project_id, section_id, parent_id, order_index, priority,
            due_date, due_string, due_is_recurring, due_lang, due_timezone,
            deadline_date, deadline_lang,
            duration_amount, duration_unit,
            assignee_id, assigner_id, creator_id,
            is_completed, completed_at,
            labels, url,
            created_at, updated_at, synced_at
        ) VALUES (
            :id, :content, :description,
            :project_id, :section_id, :parent_id, :order_index, :priority,
            :due_date, :due_string, :due_is_recurring, :due_lang, :due_timezone,
            :deadline_date, :deadline_lang,
            :duration_amount, :duration_unit,
            :assignee_id, :assigner_id, :creator_id,
            :is_completed, :completed_at,
            :labels, :url,
            :created_at, :updated_at, :synced_at
        );
        """,
        {**task_data, "synced_at": synced_at},
    )


def get_tasks_by_project(conn: sqlite3.Connection, project_id: str) -> list[dict[str, Any]]:
    """Return all tasks belonging to a project, ordered by order_index.

    Args:
        conn: An open SQLite connection.
        project_id: The Todoist string ID of the parent project.

    Returns:
        List of task dicts. Empty list if none exist.
    """
    cursor = conn.execute(
        "SELECT * FROM tasks WHERE project_id = ? ORDER BY order_index ASC;",
        (project_id,),
    )
    return _rows_to_dicts(cursor.fetchall())


def get_tasks_by_section(conn: sqlite3.Connection, section_id: str) -> list[dict[str, Any]]:
    """Return all tasks belonging to a section, ordered by order_index.

    Args:
        conn: An open SQLite connection.
        section_id: The Todoist string ID of the parent section.

    Returns:
        List of task dicts. Empty list if none exist.
    """
    cursor = conn.execute(
        "SELECT * FROM tasks WHERE section_id = ? ORDER BY order_index ASC;",
        (section_id,),
    )
    return _rows_to_dicts(cursor.fetchall())


def get_task_by_id(conn: sqlite3.Connection, task_id: str) -> dict[str, Any] | None:
    """Return a single task by its Todoist ID, or None if not found.

    Args:
        conn: An open SQLite connection.
        task_id: The Todoist string ID of the task.

    Returns:
        A dict of column values, or None if no matching row exists.
    """
    cursor = conn.execute("SELECT * FROM tasks WHERE id = ?;", (task_id,))
    return _row_to_dict(cursor.fetchone())


def get_modified_tasks(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Return tasks that have been locally modified since their last sync.

    A task is considered modified when updated_at is more recent than
    synced_at. Both values are ISO-8601 strings; SQLite compares them
    lexicographically, which is correct for ISO-8601 format.

    Args:
        conn: An open SQLite connection.

    Returns:
        List of task dicts where updated_at > synced_at.
    """
    cursor = conn.execute(
        "SELECT * FROM tasks WHERE updated_at > synced_at ORDER BY updated_at ASC;",
    )
    return _rows_to_dicts(cursor.fetchall())


def mark_task_synced(conn: sqlite3.Connection, task_id: str) -> None:
    """Update synced_at to now for a task, clearing its modified status.

    Call this after successfully pushing a task's changes back to the API.

    Args:
        conn: An open SQLite connection.
        task_id: The Todoist string ID of the task.
    """
    conn.execute(
        "UPDATE tasks SET synced_at = ? WHERE id = ?;",
        (_now_utc_iso(), task_id),
    )


def delete_task(conn: sqlite3.Connection, task_id: str) -> None:
    """Delete a task by ID. Cascades to task_labels and comments.

    Args:
        conn: An open SQLite connection.
        task_id: The Todoist string ID of the task to delete.
    """
    conn.execute("DELETE FROM tasks WHERE id = ?;", (task_id,))


# ---------------------------------------------------------------------------
# Labels
# ---------------------------------------------------------------------------


def upsert_label(conn: sqlite3.Connection, label_data: dict[str, Any]) -> None:
    """Insert or replace a label row from API data.

    Args:
        conn: An open SQLite connection.
        label_data: Dict with keys matching the labels table columns.
                    Required key: 'id', 'name'.
    """
    synced_at = _now_utc_iso()
    conn.execute(
        """
        INSERT OR REPLACE INTO labels (
            id, name, color, order_index, is_favorite, synced_at
        ) VALUES (
            :id, :name, :color, :order_index, :is_favorite, :synced_at
        );
        """,
        {**label_data, "synced_at": synced_at},
    )


def get_all_labels(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Return all labels ordered by order_index ascending.

    Args:
        conn: An open SQLite connection.

    Returns:
        List of label dicts. Empty list if none exist.
    """
    cursor = conn.execute("SELECT * FROM labels ORDER BY order_index ASC;")
    return _rows_to_dicts(cursor.fetchall())


# ---------------------------------------------------------------------------
# Task Labels (many-to-many join)
# ---------------------------------------------------------------------------


def set_task_labels(conn: sqlite3.Connection, task_id: str, label_ids: list[str]) -> None:
    """Replace all label associations for a task atomically.

    Deletes all existing task_labels rows for this task, then inserts new
    ones for each label_id in the provided list. This keeps the join table
    consistent with the current API state without needing to diff.

    Args:
        conn: An open SQLite connection.
        task_id: The Todoist string ID of the task.
        label_ids: List of Todoist label IDs to associate with this task.
                   Pass an empty list to remove all labels from the task.
    """
    synced_at = _now_utc_iso()
    conn.execute("DELETE FROM task_labels WHERE task_id = ?;", (task_id,))
    conn.executemany(
        "INSERT INTO task_labels (task_id, label_id, synced_at) VALUES (?, ?, ?);",
        [(task_id, label_id, synced_at) for label_id in label_ids],
    )


def upsert_task_with_labels(
    conn: sqlite3.Connection,
    task: TaskLocal,
    label_name_to_id: dict[str, str],
) -> None:
    """Write a task to the DB and update the task_labels join table.

    The labels field on TaskLocal is a list[str] of label names. The tasks
    table stores them as a JSON string. The task_labels join table stores
    label IDs, so we look each name up in the name→ID map.

    Args:
        conn: An open SQLite connection.
        task: A fully populated TaskLocal object.
        label_name_to_id: Map from label name to Todoist label ID.
    """
    task_dict = task.to_dict()
    # DB column expects JSON string, not a Python list
    task_dict["labels"] = json.dumps(task_dict["labels"])
    upsert_task(conn, task_dict)

    label_ids = [label_name_to_id[name] for name in task.labels if name in label_name_to_id]
    set_task_labels(conn, task.id, label_ids)


def get_labels_for_task(conn: sqlite3.Connection, task_id: str) -> list[dict[str, Any]]:
    """Return full label rows for all labels associated with a task.

    Joins task_labels with labels so callers receive the label name and
    color, not just the ID.

    Args:
        conn: An open SQLite connection.
        task_id: The Todoist string ID of the task.

    Returns:
        List of label dicts (id, name, color, order_index, is_favorite, synced_at).
    """
    cursor = conn.execute(
        """
        SELECT labels.*
        FROM labels
        INNER JOIN task_labels ON labels.id = task_labels.label_id
        WHERE task_labels.task_id = ?
        ORDER BY labels.order_index ASC;
        """,
        (task_id,),
    )
    return _rows_to_dicts(cursor.fetchall())


# ---------------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------------


def upsert_comment(conn: sqlite3.Connection, comment_data: dict[str, Any]) -> None:
    """Insert or replace a comment row from API data.

    `attachment_json` should be a JSON string serialized from the Attachment
    object before calling this function, or None if no attachment exists.

    Args:
        conn: An open SQLite connection.
        comment_data: Dict with keys matching the comments table columns.
                      Required key: 'id', 'content'. At least one of
                      'task_id' or 'project_id' should be non-null.
    """
    synced_at = _now_utc_iso()
    conn.execute(
        """
        INSERT OR REPLACE INTO comments (
            id, task_id, project_id, content,
            posted_at, poster_id, attachment_json, synced_at
        ) VALUES (
            :id, :task_id, :project_id, :content,
            :posted_at, :poster_id, :attachment_json, :synced_at
        );
        """,
        {**comment_data, "synced_at": synced_at},
    )


def get_comments_for_task(conn: sqlite3.Connection, task_id: str) -> list[dict[str, Any]]:
    """Return all comments for a task, ordered by posted_at ascending.

    Args:
        conn: An open SQLite connection.
        task_id: The Todoist string ID of the task.

    Returns:
        List of comment dicts. Empty list if none exist.
    """
    cursor = conn.execute(
        "SELECT * FROM comments WHERE task_id = ? ORDER BY posted_at ASC;",
        (task_id,),
    )
    return _rows_to_dicts(cursor.fetchall())


def delete_comment(conn: sqlite3.Connection, comment_id: str) -> None:
    """Delete a comment by ID.

    Args:
        conn: An open SQLite connection.
        comment_id: The Todoist string ID of the comment to delete.
    """
    conn.execute("DELETE FROM comments WHERE id = ?;", (comment_id,))


# ---------------------------------------------------------------------------
# Sync State
# ---------------------------------------------------------------------------


def get_sync_value(conn: sqlite3.Connection, key: str) -> str | None:
    """Read a value from the sync_state key/value store.

    Args:
        conn: An open SQLite connection.
        key: The key to look up (e.g., 'sync_token', 'schema_version').

    Returns:
        The stored string value, or None if the key does not exist.
    """
    cursor = conn.execute("SELECT value FROM sync_state WHERE key = ?;", (key,))
    row = cursor.fetchone()
    return row["value"] if row is not None else None


def set_sync_value(conn: sqlite3.Connection, key: str, value: str) -> None:
    """Write or overwrite a value in the sync_state key/value store.

    Args:
        conn: An open SQLite connection.
        key: The key to write (e.g., 'sync_token').
        value: The string value to store.
    """
    conn.execute(
        """
        INSERT INTO sync_state (key, value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT (key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at;
        """,
        (key, value, _now_utc_iso()),
    )
