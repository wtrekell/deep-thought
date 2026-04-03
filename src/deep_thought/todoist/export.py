"""Markdown export for the Todoist Tool: DB state → structured markdown files.

Each configured project gets a subdirectory. Each section produces one .md file.
Tasks without a section go into _unsectioned.md. The format is optimised for
machine parsing by Claude, using a key-value metadata list under each task.

Output structure:
    <data_dir>/export/<project-name>/<section-name>.md
    (<data_dir> defaults to data/todoist/ or DEEP_THOUGHT_DATA_DIR if set)

Markdown format (from requirements):
    # Project Name
    ## Section Name
    - [ ] Task content
      - id: 1234567890
      - priority: 1
      - labels: label1, label2
      - due: 2026-03-15
      - recurring: every week
      - deadline: 2026-03-20
      - assignee: collaborator-name
      - claude: repo=deep-thought, branch=main
      - description: Task description text
      - comments:
        - [2026-03-10 poster-name] Comment text
      - [ ] Subtask content
        - id: 1234567891
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from deep_thought.progress import track_items
from deep_thought.todoist.db.queries import (
    get_all_projects,
    get_comments_for_task,
    get_sections_by_project,
    get_tasks_by_project,
)
from deep_thought.todoist.db.schema import get_data_dir

if TYPE_CHECKING:
    import sqlite3
    from pathlib import Path

    from deep_thought.todoist.config import TodoistConfig


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class ExportResult:
    """Summary of what was written during an export operation."""

    projects_exported: int = 0
    files_written: int = 0
    tasks_exported: int = 0


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _default_export_dir() -> Path:
    """Return the canonical export directory path."""
    return get_data_dir() / "export"


def _safe_directory_name(name: str) -> str:
    """Convert a project or section name into a filesystem-safe directory/file name.

    Replaces characters that are problematic on common filesystems with hyphens
    and strips leading/trailing whitespace.

    Args:
        name: Raw name from Todoist (e.g., project or section name).

    Returns:
        A sanitised string safe for use as a directory or file name.
    """
    safe_chars = []
    for char in name.strip():
        if char in r'/\:*?"<>|':
            safe_chars.append("-")
        else:
            safe_chars.append(char)
    sanitized = "".join(safe_chars)
    # Strip leading dots to prevent path traversal names like ".." or "..."
    sanitized = sanitized.strip(".")
    if not sanitized:
        sanitized = "_unnamed"
    return sanitized


def _task_checkbox(is_completed: bool) -> str:
    """Return the markdown checkbox string for a task.

    Args:
        is_completed: Whether the task is marked complete.

    Returns:
        '- [x]' for completed tasks, '- [ ]' for active tasks.
    """
    return "- [x]" if is_completed else "- [ ]"


def _get_poster_name(poster_id: str) -> str:
    """Look up a collaborator display name by their Todoist user ID.

    Falls back to the raw poster_id if no matching record is found. The
    collaborators table is not part of the current schema, so this always
    returns the raw ID for now. This hook exists so the lookup can be
    improved when collaborator data is available.

    Args:
        poster_id: The Todoist user ID of the comment author.

    Returns:
        A display name string (currently the raw poster_id).
    """
    # Placeholder: collaborators are not stored in the current schema.
    # Return the raw ID so comments are still attributable.
    return poster_id


def _render_comment_line(conn: sqlite3.Connection, comment: dict[str, Any]) -> str:
    """Render a single comment as a markdown list entry.

    Format: [YYYY-MM-DD poster-name] Comment text

    The date is extracted from the ISO-8601 posted_at timestamp. If the
    content spans multiple lines only the first line is included to keep
    the flat list format parseable.

    Args:
        conn: An open SQLite connection (for poster name lookup).
        comment: A comment dict from get_comments_for_task().

    Returns:
        A formatted string like '[2026-03-10 poster-name] Comment text'.
    """
    posted_at: str = comment.get("posted_at") or ""
    date_part = posted_at[:10] if len(posted_at) >= 10 else posted_at
    poster_name = _get_poster_name(comment.get("poster_id") or "unknown")
    # Keep comment content to the first line for parsability
    content_first_line = (comment.get("content") or "").split("\n")[0]
    return f"[{date_part} {poster_name}] {content_first_line}"


def _render_task_block(
    conn: sqlite3.Connection,
    task: dict[str, Any],
    subtasks: list[dict[str, Any]],
    config: TodoistConfig,
    indent: str = "",
) -> list[str]:
    """Render a task and its subtasks as a list of markdown lines.

    Only includes metadata lines that have non-empty values. The claude
    metadata line is included when the task has the configured claude label.

    Args:
        conn: An open SQLite connection (for comment and collaborator lookups).
        task: A task dict from the database.
        subtasks: List of task dicts whose parent_id matches this task's id.
        config: The loaded TodoistConfig (for claude label/repo/branch).
        indent: String prepended to each line (for subtask nesting).

    Returns:
        List of markdown line strings (without trailing newlines).
    """
    lines: list[str] = []

    is_completed: bool = bool(task.get("is_completed", False))
    content: str = task.get("content") or ""
    task_id: str = task.get("id") or ""

    # Task heading line
    lines.append(f"{indent}{_task_checkbox(is_completed)} {content}")

    # Metadata: id (always present)
    lines.append(f"{indent}  - id: {task_id}")

    # Priority
    raw_priority = task.get("priority")
    priority: int = raw_priority if raw_priority is not None else 1
    lines.append(f"{indent}  - priority: {priority}")

    # Labels — stored as JSON string in DB
    raw_labels = task.get("labels", "[]")
    label_list: list[str] = json.loads(raw_labels) if isinstance(raw_labels, str) else raw_labels
    if label_list:
        lines.append(f"{indent}  - labels: {', '.join(label_list)}")

    # Due date
    due_date: str | None = task.get("due_date")
    if due_date:
        lines.append(f"{indent}  - due: {due_date}")

    # Recurring (due_string carries the recurrence description)
    due_is_recurring: bool | None = task.get("due_is_recurring")
    due_string: str | None = task.get("due_string")
    if due_is_recurring and due_string:
        lines.append(f"{indent}  - recurring: {due_string}")

    # Deadline
    deadline_date: str | None = task.get("deadline_date")
    if deadline_date:
        lines.append(f"{indent}  - deadline: {deadline_date}")

    # Assignee
    assignee_id: str | None = task.get("assignee_id")
    if assignee_id:
        # Use assignee_id directly — no collaborator name table yet
        lines.append(f"{indent}  - assignee: {assignee_id}")

    # Claude involvement marker — rendered as a YAML-structured block so the
    # consumer can parse repo and branch without splitting an inline string.
    if config.claude.label and config.claude.label in label_list:
        lines.append(f"{indent}  - claude:")
        if config.claude.repo:
            lines.append(f"{indent}      repo: {config.claude.repo}")
        claude_branch = config.claude.branch or "main"
        lines.append(f"{indent}      branch: {claude_branch}")

    # Description
    description: str = task.get("description") or ""
    if description:
        lines.append(f"{indent}  - description: {description}")

    # Comments
    if config.comments.sync:
        comments = get_comments_for_task(conn, task_id)
        if comments:
            lines.append(f"{indent}  - comments:")
            for comment in comments:
                comment_line = _render_comment_line(conn, comment)
                lines.append(f"{indent}    - {comment_line}")

    # Subtasks (one level of indentation added)
    for subtask in subtasks:
        subtask_lines = _render_task_block(conn, subtask, [], config, indent=indent + "  ")
        lines.extend(subtask_lines)

    return lines


def _render_section_file(
    conn: sqlite3.Connection,
    project_name: str,
    section_name: str,
    tasks: list[dict[str, Any]],
    config: TodoistConfig,
) -> str:
    """Render the full markdown content for a single section file.

    Organises tasks so that top-level tasks appear first, each followed by
    their subtasks inline. Subtasks (parent_id is not None) are collected
    and attached to their parent rather than rendered at the top level.

    Args:
        conn: An open SQLite connection.
        project_name: The display name of the project (for the H1 heading).
        section_name: The display name of the section (for the H2 heading).
        tasks: All task dicts belonging to this section.
        config: The loaded TodoistConfig.

    Returns:
        Complete markdown file content as a single string.
    """
    lines: list[str] = []

    lines.append(f"# {project_name}")
    lines.append("")
    lines.append(f"## {section_name}")
    lines.append("")

    # Separate top-level tasks from subtasks
    task_by_id: dict[str, dict[str, Any]] = {task["id"]: task for task in tasks}
    top_level_tasks: list[dict[str, Any]] = []
    subtask_map: dict[str, list[dict[str, Any]]] = {}

    for task in tasks:
        parent_id: str | None = task.get("parent_id")
        if parent_id is None or parent_id not in task_by_id:
            # Top-level within this section (or orphaned subtask)
            top_level_tasks.append(task)
        else:
            subtask_map.setdefault(parent_id, []).append(task)

    for top_level_task in top_level_tasks:
        task_id: str = top_level_task["id"]
        subtasks = subtask_map.get(task_id, [])
        task_lines = _render_task_block(conn, top_level_task, subtasks, config)
        lines.extend(task_lines)
        lines.append("")  # Blank line between tasks for readability

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def export_to_markdown(
    conn: sqlite3.Connection,
    config: TodoistConfig,
    *,
    output_dir: Path | None = None,
    project_filter: str | None = None,
    verbose: bool = False,
) -> ExportResult:
    """Export database contents to markdown files.

    Writes one file per section per project. Tasks without a section are
    written to a file named _unsectioned.md in the project directory.
    Only metadata fields with non-empty values are included.

    Args:
        conn: An open SQLite connection with row_factory = sqlite3.Row.
        config: The loaded TodoistConfig.
        output_dir: Directory to write export files into. Defaults to
                    <data_dir>/export/ (see DEEP_THOUGHT_DATA_DIR).
        project_filter: If provided, only export this project name.
        verbose: If True, print progress messages to stdout.

    Returns:
        An ExportResult with counts of projects, files, and tasks exported.
    """
    result = ExportResult()
    resolved_output_dir = output_dir if output_dir is not None else _default_export_dir()
    resolved_output_dir.mkdir(parents=True, exist_ok=True)

    all_project_rows = get_all_projects(conn)

    # When config.projects is empty, treat it the same way pull does: no opt-in
    # restriction, so all projects in the DB are candidates. This mirrors the
    # behaviour of _filter_api_projects_to_configured in pull.py.
    if config.projects:
        configured_project_names: set[str] = set(config.projects)
        if project_filter is not None:
            configured_project_names = {project_filter} & configured_project_names
        projects_to_export = [project for project in all_project_rows if project["name"] in configured_project_names]
    else:
        # Empty config.projects → export everything (label filters already applied at pull time)
        if project_filter is not None:
            projects_to_export = [project for project in all_project_rows if project["name"] == project_filter]
        else:
            projects_to_export = list(all_project_rows)

    for project_row in track_items(projects_to_export, description="Exporting"):
        project_id: str = project_row["id"]
        project_name: str = project_row["name"]

        if verbose:
            print(f"Exporting project: {project_name}")

        project_dir = resolved_output_dir / _safe_directory_name(project_name)
        # Directory is created lazily — only when there are tasks to write
        # so we do not leave empty directories for projects with no tasks.

        all_project_tasks = get_tasks_by_project(conn, project_id)
        sections = get_sections_by_project(conn, project_id)

        # Build section_id → section_name map
        section_id_to_name: dict[str, str] = {section["id"]: section["name"] for section in sections}

        # Group tasks by section_id (None → unsectioned)
        tasks_by_section: dict[str | None, list[dict[str, Any]]] = {}
        for task in all_project_tasks:
            section_id: str | None = task.get("section_id")
            tasks_by_section.setdefault(section_id, []).append(task)

        # Write one file per section that has tasks
        for section in sections:
            section_id_key: str = section["id"]
            section_tasks = tasks_by_section.get(section_id_key, [])

            if not section_tasks:
                continue

            section_name = section_id_to_name[section_id_key]
            file_content = _render_section_file(conn, project_name, section_name, section_tasks, config)

            project_dir.mkdir(parents=True, exist_ok=True)
            section_filename = f"{_safe_directory_name(section_name)}.md"
            section_file_path = project_dir / section_filename
            section_file_path.write_text(file_content, encoding="utf-8")
            result.files_written += 1
            result.tasks_exported += len(section_tasks)

            if verbose:
                print(f"  Wrote {section_file_path} ({len(section_tasks)} tasks)")

        # Write unsectioned tasks (section_id is None)
        unsectioned_tasks = tasks_by_section.get(None, [])
        if unsectioned_tasks:
            unsectioned_content = _render_section_file(conn, project_name, "Unsectioned", unsectioned_tasks, config)
            project_dir.mkdir(parents=True, exist_ok=True)
            unsectioned_path = project_dir / "_unsectioned.md"
            unsectioned_path.write_text(unsectioned_content, encoding="utf-8")
            result.files_written += 1
            result.tasks_exported += len(unsectioned_tasks)

            if verbose:
                print(f"  Wrote {unsectioned_path} ({len(unsectioned_tasks)} unsectioned tasks)")

        result.projects_exported += 1

    if verbose:
        print(
            f"Export complete: {result.projects_exported} project(s), "
            f"{result.files_written} file(s), "
            f"{result.tasks_exported} task(s)."
        )

    return result
