"""Sync orchestrator for the Todoist Tool.

Runs pull then push sequentially, returning a combined result. This is the
implementation behind the `todoist sync` CLI command.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from deep_thought.todoist.pull import PullResult, pull
from deep_thought.todoist.push import PushResult, push

if TYPE_CHECKING:
    import sqlite3

    from deep_thought.todoist.client import TodoistClient
    from deep_thought.todoist.config import TodoistConfig


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class SyncResult:
    """Combined result from a full pull-then-push sync operation."""

    pull_result: PullResult
    push_result: PushResult


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def sync(
    client: TodoistClient,
    config: TodoistConfig,
    conn: sqlite3.Connection,
    *,
    dry_run: bool = False,
    verbose: bool = False,
    project_filter: str | None = None,
) -> SyncResult:
    """Run pull then push sequentially as a full bidirectional sync.

    Pull brings remote state into the local database. Push sends any locally
    modified tasks back to Todoist. Running them in this order ensures that
    conflict detection in push operates against a fresh baseline.

    Args:
        client: An initialized TodoistClient.
        config: The loaded TodoistConfig.
        conn: An open SQLite connection.
        dry_run: If True, no writes to DB, snapshot, or Todoist API occur.
        verbose: If True, print progress messages to stdout.
        project_filter: If provided, limit both pull and push to this project.

    Returns:
        A SyncResult containing both the PullResult and PushResult.
    """
    if verbose:
        print("Starting sync: pull phase...")

    pull_result = pull(
        client,
        config,
        conn,
        dry_run=dry_run,
        verbose=verbose,
        project_filter=project_filter,
    )

    if verbose:
        print("Starting sync: push phase...")

    push_result = push(
        client,
        config,
        conn,
        dry_run=dry_run,
        verbose=verbose,
        project_filter=project_filter,
    )

    if verbose:
        print("Sync complete.")

    return SyncResult(pull_result=pull_result, push_result=push_result)
