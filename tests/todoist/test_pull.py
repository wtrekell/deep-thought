"""Tests for the pull module in deep_thought.todoist.pull.

Uses an in-memory SQLite database and a mock TodoistClient so no real API
calls are made. Integration-style: the full pull() function runs against
a real (in-memory) DB to verify data is correctly written.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

if TYPE_CHECKING:
    import sqlite3
    from collections.abc import Generator
    from pathlib import Path

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
from deep_thought.todoist.pull import _filter_api_projects_to_configured, pull

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def memory_conn() -> Generator[sqlite3.Connection, None, None]:
    """Return a fully initialised in-memory SQLite connection."""
    conn = initialize_database(":memory:")
    yield conn
    conn.close()


@pytest.fixture()
def base_config() -> TodoistConfig:
    """Return a minimal TodoistConfig that opts into 'Work' project."""
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


def _mock_project(project_id: str = "proj-1", name: str = "Work") -> MagicMock:
    """Build a minimal mock SDK Project object."""
    project = MagicMock()
    project.id = project_id
    project.name = name
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
    project.url = "https://todoist.com/project/1"
    project.workspace_id = None
    project.can_assign_tasks = True
    project.created_at = "2026-01-01T00:00:00"
    project.updated_at = "2026-01-01T00:00:00"
    return project


def _mock_task(task_id: str = "task-1", content: str = "Test task") -> MagicMock:
    """Build a minimal mock SDK Task object."""
    task = MagicMock()
    task.id = task_id
    task.content = content
    task.description = ""
    task.project_id = "proj-1"
    task.section_id = None
    task.parent_id = None
    task.order = 1
    task.priority = 1
    task.due = None
    task.deadline = None
    task.duration = None
    task.assignee_id = None
    task.assigner_id = None
    task.creator_id = None
    task.is_completed = False
    task.completed_at = None
    task.labels = []
    task.url = "https://todoist.com/task/1"
    task.created_at = "2026-01-01T00:00:00"
    task.updated_at = "2026-01-01T00:00:00"
    return task


def _mock_label(label_id: str = "label-1", name: str = "urgent") -> MagicMock:
    """Build a minimal mock SDK Label object."""
    label = MagicMock()
    label.id = label_id
    label.name = name
    label.color = "red"
    label.order = 1
    label.is_favorite = False
    return label


def _build_mock_client(
    projects: list[MagicMock] | None = None,
    sections: list[MagicMock] | None = None,
    tasks: list[MagicMock] | None = None,
    labels: list[MagicMock] | None = None,
    comments: list[MagicMock] | None = None,
) -> MagicMock:
    """Build a mock TodoistClient that returns the provided data."""
    client = MagicMock()
    client.get_projects.return_value = projects or []
    client.get_sections.return_value = sections or []
    client.get_tasks.return_value = tasks or []
    client.get_labels.return_value = labels or []
    client.get_comments.return_value = comments or []
    return client


# ---------------------------------------------------------------------------
# _filter_api_projects_to_configured
# ---------------------------------------------------------------------------


class TestFilterApiProjectsToConfigured:
    def test_filters_to_configured_names(self) -> None:
        work = _mock_project("p1", "Work")
        personal = _mock_project("p2", "Personal")
        result = _filter_api_projects_to_configured([work, personal], ["Work"], None)
        assert len(result) == 1
        assert result[0].name == "Work"

    def test_project_filter_further_restricts(self) -> None:
        work = _mock_project("p1", "Work")
        personal = _mock_project("p2", "Personal")
        result = _filter_api_projects_to_configured([work, personal], ["Work", "Personal"], "Work")
        assert len(result) == 1
        assert result[0].name == "Work"

    def test_project_filter_not_in_config_returns_empty(self) -> None:
        """project_filter for an un-configured project should return nothing."""
        work = _mock_project("p1", "Work")
        result = _filter_api_projects_to_configured([work], ["Work"], "Personal")
        assert result == []

    def test_empty_api_projects_returns_empty(self) -> None:
        result = _filter_api_projects_to_configured([], ["Work"], None)
        assert result == []

    def test_empty_configured_names_returns_all_api_projects(self) -> None:
        """Empty configured list means no opt-in restriction — all API projects are used."""
        work = _mock_project("p1", "Work")
        personal = _mock_project("p2", "Personal")
        result = _filter_api_projects_to_configured([work, personal], [], None)
        assert len(result) == 2

    def test_empty_configured_names_with_project_filter_returns_match(self) -> None:
        """project_filter still restricts when configured list is empty."""
        work = _mock_project("p1", "Work")
        personal = _mock_project("p2", "Personal")
        result = _filter_api_projects_to_configured([work, personal], [], "Work")
        assert len(result) == 1
        assert result[0].name == "Work"

    def test_empty_configured_names_with_nonexistent_project_filter_returns_empty(self) -> None:
        """project_filter for a name absent from API projects returns nothing, even with empty configured list."""
        work = _mock_project("p1", "Work")
        result = _filter_api_projects_to_configured([work], [], "Personal")
        assert result == []


# ---------------------------------------------------------------------------
# pull() function
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestPull:
    def test_pull_writes_project_to_db(
        self, tmp_path: Path, memory_conn: sqlite3.Connection, base_config: TodoistConfig
    ) -> None:
        mock_project = _mock_project()
        mock_client = _build_mock_client(projects=[mock_project])

        with patch("deep_thought.todoist.pull._snapshots_dir") as mock_snap_dir:
            mock_snap_dir.return_value = tmp_path
            result = pull(mock_client, base_config, memory_conn)

        assert result.projects_synced == 1
        row = memory_conn.execute("SELECT * FROM projects WHERE id = 'proj-1';").fetchone()
        assert row is not None
        assert row["name"] == "Work"

    def test_pull_writes_labels_to_db(
        self, tmp_path: Path, memory_conn: sqlite3.Connection, base_config: TodoistConfig
    ) -> None:
        mock_project = _mock_project()
        mock_label = _mock_label("label-1", "urgent")
        mock_client = _build_mock_client(projects=[mock_project], labels=[mock_label])

        with patch("deep_thought.todoist.pull._snapshots_dir") as mock_snap_dir:
            mock_snap_dir.return_value = tmp_path
            result = pull(mock_client, base_config, memory_conn)

        assert result.labels_synced == 1
        row = memory_conn.execute("SELECT * FROM labels WHERE id = 'label-1';").fetchone()
        assert row is not None
        assert row["name"] == "urgent"

    def test_pull_writes_task_to_db(
        self, tmp_path: Path, memory_conn: sqlite3.Connection, base_config: TodoistConfig
    ) -> None:
        mock_project = _mock_project()
        mock_task = _mock_task("task-1", "Write tests")
        mock_client = _build_mock_client(projects=[mock_project], tasks=[mock_task])

        with patch("deep_thought.todoist.pull._snapshots_dir") as mock_snap_dir:
            mock_snap_dir.return_value = tmp_path
            result = pull(mock_client, base_config, memory_conn)

        assert result.tasks_synced == 1
        row = memory_conn.execute("SELECT * FROM tasks WHERE id = 'task-1';").fetchone()
        assert row is not None
        assert row["content"] == "Write tests"
        # Labels should be stored as JSON string
        assert json.loads(row["labels"]) == []

    def test_pull_dry_run_does_not_write_to_db(
        self, memory_conn: sqlite3.Connection, base_config: TodoistConfig
    ) -> None:
        mock_project = _mock_project()
        mock_task = _mock_task()
        mock_client = _build_mock_client(projects=[mock_project], tasks=[mock_task])

        result = pull(mock_client, base_config, memory_conn, dry_run=True)

        assert result.tasks_synced == 1
        # Nothing written in dry_run mode
        row = memory_conn.execute("SELECT * FROM projects WHERE id = 'proj-1';").fetchone()
        assert row is None

    def test_pull_dry_run_has_no_snapshot_path(
        self, memory_conn: sqlite3.Connection, base_config: TodoistConfig
    ) -> None:
        mock_client = _build_mock_client(projects=[_mock_project()])
        result = pull(mock_client, base_config, memory_conn, dry_run=True)
        assert result.snapshot_path is None

    def test_pull_unconfigured_project_is_skipped(
        self, memory_conn: sqlite3.Connection, base_config: TodoistConfig
    ) -> None:
        personal_project = _mock_project("p2", "Personal")  # Not in config.projects
        mock_client = _build_mock_client(projects=[personal_project])

        result = pull(mock_client, base_config, memory_conn, dry_run=True)
        assert result.projects_synced == 0

    def test_pull_filter_excludes_matching_tasks(
        self, memory_conn: sqlite3.Connection, base_config: TodoistConfig
    ) -> None:
        from deep_thought.todoist.config import FilterConfig, PullFilters

        config_with_label_filter = TodoistConfig(
            api_token_env=base_config.api_token_env,
            projects=base_config.projects,
            pull_filters=PullFilters(
                labels=FilterConfig(include=["urgent"], exclude=[]),
                projects=FilterConfig(include=[], exclude=[]),
                sections=FilterConfig(include=[], exclude=[]),
                assignee=FilterConfig(include=[], exclude=[]),
                has_due_date=None,
            ),
            push_filters=base_config.push_filters,
            comments=base_config.comments,
            claude=base_config.claude,
        )
        mock_project = _mock_project()
        task_no_label = _mock_task("t1", "No label task")
        task_no_label.labels = []
        task_with_label = _mock_task("t2", "Urgent task")
        task_with_label.labels = ["urgent"]

        mock_label = _mock_label("label-urgent", "urgent")
        mock_client = _build_mock_client(
            projects=[mock_project], tasks=[task_no_label, task_with_label], labels=[mock_label]
        )

        result = pull(mock_client, config_with_label_filter, memory_conn, dry_run=True)
        assert result.tasks_synced == 1
        assert result.tasks_filtered_out == 1
