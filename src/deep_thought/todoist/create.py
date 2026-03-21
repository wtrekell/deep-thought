"""Business logic for the `todoist create` subcommand.

Creates a new task via the Todoist API, converts it to a local model, and
writes it to the local SQLite database so it is immediately available for
export and further use without requiring a full pull.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from deep_thought.todoist.db.queries import (
    get_all_labels,
    get_all_projects,
    get_sections_by_project,
    upsert_task_with_labels,
)
from deep_thought.todoist.models import TaskLocal

if TYPE_CHECKING:
    import sqlite3

    from deep_thought.todoist.client import TodoistClient


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class CreateResult:
    """Summary of a create task operation."""

    task_id: str = ""
    task_content: str = ""
    created: bool = False
    dry_run: bool = False
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Private resolution helpers
# ---------------------------------------------------------------------------


def _resolve_project_id(conn: sqlite3.Connection, project_name: str) -> str:
    """Look up a project by name in the local database and return its ID.

    Args:
        conn: An open SQLite connection.
        project_name: The exact display name of the project.

    Returns:
        The Todoist string ID of the matching project.

    Raises:
        ValueError: If no project with that name exists in the local database.
    """
    all_project_rows = get_all_projects(conn)
    for project_row in all_project_rows:
        if project_row["name"] == project_name:
            return str(project_row["id"])
    raise ValueError(f"Project '{project_name}' not found in local database. Run 'todoist pull' first.")


def _resolve_section_id(conn: sqlite3.Connection, project_id: str, section_name: str) -> str:
    """Look up a section by name within a project and return its ID.

    Args:
        conn: An open SQLite connection.
        project_id: The Todoist string ID of the parent project.
        section_name: The exact display name of the section.

    Returns:
        The Todoist string ID of the matching section.

    Raises:
        ValueError: If no section with that name exists in the project.
    """
    project_section_rows = get_sections_by_project(conn, project_id)
    for section_row in project_section_rows:
        if section_row["name"] == section_name:
            return str(section_row["id"])
    raise ValueError(f"Section '{section_name}' not found in project. Run 'todoist pull' first.")


def _resolve_label_ids(
    conn: sqlite3.Connection,
    label_names: list[str],
) -> tuple[list[str], dict[str, str]]:
    """Resolve label names to IDs using the local database.

    Args:
        conn: An open SQLite connection.
        label_names: List of label display names to resolve.

    Returns:
        A tuple of (resolved_label_ids, full_name_to_id_map) where
        resolved_label_ids contains only the IDs for the requested names,
        and full_name_to_id_map covers all labels in the database.

    Raises:
        ValueError: If any requested label name does not exist in the local database,
                    listing all missing names in the error message.
    """
    all_label_rows = get_all_labels(conn)
    full_name_to_id_map: dict[str, str] = {row["name"]: row["id"] for row in all_label_rows}

    missing_label_names = [name for name in label_names if name not in full_name_to_id_map]
    if missing_label_names:
        missing_names_display = ", ".join(f"'{name}'" for name in missing_label_names)
        raise ValueError(f"Label(s) not found in local database: {missing_names_display}. Run 'todoist pull' first.")

    resolved_label_ids = [full_name_to_id_map[name] for name in label_names]
    return resolved_label_ids, full_name_to_id_map


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def create_task(
    client: TodoistClient,
    conn: sqlite3.Connection,
    task_content: str,
    project_name: str,
    *,
    description: str | None = None,
    due_string: str | None = None,
    priority: int | None = None,
    label_names: list[str] | None = None,
    section_name: str | None = None,
    dry_run: bool = False,
) -> CreateResult:
    """Create a new task in Todoist and write it to the local database.

    Resolves project, section, and label names against the local database
    before calling the API. If dry_run is True, resolution still occurs
    (to catch typos early) but no API call or database write is made.

    Args:
        client: An initialised TodoistClient.
        conn: An open SQLite connection.
        task_content: The text content of the new task.
        project_name: The display name of the project to add the task to.
        description: Optional longer description for the task.
        due_string: Optional natural language due date (e.g. 'tomorrow', 'next Friday').
        priority: Optional priority level: 1=normal, 2=medium, 3=high, 4=urgent.
        label_names: Optional list of label names to attach to the task.
        section_name: Optional section name within the project.
        dry_run: If True, resolve names and return a result without calling the API.

    Returns:
        A CreateResult describing what happened.

    Raises:
        ValueError: If project, section, or any label name cannot be resolved locally.
    """
    # Resolve project — let ValueError propagate to the caller
    resolved_project_id = _resolve_project_id(conn, project_name)

    # Resolve section if requested
    resolved_section_id: str | None = None
    if section_name is not None:
        resolved_section_id = _resolve_section_id(conn, resolved_project_id, section_name)

    # Resolve labels if requested; build the full name→id map for upsert later
    label_name_to_id_map: dict[str, str] = {}
    if label_names:
        _resolved_ids, label_name_to_id_map = _resolve_label_ids(conn, label_names)

    # Short-circuit for dry runs: resolution happened, but no writes
    if dry_run:
        return CreateResult(task_id="(dry-run)", task_content=task_content, dry_run=True)

    # Build only the kwargs that the SDK should receive (skip None values)
    create_kwargs: dict[str, Any] = {"project_id": resolved_project_id}
    if resolved_section_id is not None:
        create_kwargs["section_id"] = resolved_section_id
    if description is not None:
        create_kwargs["description"] = description
    if due_string is not None:
        create_kwargs["due_string"] = due_string
    if priority is not None:
        create_kwargs["priority"] = priority
    if label_names:
        # The SDK accepts label name strings directly
        create_kwargs["labels"] = label_names

    sdk_task = client.create_task(content=task_content, **create_kwargs)
    local_task = TaskLocal.from_sdk(sdk_task)

    upsert_task_with_labels(conn, local_task, label_name_to_id_map)
    conn.commit()

    return CreateResult(task_id=local_task.id, task_content=local_task.content, created=True)
