"""Shared pytest fixtures for the Reddit Tool test suite.

All database fixtures use in-memory SQLite so no disk I/O occurs.
API client fixtures use MagicMock so no real network calls are made.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

if TYPE_CHECKING:
    import sqlite3
    from collections.abc import Generator

import pytest

from deep_thought.reddit.config import RedditConfig, RuleConfig
from deep_thought.reddit.db.schema import initialize_database

# Path to the fixtures directory, used by tests that load files from disk
FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Database fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def in_memory_db() -> Generator[sqlite3.Connection, None, None]:
    """Return a fully initialized in-memory SQLite connection.

    The connection has WAL mode enabled, foreign keys enforced, and all
    migrations applied. Closes automatically after each test.
    """
    connection = initialize_database(":memory:")
    yield connection
    connection.close()


# ---------------------------------------------------------------------------
# Config fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def sample_rule_config() -> RuleConfig:
    """Return a RuleConfig with realistic test values."""
    return RuleConfig(
        name="test_rule",
        subreddit="python",
        sort="top",
        time_filter="week",
        limit=10,
        min_score=10,
        min_comments=2,
        max_age_days=7,
        include_keywords=[],
        exclude_keywords=[],
        include_flair=[],
        exclude_flair=[],
        search_comments=False,
        max_comment_depth=2,
        max_comments=50,
        include_images=False,
        exclude_stickied=False,
        exclude_locked=False,
        replace_more_limit=32,
    )


@pytest.fixture()
def sample_reddit_config(sample_rule_config: RuleConfig) -> RedditConfig:
    """Return a RedditConfig with realistic test values."""
    return RedditConfig(
        client_id_env="REDDIT_CLIENT_ID",
        client_secret_env="REDDIT_CLIENT_SECRET",
        user_agent_env="REDDIT_USER_AGENT",
        max_posts_per_run=100,
        output_dir="data/reddit/export/",
        qdrant_collection="deep_thought_documents",
        rules=[sample_rule_config],
    )


# ---------------------------------------------------------------------------
# Mock client fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_reddit_client() -> MagicMock:
    """Return a mock RedditClient with all methods returning empty lists."""
    client = MagicMock()
    client.get_submissions.return_value = []
    client.get_comments.return_value = []
    return client


# ---------------------------------------------------------------------------
# Mock submission factory
# ---------------------------------------------------------------------------


def make_mock_submission(
    post_id: str = "abc123",
    title: str = "Test Post Title",
    selftext: str = "This is the post body.",
    subreddit_name: str = "python",
    author_name: str = "test_user",
    score: int = 100,
    num_comments: int = 20,
    url: str = "https://www.reddit.com/r/python/comments/abc123/",
    is_video: bool = False,
    flair_text: str | None = None,
    created_utc: float | None = None,
    is_self: bool = True,
    permalink: str | None = None,
    upvote_ratio: float = 0.95,
    stickied: bool = False,
    locked: bool = False,
) -> MagicMock:
    """Return a mock PRAW Submission object with configurable attributes.

    Args:
        post_id: The Reddit post ID string.
        title: The post title.
        selftext: Body text for self posts; empty string for link posts.
        subreddit_name: Display name of the subreddit.
        author_name: Reddit username of the post author.
        score: Upvote score.
        num_comments: Number of comments.
        url: URL the post links to.
        is_video: Whether the post is a video.
        flair_text: Link flair text, or None.
        created_utc: Unix timestamp of post creation. Defaults to one day ago.
        is_self: Whether this is a selfpost (text post).
        permalink: Relative Reddit permalink (e.g. /r/python/comments/abc123/title/).
                   Defaults to a synthetic permalink based on post_id.
        upvote_ratio: Ratio of upvotes to total votes (0.0–1.0). Defaults to 0.95.
        stickied: Whether the post is pinned/stickied by a mod.
        locked: Whether the post has been locked and can no longer receive comments.

    Returns:
        A configured MagicMock representing a PRAW Submission.
    """
    submission = MagicMock()
    submission.id = post_id
    submission.title = title
    submission.selftext = selftext
    submission.score = score
    submission.num_comments = num_comments
    submission.url = url
    submission.is_video = is_video
    submission.link_flair_text = flair_text
    submission.is_self = is_self
    submission.name = f"t3_{post_id}"
    submission.upvote_ratio = upvote_ratio
    submission.stickied = stickied
    submission.locked = locked
    submission.permalink = permalink if permalink is not None else f"/r/{subreddit_name}/comments/{post_id}/test_title/"

    # created_utc defaults to roughly 24 hours ago
    submission.created_utc = created_utc if created_utc is not None else time.time() - 86400

    # Subreddit mock
    subreddit_mock = MagicMock()
    subreddit_mock.display_name = subreddit_name
    submission.subreddit = subreddit_mock

    # Author mock
    author_mock = MagicMock()
    author_mock.__str__ = lambda self: author_name  # type: ignore[method-assign]
    submission.author = author_mock

    # CommentForest mock (empty by default)
    comments_mock = MagicMock()
    comments_mock.__iter__ = lambda self: iter([])  # type: ignore[method-assign]
    submission.comments = comments_mock

    return submission


def make_mock_comment(
    comment_id: str = "comment1",
    body: str = "This is a comment.",
    author_name: str = "commenter",
    score: int = 10,
    parent_id: str = "t3_abc123",
) -> MagicMock:
    """Return a mock PRAW Comment object with configurable attributes.

    Args:
        comment_id: The Reddit comment ID string.
        body: The comment body text.
        author_name: Reddit username of the comment author.
        score: Upvote score.
        parent_id: Parent ID (t3_ prefix for submission, t1_ prefix for another comment).

    Returns:
        A configured MagicMock representing a PRAW Comment.
    """
    comment = MagicMock()
    comment.id = comment_id
    comment.body = body
    comment.score = score
    comment.parent_id = parent_id
    comment.created_utc = time.time() - 3600

    # Author mock
    author_mock = MagicMock()
    author_mock.__str__ = lambda self: author_name  # type: ignore[method-assign]
    comment.author = author_mock

    # Empty replies by default
    replies_mock = MagicMock()
    replies_mock.__iter__ = lambda self: iter([])  # type: ignore[method-assign]
    comment.replies = replies_mock

    return comment


# ---------------------------------------------------------------------------
# Fixture-based versions of the factories
# ---------------------------------------------------------------------------


@pytest.fixture()
def sample_submission() -> MagicMock:
    """Return a mock PRAW Submission with default realistic attributes."""
    return make_mock_submission()


@pytest.fixture()
def sample_comment() -> MagicMock:
    """Return a mock PRAW Comment at the top level of a submission."""
    return make_mock_comment()
