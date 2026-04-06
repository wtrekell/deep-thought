"""Tests for the export module in deep_thought.todoist.export.

Uses an in-memory SQLite database and a temporary directory for output files.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

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
from deep_thought.todoist.export import (
    _render_comment_line,
    _render_section_file,
    _safe_directory_name,
    export_to_markdown,
)

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


def _insert_project(conn: sqlite3.Connection, project_id: str, name: str) -> None:
    conn.execute(
        """
        INSERT INTO projects (
            id, name, description, color, is_archived, is_favorite,
            is_inbox_project, is_shared, is_collapsed, order_index,
            parent_id, folder_id, view_style, url, workspace_id,
            can_assign_tasks, created_at, updated_at, synced_at
        ) VALUES (?, ?, '', 'blue', 0, 0, 0, 0, 0, 1,
                  NULL, NULL, 'list', 'https://todoist.com/p/1', NULL,
                  1, '2026-01-01', '2026-01-01', '2026-01-01');
        """,
        (project_id, name),
    )
    conn.commit()


def _insert_section(conn: sqlite3.Connection, section_id: str, project_id: str, name: str) -> None:
    conn.execute(
        """
        INSERT INTO sections (id, name, project_id, order_index, is_collapsed, synced_at)
        VALUES (?, ?, ?, 1, 0, '2026-01-01');
        """,
        (section_id, name, project_id),
    )
    conn.commit()


def _insert_task(
    conn: sqlite3.Connection,
    task_id: str,
    project_id: str,
    content: str,
    section_id: str | None = None,
    parent_id: str | None = None,
    labels: list[str] | None = None,
    priority: int = 1,
    due_date: str | None = None,
    due_string: str | None = None,
    due_is_recurring: bool | None = None,
    deadline_date: str | None = None,
    description: str = "",
    is_completed: bool = False,
) -> None:
    conn.execute(
        """
        INSERT INTO tasks (
            id, content, description, project_id, section_id, parent_id,
            order_index, priority, due_date, due_string, due_is_recurring, due_lang, due_timezone,
            deadline_date, deadline_lang, duration_amount, duration_unit,
            assignee_id, assigner_id, creator_id, is_completed, completed_at,
            labels, url, created_at, updated_at, synced_at
        ) VALUES (
            ?, ?, ?, ?, ?, ?,
            1, ?, ?, ?, ?, NULL, NULL,
            ?, NULL, NULL, NULL,
            NULL, NULL, NULL, ?, NULL,
            ?, 'https://todoist.com/t/1',
            '2026-01-01', '2026-01-01', '2026-01-01'
        );
        """,
        (
            task_id,
            content,
            description,
            project_id,
            section_id,
            parent_id,
            priority,
            due_date,
            due_string,
            1 if due_is_recurring else 0,  # NOT NULL INTEGER, default 0
            deadline_date,
            1 if is_completed else 0,
            json.dumps(labels or []),
        ),
    )
    conn.commit()


def _insert_comment(
    conn: sqlite3.Connection,
    comment_id: str,
    task_id: str,
    content: str,
    posted_at: str = "2026-01-15T10:00:00",
    poster_id: str = "user123",
    attachment_json: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO comments (id, task_id, project_id, content, posted_at, poster_id, attachment_json, synced_at)
        VALUES (?, ?, NULL, ?, ?, ?, ?, '2026-01-15T10:00:00');
        """,
        (comment_id, task_id, content, posted_at, poster_id, attachment_json),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# _render_comment_line
# ---------------------------------------------------------------------------


class TestRenderCommentLine:
    def test_renders_basic_comment(self, memory_conn: sqlite3.Connection) -> None:
        comment: dict[str, object] = {
            "posted_at": "2026-01-15T10:00:00",
            "poster_id": "user123",
            "content": "Hello world",
            "attachment_json": None,
        }
        result = _render_comment_line(memory_conn, comment, include_attachments=False)
        assert result == "[2026-01-15 user123] Hello world"

    def test_no_attachment_when_flag_false(self, memory_conn: sqlite3.Connection) -> None:
        attachment_data = json.dumps(
            {
                "file_name": "doc.pdf",
                "file_url": "https://example.com/doc.pdf",
                "file_type": "application/pdf",
                "file_size": 10240,
            }
        )
        comment: dict[str, object] = {
            "posted_at": "2026-01-15T10:00:00",
            "poster_id": "user123",
            "content": "See file",
            "attachment_json": attachment_data,
        }
        result = _render_comment_line(memory_conn, comment, include_attachments=False)
        assert "attachment" not in result
        assert result == "[2026-01-15 user123] See file"

    def test_includes_attachment_when_flag_true(self, memory_conn: sqlite3.Connection) -> None:
        attachment_data = json.dumps(
            {
                "file_name": "report.pdf",
                "file_url": "https://example.com/report.pdf",
                "file_type": "application/pdf",
                "file_size": 20480,
            }
        )
        comment: dict[str, object] = {
            "posted_at": "2026-01-15T10:00:00",
            "poster_id": "user123",
            "content": "See attached report",
            "attachment_json": attachment_data,
        }
        result = _render_comment_line(memory_conn, comment, include_attachments=True)
        assert "[2026-01-15 user123] See attached report" in result
        assert "attachment: report.pdf" in result
        assert "application/pdf" in result
        assert "https://example.com/report.pdf" in result
        assert "20.0 KB" in result

    def test_no_attachment_appended_when_attachment_json_is_none(self, memory_conn: sqlite3.Connection) -> None:
        comment: dict[str, object] = {
            "posted_at": "2026-01-15T10:00:00",
            "poster_id": "user123",
            "content": "No file here",
            "attachment_json": None,
        }
        result = _render_comment_line(memory_conn, comment, include_attachments=True)
        assert "attachment" not in result
        assert result == "[2026-01-15 user123] No file here"


# ---------------------------------------------------------------------------
# _safe_directory_name
# ---------------------------------------------------------------------------


class TestSafeDirectoryName:
    def test_plain_name_unchanged(self) -> None:
        assert _safe_directory_name("Work") == "Work"

    def test_replaces_forward_slash(self) -> None:
        assert _safe_directory_name("A/B") == "A-B"

    def test_replaces_colon(self) -> None:
        assert _safe_directory_name("Work: Tasks") == "Work- Tasks"

    def test_strips_leading_trailing_whitespace(self) -> None:
        assert _safe_directory_name("  Work  ") == "Work"


# ---------------------------------------------------------------------------
# _render_section_file
# ---------------------------------------------------------------------------


class TestRenderSectionFile:
    def test_renders_project_and_section_headings(
        self, memory_conn: sqlite3.Connection, base_config: TodoistConfig
    ) -> None:
        task = {
            "id": "t1",
            "content": "My task",
            "description": "",
            "project_id": "p1",
            "section_id": "s1",
            "parent_id": None,
            "order_index": 1,
            "priority": 1,
            "due_date": None,
            "due_string": None,
            "due_is_recurring": None,
            "deadline_date": None,
            "assignee_id": None,
            "labels": "[]",
            "is_completed": False,
        }
        content = _render_section_file(memory_conn, "Work", "Backlog", [task], base_config)
        assert "# Work" in content
        assert "## Backlog" in content

    def test_renders_task_checkbox_uncompleted(
        self, memory_conn: sqlite3.Connection, base_config: TodoistConfig
    ) -> None:
        task = {
            "id": "t1",
            "content": "Open task",
            "description": "",
            "project_id": "p1",
            "section_id": "s1",
            "parent_id": None,
            "order_index": 1,
            "priority": 1,
            "due_date": None,
            "due_string": None,
            "due_is_recurring": None,
            "deadline_date": None,
            "assignee_id": None,
            "labels": "[]",
            "is_completed": False,
        }
        content = _render_section_file(memory_conn, "Work", "Backlog", [task], base_config)
        assert "- [ ] Open task" in content

    def test_renders_completed_task_with_x(self, memory_conn: sqlite3.Connection, base_config: TodoistConfig) -> None:
        task = {
            "id": "t1",
            "content": "Done task",
            "description": "",
            "project_id": "p1",
            "section_id": "s1",
            "parent_id": None,
            "order_index": 1,
            "priority": 1,
            "due_date": None,
            "due_string": None,
            "due_is_recurring": None,
            "deadline_date": None,
            "assignee_id": None,
            "labels": "[]",
            "is_completed": True,
        }
        content = _render_section_file(memory_conn, "Work", "Backlog", [task], base_config)
        assert "- [x] Done task" in content

    def test_renders_claude_marker_when_label_matches(
        self, memory_conn: sqlite3.Connection, base_config: TodoistConfig
    ) -> None:
        task = {
            "id": "t1",
            "content": "Claude task",
            "description": "",
            "project_id": "p1",
            "section_id": "s1",
            "parent_id": None,
            "order_index": 1,
            "priority": 1,
            "due_date": None,
            "due_string": None,
            "due_is_recurring": None,
            "deadline_date": None,
            "assignee_id": None,
            "labels": '["claude-code"]',
            "is_completed": False,
        }
        content = _render_section_file(memory_conn, "Work", "Backlog", [task], base_config)
        assert "  - claude:" in content
        assert "      repo: deep-thought" in content
        assert "      branch: main" in content

    def test_omits_claude_marker_when_label_absent(
        self, memory_conn: sqlite3.Connection, base_config: TodoistConfig
    ) -> None:
        task = {
            "id": "t1",
            "content": "Regular task",
            "description": "",
            "project_id": "p1",
            "section_id": "s1",
            "parent_id": None,
            "order_index": 1,
            "priority": 1,
            "due_date": None,
            "due_string": None,
            "due_is_recurring": None,
            "deadline_date": None,
            "assignee_id": None,
            "labels": "[]",
            "is_completed": False,
        }
        content = _render_section_file(memory_conn, "Work", "Backlog", [task], base_config)
        assert "- claude:" not in content

    def test_renders_claude_block_without_repo_when_repo_not_configured(self, memory_conn: sqlite3.Connection) -> None:
        """Should render branch but omit repo when claude.repo is None."""
        from deep_thought.todoist.config import ClaudeConfig

        config_no_repo = TodoistConfig(
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
            claude=ClaudeConfig(label="claude-code", repo=None, branch="main"),
        )
        task = {
            "id": "t1",
            "content": "Claude task no repo",
            "description": "",
            "project_id": "p1",
            "section_id": "s1",
            "parent_id": None,
            "order_index": 1,
            "priority": 1,
            "due_date": None,
            "due_string": None,
            "due_is_recurring": None,
            "deadline_date": None,
            "assignee_id": None,
            "labels": '["claude-code"]',
            "is_completed": False,
        }
        content = _render_section_file(memory_conn, "Work", "Backlog", [task], config_no_repo)
        assert "  - claude:" in content
        assert "repo:" not in content
        assert "      branch: main" in content

    def test_renders_due_date(self, memory_conn: sqlite3.Connection, base_config: TodoistConfig) -> None:
        task = {
            "id": "t1",
            "content": "Task with due",
            "description": "",
            "project_id": "p1",
            "section_id": "s1",
            "parent_id": None,
            "order_index": 1,
            "priority": 1,
            "due_date": "2026-03-15",
            "due_string": None,
            "due_is_recurring": None,
            "deadline_date": None,
            "assignee_id": None,
            "labels": "[]",
            "is_completed": False,
        }
        content = _render_section_file(memory_conn, "Work", "Backlog", [task], base_config)
        assert "- due: 2026-03-15" in content

    def test_renders_recurring_when_due_is_recurring(
        self, memory_conn: sqlite3.Connection, base_config: TodoistConfig
    ) -> None:
        task = {
            "id": "t1",
            "content": "Recurring task",
            "description": "",
            "project_id": "p1",
            "section_id": "s1",
            "parent_id": None,
            "order_index": 1,
            "priority": 1,
            "due_date": "2026-03-15",
            "due_string": "every week",
            "due_is_recurring": True,
            "deadline_date": None,
            "assignee_id": None,
            "labels": "[]",
            "is_completed": False,
        }
        content = _render_section_file(memory_conn, "Work", "Backlog", [task], base_config)
        assert "- recurring: every week" in content

    def test_omits_empty_optional_fields(self, memory_conn: sqlite3.Connection, base_config: TodoistConfig) -> None:
        task = {
            "id": "t1",
            "content": "Plain task",
            "description": "",
            "project_id": "p1",
            "section_id": "s1",
            "parent_id": None,
            "order_index": 1,
            "priority": 1,
            "due_date": None,
            "due_string": None,
            "due_is_recurring": None,
            "deadline_date": None,
            "assignee_id": None,
            "labels": "[]",
            "is_completed": False,
        }
        content = _render_section_file(memory_conn, "Work", "Backlog", [task], base_config)
        assert "- due:" not in content
        assert "- recurring:" not in content
        assert "- deadline:" not in content
        assert "- assignee:" not in content
        assert "- description:" not in content


# ---------------------------------------------------------------------------
# export_to_markdown() function
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestExportToMarkdown:
    def test_export_creates_project_directory(
        self, tmp_path: Path, memory_conn: sqlite3.Connection, base_config: TodoistConfig
    ) -> None:
        _insert_project(memory_conn, "proj-1", "Work")
        _insert_section(memory_conn, "sec-1", "proj-1", "Backlog")
        _insert_task(memory_conn, "task-1", "proj-1", "A task", section_id="sec-1")

        result = export_to_markdown(memory_conn, base_config, output_dir=tmp_path)
        assert (tmp_path / "Work").is_dir()
        assert result.projects_exported == 1

    def test_export_creates_section_file(
        self, tmp_path: Path, memory_conn: sqlite3.Connection, base_config: TodoistConfig
    ) -> None:
        _insert_project(memory_conn, "proj-1", "Work")
        _insert_section(memory_conn, "sec-1", "proj-1", "Backlog")
        _insert_task(memory_conn, "task-1", "proj-1", "A task", section_id="sec-1")

        export_to_markdown(memory_conn, base_config, output_dir=tmp_path)
        assert (tmp_path / "Work" / "Backlog.md").is_file()

    def test_export_unsectioned_tasks_to_underscore_file(
        self, tmp_path: Path, memory_conn: sqlite3.Connection, base_config: TodoistConfig
    ) -> None:
        _insert_project(memory_conn, "proj-1", "Work")
        _insert_task(memory_conn, "task-1", "proj-1", "Floating task", section_id=None)

        export_to_markdown(memory_conn, base_config, output_dir=tmp_path)
        assert (tmp_path / "Work" / "_unsectioned.md").is_file()

    def test_export_section_file_contains_task(
        self, tmp_path: Path, memory_conn: sqlite3.Connection, base_config: TodoistConfig
    ) -> None:
        _insert_project(memory_conn, "proj-1", "Work")
        _insert_section(memory_conn, "sec-1", "proj-1", "Backlog")
        _insert_task(memory_conn, "task-1", "proj-1", "Write the spec", section_id="sec-1")

        export_to_markdown(memory_conn, base_config, output_dir=tmp_path)
        content = (tmp_path / "Work" / "Backlog.md").read_text()
        assert "Write the spec" in content

    def test_export_skips_unconfigured_project(
        self, tmp_path: Path, memory_conn: sqlite3.Connection, base_config: TodoistConfig
    ) -> None:
        _insert_project(memory_conn, "proj-2", "Personal")  # not in config.projects
        _insert_section(memory_conn, "sec-1", "proj-2", "Inbox")
        _insert_task(memory_conn, "task-1", "proj-2", "Private task", section_id="sec-1")

        result = export_to_markdown(memory_conn, base_config, output_dir=tmp_path)
        assert result.projects_exported == 0
        assert not (tmp_path / "Personal").exists()

    def test_export_project_filter_limits_output(
        self, tmp_path: Path, memory_conn: sqlite3.Connection, base_config: TodoistConfig
    ) -> None:
        config_two_projects = TodoistConfig(
            api_token_env=base_config.api_token_env,
            projects=["Work", "Personal"],
            pull_filters=base_config.pull_filters,
            push_filters=base_config.push_filters,
            comments=base_config.comments,
            claude=base_config.claude,
        )
        _insert_project(memory_conn, "proj-1", "Work")
        _insert_project(memory_conn, "proj-2", "Personal")
        _insert_section(memory_conn, "sec-1", "proj-1", "Backlog")
        _insert_section(memory_conn, "sec-2", "proj-2", "Inbox")
        _insert_task(memory_conn, "t1", "proj-1", "Work task", section_id="sec-1")
        _insert_task(memory_conn, "t2", "proj-2", "Personal task", section_id="sec-2")

        result = export_to_markdown(memory_conn, config_two_projects, output_dir=tmp_path, project_filter="Work")
        assert result.projects_exported == 1
        assert (tmp_path / "Work").is_dir()
        assert not (tmp_path / "Personal").exists()

    def test_export_returns_correct_counts(
        self, tmp_path: Path, memory_conn: sqlite3.Connection, base_config: TodoistConfig
    ) -> None:
        _insert_project(memory_conn, "proj-1", "Work")
        _insert_section(memory_conn, "sec-1", "proj-1", "Backlog")
        _insert_section(memory_conn, "sec-2", "proj-1", "In Progress")
        _insert_task(memory_conn, "t1", "proj-1", "Task 1", section_id="sec-1")
        _insert_task(memory_conn, "t2", "proj-1", "Task 2", section_id="sec-1")
        _insert_task(memory_conn, "t3", "proj-1", "Task 3", section_id="sec-2")

        result = export_to_markdown(memory_conn, base_config, output_dir=tmp_path)
        assert result.projects_exported == 1
        assert result.files_written == 2
        assert result.tasks_exported == 3
