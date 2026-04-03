"""Local dataclasses mirroring Todoist SDK models.

Each model provides:
- A ``from_sdk()`` classmethod to convert an SDK object into the local representation.
- A ``to_dict()`` method that returns a flat dict keyed by DB column names.

Nested SDK objects (Due, Deadline, Duration, Attachment) are unpacked into scalar fields
so the local models remain flat and easy to store in SQLite.

Note on date/time fields
------------------------
The Todoist SDK uses ``dataclass_wizard`` pattern types (``ApiDate``, ``ApiDue``) for its
timestamp and date fields. These patterns describe *how* JSON values are deserialized; at
runtime the fields hold plain Python ``str`` values (ISO-8601 strings). Because mypy
resolves the pattern types from the SDK's annotations rather than the runtime values, we
call ``str()`` explicitly when extracting these fields so that our ``str`` annotations
remain correct from both a mypy and a runtime perspective.

Note on ``synced_at``
---------------------
All five DB tables (projects, sections, tasks, labels, comments) include a ``synced_at``
column that records when the row was last written by a sync operation. This field is
intentionally absent from every model class defined here — it is injected at write time
by ``db/queries.py`` using the current UTC timestamp. Keeping ``synced_at`` out of these
models avoids polluting the domain representation with a purely persistence-layer concern:
the Todoist API never returns a ``synced_at`` value, and no business logic in this package
should depend on it.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from todoist_api_python.models import Comment, Label, Project, Section, Task


def _to_str(value: Any) -> str:
    """Convert an SDK date/datetime pattern value to a plain string.

    The SDK uses ``dataclass_wizard`` pattern descriptors for date fields; at runtime
    these hold ISO-8601 strings. We call ``str()`` to produce a guaranteed ``str``
    and satisfy mypy's type checker.
    """
    return str(value)


def _to_optional_str(value: Any) -> str | None:
    """Convert an optional SDK date/datetime pattern value to ``str | None``."""
    if value is None:
        return None
    return str(value)


# ---------------------------------------------------------------------------
# ProjectLocal
# ---------------------------------------------------------------------------


@dataclass
class ProjectLocal:
    id: str
    name: str
    description: str
    color: str
    is_archived: bool
    is_favorite: bool
    is_inbox_project: bool
    is_shared: bool
    is_collapsed: bool
    order_index: int
    parent_id: str | None
    folder_id: str | None
    view_style: str
    url: str
    workspace_id: str | None
    can_assign_tasks: bool
    created_at: str
    updated_at: str

    @classmethod
    def from_sdk(cls, project: Project) -> ProjectLocal:
        """Convert a Todoist SDK Project object into a ProjectLocal."""
        return cls(
            id=project.id,
            name=project.name,
            description=project.description,
            color=project.color,
            is_archived=project.is_archived,
            is_favorite=project.is_favorite,
            is_inbox_project=project.is_inbox_project or False,
            is_shared=project.is_shared,
            is_collapsed=project.is_collapsed,
            order_index=project.order,
            parent_id=project.parent_id,
            folder_id=project.folder_id,
            view_style=project.view_style,
            url=project.url,
            workspace_id=project.workspace_id,
            can_assign_tasks=project.can_assign_tasks,
            created_at=_to_str(project.created_at),
            updated_at=_to_str(project.updated_at),
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a flat dict keyed by DB column names."""
        return asdict(self)


# ---------------------------------------------------------------------------
# SectionLocal
# ---------------------------------------------------------------------------


@dataclass
class SectionLocal:
    id: str
    name: str
    project_id: str
    order_index: int
    is_collapsed: bool

    @classmethod
    def from_sdk(cls, section: Section) -> SectionLocal:
        """Convert a Todoist SDK Section object into a SectionLocal."""
        return cls(
            id=section.id,
            name=section.name,
            project_id=section.project_id,
            order_index=section.order,
            is_collapsed=section.is_collapsed,
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a flat dict keyed by DB column names."""
        return asdict(self)


# ---------------------------------------------------------------------------
# TaskLocal
# ---------------------------------------------------------------------------


@dataclass
class TaskLocal:
    id: str
    content: str
    description: str
    project_id: str
    section_id: str | None
    parent_id: str | None
    order_index: int
    priority: int
    due_date: str | None
    due_string: str | None
    due_is_recurring: bool | None
    due_lang: str | None
    due_timezone: str | None
    deadline_date: str | None
    deadline_lang: str | None
    duration_amount: int | None
    duration_unit: str | None
    assignee_id: str | None
    assigner_id: str | None
    creator_id: str | None
    is_completed: bool
    completed_at: str | None
    labels: list[str]
    url: str
    created_at: str
    updated_at: str

    @classmethod
    def from_sdk(cls, task: Task) -> TaskLocal:
        """Convert a Todoist SDK Task object into a TaskLocal.

        Nested objects (Due, Deadline, Duration) are unpacked into scalar fields.
        """
        # Unpack Due fields
        due_date: str | None = None
        due_string: str | None = None
        due_is_recurring: bool = False
        due_lang: str | None = None
        due_timezone: str | None = None
        if task.due is not None:
            due_date = _to_optional_str(task.due.date)
            due_string = task.due.string
            due_is_recurring = task.due.is_recurring
            due_lang = task.due.lang
            due_timezone = task.due.timezone

        # Unpack Deadline fields
        deadline_date: str | None = None
        deadline_lang: str | None = None
        if task.deadline is not None:
            deadline_date = _to_optional_str(task.deadline.date)
            deadline_lang = task.deadline.lang

        # Unpack Duration fields
        duration_amount: int | None = None
        duration_unit: str | None = None
        if task.duration is not None:
            duration_amount = task.duration.amount
            duration_unit = task.duration.unit

        return cls(
            id=task.id,
            content=task.content,
            description=task.description,
            project_id=task.project_id,
            section_id=task.section_id,
            parent_id=task.parent_id,
            order_index=task.order,
            priority=task.priority,
            due_date=due_date,
            due_string=due_string,
            due_is_recurring=due_is_recurring,
            due_lang=due_lang,
            due_timezone=due_timezone,
            deadline_date=deadline_date,
            deadline_lang=deadline_lang,
            duration_amount=duration_amount,
            duration_unit=duration_unit,
            assignee_id=task.assignee_id,
            assigner_id=task.assigner_id,
            creator_id=task.creator_id,
            is_completed=task.is_completed,
            completed_at=_to_optional_str(task.completed_at),
            labels=task.labels or [],
            url=task.url,
            created_at=_to_str(task.created_at),
            updated_at=_to_str(task.updated_at),
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a flat dict keyed by DB column names."""
        return asdict(self)


# ---------------------------------------------------------------------------
# LabelLocal
# ---------------------------------------------------------------------------


@dataclass
class LabelLocal:
    id: str
    name: str
    color: str
    order_index: int
    is_favorite: bool

    @classmethod
    def from_sdk(cls, label: Label) -> LabelLocal:
        """Convert a Todoist SDK Label object into a LabelLocal."""
        return cls(
            id=label.id,
            name=label.name,
            color=label.color,
            order_index=label.order,
            is_favorite=label.is_favorite,
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a flat dict keyed by DB column names."""
        return asdict(self)


# ---------------------------------------------------------------------------
# CommentLocal
# ---------------------------------------------------------------------------


@dataclass
class CommentLocal:
    id: str
    task_id: str | None
    project_id: str | None
    content: str
    posted_at: str
    poster_id: str
    attachment_json: str | None  # JSON-serialised attachment data, or None

    @classmethod
    def from_sdk(cls, comment: Comment) -> CommentLocal:
        """Convert a Todoist SDK Comment object into a CommentLocal.

        The Attachment object (if present) is serialised to a JSON string so it
        can be stored as a single column value in SQLite.
        """
        attachment_json: str | None = None
        if comment.attachment is not None:
            attachment_data: dict[str, Any] = {
                "resource_type": comment.attachment.resource_type,
                "file_name": comment.attachment.file_name,
                "file_size": comment.attachment.file_size,
                "file_type": comment.attachment.file_type,
                "file_url": comment.attachment.file_url,
                "file_duration": comment.attachment.file_duration,
                "upload_state": comment.attachment.upload_state,
                "image": comment.attachment.image,
                "image_width": comment.attachment.image_width,
                "image_height": comment.attachment.image_height,
                "url": comment.attachment.url,
                "title": comment.attachment.title,
            }
            attachment_json = json.dumps(attachment_data)

        return cls(
            id=comment.id,
            task_id=comment.task_id,
            project_id=comment.project_id,
            content=comment.content,
            posted_at=_to_str(comment.posted_at),
            poster_id=comment.poster_id,
            attachment_json=attachment_json,
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a flat dict keyed by DB column names."""
        return asdict(self)
