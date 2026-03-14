"""Tests for the filter engine in deep_thought.todoist.filters.

These tests operate entirely on in-memory model objects — no database required.
"""

from __future__ import annotations

from deep_thought.todoist.config import FilterConfig, PullFilters, PushFilters
from deep_thought.todoist.filters import (
    _passes_include_exclude,
    _passes_label_filter,
    apply_pull_filters,
    apply_push_filters,
)
from deep_thought.todoist.models import TaskLocal

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_pull_filters(
    label_include: list[str] | None = None,
    label_exclude: list[str] | None = None,
    section_include: list[str] | None = None,
    section_exclude: list[str] | None = None,
    assignee_include: list[str] | None = None,
    has_due_date: bool | None = None,
) -> PullFilters:
    return PullFilters(
        labels=FilterConfig(include=label_include or [], exclude=label_exclude or []),
        projects=FilterConfig(include=[], exclude=[]),
        sections=FilterConfig(include=section_include or [], exclude=section_exclude or []),
        assignee=FilterConfig(include=assignee_include or [], exclude=[]),
        has_due_date=has_due_date,
    )


def _make_push_filters(
    label_include: list[str] | None = None,
    label_exclude: list[str] | None = None,
    assignee_include: list[str] | None = None,
) -> PushFilters:
    return PushFilters(
        labels=FilterConfig(include=label_include or [], exclude=label_exclude or []),
        assignee=FilterConfig(include=assignee_include or [], exclude=[]),
        conflict_resolution="prompt",
        require_confirmation=False,
    )


def _make_task(
    task_id: str = "task-1",
    labels: list[str] | None = None,
    section_id: str | None = None,
    assignee_id: str | None = None,
    due_date: str | None = None,
) -> TaskLocal:
    return TaskLocal(
        id=task_id,
        content="Test task",
        description="",
        project_id="proj-1",
        section_id=section_id,
        parent_id=None,
        order_index=0,
        priority=1,
        due_date=due_date,
        due_string=None,
        due_is_recurring=None,
        due_lang=None,
        due_timezone=None,
        deadline_date=None,
        deadline_lang=None,
        duration_amount=None,
        duration_unit=None,
        assignee_id=assignee_id,
        assigner_id=None,
        creator_id=None,
        is_completed=False,
        completed_at=None,
        labels=labels or [],
        url="https://todoist.com/task/1",
        created_at="2026-01-01T00:00:00",
        updated_at="2026-01-01T00:00:00",
    )


# ---------------------------------------------------------------------------
# _passes_include_exclude
# ---------------------------------------------------------------------------


class TestPassesIncludeExclude:
    def test_empty_filter_always_passes(self) -> None:
        config = FilterConfig(include=[], exclude=[])
        assert _passes_include_exclude("anything", config) is True
        assert _passes_include_exclude(None, config) is True

    def test_include_list_requires_match(self) -> None:
        config = FilterConfig(include=["alice", "bob"], exclude=[])
        assert _passes_include_exclude("alice", config) is True
        assert _passes_include_exclude("carol", config) is False

    def test_include_list_rejects_none(self) -> None:
        config = FilterConfig(include=["alice"], exclude=[])
        assert _passes_include_exclude(None, config) is False

    def test_exclude_list_blocks_matches(self) -> None:
        config = FilterConfig(include=[], exclude=["blocked-user"])
        assert _passes_include_exclude("alice", config) is True
        assert _passes_include_exclude("blocked-user", config) is False

    def test_exclude_list_allows_none(self) -> None:
        config = FilterConfig(include=[], exclude=["blocked-user"])
        assert _passes_include_exclude(None, config) is True

    def test_include_and_exclude_combined(self) -> None:
        config = FilterConfig(include=["alice", "bob"], exclude=["bob"])
        # alice is in include but not exclude → passes
        assert _passes_include_exclude("alice", config) is True
        # bob is in include AND exclude → blocked by exclude
        assert _passes_include_exclude("bob", config) is False


# ---------------------------------------------------------------------------
# _passes_label_filter
# ---------------------------------------------------------------------------


class TestPassesLabelFilter:
    def test_empty_filter_always_passes(self) -> None:
        config = FilterConfig(include=[], exclude=[])
        assert _passes_label_filter(["work", "urgent"], config) is True
        assert _passes_label_filter([], config) is True

    def test_include_requires_at_least_one_match(self) -> None:
        config = FilterConfig(include=["urgent", "important"], exclude=[])
        assert _passes_label_filter(["urgent", "low-priority"], config) is True
        assert _passes_label_filter(["low-priority"], config) is False
        assert _passes_label_filter([], config) is False

    def test_exclude_blocks_any_match(self) -> None:
        config = FilterConfig(include=[], exclude=["personal"])
        assert _passes_label_filter(["work", "urgent"], config) is True
        assert _passes_label_filter(["work", "personal"], config) is False


# ---------------------------------------------------------------------------
# apply_pull_filters
# ---------------------------------------------------------------------------


class TestApplyPullFilters:
    def test_empty_filters_return_all_tasks(self) -> None:
        tasks = [_make_task("t1"), _make_task("t2"), _make_task("t3")]
        config = _make_pull_filters()
        result = apply_pull_filters(tasks, config)
        assert len(result) == 3

    def test_label_include_filter(self) -> None:
        task_with_label = _make_task("t1", labels=["urgent"])
        task_without_label = _make_task("t2", labels=["low-priority"])
        config = _make_pull_filters(label_include=["urgent"])
        result = apply_pull_filters([task_with_label, task_without_label], config)
        assert result == [task_with_label]

    def test_label_exclude_filter(self) -> None:
        task_excluded = _make_task("t1", labels=["personal"])
        task_kept = _make_task("t2", labels=["work"])
        config = _make_pull_filters(label_exclude=["personal"])
        result = apply_pull_filters([task_excluded, task_kept], config)
        assert result == [task_kept]

    def test_section_include_filter(self) -> None:
        task_in_section = _make_task("t1", section_id="section-a")
        task_wrong_section = _make_task("t2", section_id="section-b")
        task_no_section = _make_task("t3", section_id=None)
        config = _make_pull_filters(section_include=["section-a"])
        result = apply_pull_filters([task_in_section, task_wrong_section, task_no_section], config)
        assert result == [task_in_section]

    def test_section_exclude_filter(self) -> None:
        task_excluded = _make_task("t1", section_id="section-skip")
        task_kept = _make_task("t2", section_id="section-keep")
        task_no_section = _make_task("t3", section_id=None)
        config = _make_pull_filters(section_exclude=["section-skip"])
        result = apply_pull_filters([task_excluded, task_kept, task_no_section], config)
        assert result == [task_kept, task_no_section]

    def test_assignee_include_filter(self) -> None:
        task_mine = _make_task("t1", assignee_id="user-alice")
        task_others = _make_task("t2", assignee_id="user-bob")
        task_unassigned = _make_task("t3", assignee_id=None)
        config = _make_pull_filters(assignee_include=["user-alice"])
        result = apply_pull_filters([task_mine, task_others, task_unassigned], config)
        assert result == [task_mine]

    def test_has_due_date_true_keeps_only_tasks_with_due(self) -> None:
        task_with_due = _make_task("t1", due_date="2026-03-15")
        task_without_due = _make_task("t2", due_date=None)
        config = _make_pull_filters(has_due_date=True)
        result = apply_pull_filters([task_with_due, task_without_due], config)
        assert result == [task_with_due]

    def test_has_due_date_false_keeps_only_tasks_without_due(self) -> None:
        task_with_due = _make_task("t1", due_date="2026-03-15")
        task_without_due = _make_task("t2", due_date=None)
        config = _make_pull_filters(has_due_date=False)
        result = apply_pull_filters([task_with_due, task_without_due], config)
        assert result == [task_without_due]

    def test_has_due_date_none_keeps_all(self) -> None:
        tasks = [_make_task("t1", due_date="2026-03-15"), _make_task("t2", due_date=None)]
        config = _make_pull_filters(has_due_date=None)
        result = apply_pull_filters(tasks, config)
        assert len(result) == 2

    def test_multiple_filters_applied_conjunctively(self) -> None:
        """All filter conditions must be satisfied simultaneously."""
        task_passes_all = _make_task("t1", labels=["urgent"], section_id="s1", due_date="2026-03-01")
        task_fails_label = _make_task("t2", labels=[], section_id="s1", due_date="2026-03-01")
        task_fails_section = _make_task("t3", labels=["urgent"], section_id="s2", due_date="2026-03-01")
        task_fails_due = _make_task("t4", labels=["urgent"], section_id="s1", due_date=None)

        config = _make_pull_filters(
            label_include=["urgent"],
            section_include=["s1"],
            has_due_date=True,
        )
        result = apply_pull_filters([task_passes_all, task_fails_label, task_fails_section, task_fails_due], config)
        assert result == [task_passes_all]

    def test_empty_task_list_returns_empty(self) -> None:
        config = _make_pull_filters(label_include=["urgent"])
        result = apply_pull_filters([], config)
        assert result == []


# ---------------------------------------------------------------------------
# apply_push_filters
# ---------------------------------------------------------------------------


class TestApplyPushFilters:
    def test_empty_filters_return_all_tasks(self) -> None:
        tasks = [_make_task("t1"), _make_task("t2")]
        config = _make_push_filters()
        result = apply_push_filters(tasks, config)
        assert len(result) == 2

    def test_label_include_filter(self) -> None:
        task_with_label = _make_task("t1", labels=["claude-code"])
        task_without_label = _make_task("t2", labels=[])
        config = _make_push_filters(label_include=["claude-code"])
        result = apply_push_filters([task_with_label, task_without_label], config)
        assert result == [task_with_label]

    def test_label_exclude_filter(self) -> None:
        task_excluded = _make_task("t1", labels=["no-push"])
        task_kept = _make_task("t2", labels=["push-ok"])
        config = _make_push_filters(label_exclude=["no-push"])
        result = apply_push_filters([task_excluded, task_kept], config)
        assert result == [task_kept]

    def test_assignee_include_filter(self) -> None:
        task_mine = _make_task("t1", assignee_id="user-me")
        task_others = _make_task("t2", assignee_id="user-them")
        config = _make_push_filters(assignee_include=["user-me"])
        result = apply_push_filters([task_mine, task_others], config)
        assert result == [task_mine]
