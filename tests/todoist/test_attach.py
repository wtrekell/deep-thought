"""Tests for the attach module in deep_thought.todoist.attach."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

from deep_thought.todoist.attach import attach_file
from deep_thought.todoist.db.schema import initialize_database

if TYPE_CHECKING:
    import sqlite3
    from collections.abc import Generator
    from pathlib import Path


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def memory_conn() -> Generator[sqlite3.Connection, None, None]:
    conn = initialize_database(":memory:")
    yield conn
    conn.close()


def _insert_task(conn: sqlite3.Connection, task_id: str, content: str) -> None:
    # Insert a stub project first to satisfy the FK constraint.
    conn.execute(
        """
        INSERT OR IGNORE INTO projects (
            id, name, description, color, is_archived, is_favorite,
            is_inbox_project, is_shared, is_collapsed, order_index,
            parent_id, folder_id, view_style, url, workspace_id,
            can_assign_tasks, created_at, updated_at, synced_at
        ) VALUES ('p1', 'Test', '', 'blue', 0, 0, 0, 0, 0, 1,
                  NULL, NULL, 'list', 'https://todoist.com/p/1', NULL,
                  1, '2026-01-01', '2026-01-01', '2026-01-01');
        """
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
            ?, ?, '', 'p1', NULL, NULL,
            1, 1, NULL, NULL, 0, NULL, NULL,
            NULL, NULL, NULL, NULL,
            NULL, NULL, NULL, 0, NULL,
            '[]', 'https://todoist.com/t/1',
            '2026-01-01', '2026-01-01', '2026-01-01'
        );
        """,
        (task_id, content),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# attach_file
# ---------------------------------------------------------------------------


class TestAttachFile:
    def test_raises_value_error_for_unknown_task(self, memory_conn: sqlite3.Connection, tmp_path: Path) -> None:
        client = MagicMock()
        test_file = tmp_path / "doc.pdf"
        test_file.write_bytes(b"data")
        with pytest.raises(ValueError, match="not found in local database"):
            attach_file(client, memory_conn, "nonexistent-task-id", test_file)

    def test_raises_file_not_found_for_missing_file(self, memory_conn: sqlite3.Connection, tmp_path: Path) -> None:
        _insert_task(memory_conn, "task1", "Do something")
        client = MagicMock()
        with pytest.raises(FileNotFoundError):
            attach_file(client, memory_conn, "task1", tmp_path / "nonexistent.pdf")

    def test_dry_run_returns_without_api_call(self, memory_conn: sqlite3.Connection, tmp_path: Path) -> None:
        _insert_task(memory_conn, "task1", "Do something")
        test_file = tmp_path / "report.pdf"
        test_file.write_bytes(b"PDF content here")
        client = MagicMock()

        result = attach_file(client, memory_conn, "task1", test_file, dry_run=True)

        assert result.dry_run is True
        assert result.task_id == "task1"
        assert result.file_name == "report.pdf"
        assert result.file_size == len(b"PDF content here")
        assert result.comment_id == ""
        client.upload_attachment.assert_not_called()
        client.add_comment_with_attachment.assert_not_called()

    def test_successful_attach_returns_result(self, memory_conn: sqlite3.Connection, tmp_path: Path) -> None:
        _insert_task(memory_conn, "task1", "Do something")
        test_file = tmp_path / "report.pdf"
        test_file.write_bytes(b"PDF content")

        attachment_dict = {
            "file_name": "report.pdf",
            "file_size": 11,
            "file_type": "application/pdf",
            "file_url": "https://todoist.com/uploads/report.pdf",
            "resource_type": "file",
            "upload_state": "completed",
        }
        mock_comment = MagicMock()
        mock_comment.id = "comment-abc"
        mock_comment.posted_at = "2026-04-05T10:00:00"

        client = MagicMock()
        client.upload_attachment.return_value = attachment_dict
        client.add_comment_with_attachment.return_value = mock_comment

        result = attach_file(client, memory_conn, "task1", test_file)

        assert result.dry_run is False
        assert result.task_id == "task1"
        assert result.file_name == "report.pdf"
        assert result.file_size == 11
        assert result.comment_id == "comment-abc"
        client.upload_attachment.assert_called_once_with(test_file)
        client.add_comment_with_attachment.assert_called_once_with("task1", "File attachment", attachment_dict)

    def test_successful_attach_writes_comment_to_db(self, memory_conn: sqlite3.Connection, tmp_path: Path) -> None:
        _insert_task(memory_conn, "task1", "Do something")
        test_file = tmp_path / "notes.txt"
        test_file.write_bytes(b"some notes")

        attachment_dict = {
            "file_name": "notes.txt",
            "file_size": 10,
            "file_type": "text/plain",
            "file_url": "https://todoist.com/uploads/notes.txt",
            "resource_type": "file",
            "upload_state": "completed",
        }
        mock_comment = MagicMock()
        mock_comment.id = "comment-xyz"
        mock_comment.posted_at = "2026-04-05T10:00:00"

        client = MagicMock()
        client.upload_attachment.return_value = attachment_dict
        client.add_comment_with_attachment.return_value = mock_comment

        attach_file(client, memory_conn, "task1", test_file)

        cursor = memory_conn.execute("SELECT * FROM comments WHERE id = 'comment-xyz';")
        row = cursor.fetchone()
        assert row is not None
        assert row["task_id"] == "task1"
        assert row["content"] == "File attachment"
        stored_attachment = json.loads(row["attachment_json"])
        assert stored_attachment["file_name"] == "notes.txt"

    def test_custom_message_is_used(self, memory_conn: sqlite3.Connection, tmp_path: Path) -> None:
        _insert_task(memory_conn, "task1", "Do something")
        test_file = tmp_path / "file.txt"
        test_file.write_bytes(b"x")

        attachment_dict = {
            "file_name": "file.txt",
            "file_size": 1,
            "file_type": "text/plain",
            "file_url": "https://todoist.com/uploads/file.txt",
            "resource_type": "file",
            "upload_state": "completed",
        }
        mock_comment = MagicMock()
        mock_comment.id = "c1"
        mock_comment.posted_at = "2026-04-05T10:00:00"

        client = MagicMock()
        client.upload_attachment.return_value = attachment_dict
        client.add_comment_with_attachment.return_value = mock_comment

        attach_file(client, memory_conn, "task1", test_file, message="See attached spec")

        client.add_comment_with_attachment.assert_called_once_with("task1", "See attached spec", attachment_dict)
