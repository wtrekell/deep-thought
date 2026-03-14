"""
db — Database layer for the Todoist Tool.

Public API surface:
- Schema / connection management from schema.py
- All query functions from queries.py
"""

from __future__ import annotations

from deep_thought.todoist.db.queries import (
    delete_comment,
    delete_project,
    delete_section,
    delete_task,
    get_all_labels,
    get_all_projects,
    get_comments_for_task,
    get_labels_for_task,
    get_modified_tasks,
    get_project_by_id,
    get_sections_by_project,
    get_sync_value,
    get_task_by_id,
    get_tasks_by_project,
    get_tasks_by_section,
    mark_task_synced,
    set_sync_value,
    set_task_labels,
    upsert_comment,
    upsert_label,
    upsert_project,
    upsert_section,
    upsert_task,
)
from deep_thought.todoist.db.schema import (
    get_connection,
    get_database_path,
    initialize_database,
)

__all__ = [
    # Schema / connection
    "get_connection",
    "get_database_path",
    "initialize_database",
    # Projects
    "delete_project",
    "get_all_projects",
    "get_project_by_id",
    "upsert_project",
    # Sections
    "delete_section",
    "get_sections_by_project",
    "upsert_section",
    # Tasks
    "delete_task",
    "get_modified_tasks",
    "get_task_by_id",
    "get_tasks_by_project",
    "get_tasks_by_section",
    "mark_task_synced",
    "upsert_task",
    # Labels
    "get_all_labels",
    "upsert_label",
    # Task Labels
    "get_labels_for_task",
    "set_task_labels",
    # Comments
    "delete_comment",
    "get_comments_for_task",
    "upsert_comment",
    # Sync State
    "get_sync_value",
    "set_sync_value",
]
