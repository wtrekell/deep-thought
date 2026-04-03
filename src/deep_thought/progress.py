"""Standardized progress display for all deep-thought CLI tools.

Provides an orange spinner + purple progress bar that is used consistently
across every tool. Individual tools never configure colors or styles --
this module owns the standard appearance.

Progress renders to stderr so it does not interfere with stdout data.
When stderr is not a TTY (piped output), all functions degrade gracefully
with no ANSI codes emitted.
"""

from __future__ import annotations

import contextlib
import sys
from contextlib import contextmanager
from typing import TYPE_CHECKING

from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator


def _standard_columns() -> tuple[
    SpinnerColumn,
    TextColumn,
    BarColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
]:
    """Return the standard column layout: orange spinner + purple bar."""
    return (
        SpinnerColumn(spinner_name="dots", style="orange1"),
        TextColumn("[bold]{task.description}"),
        BarColumn(complete_style="purple", finished_style="bright_magenta", pulse_style="purple"),
        TaskProgressColumn(),
        TextColumn("({task.completed}/{task.total})"),
        TimeElapsedColumn(),
    )


def create_progress() -> Progress:
    """Return a configured Progress instance for manual control.

    Use this when you need direct control over task creation and updates
    (e.g., while-loops where the total is not known upfront). The caller
    is responsible for using it as a context manager and calling
    ``add_task()`` / ``advance()``.

    Returns:
        A Progress instance with the standard orange-spinner + purple-bar columns.
    """
    return Progress(
        *_standard_columns(),
        console=Console(stderr=True),
    )


def track_items[T](
    iterable: Iterable[T],
    *,
    description: str = "Processing",
    total: int | None = None,
) -> Iterator[T]:
    """Wrap an iterable with the standardized progress display.

    When stderr is not a TTY, yields items directly without any display.

    Args:
        iterable: The items to iterate over.
        description: Label shown next to the progress bar.
        total: Number of items. If None, attempts ``len()`` on the iterable.
            If that also fails, the bar pulses (indeterminate mode).

    Yields:
        Each item from the iterable, one at a time.
    """
    if not sys.stderr.isatty():
        yield from iterable
        return

    if total is None:
        with contextlib.suppress(TypeError):
            total = len(iterable)  # type: ignore[arg-type]

    progress = create_progress()
    with progress:
        task_id = progress.add_task(description, total=total)
        for item in iterable:
            yield item
            progress.advance(task_id)


@contextmanager
def spinner_context(description: str = "Working") -> Iterator[None]:
    """Display an indeterminate spinner for single long-running operations.

    Used where there is no iterable to track -- just a long-running call
    (e.g., a research API query). Shows the orange spinner + purple pulsing bar.

    When stderr is not a TTY, prints the description once and yields.

    Args:
        description: Label shown next to the spinner.

    Yields:
        None. The caller does its work inside the with-block.
    """
    if not sys.stderr.isatty():
        print(description, file=sys.stderr)
        yield
        return

    progress = create_progress()
    with progress:
        progress.add_task(description, total=None)
        yield
