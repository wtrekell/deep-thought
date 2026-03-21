"""Pull logic for the Todoist Tool: API → local models → filters → DB → JSON snapshot.

Fetches all configured projects from the Todoist API, converts SDK objects to
local models, applies pull filters, writes to the SQLite database, and saves
a JSON snapshot of the raw API response for debugging/backup.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from deep_thought.todoist.db.queries import (
    get_all_labels,
    set_sync_value,
    upsert_comment,
    upsert_label,
    upsert_project,
    upsert_section,
    upsert_task_with_labels,
)
from deep_thought.todoist.db.schema import get_data_dir
from deep_thought.todoist.filters import apply_pull_filters
from deep_thought.todoist.models import (
    CommentLocal,
    LabelLocal,
    ProjectLocal,
    SectionLocal,
    TaskLocal,
)

if TYPE_CHECKING:
    import sqlite3
    from pathlib import Path

    from todoist_api_python.models import Project

    from deep_thought.todoist.client import TodoistClient
    from deep_thought.todoist.config import TodoistConfig


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class PullResult:
    """Summary of what was fetched and stored during a pull operation."""

    projects_synced: int = 0
    sections_synced: int = 0
    tasks_synced: int = 0
    tasks_filtered_out: int = 0
    comments_synced: int = 0
    labels_synced: int = 0
    snapshot_path: str | None = None
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _snapshots_dir() -> Path:
    """Return the path to the JSON snapshots directory, creating it if needed."""
    snapshots_directory = get_data_dir() / "snapshots"
    snapshots_directory.mkdir(parents=True, exist_ok=True)
    return snapshots_directory


def _iso_timestamp_filename() -> str:
    """Return an ISO-8601 timestamp string safe for use as a filename."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H%M%S")


def _filter_api_projects_to_configured(
    api_projects: list[Project],
    configured_project_names: list[str],
    project_name_filter: str | None,
) -> list[Project]:
    """Return only the API projects that appear in the configured opt-in list.

    If configured_project_names is empty, no opt-in restriction applies and all API
    projects are used as candidates (label filters then limit what gets stored).
    If project_name_filter is provided, further limits to a single project name.

    Args:
        api_projects: All projects returned by the Todoist API.
        configured_project_names: Project names from the YAML config opt-in list.
        project_name_filter: Optional single project name to further restrict to.

    Returns:
        Filtered list of SDK Project objects.
    """
    # Empty configured list = no opt-in restriction; collect from all projects
    if not configured_project_names:
        if project_name_filter is not None:
            return [project for project in api_projects if project.name == project_name_filter]
        return list(api_projects)

    allowed_names = set(configured_project_names)
    if project_name_filter is not None:
        allowed_names = {project_name_filter} & allowed_names

    return [project for project in api_projects if project.name in allowed_names]


def _build_label_name_to_id_map(conn: sqlite3.Connection) -> dict[str, str]:
    """Build a mapping from label name → label ID using the current DB state.

    Args:
        conn: An open SQLite connection.

    Returns:
        Dict mapping label name strings to their Todoist ID strings.
    """
    all_label_rows = get_all_labels(conn)
    return {row["name"]: row["id"] for row in all_label_rows}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def pull(
    client: TodoistClient,
    config: TodoistConfig,
    conn: sqlite3.Connection,
    *,
    dry_run: bool = False,
    verbose: bool = False,
    project_filter: str | None = None,
) -> PullResult:
    """Pull data from the Todoist API and store it in the local database.

    Steps:
    1. Fetch all projects from the API and filter to configured opt-in list.
    2. Fetch labels globally (not per-project) and upsert them.
    3. For each configured project: fetch sections, tasks, and comments.
    4. Convert SDK objects to local models.
    5. Apply pull filters to tasks.
    6. If not dry_run: upsert all data to the DB.
    7. Save a JSON snapshot to <data_dir>/snapshots/.
    8. Return a summary of what was pulled.

    Args:
        client: An initialized TodoistClient.
        config: The loaded TodoistConfig.
        conn: An open SQLite connection.
        dry_run: If True, fetch and count data but do not write to DB or snapshot.
        verbose: If True, print progress messages to stdout.
        project_filter: If provided, only sync this one project name.

    Returns:
        A PullResult with counts of synced and filtered items.
    """
    result = PullResult()

    # ------------------------------------------------------------------
    # Fetch all projects and filter to configured list
    # ------------------------------------------------------------------
    api_projects = client.get_projects()
    configured_projects = _filter_api_projects_to_configured(api_projects, config.projects, project_filter)

    if verbose:
        print(f"Found {len(configured_projects)} configured project(s) to sync.")

    # ------------------------------------------------------------------
    # Fetch and upsert labels (global, not per-project)
    # ------------------------------------------------------------------
    api_labels = client.get_labels()
    local_labels = [LabelLocal.from_sdk(label) for label in api_labels]
    result.labels_synced = len(local_labels)

    if verbose:
        print(f"Fetched {result.labels_synced} label(s).")

    if not dry_run:
        for label in local_labels:
            upsert_label(conn, label.to_dict())
        conn.commit()

    # Build a name→ID map from the labels we just upserted (or fetched)
    # We derive this from local_labels rather than re-querying if dry_run
    label_name_to_id: dict[str, str] = {label.name: label.id for label in local_labels}

    # ------------------------------------------------------------------
    # Collect raw API data for snapshot
    # ------------------------------------------------------------------
    snapshot_data: dict[str, Any] = {
        "timestamp": datetime.now(UTC).isoformat(),
        "projects": [],
        "sections": [],
        "tasks": [],
        "labels": [label.to_dict() for label in local_labels],
        "comments": [],
    }

    # ------------------------------------------------------------------
    # Per-project fetch, convert, filter, and upsert
    # ------------------------------------------------------------------
    for api_project in configured_projects:
        local_project = ProjectLocal.from_sdk(api_project)

        if verbose:
            print(f"  Project: {local_project.name}")

        snapshot_data["projects"].append(local_project.to_dict())
        if not dry_run:
            upsert_project(conn, local_project.to_dict())

        result.projects_synced += 1

        # Sections
        api_sections = client.get_sections(project_id=local_project.id)
        local_sections = [SectionLocal.from_sdk(section) for section in api_sections]
        snapshot_data["sections"].extend(section.to_dict() for section in local_sections)
        if not dry_run:
            for section in local_sections:
                upsert_section(conn, section.to_dict())

        result.sections_synced += len(local_sections)

        if verbose:
            print(f"    Sections: {len(local_sections)}")

        # Tasks — fetch, convert, then apply pull filters
        api_tasks = client.get_tasks(project_id=local_project.id)
        local_tasks = [TaskLocal.from_sdk(task) for task in api_tasks]

        filtered_tasks = apply_pull_filters(local_tasks, config.pull_filters)
        tasks_filtered_count = len(local_tasks) - len(filtered_tasks)
        result.tasks_filtered_out += tasks_filtered_count

        if verbose:
            print(f"    Tasks: {len(local_tasks)} fetched, {tasks_filtered_count} filtered out.")

        for task in local_tasks:
            # Note: task.to_dict() includes labels as a Python list here.
            # The DB stores labels as a JSON string (see upsert_task_with_labels in db/queries.py).
            # This difference is intentional — the snapshot is for debugging/backup,
            # not for DB import, so the native list form is more readable.
            snapshot_data["tasks"].append(task.to_dict())
        if not dry_run:
            for task in filtered_tasks:
                upsert_task_with_labels(conn, task, label_name_to_id)

        result.tasks_synced += len(filtered_tasks)

        # Comments (only if comment sync is enabled and not dry_run for writing)
        if config.comments.sync:
            for task in filtered_tasks:
                task_comments = client.get_comments(task_id=task.id)
                local_comments = [CommentLocal.from_sdk(comment) for comment in task_comments]
                result.comments_synced += len(local_comments)

                for comment in local_comments:
                    snapshot_data["comments"].append(comment.to_dict())
                if not dry_run:
                    for comment in local_comments:
                        upsert_comment(conn, comment.to_dict())

    # ------------------------------------------------------------------
    # Commit all writes
    # ------------------------------------------------------------------
    if not dry_run:
        conn.commit()

    # ------------------------------------------------------------------
    # Record the time of this sync so status/diff can report it
    # ------------------------------------------------------------------
    if not dry_run:
        set_sync_value(conn, "last_sync_time", datetime.now(UTC).isoformat())
        conn.commit()

    # ------------------------------------------------------------------
    # Save JSON snapshot
    # ------------------------------------------------------------------
    if not dry_run:
        snapshot_filename = f"{_iso_timestamp_filename()}.json"
        snapshot_path = _snapshots_dir() / snapshot_filename
        snapshot_path.write_text(json.dumps(snapshot_data, indent=2), encoding="utf-8")
        result.snapshot_path = str(snapshot_path)

        if verbose:
            print(f"  Snapshot saved: {result.snapshot_path}")

    if verbose:
        print(
            f"Pull complete: {result.projects_synced} projects, "
            f"{result.sections_synced} sections, "
            f"{result.tasks_synced} tasks "
            f"({result.tasks_filtered_out} filtered), "
            f"{result.comments_synced} comments, "
            f"{result.labels_synced} labels."
        )

    return result
