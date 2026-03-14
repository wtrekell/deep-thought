"""Shared pytest fixtures for the Todoist Tool test suite.

All database fixtures use in-memory SQLite so no disk I/O occurs.
API client fixtures use MagicMock so no real network calls are made.
"""

from __future__ import annotations

import json
from pathlib import Path
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

# Path to the fixtures directory, used by tests that load files from disk
FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Database fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def in_memory_db() -> Generator[sqlite3.Connection, None, None]:
    """Return a fully initialized in-memory SQLite connection.

    The connection has WAL mode enabled, foreign keys enforced, and all
    migrations applied. Closes automatically after each test.
    """
    connection = initialize_database(":memory:")
    yield connection
    connection.close()


@pytest.fixture()
def populated_db(in_memory_db: sqlite3.Connection) -> Generator[sqlite3.Connection, None, None]:
    """An in-memory DB with one project, section, task, label, and comment seeded.

    Use this fixture in tests that need existing data without caring about
    the exact insertion mechanics.
    """
    in_memory_db.execute(
        """
        INSERT INTO projects (
            id, name, description, color, is_archived, is_favorite,
            is_inbox_project, is_shared, is_collapsed, order_index,
            parent_id, folder_id, view_style, url, workspace_id,
            can_assign_tasks, created_at, updated_at, synced_at
        ) VALUES (
            'proj-1', 'Work', '', 'blue', 0, 0, 0, 0, 0, 1,
            NULL, NULL, 'list', 'https://todoist.com/p/1', NULL,
            1, '2026-01-01T00:00:00', '2026-01-01T00:00:00', '2026-01-01T00:00:00'
        );
        """
    )
    in_memory_db.execute(
        """
        INSERT INTO sections (id, name, project_id, order_index, is_collapsed, synced_at)
        VALUES ('sec-1', 'Backlog', 'proj-1', 1, 0, '2026-01-01T00:00:00');
        """
    )
    in_memory_db.execute(
        """
        INSERT INTO labels (id, name, color, order_index, is_favorite, synced_at)
        VALUES ('label-1', 'urgent', 'red', 1, 0, '2026-01-01T00:00:00');
        """
    )
    in_memory_db.execute(
        """
        INSERT INTO tasks (
            id, content, description, project_id, section_id, parent_id,
            order_index, priority, due_date, due_string, due_is_recurring, due_lang, due_timezone,
            deadline_date, deadline_lang, duration_amount, duration_unit,
            assignee_id, assigner_id, creator_id, is_completed, completed_at,
            labels, url, created_at, updated_at, synced_at
        ) VALUES (
            'task-1', 'Write tests', 'A description', 'proj-1', 'sec-1', NULL,
            1, 2, '2026-03-15', NULL, 0, NULL, NULL,
            NULL, NULL, NULL, NULL,
            NULL, NULL, 'user-1', 0, NULL,
            ?, 'https://todoist.com/t/1',
            '2026-01-01T00:00:00', '2026-01-01T00:00:00', '2026-01-01T00:00:00'
        );
        """,
        (json.dumps(["urgent"]),),
    )
    in_memory_db.execute(
        """
        INSERT INTO task_labels (task_id, label_id, synced_at)
        VALUES ('task-1', 'label-1', '2026-01-01T00:00:00');
        """
    )
    in_memory_db.execute(
        """
        INSERT INTO comments (
            id, task_id, project_id, content, posted_at, poster_id, attachment_json, synced_at
        ) VALUES (
            'comment-1', 'task-1', NULL, 'Looks good!',
            '2026-03-10T09:00:00', 'user-1', NULL, '2026-01-01T00:00:00'
        );
        """
    )
    in_memory_db.commit()
    yield in_memory_db


# ---------------------------------------------------------------------------
# Config fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def sample_config() -> TodoistConfig:
    """Return a TodoistConfig with realistic test values."""
    return TodoistConfig(
        api_token_env="TEST_TODOIST_API_TOKEN",
        projects=["Work", "Personal"],
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
            conflict_resolution="remote_wins",
            require_confirmation=False,
        ),
        comments=CommentConfig(sync=True, include_attachments=False),
        claude=ClaudeConfig(label="claude-code", repo="deep-thought", branch="main"),
    )


# ---------------------------------------------------------------------------
# Mock client fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_client() -> MagicMock:
    """Return a mock TodoistClient with all methods returning empty lists."""
    client = MagicMock()
    client.get_projects.return_value = []
    client.get_sections.return_value = []
    client.get_tasks.return_value = []
    client.get_labels.return_value = []
    client.get_comments.return_value = []
    return client


# ---------------------------------------------------------------------------
# SDK mock object factories
# ---------------------------------------------------------------------------


@pytest.fixture()
def sample_project_sdk() -> MagicMock:
    """Return a mock Todoist SDK Project object with realistic values."""
    project = MagicMock()
    project.id = "proj-1"
    project.name = "Work"
    project.description = ""
    project.color = "blue"
    project.is_archived = False
    project.is_favorite = False
    project.is_inbox_project = False
    project.is_shared = False
    project.is_collapsed = False
    project.order = 1
    project.parent_id = None
    project.folder_id = None
    project.view_style = "list"
    project.url = "https://todoist.com/project/proj-1"
    project.workspace_id = None
    project.can_assign_tasks = True
    project.created_at = "2026-01-01T00:00:00"
    project.updated_at = "2026-01-01T00:00:00"
    return project


@pytest.fixture()
def sample_section_sdk() -> MagicMock:
    """Return a mock Todoist SDK Section object."""
    section = MagicMock()
    section.id = "sec-1"
    section.name = "Backlog"
    section.project_id = "proj-1"
    section.order = 1
    section.is_collapsed = False
    return section


@pytest.fixture()
def sample_task_sdk() -> MagicMock:
    """Return a mock Todoist SDK Task object with no nested objects set."""
    task = MagicMock()
    task.id = "task-1"
    task.content = "Write tests"
    task.description = "A test task"
    task.project_id = "proj-1"
    task.section_id = "sec-1"
    task.parent_id = None
    task.order = 1
    task.priority = 2
    task.due = None
    task.deadline = None
    task.duration = None
    task.assignee_id = None
    task.assigner_id = None
    task.creator_id = "user-1"
    task.is_completed = False
    task.completed_at = None
    task.labels = ["urgent"]
    task.url = "https://todoist.com/task/task-1"
    task.created_at = "2026-01-01T00:00:00"
    task.updated_at = "2026-03-10T00:00:00"
    return task


@pytest.fixture()
def sample_label_sdk() -> MagicMock:
    """Return a mock Todoist SDK Label object."""
    label = MagicMock()
    label.id = "label-1"
    label.name = "urgent"
    label.color = "red"
    label.order = 1
    label.is_favorite = False
    return label


@pytest.fixture()
def sample_comment_sdk() -> MagicMock:
    """Return a mock Todoist SDK Comment object with no attachment."""
    comment = MagicMock()
    comment.id = "comment-1"
    comment.task_id = "task-1"
    comment.project_id = None
    comment.content = "Looks good!"
    comment.posted_at = "2026-03-10T09:00:00"
    comment.poster_id = "user-1"
    comment.attachment = None
    return comment


# ---------------------------------------------------------------------------
# Shared data-insertion helpers (not fixtures — used as plain functions in tests)
# ---------------------------------------------------------------------------


def insert_project(
    conn: sqlite3.Connection,
    project_id: str = "proj-1",
    name: str = "Work",
) -> None:
    """Insert a minimal project row for use in test setup."""
    conn.execute(
        """
        INSERT OR IGNORE INTO projects (
            id, name, description, color, is_archived, is_favorite,
            is_inbox_project, is_shared, is_collapsed, order_index,
            parent_id, folder_id, view_style, url, workspace_id,
            can_assign_tasks, created_at, updated_at, synced_at
        ) VALUES (
            ?, ?, '', 'blue', 0, 0, 0, 0, 0, 1,
            NULL, NULL, 'list', 'https://todoist.com/p/1', NULL,
            1, '2026-01-01T00:00:00', '2026-01-01T00:00:00', '2026-01-01T00:00:00'
        );
        """,
        (project_id, name),
    )
    conn.commit()


def insert_task(
    conn: sqlite3.Connection,
    task_id: str = "task-1",
    project_id: str = "proj-1",
    content: str = "Test task",
    *,
    section_id: str | None = None,
    parent_id: str | None = None,
    labels: list[str] | None = None,
    updated_at: str = "2026-01-01T00:00:00",
    synced_at: str = "2026-01-01T00:00:00",
    priority: int = 1,
    due_date: str | None = None,
) -> None:
    """Insert a task row with controllable updated_at and synced_at for modification tests."""
    conn.execute(
        """
        INSERT OR REPLACE INTO tasks (
            id, content, description, project_id, section_id, parent_id,
            order_index, priority, due_date, due_string, due_is_recurring, due_lang, due_timezone,
            deadline_date, deadline_lang, duration_amount, duration_unit,
            assignee_id, assigner_id, creator_id, is_completed, completed_at,
            labels, url, created_at, updated_at, synced_at
        ) VALUES (
            ?, ?, '', ?, ?, ?,
            1, ?, ?, NULL, 0, NULL, NULL,
            NULL, NULL, NULL, NULL,
            NULL, NULL, NULL, 0, NULL,
            ?, 'https://todoist.com/t/1',
            '2026-01-01T00:00:00', ?, ?
        );
        """,
        (
            task_id,
            content,
            project_id,
            section_id,
            parent_id,
            priority,
            due_date,
            json.dumps(labels or []),
            updated_at,
            synced_at,
        ),
    )
    conn.commit()
