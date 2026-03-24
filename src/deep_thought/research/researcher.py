"""Perplexity API client for the Research Tool."""

from __future__ import annotations

import contextlib
import logging
import time
from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    from deep_thought.research.config import ResearchConfig
    from deep_thought.research.models import ResearchResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PERPLEXITY_BASE_URL = "https://api.perplexity.ai"
_SYNC_ENDPOINT = "/chat/completions"
_ASYNC_SUBMIT_ENDPOINT = "/async/chat/completions"
_ASYNC_POLL_INTERVAL_SECONDS = 5
_ASYNC_TIMEOUT_SECONDS = 600  # 10 minutes

# HTTP status codes that warrant a retry with exponential backoff.
_RETRYABLE_STATUS_CODES = {429, 500, 503}


# ---------------------------------------------------------------------------
# PerplexityClient
# ---------------------------------------------------------------------------


class PerplexityClient:
    """HTTP client for the Perplexity API with retry and polling support.

    Wraps the synchronous ``/chat/completions`` endpoint for fast search
    queries and the asynchronous ``/async/chat/completions`` endpoint for
    deep research jobs that can take several minutes to complete.

    Create one instance per invocation and call ``close()`` when done, or
    use it as a context manager.
    """

    def __init__(self, api_key: str, config: ResearchConfig) -> None:
        """Initialise the client with credentials and loaded configuration.

        Args:
            api_key: The Perplexity API key used for Bearer authentication.
            config: A loaded ResearchConfig specifying models, retry behaviour,
                and other tool-level settings.
        """
        self._config = config
        self._client = httpx.Client(
            base_url=_PERPLEXITY_BASE_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(30.0, read=300.0),
        )

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    def search(
        self,
        query: str,
        *,
        recency: str | None = None,
        domains: list[str] | None = None,
        context_files: list[str] | None = None,
    ) -> ResearchResult:
        """Run a fast synchronous search query against the Perplexity API.

        Builds a chat-completion request, submits it to the synchronous
        endpoint, and returns a fully parsed ResearchResult.

        Args:
            query: The research question to submit.
            recency: Optional recency filter (e.g. "week", "month").
            domains: Optional list of domains to restrict or exclude.
            context_files: Optional list of local file paths to include as
                prior research context.

        Returns:
            A ResearchResult populated from the API response.

        Raises:
            FileNotFoundError: If any path in context_files does not exist.
            httpx.HTTPStatusError: If the request fails after all retries.
        """
        from deep_thought.research.models import ResearchResult

        resolved_domains = domains or []
        resolved_context_files = context_files or []

        messages = self._build_messages(query, resolved_context_files)
        request_body = self._build_request_body(
            self._config.search_model,
            messages,
            recency,
            resolved_domains,
        )

        logger.debug("Submitting search query to %s", _SYNC_ENDPOINT)
        response_data = self._execute_with_retry("POST", _SYNC_ENDPOINT, json=request_body)

        return ResearchResult.from_api_response(
            response_data,
            query=query,
            mode="search",
            model=self._config.search_model,
            recency=recency,
            domains=resolved_domains,
            context_files=resolved_context_files,
        )

    def research(
        self,
        query: str,
        *,
        recency: str | None = None,
        domains: list[str] | None = None,
        context_files: list[str] | None = None,
    ) -> ResearchResult:
        """Run a deep asynchronous research job against the Perplexity API.

        Submits a job to the async endpoint, then polls until the job
        completes or the timeout is reached.

        Args:
            query: The research question to submit.
            recency: Optional recency filter (e.g. "week", "month").
            domains: Optional list of domains to restrict or exclude.
            context_files: Optional list of local file paths to include as
                prior research context.

        Returns:
            A ResearchResult populated from the completed API response.

        Raises:
            FileNotFoundError: If any path in context_files does not exist.
            TimeoutError: If the job does not complete within 600 seconds.
            httpx.HTTPStatusError: If any request fails after all retries.
        """
        from deep_thought.research.models import ResearchResult

        resolved_domains = domains or []
        resolved_context_files = context_files or []

        messages = self._build_messages(query, resolved_context_files)
        request_body = self._build_request_body(
            self._config.research_model,
            messages,
            recency,
            resolved_domains,
        )

        logger.debug("Submitting deep research job to %s", _ASYNC_SUBMIT_ENDPOINT)
        submit_response = self._execute_with_retry("POST", _ASYNC_SUBMIT_ENDPOINT, json=request_body)
        if "id" not in submit_response:
            response_keys = list(submit_response.keys())
            raise ValueError(f"Async job submission failed: no job ID in API response. Response keys: {response_keys}")
        job_id: str = submit_response["id"]
        logger.debug("Deep research job submitted with ID: %s", job_id)

        poll_url = f"{_ASYNC_SUBMIT_ENDPOINT}/{job_id}"
        elapsed_start = time.monotonic()
        completed_response: dict[str, Any] | None = None

        while True:
            elapsed_seconds = time.monotonic() - elapsed_start
            if elapsed_seconds > _ASYNC_TIMEOUT_SECONDS:
                raise TimeoutError("Deep research timed out after 600 seconds")

            logger.debug("Polling job %s (%.0fs elapsed)", job_id, elapsed_seconds)
            poll_response = self._execute_with_retry("GET", poll_url)

            if poll_response.get("status") == "completed":
                completed_response = poll_response
                break

            time.sleep(_ASYNC_POLL_INTERVAL_SECONDS)

        return ResearchResult.from_api_response(
            completed_response,
            query=query,
            mode="research",
            model=self._config.research_model,
            recency=recency,
            domains=resolved_domains,
            context_files=resolved_context_files,
        )

    def close(self) -> None:
        """Close the underlying HTTP client and release its resources."""
        self._client.close()

    # -----------------------------------------------------------------------
    # Private helpers
    # -----------------------------------------------------------------------

    def _build_messages(self, query: str, context_files: list[str]) -> list[dict[str, str]]:
        """Build the messages list for a chat-completion request.

        When context_files is empty, returns a single user message containing
        just the query. When files are provided, wraps their contents in XML
        ``<prior_research>`` tags and appends a ``<query>`` tag.

        Args:
            query: The research question.
            context_files: Paths to local files to include as prior context.

        Returns:
            A list containing a single user-role message dict.

        Raises:
            FileNotFoundError: If any path in context_files does not exist on disk.
        """
        if not context_files:
            return [{"role": "user", "content": query}]

        file_sections: list[str] = []
        for file_path_string in context_files:
            from pathlib import Path

            file_path = Path(file_path_string)
            if not file_path.exists():
                raise FileNotFoundError(
                    f"Context file not found: {file_path_string}. "
                    "Ensure the path is correct and the file exists before running research."
                )
            file_contents = file_path.read_text(encoding="utf-8")
            file_sections.append(f'<file path="{file_path_string}">\n{file_contents}\n</file>')

        all_files_xml = "\n".join(file_sections)
        assembled_content = f"<prior_research>\n{all_files_xml}\n</prior_research>\n\n<query>{query}</query>"

        return [{"role": "user", "content": assembled_content}]

    def _build_request_body(
        self,
        model: str,
        messages: list[dict[str, str]],
        recency: str | None,
        domains: list[str],
    ) -> dict[str, Any]:
        """Assemble the JSON request body for a chat-completion call.

        Always includes model, messages, and return_related_questions.
        Conditionally adds search_recency_filter and search_domain_filter
        when those parameters carry values.

        Args:
            model: The Perplexity model name to use.
            messages: The prepared messages list.
            recency: Optional recency filter string, or None to omit.
            domains: List of domain filters; omitted from the body if empty.

        Returns:
            A dict ready to be serialised as the request JSON body.
        """
        request_body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "return_related_questions": True,
        }

        if recency is not None:
            request_body["search_recency_filter"] = recency

        if domains:
            request_body["search_domain_filter"] = domains

        return request_body

    def _execute_with_retry(self, method: str, endpoint: str, **kwargs: Any) -> dict[str, Any]:
        """Execute an HTTP request with exponential backoff on transient errors.

        Retries on HTTP 429, 500, and 503 responses for up to
        ``config.retry_max_attempts`` attempts. For 429 responses, honours the
        ``Retry-After`` header when present. Permanent 4xx errors (other than
        429) are raised immediately without retrying.

        Args:
            method: HTTP method string (e.g. "GET", "POST").
            endpoint: The API endpoint path (relative to base URL).
            **kwargs: Additional keyword arguments forwarded to
                ``httpx.Client.request`` (e.g. ``json=...``).

        Returns:
            The parsed JSON response body as a dict.

        Raises:
            httpx.HTTPStatusError: If all retry attempts are exhausted or a
                non-retryable 4xx error is encountered.
        """
        last_response: httpx.Response | None = None

        for attempt in range(self._config.retry_max_attempts):
            response = self._client.request(method, endpoint, **kwargs)
            last_response = response

            if response.status_code in _RETRYABLE_STATUS_CODES:
                if attempt < self._config.retry_max_attempts - 1:
                    retry_delay = float(self._config.retry_base_delay_seconds * (2**attempt))

                    # Honour the Retry-After header for rate-limit responses.
                    if response.status_code == 429:
                        retry_after_header = response.headers.get("Retry-After")
                        if retry_after_header is not None:
                            with contextlib.suppress(ValueError):
                                retry_delay = float(retry_after_header)

                    logger.warning(
                        "Perplexity API returned %d (attempt %d/%d), retrying in %.1fs...",
                        response.status_code,
                        attempt + 1,
                        self._config.retry_max_attempts,
                        retry_delay,
                    )
                    time.sleep(retry_delay)
                continue

            if response.is_client_error:
                # Permanent 4xx error — raise immediately, no retry.
                response.raise_for_status()

            # Success (2xx) or unexpected non-error status.
            result: dict[str, Any] = response.json()
            return result

        # All attempts exhausted — raise on the last response received.
        if last_response is not None:
            last_response.raise_for_status()

        raise RuntimeError("Unexpected state in _execute_with_retry")  # pragma: no cover
