"""Tests for the database layer: schema initialization and query functions.

All tests use in-memory SQLite (no disk writes). The in_memory_db fixture
from conftest.py is used throughout.
"""

from __future__ import annotations

from typing import Any

import pytest

from deep_thought.todoist.db.queries import (
    delete_comment,
    delete_project,
    delete_section,
    delete_task,
    get_all_labels,
    get_all_projects,
    get_comments_for_task,
    get_labels_for_task,
    get_modified_tasks,
    get_project_by_id,
    get_sections_by_project,
    get_sync_value,
    get_task_by_id,
    get_tasks_by_project,
    get_tasks_by_section,
    mark_task_completed,
    mark_task_synced,
    set_sync_value,
    set_task_labels,
    upsert_comment,
    upsert_label,
    upsert_project,
    upsert_section,
    upsert_task,
)
from deep_thought.todoist.db.schema import get_schema_version, initialize_database
from tests.todoist.conftest import insert_project, insert_task

# ---------------------------------------------------------------------------
# Shared project / task data dicts
# ---------------------------------------------------------------------------


def _project_data(project_id: str = "proj-1", name: str = "Work") -> dict[str, Any]:
    return {
        "id": project_id,
        "name": name,
        "description": "",
        "color": "blue",
        "is_archived": False,
        "is_favorite": False,
        "is_inbox_project": False,
        "is_shared": False,
        "is_collapsed": False,
        "order_index": 1,
        "parent_id": None,
        "folder_id": None,
        "view_style": "list",
        "url": "https://todoist.com/p/1",
        "workspace_id": None,
        "can_assign_tasks": True,
        "created_at": "2026-01-01T00:00:00",
        "updated_at": "2026-01-01T00:00:00",
    }


def _section_data(section_id: str = "sec-1", project_id: str = "proj-1") -> dict[str, Any]:
    return {
        "id": section_id,
        "name": "Backlog",
        "project_id": project_id,
        "order_index": 1,
        "is_collapsed": False,
    }


def _task_data(task_id: str = "task-1", project_id: str = "proj-1") -> dict[str, Any]:
    return {
        "id": task_id,
        "content": "Write tests",
        "description": "",
        "project_id": project_id,
        "section_id": None,
        "parent_id": None,
        "order_index": 1,
        "priority": 1,
        "due_date": None,
        "due_string": None,
        "due_is_recurring": False,
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
        "created_at": "2026-01-01T00:00:00",
        "updated_at": "2026-01-01T00:00:00",
    }


def _label_data(label_id: str = "label-1", name: str = "urgent") -> dict[str, Any]:
    return {
        "id": label_id,
        "name": name,
        "color": "red",
        "order_index": 1,
        "is_favorite": False,
    }


def _comment_data(comment_id: str = "comment-1", task_id: str = "task-1") -> dict[str, Any]:
    return {
        "id": comment_id,
        "task_id": task_id,
        "project_id": None,
        "content": "Looks good!",
        "posted_at": "2026-03-10T09:00:00",
        "poster_id": "user-1",
        "attachment_json": None,
    }


# ---------------------------------------------------------------------------
# initialize_database / schema version
# ---------------------------------------------------------------------------


class TestInitializeDatabase:
    def test_creates_all_required_tables(self, in_memory_db: Any) -> None:
        """All tables defined in the migration must exist after initialization."""
        expected_tables = {"projects", "sections", "tasks", "labels", "task_labels", "comments", "sync_state"}
        cursor = in_memory_db.execute("SELECT name FROM sqlite_master WHERE type='table';")
        existing_tables = {row["name"] for row in cursor.fetchall()}
        assert expected_tables.issubset(existing_tables)

    def test_schema_version_is_nonzero_after_init(self, in_memory_db: Any) -> None:
        """After initialization, the schema version must be at least 1."""
        version = get_schema_version(in_memory_db)
        assert version >= 1

    def test_schema_version_returns_zero_on_empty_connection(self) -> None:
        """get_schema_version on a raw connection with no tables must return 0."""
        import sqlite3

        raw_conn = sqlite3.connect(":memory:")
        raw_conn.row_factory = sqlite3.Row
        version = get_schema_version(raw_conn)
        raw_conn.close()
        assert version == 0

    def test_running_init_twice_is_idempotent(self) -> None:
        """Calling initialize_database twice on the same path must not fail."""
        conn1 = initialize_database(":memory:")
        conn1.close()
        # A second call should also succeed without raising
        conn2 = initialize_database(":memory:")
        conn2.close()


# ---------------------------------------------------------------------------
# Projects CRUD
# ---------------------------------------------------------------------------


class TestProjectQueries:
    def test_upsert_and_get_project(self, in_memory_db: Any) -> None:
        upsert_project(in_memory_db, _project_data())
        row = get_project_by_id(in_memory_db, "proj-1")
        assert row is not None
        assert row["name"] == "Work"

    def test_get_all_projects_returns_ordered_list(self, in_memory_db: Any) -> None:
        upsert_project(in_memory_db, {**_project_data("proj-1"), "order_index": 2})
        upsert_project(in_memory_db, {**_project_data("proj-2", "Personal"), "order_index": 1})
        projects = get_all_projects(in_memory_db)
        assert projects[0]["id"] == "proj-2"  # lower order_index first
        assert projects[1]["id"] == "proj-1"

    def test_get_project_by_id_returns_none_for_missing(self, in_memory_db: Any) -> None:
        result = get_project_by_id(in_memory_db, "does-not-exist")
        assert result is None

    def test_upsert_project_updates_existing_row(self, in_memory_db: Any) -> None:
        upsert_project(in_memory_db, _project_data())
        updated_data = {**_project_data(), "name": "Updated Work"}
        upsert_project(in_memory_db, updated_data)
        row = get_project_by_id(in_memory_db, "proj-1")
        assert row is not None
        assert row["name"] == "Updated Work"

    def test_delete_project(self, in_memory_db: Any) -> None:
        upsert_project(in_memory_db, _project_data())
        delete_project(in_memory_db, "proj-1")
        assert get_project_by_id(in_memory_db, "proj-1") is None

    def test_upsert_sets_synced_at(self, in_memory_db: Any) -> None:
        upsert_project(in_memory_db, _project_data())
        row = get_project_by_id(in_memory_db, "proj-1")
        assert row is not None
        assert row["synced_at"] is not None

    def test_upsert_project_preserves_created_at_on_re_upsert(self, in_memory_db: Any) -> None:
        """Re-upserting a project must NOT overwrite the original created_at value."""
        original_created_at = "2025-01-01T00:00:00"
        upsert_project(in_memory_db, {**_project_data(), "created_at": original_created_at})

        # Simulate a subsequent pull with a different (newer) created_at coming from the API
        later_created_at = "2026-06-01T00:00:00"
        upsert_project(in_memory_db, {**_project_data(), "name": "Updated Work", "created_at": later_created_at})

        row = get_project_by_id(in_memory_db, "proj-1")
        assert row is not None
        assert row["name"] == "Updated Work"  # mutable fields are updated
        assert row["created_at"] == original_created_at  # created_at is never overwritten


# ---------------------------------------------------------------------------
# Sections CRUD
# ---------------------------------------------------------------------------


class TestSectionQueries:
    def test_upsert_and_get_sections_by_project(self, in_memory_db: Any) -> None:
        upsert_project(in_memory_db, _project_data())
        upsert_section(in_memory_db, _section_data())
        sections = get_sections_by_project(in_memory_db, "proj-1")
        assert len(sections) == 1
        assert sections[0]["name"] == "Backlog"

    def test_get_sections_returns_empty_for_unknown_project(self, in_memory_db: Any) -> None:
        sections = get_sections_by_project(in_memory_db, "no-such-project")
        assert sections == []

    def test_delete_section(self, in_memory_db: Any) -> None:
        upsert_project(in_memory_db, _project_data())
        upsert_section(in_memory_db, _section_data())
        delete_section(in_memory_db, "sec-1")
        sections = get_sections_by_project(in_memory_db, "proj-1")
        assert sections == []


# ---------------------------------------------------------------------------
# Tasks CRUD
# ---------------------------------------------------------------------------


class TestTaskQueries:
    def test_upsert_and_get_task_by_id(self, in_memory_db: Any) -> None:
        upsert_project(in_memory_db, _project_data())
        upsert_task(in_memory_db, _task_data())
        task = get_task_by_id(in_memory_db, "task-1")
        assert task is not None
        assert task["content"] == "Write tests"

    def test_get_task_by_id_returns_none_for_missing(self, in_memory_db: Any) -> None:
        result = get_task_by_id(in_memory_db, "missing-id")
        assert result is None

    def test_get_tasks_by_project_returns_all_tasks(self, in_memory_db: Any) -> None:
        upsert_project(in_memory_db, _project_data())
        upsert_task(in_memory_db, _task_data("task-1"))
        upsert_task(in_memory_db, {**_task_data("task-2"), "order_index": 2})
        tasks = get_tasks_by_project(in_memory_db, "proj-1")
        assert len(tasks) == 2

    def test_get_tasks_by_section(self, in_memory_db: Any) -> None:
        upsert_project(in_memory_db, _project_data())
        upsert_section(in_memory_db, _section_data())
        upsert_task(in_memory_db, {**_task_data(), "section_id": "sec-1"})
        tasks = get_tasks_by_section(in_memory_db, "sec-1")
        assert len(tasks) == 1

    def test_delete_task(self, in_memory_db: Any) -> None:
        upsert_project(in_memory_db, _project_data())
        upsert_task(in_memory_db, _task_data())
        delete_task(in_memory_db, "task-1")
        assert get_task_by_id(in_memory_db, "task-1") is None

    def test_upsert_task_preserves_created_at_on_re_upsert(self, in_memory_db: Any) -> None:
        """Re-upserting a task must NOT overwrite the original created_at value."""
        original_created_at = "2025-01-01T00:00:00"
        upsert_project(in_memory_db, _project_data())
        upsert_task(in_memory_db, {**_task_data(), "created_at": original_created_at})

        later_created_at = "2026-06-01T00:00:00"
        upsert_task(in_memory_db, {**_task_data(), "content": "Updated content", "created_at": later_created_at})

        task = get_task_by_id(in_memory_db, "task-1")
        assert task is not None
        assert task["content"] == "Updated content"  # mutable fields are updated
        assert task["created_at"] == original_created_at  # created_at is never overwritten


# ---------------------------------------------------------------------------
# get_modified_tasks and mark_task_synced
# ---------------------------------------------------------------------------


class TestModifiedTasks:
    def test_get_modified_tasks_returns_tasks_with_newer_updated_at(self, in_memory_db: Any) -> None:
        """A task where updated_at > synced_at must appear in modified results."""
        insert_project(in_memory_db)
        insert_task(
            in_memory_db,
            updated_at="2026-03-01T12:00:00",
            synced_at="2026-01-01T00:00:00",
        )
        modified = get_modified_tasks(in_memory_db)
        assert len(modified) == 1
        assert modified[0]["id"] == "task-1"

    def test_get_modified_tasks_excludes_synced_tasks(self, in_memory_db: Any) -> None:
        """A task where updated_at == synced_at must NOT appear in modified results."""
        insert_project(in_memory_db)
        insert_task(
            in_memory_db,
            updated_at="2026-01-01T00:00:00",
            synced_at="2026-01-01T00:00:00",
        )
        modified = get_modified_tasks(in_memory_db)
        assert modified == []

    def test_mark_task_synced_clears_modified_status(self, in_memory_db: Any) -> None:
        """After mark_task_synced, the task must not appear in modified results."""
        insert_project(in_memory_db)
        insert_task(
            in_memory_db,
            updated_at="2026-03-01T12:00:00",
            synced_at="2026-01-01T00:00:00",
        )
        mark_task_synced(in_memory_db, "task-1")
        in_memory_db.commit()
        modified = get_modified_tasks(in_memory_db)
        assert modified == []

    def test_mark_task_synced_sets_synced_at_to_now(self, in_memory_db: Any) -> None:
        """After mark_task_synced, synced_at must be >= updated_at."""
        insert_project(in_memory_db)
        insert_task(
            in_memory_db,
            updated_at="2026-03-01T12:00:00",
            synced_at="2026-01-01T00:00:00",
        )
        mark_task_synced(in_memory_db, "task-1")
        in_memory_db.commit()
        task = get_task_by_id(in_memory_db, "task-1")
        assert task is not None
        assert task["synced_at"] >= task["updated_at"]


# ---------------------------------------------------------------------------
# mark_task_completed
# ---------------------------------------------------------------------------


class TestMarkTaskCompleted:
    def test_sets_is_completed_flag(self, in_memory_db: Any) -> None:
        """After mark_task_completed, is_completed must be truthy."""
        insert_project(in_memory_db)
        insert_task(in_memory_db)
        mark_task_completed(in_memory_db, "task-1")
        in_memory_db.commit()
        task = get_task_by_id(in_memory_db, "task-1")
        assert task is not None
        assert bool(task["is_completed"])

    def test_sets_completed_at_to_a_timestamp(self, in_memory_db: Any) -> None:
        """After mark_task_completed, completed_at must be a non-null timestamp string."""
        insert_project(in_memory_db)
        insert_task(in_memory_db)
        mark_task_completed(in_memory_db, "task-1")
        in_memory_db.commit()
        task = get_task_by_id(in_memory_db, "task-1")
        assert task is not None
        assert task["completed_at"] is not None

    def test_task_does_not_appear_modified_after_completion(self, in_memory_db: Any) -> None:
        """After mark_task_completed, updated_at == synced_at so task is not in modified list."""
        insert_project(in_memory_db)
        insert_task(
            in_memory_db,
            updated_at="2026-03-01T12:00:00",
            synced_at="2026-01-01T00:00:00",
        )
        mark_task_completed(in_memory_db, "task-1")
        in_memory_db.commit()
        modified = get_modified_tasks(in_memory_db)
        assert modified == []


# ---------------------------------------------------------------------------
# Labels CRUD
# ---------------------------------------------------------------------------


class TestLabelQueries:
    def test_upsert_and_get_all_labels(self, in_memory_db: Any) -> None:
        upsert_label(in_memory_db, _label_data())
        labels = get_all_labels(in_memory_db)
        assert len(labels) == 1
        assert labels[0]["name"] == "urgent"

    def test_get_all_labels_returns_empty_when_none(self, in_memory_db: Any) -> None:
        assert get_all_labels(in_memory_db) == []


# ---------------------------------------------------------------------------
# Task labels (many-to-many join)
# ---------------------------------------------------------------------------


class TestTaskLabels:
    def test_set_task_labels_creates_join_rows(self, in_memory_db: Any) -> None:
        upsert_project(in_memory_db, _project_data())
        upsert_task(in_memory_db, _task_data())
        upsert_label(in_memory_db, _label_data("label-1", "urgent"))
        set_task_labels(in_memory_db, "task-1", ["label-1"])
        labels = get_labels_for_task(in_memory_db, "task-1")
        assert len(labels) == 1
        assert labels[0]["name"] == "urgent"

    def test_set_task_labels_replaces_existing_atomically(self, in_memory_db: Any) -> None:
        """Calling set_task_labels a second time must replace the old associations."""
        upsert_project(in_memory_db, _project_data())
        upsert_task(in_memory_db, _task_data())
        upsert_label(in_memory_db, _label_data("label-1", "urgent"))
        upsert_label(in_memory_db, {**_label_data("label-2", "work"), "order_index": 2})

        set_task_labels(in_memory_db, "task-1", ["label-1"])
        set_task_labels(in_memory_db, "task-1", ["label-2"])  # replaces label-1

        labels = get_labels_for_task(in_memory_db, "task-1")
        assert len(labels) == 1
        assert labels[0]["id"] == "label-2"

    def test_set_task_labels_with_empty_list_removes_all(self, in_memory_db: Any) -> None:
        upsert_project(in_memory_db, _project_data())
        upsert_task(in_memory_db, _task_data())
        upsert_label(in_memory_db, _label_data())
        set_task_labels(in_memory_db, "task-1", ["label-1"])
        set_task_labels(in_memory_db, "task-1", [])
        labels = get_labels_for_task(in_memory_db, "task-1")
        assert labels == []

    def test_get_labels_for_task_returns_empty_when_no_labels(self, in_memory_db: Any) -> None:
        upsert_project(in_memory_db, _project_data())
        upsert_task(in_memory_db, _task_data())
        labels = get_labels_for_task(in_memory_db, "task-1")
        assert labels == []


# ---------------------------------------------------------------------------
# Comments CRUD
# ---------------------------------------------------------------------------


class TestCommentQueries:
    def test_upsert_and_get_comments_for_task(self, in_memory_db: Any) -> None:
        upsert_project(in_memory_db, _project_data())
        upsert_task(in_memory_db, _task_data())
        upsert_comment(in_memory_db, _comment_data())
        comments = get_comments_for_task(in_memory_db, "task-1")
        assert len(comments) == 1
        assert comments[0]["content"] == "Looks good!"

    def test_get_comments_returns_empty_for_unknown_task(self, in_memory_db: Any) -> None:
        comments = get_comments_for_task(in_memory_db, "no-such-task")
        assert comments == []

    def test_delete_comment(self, in_memory_db: Any) -> None:
        upsert_project(in_memory_db, _project_data())
        upsert_task(in_memory_db, _task_data())
        upsert_comment(in_memory_db, _comment_data())
        delete_comment(in_memory_db, "comment-1")
        comments = get_comments_for_task(in_memory_db, "task-1")
        assert comments == []


# ---------------------------------------------------------------------------
# sync_state get/set
# ---------------------------------------------------------------------------


class TestSyncState:
    def test_get_sync_value_returns_none_for_missing_key(self, in_memory_db: Any) -> None:
        result = get_sync_value(in_memory_db, "nonexistent_key")
        assert result is None

    def test_set_and_get_sync_value_roundtrip(self, in_memory_db: Any) -> None:
        set_sync_value(in_memory_db, "test_key", "test_value")
        result = get_sync_value(in_memory_db, "test_key")
        assert result == "test_value"

    def test_set_sync_value_overwrites_existing(self, in_memory_db: Any) -> None:
        set_sync_value(in_memory_db, "test_key", "original")
        set_sync_value(in_memory_db, "test_key", "overwritten")
        result = get_sync_value(in_memory_db, "test_key")
        assert result == "overwritten"

    def test_schema_version_is_stored_in_sync_state(self, in_memory_db: Any) -> None:
        """After init, schema_version must be readable from sync_state."""
        version_str = get_sync_value(in_memory_db, "schema_version")
        assert version_str is not None
        assert int(version_str) >= 1


# ---------------------------------------------------------------------------
# Foreign key cascade tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestForeignKeyCascades:
    def test_deleting_project_cascades_to_sections(self, in_memory_db: Any) -> None:
        upsert_project(in_memory_db, _project_data())
        upsert_section(in_memory_db, _section_data())
        delete_project(in_memory_db, "proj-1")
        in_memory_db.commit()
        sections = get_sections_by_project(in_memory_db, "proj-1")
        assert sections == []

    def test_deleting_project_cascades_to_tasks(self, in_memory_db: Any) -> None:
        upsert_project(in_memory_db, _project_data())
        upsert_task(in_memory_db, _task_data())
        delete_project(in_memory_db, "proj-1")
        in_memory_db.commit()
        assert get_task_by_id(in_memory_db, "task-1") is None

    def test_deleting_task_cascades_to_comments(self, in_memory_db: Any) -> None:
        upsert_project(in_memory_db, _project_data())
        upsert_task(in_memory_db, _task_data())
        upsert_comment(in_memory_db, _comment_data())
        delete_task(in_memory_db, "task-1")
        in_memory_db.commit()
        comments = get_comments_for_task(in_memory_db, "task-1")
        assert comments == []

    def test_deleting_task_cascades_to_task_labels(self, in_memory_db: Any) -> None:
        upsert_project(in_memory_db, _project_data())
        upsert_task(in_memory_db, _task_data())
        upsert_label(in_memory_db, _label_data())
        set_task_labels(in_memory_db, "task-1", ["label-1"])
        delete_task(in_memory_db, "task-1")
        in_memory_db.commit()
        # No task_labels rows must remain for the deleted task
        cursor = in_memory_db.execute("SELECT COUNT(*) as cnt FROM task_labels WHERE task_id = 'task-1';")
        assert cursor.fetchone()["cnt"] == 0
