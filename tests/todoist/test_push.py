"""Tests for the push module in deep_thought.todoist.push.

Uses an in-memory SQLite database and a mock TodoistClient.
"""

from __future__ import annotations

import json
from datetime import date
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

if TYPE_CHECKING:
    import sqlite3
    from collections.abc import Generator

import pytest

from deep_thought.todoist.config import (
    ClaudeConfig,
    CommentConfig,
    FilterConfig,
    PullFilters,
    PushFilters,
    TodoistConfig,
)
from deep_thought.todoist.db.schema import initialize_database
from deep_thought.todoist.models import TaskLocal
from deep_thought.todoist.push import _build_update_kwargs, _task_dict_to_local_model, push

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def memory_conn() -> Generator[sqlite3.Connection, None, None]:
    conn = initialize_database(":memory:")
    yield conn
    conn.close()


@pytest.fixture()
def base_config() -> TodoistConfig:
    return TodoistConfig(
        api_token_env="TODOIST_API_TOKEN",
        projects=["Work"],
        pull_filters=PullFilters(
            labels=FilterConfig(include=[], exclude=[]),
            projects=FilterConfig(include=[], exclude=[]),
            sections=FilterConfig(include=[], exclude=[]),
            assignee=FilterConfig(include=[], exclude=[]),
            has_due_date=None,
        ),
        push_filters=PushFilters(
            labels=FilterConfig(include=[], exclude=[]),
            assignee=FilterConfig(include=[], exclude=[]),
            conflict_resolution="prompt",
            require_confirmation=False,
        ),
        comments=CommentConfig(sync=True, include_attachments=False),
        claude=ClaudeConfig(label="claude-code", repo="deep-thought", branch="main"),
    )


def _insert_modified_task(conn: sqlite3.Connection, task_id: str = "task-1", project_id: str = "proj-1") -> None:
    """Insert a project and task row into the DB. Task appears locally modified (updated_at > synced_at)."""
    # Ensure a parent project exists to satisfy the FK constraint
    conn.execute(
        """
        INSERT OR IGNORE INTO projects (
            id, name, description, color, is_archived, is_favorite,
            is_inbox_project, is_shared, is_collapsed, order_index,
            parent_id, folder_id, view_style, url, workspace_id,
            can_assign_tasks, created_at, updated_at, synced_at
        ) VALUES (?, 'Test Project', '', 'blue', 0, 0, 0, 0, 0, 1,
                  NULL, NULL, 'list', 'https://todoist.com/p/1', NULL,
                  1, '2026-01-01', '2026-01-01', '2026-01-01');
        """,
        (project_id,),
    )
    conn.execute(
        """
        INSERT INTO tasks (
            id, content, description, project_id, section_id, parent_id,
            order_index, priority, due_date, due_string, due_is_recurring, due_lang, due_timezone,
            deadline_date, deadline_lang, duration_amount, duration_unit,
            assignee_id, assigner_id, creator_id, is_completed, completed_at,
            labels, url, created_at, updated_at, synced_at
        ) VALUES (
            ?, 'Modified task', '', ?, NULL, NULL,
            1, 1, NULL, NULL, 0, NULL, NULL,
            NULL, NULL, NULL, NULL,
            NULL, NULL, NULL, 0, NULL,
            ?, 'https://todoist.com/task/1',
            '2026-01-01T00:00:00', '2026-03-01T12:00:00', '2026-01-01T00:00:00'
        );
        """,
        (task_id, project_id, json.dumps([])),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# _task_dict_to_local_model
# ---------------------------------------------------------------------------


class TestTaskDictToLocalModel:
    def test_converts_json_labels_string_to_list(self) -> None:
        task_dict = {
            "id": "t1",
            "content": "Test",
            "description": "",
            "project_id": "p1",
            "section_id": None,
            "parent_id": None,
            "order_index": 0,
            "priority": 1,
            "due_date": None,
            "due_string": None,
            "due_is_recurring": None,
            "due_lang": None,
            "due_timezone": None,
            "deadline_date": None,
            "deadline_lang": None,
            "duration_amount": None,
            "duration_unit": None,
            "assignee_id": None,
            "assigner_id": None,
            "creator_id": None,
            "is_completed": False,
            "completed_at": None,
            "labels": '["urgent", "work"]',
            "url": "https://todoist.com/t/1",
            "created_at": "2026-01-01",
            "updated_at": "2026-01-02",
        }
        task = _task_dict_to_local_model(task_dict)
        assert task.labels == ["urgent", "work"]

    def test_handles_empty_labels_json(self) -> None:
        task_dict = {
            "id": "t1",
            "content": "Test",
            "description": "",
            "project_id": "p1",
            "section_id": None,
            "parent_id": None,
            "order_index": 0,
            "priority": 1,
            "due_date": None,
            "due_string": None,
            "due_is_recurring": None,
            "due_lang": None,
            "due_timezone": None,
            "deadline_date": None,
            "deadline_lang": None,
            "duration_amount": None,
            "duration_unit": None,
            "assignee_id": None,
            "assigner_id": None,
            "creator_id": None,
            "is_completed": False,
            "completed_at": None,
            "labels": "[]",
            "url": "https://todoist.com/t/1",
            "created_at": "2026-01-01",
            "updated_at": "2026-01-02",
        }
        task = _task_dict_to_local_model(task_dict)
        assert task.labels == []


# ---------------------------------------------------------------------------
# _build_update_kwargs
# ---------------------------------------------------------------------------


class TestBuildUpdateKwargs:
    def _make_task(
        self,
        *,
        due_string: str | None = None,
        due_date: str | None = None,
        deadline_date: str | None = None,
        duration_amount: int | None = None,
        duration_unit: str | None = None,
        assignee_id: str | None = None,
    ) -> TaskLocal:
        return TaskLocal(
            id="t1",
            content="Task content",
            description="A description",
            project_id="p1",
            section_id=None,
            parent_id=None,
            order_index=0,
            priority=2,
            due_date=due_date,
            due_string=due_string,
            due_is_recurring=None,
            due_lang=None,
            due_timezone=None,
            deadline_date=deadline_date,
            deadline_lang=None,
            duration_amount=duration_amount,
            duration_unit=duration_unit,
            assignee_id=assignee_id,
            assigner_id=None,
            creator_id=None,
            is_completed=False,
            completed_at=None,
            labels=["work"],
            url="https://todoist.com/t/1",
            created_at="2026-01-01",
            updated_at="2026-01-02",
        )

    def test_always_includes_content_description_priority_labels(self) -> None:
        task = self._make_task()
        kwargs = _build_update_kwargs(task)
        assert "content" in kwargs
        assert "description" in kwargs
        assert "priority" in kwargs
        assert "labels" in kwargs

    def test_due_string_preferred_over_due_date(self) -> None:
        task = self._make_task(due_string="every day", due_date="2026-03-15")
        kwargs = _build_update_kwargs(task)
        assert kwargs.get("due_string") == "every day"
        assert "due_date" not in kwargs

    def test_due_date_used_when_no_due_string(self) -> None:
        task = self._make_task(due_date="2026-03-15", due_string=None)
        kwargs = _build_update_kwargs(task)
        # SDK v3 expects datetime.date objects, not strings
        assert kwargs.get("due_date") == date(2026, 3, 15)
        assert "due_string" not in kwargs

    def test_deadline_date_included_when_present(self) -> None:
        task = self._make_task(deadline_date="2026-04-01")
        kwargs = _build_update_kwargs(task)
        # SDK v3 expects datetime.date objects, not strings
        assert kwargs.get("deadline_date") == date(2026, 4, 1)

    def test_duration_included_when_both_present(self) -> None:
        task = self._make_task(duration_amount=30, duration_unit="minute")
        kwargs = _build_update_kwargs(task)
        assert kwargs.get("duration") == 30
        assert kwargs.get("duration_unit") == "minute"

    def test_duration_omitted_when_amount_missing(self) -> None:
        task = self._make_task(duration_amount=None, duration_unit="minute")
        kwargs = _build_update_kwargs(task)
        assert "duration" not in kwargs


# ---------------------------------------------------------------------------
# push() function
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestPush:
    def test_push_no_modified_tasks_returns_zero_pushed(
        self, memory_conn: sqlite3.Connection, base_config: TodoistConfig
    ) -> None:
        mock_client = MagicMock()
        result = push(mock_client, base_config, memory_conn)
        assert result.tasks_pushed == 0
        assert result.tasks_failed == 0

    def test_push_dry_run_does_not_call_api(self, memory_conn: sqlite3.Connection, base_config: TodoistConfig) -> None:
        _insert_modified_task(memory_conn)
        mock_client = MagicMock()
        result = push(mock_client, base_config, memory_conn, dry_run=True)
        mock_client.update_task.assert_not_called()
        # Count is still incremented in dry_run so caller can see what would happen
        assert result.tasks_pushed == 1

    def test_push_calls_update_task_for_modified_task(
        self, memory_conn: sqlite3.Connection, base_config: TodoistConfig
    ) -> None:
        _insert_modified_task(memory_conn, "task-1")
        mock_client = MagicMock()
        mock_client.update_task.return_value = MagicMock()

        result = push(mock_client, base_config, memory_conn)
        mock_client.update_task.assert_called_once()
        assert result.tasks_pushed == 1
        assert result.tasks_failed == 0

    def test_push_marks_task_synced_after_success(
        self, memory_conn: sqlite3.Connection, base_config: TodoistConfig
    ) -> None:
        _insert_modified_task(memory_conn, "task-1")
        mock_client = MagicMock()
        mock_client.update_task.return_value = MagicMock()

        push(mock_client, base_config, memory_conn)

        # After a successful push, updated_at should no longer exceed synced_at
        row = memory_conn.execute("SELECT updated_at, synced_at FROM tasks WHERE id = 'task-1';").fetchone()
        assert row is not None
        assert row["synced_at"] >= row["updated_at"]

    def test_push_records_error_on_api_failure(
        self, memory_conn: sqlite3.Connection, base_config: TodoistConfig
    ) -> None:
        _insert_modified_task(memory_conn, "task-1")
        mock_client = MagicMock()
        mock_client.update_task.side_effect = RuntimeError("API unavailable")

        result = push(mock_client, base_config, memory_conn)
        assert result.tasks_failed == 1
        assert len(result.errors) == 1
        assert "API unavailable" in result.errors[0]

    def test_push_project_filter_limits_scope(
        self, memory_conn: sqlite3.Connection, base_config: TodoistConfig
    ) -> None:
        # Insert project rows so the filter can look up by name
        memory_conn.execute(
            """
            INSERT INTO projects (
                id, name, description, color, is_archived, is_favorite,
                is_inbox_project, is_shared, is_collapsed, order_index,
                parent_id, folder_id, view_style, url, workspace_id,
                can_assign_tasks, created_at, updated_at, synced_at
            ) VALUES ('proj-1', 'Work', '', 'blue', 0, 0, 0, 0, 0, 1,
                      NULL, NULL, 'list', 'https://todoist.com/p/1', NULL,
                      1, '2026-01-01', '2026-01-01', '2026-01-01');
            """
        )
        memory_conn.execute(
            """
            INSERT INTO projects (
                id, name, description, color, is_archived, is_favorite,
                is_inbox_project, is_shared, is_collapsed, order_index,
                parent_id, folder_id, view_style, url, workspace_id,
                can_assign_tasks, created_at, updated_at, synced_at
            ) VALUES ('proj-2', 'Personal', '', 'red', 0, 0, 0, 0, 0, 2,
                      NULL, NULL, 'list', 'https://todoist.com/p/2', NULL,
                      1, '2026-01-01', '2026-01-01', '2026-01-01');
            """
        )
        memory_conn.commit()

        _insert_modified_task(memory_conn, "task-work", "proj-1")
        _insert_modified_task(memory_conn, "task-personal", "proj-2")
        mock_client = MagicMock()
        mock_client.update_task.return_value = MagicMock()

        result = push(mock_client, base_config, memory_conn, project_filter="Work")
        assert result.tasks_pushed == 1
