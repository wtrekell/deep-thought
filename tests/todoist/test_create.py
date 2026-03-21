"""Tests for the create subcommand business logic (create.py).

Uses in-memory SQLite via the shared `in_memory_db` fixture and a MagicMock
client via the shared `mock_client` fixture. No real API calls are made.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from deep_thought.todoist.create import (
    _resolve_label_ids,
    _resolve_project_id,
    _resolve_section_id,
    create_task,
)

if TYPE_CHECKING:
    import sqlite3
    from unittest.mock import MagicMock

from tests.todoist.conftest import insert_project  # noqa: E402

# ---------------------------------------------------------------------------
# Local insertion helpers (only needed by this test module)
# ---------------------------------------------------------------------------


def insert_section(
    conn: sqlite3.Connection,
    section_id: str = "sec-1",
    project_id: str = "proj-1",
    name: str = "Backlog",
) -> None:
    """Insert a minimal section row for use in test setup."""
    conn.execute(
        """
        INSERT OR IGNORE INTO sections (id, name, project_id, order_index, is_collapsed, synced_at)
        VALUES (?, ?, ?, 1, 0, '2026-01-01T00:00:00');
        """,
        (section_id, name, project_id),
    )
    conn.commit()


def insert_label(
    conn: sqlite3.Connection,
    label_id: str = "label-1",
    name: str = "urgent",
) -> None:
    """Insert a minimal label row for use in test setup."""
    conn.execute(
        """
        INSERT OR IGNORE INTO labels (id, name, color, order_index, is_favorite, synced_at)
        VALUES (?, ?, 'red', 1, 0, '2026-01-01T00:00:00');
        """,
        (label_id, name),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# TestResolveProjectId
# ---------------------------------------------------------------------------


class TestResolveProjectId:
    def test_resolves_existing_project_by_name(self, in_memory_db: sqlite3.Connection) -> None:
        """Returns the correct project ID when the project exists in the DB."""
        insert_project(in_memory_db, project_id="proj-42", name="My Project")

        resolved_id = _resolve_project_id(in_memory_db, "My Project")

        assert resolved_id == "proj-42"

    def test_raises_value_error_for_unknown_project(self, in_memory_db: sqlite3.Connection) -> None:
        """Raises ValueError with a helpful message when the project is not found."""
        with pytest.raises(ValueError, match="todoist pull"):
            _resolve_project_id(in_memory_db, "Ghost Project")


# ---------------------------------------------------------------------------
# TestResolveSectionId
# ---------------------------------------------------------------------------


class TestResolveSectionId:
    def test_resolves_existing_section_by_name_within_project(self, in_memory_db: sqlite3.Connection) -> None:
        """Returns the correct section ID when it exists under the given project."""
        insert_project(in_memory_db, project_id="proj-1", name="Work")
        insert_section(in_memory_db, section_id="sec-99", project_id="proj-1", name="Sprint 1")

        resolved_id = _resolve_section_id(in_memory_db, "proj-1", "Sprint 1")

        assert resolved_id == "sec-99"

    def test_raises_value_error_for_section_in_wrong_project(self, in_memory_db: sqlite3.Connection) -> None:
        """Raises ValueError when section exists but belongs to a different project."""
        insert_project(in_memory_db, project_id="proj-1", name="Work")
        insert_project(in_memory_db, project_id="proj-2", name="Personal")
        insert_section(in_memory_db, section_id="sec-1", project_id="proj-2", name="Backlog")

        with pytest.raises(ValueError, match="todoist pull"):
            _resolve_section_id(in_memory_db, "proj-1", "Backlog")

    def test_raises_value_error_for_unknown_section(self, in_memory_db: sqlite3.Connection) -> None:
        """Raises ValueError when the section name doesn't exist at all."""
        insert_project(in_memory_db, project_id="proj-1", name="Work")

        with pytest.raises(ValueError, match="todoist pull"):
            _resolve_section_id(in_memory_db, "proj-1", "Nonexistent Section")


# ---------------------------------------------------------------------------
# TestResolveLabelIds
# ---------------------------------------------------------------------------


class TestResolveLabelIds:
    def test_resolves_all_labels_that_exist(self, in_memory_db: sqlite3.Connection) -> None:
        """Returns the correct IDs and full name→id map when all labels are found."""
        insert_label(in_memory_db, label_id="label-1", name="urgent")
        insert_label(in_memory_db, label_id="label-2", name="bug")

        resolved_ids, name_to_id_map = _resolve_label_ids(in_memory_db, ["urgent", "bug"])

        assert resolved_ids == ["label-1", "label-2"]
        assert name_to_id_map == {"urgent": "label-1", "bug": "label-2"}

    def test_raises_value_error_for_any_unknown_label(self, in_memory_db: sqlite3.Connection) -> None:
        """Raises ValueError that names the missing label when any are not found."""
        insert_label(in_memory_db, label_id="label-1", name="urgent")

        with pytest.raises(ValueError, match="missing-label"):
            _resolve_label_ids(in_memory_db, ["urgent", "missing-label"])

    def test_returns_empty_for_empty_label_list(self, in_memory_db: sqlite3.Connection) -> None:
        """Returns empty IDs and an empty map when given an empty label list."""
        resolved_ids, name_to_id_map = _resolve_label_ids(in_memory_db, [])

        assert resolved_ids == []
        assert name_to_id_map == {}


# ---------------------------------------------------------------------------
# TestCreateTask
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestCreateTask:
    def test_dry_run_does_not_call_api(self, mock_client: MagicMock, in_memory_db: sqlite3.Connection) -> None:
        """API create_task is never called in dry-run mode."""
        insert_project(in_memory_db, project_id="proj-1", name="Work")

        create_task(
            mock_client,
            in_memory_db,
            "Buy coffee",
            "Work",
            dry_run=True,
        )

        mock_client.create_task.assert_not_called()

    def test_dry_run_does_not_write_to_db(self, mock_client: MagicMock, in_memory_db: sqlite3.Connection) -> None:
        """No task row is inserted into the database during a dry run."""
        insert_project(in_memory_db, project_id="proj-1", name="Work")

        create_task(
            mock_client,
            in_memory_db,
            "Buy coffee",
            "Work",
            dry_run=True,
        )

        cursor = in_memory_db.execute("SELECT COUNT(*) FROM tasks;")
        task_count = cursor.fetchone()[0]
        assert task_count == 0

    def test_creates_task_and_writes_to_db(
        self,
        mock_client: MagicMock,
        in_memory_db: sqlite3.Connection,
        sample_task_sdk: MagicMock,
    ) -> None:
        """Happy path: API is called and resulting task is written to the DB."""
        insert_project(in_memory_db, project_id="proj-1", name="Work")
        sample_task_sdk.content = "Buy coffee"
        sample_task_sdk.section_id = None  # avoid FK constraint on sections table
        sample_task_sdk.labels = []
        mock_client.create_task.return_value = sample_task_sdk

        result = create_task(mock_client, in_memory_db, "Buy coffee", "Work")

        assert result.created is True
        assert result.task_content == "Buy coffee"

        cursor = in_memory_db.execute("SELECT content FROM tasks WHERE id = ?;", (sample_task_sdk.id,))
        row = cursor.fetchone()
        assert row is not None
        assert row["content"] == "Buy coffee"

    def test_creates_task_with_section(
        self,
        mock_client: MagicMock,
        in_memory_db: sqlite3.Connection,
        sample_task_sdk: MagicMock,
    ) -> None:
        """When --section is given, the resolved section_id is passed to the API."""
        insert_project(in_memory_db, project_id="proj-1", name="Work")
        insert_section(in_memory_db, section_id="sec-99", project_id="proj-1", name="Sprint 1")
        sample_task_sdk.section_id = "sec-99"  # match the inserted section for FK compliance
        sample_task_sdk.labels = []
        mock_client.create_task.return_value = sample_task_sdk

        create_task(
            mock_client,
            in_memory_db,
            "Fix bug",
            "Work",
            section_name="Sprint 1",
        )

        call_kwargs = mock_client.create_task.call_args.kwargs
        assert call_kwargs["section_id"] == "sec-99"

    def test_creates_task_with_labels(
        self,
        mock_client: MagicMock,
        in_memory_db: sqlite3.Connection,
        sample_task_sdk: MagicMock,
    ) -> None:
        """Label names are forwarded to the API and the task_labels join row is written."""
        insert_project(in_memory_db, project_id="proj-1", name="Work")
        insert_label(in_memory_db, label_id="label-1", name="urgent")
        sample_task_sdk.section_id = None  # avoid FK constraint on sections table
        sample_task_sdk.labels = ["urgent"]
        mock_client.create_task.return_value = sample_task_sdk

        create_task(
            mock_client,
            in_memory_db,
            "Fix bug",
            "Work",
            label_names=["urgent"],
        )

        call_kwargs = mock_client.create_task.call_args.kwargs
        assert call_kwargs["labels"] == ["urgent"]

        cursor = in_memory_db.execute("SELECT label_id FROM task_labels WHERE task_id = ?;", (sample_task_sdk.id,))
        task_label_row = cursor.fetchone()
        assert task_label_row is not None
        assert task_label_row["label_id"] == "label-1"

    def test_creates_task_with_due_and_priority(
        self,
        mock_client: MagicMock,
        in_memory_db: sqlite3.Connection,
        sample_task_sdk: MagicMock,
    ) -> None:
        """due_string and priority are forwarded as kwargs to the API create call."""
        insert_project(in_memory_db, project_id="proj-1", name="Work")
        sample_task_sdk.section_id = None  # avoid FK constraint on sections table
        sample_task_sdk.labels = []
        mock_client.create_task.return_value = sample_task_sdk

        create_task(
            mock_client,
            in_memory_db,
            "Important thing",
            "Work",
            due_string="tomorrow",
            priority=4,
        )

        call_kwargs = mock_client.create_task.call_args.kwargs
        assert call_kwargs["due_string"] == "tomorrow"
        assert call_kwargs["priority"] == 4

    def test_raises_value_error_when_project_not_in_db(
        self, mock_client: MagicMock, in_memory_db: sqlite3.Connection
    ) -> None:
        """Raises ValueError (not an API call) when the project is not in the local DB."""
        with pytest.raises(ValueError, match="todoist pull"):
            create_task(mock_client, in_memory_db, "Some task", "Nonexistent Project")

        mock_client.create_task.assert_not_called()

    def test_raises_value_error_when_section_not_in_db(
        self, mock_client: MagicMock, in_memory_db: sqlite3.Connection
    ) -> None:
        """Raises ValueError when section name cannot be resolved."""
        insert_project(in_memory_db, project_id="proj-1", name="Work")

        with pytest.raises(ValueError, match="todoist pull"):
            create_task(
                mock_client,
                in_memory_db,
                "Some task",
                "Work",
                section_name="Ghost Section",
            )

        mock_client.create_task.assert_not_called()

    def test_raises_value_error_when_label_not_in_db(
        self, mock_client: MagicMock, in_memory_db: sqlite3.Connection
    ) -> None:
        """Raises ValueError when a label name cannot be resolved."""
        insert_project(in_memory_db, project_id="proj-1", name="Work")

        with pytest.raises(ValueError, match="todoist pull"):
            create_task(
                mock_client,
                in_memory_db,
                "Some task",
                "Work",
                label_names=["nonexistent-label"],
            )

        mock_client.create_task.assert_not_called()
