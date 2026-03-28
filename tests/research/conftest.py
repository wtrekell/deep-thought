"""Shared fixtures for Research Tool tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Response factory functions
# ---------------------------------------------------------------------------


def make_search_response(
    answer: str = "Default answer.",
    search_results: list[dict[str, Any]] | None = None,
    related_questions: list[str] | None = None,
    total_cost: float = 0.006,
) -> dict[str, Any]:
    """Return a dict mimicking a Perplexity synchronous chat-completion response.

    Builds a response structure matching the Perplexity API ``/chat/completions``
    format with choices, search_results, related_questions, and a full usage block.

    Args:
        answer: The synthesised answer text in the first choice's message content.
        search_results: List of source citation dicts. Defaults to two sample entries.
        related_questions: List of follow-up question strings. Defaults to two samples.
        total_cost: Total cost in USD placed in the nested usage.cost block.

    Returns:
        A dict matching the Perplexity API sync response format.
    """
    resolved_search_results: list[dict[str, Any]] = (
        search_results
        if search_results is not None
        else [
            {
                "title": "Sample Source One",
                "url": "https://example.com/source-one",
                "snippet": "A relevant excerpt from source one.",
                "date": "2026-03-20",
            },
            {
                "title": "Sample Source Two",
                "url": "https://example.com/source-two",
                "snippet": "A relevant excerpt from source two.",
                "date": "2026-03-18",
            },
        ]
    )

    resolved_related_questions: list[str] = (
        related_questions
        if related_questions is not None
        else [
            "What is the first related question?",
            "What is the second related question?",
        ]
    )

    return {
        "id": "chatcmpl-test123",
        "model": "sonar",
        "object": "chat.completion",
        "created": 1711180800,
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {
                    "role": "assistant",
                    "content": answer,
                },
            }
        ],
        "search_results": resolved_search_results,
        "related_questions": resolved_related_questions,
        "usage": {
            "prompt_tokens": 25,
            "completion_tokens": 50,
            "total_tokens": 75,
            "citation_tokens": 10,
            "num_search_queries": 1,
            "cost": {
                "input_tokens_cost": 0.001,
                "output_tokens_cost": 0.003,
                "reasoning_tokens_cost": None,
                "request_cost": 0.002,
                "citation_tokens_cost": 0.0001,
                "search_queries_cost": None,
                "total_cost": total_cost,
            },
        },
    }


def make_async_submit_response(job_id: str = "async_job_123") -> dict[str, Any]:
    """Return a dict mimicking the Perplexity async job submission response.

    The API immediately returns a job ID and a pending status upon submission
    to ``/v1/async/sonar``.

    Args:
        job_id: The job identifier string assigned by the API.

    Returns:
        A dict with ``id`` and ``status`` fields.
    """
    return {"id": job_id, "status": "pending"}


def make_async_poll_response(
    status: str = "COMPLETED",
    answer: str = "Deep answer.",
    search_results: list[dict[str, Any]] | None = None,
    related_questions: list[str] | None = None,
    total_cost: float = 0.24,
) -> dict[str, Any]:
    """Return a dict mimicking a Perplexity async job poll response.

    When status is "COMPLETED", returns the full response structure (same
    shape as the synchronous response) with an added top-level ``status``
    field. When status is anything else (e.g. "pending", "processing"),
    returns the minimal in-progress payload.

    Args:
        status: The job status string. Use "COMPLETED" for a finished job.
        answer: The synthesised answer text (only used when status is "COMPLETED").
        search_results: Source citation dicts (only used when status is "COMPLETED").
            Defaults to two sample entries.
        related_questions: Follow-up questions (only used when status is "COMPLETED").
            Defaults to two samples.
        total_cost: Total cost in USD (only used when status is "COMPLETED").

    Returns:
        A dict matching the Perplexity async poll response format.
    """
    if status != "COMPLETED":
        return {"id": "async_job_123", "status": status}

    resolved_search_results: list[dict[str, Any]] = (
        search_results
        if search_results is not None
        else [
            {
                "title": "Deep Research Source One",
                "url": "https://example.com/deep-one",
                "snippet": "A detailed excerpt from deep source one.",
                "date": "2026-03-21",
            },
            {
                "title": "Deep Research Source Two",
                "url": "https://example.com/deep-two",
                "snippet": "A detailed excerpt from deep source two.",
                "date": "2026-03-19",
            },
        ]
    )

    resolved_related_questions: list[str] = (
        related_questions
        if related_questions is not None
        else [
            "What is the first deep related question?",
            "What is the second deep related question?",
        ]
    )

    return {
        "id": "async_job_123",
        "status": "COMPLETED",
        "response": {
            "id": "async_job_123",
            "model": "sonar-deep-research",
            "object": "chat.completion",
            "created": 1711267200,
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {
                        "role": "assistant",
                        "content": answer,
                    },
                }
            ],
            "search_results": resolved_search_results,
            "related_questions": resolved_related_questions,
            "usage": {
                "prompt_tokens": 42,
                "completion_tokens": 500,
                "total_tokens": 542,
                "citation_tokens": 100,
                "num_search_queries": 8,
                "cost": {
                    "input_tokens_cost": 0.008,
                    "output_tokens_cost": 0.100,
                    "reasoning_tokens_cost": 0.018,
                    "request_cost": 0.005,
                    "citation_tokens_cost": 0.006,
                    "search_queries_cost": 0.016,
                    "total_cost": total_cost,
                },
            },
        },
    }


# ---------------------------------------------------------------------------
# Config fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def sample_config() -> Any:
    """Return a ResearchConfig loaded from the test fixture YAML file.

    Uses the test_config.yaml in the fixtures directory, which specifies
    a short retry count and test-specific env var names.
    """
    from deep_thought.research.config import ResearchConfig, load_config

    config: ResearchConfig = load_config(FIXTURES_DIR / "test_config.yaml")
    return config


# ---------------------------------------------------------------------------
# Mock httpx client fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_httpx_client() -> MagicMock:
    """Return a MagicMock standing in for an httpx.Client instance.

    The default configuration returns a successful search response with
    HTTP 200 when ``client.request()`` is called. Individual tests can
    override ``mock_httpx_client.request.return_value`` or use
    ``side_effect`` to simulate errors and retries.
    """
    client = MagicMock()

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.is_client_error = False
    mock_response.json.return_value = make_search_response()
    mock_response.raise_for_status.return_value = None

    client.request.return_value = mock_response
    return client


# ---------------------------------------------------------------------------
# Fixture-based access to raw fixture files
# ---------------------------------------------------------------------------


@pytest.fixture()
def search_response_fixture() -> dict[str, Any]:
    """Return the parsed contents of search_response.json from the fixtures directory."""
    fixture_path = FIXTURES_DIR / "search_response.json"
    raw_content = fixture_path.read_text(encoding="utf-8")
    result: dict[str, Any] = json.loads(raw_content)
    return result


@pytest.fixture()
def deep_research_response_fixture() -> dict[str, Any]:
    """Return the parsed contents of deep_research_response.json from the fixtures directory."""
    fixture_path = FIXTURES_DIR / "deep_research_response.json"
    raw_content = fixture_path.read_text(encoding="utf-8")
    result: dict[str, Any] = json.loads(raw_content)
    return result
