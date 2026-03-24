"""Tests for the Research Tool data models."""

from __future__ import annotations

import json
from pathlib import Path

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


# ---------------------------------------------------------------------------
# TestToFrontmatterDict
# ---------------------------------------------------------------------------


class TestToFrontmatterDict:
    """Tests for ResearchResult.to_frontmatter_dict."""

    def _make_result(self, **overrides: object) -> ResearchResult:
        """Return a ResearchResult with sensible defaults, optionally overridden."""
        defaults: dict[str, object] = {
            "query": "What is MLX?",
            "mode": "search",
            "model": "sonar",
            "recency": None,
            "domains": [],
            "context_files": [],
            "answer": "MLX is Apple's ML framework.",
            "search_results": [],
            "related_questions": [],
            "cost_usd": 0.005,
            "processed_date": "2026-03-23T12:00:00Z",
        }
        defaults.update(overrides)
        return ResearchResult(**defaults)  # type: ignore[arg-type]

    def test_includes_required_fields(self) -> None:
        """Should always include tool, query, mode, model, cost_usd, and processed_date."""
        result = self._make_result()
        frontmatter_dict = result.to_frontmatter_dict()
        assert frontmatter_dict["tool"] == "research"
        assert frontmatter_dict["query"] == "What is MLX?"
        assert frontmatter_dict["mode"] == "search"
        assert frontmatter_dict["model"] == "sonar"
        assert frontmatter_dict["cost_usd"] == 0.005
        assert frontmatter_dict["processed_date"] == "2026-03-23T12:00:00Z"

    def test_omits_none_recency(self) -> None:
        """Should not include recency in the dict when it is None."""
        result = self._make_result(recency=None)
        frontmatter_dict = result.to_frontmatter_dict()
        assert "recency" not in frontmatter_dict

    def test_includes_recency_when_set(self) -> None:
        """Should include recency in the dict when it holds a non-None value."""
        result = self._make_result(recency="week")
        frontmatter_dict = result.to_frontmatter_dict()
        assert frontmatter_dict["recency"] == "week"

    def test_omits_empty_domains(self) -> None:
        """Should not include domains in the dict when the list is empty."""
        result = self._make_result(domains=[])
        frontmatter_dict = result.to_frontmatter_dict()
        assert "domains" not in frontmatter_dict

    def test_omits_empty_context_files(self) -> None:
        """Should not include context_files in the dict when the list is empty."""
        result = self._make_result(context_files=[])
        frontmatter_dict = result.to_frontmatter_dict()
        assert "context_files" not in frontmatter_dict
