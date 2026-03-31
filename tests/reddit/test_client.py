"""Tests for client.py — PRAW wrapper and comment tree flattening.

All PRAW network calls are mocked at the module boundary so no real Reddit
API requests are made during testing.
"""

from __future__ import annotations

import sys
from types import ModuleType
from typing import Any
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Lazy-import helpers
# ---------------------------------------------------------------------------
# praw is not typed; inject a minimal mock into sys.modules before importing
# the module under test so type checks and imports succeed without a real
# praw installation needing to be present.


def _make_praw_mock() -> ModuleType:
    """Return a minimal sys.modules-compatible mock for praw."""
    praw_mock = ModuleType("praw")
    praw_models_mock = ModuleType("praw.models")

    # MoreComments is used in isinstance checks inside _flatten_comment_tree
    praw_models_mock.MoreComments = type("MoreComments", (), {})  # type: ignore[attr-defined]
    praw_mock.Reddit = MagicMock()  # type: ignore[attr-defined]
    praw_mock.models = praw_models_mock  # type: ignore[attr-defined]
    praw_mock.exceptions = ModuleType("praw.exceptions")  # type: ignore[attr-defined]

    return praw_mock


# Inject the mock before importing the module under test
_praw_module = _make_praw_mock()
sys.modules.setdefault("praw", _praw_module)
sys.modules.setdefault("praw.models", _praw_module.models)

from deep_thought.reddit.client import RedditClient, _flatten_comment_tree  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_comment(
    comment_id: str = "c1",
    body: str = "A comment.",
    score: int = 5,
    parent_id: str = "t3_abc",
    replies: list[Any] | None = None,
) -> MagicMock:
    """Build a mock PRAW Comment object."""
    comment = MagicMock()
    comment.id = comment_id
    comment.body = body
    comment.score = score
    comment.parent_id = parent_id

    replies_mock = MagicMock()
    replies_list = replies or []
    replies_mock.__iter__ = lambda self: iter(replies_list)  # type: ignore[method-assign]
    replies_mock.__bool__ = lambda self: bool(replies_list)  # type: ignore[method-assign]
    comment.replies = replies_mock

    # Make isinstance(comment, praw.models.MoreComments) return False
    comment.__class__ = type("Comment", (), {})
    return comment


# ---------------------------------------------------------------------------
# RedditClient initialisation
# ---------------------------------------------------------------------------


class TestRedditClientInit:
    def test_creates_reddit_instance_with_credentials(self) -> None:
        """RedditClient must initialise a PRAW Reddit instance using the provided credentials."""
        mock_reddit_class = MagicMock()
        sys.modules["praw"].Reddit = mock_reddit_class  # type: ignore[attr-defined]

        RedditClient(client_id="test_id", client_secret="test_secret", user_agent="test_agent")

        mock_reddit_class.assert_called_once_with(
            client_id="test_id",
            client_secret="test_secret",
            user_agent="test_agent",
        )


# ---------------------------------------------------------------------------
# RedditClient.get_submissions
# ---------------------------------------------------------------------------


class TestGetSubmissions:
    def _make_client_with_subreddit(self, sort: str = "hot") -> tuple[RedditClient, MagicMock]:
        """Return a RedditClient whose internal PRAW instance is fully mocked."""
        mock_submission = MagicMock()
        mock_submission.id = "post1"

        mock_subreddit = MagicMock()
        mock_subreddit.hot.return_value = [mock_submission]
        mock_subreddit.new.return_value = [mock_submission]
        mock_subreddit.top.return_value = [mock_submission]
        mock_subreddit.rising.return_value = [mock_submission]

        mock_reddit = MagicMock()
        mock_reddit.subreddit.return_value = mock_subreddit

        with patch.object(RedditClient, "__init__", lambda self, **kwargs: None):
            client = RedditClient.__new__(RedditClient)
            client._reddit = mock_reddit  # type: ignore[attr-defined]

        return client, mock_subreddit

    def test_sort_hot_calls_hot(self) -> None:
        """sort='hot' must call subreddit.hot() on the PRAW instance."""
        client, mock_subreddit = self._make_client_with_subreddit()
        client.get_submissions("python", sort="hot", time_filter="week", limit=5)
        mock_subreddit.hot.assert_called_once_with(limit=5)

    def test_sort_new_calls_new(self) -> None:
        """sort='new' must call subreddit.new() on the PRAW instance."""
        client, mock_subreddit = self._make_client_with_subreddit()
        client.get_submissions("python", sort="new", time_filter="week", limit=10)
        mock_subreddit.new.assert_called_once_with(limit=10)

    def test_sort_top_calls_top_with_time_filter(self) -> None:
        """sort='top' must call subreddit.top() with the time_filter argument."""
        client, mock_subreddit = self._make_client_with_subreddit()
        client.get_submissions("python", sort="top", time_filter="month", limit=25)
        mock_subreddit.top.assert_called_once_with(time_filter="month", limit=25)

    def test_sort_rising_calls_rising(self) -> None:
        """sort='rising' must call subreddit.rising() on the PRAW instance."""
        client, mock_subreddit = self._make_client_with_subreddit()
        client.get_submissions("python", sort="rising", time_filter="week", limit=5)
        mock_subreddit.rising.assert_called_once_with(limit=5)

    def test_unknown_sort_falls_back_to_hot(self) -> None:
        """An unrecognised sort string must fall back to hot without raising."""
        client, mock_subreddit = self._make_client_with_subreddit()
        result = client.get_submissions("python", sort="unknown", time_filter="week", limit=5)
        mock_subreddit.hot.assert_called_once()
        assert isinstance(result, list)

    def test_returns_list_of_submissions(self) -> None:
        """get_submissions must return a plain list, not a generator."""
        client, _ = self._make_client_with_subreddit()
        result = client.get_submissions("python", sort="hot", time_filter="week", limit=5)
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# _flatten_comment_tree
# ---------------------------------------------------------------------------


class TestFlattenCommentTree:
    def test_flat_list_of_comments(self) -> None:
        """A list with no nested replies should be flattened as-is."""
        comments = [_make_mock_comment(f"c{i}") for i in range(3)]
        result: list[Any] = []
        _flatten_comment_tree(
            comment_list=comments,
            current_depth=0,
            max_depth=3,
            max_comments=100,
            result=result,
        )
        assert len(result) == 3

    def test_respects_max_comments_cap(self) -> None:
        """Flattening must stop once max_comments is reached."""
        comments = [_make_mock_comment(f"c{i}") for i in range(10)]
        result: list[Any] = []
        _flatten_comment_tree(
            comment_list=comments,
            current_depth=0,
            max_depth=3,
            max_comments=5,
            result=result,
        )
        assert len(result) == 5

    def test_respects_max_depth(self) -> None:
        """Comments deeper than max_depth must not be included."""
        deep_reply = _make_mock_comment("deep")
        top_level = _make_mock_comment("top", replies=[deep_reply])

        # Force isinstance check to fail for MoreComments so the comments are processed
        deep_reply.__class__ = type("Comment", (), {})
        top_level.__class__ = type("Comment", (), {})

        result: list[Any] = []
        _flatten_comment_tree(
            comment_list=[top_level],
            current_depth=0,
            max_depth=0,  # no depth allowed, so replies are skipped
            max_comments=100,
            result=result,
        )
        # max_depth=0 means we only collect depth-0 comments, not their replies
        assert len(result) == 1
        assert result[0].id == "top"

    def test_skips_more_comments_placeholders(self) -> None:
        """MoreComments placeholder objects must be silently skipped.

        We need an object whose isinstance check against the *actual* MoreComments
        class (as imported by client.py) returns True. We import the class from
        praw.models as it is known to client.py and pass a real instance.
        """
        import praw.models  # type: ignore[import-untyped]

        # Build a real MoreComments-compatible object via subclassing to satisfy
        # isinstance; give it the minimal attributes PRAW's class needs.
        more_comments_instance = MagicMock(spec=praw.models.MoreComments)
        more_comments_instance.__class__ = praw.models.MoreComments

        real_comment = _make_mock_comment("real")
        result: list[Any] = []
        _flatten_comment_tree(
            comment_list=[more_comments_instance, real_comment],
            current_depth=0,
            max_depth=3,
            max_comments=100,
            result=result,
        )
        assert len(result) == 1
        assert result[0].id == "real"

    def test_empty_comment_list_returns_empty_result(self) -> None:
        """An empty input list must produce an empty result."""
        result: list[Any] = []
        _flatten_comment_tree(
            comment_list=[],
            current_depth=0,
            max_depth=3,
            max_comments=100,
            result=result,
        )
        assert result == []
