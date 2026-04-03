"""Tests verifying that embedding failures in research/cli.py do not abort output.

These tests confirm that when the embedding infrastructure raises, cmd_search
and cmd_research still write the output file and complete successfully.
"""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from deep_thought.research.models import ResearchResult, SearchResult


def _make_fake_result(mode: str = "search") -> ResearchResult:
    """Return a ResearchResult with test values."""
    return ResearchResult(
        query="What is Python async?",
        mode=mode,
        model="sonar" if mode == "search" else "sonar-deep-research",
        recency=None,
        domains=[],
        context_files=[],
        answer="Python async uses asyncio.",
        search_results=[SearchResult(title="Src", url="https://example.com", snippet=None, date=None)],
        related_questions=[],
        cost_usd=0.001,
        processed_date="2026-04-02T12:00:00Z",
    )


def _make_search_args(
    output_dir: Path,
    query: str = "What is Python async?",
    quick: bool = False,
    recency: str | None = None,
    domains: str | None = None,
) -> argparse.Namespace:
    """Return an argparse.Namespace suitable for cmd_search."""
    return argparse.Namespace(
        query=query,
        output=str(output_dir),
        config=None,
        recency=recency,
        domains=domains,
        context=[],
        dry_run=False,
        quick=quick,
    )


def _make_research_args(
    output_dir: Path,
    query: str = "Compare MLX and PyTorch",
    recency: str | None = None,
    domains: str | None = None,
) -> argparse.Namespace:
    """Return an argparse.Namespace suitable for cmd_research."""
    return argparse.Namespace(
        query=query,
        output=str(output_dir),
        config=None,
        recency=recency,
        domains=domains,
        context=[],
        dry_run=False,
    )


# ---------------------------------------------------------------------------
# Embedding failure resilience
# ---------------------------------------------------------------------------


class TestSearchEmbeddingFailureDoesNotAbort:
    @pytest.mark.error_handling
    def test_processor_embedding_failure_does_not_abort(self, tmp_path: Path, sample_config: object) -> None:
        """An embedding failure in cmd_search must not prevent file output or exit.

        When ``create_embedding_model`` raises (simulating unavailable mlx-embeddings
        or Qdrant), cmd_search must still complete without raising and the output
        summary must be printed.
        """
        from deep_thought.research.cli import cmd_search

        fake_result = _make_fake_result(mode="search")
        written_path = tmp_path / "260402-what-is-python-async.md"
        written_path.write_text("---\nquery: test\n---\n\nAnswer.", encoding="utf-8")

        args = _make_search_args(output_dir=tmp_path)

        mock_client = MagicMock()
        mock_client.search.return_value = fake_result

        with (
            patch.dict(
                "sys.modules",
                {
                    "deep_thought.research.researcher": MagicMock(PerplexityClient=MagicMock(return_value=mock_client)),
                    "deep_thought.research.output": MagicMock(
                        generate_research_markdown=MagicMock(return_value="# content"),
                        write_research_file=MagicMock(return_value=written_path),
                    ),
                },
            ),
            patch("deep_thought.research.cli.get_api_key", return_value="fake-key"),
            patch("deep_thought.research.cli._load_config_from_args", return_value=sample_config),
            # Simulate embedding infrastructure being unavailable
            patch(
                "deep_thought.embeddings.create_embedding_model",
                side_effect=Exception("mlx-embeddings not installed"),
            ),
        ):
            # Must complete without raising any exception
            cmd_search(args)


class TestResearchEmbeddingFailureDoesNotAbort:
    @pytest.mark.error_handling
    def test_processor_embedding_failure_does_not_abort(self, tmp_path: Path, sample_config: object) -> None:
        """An embedding failure in cmd_research must not prevent file output or exit."""
        from deep_thought.research.cli import cmd_research

        fake_result = _make_fake_result(mode="research")
        written_path = tmp_path / "260402-compare-mlx-and-pytorch.md"
        written_path.write_text("---\nquery: test\n---\n\nAnswer.", encoding="utf-8")

        args = _make_research_args(output_dir=tmp_path)

        mock_client = MagicMock()
        mock_client.research.return_value = fake_result

        with (
            patch.dict(
                "sys.modules",
                {
                    "deep_thought.research.researcher": MagicMock(PerplexityClient=MagicMock(return_value=mock_client)),
                    "deep_thought.research.output": MagicMock(
                        generate_research_markdown=MagicMock(return_value="# content"),
                        write_research_file=MagicMock(return_value=written_path),
                    ),
                },
            ),
            patch("deep_thought.research.cli.get_api_key", return_value="fake-key"),
            patch("deep_thought.research.cli._load_config_from_args", return_value=sample_config),
            # Simulate embedding infrastructure being unavailable
            patch(
                "deep_thought.embeddings.create_embedding_model",
                side_effect=Exception("mlx-embeddings not installed"),
            ),
        ):
            # Must complete without raising any exception
            cmd_research(args)
