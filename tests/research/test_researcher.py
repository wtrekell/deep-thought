"""Tests for the Research Tool PerplexityClient (researcher.py)."""

from __future__ import annotations

from pathlib import Path  # noqa: TC003
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, patch

import httpx
import pytest

from deep_thought.research.researcher import PerplexityClient

if TYPE_CHECKING:
    from deep_thought.research.config import ResearchConfig

from tests.research.conftest import (
    make_async_poll_response,
    make_async_submit_response,
    make_search_response,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_client(sample_config: ResearchConfig) -> PerplexityClient:
    """Construct a PerplexityClient with a test API key and the given config."""
    return PerplexityClient(api_key="test-api-key", config=sample_config)


def _make_mock_response(status_code: int, body: dict[str, Any], headers: dict[str, str] | None = None) -> MagicMock:
    """Return a MagicMock standing in for an httpx.Response.

    Args:
        status_code: The HTTP status code the mock should report.
        body: The dict the mock's ``.json()`` method should return.
        headers: Optional response headers dict (e.g. for Retry-After).

    Returns:
        A configured MagicMock httpx.Response.
    """
    mock_response = MagicMock()
    mock_response.status_code = status_code
    mock_response.is_client_error = 400 <= status_code < 500
    mock_response.json.return_value = body
    mock_response.headers = headers or {}
    mock_response.raise_for_status.side_effect = (
        httpx.HTTPStatusError(
            f"HTTP {status_code}",
            request=MagicMock(),
            response=MagicMock(status_code=status_code),
        )
        if status_code >= 400
        else None
    )
    return mock_response


# ---------------------------------------------------------------------------
# TestBuildMessages
# ---------------------------------------------------------------------------


class TestBuildMessages:
    """Tests for PerplexityClient._build_messages."""

    def test_query_only_no_context(self, sample_config: ResearchConfig) -> None:
        """Should return a single user message containing only the query when no context files are given."""
        client = _make_client(sample_config)
        messages = client._build_messages("What is Python?", [])

        assert messages == [{"role": "user", "content": "What is Python?"}]

    def test_single_context_file(self, sample_config: ResearchConfig, tmp_path: Path) -> None:
        """Should wrap file contents in XML tags and append a query tag when one context file is given."""
        context_file = tmp_path / "prior.md"
        context_file.write_text("Prior research content.", encoding="utf-8")

        client = _make_client(sample_config)
        messages = client._build_messages("Follow-up question?", [str(context_file)])

        assert len(messages) == 1
        content = messages[0]["content"]
        assert messages[0]["role"] == "user"
        assert "<prior_research>" in content
        assert f'<file path="{context_file}">' in content
        assert "Prior research content." in content
        assert "</file>" in content
        assert "</prior_research>" in content
        assert "<query>Follow-up question?</query>" in content

    def test_multiple_context_files(self, sample_config: ResearchConfig, tmp_path: Path) -> None:
        """Should include all provided context files in the XML output."""
        file_one = tmp_path / "first.md"
        file_one.write_text("First prior research.", encoding="utf-8")
        file_two = tmp_path / "second.md"
        file_two.write_text("Second prior research.", encoding="utf-8")

        client = _make_client(sample_config)
        messages = client._build_messages("Combined question?", [str(file_one), str(file_two)])

        content = messages[0]["content"]
        assert f'<file path="{file_one}">' in content
        assert "First prior research." in content
        assert f'<file path="{file_two}">' in content
        assert "Second prior research." in content

    @pytest.mark.error_handling
    def test_missing_context_file_raises(self, sample_config: ResearchConfig) -> None:
        """Should raise FileNotFoundError when a context file path does not exist."""
        client = _make_client(sample_config)
        nonexistent_path = "/tmp/does_not_exist_at_all.md"

        with pytest.raises(FileNotFoundError):
            client._build_messages("Any query?", [nonexistent_path])


# ---------------------------------------------------------------------------
# TestBuildRequestBody
# ---------------------------------------------------------------------------


class TestBuildRequestBody:
    """Tests for PerplexityClient._build_request_body."""

    def test_basic_request(self, sample_config: ResearchConfig) -> None:
        """Should always include model, messages, and return_related_questions keys."""
        client = _make_client(sample_config)
        sample_messages = [{"role": "user", "content": "A question."}]
        body = client._build_request_body("sonar", sample_messages, None, [])

        assert body["model"] == "sonar"
        assert body["messages"] == sample_messages
        assert body["return_related_questions"] is True

    def test_includes_recency_when_set(self, sample_config: ResearchConfig) -> None:
        """Should include search_recency_filter in the body when recency is not None."""
        client = _make_client(sample_config)
        body = client._build_request_body("sonar", [], "week", [])

        assert "search_recency_filter" in body
        assert body["search_recency_filter"] == "week"

    def test_omits_recency_when_none(self, sample_config: ResearchConfig) -> None:
        """Should NOT include search_recency_filter when recency is None."""
        client = _make_client(sample_config)
        body = client._build_request_body("sonar", [], None, [])

        assert "search_recency_filter" not in body

    def test_includes_domains_when_set(self, sample_config: ResearchConfig) -> None:
        """Should include search_domain_filter in the body when domains list is non-empty."""
        client = _make_client(sample_config)
        allowed_domains = ["example.com", "trusted.org"]
        body = client._build_request_body("sonar", [], None, allowed_domains)

        assert "search_domain_filter" in body
        assert body["search_domain_filter"] == allowed_domains

    def test_omits_domains_when_empty(self, sample_config: ResearchConfig) -> None:
        """Should NOT include search_domain_filter when domains list is empty."""
        client = _make_client(sample_config)
        body = client._build_request_body("sonar", [], None, [])

        assert "search_domain_filter" not in body

    def test_recency_alias_3_months_maps_to_year(self, sample_config: ResearchConfig) -> None:
        """'3 months' alias must be translated to 'year' before the API call."""
        client = _make_client(sample_config)
        body = client._build_request_body("sonar", [], "3 months", [])

        assert body["search_recency_filter"] == "year"

    def test_recency_alias_6_months_maps_to_year(self, sample_config: ResearchConfig) -> None:
        """'6 months' alias must be translated to 'year' before the API call."""
        client = _make_client(sample_config)
        body = client._build_request_body("sonar", [], "6 months", [])

        assert body["search_recency_filter"] == "year"

    def test_native_recency_values_pass_through_unchanged(self, sample_config: ResearchConfig) -> None:
        """Native Perplexity values must not be remapped."""
        client = _make_client(sample_config)
        for native in ("hour", "day", "week", "month", "year"):
            body = client._build_request_body("sonar", [], native, [])
            got = body["search_recency_filter"]
            assert got == native, f"Expected '{native}' unchanged, got '{got}'"


# ---------------------------------------------------------------------------
# TestSearch
# ---------------------------------------------------------------------------


class TestSearch:
    """Tests for PerplexityClient.search."""

    def test_successful_search(self, sample_config: ResearchConfig) -> None:
        """Should return a ResearchResult populated from the mock API response."""
        from deep_thought.research.models import ResearchResult

        search_response_body = make_search_response(answer="Python is a programming language.")
        mock_response = _make_mock_response(200, search_response_body)

        client = _make_client(sample_config)
        client._client = MagicMock()
        client._client.request.return_value = mock_response

        result = client.search("What is Python?")

        assert isinstance(result, ResearchResult)
        assert result.query == "What is Python?"
        assert result.mode == "search"
        assert result.answer == "Python is a programming language."
        assert len(result.search_results) == 2
        assert result.cost_usd == 0.006

    def test_search_calls_sync_endpoint(self, sample_config: ResearchConfig) -> None:
        """Should POST to the /chat/completions synchronous endpoint."""
        mock_response = _make_mock_response(200, make_search_response())
        client = _make_client(sample_config)
        client._client = MagicMock()
        client._client.request.return_value = mock_response

        client.search("Test query")

        call_args = client._client.request.call_args
        method_arg, endpoint_arg = call_args[0]
        assert method_arg == "POST"
        assert endpoint_arg == "/chat/completions"

    def test_search_uses_correct_model(self, sample_config: ResearchConfig) -> None:
        """Should include the search_model from config in the request body."""
        mock_response = _make_mock_response(200, make_search_response())
        client = _make_client(sample_config)
        client._client = MagicMock()
        client._client.request.return_value = mock_response

        client.search("Test query")

        call_kwargs = client._client.request.call_args[1]
        request_body = call_kwargs["json"]
        assert request_body["model"] == sample_config.search_model


# ---------------------------------------------------------------------------
# TestResearch
# ---------------------------------------------------------------------------


class TestResearch:
    """Tests for PerplexityClient.research."""

    def test_successful_research(self, sample_config: ResearchConfig) -> None:
        """Should return a ResearchResult from the completed async job response."""
        from deep_thought.research.models import ResearchResult

        submit_body = make_async_submit_response(job_id="job_abc")
        completed_body = make_async_poll_response(status="COMPLETED", answer="Deep answer here.")

        mock_submit_response = _make_mock_response(200, submit_body)
        mock_poll_response = _make_mock_response(200, completed_body)

        client = _make_client(sample_config)
        client._client = MagicMock()
        client._client.request.side_effect = [mock_submit_response, mock_poll_response]

        with patch("time.sleep"):
            result = client.research("Deep question?")

        assert isinstance(result, ResearchResult)
        assert result.query == "Deep question?"
        assert result.mode == "research"
        assert result.answer == "Deep answer here."

    def test_research_calls_async_endpoint(self, sample_config: ResearchConfig) -> None:
        """Should POST to the /v1/async/sonar endpoint for the initial submission."""
        submit_body = make_async_submit_response()
        completed_body = make_async_poll_response(status="COMPLETED")

        client = _make_client(sample_config)
        client._client = MagicMock()
        client._client.request.side_effect = [
            _make_mock_response(200, submit_body),
            _make_mock_response(200, completed_body),
        ]

        with patch("time.sleep"):
            client.research("Test question?")

        first_call_args = client._client.request.call_args_list[0][0]
        method_arg, endpoint_arg = first_call_args
        assert method_arg == "POST"
        assert endpoint_arg == "/v1/async/sonar"

    def test_research_polls_until_complete(self, sample_config: ResearchConfig) -> None:
        """Should keep polling until status is 'COMPLETED', making 3 total requests."""
        submit_body = make_async_submit_response(job_id="job_xyz")
        pending_body_one = make_async_poll_response(status="pending")
        pending_body_two = make_async_poll_response(status="pending")
        completed_body = make_async_poll_response(status="COMPLETED")

        client = _make_client(sample_config)
        client._client = MagicMock()
        client._client.request.side_effect = [
            _make_mock_response(200, submit_body),
            _make_mock_response(200, pending_body_one),
            _make_mock_response(200, pending_body_two),
            _make_mock_response(200, completed_body),
        ]

        with patch("time.sleep"):
            client.research("What is deep research?")

        # 1 submit + 2 pending polls + 1 completed poll = 4 total requests
        assert client._client.request.call_count == 4

    @pytest.mark.error_handling
    def test_research_timeout(self, sample_config: ResearchConfig) -> None:
        """Should raise TimeoutError when the job does not complete within the timeout."""
        submit_body = make_async_submit_response()
        pending_body = make_async_poll_response(status="pending")

        client = _make_client(sample_config)
        client._client = MagicMock()
        # Always return pending so it never completes
        client._client.request.side_effect = [
            _make_mock_response(200, submit_body),
        ] + [_make_mock_response(200, pending_body)] * 20

        # Use a counter that exceeds the timeout after the initial calls.
        # Robust against future code adding extra monotonic() calls.
        call_count = 0

        def _advancing_monotonic() -> float:
            nonlocal call_count
            call_count += 1
            return 0.0 if call_count <= 2 else 601.0

        with (
            patch("time.sleep"),
            patch("time.monotonic", side_effect=_advancing_monotonic),
            pytest.raises(TimeoutError),
        ):
            client.research("Slow question?")


# ---------------------------------------------------------------------------
# TestResearchErrorHandling
# ---------------------------------------------------------------------------


class TestResearchErrorHandling:
    """Tests for error paths in PerplexityClient.research."""

    @pytest.mark.error_handling
    def test_submit_response_missing_id_raises_value_error(self, sample_config: ResearchConfig) -> None:
        """Should raise ValueError when the async submit response has no 'id' key."""
        # A response body without the required 'id' field triggers the guard in research().
        submit_body_without_id = {"status": "pending"}
        mock_submit_response = _make_mock_response(200, submit_body_without_id)

        client = _make_client(sample_config)
        client._client = MagicMock()
        client._client.request.return_value = mock_submit_response

        with pytest.raises(ValueError, match="no job ID"):
            client.research("Deep question?")

    @pytest.mark.error_handling
    def test_failed_poll_status_raises_runtime_error(self, sample_config: ResearchConfig) -> None:
        """Should raise RuntimeError when the poll response returns status 'FAILED'."""
        submit_body = make_async_submit_response(job_id="job_fail_test")
        failed_poll_body = {"id": "job_fail_test", "status": "FAILED", "error": "something broke"}

        mock_submit_response = _make_mock_response(200, submit_body)
        mock_failed_poll_response = _make_mock_response(200, failed_poll_body)

        client = _make_client(sample_config)
        client._client = MagicMock()
        client._client.request.side_effect = [mock_submit_response, mock_failed_poll_response]

        with (
            patch("time.sleep"),
            pytest.raises(RuntimeError, match="something broke"),
        ):
            client.research("Will this fail?")

    @pytest.mark.error_handling
    def test_429_retry_after_header_is_honoured(self, sample_config: ResearchConfig) -> None:
        """A 429 with Retry-After: 5 must sleep for 5 seconds before retrying."""
        rate_limit_response = _make_mock_response(429, {}, headers={"Retry-After": "5"})
        rate_limit_response.is_client_error = False  # 429 is retryable, not permanent
        success_response = _make_mock_response(200, make_search_response())

        client = _make_client(sample_config)
        client._client = MagicMock()
        client._client.request.side_effect = [rate_limit_response, success_response]

        with patch("time.sleep") as mock_sleep:
            client._execute_with_retry("POST", "/chat/completions", json={})

        # The Retry-After header value (5) must be used as the sleep duration.
        mock_sleep.assert_called_once_with(5.0)
        assert client._client.request.call_count == 2


# ---------------------------------------------------------------------------
# TestRetryWithBackoff
# ---------------------------------------------------------------------------


class TestRetryWithBackoff:
    """Tests for PerplexityClient._execute_with_retry."""

    def test_retries_on_429(self, sample_config: ResearchConfig) -> None:
        """Should retry after a 429 rate-limit response and succeed on the next attempt."""
        rate_limit_response = _make_mock_response(429, {})
        rate_limit_response.is_client_error = False  # 429 is retryable, not permanent
        success_response = _make_mock_response(200, make_search_response())

        client = _make_client(sample_config)
        client._client = MagicMock()
        client._client.request.side_effect = [rate_limit_response, success_response]

        with patch("time.sleep"):
            client._execute_with_retry("POST", "/chat/completions", json={})

        assert client._client.request.call_count == 2

    def test_retries_on_500(self, sample_config: ResearchConfig) -> None:
        """Should retry after a 500 server error and succeed on the next attempt."""
        server_error_response = _make_mock_response(500, {})
        server_error_response.is_client_error = False
        success_response = _make_mock_response(200, make_search_response())

        client = _make_client(sample_config)
        client._client = MagicMock()
        client._client.request.side_effect = [server_error_response, success_response]

        with patch("time.sleep"):
            client._execute_with_retry("POST", "/chat/completions", json={})

        assert client._client.request.call_count == 2

    def test_retries_on_503(self, sample_config: ResearchConfig) -> None:
        """Should retry after a 503 service-unavailable response and succeed on the next attempt."""
        unavailable_response = _make_mock_response(503, {})
        unavailable_response.is_client_error = False
        success_response = _make_mock_response(200, make_search_response())

        client = _make_client(sample_config)
        client._client = MagicMock()
        client._client.request.side_effect = [unavailable_response, success_response]

        with patch("time.sleep"):
            client._execute_with_retry("POST", "/chat/completions", json={})

        assert client._client.request.call_count == 2

    @pytest.mark.error_handling
    def test_no_retry_on_400(self, sample_config: ResearchConfig) -> None:
        """Should raise HTTPStatusError immediately on a permanent 400 error without retrying."""
        bad_request_response = _make_mock_response(400, {"error": "bad request"})

        client = _make_client(sample_config)
        client._client = MagicMock()
        client._client.request.return_value = bad_request_response

        with pytest.raises(httpx.HTTPStatusError):
            client._execute_with_retry("POST", "/chat/completions", json={})

        # Only one attempt — no retry on permanent 4xx
        assert client._client.request.call_count == 1

    @pytest.mark.error_handling
    def test_respects_max_attempts(self, sample_config: ResearchConfig) -> None:
        """Should stop retrying after retry_max_attempts calls and raise on the last response."""
        always_error_response = _make_mock_response(500, {})
        always_error_response.is_client_error = False

        client = _make_client(sample_config)
        client._client = MagicMock()
        client._client.request.return_value = always_error_response

        with patch("time.sleep"), pytest.raises(httpx.HTTPStatusError):
            client._execute_with_retry("POST", "/chat/completions", json={})

        # test_config.yaml sets retry_max_attempts: 2
        assert client._client.request.call_count == sample_config.retry_max_attempts
