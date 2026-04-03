"""Push logic for the Todoist Tool: local DB changes → Todoist API.

Finds tasks that have been locally modified since their last sync (updated_at > synced_at),
applies push filters, optionally prompts for confirmation, and updates each task via the
Todoist API. Marks successfully pushed tasks as synced in the database.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Any

from deep_thought.progress import track_items
from deep_thought.todoist.create import _validate_priority
from deep_thought.todoist.db.queries import (
    get_modified_tasks,
    get_project_ids_by_name,
    mark_task_synced,
    set_sync_value,
)
from deep_thought.todoist.filters import apply_push_filters
from deep_thought.todoist.models import TaskLocal

if TYPE_CHECKING:
    import sqlite3

    from deep_thought.todoist.client import TodoistClient
    from deep_thought.todoist.config import TodoistConfig


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class PushResult:
    """Summary of what was pushed to Todoist during a push operation."""

    tasks_pushed: int = 0
    tasks_filtered_out: int = 0
    tasks_failed: int = 0
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _task_dict_to_local_model(task_dict: dict[str, Any]) -> TaskLocal:
    """Convert a raw DB row dict back into a TaskLocal object.

    The DB stores labels as a JSON string; this function deserialises them
    back into a list[str] so the TaskLocal is properly typed.

    Args:
        task_dict: A dict from get_modified_tasks() or similar query functions.

    Returns:
        A TaskLocal with labels as list[str].
    """
    raw_labels = task_dict.get("labels", "[]")
    try:
        deserialized_labels: list[str] = json.loads(raw_labels) if isinstance(raw_labels, str) else raw_labels
    except json.JSONDecodeError:
        task_id_for_log = task_dict.get("id", "<unknown>")
        logger.warning("Task %s has malformed JSON in labels column; treating as no labels.", task_id_for_log)
        deserialized_labels = []

    return TaskLocal(
        id=task_dict["id"],
        content=task_dict["content"],
        description=task_dict.get("description") or "",
        project_id=task_dict["project_id"],
        section_id=task_dict.get("section_id"),
        parent_id=task_dict.get("parent_id"),
        order_index=task_dict.get("order_index", 0),
        priority=task_dict.get("priority", 1),
        due_date=task_dict.get("due_date"),
        due_string=task_dict.get("due_string"),
        due_is_recurring=task_dict.get("due_is_recurring", False),
        due_lang=task_dict.get("due_lang"),
        due_timezone=task_dict.get("due_timezone"),
        deadline_date=task_dict.get("deadline_date"),
        deadline_lang=task_dict.get("deadline_lang"),
        duration_amount=task_dict.get("duration_amount"),
        duration_unit=task_dict.get("duration_unit"),
        assignee_id=task_dict.get("assignee_id"),
        assigner_id=task_dict.get("assigner_id"),
        creator_id=task_dict.get("creator_id"),
        is_completed=bool(task_dict.get("is_completed", False)),
        completed_at=task_dict.get("completed_at"),
        labels=deserialized_labels,
        url=task_dict.get("url") or "",
        created_at=task_dict.get("created_at") or "",
        updated_at=task_dict.get("updated_at") or "",
    )


def _build_update_kwargs(task: TaskLocal) -> dict[str, Any]:
    """Build the kwargs dict for client.update_task() from a TaskLocal.

    Only includes fields that the Todoist API update_task endpoint accepts.
    None values for optional fields are intentionally excluded so we don't
    inadvertently clear fields on the remote task.

    Args:
        task: A TaskLocal with the desired updated state.

    Returns:
        Dict of keyword arguments to pass to client.update_task().
    """
    update_kwargs: dict[str, Any] = {
        "content": task.content,
        "description": task.description,
        "priority": _validate_priority(task.priority),
        "labels": task.labels,
    }

    if task.due_string is not None:
        update_kwargs["due_string"] = task.due_string
    elif task.due_date is not None:
        try:
            update_kwargs["due_date"] = date.fromisoformat(task.due_date)
        except ValueError:
            logger.warning("Task %s has malformed due_date %r; skipping field.", task.id, task.due_date)

    if task.deadline_date is not None:
        try:
            update_kwargs["deadline_date"] = date.fromisoformat(task.deadline_date)
        except ValueError:
            logger.warning("Task %s has malformed deadline_date %r; skipping field.", task.id, task.deadline_date)

    if task.assignee_id is not None:
        update_kwargs["assignee_id"] = task.assignee_id

    if task.duration_amount is not None and task.duration_unit is not None:
        update_kwargs["duration"] = task.duration_amount
        update_kwargs["duration_unit"] = task.duration_unit

    return update_kwargs


def _print_task_changes(task: TaskLocal) -> None:
    """Print a human-readable summary of a task that is about to be pushed.

    Args:
        task: The TaskLocal with pending changes.
    """
    print(f"  Task: {task.id} — {task.content}")
    if task.is_completed:
        print("    status: completed")
    print(f"    priority: {task.priority}")
    if task.labels:
        print(f"    labels: {', '.join(task.labels)}")
    if task.due_date:
        print(f"    due: {task.due_date}")
    if task.description:
        print(f"    description: {task.description[:80]}{'...' if len(task.description) > 80 else ''}")


def _confirm_push() -> bool:
    """Prompt the user to confirm pushing a task change.

    Returns:
        True if the user confirms, False otherwise.
    """
    response = input("    Push this change? [y/N] ").strip().lower()
    return response in {"y", "yes"}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def push(
    client: TodoistClient,
    config: TodoistConfig,
    conn: sqlite3.Connection,
    *,
    dry_run: bool = False,
    verbose: bool = False,
    project_filter: str | None = None,
) -> PushResult:
    """Push locally modified tasks back to the Todoist API.

    Steps:
    1. Query tasks where updated_at > synced_at (locally modified).
    2. Apply push filters from configuration.
    3. If project_filter is set, limit to that project only.
    4. For each task:
       a. If require_confirmation and not dry_run: print changes and prompt.
       b. Call client.update_task() with the changed fields.
       c. Mark the task as synced in the DB.
    5. Commit and return a summary.

    Args:
        client: An initialized TodoistClient.
        config: The loaded TodoistConfig.
        conn: An open SQLite connection.
        dry_run: If True, identify and report changes but do not push or update DB.
        verbose: If True, print progress messages to stdout.
        project_filter: If provided, only push tasks belonging to this project name.

    Returns:
        A PushResult with counts of pushed, filtered, and failed tasks.
    """
    result = PushResult()

    # ------------------------------------------------------------------
    # Find locally modified tasks
    # ------------------------------------------------------------------
    modified_task_rows = get_modified_tasks(conn)
    modified_tasks = [_task_dict_to_local_model(row) for row in modified_task_rows]

    if verbose:
        print(f"Found {len(modified_tasks)} locally modified task(s).")

    # ------------------------------------------------------------------
    # Apply push filters
    # ------------------------------------------------------------------
    filtered_tasks = apply_push_filters(modified_tasks, config.push_filters)
    tasks_filtered_count = len(modified_tasks) - len(filtered_tasks)
    result.tasks_filtered_out = tasks_filtered_count

    if verbose and tasks_filtered_count > 0:
        print(f"  {tasks_filtered_count} task(s) excluded by push filters.")

    # ------------------------------------------------------------------
    # If project_filter is set, further restrict by project name.
    # We only have project_id on the task, so we need to match by ID.
    # Fetch the project name→ID map from what we already have in the DB.
    # ------------------------------------------------------------------
    if project_filter is not None:
        allowed_project_ids = set(get_project_ids_by_name(conn, project_filter))
        filtered_tasks = [task for task in filtered_tasks if task.project_id in allowed_project_ids]

        if verbose:
            print(f"  Filtered to project '{project_filter}': {len(filtered_tasks)} task(s) remain.")

    # ------------------------------------------------------------------
    # Push each task
    # ------------------------------------------------------------------
    tasks_iterable = (
        filtered_tasks
        if config.push_filters.require_confirmation
        else track_items(filtered_tasks, description="Pushing tasks")
    )
    for task in tasks_iterable:
        if dry_run:
            if verbose or config.push_filters.require_confirmation:
                print(f"[dry-run] Would push task {task.id}: {task.content}")
            result.tasks_pushed += 1
            continue

        if config.push_filters.require_confirmation:
            _print_task_changes(task)
            if not _confirm_push():
                if verbose:
                    print(f"    Skipped task {task.id}.")
                result.tasks_filtered_out += 1
                continue

        try:
            if task.is_completed:
                client.close_task(task.id)
            else:
                update_kwargs = _build_update_kwargs(task)
                client.update_task(task.id, **update_kwargs)
            mark_task_synced(conn, task.id)
            result.tasks_pushed += 1

            if verbose:
                print(f"  Pushed task {task.id}: {task.content}")

        except Exception as push_error:
            error_message = f"Failed to push task {task.id} ({task.content!r}): {push_error}"
            result.errors.append(error_message)
            result.tasks_failed += 1

            if verbose:
                print(f"  ERROR: {error_message}")

    if not dry_run:
        set_sync_value(conn, "last_sync_time", datetime.now(UTC).isoformat())
        conn.commit()

    if verbose:
        print(
            f"Push complete: {result.tasks_pushed} pushed, "
            f"{result.tasks_filtered_out} filtered/skipped, "
            f"{result.tasks_failed} failed."
        )

    return result
