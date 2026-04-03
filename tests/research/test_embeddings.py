"""Tests for deep_thought.research.embeddings.

All tests mock ``deep_thought.embeddings.write_embedding`` at the module
boundary so no real MLX model or Qdrant connection is required.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from deep_thought.research.models import ResearchResult, SearchResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_research_result(
    mode: str = "search",
    recency: str | None = "month",
) -> ResearchResult:
    """Return a ResearchResult with realistic test values."""
    return ResearchResult(
        query="What are the best practices for Python async?",
        mode=mode,
        model="sonar",
        recency=recency,
        domains=[],
        context_files=[],
        answer="Here is a detailed answer about Python async best practices.",
        search_results=[
            SearchResult(
                title="Python Async Guide",
                url="https://docs.python.org/async",
                snippet="An in-depth look at asyncio.",
                date="2026-03-01",
            ),
            SearchResult(
                title="Async Patterns",
                url="https://example.com/async",
                snippet="Common async patterns.",
                date="2026-02-15",
            ),
        ],
        related_questions=["How does asyncio work?"],
        cost_usd=0.006,
        processed_date="2026-04-02T12:00:00Z",
    )


def _call_write_embedding(
    result: ResearchResult,
    output_path: str = "/data/research/export/260402-python-async.md",
    content: str = "Query: What are the best practices?\n\nDetailed answer.",
) -> Any:
    """Invoke the module under test with a mock model and client, returning the mock."""
    mock_model = MagicMock()
    mock_client = MagicMock()

    with patch("deep_thought.embeddings.write_embedding") as mock_shared_write:
        from deep_thought.research.embeddings import write_embedding

        write_embedding(
            content=content,
            result=result,
            output_path=output_path,
            model=mock_model,
            qdrant_client=mock_client,
        )
        return mock_shared_write


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestWriteEmbeddingCallsSharedFunction:
    def test_write_embedding_calls_shared_write_embedding(self) -> None:
        """The research write_embedding must call the shared write_embedding exactly once."""
        result = _make_research_result()
        mock_shared = _call_write_embedding(result)
        mock_shared.assert_called_once()

    def test_write_embedding_payload_source_tool(self) -> None:
        """The payload passed to the shared function must have source_tool='research'."""
        result = _make_research_result()
        mock_shared = _call_write_embedding(result)
        call_kwargs = mock_shared.call_args.kwargs
        assert call_kwargs["payload"]["source_tool"] == "research"

    def test_write_embedding_payload_required_fields(self) -> None:
        """The payload must contain the four fields required by every tool."""
        result = _make_research_result()
        mock_shared = _call_write_embedding(result)
        payload = mock_shared.call_args.kwargs["payload"]
        assert "source_tool" in payload
        assert "source_type" in payload
        assert "rule_name" in payload
        assert "collected_date" in payload

    def test_write_embedding_output_path_passed(self) -> None:
        """The output_path kwarg must match the path provided to write_embedding."""
        expected_output_path = "/data/research/export/260402-specific-query.md"
        result = _make_research_result()
        mock_shared = _call_write_embedding(result, output_path=expected_output_path)
        call_kwargs = mock_shared.call_args.kwargs
        assert call_kwargs["output_path"] == expected_output_path

    def test_source_type_research_deep(self) -> None:
        """Mode 'research' must map to source_type='research_deep'."""
        result = _make_research_result(mode="research")
        mock_shared = _call_write_embedding(result)
        payload = mock_shared.call_args.kwargs["payload"]
        assert payload["source_type"] == "research_deep"

    def test_source_type_research_search(self) -> None:
        """Mode 'search' must map to source_type='research_search'."""
        result = _make_research_result(mode="search")
        mock_shared = _call_write_embedding(result)
        payload = mock_shared.call_args.kwargs["payload"]
        assert payload["source_type"] == "research_search"

    def test_rule_name_is_empty_string(self) -> None:
        """Research has no rule system, so rule_name must always be empty string."""
        result = _make_research_result()
        mock_shared = _call_write_embedding(result)
        payload = mock_shared.call_args.kwargs["payload"]
        assert payload["rule_name"] == ""

    def test_recency_included_when_present(self) -> None:
        """When recency is set, the payload must include the recency field."""
        result = _make_research_result(recency="week")
        mock_shared = _call_write_embedding(result)
        payload = mock_shared.call_args.kwargs["payload"]
        assert "recency" in payload
        assert payload["recency"] == "week"

    def test_recency_omitted_when_none(self) -> None:
        """When result.recency is None, the payload must not contain the 'recency' key."""
        result = _make_research_result(recency=None)
        mock_shared = _call_write_embedding(result)
        payload = mock_shared.call_args.kwargs["payload"]
        assert "recency" not in payload

    def test_collected_date_from_processed_date(self) -> None:
        """collected_date must be taken directly from result.processed_date."""
        result = _make_research_result()
        mock_shared = _call_write_embedding(result)
        payload = mock_shared.call_args.kwargs["payload"]
        assert payload["collected_date"] == result.processed_date

    def test_source_count_matches_search_results_length(self) -> None:
        """source_count must equal the number of search results in the result."""
        result = _make_research_result()
        mock_shared = _call_write_embedding(result)
        payload = mock_shared.call_args.kwargs["payload"]
        assert payload["source_count"] == len(result.search_results)

    def test_query_in_payload(self) -> None:
        """The query field must be forwarded to the payload."""
        result = _make_research_result()
        mock_shared = _call_write_embedding(result)
        payload = mock_shared.call_args.kwargs["payload"]
        assert payload["query"] == result.query

    def test_content_passed_through(self) -> None:
        """The content string must be forwarded unchanged to the shared function."""
        result = _make_research_result()
        expected_content = "Query: Test\n\nUnique answer text for this assertion."
        mock_shared = _call_write_embedding(result, content=expected_content)
        assert mock_shared.call_args.kwargs["content"] == expected_content
