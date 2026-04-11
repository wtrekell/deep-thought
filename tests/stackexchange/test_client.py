"""Tests for deep_thought.stackexchange.client.StackExchangeClient.

All HTTP calls are mocked via unittest.mock so no real network requests are made.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import pytest

from deep_thought.stackexchange.client import StackExchangeClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_response(
    items: list[dict[str, Any]],
    has_more: bool = False,
    quota_remaining: int = 9000,
    backoff: int | None = None,
    status_code: int = 200,
) -> MagicMock:
    """Build a mock httpx.Response for a Stack Exchange API call.

    Args:
        items: The 'items' list returned in the JSON body.
        has_more: Whether there are additional pages of results.
        quota_remaining: Simulated API quota_remaining value.
        backoff: Seconds to backoff if requested by the API, or None.
        status_code: HTTP status code to simulate.

    Returns:
        A MagicMock configured to look like an httpx.Response.
    """
    response_data: dict[str, Any] = {
        "items": items,
        "has_more": has_more,
        "quota_remaining": quota_remaining,
    }
    if backoff is not None:
        response_data["backoff"] = backoff

    mock_response = MagicMock()
    mock_response.status_code = status_code
    mock_response.json.return_value = response_data

    if status_code >= 400:
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            message=f"HTTP {status_code}",
            request=MagicMock(),
            response=mock_response,
        )
    else:
        mock_response.raise_for_status.return_value = None

    return mock_response


# ---------------------------------------------------------------------------
# TestStackExchangeClient
# ---------------------------------------------------------------------------


class TestStackExchangeClient:
    def test_get_questions_calls_correct_endpoint(self) -> None:
        """get_questions should call the 'questions' API endpoint."""
        mock_response = _make_mock_response(items=[])
        client = StackExchangeClient(api_key=None)

        with patch.object(client._client, "get", return_value=mock_response) as mock_get:
            client.get_questions(site="stackoverflow", max_questions=10)

        called_url = mock_get.call_args[0][0]
        assert "questions" in called_url

    def test_get_questions_includes_site_param(self) -> None:
        """get_questions should pass the site parameter in the query string."""
        mock_response = _make_mock_response(items=[])
        client = StackExchangeClient(api_key=None)

        with patch.object(client._client, "get", return_value=mock_response) as mock_get:
            client.get_questions(site="superuser", max_questions=5)

        called_params = mock_get.call_args[1]["params"]
        assert called_params["site"] == "superuser"

    def test_api_key_is_passed_as_param(self) -> None:
        """When an api_key is set, it should be included in the query parameters."""
        mock_response = _make_mock_response(items=[])
        client = StackExchangeClient(api_key="my_test_api_key")

        with patch.object(client._client, "get", return_value=mock_response) as mock_get:
            client.get_questions(site="stackoverflow", max_questions=5)

        called_params = mock_get.call_args[1]["params"]
        assert called_params.get("key") == "my_test_api_key"

    def test_no_api_key_omits_key_param(self) -> None:
        """When no api_key is set, the 'key' parameter should not be in the request."""
        mock_response = _make_mock_response(items=[])
        client = StackExchangeClient(api_key=None)

        with patch.object(client._client, "get", return_value=mock_response) as mock_get:
            client.get_questions(site="stackoverflow", max_questions=5)

        called_params = mock_get.call_args[1]["params"]
        assert "key" not in called_params

    def test_get_questions_returns_list(self) -> None:
        """get_questions should return a plain list of question dicts."""
        items = [{"question_id": 1}, {"question_id": 2}]
        mock_response = _make_mock_response(items=items)
        client = StackExchangeClient(api_key=None)

        with patch.object(client._client, "get", return_value=mock_response):
            result = client.get_questions(site="stackoverflow", max_questions=10)

        assert isinstance(result, list)
        assert len(result) == 2

    def test_quota_remaining_updated_after_request(self) -> None:
        """quota_remaining property should reflect the latest API response value."""
        mock_response = _make_mock_response(items=[], quota_remaining=7777)
        client = StackExchangeClient(api_key=None)

        with patch.object(client._client, "get", return_value=mock_response):
            client.get_questions(site="stackoverflow", max_questions=5)

        assert client.quota_remaining == 7777

    def test_close_calls_underlying_client(self) -> None:
        """close() should close the underlying httpx client."""
        client = StackExchangeClient(api_key=None)
        with patch.object(client._client, "close") as mock_close:
            client.close()
        mock_close.assert_called_once()


# ---------------------------------------------------------------------------
# TestPagination
# ---------------------------------------------------------------------------


class TestPagination:
    def test_multiple_pages_are_fetched(self) -> None:
        """When has_more=True, the client should fetch subsequent pages."""
        page_one_items = [{"question_id": i} for i in range(100)]
        page_two_items = [{"question_id": i} for i in range(100, 120)]

        page_one_response = _make_mock_response(items=page_one_items, has_more=True)
        page_two_response = _make_mock_response(items=page_two_items, has_more=False)

        client = StackExchangeClient(api_key=None)

        with patch.object(client._client, "get", side_effect=[page_one_response, page_two_response]):
            result = client.get_questions(site="stackoverflow", max_questions=200)

        assert len(result) == 120

    def test_max_items_is_respected(self) -> None:
        """The client should stop fetching once max_items is reached."""
        large_items = [{"question_id": i} for i in range(100)]
        mock_response = _make_mock_response(items=large_items, has_more=True)

        client = StackExchangeClient(api_key=None)

        with patch.object(client._client, "get", return_value=mock_response):
            result = client.get_questions(site="stackoverflow", max_questions=50)

        assert len(result) == 50

    def test_stops_when_has_more_is_false(self) -> None:
        """Pagination should stop when has_more=False even if under the max."""
        items = [{"question_id": i} for i in range(10)]
        mock_response = _make_mock_response(items=items, has_more=False)

        client = StackExchangeClient(api_key=None)

        with patch.object(client._client, "get", return_value=mock_response) as mock_get:
            result = client.get_questions(site="stackoverflow", max_questions=500)

        # Should have made only one request because has_more=False
        assert mock_get.call_count == 1
        assert len(result) == 10


# ---------------------------------------------------------------------------
# TestBackoff
# ---------------------------------------------------------------------------


class TestBackoff:
    @pytest.mark.error_handling
    def test_backoff_field_triggers_sleep(self) -> None:
        """When the API response includes a 'backoff' field, the client should sleep for that duration."""
        mock_response = _make_mock_response(items=[], backoff=5)
        client = StackExchangeClient(api_key=None)

        with (
            patch.object(client._client, "get", return_value=mock_response),
            patch("deep_thought.stackexchange.client.time.sleep") as mock_sleep,
        ):
            client.get_questions(site="stackoverflow", max_questions=5)

        mock_sleep.assert_called_once_with(5)

    @pytest.mark.error_handling
    def test_no_backoff_field_does_not_sleep(self) -> None:
        """When the API response has no 'backoff' field, time.sleep should not be called."""
        mock_response = _make_mock_response(items=[])
        client = StackExchangeClient(api_key=None)

        with (
            patch.object(client._client, "get", return_value=mock_response),
            patch("deep_thought.stackexchange.client.time.sleep") as mock_sleep,
        ):
            client.get_questions(site="stackoverflow", max_questions=5)

        mock_sleep.assert_not_called()


# ---------------------------------------------------------------------------
# TestRetry
# ---------------------------------------------------------------------------


class TestRetry:
    @pytest.mark.error_handling
    def test_429_triggers_retry(self) -> None:
        """A 429 response should trigger a retry attempt."""
        rate_limited_response = _make_mock_response(items=[], status_code=429)
        success_response = _make_mock_response(items=[])

        client = StackExchangeClient(api_key=None)

        with (
            patch.object(client._client, "get", side_effect=[rate_limited_response, success_response]),
            patch("deep_thought.stackexchange.client.time.sleep"),
        ):
            result = client.get_questions(site="stackoverflow", max_questions=5)

        assert isinstance(result, list)

    @pytest.mark.error_handling
    def test_500_triggers_retry(self) -> None:
        """A 500 response should trigger a retry attempt."""
        server_error_response = _make_mock_response(items=[], status_code=500)
        success_response = _make_mock_response(items=[])

        client = StackExchangeClient(api_key=None)

        with (
            patch.object(client._client, "get", side_effect=[server_error_response, success_response]),
            patch("deep_thought.stackexchange.client.time.sleep"),
        ):
            result = client.get_questions(site="stackoverflow", max_questions=5)

        assert isinstance(result, list)

    @pytest.mark.error_handling
    def test_non_retryable_error_raises_immediately(self) -> None:
        """A 400 or 404 response should raise HTTPStatusError without retrying."""
        not_found_response = _make_mock_response(items=[], status_code=404)
        client = StackExchangeClient(api_key=None)

        with (
            patch.object(client._client, "get", return_value=not_found_response),
            pytest.raises(httpx.HTTPStatusError),
        ):
            client.get_questions(site="stackoverflow", max_questions=5)
