"""Meta-based filter engine for the Todoist Tool.

Filters operate entirely on in-memory model objects — no database access.
Each filter function returns a subset of the input list based on the rules
defined in the YAML configuration (PullFilters or PushFilters).

Filter rule semantics:
- include list non-empty → item must match at least one entry
- exclude list non-empty → item must NOT match any entry
- Empty list → no constraint applied (all pass)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from deep_thought.todoist.config import FilterConfig, PullFilters, PushFilters
    from deep_thought.todoist.models import TaskLocal


def _passes_include_exclude(value: str | None, filter_config: FilterConfig) -> bool:
    """Check whether a single string value satisfies include/exclude constraints.

    Args:
        value: The value to check (e.g., an assignee_id). None never satisfies
               a non-empty include list and always fails when present in an exclude list.
        filter_config: A FilterConfig with include and exclude lists.

    Returns:
        True if the value is permitted by the filter, False otherwise.
    """
    # Item must match at least one entry in the include list (if non-empty)
    if filter_config.include and (value is None or value not in filter_config.include):
        return False

    # Item must not match any entry in the exclude list (if non-empty)
    return not (filter_config.exclude and (value is not None and value in filter_config.exclude))


def _passes_label_filter(task_labels: list[str], filter_config: FilterConfig) -> bool:
    """Check whether a task's labels satisfy include/exclude constraints.

    For labels:
    - include: task must have at least one label from the include list
    - exclude: task must have none of the labels in the exclude list

    Args:
        task_labels: The list of label names on the task.
        filter_config: A FilterConfig with include and exclude label lists.

    Returns:
        True if the task's labels satisfy the filter, False otherwise.
    """
    # Task must have at least one label from the include list (if non-empty)
    if filter_config.include and not any(label in filter_config.include for label in task_labels):
        return False

    # Task must not have any label from the exclude list (if non-empty)
    return not (filter_config.exclude and any(label in filter_config.exclude for label in task_labels))


def apply_pull_filters(tasks: list[TaskLocal], config: PullFilters) -> list[TaskLocal]:
    """Filter tasks based on pull filter rules from configuration.

    Rules applied in order:
    - labels.include: if non-empty, task must have at least one of these labels
    - labels.exclude: task must NOT have any of these labels
    - sections.include: if non-empty, task's section_id must be in this list
    - sections.exclude: task's section_id must NOT be in this list
    - assignee.include: if non-empty, task's assignee_id must be in this list
    - has_due_date: True = only tasks with due_date set, False = only without, None = all

    Args:
        tasks: List of TaskLocal objects fetched from the API.
        config: PullFilters from the loaded YAML configuration.

    Returns:
        Filtered list containing only tasks that pass all rules.
    """
    included_tasks: list[TaskLocal] = []

    for task in tasks:
        if not _passes_label_filter(task.labels, config.labels):
            continue

        # Section filter — section_id may be None for unsectioned tasks
        if config.sections.include and (task.section_id is None or task.section_id not in config.sections.include):
            continue

        if config.sections.exclude and (task.section_id is not None and task.section_id in config.sections.exclude):
            continue

        if not _passes_include_exclude(task.assignee_id, config.assignee):
            continue

        if config.has_due_date is True and task.due_date is None:
            continue

        if config.has_due_date is False and task.due_date is not None:
            continue

        included_tasks.append(task)

    return included_tasks


def apply_push_filters(tasks: list[TaskLocal], config: PushFilters) -> list[TaskLocal]:
    """Filter tasks based on push filter rules from configuration.

    Rules applied in order:
    - labels.include: if non-empty, task must have at least one of these labels
    - labels.exclude: task must NOT have any of these labels
    - assignee.include: if non-empty, task's assignee_id must be in this list

    Args:
        tasks: List of TaskLocal objects with locally modified state.
        config: PushFilters from the loaded YAML configuration.

    Returns:
        Filtered list containing only tasks that pass all rules.
    """
    included_tasks: list[TaskLocal] = []

    for task in tasks:
        if not _passes_label_filter(task.labels, config.labels):
            continue

        if not _passes_include_exclude(task.assignee_id, config.assignee):
            continue

        included_tasks.append(task)

    return included_tasks
