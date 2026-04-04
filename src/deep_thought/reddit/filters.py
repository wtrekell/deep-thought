"""Rule-based filter engine for the Reddit Tool.

Each filter function tests a single attribute of a PRAW Submission object
against the corresponding rule configuration value. All functions are pure
and operate entirely on in-memory objects — no database access.

Filter semantics:
- include list non-empty → submission must match at least one entry
- exclude list non-empty → submission must NOT match any entry
- Empty list → no constraint applied (all pass)
- Keyword matching supports glob wildcards via fnmatch
"""

from __future__ import annotations

import fnmatch
import logging
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from deep_thought.reddit.config import RuleConfig

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Individual filter functions
# ---------------------------------------------------------------------------


def passes_score_filter(submission: Any, min_score: int) -> bool:
    """Check whether a submission meets the minimum score threshold.

    Args:
        submission: A PRAW Submission object.
        min_score: Minimum upvote score required (inclusive).

    Returns:
        True if the submission's score is >= min_score, False otherwise.
    """
    return int(submission.score) >= min_score


def passes_comment_filter(submission: Any, min_comments: int) -> bool:
    """Check whether a submission meets the minimum comment count threshold.

    Args:
        submission: A PRAW Submission object.
        min_comments: Minimum number of comments required (inclusive).

    Returns:
        True if the submission's num_comments is >= min_comments, False otherwise.
    """
    return int(submission.num_comments) >= min_comments


def passes_age_filter(submission: Any, max_age_days: int) -> bool:
    """Check whether a submission was created within the allowed age window.

    Compares the submission's created_utc Unix timestamp against the current
    time. Posts older than max_age_days do not pass.

    Args:
        submission: A PRAW Submission object with a created_utc attribute.
        max_age_days: Maximum allowed age in days (inclusive).

    Returns:
        True if the submission is <= max_age_days old, False otherwise.
    """
    current_timestamp = time.time()
    max_age_seconds = max_age_days * 86400
    post_age_seconds = current_timestamp - float(submission.created_utc)
    return post_age_seconds <= max_age_seconds


def passes_keyword_filter(
    submission: Any,
    include_keywords: list[str],
    exclude_keywords: list[str],
    search_comments: bool,
    comments: list[Any] | None = None,
) -> bool:
    """Check whether a submission's text matches keyword include/exclude rules.

    Uses fnmatch for glob-style wildcard matching (* matches any substring).
    Matching is case-insensitive. The search covers the post title and body
    (selftext) by default; set search_comments=True to also scan comments.

    Args:
        submission: A PRAW Submission object with title and selftext attributes.
        include_keywords: Post must match at least one (glob wildcards supported).
                          Empty list means no constraint — all posts pass.
        exclude_keywords: Post must not match any of these. Empty list means no exclusions.
        search_comments: If True, also search comment bodies for keyword matches.
        comments: Pre-fetched list of PRAW Comment objects (used when search_comments=True).

    Returns:
        True if the submission passes all keyword constraints, False otherwise.
    """
    title_text = str(submission.title).lower()
    body_text = str(submission.selftext).lower()

    comment_texts: list[str] = []
    if search_comments and comments:
        for comment in comments:
            comment_body = getattr(comment, "body", "")
            if comment_body:
                comment_texts.append(str(comment_body).lower())

    searchable_texts = [title_text, body_text] + comment_texts

    def _matches_any_keyword(keywords: list[str]) -> bool:
        """Return True if any searchable text matches any keyword pattern."""
        for keyword_pattern in keywords:
            pattern_lower = keyword_pattern.lower()
            for text in searchable_texts:
                if fnmatch.fnmatch(text, f"*{pattern_lower}*"):
                    return True
        return False

    # include constraint: at least one keyword must match
    if include_keywords and not _matches_any_keyword(include_keywords):
        return False

    # exclude constraint: no keyword must match
    return not (exclude_keywords and _matches_any_keyword(exclude_keywords))


def passes_flair_filter(
    submission: Any,
    include_flair: list[str],
    exclude_flair: list[str],
) -> bool:
    """Check whether a submission's link flair satisfies include/exclude rules.

    Comparison is case-insensitive. A submission with no flair (None) will
    fail a non-empty include list and pass an exclude list (nothing to exclude).

    Args:
        submission: A PRAW Submission object with a link_flair_text attribute.
        include_flair: Only collect posts with these flair values. Empty = all.
        exclude_flair: Skip posts with any of these flair values. Empty = none excluded.

    Returns:
        True if the submission's flair satisfies both constraints, False otherwise.
    """
    raw_flair = submission.link_flair_text
    flair_text: str | None = str(raw_flair).lower() if raw_flair is not None else None

    # include constraint: flair must be in the include list (if non-empty)
    if include_flair:
        if flair_text is None:
            return False
        include_lower = [f.lower() for f in include_flair]
        if flair_text not in include_lower:
            return False

    # exclude constraint: flair must not be in the exclude list (if non-empty)
    if exclude_flair and flair_text is not None:
        exclude_lower = [f.lower() for f in exclude_flair]
        if flair_text in exclude_lower:
            return False

    return True


def passes_stickied_filter(submission: Any, exclude_stickied: bool) -> bool:
    """Check whether a submission passes the stickied exclusion filter.

    Stickied posts are typically mod announcements pinned to the top of a
    subreddit. When exclude_stickied is True, any stickied post is rejected.

    Args:
        submission: A PRAW Submission object with a stickied attribute.
        exclude_stickied: If True, stickied posts do not pass.

    Returns:
        True if the submission passes the filter, False otherwise.
    """
    return not (exclude_stickied and bool(getattr(submission, "stickied", False)))


def passes_locked_filter(submission: Any, exclude_locked: bool) -> bool:
    """Check whether a submission passes the locked exclusion filter.

    Locked posts cannot receive new comments, so the incremental update
    logic (which re-fetches posts with rising comment counts) is wasted
    on them. When exclude_locked is True, any locked post is rejected.

    Args:
        submission: A PRAW Submission object with a locked attribute.
        exclude_locked: If True, locked posts do not pass.

    Returns:
        True if the submission passes the filter, False otherwise.
    """
    return not (exclude_locked and bool(getattr(submission, "locked", False)))


# ---------------------------------------------------------------------------
# Combined filter application
# ---------------------------------------------------------------------------


def apply_rule_filters(
    submission: Any,
    rule_config: RuleConfig,
    comments: list[Any] | None = None,
) -> bool:
    """Apply all rule filters to a submission and return whether it passes.

    Filters are applied in a short-circuit order from cheapest (score) to
    most expensive (keyword). The first failing filter immediately returns False.

    Args:
        submission: A PRAW Submission object to evaluate.
        rule_config: The RuleConfig containing all filter parameters.
        comments: Pre-fetched comments for keyword searching. Required when
                  rule_config.search_comments is True.

    Returns:
        True if the submission passes all configured filters, False otherwise.
    """
    if not passes_score_filter(submission, rule_config.min_score):
        logger.debug(
            "Post %s failed score filter (score=%d, min=%d).",
            submission.id,
            submission.score,
            rule_config.min_score,
        )
        return False

    if not passes_comment_filter(submission, rule_config.min_comments):
        logger.debug(
            "Post %s failed comment filter (count=%d, min=%d).",
            submission.id,
            submission.num_comments,
            rule_config.min_comments,
        )
        return False

    if not passes_stickied_filter(submission, rule_config.exclude_stickied):
        logger.debug("Post %s failed stickied filter (stickied=True).", submission.id)
        return False

    if not passes_locked_filter(submission, rule_config.exclude_locked):
        logger.debug("Post %s failed locked filter (locked=True).", submission.id)
        return False

    if not passes_age_filter(submission, rule_config.max_age_days):
        logger.debug("Post %s failed age filter (max_age_days=%d).", submission.id, rule_config.max_age_days)
        return False

    if not passes_flair_filter(submission, rule_config.include_flair, rule_config.exclude_flair):
        logger.debug("Post %s failed flair filter (flair=%r).", submission.id, submission.link_flair_text)
        return False

    if (rule_config.include_keywords or rule_config.exclude_keywords) and not passes_keyword_filter(
        submission,
        rule_config.include_keywords,
        rule_config.exclude_keywords,
        rule_config.search_comments,
        comments,
    ):
        logger.debug("Post %s failed keyword filter.", submission.id)
        return False

    return True
