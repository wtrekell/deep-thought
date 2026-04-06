"""Thin wrapper around the Todoist SDK's TodoistAPI.

Each method handles SDK pagination (Iterator[list[T]]) transparently, returning
flat lists to callers so they never need to worry about paging logic.

Write operations (update, create, close, reopen, comment mutations) are direct
pass-throughs with typed signatures.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx
from todoist_api_python.api import TodoistAPI
from todoist_api_python.models import Attachment

if TYPE_CHECKING:
    from pathlib import Path

    from todoist_api_python.models import Comment, Label, Project, Section, Task

_TODOIST_SYNC_UPLOAD_URL = "https://api.todoist.com/sync/v9/uploads/add"


class TodoistClient:
    """Wrapper around TodoistAPI that presents a simple, fully-typed interface."""

    def __init__(self, api_token: str) -> None:
        self._api_token = api_token
        self._api = TodoistAPI(api_token)

    # ------------------------------------------------------------------
    # Read operations — paginated iterators are collapsed into flat lists
    # ------------------------------------------------------------------

    def get_projects(self) -> list[Project]:
        """Fetch all active projects, transparently handling API pagination."""
        all_projects: list[Project] = []
        for project_page in self._api.get_projects():
            all_projects.extend(project_page)
        return all_projects

    def get_sections(self, project_id: str | None = None) -> list[Section]:
        """Fetch all sections, optionally filtered to a single project."""
        all_sections: list[Section] = []
        for section_page in self._api.get_sections(project_id=project_id):
            all_sections.extend(section_page)
        return all_sections

    def get_tasks(self, project_id: str | None = None) -> list[Task]:
        """Fetch all active tasks, optionally filtered to a single project."""
        all_tasks: list[Task] = []
        for task_page in self._api.get_tasks(project_id=project_id):
            all_tasks.extend(task_page)
        return all_tasks

    def get_labels(self) -> list[Label]:
        """Fetch all personal labels defined in the account."""
        all_labels: list[Label] = []
        for label_page in self._api.get_labels():
            all_labels.extend(label_page)
        return all_labels

    def get_comments(
        self,
        task_id: str | None = None,
        project_id: str | None = None,
    ) -> list[Comment]:
        """Fetch comments for a task or project, transparently handling pagination.

        Exactly one of task_id or project_id must be provided (Todoist API requirement).
        """
        all_comments: list[Comment] = []
        for comment_page in self._api.get_comments(task_id=task_id, project_id=project_id):
            all_comments.extend(comment_page)
        return all_comments

    # ------------------------------------------------------------------
    # Task write operations
    # ------------------------------------------------------------------

    def update_task(self, task_id: str, **kwargs: Any) -> Task:
        """Update an existing task by ID.

        Keyword arguments are passed directly to the SDK's update_task method.
        Common kwargs: content, description, labels, priority, due_string,
        due_date, assignee_id, duration, duration_unit, deadline_date.
        """
        return self._api.update_task(task_id, **kwargs)

    def create_task(self, content: str, **kwargs: Any) -> Task:
        """Create a new task with the given content.

        Keyword arguments are passed directly to the SDK's add_task method.
        Common kwargs: description, project_id, section_id, parent_id, labels,
        priority, due_string, due_date, assignee_id, duration, duration_unit,
        deadline_date.
        """
        return self._api.add_task(content, **kwargs)

    def close_task(self, task_id: str) -> None:
        """Mark a task as completed."""
        self._api.complete_task(task_id)

    def reopen_task(self, task_id: str) -> None:
        """Reopen a previously completed task."""
        self._api.uncomplete_task(task_id)

    # ------------------------------------------------------------------
    # Comment write operations
    # ------------------------------------------------------------------

    def add_comment(
        self,
        content: str,
        task_id: str | None = None,
        project_id: str | None = None,
    ) -> Comment:
        """Add a comment to a task or project.

        Exactly one of task_id or project_id must be provided.
        """
        return self._api.add_comment(content, task_id=task_id, project_id=project_id)

    def update_comment(self, comment_id: str, content: str) -> Comment:
        """Update the text content of an existing comment."""
        return self._api.update_comment(comment_id, content)

    def delete_comment(self, comment_id: str) -> None:
        """Permanently delete a comment by ID."""
        self._api.delete_comment(comment_id)

    # ------------------------------------------------------------------
    # File upload operations (Sync API v9 — not exposed by the REST SDK)
    # ------------------------------------------------------------------

    def upload_attachment(self, file_path: Path) -> dict[str, Any]:
        """Upload a local file to Todoist and return the attachment object.

        Uses the Todoist Sync API v9 upload endpoint, which is not exposed
        by the REST SDK. The returned dict is ready to pass directly to
        add_comment_with_attachment().

        Args:
            file_path: Path to the local file to upload.

        Returns:
            Attachment dict with keys: file_url, file_name, file_size,
            file_type, resource_type, upload_state.

        Raises:
            FileNotFoundError: If file_path does not exist.
            httpx.HTTPStatusError: If the upload API returns a non-2xx response.
        """
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        with file_path.open("rb") as file_handle:
            response = httpx.post(
                _TODOIST_SYNC_UPLOAD_URL,
                headers={"Authorization": f"Bearer {self._api_token}"},
                files={"file": (file_path.name, file_handle)},
                timeout=120.0,
            )
        response.raise_for_status()
        result: dict[str, Any] = response.json()
        return result

    def add_comment_with_attachment(
        self,
        task_id: str,
        content: str,
        attachment: dict[str, Any],
    ) -> Comment:
        """Add a comment to a task with a file attachment.

        Args:
            task_id: The Todoist task ID to attach the comment to.
            content: Text body of the comment.
            attachment: Attachment dict returned by upload_attachment().

        Returns:
            The created Comment object.
        """
        attachment_obj = Attachment(
            resource_type=attachment.get("resource_type"),
            file_name=attachment.get("file_name"),
            file_size=attachment.get("file_size"),
            file_type=attachment.get("file_type"),
            file_url=attachment.get("file_url"),
            upload_state=attachment.get("upload_state"),
        )
        return self._api.add_comment(content, task_id=task_id, attachment=attachment_obj)
