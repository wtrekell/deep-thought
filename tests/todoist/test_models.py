"""Tests for local dataclasses in deep_thought.todoist.models.

Each from_sdk() method is tested with a mock SDK object. Nested objects
(Due, Deadline, Duration, Attachment) are tested both with None and
with populated values.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from deep_thought.todoist.models import (
    CommentLocal,
    LabelLocal,
    ProjectLocal,
    SectionLocal,
    TaskLocal,
)

# ---------------------------------------------------------------------------
# Helpers — build minimal mock SDK objects
# ---------------------------------------------------------------------------


def _make_sdk_project(
    project_id: str = "proj-1",
    name: str = "Work",
    *,
    is_inbox_project: bool = False,
) -> MagicMock:
    project = MagicMock()
    project.id = project_id
    project.name = name
    project.description = "A project"
    project.color = "blue"
    project.is_archived = False
    project.is_favorite = True
    project.is_inbox_project = is_inbox_project
    project.is_shared = False
    project.is_collapsed = False
    project.order = 3
    project.parent_id = None
    project.folder_id = None
    project.view_style = "list"
    project.url = "https://todoist.com/project/proj-1"
    project.workspace_id = None
    project.can_assign_tasks = True
    project.created_at = "2026-01-01T00:00:00"
    project.updated_at = "2026-02-01T00:00:00"
    return project


def _make_sdk_section() -> MagicMock:
    section = MagicMock()
    section.id = "sec-1"
    section.name = "Backlog"
    section.project_id = "proj-1"
    section.order = 2
    section.is_collapsed = False
    return section


def _make_sdk_task(*, has_due: bool = False, has_deadline: bool = False, has_duration: bool = False) -> MagicMock:
    task = MagicMock()
    task.id = "task-1"
    task.content = "Write tests"
    task.description = "Important work"
    task.project_id = "proj-1"
    task.section_id = "sec-1"
    task.parent_id = None
    task.order = 1
    task.priority = 2
    task.assignee_id = None
    task.assigner_id = None
    task.creator_id = "user-1"
    task.is_completed = False
    task.completed_at = None
    task.labels = ["urgent"]
    task.url = "https://todoist.com/task/task-1"
    task.created_at = "2026-01-01T00:00:00"
    task.updated_at = "2026-03-10T00:00:00"

    if has_due:
        due = MagicMock()
        due.date = "2026-03-15"
        due.string = "Mar 15"
        due.is_recurring = True
        due.lang = "en"
        due.timezone = "America/New_York"
        task.due = due
    else:
        task.due = None

    if has_deadline:
        deadline = MagicMock()
        deadline.date = "2026-04-01"
        deadline.lang = "en"
        task.deadline = deadline
    else:
        task.deadline = None

    if has_duration:
        duration = MagicMock()
        duration.amount = 30
        duration.unit = "minute"
        task.duration = duration
    else:
        task.duration = None

    return task


def _make_sdk_label() -> MagicMock:
    label = MagicMock()
    label.id = "label-1"
    label.name = "urgent"
    label.color = "red"
    label.order = 1
    label.is_favorite = False
    return label


def _make_sdk_comment(*, has_attachment: bool = False) -> MagicMock:
    comment = MagicMock()
    comment.id = "comment-1"
    comment.task_id = "task-1"
    comment.project_id = None
    comment.content = "Looks good!"
    comment.posted_at = "2026-03-10T09:00:00"
    comment.poster_id = "user-1"

    if has_attachment:
        attachment = MagicMock()
        attachment.resource_type = "file"
        attachment.file_name = "notes.pdf"
        attachment.file_size = 1024
        attachment.file_type = "application/pdf"
        attachment.file_url = "https://example.com/notes.pdf"
        attachment.file_duration = None
        attachment.upload_state = "completed"
        attachment.image = None
        attachment.image_width = None
        attachment.image_height = None
        attachment.url = "https://example.com/notes.pdf"
        attachment.title = "Meeting notes"
        comment.attachment = attachment
    else:
        comment.attachment = None

    return comment


# ---------------------------------------------------------------------------
# ProjectLocal.from_sdk()
# ---------------------------------------------------------------------------


class TestProjectLocalFromSdk:
    def test_all_fields_mapped_correctly(self) -> None:
        sdk_project = _make_sdk_project()
        local_project = ProjectLocal.from_sdk(sdk_project)

        assert local_project.id == "proj-1"
        assert local_project.name == "Work"
        assert local_project.description == "A project"
        assert local_project.color == "blue"
        assert local_project.is_archived is False
        assert local_project.is_favorite is True
        assert local_project.order_index == 3
        assert local_project.view_style == "list"
        assert local_project.url == "https://todoist.com/project/proj-1"
        assert local_project.can_assign_tasks is True
        assert local_project.created_at == "2026-01-01T00:00:00"
        assert local_project.updated_at == "2026-02-01T00:00:00"

    def test_is_inbox_project_none_defaults_to_false(self) -> None:
        """is_inbox_project=None from SDK must default to False."""
        sdk_project = _make_sdk_project()
        sdk_project.is_inbox_project = None
        local_project = ProjectLocal.from_sdk(sdk_project)
        assert local_project.is_inbox_project is False

    def test_to_dict_returns_all_keys(self) -> None:
        sdk_project = _make_sdk_project()
        result = ProjectLocal.from_sdk(sdk_project).to_dict()
        expected_keys = {
            "id",
            "name",
            "description",
            "color",
            "is_archived",
            "is_favorite",
            "is_inbox_project",
            "is_shared",
            "is_collapsed",
            "order_index",
            "parent_id",
            "folder_id",
            "view_style",
            "url",
            "workspace_id",
            "can_assign_tasks",
            "created_at",
            "updated_at",
        }
        assert expected_keys.issubset(result.keys())


# ---------------------------------------------------------------------------
# SectionLocal.from_sdk()
# ---------------------------------------------------------------------------


class TestSectionLocalFromSdk:
    def test_all_fields_mapped_correctly(self) -> None:
        sdk_section = _make_sdk_section()
        local_section = SectionLocal.from_sdk(sdk_section)

        assert local_section.id == "sec-1"
        assert local_section.name == "Backlog"
        assert local_section.project_id == "proj-1"
        assert local_section.order_index == 2
        assert local_section.is_collapsed is False

    def test_to_dict_returns_all_keys(self) -> None:
        result = SectionLocal.from_sdk(_make_sdk_section()).to_dict()
        assert {"id", "name", "project_id", "order_index", "is_collapsed"}.issubset(result.keys())


# ---------------------------------------------------------------------------
# TaskLocal.from_sdk()
# ---------------------------------------------------------------------------


class TestTaskLocalFromSdk:
    def test_basic_fields_mapped_correctly(self) -> None:
        sdk_task = _make_sdk_task()
        local_task = TaskLocal.from_sdk(sdk_task)

        assert local_task.id == "task-1"
        assert local_task.content == "Write tests"
        assert local_task.project_id == "proj-1"
        assert local_task.priority == 2
        assert local_task.labels == ["urgent"]
        assert local_task.is_completed is False

    def test_due_is_none_when_sdk_due_is_none(self) -> None:
        sdk_task = _make_sdk_task(has_due=False)
        local_task = TaskLocal.from_sdk(sdk_task)

        assert local_task.due_date is None
        assert local_task.due_string is None
        assert local_task.due_is_recurring is None
        assert local_task.due_lang is None
        assert local_task.due_timezone is None

    def test_due_fields_populated_when_sdk_due_set(self) -> None:
        sdk_task = _make_sdk_task(has_due=True)
        local_task = TaskLocal.from_sdk(sdk_task)

        assert local_task.due_date == "2026-03-15"
        assert local_task.due_string == "Mar 15"
        assert local_task.due_is_recurring is True
        assert local_task.due_lang == "en"
        assert local_task.due_timezone == "America/New_York"

    def test_deadline_is_none_when_sdk_deadline_is_none(self) -> None:
        sdk_task = _make_sdk_task(has_deadline=False)
        local_task = TaskLocal.from_sdk(sdk_task)

        assert local_task.deadline_date is None
        assert local_task.deadline_lang is None

    def test_deadline_fields_populated_when_sdk_deadline_set(self) -> None:
        sdk_task = _make_sdk_task(has_deadline=True)
        local_task = TaskLocal.from_sdk(sdk_task)

        assert local_task.deadline_date == "2026-04-01"
        assert local_task.deadline_lang == "en"

    def test_duration_is_none_when_sdk_duration_is_none(self) -> None:
        sdk_task = _make_sdk_task(has_duration=False)
        local_task = TaskLocal.from_sdk(sdk_task)

        assert local_task.duration_amount is None
        assert local_task.duration_unit is None

    def test_duration_fields_populated_when_sdk_duration_set(self) -> None:
        sdk_task = _make_sdk_task(has_duration=True)
        local_task = TaskLocal.from_sdk(sdk_task)

        assert local_task.duration_amount == 30
        assert local_task.duration_unit == "minute"

    def test_empty_labels_defaults_to_empty_list(self) -> None:
        sdk_task = _make_sdk_task()
        sdk_task.labels = None
        local_task = TaskLocal.from_sdk(sdk_task)
        assert local_task.labels == []

    def test_to_dict_returns_all_keys(self) -> None:
        result = TaskLocal.from_sdk(_make_sdk_task()).to_dict()
        expected_keys = {
            "id",
            "content",
            "description",
            "project_id",
            "section_id",
            "parent_id",
            "order_index",
            "priority",
            "due_date",
            "due_string",
            "due_is_recurring",
            "due_lang",
            "due_timezone",
            "deadline_date",
            "deadline_lang",
            "duration_amount",
            "duration_unit",
            "assignee_id",
            "assigner_id",
            "creator_id",
            "is_completed",
            "completed_at",
            "labels",
            "url",
            "created_at",
            "updated_at",
        }
        assert expected_keys.issubset(result.keys())


# ---------------------------------------------------------------------------
# LabelLocal.from_sdk()
# ---------------------------------------------------------------------------


class TestLabelLocalFromSdk:
    def test_all_fields_mapped_correctly(self) -> None:
        sdk_label = _make_sdk_label()
        local_label = LabelLocal.from_sdk(sdk_label)

        assert local_label.id == "label-1"
        assert local_label.name == "urgent"
        assert local_label.color == "red"
        assert local_label.order_index == 1
        assert local_label.is_favorite is False

    def test_to_dict_returns_all_keys(self) -> None:
        result = LabelLocal.from_sdk(_make_sdk_label()).to_dict()
        assert {"id", "name", "color", "order_index", "is_favorite"}.issubset(result.keys())


# ---------------------------------------------------------------------------
# CommentLocal.from_sdk()
# ---------------------------------------------------------------------------


class TestCommentLocalFromSdk:
    def test_all_fields_mapped_correctly_without_attachment(self) -> None:
        sdk_comment = _make_sdk_comment(has_attachment=False)
        local_comment = CommentLocal.from_sdk(sdk_comment)

        assert local_comment.id == "comment-1"
        assert local_comment.task_id == "task-1"
        assert local_comment.project_id is None
        assert local_comment.content == "Looks good!"
        assert local_comment.posted_at == "2026-03-10T09:00:00"
        assert local_comment.poster_id == "user-1"
        assert local_comment.attachment_json is None

    def test_attachment_serialized_to_json_when_present(self) -> None:
        sdk_comment = _make_sdk_comment(has_attachment=True)
        local_comment = CommentLocal.from_sdk(sdk_comment)

        assert local_comment.attachment_json is not None
        attachment_data = json.loads(local_comment.attachment_json)
        assert attachment_data["file_name"] == "notes.pdf"
        assert attachment_data["resource_type"] == "file"
        assert attachment_data["title"] == "Meeting notes"

    def test_attachment_json_is_none_when_attachment_is_none(self) -> None:
        sdk_comment = _make_sdk_comment(has_attachment=False)
        local_comment = CommentLocal.from_sdk(sdk_comment)
        assert local_comment.attachment_json is None

    def test_to_dict_returns_all_keys(self) -> None:
        result = CommentLocal.from_sdk(_make_sdk_comment()).to_dict()
        assert {"id", "task_id", "project_id", "content", "posted_at", "poster_id", "attachment_json"}.issubset(
            result.keys()
        )
