"""Tests for the Research Tool data models."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from deep_thought.research.models import ResearchResult, SearchResult

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# TestSearchResult
# ---------------------------------------------------------------------------


class TestSearchResult:
    """Tests for SearchResult construction and field access."""

    def test_basic_construction(self) -> None:
        """Should construct a SearchResult from explicit field values."""
        source = SearchResult(
            title="MLX Docs",
            url="https://ml-explore.github.io/mlx/",
            snippet=None,
            date=None,
        )
        assert source.title == "MLX Docs"
        assert source.url == "https://ml-explore.github.io/mlx/"

    def test_all_fields_populated(self) -> None:
        """Should store all four fields when each is provided."""
        source = SearchResult(
            title="MLX Benchmarks",
            url="https://example.com/benchmarks",
            snippet="Detailed benchmark results.",
            date="2026-03-15",
        )
        assert source.title == "MLX Benchmarks"
        assert source.url == "https://example.com/benchmarks"
        assert source.snippet == "Detailed benchmark results."
        assert source.date == "2026-03-15"

    def test_optional_fields_none(self) -> None:
        """Should accept None for both snippet and date."""
        source = SearchResult(title="Title", url="https://example.com", snippet=None, date=None)
        assert source.snippet is None
        assert source.date is None


# ---------------------------------------------------------------------------
# TestResearchResult
# ---------------------------------------------------------------------------


class TestResearchResult:
    """Tests for ResearchResult construction and field access."""

    def test_basic_construction(self) -> None:
        """Should construct a ResearchResult from explicit field values."""
        result = ResearchResult(
            query="What is MLX?",
            mode="search",
            model="sonar",
            recency=None,
            domains=[],
            context_files=[],
            answer="MLX is Apple's ML framework.",
            search_results=[],
            related_questions=[],
            cost_usd=0.005,
            processed_date="2026-03-23T12:00:00Z",
        )
        assert result.query == "What is MLX?"
        assert result.mode == "search"
        assert result.model == "sonar"
        assert result.cost_usd == 0.005

    def test_default_empty_lists(self) -> None:
        """Should allow empty lists for domains, context_files, search_results, and related_questions."""
        result = ResearchResult(
            query="test",
            mode="search",
            model="sonar",
            recency=None,
            domains=[],
            context_files=[],
            answer="answer",
            search_results=[],
            related_questions=[],
            cost_usd=0.0,
            processed_date="2026-03-23T12:00:00Z",
        )
        assert result.domains == []
        assert result.context_files == []
        assert result.search_results == []
        assert result.related_questions == []


# ---------------------------------------------------------------------------
# TestFromApiResponse
# ---------------------------------------------------------------------------


class TestFromApiResponse:
    """Tests for ResearchResult.from_api_response."""

    def test_parses_search_response(self) -> None:
        """Should parse the search fixture and populate all fields correctly."""
        raw_response = json.loads((FIXTURES_DIR / "search_response.json").read_text(encoding="utf-8"))
        result = ResearchResult.from_api_response(
            response_data=raw_response,
            query="What is MLX?",
            mode="search",
            model="sonar",
            recency=None,
            domains=[],
            context_files=[],
        )

        assert result.query == "What is MLX?"
        assert result.mode == "search"
        assert result.model == "sonar"
        assert result.recency is None
        assert result.domains == []
        assert result.context_files == []

        assert "MLX" in result.answer

        assert len(result.search_results) == 2
        first_source = result.search_results[0]
        assert first_source.title == "MLX: Apple's New ML Framework"
        assert first_source.url == "https://ml-explore.github.io/mlx/"
        assert first_source.snippet == "MLX is an array framework for machine learning research on Apple silicon."
        assert first_source.date == "2026-03-15"

        assert len(result.related_questions) == 2
        assert result.related_questions[0] == "How does MLX compare to PyTorch on Apple Silicon?"

        assert result.cost_usd == 0.0065
        assert result.processed_date != ""

    def test_parses_deep_research_response(self) -> None:
        """Should parse the deep_research fixture including all four sources and three related questions."""
        raw_response = json.loads((FIXTURES_DIR / "deep_research_response.json").read_text(encoding="utf-8"))
        result = ResearchResult.from_api_response(
            response_data=raw_response,
            query="How does MLX compare to PyTorch?",
            mode="research",
            model="sonar-deep-research",
            recency="month",
            domains=["ml-explore.github.io"],
            context_files=[],
        )

        assert result.query == "How does MLX compare to PyTorch?"
        assert result.mode == "research"
        assert result.model == "sonar-deep-research"
        assert result.recency == "month"
        assert result.domains == ["ml-explore.github.io"]

        assert len(result.search_results) == 4
        assert len(result.related_questions) == 3
        assert result.cost_usd == 0.2498

    def test_handles_missing_search_results(self) -> None:
        """Should return an empty search_results list when the key is absent."""
        response_without_sources = {
            "choices": [{"message": {"content": "Some answer."}}],
            "usage": {"cost": {"total_cost": 0.001}},
        }
        result = ResearchResult.from_api_response(
            response_data=response_without_sources,
            query="test query",
            mode="search",
            model="sonar",
            recency=None,
            domains=[],
            context_files=[],
        )
        assert result.search_results == []

    def test_handles_missing_related_questions(self) -> None:
        """Should return an empty related_questions list when the key is absent."""
        response_without_questions = {
            "choices": [{"message": {"content": "Some answer."}}],
            "search_results": [],
            "usage": {"cost": {"total_cost": 0.001}},
        }
        result = ResearchResult.from_api_response(
            response_data=response_without_questions,
            query="test query",
            mode="search",
            model="sonar",
            recency=None,
            domains=[],
            context_files=[],
        )
        assert result.related_questions == []

    def test_handles_missing_cost(self) -> None:
        """Should default cost_usd to 0.0 when the usage.cost.total_cost key is absent."""
        response_without_cost = {
            "choices": [{"message": {"content": "Some answer."}}],
            "search_results": [],
        }
        result = ResearchResult.from_api_response(
            response_data=response_without_cost,
            query="test query",
            mode="search",
            model="sonar",
            recency=None,
            domains=[],
            context_files=[],
        )
        assert result.cost_usd == 0.0

    def test_raises_value_error_for_empty_answer(self) -> None:
        """Should raise ValueError when the API response contains no answer text."""
        empty_answer_response: dict[str, object] = {
            "choices": [{"message": {"content": ""}}],
            "search_results": [],
            "usage": {"cost": {"total_cost": 0.001}},
        }
        with pytest.raises(ValueError, match="empty answer"):
            ResearchResult.from_api_response(
                response_data=empty_answer_response,
                query="test query",
                mode="search",
                model="sonar",
                recency=None,
                domains=[],
                context_files=[],
            )

    def test_raises_value_error_for_missing_choices(self) -> None:
        """Should raise ValueError when the choices array is missing entirely."""
        missing_choices_response: dict[str, object] = {
            "search_results": [],
            "usage": {"cost": {"total_cost": 0.001}},
        }
        with pytest.raises(ValueError, match="empty answer"):
            ResearchResult.from_api_response(
                response_data=missing_choices_response,
                query="test query",
                mode="search",
                model="sonar",
                recency=None,
                domains=[],
                context_files=[],
            )


# ---------------------------------------------------------------------------
# TestSearchResultWarnings
# ---------------------------------------------------------------------------


class TestSearchResultWarnings:
    """Tests for SearchResult.from_api_dict warning behaviour."""

    def test_warns_on_empty_title(self, caplog: pytest.LogCaptureFixture) -> None:
        """Should log a warning when the API returns a source with an empty title."""
        with caplog.at_level(logging.WARNING, logger="deep_thought.research.models"):
            SearchResult.from_api_dict({"title": "", "url": "https://example.com"})
        assert any("empty title" in record.message for record in caplog.records)

    def test_warns_on_empty_url(self, caplog: pytest.LogCaptureFixture) -> None:
        """Should log a warning when the API returns a source with an empty URL."""
        with caplog.at_level(logging.WARNING, logger="deep_thought.research.models"):
            SearchResult.from_api_dict({"title": "Some Title", "url": ""})
        assert any("empty URL" in record.message for record in caplog.records)

    def test_warns_on_missing_title_key(self, caplog: pytest.LogCaptureFixture) -> None:
        """Should log a warning when the title key is absent from the source dict."""
        with caplog.at_level(logging.WARNING, logger="deep_thought.research.models"):
            SearchResult.from_api_dict({"url": "https://example.com"})
        assert any("empty title" in record.message for record in caplog.records)

    def test_no_warning_for_valid_source(self, caplog: pytest.LogCaptureFixture) -> None:
        """Should not log any warnings when both title and URL are populated."""
        with caplog.at_level(logging.WARNING, logger="deep_thought.research.models"):
            SearchResult.from_api_dict({"title": "Valid Title", "url": "https://example.com"})
        assert caplog.records == []
