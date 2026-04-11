"""Stack Exchange API v2.3 client.

Thin httpx wrapper that handles pagination, rate limiting, quota tracking,
and response decompression. Keeps business logic out — filtering, scoring,
and output decisions live in processor.py and filters.py.
"""

from __future__ import annotations

import logging
import time
from typing import Any, cast

import httpx

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.stackexchange.com/2.3/"

# Custom filter that includes body_markdown on questions/answers and body on comments.
# Created via https://api.stackexchange.com/docs/create-filter
# Includes: question.body_markdown, answer.body_markdown, comment.body,
#           question.accepted_answer_id, answer.is_accepted
_API_FILTER = "!nNPvSNdWme"

_MAX_PAGE_SIZE = 100
_MAX_IDS_PER_REQUEST = 100
_MAX_RETRIES = 3
_BASE_BACKOFF_SECONDS = 10.0


class StackExchangeClient:
    """Client for the Stack Exchange API v2.3."""

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key
        self._client = httpx.Client(timeout=30.0)
        self._quota_remaining: int | None = None

    @property
    def quota_remaining(self) -> int | None:
        """Return the most recently observed quota_remaining value, or None if no requests made."""
        return self._quota_remaining

    def _request(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        """Make a single API request with retry and backoff handling.

        Args:
            endpoint: API path relative to base URL (e.g., "questions").
            params: Query parameters to include.

        Returns:
            The parsed JSON response wrapper dict.

        Raises:
            httpx.HTTPStatusError: On non-retryable HTTP errors.
        """
        params["filter"] = _API_FILTER
        if self._api_key:
            params["key"] = self._api_key

        url = f"{_BASE_URL}{endpoint}"
        last_exception: Exception | None = None

        for attempt in range(_MAX_RETRIES):
            try:
                response = self._client.get(url, params=params)
                response.raise_for_status()
                data: dict[str, Any] = cast("dict[str, Any]", response.json())

                # Track quota
                if "quota_remaining" in data:
                    self._quota_remaining = int(data["quota_remaining"])

                # Respect mandatory backoff from API
                backoff_seconds = data.get("backoff")
                if backoff_seconds is not None:
                    logger.info("API backoff requested: %d seconds", backoff_seconds)
                    time.sleep(int(backoff_seconds))

                return data

            except httpx.HTTPStatusError as http_error:
                status_code = http_error.response.status_code
                if status_code == 429 or status_code >= 500:
                    delay = _BASE_BACKOFF_SECONDS * (2**attempt)
                    logger.warning(
                        "HTTP %d on attempt %d/%d, retrying in %.0fs",
                        status_code,
                        attempt + 1,
                        _MAX_RETRIES,
                        delay,
                    )
                    last_exception = http_error
                    time.sleep(delay)
                else:
                    raise

        if last_exception is not None:
            raise last_exception
        raise RuntimeError("Request failed with no exception captured")

    def _paginate(
        self,
        endpoint: str,
        params: dict[str, Any],
        max_items: int,
    ) -> list[dict[str, Any]]:
        """Paginate through API results up to max_items.

        Args:
            endpoint: API path.
            params: Base query params (page/pagesize will be set).
            max_items: Maximum total items to return.

        Returns:
            Flat list of item dicts.
        """
        all_items: list[dict[str, Any]] = []
        page = 1
        page_size = min(max_items, _MAX_PAGE_SIZE)
        params["pagesize"] = page_size

        while len(all_items) < max_items:
            params["page"] = page
            data = self._request(endpoint, dict(params))
            items = data.get("items", [])
            all_items.extend(items)

            if not data.get("has_more", False) or not items:
                break
            page += 1

        return all_items[:max_items]

    def get_questions(
        self,
        site: str,
        *,
        tagged: str | None = None,
        sort: str = "votes",
        order: str = "desc",
        max_questions: int = 50,
    ) -> list[dict[str, Any]]:
        """Fetch questions from a Stack Exchange site.

        Args:
            site: SE site slug (e.g., "stackoverflow").
            tagged: Semicolon-separated tags for AND matching.
            sort: Sort field ("activity", "votes", "creation").
            order: Sort order ("asc" or "desc").
            max_questions: Maximum questions to return.

        Returns:
            List of question dicts from the API.
        """
        params: dict[str, Any] = {
            "site": site,
            "sort": sort,
            "order": order,
        }
        if tagged:
            params["tagged"] = tagged
        return self._paginate("questions", params, max_questions)

    def get_answers(
        self,
        question_ids: list[int],
        site: str,
        *,
        sort: str = "votes",
        max_answers_per_question: int = 5,
    ) -> dict[int, list[dict[str, Any]]]:
        """Fetch answers for given question IDs, grouped by question_id.

        Args:
            question_ids: List of question IDs to fetch answers for.
            site: SE site slug.
            sort: Sort field for answers.
            max_answers_per_question: Max answers per question.

        Returns:
            Dict mapping question_id to list of answer dicts.
        """
        result: dict[int, list[dict[str, Any]]] = {qid: [] for qid in question_ids}

        for batch_start in range(0, len(question_ids), _MAX_IDS_PER_REQUEST):
            batch_ids = question_ids[batch_start : batch_start + _MAX_IDS_PER_REQUEST]
            ids_str = ";".join(str(qid) for qid in batch_ids)
            params: dict[str, Any] = {
                "site": site,
                "sort": sort,
                "order": "desc",
            }
            # Fetch more than needed per question to handle batching
            max_items = max_answers_per_question * len(batch_ids)
            items = self._paginate(f"questions/{ids_str}/answers", params, max_items)

            for answer in items:
                question_id = int(answer["question_id"])
                if question_id in result and len(result[question_id]) < max_answers_per_question:
                    result[question_id].append(answer)

        return result

    def get_question_comments(
        self,
        question_ids: list[int],
        site: str,
        *,
        max_comments: int = 30,
    ) -> dict[int, list[dict[str, Any]]]:
        """Fetch comments on questions, grouped by question ID (post_id).

        Args:
            question_ids: List of question IDs.
            site: SE site slug.
            max_comments: Max comments per question.

        Returns:
            Dict mapping question_id to list of comment dicts.
        """
        result: dict[int, list[dict[str, Any]]] = {qid: [] for qid in question_ids}

        for batch_start in range(0, len(question_ids), _MAX_IDS_PER_REQUEST):
            batch_ids = question_ids[batch_start : batch_start + _MAX_IDS_PER_REQUEST]
            ids_str = ";".join(str(qid) for qid in batch_ids)
            params: dict[str, Any] = {"site": site, "sort": "votes", "order": "desc"}
            max_items = max_comments * len(batch_ids)
            items = self._paginate(f"questions/{ids_str}/comments", params, max_items)

            for comment in items:
                post_id = int(comment["post_id"])
                if post_id in result and len(result[post_id]) < max_comments:
                    result[post_id].append(comment)

        return result

    def get_answer_comments(
        self,
        answer_ids: list[int],
        site: str,
        *,
        max_comments: int = 30,
    ) -> dict[int, list[dict[str, Any]]]:
        """Fetch comments on answers, grouped by answer ID (post_id).

        Args:
            answer_ids: List of answer IDs.
            site: SE site slug.
            max_comments: Max comments per answer.

        Returns:
            Dict mapping answer_id to list of comment dicts.
        """
        if not answer_ids:
            return {}
        result: dict[int, list[dict[str, Any]]] = {aid: [] for aid in answer_ids}

        for batch_start in range(0, len(answer_ids), _MAX_IDS_PER_REQUEST):
            batch_ids = answer_ids[batch_start : batch_start + _MAX_IDS_PER_REQUEST]
            ids_str = ";".join(str(aid) for aid in batch_ids)
            params: dict[str, Any] = {"site": site, "sort": "votes", "order": "desc"}
            max_items = max_comments * len(batch_ids)
            items = self._paginate(f"answers/{ids_str}/comments", params, max_items)

            for comment in items:
                post_id = int(comment["post_id"])
                if post_id in result and len(result[post_id]) < max_comments:
                    result[post_id].append(comment)

        return result

    def close(self) -> None:
        """Close the underlying httpx client."""
        self._client.close()
