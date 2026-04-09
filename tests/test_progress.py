"""Tests for the shared progress display module."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

if TYPE_CHECKING:
    from collections.abc import Iterator

from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)

from deep_thought.progress import create_progress, spinner_context, track_items

# ---------------------------------------------------------------------------
# track_items
# ---------------------------------------------------------------------------


class TestTrackItems:
    """Tests for track_items."""

    def test_yields_all_items(self) -> None:
        """Every item from the input iterable should be yielded."""
        items = [1, 2, 3, 4, 5]
        result = list(track_items(items, description="Testing"))
        assert result == [1, 2, 3, 4, 5]

    def test_preserves_item_order(self) -> None:
        """Items should be yielded in their original order."""
        items = ["a", "b", "c"]
        result = list(track_items(items, description="Order test"))
        assert result == ["a", "b", "c"]

    def test_handles_empty_iterable(self) -> None:
        """An empty iterable should produce no items and no errors."""
        result = list(track_items([], description="Empty"))
        assert result == []

    def test_non_tty_yields_without_display(self) -> None:
        """When stderr is not a TTY, items should be yielded directly."""
        with patch("deep_thought.progress.sys.stderr") as mock_stderr:
            mock_stderr.isatty.return_value = False
            result = list(track_items([10, 20, 30], description="Non-TTY"))
        assert result == [10, 20, 30]

    def test_generator_input(self) -> None:
        """A generator (no len()) should work in indeterminate mode."""

        def gen() -> Iterator[int]:
            yield from range(3)

        result = list(track_items(gen(), description="Generator"))
        assert result == [0, 1, 2]

    def test_explicit_total_overrides_len(self) -> None:
        """Passing total= explicitly should override automatic len() inference."""
        items = [1, 2, 3]
        result = list(track_items(items, description="Override", total=10))
        assert result == [1, 2, 3]

    def test_single_item(self) -> None:
        """A single-item iterable should work correctly."""
        result = list(track_items(["only"], description="Single"))
        assert result == ["only"]


# ---------------------------------------------------------------------------
# spinner_context
# ---------------------------------------------------------------------------


class TestSpinnerContext:
    """Tests for spinner_context."""

    def test_yields_control(self) -> None:
        """The context manager should yield and allow the caller to execute."""
        executed = False
        with spinner_context("Working"):
            executed = True
        assert executed

    def test_non_tty_prints_description(self) -> None:
        """When stderr is not a TTY, should print description and yield."""
        with patch("deep_thought.progress.sys.stderr") as mock_stderr:
            mock_stderr.isatty.return_value = False
            mock_stderr.write = lambda x: None  # Absorb print output
            executed = False
            with spinner_context("Searching"):
                executed = True
        assert executed


# ---------------------------------------------------------------------------
# create_progress
# ---------------------------------------------------------------------------


class TestCreateProgress:
    """Tests for create_progress."""

    def test_returns_progress_instance(self) -> None:
        """Should return a rich Progress object."""
        progress = create_progress()
        assert isinstance(progress, Progress)

    def test_has_spinner_column(self) -> None:
        """The Progress should include a SpinnerColumn."""
        progress = create_progress()
        column_types = [type(col) for col in progress.columns]
        assert SpinnerColumn in column_types

    def test_has_bar_column(self) -> None:
        """The Progress should include a BarColumn."""
        progress = create_progress()
        column_types = [type(col) for col in progress.columns]
        assert BarColumn in column_types

    def test_has_task_progress_column(self) -> None:
        """The Progress should include a TaskProgressColumn."""
        progress = create_progress()
        column_types = [type(col) for col in progress.columns]
        assert TaskProgressColumn in column_types

    def test_has_time_elapsed_column(self) -> None:
        """The Progress should include a TimeElapsedColumn."""
        progress = create_progress()
        column_types = [type(col) for col in progress.columns]
        assert TimeElapsedColumn in column_types

    def test_column_order(self) -> None:
        """Columns should be in standard order: spinner, text, bar, progress, text, time."""
        progress = create_progress()
        column_types = [type(col) for col in progress.columns]
        assert column_types == [
            SpinnerColumn,
            TextColumn,
            BarColumn,
            TaskProgressColumn,
            TextColumn,
            TimeElapsedColumn,
        ]

    def test_bar_column_uses_purple(self) -> None:
        """The BarColumn should use purple styling."""
        progress = create_progress()
        bar_columns = [col for col in progress.columns if isinstance(col, BarColumn)]
        assert len(bar_columns) == 1
        bar_col = bar_columns[0]
        assert bar_col.complete_style == "purple"

    def test_spinner_column_uses_orange(self) -> None:
        """The SpinnerColumn should use orange1 styling."""
        progress = create_progress()
        spinner_columns = [col for col in progress.columns if isinstance(col, SpinnerColumn)]
        assert len(spinner_columns) == 1
        spinner_col = spinner_columns[0]
        assert spinner_col.spinner.style == "orange1"
