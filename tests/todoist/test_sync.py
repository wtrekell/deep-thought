"""Tests for the Todoist sync orchestrator (deep_thought.todoist.sync).

Verifies that sync() calls pull then push in the correct order and that a
pull failure prevents push from running.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from deep_thought.todoist.pull import PullResult
from deep_thought.todoist.push import PushResult
from deep_thought.todoist.sync import SyncResult, sync

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_client() -> MagicMock:
    """Return a minimal mock TodoistClient."""
    return MagicMock()


def _make_mock_config() -> MagicMock:
    """Return a minimal mock TodoistConfig."""
    return MagicMock()


def _make_mock_conn() -> MagicMock:
    """Return a minimal mock sqlite3.Connection."""
    return MagicMock()


def _default_pull_result() -> PullResult:
    """Return a PullResult with all-zero counters for use as a mock return value."""
    return PullResult(
        projects_synced=0,
        sections_synced=0,
        tasks_synced=0,
        tasks_filtered_out=0,
        comments_synced=0,
        labels_synced=0,
        snapshot_path=None,
    )


def _default_push_result() -> PushResult:
    """Return a PushResult with all-zero counters for use as a mock return value."""
    return PushResult(tasks_pushed=0, tasks_filtered_out=0, tasks_failed=0, errors=[])


# ---------------------------------------------------------------------------
# TestSync
# ---------------------------------------------------------------------------


class TestSync:
    """Tests for sync()."""

    def test_pull_called_before_push(self) -> None:
        """sync() must call pull first, then push, in that order."""
        call_order: list[str] = []

        def recording_pull(*args: object, **kwargs: object) -> PullResult:
            call_order.append("pull")
            return _default_pull_result()

        def recording_push(*args: object, **kwargs: object) -> PushResult:
            call_order.append("push")
            return _default_push_result()

        with (
            patch("deep_thought.todoist.sync.pull", side_effect=recording_pull),
            patch("deep_thought.todoist.sync.push", side_effect=recording_push),
        ):
            result = sync(
                client=_make_mock_client(),
                config=_make_mock_config(),
                conn=_make_mock_conn(),
            )

        assert call_order == ["pull", "push"]
        assert isinstance(result, SyncResult)

    def test_pull_called_once_and_push_called_once(self) -> None:
        """sync() must call pull exactly once and push exactly once."""
        mock_pull = MagicMock(return_value=_default_pull_result())
        mock_push = MagicMock(return_value=_default_push_result())

        with (
            patch("deep_thought.todoist.sync.pull", mock_pull),
            patch("deep_thought.todoist.sync.push", mock_push),
        ):
            sync(
                client=_make_mock_client(),
                config=_make_mock_config(),
                conn=_make_mock_conn(),
            )

        mock_pull.assert_called_once()
        mock_push.assert_called_once()

    def test_returns_sync_result_containing_both_results(self) -> None:
        """sync() must return a SyncResult that wraps both the pull and push results."""
        expected_pull_result = PullResult(
            projects_synced=3,
            sections_synced=2,
            tasks_synced=10,
            tasks_filtered_out=1,
            comments_synced=5,
            labels_synced=2,
            snapshot_path="/tmp/snapshot.json",
        )
        expected_push_result = PushResult(tasks_pushed=2, tasks_filtered_out=0, tasks_failed=1, errors=[])

        with (
            patch("deep_thought.todoist.sync.pull", return_value=expected_pull_result),
            patch("deep_thought.todoist.sync.push", return_value=expected_push_result),
        ):
            result = sync(
                client=_make_mock_client(),
                config=_make_mock_config(),
                conn=_make_mock_conn(),
            )

        assert result.pull_result is expected_pull_result
        assert result.push_result is expected_push_result

    def test_pull_error_prevents_push(self) -> None:
        """If pull raises an exception, push must not be called."""
        mock_push = MagicMock(return_value=_default_push_result())

        with (
            patch("deep_thought.todoist.sync.pull", side_effect=RuntimeError("API timeout")),
            patch("deep_thought.todoist.sync.push", mock_push),
            pytest.raises(RuntimeError, match="API timeout"),
        ):
            sync(
                client=_make_mock_client(),
                config=_make_mock_config(),
                conn=_make_mock_conn(),
            )

        mock_push.assert_not_called()

    def test_dry_run_forwarded_to_both_phases(self) -> None:
        """dry_run=True must be passed through to both pull and push."""
        mock_pull = MagicMock(return_value=_default_pull_result())
        mock_push = MagicMock(return_value=_default_push_result())

        with (
            patch("deep_thought.todoist.sync.pull", mock_pull),
            patch("deep_thought.todoist.sync.push", mock_push),
        ):
            sync(
                client=_make_mock_client(),
                config=_make_mock_config(),
                conn=_make_mock_conn(),
                dry_run=True,
            )

        pull_kwargs = mock_pull.call_args.kwargs
        push_kwargs = mock_push.call_args.kwargs
        assert pull_kwargs["dry_run"] is True
        assert push_kwargs["dry_run"] is True

    def test_project_filter_forwarded_to_both_phases(self) -> None:
        """project_filter must be passed through to both pull and push when set."""
        mock_pull = MagicMock(return_value=_default_pull_result())
        mock_push = MagicMock(return_value=_default_push_result())

        with (
            patch("deep_thought.todoist.sync.pull", mock_pull),
            patch("deep_thought.todoist.sync.push", mock_push),
        ):
            sync(
                client=_make_mock_client(),
                config=_make_mock_config(),
                conn=_make_mock_conn(),
                project_filter="Work",
            )

        pull_kwargs = mock_pull.call_args.kwargs
        push_kwargs = mock_push.call_args.kwargs
        assert pull_kwargs["project_filter"] == "Work"
        assert push_kwargs["project_filter"] == "Work"
