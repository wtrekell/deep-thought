"""Local dataclasses for the Research Tool.

SearchResult represents a single source citation returned by the Perplexity API.

ResearchResult captures the full output of a search or research query: the
synthesized answer, structured source citations, follow-up questions, cost, and
all parameters that produced it. It is constructed from a raw API response dict
via the ``from_api_response`` classmethod; YAML frontmatter serialization is
handled by ``output.py``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SearchResult
# ---------------------------------------------------------------------------


@dataclass
class SearchResult:
    """A single source citation from the Perplexity API search results array.

    Maps to one entry in the ``search_results`` list returned by the API.
    """

    title: str
    """Source page title."""

    url: str
    """Source URL."""

    snippet: str | None
    """Relevant excerpt from the source, if provided by the API."""

    date: str | None
    """Publication date of the source, if available."""

    @classmethod
    def from_api_dict(cls, source_dict: dict[str, Any]) -> SearchResult:
        """Construct a SearchResult from a single API search-result entry.

        Args:
            source_dict: One item from the ``search_results`` array in the
                Perplexity API response.

        Returns:
            A SearchResult with all fields populated from the dict.
        """
        title = source_dict.get("title", "")
        url = source_dict.get("url", "")

        if not title:
            logger.warning("SearchResult: API returned a source with an empty title.")
        if not url:
            logger.warning("SearchResult: API returned a source with an empty URL.")

        return cls(
            title=title,
            url=url,
            snippet=source_dict.get("snippet"),
            date=source_dict.get("date"),
        )


# ---------------------------------------------------------------------------
# ResearchResult
# ---------------------------------------------------------------------------


@dataclass
class ResearchResult:
    """Full output of a Perplexity search or research query.

    Captures the synthesized answer, structured source citations, follow-up
    questions, cost, and all parameters used to produce the result. The
    ``from_api_response`` classmethod constructs an instance from a raw API
    response; YAML frontmatter serialization is handled by ``output.py``.
    """

    query: str
    """The research question submitted to the API."""

    mode: str
    """Query mode — "search" for fast lookup, "research" for deeper analysis."""

    model: str
    """Perplexity model name used to produce the answer."""

    recency: str | None
    """Recency filter applied to the query (e.g. "month"), or None if unset."""

    domains: list[str]
    """Domain filters used to restrict or exclude sources. Empty if none."""

    context_files: list[str]
    """Paths to local context files included with the query. Empty if none."""

    answer: str
    """Synthesized answer text from the API."""

    search_results: list[SearchResult]
    """Structured source citations returned alongside the answer."""

    related_questions: list[str]
    """Follow-up questions suggested by the API."""

    cost_usd: float
    """Total cost of the API call in USD, from ``usage.cost.total_cost``."""

    processed_date: str
    """ISO 8601 UTC timestamp recording when this result was produced."""

    @classmethod
    def from_api_response(
        cls,
        response_data: dict[str, Any],
        query: str,
        mode: str,
        model: str,
        recency: str | None,
        domains: list[str],
        context_files: list[str],
    ) -> ResearchResult:
        """Parse a raw Perplexity API response into a ResearchResult.

        Extracts the synthesized answer from the first choice's message
        content, converts each search-result entry into a SearchResult
        dataclass, reads related follow-up questions, and pulls the total
        cost from the nested usage block. All missing keys are handled
        gracefully via ``.get()`` with safe defaults.

        Args:
            response_data: The full JSON response dict from the Perplexity API.
            query: The original research question that was submitted.
            mode: The query mode — "search" or "research".
            model: The Perplexity model name that was used.
            recency: The recency filter that was applied, or None.
            domains: Domain filters that were active for this query.
            context_files: Paths to any local context files that were included.

        Returns:
            A ResearchResult with all fields populated.
        """
        first_choice: dict[str, Any] = response_data.get("choices", [{}])[0]
        answer_text: str = first_choice.get("message", {}).get("content", "")

        if not answer_text:
            raise ValueError(
                "Perplexity API returned an empty answer. "
                "The response may be malformed or the model returned no content."
            )

        raw_search_results: list[dict[str, Any]] = response_data.get("search_results", [])
        parsed_search_results: list[SearchResult] = [
            SearchResult.from_api_dict(source_entry) for source_entry in raw_search_results
        ]

        related_questions: list[str] = response_data.get("related_questions", [])

        usage_block: dict[str, Any] = response_data.get("usage", {})
        cost_block: dict[str, Any] = usage_block.get("cost", {})
        total_cost: float = cost_block.get("total_cost", 0.0)

        processed_timestamp: str = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

        return cls(
            query=query,
            mode=mode,
            model=model,
            recency=recency,
            domains=domains,
            context_files=context_files,
            answer=answer_text,
            search_results=parsed_search_results,
            related_questions=related_questions,
            cost_usd=total_cost,
            processed_date=processed_timestamp,
        )


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class SearchCommandResult:
    """Summary of a completed search command invocation."""

    output_path: str = ""
    """Path where the markdown output file was written, or empty for stdout."""

    query: str = ""
    """The research question that was submitted."""

    source_count: int = 0
    """Number of source citations returned."""

    cost_usd: float = 0.0
    """Total API cost in USD."""


@dataclass
class ResearchCommandResult:
    """Summary of a completed research command invocation."""

    output_path: str = ""
    """Path where the markdown output file was written, or empty for stdout."""

    query: str = ""
    """The research question that was submitted."""

    source_count: int = 0
    """Number of source citations returned."""

    cost_usd: float = 0.0
    """Total API cost in USD."""

    context_file_count: int = field(default=0)
    """Number of context files included in the query."""
