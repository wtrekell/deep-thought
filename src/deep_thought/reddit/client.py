"""PRAW wrapper client for the Reddit Tool.

Wraps the PRAW Reddit instance in a thin class that normalises the API
surface used by the rest of the tool, making it easy to mock in tests.
"""

from __future__ import annotations

import logging
from typing import Any

import praw  # type: ignore[import-untyped]
import praw.models  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# RedditClient
# ---------------------------------------------------------------------------


class RedditClient:
    """Thin wrapper around a read-only PRAW Reddit instance.

    Uses OAuth 2.0 client credentials (script-less read-only mode), so no
    Reddit account credentials are required. PRAW handles rate limiting
    internally (60 requests/minute).
    """

    def __init__(self, client_id: str, client_secret: str, user_agent: str) -> None:
        """Create a read-only PRAW Reddit instance.

        Args:
            client_id: Reddit API application client ID.
            client_secret: Reddit API application client secret.
            user_agent: Descriptive user agent string for the API requests.
        """
        self._reddit = praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent=user_agent,
        )

    def get_submissions(
        self,
        subreddit: str,
        sort: str,
        time_filter: str,
        limit: int,
    ) -> list[Any]:
        """Fetch submissions from a subreddit using the given sort and filter.

        Args:
            subreddit: Subreddit name without the r/ prefix (e.g. "python").
            sort: One of 'new', 'hot', 'top', 'rising'.
            time_filter: For 'top' sort — one of 'hour', 'day', 'week', 'month', 'year', 'all'.
                         Ignored for other sort types.
            limit: Maximum number of submissions to return.

        Returns:
            A list of PRAW Submission objects.

        Raises:
            praw.exceptions.PRAWException: On API errors.
        """
        subreddit_instance = self._reddit.subreddit(subreddit)

        if sort == "new":
            listing = subreddit_instance.new(limit=limit)
        elif sort == "hot":
            listing = subreddit_instance.hot(limit=limit)
        elif sort == "rising":
            listing = subreddit_instance.rising(limit=limit)
        elif sort == "top":
            listing = subreddit_instance.top(time_filter=time_filter, limit=limit)
        else:
            logger.warning("Unknown sort '%s', falling back to 'hot'.", sort)
            listing = subreddit_instance.hot(limit=limit)

        return list(listing)

    def get_comments(
        self,
        submission: Any,
        max_depth: int,
        max_comments: int,
    ) -> list[Any]:
        """Fetch and flatten the comment tree for a submission.

        Replaces MoreComments objects up to the configured limits, then
        performs a depth-first flattening of the tree.

        Args:
            submission: A PRAW Submission object whose comments to fetch.
            max_depth: Maximum comment nesting depth to traverse.
            max_comments: Maximum number of total comments to return.

        Returns:
            A list of PRAW Comment objects, ordered depth-first.
        """
        try:
            submission.comments.replace_more(limit=0)
        except Exception as replace_error:
            logger.warning("Could not replace MoreComments for %s: %s", submission.id, replace_error)

        flattened_comments: list[Any] = []
        _flatten_comment_tree(
            comment_list=list(submission.comments),
            current_depth=0,
            max_depth=max_depth,
            max_comments=max_comments,
            result=flattened_comments,
        )
        return flattened_comments


def _flatten_comment_tree(
    comment_list: list[Any],
    current_depth: int,
    max_depth: int,
    max_comments: int,
    result: list[Any],
) -> None:
    """Recursively flatten a PRAW comment tree into a list in depth-first order.

    Stops when max_depth is reached or max_comments is hit. Skips
    MoreComments placeholder objects (they should have been replaced already).

    Args:
        comment_list: The list of Comment (or MoreComments) objects at this level.
        current_depth: The current recursion depth (0 = top level).
        max_depth: Maximum depth to recurse into.
        max_comments: Hard cap on total comments collected.
        result: Mutable list to append comments into.
    """
    if current_depth > max_depth:
        return

    for comment in comment_list:
        if len(result) >= max_comments:
            return

        # Skip MoreComments placeholders
        if isinstance(comment, praw.models.MoreComments):
            continue

        result.append(comment)

        if hasattr(comment, "replies") and comment.replies and current_depth < max_depth:
            _flatten_comment_tree(
                comment_list=list(comment.replies),
                current_depth=current_depth + 1,
                max_depth=max_depth,
                max_comments=max_comments,
                result=result,
            )
